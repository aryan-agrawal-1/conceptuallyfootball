"""Public, cached Team Style Shape API.

This adapter owns query scoping and cohort assembly.  Formula work remains in
``services.team_style_shape`` so the endpoint and durable unit tests share one
deterministic axis contract.
"""

from __future__ import annotations

from collections.abc import Sequence
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
    Provider,
    ProviderMatchCarry,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchPossession,
    ProviderMatchPossessionBuild,
    ProviderMatchTeamGameStateEpisode,
    TeamSeasonEventProfile,
)
from ingestion.services.possession_context import POSSESSION_CALCULATION_VERSION
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


TEAM_STYLE_SHAPE_API_VERSION = "v1"


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


def _event_key(event) -> tuple[int, int]:
    return event.provider_match_id, event.event_index


class TeamStyleShapeApi(APIView):
    """Expose overall, state-selected, and baseline team style evidence."""

    def get(self, request, canonical_team_id: int):
        try:
            profile = resolve_team_event_profile(request, canonical_team_id)
            match_ref = parse_optional_match(request)
            lens = parse_state_lens(request)
            axis_keys = parse_axis_selection(request)
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
                builder=lambda: self.build_payload(profile, match_ref, lens, axis_keys),
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

        target_overall = self.build_team_scope(
            team_id=profile.team_id,
            events=target_eligible_events,
            match_ids=target_match_ids,
            scope=StateLensScope(),
            evidence=scope_evidence(profile.team_id, target_match_ids, StateLensScope()),
            axis_keys=axis_keys,
        )
        target_selected = self.build_team_scope(
            team_id=profile.team_id,
            events=target_eligible_events,
            match_ids=target_match_ids,
            scope=lens.selected,
            evidence=target_state_metadata["evidence"],
            axis_keys=axis_keys,
        )
        target_baseline = None
        if lens.baseline is not None:
            target_baseline = self.build_team_scope(
                team_id=profile.team_id,
                events=target_eligible_events,
                match_ids=target_match_ids,
                scope=lens.baseline,
                evidence=target_state_metadata["comparison"]["baseline_evidence"],
                axis_keys=axis_keys,
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
        cohort_overall: dict[int, dict] = {}
        cohort_selected: dict[int, dict] = {}
        cohort_baseline: dict[int, dict] = {}

        if match_ref is None:
            for team_id in team_ids:
                team_events = event_queryset(competition_season).filter(team_id=team_id)
                team_match_ids = list(
                    team_events.values_list("provider_match_id", flat=True).distinct()
                )
                team_eligible_events = team_events.filter(
                    provider_match__game_state__eligible=True
                )
                overall_evidence = scope_evidence(
                    team_id,
                    team_match_ids,
                    StateLensScope(),
                )
                selected_evidence = scope_evidence(team_id, team_match_ids, lens.selected)
                cohort_overall[team_id] = self.build_team_scope(
                    team_id=team_id,
                    events=team_eligible_events,
                    match_ids=team_match_ids,
                    scope=StateLensScope(),
                    evidence=overall_evidence,
                    axis_keys=axis_keys,
                )
                cohort_selected[team_id] = self.build_team_scope(
                    team_id=team_id,
                    events=team_eligible_events,
                    match_ids=team_match_ids,
                    scope=lens.selected,
                    evidence=selected_evidence,
                    axis_keys=axis_keys,
                )
                if lens.baseline is not None:
                    cohort_baseline[team_id] = self.build_team_scope(
                        team_id=team_id,
                        events=team_eligible_events,
                        match_ids=team_match_ids,
                        scope=lens.baseline,
                        evidence=scope_evidence(team_id, team_match_ids, lens.baseline),
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

        comparison = {
            "enabled": target_baseline is not None,
            "baseline": target_baseline,
            "selected_minus_baseline": (
                signed_shift(target_selected, target_baseline, selected_distributions)
                if target_baseline is not None
                else None
            ),
            "normalisation_note": (
                "Signed radial values use raw selected-minus-baseline change divided by "
                "the same-axis competition-season p90-minus-p10 spread, clipped to [-1,1]."
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
            "notes": [
                "Percentiles describe how prevalent a style behavior is in this competition-season; they are not quality or outcome grades.",
                "Pass, shot, defensive, state-exposure, and possession semantics are inherited from the Batch 9 contracts.",
                "Counter axes use derived possession evidence; provider-tagged fast-break shots remain a separate observation.",
                "Settled block height uses opponent possessions after the persisted establishment rule and excludes transition defence.",
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
