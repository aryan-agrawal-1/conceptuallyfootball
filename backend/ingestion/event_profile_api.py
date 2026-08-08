from __future__ import annotations

from collections.abc import Callable

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.api_cache import get_or_build_payload_response, joined_version, stable_cache_key
from ingestion.derived_api import _resolve_competition_season
from ingestion.models import (
    EventProfileSplitType,
    MatchEventType,
    PlayerSeasonDerivedStats,
    PlayerSeasonEventProfile,
    Provider,
    ProviderMatchEvent,
    TeamSeasonEventProfile,
)
from ingestion.services.event_profiles import event_profile_availability


PASS_RESPONSE_LIMIT = 5_000
COORDINATE_SCALE = 100

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
    return event_profile_availability(
        profile.pass_attempts,
        profile.shots,
        profile.valid_location_actions,
    )


def coverage_for_player(profile: PlayerSeasonEventProfile) -> dict:
    run_coverage = profile.materialized_ingestion_run.stats.get("coverage", {})
    return {
        "observed_matches": profile.observed_match_count,
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


def compact_match_lookup(events: list[ProviderMatchEvent]) -> tuple[list[dict], dict[int, int]]:
    matches = {event.provider_match_id: event.provider_match for event in events}
    ordered = sorted(matches.values(), key=lambda match: (match.kickoff_at, match.id))
    references = {match.id: index for index, match in enumerate(ordered)}
    lookup = [
        {
            "ref": references[match.id],
            "kickoff_at": match.kickoff_at.isoformat(),
            "home_team_id": match.home_team_id,
            "home_team_name": match.home_team.name if match.home_team else None,
            "away_team_id": match.away_team_id,
            "away_team_name": match.away_team.name if match.away_team else None,
            "home_score": match.home_score,
            "away_score": match.away_score,
        }
        for match in ordered
    ]
    return lookup, references


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


PASS_FILTERS: dict[str, Callable[[QuerySet], QuerySet]] = {
    "completed": lambda queryset: queryset.filter(outcome_successful=True),
    "progressive": lambda queryset: queryset.filter(is_progressive_pass=True),
    "final_third_entry": lambda queryset: queryset.filter(is_final_third_entry=True),
    "box_entry": lambda queryset: queryset.filter(is_box_entry=True),
    "key_pass": lambda queryset: queryset.filter(is_key_pass=True),
    "cross": lambda queryset: queryset.filter(is_cross=True),
    "long_ball": lambda queryset: queryset.filter(is_long_ball=True),
    "failed": lambda queryset: queryset.filter(outcome_successful=False),
}

PASS_FILTER_ALIASES = {
    "all": "completed",
    "all_completed": "completed",
    "final-third-entry": "final_third_entry",
    "final_third_entries": "final_third_entry",
    "box-entry": "box_entry",
    "box_entries": "box_entry",
    "key-pass": "key_pass",
    "key_passes": "key_pass",
    "crosses": "cross",
    "long-ball": "long_ball",
    "long_balls": "long_ball",
    "failed_passes": "failed",
}


def normalized_pass_filter(request) -> str:
    requested = (request.query_params.get("filter") or "completed").strip().lower()
    value = PASS_FILTER_ALIASES.get(requested, requested)
    if value not in PASS_FILTERS:
        raise DjangoValidationError(
            "Unsupported pass filter. Use completed, progressive, final_third_entry, "
            "box_entry, key_pass, cross, long_ball, or failed."
        )
    return value


class PlayerEventProfileMixin:
    def resolve_profile(self, request, canonical_player_id: int) -> PlayerSeasonEventProfile:
        competition_season = resolve_event_profile_competition_season(request)
        team_id = parse_optional_team(request)
        if not PlayerSeasonDerivedStats.objects.filter(
            competition_season=competition_season,
            canonical_player_id=canonical_player_id,
            is_current=True,
        ).exists():
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
            cache_key = stable_cache_key(
                f"event-profile:{profile.competition_season_id}:player",
                {
                    "endpoint": "player",
                    "player": canonical_player_id,
                    "competition": profile.competition_season.competition.short_code,
                    "season": profile.competition_season.season.label,
                    "team": profile.team_id,
                    "formula_version": profile.formula_version,
                    "materialization_run": profile.materialized_ingestion_run_id,
                    "profile_version": profile.id,
                },
            )
            response, _ = get_or_build_payload_response(
                cache_key=cache_key,
                source_version=profile_source_version("player", profile),
                builder=lambda: self.build_payload(profile),
            )
            return response
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PlayerSeasonEventProfile.DoesNotExist:
            return Response(
                {"detail": "Public player event profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def build_payload(self, profile: PlayerSeasonEventProfile) -> dict:
        shots = list(
            player_event_queryset(profile)
            .filter(event_type=MatchEventType.SHOT)
            .order_by("provider_match__kickoff_at", "provider_match_id", "event_index")
        )
        matches, references = compact_match_lookup(shots)
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
            "summary": {field: getattr(profile, field) for field in PLAYER_SUMMARY_FIELDS},
            "average_touch_location": {
                "x": public_coordinate(profile.average_touch_x),
                "y": public_coordinate(profile.average_touch_y),
                "sample_size": profile.touches,
            },
            "action_grid": profile.action_grid,
            "shots": [compact_shot(event, references) for event in shots],
            "matches": matches,
        }


class PlayerEventProfilePassesApi(PlayerEventProfileMixin, APIView):
    def get(self, request, canonical_player_id: int):
        try:
            profile = self.resolve_profile(request, canonical_player_id)
            pass_filter = normalized_pass_filter(request)
            cache_key = stable_cache_key(
                f"event-profile:{profile.competition_season_id}:player-passes",
                {
                    "endpoint": "player-passes",
                    "player": canonical_player_id,
                    "competition": profile.competition_season.competition.short_code,
                    "season": profile.competition_season.season.label,
                    "team": profile.team_id,
                    "pass_filter": pass_filter,
                    "formula_version": profile.formula_version,
                    "materialization_run": profile.materialized_ingestion_run_id,
                    "profile_version": profile.id,
                },
            )
            response, _ = get_or_build_payload_response(
                cache_key=cache_key,
                source_version=profile_source_version("player-passes", profile, pass_filter),
                builder=lambda: self.build_payload(profile, pass_filter),
            )
            return response
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PlayerSeasonEventProfile.DoesNotExist:
            return Response(
                {"detail": "Public player event profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def build_payload(self, profile: PlayerSeasonEventProfile, pass_filter: str) -> dict:
        queryset = player_event_queryset(profile).filter(event_type=MatchEventType.PASS)
        queryset = PASS_FILTERS[pass_filter](queryset)
        total_matching_count = queryset.count()
        events = list(
            queryset.order_by("provider_match__kickoff_at", "provider_match_id", "event_index")[
                :PASS_RESPONSE_LIMIT
            ]
        )
        matches, references = compact_match_lookup(events)
        return {
            "canonical_player_id": profile.player_id,
            "canonical_team_id": profile.team_id,
            "competition_season": profile.competition_season_id,
            "competition_code": profile.competition_season.competition.short_code,
            "season_label": profile.competition_season.season.label,
            "filter": pass_filter,
            "total_matching_count": total_matching_count,
            "truncated": total_matching_count > PASS_RESPONSE_LIMIT,
            "materialization": materialization_metadata(profile),
            "passes": [compact_pass(event, references) for event in events],
            "matches": matches,
        }


class TeamEventProfileApi(APIView):
    def get(self, request, canonical_team_id: int):
        try:
            competition_season = resolve_event_profile_competition_season(request)
            profile = TeamSeasonEventProfile.objects.select_related(
                "team", "competition_season__competition", "competition_season__season"
            ).get(
                competition_season=competition_season,
                team_id=canonical_team_id,
                is_current=True,
            )
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
                },
            )
            response, _ = get_or_build_payload_response(
                cache_key=cache_key,
                source_version=profile_source_version("team", profile),
                builder=lambda: self.build_payload(profile),
            )
            return response
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except TeamSeasonEventProfile.DoesNotExist:
            return Response(
                {"detail": "Team event profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def build_payload(self, profile: TeamSeasonEventProfile) -> dict:
        match_ids = event_queryset(profile.competition_season).filter(team_id=profile.team_id).values(
            "provider_match_id"
        )
        shots = list(
            event_queryset(profile.competition_season)
            .filter(provider_match_id__in=match_ids, event_type=MatchEventType.SHOT)
            .order_by("provider_match__kickoff_at", "provider_match_id", "event_index")
        )
        matches, references = compact_match_lookup(shots)
        shots_for = [event for event in shots if event.team_id == profile.team_id]
        shots_against = [event for event in shots if event.team_id != profile.team_id]
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
            "summary": {field: getattr(profile, field) for field in TEAM_SUMMARY_FIELDS},
            "pass_flow": profile.pass_flow,
            "action_grid": profile.action_grid,
            "opponent_action_grid": profile.opponent_action_grid,
            "shots_for": [compact_shot(event, references) for event in shots_for],
            "shots_against": [compact_shot(event, references) for event in shots_against],
            "matches": matches,
        }
