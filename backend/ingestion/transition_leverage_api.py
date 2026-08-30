"""Public API for the inspectable Transition Leverage contract."""

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
    parse_optional_match,
    resolve_event_profile_competition_season,
)
from ingestion.models import (
    CanonicalTeam,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchPlayerParticipationBuild,
    ProviderMatchPlayerInterval,
    ProviderMatchPlayerParticipation,
    ProviderMatchPossessionBuild,
    ProviderMatchPossession,
    ProviderMatchPossessionEvent,
    ProviderMatchTeamGameStateEpisode,
)
from ingestion.services.possession_context import POSSESSION_CALCULATION_VERSION
from ingestion.services.transition_leverage import (
    TRANSITION_LEVERAGE_API_VERSION,
    TRANSITION_LEVERAGE_FORMULA_VERSION,
    TRANSITION_LEVERAGE_PAYLOAD_SHAPE_VERSION,
    build_transition_leverage_payload,
)
from ingestion.state_lens import parse_state_lens


class TeamTransitionLeverageApi(APIView):
    """Serve cached, provider-neutral transition observations for one team."""

    def get(self, request, canonical_team_id: int):
        try:
            competition_season = resolve_event_profile_competition_season(request)
            team = CanonicalTeam.objects.get(pk=canonical_team_id)
            match_ref = parse_optional_match(request)
            lens = parse_state_lens(request)
            season_filter = {"provider_match__competition_season": competition_season}
            cache_key = stable_cache_key(
                f"event-profile:{competition_season.id}:team-transition-leverage",
                {
                    "endpoint": "team-transition-leverage",
                    "team": team.id,
                    "match": match_ref,
                    "state_lens": lens.cache_scope(),
                    "formula": TRANSITION_LEVERAGE_FORMULA_VERSION,
                },
            )
            source_version = joined_version(
                TRANSITION_LEVERAGE_API_VERSION,
                TRANSITION_LEVERAGE_FORMULA_VERSION,
                TRANSITION_LEVERAGE_PAYLOAD_SHAPE_VERSION,
                POSSESSION_CALCULATION_VERSION,
                model_version(ProviderMatch, {"competition_season": competition_season}),
                model_version(ProviderMatchEvent, season_filter),
                model_version(ProviderMatchGameState, season_filter),
                model_version(ProviderMatchTeamGameStateEpisode, season_filter),
                model_version(ProviderMatchPossession, season_filter),
                model_version(ProviderMatchPossessionBuild, season_filter),
                model_version(ProviderMatchPossessionEvent, {"possession__provider_match__competition_season": competition_season}),
                model_version(ProviderMatchPlayerParticipation, season_filter),
                model_version(ProviderMatchPlayerParticipationBuild, season_filter),
                model_version(ProviderMatchPlayerInterval, {"participation__provider_match__competition_season": competition_season}),
            )
            response, cached = get_or_build_payload_response(
                cache_key=cache_key,
                source_version=source_version,
                builder=lambda: build_transition_leverage_payload(
                    competition_season=competition_season,
                    team=team,
                    match_ref=match_ref,
                    lens=lens,
                ),
            )
            response["X-Materialized-Payload"] = "hit" if cached else "miss"
            return response
        except DjangoValidationError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except CanonicalTeam.DoesNotExist:
            return Response(
                {"detail": "Unknown canonical team."},
                status=status.HTTP_404_NOT_FOUND,
            )
