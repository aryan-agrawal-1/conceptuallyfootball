"""Comparison-ready team pass evidence scoped by the shared State Lens."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.api_cache import get_or_build_payload_response, joined_version, model_version, stable_cache_key
from ingestion.event_profile_api import (
    event_queryset,
    parse_optional_match,
    profile_source_version,
    resolve_team_event_profile,
    scope_queryset_to_match,
)
from ingestion.models import (
    MatchEventType,
    ProviderMatchGameState,
    ProviderMatchTeamGameStateEpisode,
    TeamSeasonEventProfile,
)
from ingestion.services.pass_state import (
    PASS_STATE_EVENT_LIMIT,
    PASS_STATE_FORMULA_VERSION,
    build_pass_state_evidence,
    comparison_delta,
)
from ingestion.state_lens import (
    parse_state_lens,
    scope_team_events,
    state_lens_metadata,
)

PASS_STATE_API_VERSION = "v1"


class TeamPassStateApi(APIView):
    def get(self, request, canonical_team_id: int):
        try:
            profile = resolve_team_event_profile(request, canonical_team_id)
            competition_season = profile.competition_season
            match_ref = parse_optional_match(request)
            lens = parse_state_lens(request)
            cache_key = stable_cache_key(
                f"event-profile:{profile.competition_season_id}:team-pass-state",
                {
                    "endpoint": "team-pass-state",
                    "team": canonical_team_id,
                    "profile": profile.id,
                    "match": match_ref,
                    "state_lens": lens.cache_scope(),
                    "formula": PASS_STATE_FORMULA_VERSION,
                },
            )
            source_version = joined_version(
                profile_source_version("team-pass-state", profile, match_ref),
                PASS_STATE_API_VERSION,
                PASS_STATE_FORMULA_VERSION,
                model_version(
                    ProviderMatchTeamGameStateEpisode,
                    {"provider_match__competition_season": competition_season},
                ),
                model_version(
                    ProviderMatchGameState,
                    {"provider_match__competition_season": competition_season},
                ),
            )
            response, _ = get_or_build_payload_response(
                cache_key=cache_key,
                source_version=source_version,
                builder=lambda: self.build_payload(profile, match_ref, lens),
            )
            return response
        except DjangoValidationError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except TeamSeasonEventProfile.DoesNotExist:
            return Response(
                {"detail": "Team event profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def build_payload(self, profile, match_ref, lens) -> dict:
        team_matches = event_queryset(profile.competition_season).filter(
            team_id=profile.team_id
        ).values("provider_match_id")
        scoped, matches, references = scope_queryset_to_match(
            event_queryset(profile.competition_season).filter(
                provider_match_id__in=team_matches,
                team_id=profile.team_id,
            ),
            match_ref,
            profile.team_id,
        )
        match_ids = list(
            scoped.values_list("provider_match_id", flat=True).distinct()
        )
        # Every rate denominator comes from verified canonical episodes, so the
        # numerator must exclude the same unaudited/ineligible matches even for
        # the State Lens default (`state=all`) scope.
        scoped = scoped.filter(provider_match__game_state__eligible=True)
        metadata = state_lens_metadata(profile.team_id, match_ids, lens)
        selected = self.evidence(
            scoped,
            profile.team_id,
            lens.selected,
            metadata["evidence"]["exposure_seconds"],
        )
        comparison = None
        if lens.comparison_enabled:
            baseline = self.evidence(
                scoped,
                profile.team_id,
                lens.baseline,
                metadata["comparison"]["baseline_evidence"]["exposure_seconds"],
            )
            comparison = {
                "baseline": baseline,
                "delta": comparison_delta(selected, baseline),
            }
        return {
            "canonical_team_id": profile.team_id,
            "canonical_team_name": profile.team.name,
            "competition_season": profile.competition_season_id,
            "competition_code": profile.competition_season.competition.short_code,
            "season_label": profile.competition_season.season.label,
            "selected_match_ref": match_ref,
            "matches": matches,
            "state_lens": metadata,
            "selected": selected,
            "comparison": comparison,
        }

    @staticmethod
    def evidence(queryset, team_id, scope, exposure_seconds):
        passes = scope_team_events(
            queryset.filter(event_type=MatchEventType.PASS), team_id, scope
        )
        counts = passes.aggregate(
            attempts=Count("id"),
            completions=Count("id", filter=Q(outcome_successful=True)),
            progressive_attempts=Count("id", filter=Q(is_progressive_pass=True)),
            progressive_completions=Count(
                "id", filter=Q(is_progressive_pass=True, outcome_successful=True)
            ),
            missing_coordinates=Count(
                "id",
                filter=(
                    Q(x__isnull=True)
                    | Q(y__isnull=True)
                    | Q(end_x__isnull=True)
                    | Q(end_y__isnull=True)
                ),
            ),
        )
        events = list(
            passes.order_by(
                "provider_match__kickoff_at", "provider_match_id", "event_index"
            )[:PASS_STATE_EVENT_LIMIT]
        )
        return build_pass_state_evidence(
            events,
            exposure_seconds=exposure_seconds,
            source_event_count=counts["attempts"],
            source_completion_count=counts["completions"],
            source_progressive_attempt_count=counts["progressive_attempts"],
            source_progressive_completion_count=counts["progressive_completions"],
            source_missing_coordinate_count=counts["missing_coordinates"],
        )
