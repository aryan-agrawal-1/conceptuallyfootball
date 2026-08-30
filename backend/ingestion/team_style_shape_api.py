"""Public, cached Team Style Shape API.

This adapter owns query scoping and cohort assembly.  Formula work remains in
``services.team_style_shape`` so the endpoint and durable unit tests share one
deterministic axis contract.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from hashlib import sha256

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.api_cache import (
    get_or_build_payload_response,
    joined_version,
    model_version,
    stable_cache_key,
)
from ingestion.event_profile_api import (
    event_queryset,
    parse_optional_match,
    profile_source_version,
    resolve_team_event_profile,
    scope_queryset_to_match,
)
from ingestion.models import (
    MatchEventGameState,
    MatchGameStateExclusionReason,
    Provider,
    ProviderMatchCarry,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchPossession,
    ProviderMatchPossessionEvent,
    ProviderMatchPossessionBuild,
    ProviderMatchTeamGameStateEpisode,
    TeamSeasonEventProfile,
)
from ingestion.services.possession_context import POSSESSION_CALCULATION_VERSION
from ingestion.services.game_state import GAME_STATE_CALCULATION_VERSION
from ingestion.services.team_style_shape import (
    DEFAULT_AXIS_KEYS,
    TEAM_STYLE_SHAPE_FORMULA_VERSION,
    add_prevalence_percentile,
    attach_cohort_distributions,
    axis_definitions,
    build_style_cohort,
    signed_shift,
)
from ingestion.state_lens import (
    StateLens,
    StateLensScope,
    parse_state_lens,
    scope_evidence,
    scope_team_events,
    state_lens_metadata,
)


TEAM_STYLE_SHAPE_API_VERSION = "v2"
STYLE_GAME_STATES = ("winning", "drawing", "losing")


def parse_axis_selection(request) -> tuple[str, ...]:
    """Parse a stable comma-separated axis selection for custom views."""

    raw = request.query_params.get("axes")
    if raw in (None, ""):
        raw = request.query_params.get("axis")
    if raw in (None, ""):
        return DEFAULT_AXIS_KEYS
    requested = tuple(dict.fromkeys(value.strip() for value in raw.split(",") if value.strip()))
    if not requested:
        raise DjangoValidationError("axes must contain at least one Team Style Shape axis.")
    unknown = sorted(set(requested) - set(DEFAULT_AXIS_KEYS))
    if unknown:
        raise DjangoValidationError(
            "Unknown Team Style Shape axis: " + ", ".join(unknown) + "."
        )
    return tuple(key for key in DEFAULT_AXIS_KEYS if key in requested)


def parse_game_state_view(request) -> bool:
    """Opt into the small target-team state series used by the chart view."""

    raw = request.query_params.get("include_game_states", "")
    return raw.strip().lower() in {"1", "true", "yes"}


def _event_key(event) -> tuple[int, int]:
    return _row_value(event, "provider_match_id"), _row_value(event, "event_index")


def _row_value(row, name: str, default=None):
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


def _episode_matches_scope(episode, filters: Mapping) -> bool:
    """Match the State Lens predicates without issuing an event subquery."""

    for field in ("state", "goal_difference", "phase", "draw_provenance"):
        expected = filters[field]
        if expected is not None and getattr(episode, field) != expected:
            return False
    return True


def _events_in_scope(event_rows: Sequence[Mapping], episodes: Sequence, scope: StateLensScope, filters: Mapping) -> list:
    """Mirror ``scope_events_to_focal_state`` for one preloaded match/team."""

    minimum_age = scope.minimum_state_age_seconds
    maximum_age = scope.maximum_state_age_seconds
    result = []
    for event in event_rows:
        timeline_seconds = event["timeline_seconds"]
        if timeline_seconds is None:
            continue
        for episode in episodes:
            if not episode.start_second <= timeline_seconds < episode.end_second:
                continue
            if not _episode_matches_scope(episode, filters):
                continue
            if minimum_age is not None and timeline_seconds < episode.state_entry_second + minimum_age:
                continue
            if maximum_age is not None and timeline_seconds >= episode.state_entry_second + maximum_age:
                continue
            result.append(event)
            break
    return result


def _bulk_scope_evidence(
    focal_team_id: int,
    match_ids: Sequence[int],
    scope: StateLensScope,
    episodes_by_key,
    audits_by_match,
) -> dict:
    """Build State Lens exposure metadata from already-loaded source rows."""

    exposure_seconds = 0
    episodes = set()
    included_matches = set()
    for match_id in match_ids:
        for episode in episodes_by_key.get((match_id, focal_team_id), ()):
            if not _episode_matches_scope(episode, scope.event_filters()):
                continue
            start = episode.start_second
            end = episode.end_second
            if scope.minimum_state_age_seconds is not None:
                start = max(
                    start,
                    episode.state_entry_second + scope.minimum_state_age_seconds,
                )
            if scope.maximum_state_age_seconds is not None:
                end = min(
                    end,
                    episode.state_entry_second + scope.maximum_state_age_seconds,
                )
            if end <= start:
                continue
            exposure_seconds += end - start
            episodes.add((episode.provider_match_id, episode.episode_index))
            included_matches.add(episode.provider_match_id)

    audits = [audits_by_match[match_id] for match_id in match_ids if match_id in audits_by_match]
    eligible_matches = sum(bool(audit.eligible) for audit in audits)
    reasons = {}
    for audit in audits:
        if audit.eligible:
            continue
        reason = str(audit.exclusion_reason or MatchGameStateExclusionReason.INVALID_SCORE_REPLAY)
        reasons[reason] = reasons.get(reason, 0) + 1
    missing = len(match_ids) - len(audits)
    if missing:
        key = str(MatchGameStateExclusionReason.INVALID_SCORE_REPLAY)
        reasons[key] = reasons.get(key, 0) + missing
    return {
        "exposure_seconds": exposure_seconds,
        "exposure_minutes": round(exposure_seconds / 60, 2),
        "episode_count": len(episodes),
        "match_count": len(included_matches),
        "matches_included": eligible_matches,
        "matches_excluded": len(match_ids) - eligible_matches,
        "exclusion_reasons": dict(sorted(reasons.items())),
        "formula_version": GAME_STATE_CALCULATION_VERSION,
        "empty": exposure_seconds == 0,
        "reliability": {
            "eligible_only": True,
            "timeline": "half_open_played_seconds",
            "shootouts_included": False,
        },
    }


def _bulk_eligible_refinements(episodes: Sequence) -> dict:
    states = {
        MatchEventGameState.DRAWING: "drawing",
        MatchEventGameState.WINNING: "winning",
        MatchEventGameState.LOSING: "losing",
    }
    return {
        "states": sorted({states[row.state] for row in episodes if row.state in states}),
        "goal_differences": sorted({row.goal_difference for row in episodes}),
        "phases": sorted({row.phase for row in episodes}),
        "draw_provenances": sorted({row.draw_provenance for row in episodes}),
        "state_age_seconds": {
            "minimum": 0 if episodes else None,
            "maximum": max(
                (row.end_second - row.state_entry_second for row in episodes),
                default=None,
            ),
        },
    }


def _load_bulk_style_inputs(competition_season, team_ids: Sequence[int], scopes: dict[str, StateLensScope]) -> dict:
    """Load a season's style inputs once for all team/state cohorts.

    The first implementation evaluated seven querysets per team/state cohort.
    A full competition season therefore performed hundreds of repeated event,
    possession, carry, and episode scans.  This loader keeps the same source
    filters but shares the rows and applies the State Lens in memory.
    """

    provider_match_filter = {
        "provider_match__competition_season": competition_season,
        "provider_match__provider": Provider.WHOSCORED,
    }
    team_ids = tuple(sorted(set(team_ids)))
    match_team_rows = list(
        ProviderMatchEvent.objects.filter(
            **provider_match_filter,
            team_id__in=team_ids,
        ).values_list("provider_match_id", "team_id").distinct()
    )
    match_ids_by_team: dict[int, list[int]] = defaultdict(list)
    all_match_ids = set()
    for match_id, team_id in match_team_rows:
        match_ids_by_team[int(team_id)].append(int(match_id))
        all_match_ids.add(int(match_id))
    for team_id in match_ids_by_team:
        match_ids_by_team[team_id] = sorted(set(match_ids_by_team[team_id]))
    all_match_ids = sorted(all_match_ids)

    event_rows = list(
        ProviderMatchEvent.objects.filter(
            **provider_match_filter,
            provider_match__game_state__eligible=True,
            team_id__in=team_ids,
        )
        .values(
            "id",
            "provider_match_id",
            "event_index",
            "team_id",
            "event_type",
            "x",
            "y",
            "end_x",
            "end_y",
            "outcome_successful",
            "is_progressive_pass",
            "is_box_entry",
            "is_defensive",
            "shot_situation",
            "timeline_seconds",
        )
        .order_by("provider_match_id", "event_index")
    )
    episodes = list(
        ProviderMatchTeamGameStateEpisode.objects.filter(
            provider_match_id__in=all_match_ids,
            focal_team_id__in=team_ids,
        )
        .only(
            "provider_match_id",
            "focal_team_id",
            "episode_index",
            "start_second",
            "end_second",
            "state",
            "goal_difference",
            "phase",
            "draw_provenance",
            "state_entry_second",
        )
        .order_by("provider_match_id", "focal_team_id", "episode_index")
    )
    episodes_by_key: dict[tuple[int, int], list] = defaultdict(list)
    for episode in episodes:
        episodes_by_key[(episode.provider_match_id, episode.focal_team_id)].append(episode)
    audits_by_match = {
        int(audit.provider_match_id): audit
        for audit in ProviderMatchGameState.objects.filter(provider_match_id__in=all_match_ids)
        .only("provider_match_id", "eligible", "exclusion_reason")
    }

    events_by_scope: dict[str, dict[int, list]] = {
        name: defaultdict(list) for name in scopes
    }
    event_ids_by_scope: dict[str, dict[int, set[int]]] = {
        name: defaultdict(set) for name in scopes
    }
    event_keys_by_scope: dict[str, dict[int, set[tuple[int, int]]]] = {
        name: defaultdict(set) for name in scopes
    }
    event_team_by_id = {}
    events_by_match_team: dict[tuple[int, int], list] = defaultdict(list)
    for event in event_rows:
        event_team_by_id[event["id"]] = event["team_id"]
        events_by_match_team[(event["provider_match_id"], event["team_id"])].append(event)
    scoped_names = {
        name: (scope, scope.event_filters())
        for name, scope in scopes.items()
        if not scope.is_default
    }
    for (match_id, team_id), rows in events_by_match_team.items():
        for name, scope in scopes.items():
            scoped_rows = (
                rows
                if scope.is_default
                else _events_in_scope(
                    rows,
                    episodes_by_key.get((match_id, team_id), ()),
                    scope,
                    scoped_names[name][1],
                )
            )
            if not scoped_rows:
                continue
            events_by_scope[name][team_id].extend(scoped_rows)
            event_ids_by_scope[name][team_id].update(event["id"] for event in scoped_rows)
            event_keys_by_scope[name][team_id].update(_event_key(event) for event in scoped_rows)

    possession_rows = list(
        ProviderMatchPossession.objects.filter(
            provider_match_id__in=all_match_ids,
            provider_match__provider=Provider.WHOSCORED,
            build__calculation_version=POSSESSION_CALCULATION_VERSION,
            is_ambiguous=False,
        )
        .values(
            "id",
            "provider_match_id",
            "team_id",
            "is_counter_launch",
            "counter_final_third_arrival",
            "counter_shot",
            "counter_speed_mps",
            "provider_fast_break_shot_count",
            "settled_defensive_average_x",
        )
        .order_by("provider_match_id", "possession_index")
    )
    possession_by_id = {row["id"]: row for row in possession_rows}
    links = ProviderMatchPossessionEvent.objects.filter(
        possession_id__in=possession_by_id,
    ).values_list("possession_id", "event_id", "is_settled_defensive_action")
    own_ids_by_scope: dict[str, dict[int, set[int]]] = {
        name: defaultdict(set) for name in scopes
    }
    settled_ids_by_scope: dict[str, dict[int, set[int]]] = {
        name: defaultdict(set) for name in scopes
    }
    for possession_id, event_id, settled in links:
        event_team = event_team_by_id.get(event_id)
        if event_team is None:
            continue
        possession = possession_by_id[possession_id]
        for name in scopes:
            if event_id not in event_ids_by_scope[name].get(event_team, ()):
                continue
            if possession["team_id"] == event_team:
                own_ids_by_scope[name][event_team].add(possession_id)
            elif settled:
                settled_ids_by_scope[name][event_team].add(possession_id)
    own_by_scope = {
        name: {
            team_id: [possession_by_id[row_id] for row_id in sorted(row_ids)]
            for team_id, row_ids in team_rows.items()
        }
        for name, team_rows in own_ids_by_scope.items()
    }
    settled_by_scope = {
        name: {
            team_id: [possession_by_id[row_id] for row_id in sorted(row_ids)]
            for team_id, row_ids in team_rows.items()
        }
        for name, team_rows in settled_ids_by_scope.items()
    }

    carry_rows = list(
        ProviderMatchCarry.objects.filter(
            provider_match_id__in=all_match_ids,
            provider_match__provider=Provider.WHOSCORED,
            team_id__in=team_ids,
        )
        .values(
            "provider_match_id",
            "start_event_index",
            "team_id",
            "is_progressive_carry",
            "is_final_third_entry",
            "is_box_entry",
            "is_low_confidence",
        )
        .order_by("provider_match_id", "start_event_index")
    )
    carry_by_key = {
        (_row_value(row, "provider_match_id"), _row_value(row, "start_event_index")): row
        for row in carry_rows
    }
    carries_by_scope = {
        name: {
            team_id: [
                carry_by_key[key]
                for key in sorted(event_keys_by_scope[name].get(team_id, ()))
                if key in carry_by_key
            ]
            for team_id in team_ids
        }
        for name in scopes
    }
    evidence_by_scope = {
        name: {
            team_id: _bulk_scope_evidence(
                team_id,
                match_ids_by_team.get(team_id, ()),
                scope,
                episodes_by_key,
                audits_by_match,
            )
            for team_id in team_ids
        }
        for name, scope in scopes.items()
    }
    return {
        "match_ids_by_team": match_ids_by_team,
        "events_by_scope": events_by_scope,
        "event_ids_by_scope": event_ids_by_scope,
        "event_keys_by_scope": event_keys_by_scope,
        "own_by_scope": own_by_scope,
        "settled_by_scope": settled_by_scope,
        "carries_by_scope": carries_by_scope,
        "evidence_by_scope": evidence_by_scope,
        "episodes_by_key": episodes_by_key,
        "audits_by_match": audits_by_match,
        "episodes_by_target": {
            team_id: [
                episode
                for (match_id, focal_team_id), rows in episodes_by_key.items()
                if focal_team_id == team_id
                for episode in rows
            ]
            for team_id in team_ids
        },
    }


def _bulk_scope_rows(data: dict, scope_name: str, team_id: int, match_ids: Sequence[int] | None = None) -> tuple[list, list, list, list]:
    """Return event, possession, settled-block, and carry rows for one cohort."""

    if match_ids is None:
        return (
            data["events_by_scope"][scope_name].get(team_id, []),
            data["own_by_scope"][scope_name].get(team_id, []),
            data["settled_by_scope"][scope_name].get(team_id, []),
            data["carries_by_scope"][scope_name].get(team_id, []),
        )
    match_set = set(match_ids)
    return tuple(
        [row for row in rows if _row_value(row, "provider_match_id") in match_set]
        for rows in (
            data["events_by_scope"][scope_name].get(team_id, []),
            data["own_by_scope"][scope_name].get(team_id, []),
            data["settled_by_scope"][scope_name].get(team_id, []),
            data["carries_by_scope"][scope_name].get(team_id, []),
        )
    )


def _build_bulk_cohort(
    data: dict,
    *,
    scope_name: str,
    scope: StateLensScope,
    team_id: int,
    evidence: dict,
    axis_keys: Sequence[str],
    match_ids: Sequence[int] | None = None,
) -> dict:
    events, possessions, settled_blocks, carries = _bulk_scope_rows(
        data,
        scope_name,
        team_id,
        match_ids,
    )
    return build_style_cohort(
        events,
        exposure_seconds=evidence["exposure_seconds"],
        possessions=possessions,
        settled_blocks=settled_blocks,
        carries=carries,
        scope=scope.public(),
        match_count=evidence["match_count"],
        episode_count=evidence["episode_count"],
        matches_excluded=evidence["matches_excluded"],
        axis_keys=axis_keys,
    )


class TeamStyleShapeApi(APIView):
    """Expose overall, state-selected, and baseline team style evidence."""

    def get(self, request, canonical_team_id: int):
        try:
            profile = resolve_team_event_profile(request, canonical_team_id)
            match_ref = parse_optional_match(request)
            lens = parse_state_lens(request)
            axis_keys = parse_axis_selection(request)
            include_game_states = parse_game_state_view(request)
            competition_season = profile.competition_season
            event_version = model_version(
                ProviderMatchEvent,
                {"provider_match__competition_season": competition_season.id},
            )
            game_state_version = model_version(
                ProviderMatchGameState,
                {"provider_match__competition_season": competition_season.id},
            )
            episode_version = model_version(
                ProviderMatchTeamGameStateEpisode,
                {"provider_match__competition_season": competition_season.id},
            )
            possession_version = model_version(
                ProviderMatchPossessionBuild,
                {"provider_match__competition_season": competition_season.id},
            )
            carry_version = model_version(
                ProviderMatchCarry,
                {"provider_match__competition_season": competition_season.id},
            )
            cache_key = stable_cache_key(
                f"event-profile:{competition_season.id}:team-style-shape",
                {
                    "endpoint": "team-style-shape",
                    "team": canonical_team_id,
                    "profile": profile.id,
                    "match": match_ref,
                    "state_lens": lens.cache_scope(),
                    "axes": axis_keys,
                    "include_game_states": include_game_states,
                    "formula_version": TEAM_STYLE_SHAPE_FORMULA_VERSION,
                    "possession_version": POSSESSION_CALCULATION_VERSION,
                },
            )
            source_version = profile_source_version(
                "team-style-shape",
                profile,
                TEAM_STYLE_SHAPE_API_VERSION,
                TEAM_STYLE_SHAPE_FORMULA_VERSION,
                POSSESSION_CALCULATION_VERSION,
                match_ref,
                lens.source_token(),
                axis_keys,
                event_version,
                game_state_version,
                episode_version,
                possession_version,
                carry_version,
            )
            # MaterializedApiPayload.source_version is bounded to 128 chars;
            # the full joined provenance is intentionally hashed rather than
            # truncated so every source/formula change remains distinct.
            if len(source_version) > 128:
                source_version = f"{TEAM_STYLE_SHAPE_API_VERSION}:{sha256(source_version.encode()).hexdigest()}"
            response, cached = get_or_build_payload_response(
                cache_key=cache_key,
                source_version=source_version,
                builder=lambda: self.build_payload(
                    profile,
                    match_ref,
                    lens,
                    axis_keys,
                    include_game_states=include_game_states,
                ),
            )
            response["X-Materialized-Payload"] = "hit" if cached else "miss"
            return response
        except DjangoValidationError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except TeamSeasonEventProfile.DoesNotExist:
            return Response(
                {"detail": "Public team style-shape profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def build_payload(
        self,
        profile,
        match_ref: int | None,
        lens: StateLens,
        axis_keys: Sequence[str] = DEFAULT_AXIS_KEYS,
        *,
        include_game_states: bool = False,
    ) -> dict:
        competition_season = profile.competition_season
        target_events_all = event_queryset(competition_season).filter(team_id=profile.team_id)
        target_scoped_all, matches, _references = scope_queryset_to_match(
            target_events_all,
            match_ref,
            profile.team_id,
        )
        target_match_ids = list(
            target_scoped_all.values_list("provider_match_id", flat=True).distinct()
        )
        target_eligible_events = target_scoped_all.filter(
            provider_match__game_state__eligible=True
        )
        target_state_metadata = state_lens_metadata(
            profile.team_id,
            target_match_ids,
            lens,
        )

        # A single-match view is useful for raw evidence but has no meaningful
        # same-season team percentile cohort.  Keep the rows available for
        # season views, and explicitly suppress percentiles for a match view.
        profiles = list(
            TeamSeasonEventProfile.objects.filter(
                competition_season=competition_season,
                is_current=True,
            ).select_related("team")
        )
        team_names = {row.team_id: row.team.name for row in profiles}
        team_names[profile.team_id] = profile.team.name
        team_ids = sorted(set(team_names))
        scopes = {"overall": StateLensScope(), "selected": lens.selected}
        if lens.baseline is not None:
            scopes["baseline"] = lens.baseline
        if include_game_states:
            scopes.update({
                state: StateLensScope(state=state)
                for state in STYLE_GAME_STATES
            })
        bulk = _load_bulk_style_inputs(competition_season, team_ids, scopes)
        target_overall_evidence = _bulk_scope_evidence(
            profile.team_id,
            target_match_ids,
            scopes["overall"],
            bulk["episodes_by_key"],
            bulk["audits_by_match"],
        )
        target_overall = _build_bulk_cohort(
            bulk,
            scope_name="overall",
            scope=scopes["overall"],
            team_id=profile.team_id,
            evidence=target_overall_evidence,
            axis_keys=axis_keys,
            match_ids=target_match_ids,
        )
        target_selected = _build_bulk_cohort(
            bulk,
            scope_name="selected",
            scope=scopes["selected"],
            team_id=profile.team_id,
            evidence=target_state_metadata["evidence"],
            axis_keys=axis_keys,
            match_ids=target_match_ids,
        )
        target_baseline = None
        if lens.baseline is not None:
            target_baseline = _build_bulk_cohort(
                bulk,
                scope_name="baseline",
                scope=scopes["baseline"],
                team_id=profile.team_id,
                evidence=target_state_metadata["comparison"]["baseline_evidence"],
                axis_keys=axis_keys,
                match_ids=target_match_ids,
            )
        cohort_overall: dict[int, dict] = {}
        cohort_selected: dict[int, dict] = {}
        cohort_baseline: dict[int, dict] = {}

        if match_ref is None:
            for team_id in team_ids:
                cohort_overall[team_id] = _build_bulk_cohort(
                    bulk,
                    scope_name="overall",
                    scope=scopes["overall"],
                    team_id=team_id,
                    evidence=bulk["evidence_by_scope"]["overall"][team_id],
                    axis_keys=axis_keys,
                )
                cohort_selected[team_id] = _build_bulk_cohort(
                    bulk,
                    scope_name="selected",
                    scope=scopes["selected"],
                    team_id=team_id,
                    evidence=bulk["evidence_by_scope"]["selected"][team_id],
                    axis_keys=axis_keys,
                )
                if lens.baseline is not None:
                    cohort_baseline[team_id] = _build_bulk_cohort(
                        bulk,
                        scope_name="baseline",
                        scope=scopes["baseline"],
                        team_id=team_id,
                        evidence=bulk["evidence_by_scope"]["baseline"][team_id],
                        axis_keys=axis_keys,
                    )

            # A profile can be present before its first event is published; the
            # subject remains visible but does not create a fabricated cohort
            # observation.
            cohort_overall.setdefault(profile.team_id, target_overall)
            cohort_selected.setdefault(profile.team_id, target_selected)
            if target_baseline is not None:
                cohort_baseline.setdefault(profile.team_id, target_baseline)

        overall_distributions = attach_cohort_distributions(
            cohort_overall,
            target_team_id=profile.team_id,
            axis_keys=axis_keys,
            team_names=team_names,
            comparison_available=match_ref is None,
        )
        selected_distributions = attach_cohort_distributions(
            cohort_selected,
            target_team_id=profile.team_id,
            axis_keys=axis_keys,
            team_names=team_names,
            comparison_available=match_ref is None,
        )
        baseline_distributions = (
            attach_cohort_distributions(
                cohort_baseline,
                target_team_id=profile.team_id,
                axis_keys=axis_keys,
                team_names=team_names,
                comparison_available=match_ref is None,
            )
            if target_baseline is not None
            else {}
        )

        # The direct target rows above are not necessarily the same dictionary
        # objects as their cohort copies.  Apply the target's distribution
        # percentile explicitly so the returned row is always authoritative.
        add_prevalence_percentile(target_overall, overall_distributions)
        add_prevalence_percentile(target_selected, selected_distributions)
        if target_baseline is not None:
            add_prevalence_percentile(target_baseline, baseline_distributions)

        target_overall["team_id"] = profile.team_id
        target_overall["team_name"] = profile.team.name
        target_selected["team_id"] = profile.team_id
        target_selected["team_name"] = profile.team.name
        if target_baseline is not None:
            target_baseline["team_id"] = profile.team_id
            target_baseline["team_name"] = profile.team.name

        game_states = None
        if include_game_states:
            game_states = {}
            for state in STYLE_GAME_STATES:
                state_scope = scopes[state]
                state_evidence = _bulk_scope_evidence(
                    profile.team_id,
                    target_match_ids,
                    state_scope,
                    bulk["episodes_by_key"],
                    bulk["audits_by_match"],
                )
                state_cohort = _build_bulk_cohort(
                    bulk,
                    scope_name=state,
                    scope=state_scope,
                    team_id=profile.team_id,
                    evidence=state_evidence,
                    axis_keys=axis_keys,
                    match_ids=target_match_ids,
                )
                state_cohort["team_id"] = profile.team_id
                state_cohort["team_name"] = profile.team.name
                game_states[state] = state_cohort

        comparison = {
            "enabled": target_baseline is not None,
            "baseline": target_baseline,
            "selected_minus_baseline": (
                signed_shift(target_selected, target_baseline, selected_distributions)
                if target_baseline is not None
                else None
            ),
            "normalisation_note": (
                "Horizontal state positions use each axis's all-state competition-season p10-p90 spread; "
                "0 is p10, 100 is p90, and values outside that typical range are clipped with an edge marker."
            ),
        }

        return {
            "contract_version": TEAM_STYLE_SHAPE_API_VERSION,
            "formula_version": TEAM_STYLE_SHAPE_FORMULA_VERSION,
            "percentile_version": "midrank_percentile_v1",
            "canonical_team_id": profile.team_id,
            "canonical_team_name": profile.team.name,
            "competition_season": profile.competition_season_id,
            "competition_code": competition_season.competition.short_code,
            "season_label": competition_season.season.label,
            "selected_match_ref": match_ref,
            "matches": matches,
            "axis_keys": list(axis_keys),
            "axis_definitions": axis_definitions(axis_keys),
            "cohort": {
                "type": "competition_season",
                "competition_season_id": competition_season.id,
                "competition_code": competition_season.competition.short_code,
                "season_label": competition_season.season.label,
                "team_count": len(team_ids) if match_ref is None else 0,
                "teams": [
                    {"team_id": team_id, "team_name": team_names.get(team_id)}
                    for team_id in team_ids
                ] if match_ref is None else [],
                "percentiles_available": match_ref is None,
                "percentile_note": (
                    "Same competition-season current team profiles with eligible state evidence. "
                    "Percentiles describe style prevalence, not quality."
                    if match_ref is None
                    else "Single-match style retains raw evidence; season cohort percentiles are withheld."
                ),
            },
            "state_lens": target_state_metadata,
            "overall": target_overall,
            "selected": target_selected,
            "baseline": target_baseline,
            "distributions": {
                "overall": overall_distributions,
                "selected": selected_distributions,
                "baseline": baseline_distributions if target_baseline is not None else None,
            },
            "comparison": comparison,
            "game_states": game_states,
            "notes": [
                "Percentiles describe how prevalent a style behavior is in this competition-season; they are not quality or outcome grades.",
                "Pass, shot, defensive, state-exposure, and possession semantics are inherited from the Batch 9 contracts.",
                "Counter starts begin with a non-restart recovery or control change at or behind x=60 and are tracked for 12 seconds; final-third and shot outcomes require at least 21 metres of forward progress.",
                "Settled block height uses opponent possessions after the persisted establishment rule and excludes transition defence; defensive-action height includes all qualified defensive events.",
                "Lead ownership, result attribution, and causal quality claims are outside this profile.",
            ],
        }

    @staticmethod
    def build_team_scope(
        *,
        team_id: int,
        events,
        match_ids: list[int],
        scope: StateLensScope,
        evidence: dict,
        axis_keys: Sequence[str],
    ) -> dict:
        scoped_events = scope_team_events(events, team_id, scope)
        scoped_event_ids = scoped_events.values("id")
        scoped_event_rows = list(
            scoped_events.order_by(
                "provider_match__kickoff_at",
                "provider_match_id",
                "event_index",
            )
        )
        possession_base = ProviderMatchPossession.objects.filter(
            provider_match__provider=Provider.WHOSCORED,
            provider_match_id__in=match_ids,
            build__calculation_version=POSSESSION_CALCULATION_VERSION,
            is_ambiguous=False,
        )
        own_possessions = possession_base.filter(
            team_id=team_id,
            event_links__event_id__in=scoped_event_ids,
        ).distinct()
        # Keep settled blocks separate from own counter possessions.  The
        # event-link flag is the persisted #112 boundary for settled defence.
        settled_blocks = possession_base.exclude(team_id=team_id).filter(
            event_links__event_id__in=scoped_event_ids,
            event_links__is_settled_defensive_action=True,
        ).distinct()
        carry_rows = list(
            ProviderMatchCarry.objects.filter(
                provider_match__provider=Provider.WHOSCORED,
                provider_match_id__in=match_ids,
                team_id=team_id,
            )
        )
        scoped_event_keys = {_event_key(event) for event in scoped_event_rows}
        carry_rows = [
            carry for carry in carry_rows
            if (carry.provider_match_id, carry.start_event_index) in scoped_event_keys
        ]
        return build_style_cohort(
            scoped_event_rows,
            exposure_seconds=evidence["exposure_seconds"],
            possessions=list(own_possessions),
            settled_blocks=list(settled_blocks),
            carries=carry_rows,
            scope=scope.public(),
            match_count=evidence["match_count"],
            episode_count=evidence["episode_count"],
            matches_excluded=evidence["matches_excluded"],
            axis_keys=axis_keys,
        )
