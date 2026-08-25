from __future__ import annotations

from collections.abc import Callable

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.api_cache import (
    get_or_build_payload_response,
    joined_version,
    model_version,
    stable_cache_key,
)
from ingestion.derived_api import _resolve_competition_season
from ingestion.models import (
    EventProfileSplitType,
    MatchEventType,
    PlayerSeasonDerivedStats,
    PlayerSeasonEventProfile,
    PlayerSeasonGkDerivedStats,
    Provider,
    ProviderMatch,
    ProviderMatchCarry,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchTeamGameStateEpisode,
    TeamSeasonEventProfile,
)
from ingestion.services.event_profiles import (
    FORMULA_VERSION,
    _grid,
    _pass_flow,
    _summary,
    event_profile_availability,
)
from ingestion.state_lens import (
    parse_state_lens,
    scope_team_events,
    state_lens_metadata,
)


PASS_RESPONSE_LIMIT = 5_000
COORDINATE_SCALE = 100
EVENT_PROFILE_API_VERSION = "v4"

PLAYER_SUMMARY_FIELDS = (
    "minutes",
    "observed_event_minutes",
    "valid_location_actions",
    "touches",
    "pass_attempts",
    "pass_completions",
    "progressive_pass_attempts",
    "progressive_pass_completions",
    "final_third_entries",
    "box_entries",
    "key_passes",
    "crosses",
    "long_balls",
    "shots",
    "goals",
    "big_chance_shots",
    "take_ons_attempted",
    "take_ons_successful",
    "defensive_actions",
)

TEAM_SUMMARY_FIELDS = (
    "valid_location_actions",
    "touches",
    "pass_attempts",
    "pass_completions",
    "progressive_pass_attempts",
    "progressive_pass_completions",
    "final_third_entries",
    "box_entries",
    "key_passes",
    "crosses",
    "long_balls",
    "shots_for",
    "goals_for",
    "big_chance_shots_for",
    "shots_against",
    "goals_against",
    "big_chance_shots_against",
    "take_ons_attempted",
    "take_ons_successful",
    "defensive_actions",
)


def resolve_event_profile_competition_season(request):
    competition = (request.query_params.get("competition") or "").strip().upper()
    if competition in {"BIG5", "ALL"}:
        raise DjangoValidationError("Event profiles require a concrete competition-season.")
    return _resolve_competition_season(request)


def resolve_team_event_profile(request, canonical_team_id: int) -> TeamSeasonEventProfile:
    """Resolve the canonical public profile shared by team event-analysis APIs."""
    competition_season = resolve_event_profile_competition_season(request)
    return TeamSeasonEventProfile.objects.select_related(
        "team",
        "competition_season__competition",
        "competition_season__season",
        "materialized_ingestion_run",
    ).get(
        competition_season=competition_season,
        team_id=canonical_team_id,
        is_current=True,
    )


def player_profile_queryset(competition_season, canonical_player_id: int, team_id: int | None):
    queryset = PlayerSeasonEventProfile.objects.filter(
        competition_season=competition_season,
        player_id=canonical_player_id,
        is_current=True,
    ).select_related("player", "team", "competition_season__competition", "competition_season__season")
    if team_id is None:
        return queryset.filter(split_type=EventProfileSplitType.SEASON_TOTAL, team__isnull=True)
    return queryset.filter(split_type=EventProfileSplitType.TEAM, team_id=team_id)


def parse_optional_team(request) -> int | None:
    value = request.query_params.get("team")
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise DjangoValidationError("team must be a canonical team ID.") from exc


def availability_for_player(profile: PlayerSeasonEventProfile) -> dict:
    located_touches = (
        sum(cell.get("raw_count", 0) for cell in profile.action_grid)
        if profile.formula_version == FORMULA_VERSION
        else 0
    )
    return event_profile_availability(
        profile.pass_attempts,
        profile.shots,
        located_touches,
    )


