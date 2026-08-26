"""Public player State Lens comparison API."""

from __future__ import annotations

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
    PlayerEventProfileMixin,
    parse_optional_match,
    player_event_queryset,
    scope_queryset_to_match,
)
from ingestion.models import (
    PlayerSeasonEventProfile,
    ProviderMatchEvent,
    ProviderMatchPlayerParticipationBuild,
    ProviderMatchPlayerParticipation,
    ProviderMatchPlayerStateExposure,
    ProviderMatchPossession,
    ProviderMatchPossessionBuild,
    ProviderMatchPossessionEvent,
    ProviderMatchTeamGameStateEpisode,
)
from ingestion.services.player_state_comparison import (
    PLAYER_STATE_COMPARISON_VERSION,
    build_player_state_comparison,
    player_state_lens_metadata,
)
from ingestion.state_lens import parse_state_lens


class PlayerStateComparisonApi(PlayerEventProfileMixin, APIView):
    """Verified player state cohorts and matched team-relative evidence."""

    def get(self, request, canonical_player_id: int):
        try:
            profile = self.resolve_profile(request, canonical_player_id)
            match_ref = parse_optional_match(request)
            lens = parse_state_lens(request)
            event_queryset = player_event_queryset(profile)
            scoped_events, _matches, _references = scope_queryset_to_match(
                event_queryset, match_ref
            )
            match_ids = list(
                scoped_events.values_list("provider_match_id", flat=True).distinct()
            )
            team_ids = set(
                ProviderMatchPlayerParticipation.objects.filter(
                    provider_match__competition_season=profile.competition_season,
                    player_id=profile.player_id,
                )
                .exclude(team_id__isnull=True)
                .values_list("team_id", flat=True)
            )
            if profile.team_id is not None:
                team_context_available = True
            else:
                team_context_available = len(team_ids) <= 1
            cache_key = stable_cache_key(
                f"event-profile:{profile.competition_season_id}:player-state-comparison",
                {
                    "endpoint": "player-state-comparison",
                    "player": canonical_player_id,
                    "competition": profile.competition_season.competition.short_code,
                    "season": profile.competition_season.season.label,
                    "team": profile.team_id,
                    "match": match_ref,
                    "state_lens": lens.cache_scope(),
                    "profile_version": profile.id,
                },
            )
            response, cached = get_or_build_payload_response(
                cache_key=cache_key,
                source_version=joined_version(
                    PLAYER_STATE_COMPARISON_VERSION,
                    profile.competition_season_id,
                    profile.id,
                    profile.formula_version,
                    model_version(
                        ProviderMatchEvent,
                        {"provider_match__competition_season": profile.competition_season_id},
                    ),
                    model_version(
                        ProviderMatchPlayerStateExposure,
                        {
                            "player_interval__participation__provider_match__competition_season": profile.competition_season_id,
                            "player_interval__participation__player_id": profile.player_id,
                        },
                    ),
                    model_version(
                        ProviderMatchPlayerParticipation,
                        {
                            "provider_match__competition_season": profile.competition_season_id,
                            "player_id": profile.player_id,
                        },
                    ),
                    model_version(
                        ProviderMatchPlayerParticipationBuild,
                        {"provider_match__competition_season": profile.competition_season_id},
                    ),
                    model_version(
                        ProviderMatchPossession,
                        {"provider_match__competition_season": profile.competition_season_id},
                    ),
                    model_version(
                        ProviderMatchPossessionBuild,
                        {"provider_match__competition_season": profile.competition_season_id},
                    ),
                    model_version(
                        ProviderMatchPossessionEvent,
                        {"possession__provider_match__competition_season": profile.competition_season_id},
                    ),
                    model_version(
                        ProviderMatchTeamGameStateEpisode,
                        {"provider_match__competition_season": profile.competition_season_id},
                    ),
                    lens.source_token(),
                ),
                builder=lambda: self.build_payload(
                    profile,
                    match_ref,
                    lens,
                    match_ids,
                    team_context_available,
                ),
            )
            response["X-Materialized-Payload"] = "hit" if cached else "miss"
            return response
        except DjangoValidationError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except PlayerSeasonEventProfile.DoesNotExist:
            return Response(
                {"detail": "Public player event profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

    @staticmethod
    def build_payload(profile, match_ref, lens, match_ids, team_context_available):
        comparison = build_player_state_comparison(
            profile,
            lens,
            match_ids,
            team_context_required=team_context_available,
        )
        metadata = player_state_lens_metadata(profile, match_ids, lens)
        return comparison | {
            "selected_match_ref": match_ref,
            "state_lens": metadata,
            "team_context": comparison["team_context"] | {
                "selection_required": not team_context_available,
                "selection_note": (
                    "Choose a team split before reading team-relative changes."
                    if not team_context_available
                    else None
                ),
            },
        }
