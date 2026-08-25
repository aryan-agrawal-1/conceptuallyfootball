from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.api_cache import get_or_build_payload_response, model_version, stable_cache_key
from ingestion.event_profile_api import (
    event_queryset,
    parse_optional_match,
    profile_source_version,
    resolve_team_event_profile,
    scope_queryset_to_match,
)
from ingestion.models import (
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchTeamGameStateEpisode,
    TeamSeasonEventProfile,
)
from ingestion.services.defensive_territory import defensive_territory_payload
from ingestion.state_lens import (
    build_state_lens_cohorts,
    parse_state_lens,
    scope_team_events,
    state_lens_metadata,
)


class TeamDefensiveTerritoryApi(APIView):
    """Cached public defensive event-location evidence for one team."""

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
            audit_version = model_version(
                ProviderMatchGameState,
                {"provider_match__competition_season": competition_season.id},
            )
            episode_version = model_version(
                ProviderMatchTeamGameStateEpisode,
                {"provider_match__competition_season": competition_season.id},
            )
            cache_key = stable_cache_key(
                f"event-profile:{competition_season.id}:team-defensive-territory",
                {
                    "team": canonical_team_id,
                    "profile": profile.id,
                    "match": match_ref,
                    "state_lens": lens.cache_scope(),
                },
            )
            response, cached = get_or_build_payload_response(
                cache_key=cache_key,
                source_version=profile_source_version(
                    "team-defensive-territory",
                    profile,
                    event_version,
                    audit_version,
                    episode_version,
                    match_ref,
                    lens.source_token(),
                ),
                builder=lambda: self.build_payload(profile, match_ref, lens),
            )
            response["X-Materialized-Payload"] = "hit" if cached else "miss"
            return response
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except TeamSeasonEventProfile.DoesNotExist:
            return Response(
                {"detail": "Public team event profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def build_payload(self, profile, match_ref, lens) -> dict:
        focal_events = event_queryset(profile.competition_season).filter(team_id=profile.team_id)
        scoped, matches, _ = scope_queryset_to_match(focal_events, match_ref, profile.team_id)
        match_ids = list(scoped.values_list("provider_match_id", flat=True).distinct())
        eligible_ids = set(
            ProviderMatchGameState.objects.filter(
                provider_match_id__in=match_ids, eligible=True
            ).values_list("provider_match_id", flat=True)
        )
        eligible_events = scoped.filter(provider_match_id__in=eligible_ids)
        excluded_match_events = scoped.exclude(provider_match_id__in=eligible_ids).count()
        metadata = state_lens_metadata(profile.team_id, match_ids, lens)

        def build_scope(scope, evidence):
            events = scope_team_events(eligible_events, profile.team_id, scope)
            return defensive_territory_payload(
                events.order_by("provider_match__kickoff_at", "provider_match_id", "event_index"),
                exposure_seconds=evidence["exposure_seconds"],
                excluded_match_events=excluded_match_events,
            )

        selected, baseline = build_state_lens_cohorts(lens, metadata, build_scope)
        return {
            "canonical_team_id": profile.team_id,
            "canonical_team_name": profile.team.name,
            "competition_code": profile.competition_season.competition.short_code,
            "season_label": profile.competition_season.season.label,
            "selected_match_ref": match_ref,
            "matches": matches,
            "state_lens": metadata,
            "selected": selected,
            "baseline": baseline,
        }