def coverage_for_player(profile: PlayerSeasonEventProfile) -> dict:
    run_coverage = profile.materialized_ingestion_run.stats.get("coverage", {})
    competition_season = profile.competition_season
    expected_matches = (
        round(
            competition_season.whoscored_expected_match_count
            * 2
            / competition_season.expected_team_count
        )
        if competition_season.whoscored_expected_match_count
        and competition_season.expected_team_count
        else None
    )
    return {
        "observed_matches": profile.observed_match_count,
        "expected_matches": expected_matches,
        "observed_event_minutes": profile.observed_event_minutes,
        "competition_observed_matches": run_coverage.get("observed_matches"),
        "competition_completed_matches": run_coverage.get("completed_matches"),
        "competition_expected_matches": run_coverage.get("expected_matches"),
        "competition_complete": bool(run_coverage.get("complete", False)),
    }


def materialization_metadata(profile) -> dict:
    return {
        "formula_version": profile.formula_version,
        "materialization_run_id": profile.materialized_ingestion_run_id,
        "profile_version": profile.id,
        "materialized_at": profile.created_at.isoformat(),
    }


def profile_source_version(endpoint: str, profile, *parts) -> str:
    return joined_version(
        endpoint,
        EVENT_PROFILE_API_VERSION,
        profile.competition_season_id,
        profile.formula_version,
        profile.materialized_ingestion_run_id,
        profile.id,
        *parts,
    )


def event_queryset(competition_season) -> QuerySet[ProviderMatchEvent]:
    return ProviderMatchEvent.objects.filter(
        provider_match__competition_season=competition_season,
        provider_match__provider=Provider.WHOSCORED,
    ).select_related(
        "provider_match",
        "provider_match__home_team",
        "provider_match__away_team",
        "player",
        "team",
    )


def player_event_queryset(profile: PlayerSeasonEventProfile) -> QuerySet[ProviderMatchEvent]:
    queryset = event_queryset(profile.competition_season).filter(player_id=profile.player_id)
    if profile.team_id is not None:
        queryset = queryset.filter(team_id=profile.team_id)
    return queryset


def compact_match_lookup(
    provider_matches: list[ProviderMatch],
    subject_team_ids: dict[int, int],
) -> tuple[list[dict], dict[int, int]]:
    ordered = sorted(provider_matches, key=lambda match: (match.kickoff_at, match.id))
    references = {match.id: index for index, match in enumerate(ordered)}
    lookup = [
        {
            "ref": references[match.id],
            "kickoff_at": match.kickoff_at.isoformat(),
            "home_team_id": match.home_team_id,
            "home_team_name": match.home_team.name if match.home_team else None,
            "away_team_id": match.away_team_id,
            "away_team_name": match.away_team.name if match.away_team else None,
            "subject_team_id": subject_team_ids.get(match.id),
            "home_score": match.home_score,
            "away_score": match.away_score,
        }
        for match in ordered
    ]
    return lookup, references


def parse_optional_match(request) -> int | None:
    value = request.query_params.get("match")
    if value in (None, ""):
        return None
    try:
        match_ref = int(value)
    except ValueError as exc:
        raise DjangoValidationError("match must be a match reference from this event profile.") from exc
    if match_ref < 0:
        raise DjangoValidationError("match must be a match reference from this event profile.")
    return match_ref


def scope_queryset_to_match(
    queryset: QuerySet[ProviderMatchEvent],
    match_ref: int | None,
    subject_team_id: int | None = None,
) -> tuple[QuerySet[ProviderMatchEvent], list[dict], dict[int, int]]:
    match_ids = queryset.values_list("provider_match_id", flat=True).distinct()
    provider_matches = list(
        ProviderMatch.objects.filter(id__in=match_ids).select_related("home_team", "away_team")
    )
    subject_team_ids = (
        {match.id: subject_team_id for match in provider_matches}
        if subject_team_id is not None
        else dict(
            queryset.exclude(team_id__isnull=True)
            .values_list("provider_match_id", "team_id")
            .distinct()
        )
    )
    matches, references = compact_match_lookup(provider_matches, subject_team_ids)
    if match_ref is None:
        return queryset, matches, references
    selected_match_ids = [
        match_id for match_id, reference in references.items() if reference == match_ref
    ]
    if not selected_match_ids:
        raise DjangoValidationError("match is not available in this event profile.")
    return queryset.filter(provider_match_id__in=selected_match_ids), matches, references


