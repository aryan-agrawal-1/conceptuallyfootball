"""Cached public API for team post-concession Response Half-Life."""

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
    event_queryset,
    parse_optional_match,
    profile_source_version,
    resolve_team_event_profile,
    scope_queryset_to_match,
)
from ingestion.models import (
    Provider,
    ProviderMatch,
    ProviderMatchCarry,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchPlayedPeriod,
    ProviderMatchTeamGameStateEpisode,
    TeamSeasonEventProfile,
)
from ingestion.services.response_half_life import (
    RESPONSE_HALF_LIFE_API_VERSION,
    RESPONSE_HALF_LIFE_FORMULA_VERSION,
    ResponseMatchData,
    build_response_half_life_cohort,
    build_response_half_life_payload,
)
from ingestion.state_lens import parse_state_lens, state_lens_metadata


class TeamResponseHalfLifeApi(APIView):
    """Serve deterministic, inspectable response half-life evidence."""

    def get(self, request, canonical_team_id: int):
        try:
            profile = resolve_team_event_profile(request, canonical_team_id)
            competition_season = profile.competition_season
            match_ref = parse_optional_match(request)
            lens = parse_state_lens(request)
            event_version = model_version(
                ProviderMatchEvent,
                {"provider_match__competition_season": competition_season.id},
            )
            match_version = model_version(
                ProviderMatch,
                {"competition_season": competition_season.id},
            )
            game_state_version = model_version(
                ProviderMatchGameState,
                {"provider_match__competition_season": competition_season.id},
            )
            episode_version = model_version(
                ProviderMatchTeamGameStateEpisode,
                {"provider_match__competition_season": competition_season.id},
            )
            carry_version = model_version(
                ProviderMatchCarry,
                {"provider_match__competition_season": competition_season.id},
            )
            period_version = model_version(
                ProviderMatchPlayedPeriod,
                {"provider_match__competition_season": competition_season.id},
            )
            cache_key = stable_cache_key(
                f"event-profile:{competition_season.id}:team-response-half-life",
                {
                    "endpoint": "team-response-half-life",
                    "team": canonical_team_id,
                    "profile": profile.id,
                    "match": match_ref,
                    "state_lens": lens.cache_scope(),
                    "formula_version": RESPONSE_HALF_LIFE_FORMULA_VERSION,
                },
            )
            source_version = profile_source_version(
                "team-response-half-life",
                profile,
                RESPONSE_HALF_LIFE_API_VERSION,
                RESPONSE_HALF_LIFE_FORMULA_VERSION,
                match_ref,
                lens.source_token(),
                match_version,
                event_version,
                game_state_version,
                episode_version,
                carry_version,
                period_version,
            )
            response, cached = get_or_build_payload_response(
                cache_key=cache_key,
                source_version=source_version,
                builder=lambda: self.build_payload(profile, match_ref, lens),
            )
            response["X-Materialized-Payload"] = "hit" if cached else "miss"
            return response
        except DjangoValidationError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except TeamSeasonEventProfile.DoesNotExist:
            return Response(
                {"detail": "Public team response half-life profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def build_payload(self, profile, match_ref, lens):
        competition_season = profile.competition_season
        all_team_events = event_queryset(competition_season).filter(team_id=profile.team_id)
        selected_events, matches, references = scope_queryset_to_match(
            all_team_events,
            match_ref,
            profile.team_id,
        )
        selected_match_ids = list(
            selected_events.values_list("provider_match_id", flat=True).distinct()
        )
        all_match_ids = list(
            all_team_events.values_list("provider_match_id", flat=True).distinct()
        )
        # A destination is season-scoped so a selected single-match trace can
        # still be compared with established behaviour.  The destination
        # calculation itself only accepts eligible game-state materializations.
        match_rows = list(
            ProviderMatch.objects.filter(
                id__in=all_match_ids,
                provider=Provider.WHOSCORED,
            ).select_related("home_team", "away_team")
        )
        game_state_ids = set(
            ProviderMatchGameState.objects.filter(
                provider_match_id__in=all_match_ids,
                eligible=True,
            ).values_list("provider_match_id", flat=True)
        )
        event_rows = {
            match.id: tuple(
                ProviderMatchEvent.objects.filter(provider_match=match).order_by(
                    "timeline_seconds", "provider_event_sequence_id", "event_index"
                )
            )
            for match in match_rows
        }
        episode_rows = {
            match.id: tuple(
                ProviderMatchTeamGameStateEpisode.objects.filter(
                    provider_match=match,
                    focal_team_id=profile.team_id,
                ).order_by("start_second", "episode_index")
            )
            for match in match_rows
        }
        carry_rows = {
            match.id: tuple(
                ProviderMatchCarry.objects.filter(
                    provider_match=match,
                    team_id=profile.team_id,
                )
            )
            for match in match_rows
        }
        periods_by_match = {
            match.id: tuple(
                ProviderMatchPlayedPeriod.objects.filter(provider_match=match).order_by(
                    "period_index", "period"
                )
            )
            for match in match_rows
        }
        loaded = [
            ResponseMatchData(
                match=match,
                events=event_rows.get(match.id, ()),
                episodes=episode_rows.get(match.id, ()),
                carries=carry_rows.get(match.id, ()),
                eligible=match.id in game_state_ids and bool(episode_rows.get(match.id)),
            )
            for match in match_rows
        ]
        selected_loaded = [
            item for item in loaded if item.match.id in set(selected_match_ids)
        ]
        destination_loaded = [item for item in loaded if item.eligible]
        metadata = state_lens_metadata(profile.team_id, all_match_ids, lens)
        selected = build_response_half_life_cohort(
            focal_team_id=profile.team_id,
            matches=selected_loaded,
            destination_matches=destination_loaded,
            scope=lens.selected,
            periods_by_match=periods_by_match,
            match_refs=references,
        )
        baseline = None
        if lens.baseline is not None:
            baseline = build_response_half_life_cohort(
                focal_team_id=profile.team_id,
                matches=selected_loaded,
                destination_matches=destination_loaded,
                scope=lens.baseline,
                periods_by_match=periods_by_match,
                match_refs=references,
            )
        return build_response_half_life_payload(
            canonical_team_id=profile.team_id,
            canonical_team_name=profile.team.name,
            competition_season=profile.competition_season_id,
            competition_code=competition_season.competition.short_code,
            season_label=competition_season.season.label,
            selected=selected,
            baseline=baseline,
            state_lens=metadata,
            matches=matches,
            selected_match_ref=match_ref,
        )
