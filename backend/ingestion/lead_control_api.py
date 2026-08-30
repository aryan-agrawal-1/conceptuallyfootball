"""Cached public API adapter for Lead Gravity and Lead Ownership."""

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
    compact_match_lookup,
    event_queryset,
    parse_optional_match,
    resolve_event_profile_competition_season,
    scope_queryset_to_match,
)
from ingestion.models import (
    CanonicalTeam,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchPossession,
    ProviderMatchPossessionBuild,
    ProviderMatchTeamGameStateEpisode,
)
from ingestion.services.lead_control import (
    LEAD_CONTROL_API_VERSION,
    LEAD_CONTROL_FORMULA_VERSION,
    build_lead_control_payload,
)
from ingestion.services.possession_context import POSSESSION_CALCULATION_VERSION
from ingestion.state_lens import parse_state_lens, state_lens_metadata


class TeamLeadControlApi(APIView):
    """Serve inspectable, provider-neutral lead behaviour and control."""

    def get(self, request, canonical_team_id: int):
        try:
            competition_season = resolve_event_profile_competition_season(request)
            team = CanonicalTeam.objects.get(pk=canonical_team_id)
            match_ref = parse_optional_match(request)
            lens = parse_state_lens(request)
            match_filter = {
                "competition_season": competition_season,
                "provider": Provider.WHOSCORED,
            }
            related_season_filter = {
                "provider_match__competition_season": competition_season,
                "provider_match__provider": Provider.WHOSCORED,
            }
            cache_key = stable_cache_key(
                f"event-profile:{competition_season.id}:team-lead-control",
                {
                    "endpoint": "team-lead-control",
                    "team": team.id,
                    "match": match_ref,
                    "state_lens": lens.cache_scope(),
                    "formula": LEAD_CONTROL_FORMULA_VERSION,
                },
            )
            source_version = joined_version(
                LEAD_CONTROL_API_VERSION,
                LEAD_CONTROL_FORMULA_VERSION,
                POSSESSION_CALCULATION_VERSION,
                model_version(ProviderMatch, match_filter),
                model_version(ProviderMatchEvent, related_season_filter),
                model_version(ProviderMatchGameState, related_season_filter),
                model_version(ProviderMatchTeamGameStateEpisode, related_season_filter),
                model_version(ProviderMatchPossessionBuild, related_season_filter),
                model_version(ProviderMatchPossession, related_season_filter),
            )
            response, cached = get_or_build_payload_response(
                cache_key=cache_key,
                source_version=source_version,
                builder=lambda: self.build_payload(
                    competition_season,
                    team,
                    match_ref,
                    lens,
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

    @staticmethod
    def build_payload(competition_season, team, match_ref, lens):
        """Assemble both sides from verified match, episode, and event rows."""

        focal_events = event_queryset(competition_season).filter(team=team)
        scoped_focal_events, _ignored_matches, references = scope_queryset_to_match(
            focal_events,
            match_ref,
            team.id,
        )
        match_ids = list(
            scoped_focal_events.values_list("provider_match_id", flat=True).distinct()
        )
        provider_matches = list(
            ProviderMatch.objects.filter(
                id__in=match_ids,
                provider=Provider.WHOSCORED,
            ).select_related("home_team", "away_team")
        )
        subject_team_ids = {match.id: team.id for match in provider_matches}
        matches, references = compact_match_lookup(provider_matches, subject_team_ids)
        eligible_match_ids = set(
            ProviderMatchGameState.objects.filter(
                provider_match_id__in=match_ids,
                eligible=True,
            ).values_list("provider_match_id", flat=True)
        )
        match_end_seconds = {
            row["provider_match_id"]: row["supported_end_second"]
            for row in ProviderMatchGameState.objects.filter(
                provider_match_id__in=eligible_match_ids,
            ).values("provider_match_id", "supported_end_second")
            if row["supported_end_second"] is not None
        }
        events = list(
            ProviderMatchEvent.objects.filter(
                provider_match_id__in=match_ids,
                provider_match__provider=Provider.WHOSCORED,
            )
            .order_by("provider_match_id", "period", "timeline_seconds", "event_index")
        )
        episodes = list(
            ProviderMatchTeamGameStateEpisode.objects.filter(
                provider_match_id__in=eligible_match_ids,
                focal_team=team,
            ).order_by("provider_match_id", "start_second", "episode_index")
        )
        possessions = list(
            ProviderMatchPossession.objects.filter(
                provider_match_id__in=eligible_match_ids,
                provider_match__provider=Provider.WHOSCORED,
                build__calculation_version=POSSESSION_CALCULATION_VERSION,
                is_ambiguous=False,
            ).order_by("provider_match_id", "start_second", "possession_index")
        )
        focal_provider_by_match = {}
        for match in provider_matches:
            if match.home_team_id == team.id:
                focal_provider_by_match[match.id] = str(match.home_provider_team_id)
            elif match.away_team_id == team.id:
                focal_provider_by_match[match.id] = str(match.away_provider_team_id)

        payload = build_lead_control_payload(
            events,
            episodes,
            possessions,
            focal_team_id=team.id,
            team_name=team.name,
            matches=provider_matches,
            match_references=references,
            focal_provider_by_match=focal_provider_by_match,
            lens=lens,
            eligible_match_ids=eligible_match_ids,
            selected_match_ref=match_ref,
            match_end_seconds=match_end_seconds,
        )
        payload["competition_season"] = {
            "id": competition_season.id,
            "competition": competition_season.competition.short_code,
            "season": competition_season.season.label,
        }
        payload["matches"] = matches
        payload["state_lens"] = state_lens_metadata(team.id, match_ids, lens)
        return payload