def public_coordinate(value: int | None) -> float | None:
    if value is None:
        return None
    return value / COORDINATE_SCALE


def compact_shot(event: ProviderMatchEvent, match_references: dict[int, int]) -> dict:
    return {
        "match_ref": match_references[event.provider_match_id],
        "team_id": event.team_id,
        "event_index": event.event_index,
        "match_seconds": event.match_seconds,
        "x": public_coordinate(event.x),
        "y": public_coordinate(event.y),
        "outcome": event.get_shot_outcome_display(),
        "body_part": event.get_body_part_display(),
        "situation": event.get_shot_situation_display(),
        "big_chance": event.is_big_chance,
        "assisted": event.is_shot_assist,
        "goal_mouth_y": public_coordinate(event.goal_mouth_y),
        "goal_mouth_z": public_coordinate(event.goal_mouth_z),
        "blocked_x": public_coordinate(event.blocked_x),
        "blocked_y": public_coordinate(event.blocked_y),
        "player_id": event.player_id,
        "player_name": event.player.display_name if event.player else None,
    }


def compact_pass(event: ProviderMatchEvent, match_references: dict[int, int]) -> dict:
    return {
        "match_ref": match_references[event.provider_match_id],
        "team_id": event.team_id,
        "event_index": event.event_index,
        "match_seconds": event.match_seconds,
        "x": public_coordinate(event.x),
        "y": public_coordinate(event.y),
        "end_x": public_coordinate(event.end_x),
        "end_y": public_coordinate(event.end_y),
        "completed": event.outcome_successful is True,
        "progressive": event.is_progressive_pass,
        "final_third_entry": event.is_final_third_entry,
        "box_entry": event.is_box_entry,
        "key_pass": event.is_key_pass,
        "cross": event.is_cross,
        "long_ball": event.is_long_ball,
    }


def compact_carry(carry: ProviderMatchCarry, match_references: dict[int, int]) -> dict:
    return {
        "match_ref": match_references[carry.provider_match_id],
        "team_id": carry.team_id,
        "start_event_index": carry.start_event_index,
        "end_event_index": carry.end_event_index,
        "match_seconds": carry.match_seconds,
        "x": public_coordinate(carry.x),
        "y": public_coordinate(carry.y),
        "end_x": public_coordinate(carry.end_x),
        "end_y": public_coordinate(carry.end_y),
        "progressive": carry.is_progressive_carry,
        "final_third_entry": carry.is_final_third_entry,
        "box_entry": carry.is_box_entry,
        "low_confidence": carry.is_low_confidence,
    }


PASS_FILTERS: dict[str, Callable[[QuerySet], QuerySet]] = {
    "all": lambda queryset: queryset,
    "progressive": lambda queryset: queryset.filter(is_progressive_pass=True),
    "final_third_entry": lambda queryset: queryset.filter(is_final_third_entry=True),
    "box_entry": lambda queryset: queryset.filter(is_box_entry=True),
    "key_pass": lambda queryset: queryset.filter(is_key_pass=True),
    "cross": lambda queryset: queryset.filter(is_cross=True),
    "long_ball": lambda queryset: queryset.filter(is_long_ball=True),
}

CARRY_FILTERS: dict[str, Callable[[QuerySet], QuerySet]] = {
    "all": lambda queryset: queryset,
    "progressive": lambda queryset: queryset.filter(is_progressive_carry=True),
    "final_third_entry": lambda queryset: queryset.filter(is_final_third_entry=True),
    "box_entry": lambda queryset: queryset.filter(is_box_entry=True),
    "key_pass": lambda queryset: queryset.none(),
    "cross": lambda queryset: queryset.none(),
    "long_ball": lambda queryset: queryset.none(),
}

PASS_OUTCOMES: dict[str, Callable[[QuerySet], QuerySet]] = {
    "all": lambda queryset: queryset,
    "completed": lambda queryset: queryset.filter(outcome_successful=True),
    "incomplete": lambda queryset: queryset.filter(outcome_successful=False),
}

PASS_FILTER_ALIASES = {
    "final-third-entry": "final_third_entry",
    "final_third_entries": "final_third_entry",
    "box-entry": "box_entry",
    "box_entries": "box_entry",
    "key-pass": "key_pass",
    "key_passes": "key_pass",
    "crosses": "cross",
    "long-ball": "long_ball",
    "long_balls": "long_ball",
}

PASS_OUTCOME_ALIASES = {
    "failed": "incomplete",
    "failed_passes": "incomplete",
    "successful": "completed",
    "unsuccessful": "incomplete",
}


def normalized_pass_filter(request) -> tuple[str, str]:
    requested = (request.query_params.get("filter") or "all").strip().lower()
    legacy_outcome = None
    if requested in {"completed", "all_completed"}:
        requested = "all"
        legacy_outcome = "completed"
    elif requested in {"failed", "failed_passes"}:
        requested = "all"
        legacy_outcome = "incomplete"
    value = PASS_FILTER_ALIASES.get(requested, requested)
    if value not in PASS_FILTERS:
        raise DjangoValidationError(
            "Unsupported pass filter. Use all, progressive, final_third_entry, box_entry, "
            "key_pass, cross, or long_ball."
        )
    requested_outcome = (request.query_params.get("outcome") or legacy_outcome or "all").strip().lower()
    outcome = PASS_OUTCOME_ALIASES.get(requested_outcome, requested_outcome)
    if outcome not in PASS_OUTCOMES:
        raise DjangoValidationError("Unsupported pass outcome. Use all, completed, or incomplete.")
    return value, outcome


class PlayerEventProfileMixin:
    def resolve_profile(self, request, canonical_player_id: int) -> PlayerSeasonEventProfile:
        competition_season = resolve_event_profile_competition_season(request)
        team_id = parse_optional_team(request)
        has_outfield_profile = PlayerSeasonDerivedStats.objects.filter(
            competition_season=competition_season,
            canonical_player_id=canonical_player_id,
            is_current=True,
        ).exists()
        has_goalkeeper_profile = PlayerSeasonGkDerivedStats.objects.filter(
            competition_season=competition_season,
            canonical_player_id=canonical_player_id,
            is_current=True,
        ).exists()
        if not has_outfield_profile and not has_goalkeeper_profile:
            raise PlayerSeasonEventProfile.DoesNotExist
        profile = player_profile_queryset(competition_season, canonical_player_id, team_id).first()
        if profile is None or not any(
            module["available"] for module in availability_for_player(profile).values()
        ):
            raise PlayerSeasonEventProfile.DoesNotExist
        return profile


class PlayerEventProfileApi(PlayerEventProfileMixin, APIView):
    def get(self, request, canonical_player_id: int):
        try:
            profile = self.resolve_profile(request, canonical_player_id)
            match_ref = parse_optional_match(request)
            cache_key = stable_cache_key(
                f"event-profile:{profile.competition_season_id}:player",
                {
                    "endpoint": "player",
                    "player": canonical_player_id,
                    "competition": profile.competition_season.competition.short_code,
                    "season": profile.competition_season.season.label,
                    "team": profile.team_id,
                    "match": match_ref,
                    "formula_version": profile.formula_version,
                    "materialization_run": profile.materialized_ingestion_run_id,
                    "profile_version": profile.id,
                },
            )
            response, _ = get_or_build_payload_response(
                cache_key=cache_key,
                source_version=profile_source_version("player", profile, match_ref),
                builder=lambda: self.build_payload(profile, match_ref),
            )
            return response
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PlayerSeasonEventProfile.DoesNotExist:
            return Response(
                {"detail": "Public player event profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def build_payload(self, profile: PlayerSeasonEventProfile, match_ref: int | None) -> dict:
        scoped_queryset, matches, references = scope_queryset_to_match(
            player_event_queryset(profile), match_ref
        )
        shots = list(
            scoped_queryset.filter(event_type=MatchEventType.SHOT).order_by(
                "provider_match__kickoff_at", "provider_match_id", "event_index"
            )
        )
        if match_ref is None:
            summary = {field: getattr(profile, field) for field in PLAYER_SUMMARY_FIELDS}
            touch_grid = profile.action_grid if profile.formula_version == FORMULA_VERSION else []
            located_touch_count = sum(cell.get("raw_count", 0) for cell in touch_grid)
            average_touch_x = profile.average_touch_x
            average_touch_y = profile.average_touch_y
        else:
            events = list(scoped_queryset)
            summary_values = _summary(events)
            observed_minutes = max(
                (
                    event.expanded_minute
                    if event.expanded_minute is not None
                    else event.minute
                )
                for event in events
            ) if events else 0
            summary = {
                field: summary_values[field]
                for field in PLAYER_SUMMARY_FIELDS
                if field not in {"minutes", "observed_event_minutes"}
            }
            summary.update({
                "minutes": observed_minutes,
                "observed_event_minutes": observed_minutes,
            })
            touch_grid, located_touch_count = _grid(events, 90, touches_only=True)
            average_touch_x = summary_values["average_touch_x"]
            average_touch_y = summary_values["average_touch_y"]
        return {
            "canonical_player_id": profile.player_id,
            "canonical_player_name": profile.player.display_name,
            "canonical_team_id": profile.team_id,
            "canonical_team_name": profile.team.name if profile.team else None,
            "split_type": profile.split_type,
            "competition_season": profile.competition_season_id,
            "competition_code": profile.competition_season.competition.short_code,
            "season_label": profile.competition_season.season.label,
            "coverage": coverage_for_player(profile),
            "availability": availability_for_player(profile),
            "materialization": materialization_metadata(profile),
            "summary": summary,
            "average_touch_location": {
                "x": public_coordinate(average_touch_x),
                "y": public_coordinate(average_touch_y),
                "sample_size": located_touch_count,
            },
            "touch_grid": touch_grid,
            "action_grid": touch_grid,
            "shots": [compact_shot(event, references) for event in shots],
            "matches": matches,
            "selected_match_ref": match_ref,
        }


class PlayerEventProfilePassesApi(PlayerEventProfileMixin, APIView):
    def get(self, request, canonical_player_id: int):
        try:
            profile = self.resolve_profile(request, canonical_player_id)
            pass_filter, pass_outcome = normalized_pass_filter(request)
            match_ref = parse_optional_match(request)
            carry_version = model_version(
                ProviderMatchCarry,
                {"provider_match__competition_season": profile.competition_season_id},
            )
            cache_key = stable_cache_key(
                f"event-profile:{profile.competition_season_id}:player-passes",
                {
                    "endpoint": "player-passes",
                    "player": canonical_player_id,
                    "competition": profile.competition_season.competition.short_code,
                    "season": profile.competition_season.season.label,
                    "team": profile.team_id,
                    "pass_filter": pass_filter,
                    "pass_outcome": pass_outcome,
                    "match": match_ref,
                    "formula_version": profile.formula_version,
                    "materialization_run": profile.materialized_ingestion_run_id,
                    "profile_version": profile.id,
                },
            )
            response, _ = get_or_build_payload_response(
                cache_key=cache_key,
                source_version=profile_source_version(
                    "player-passes", profile, pass_filter, pass_outcome, match_ref, carry_version
                ),
                builder=lambda: self.build_payload(profile, pass_filter, pass_outcome, match_ref),
            )
            return response
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PlayerSeasonEventProfile.DoesNotExist:
            return Response(
                {"detail": "Public player event profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def build_payload(
        self,
        profile: PlayerSeasonEventProfile,
        pass_filter: str,
        pass_outcome: str,
        match_ref: int | None,
    ) -> dict:
        base_queryset = player_event_queryset(profile)
        queryset, matches, references = scope_queryset_to_match(base_queryset, match_ref)
        scoped_events = queryset
        queryset = queryset.filter(event_type=MatchEventType.PASS)
        queryset = PASS_FILTERS[pass_filter](queryset)
        queryset = PASS_OUTCOMES[pass_outcome](queryset)
        total_matching_count = queryset.count()
        events = list(
            queryset.order_by("provider_match__kickoff_at", "provider_match_id", "event_index")[
                :PASS_RESPONSE_LIMIT
            ]
        )
        all_carries_queryset = self.derived_carries(profile, scoped_events)
        total_all_carry_count = all_carries_queryset.count()
        carries_queryset = CARRY_FILTERS[pass_filter](all_carries_queryset)
        total_carry_count = carries_queryset.count()
        carries = list(carries_queryset[:PASS_RESPONSE_LIMIT])
        return {
            "canonical_player_id": profile.player_id,
            "canonical_team_id": profile.team_id,
            "competition_season": profile.competition_season_id,
            "competition_code": profile.competition_season.competition.short_code,
            "season_label": profile.competition_season.season.label,
            "filter": pass_filter,
            "outcome": pass_outcome,
            "total_matching_count": total_matching_count,
            "truncated": total_matching_count > PASS_RESPONSE_LIMIT,
            "total_carry_count": total_carry_count,
            "total_all_carry_count": total_all_carry_count,
            "carries_truncated": total_carry_count > PASS_RESPONSE_LIMIT,
            "materialization": materialization_metadata(profile),
            "passes": [compact_pass(event, references) for event in events],
            "carries": [compact_carry(carry, references) for carry in carries],
            "matches": matches,
            "selected_match_ref": match_ref,
        }

    def derived_carries(
        self,
        profile: PlayerSeasonEventProfile,
        scoped_events: QuerySet[ProviderMatchEvent],
    ):
        """All derived carries for the same player, team and match scope."""
        scoped_match_ids = scoped_events.values_list("provider_match_id", flat=True).distinct()
        carries_queryset = ProviderMatchCarry.objects.filter(
            player_id=profile.player_id,
            provider_match_id__in=scoped_match_ids,
        )
        if profile.team_id is not None:
            carries_queryset = carries_queryset.filter(team_id=profile.team_id)
        return carries_queryset.select_related("provider_match").order_by(
            "provider_match__kickoff_at", "provider_match_id", "start_event_index"
        )


class TeamEventProfileApi(APIView):
    def get(self, request, canonical_team_id: int):
        try:
            profile = resolve_team_event_profile(request, canonical_team_id)
            competition_season = profile.competition_season
            match_ref = parse_optional_match(request)
            state_lens = parse_state_lens(request)
            cache_key = stable_cache_key(
                f"event-profile:{profile.competition_season_id}:team",
                {
                    "endpoint": "team",
                    "team": canonical_team_id,
                    "competition": profile.competition_season.competition.short_code,
                    "season": profile.competition_season.season.label,
                    "formula_version": profile.formula_version,
                    "materialization_run": profile.materialized_ingestion_run_id,
                    "profile_version": profile.id,
                    "match": match_ref,
                    "state_lens": state_lens.cache_scope(),
                },
            )
            response, _ = get_or_build_payload_response(
                cache_key=cache_key,
                source_version=profile_source_version(
                    "team",
                    profile,
                    match_ref,
                    state_lens.source_token(),
                    model_version(
                        ProviderMatchGameState,
                        {"provider_match__competition_season": competition_season},
                    ),
                    model_version(
                        ProviderMatchTeamGameStateEpisode,
                        {"provider_match__competition_season": competition_season},
                    ),
                ),
                builder=lambda: self.build_payload(profile, match_ref, state_lens),
            )
            return response
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except TeamSeasonEventProfile.DoesNotExist:
            return Response(
                {"detail": "Team event profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def build_payload(self, profile: TeamSeasonEventProfile, match_ref: int | None, state_lens) -> dict:
        match_ids = event_queryset(profile.competition_season).filter(
            team_id=profile.team_id
        ).values("provider_match_id")
        scoped_queryset, matches, references = scope_queryset_to_match(
            event_queryset(profile.competition_season).filter(provider_match_id__in=match_ids),
            match_ref,
            profile.team_id,
        )
        evidence_match_ids = list(
            scoped_queryset.values_list("provider_match_id", flat=True).distinct()
        )
        scoped_queryset = scope_team_events(
            scoped_queryset, profile.team_id, state_lens.selected
        )
        shots = list(
            scoped_queryset.filter(event_type=MatchEventType.SHOT).order_by(
                "provider_match__kickoff_at", "provider_match_id", "event_index"
            )
        )
        shots_for = [event for event in shots if event.team_id == profile.team_id]
        shots_against = [event for event in shots if event.team_id != profile.team_id]
        if match_ref is None and state_lens.selected.is_default:
            summary = {field: getattr(profile, field) for field in TEAM_SUMMARY_FIELDS}
            pass_flow = profile.pass_flow if profile.formula_version == FORMULA_VERSION else []
            touch_grid = profile.action_grid if profile.formula_version == FORMULA_VERSION else []
            opponent_touch_grid = (
                profile.opponent_action_grid if profile.formula_version == FORMULA_VERSION else []
            )
        else:
            events = list(scoped_queryset)
            team_events = [event for event in events if event.team_id == profile.team_id]
            opponent_events = [event for event in events if event.team_id != profile.team_id]
            team_summary = _summary(team_events)
            opponent_summary = _summary(opponent_events)
            summary = {
                field: team_summary[field]
                for field in TEAM_SUMMARY_FIELDS
                if field
                not in {
                    "shots_for",
                    "goals_for",
                    "big_chance_shots_for",
                    "shots_against",
                    "goals_against",
                    "big_chance_shots_against",
                }
            }
            summary.update({
                "shots_for": team_summary["shots"],
                "goals_for": team_summary["goals"],
                "big_chance_shots_for": team_summary["big_chance_shots"],
                "shots_against": opponent_summary["shots"],
                "goals_against": opponent_summary["goals"],
                "big_chance_shots_against": opponent_summary["big_chance_shots"],
            })
            pass_flow = _pass_flow(team_events)
            touch_grid, _ = _grid(team_events, 0, touches_only=True)
            opponent_touch_grid, _ = _grid(opponent_events, 0, touches_only=True)
        return {
            "canonical_team_id": profile.team_id,
            "canonical_team_name": profile.team.name,
            "competition_season": profile.competition_season_id,
            "competition_code": profile.competition_season.competition.short_code,
            "season_label": profile.competition_season.season.label,
            "coverage": {
                "observed_matches": profile.observed_match_count,
                "expected_matches": profile.expected_match_count,
                "ratio": profile.coverage,
            },
            "materialization": materialization_metadata(profile),
            "summary": summary,
            "pass_flow": pass_flow,
            "touch_grid": touch_grid,
            "opponent_touch_grid": opponent_touch_grid,
            "action_grid": touch_grid,
            "opponent_action_grid": opponent_touch_grid,
            "shots_for": [compact_shot(event, references) for event in shots_for],
            "shots_against": [compact_shot(event, references) for event in shots_against],
            "matches": matches,
            "selected_match_ref": match_ref,
            "state_lens": state_lens_metadata(
                profile.team_id, evidence_match_ids, state_lens
            ),
        }
