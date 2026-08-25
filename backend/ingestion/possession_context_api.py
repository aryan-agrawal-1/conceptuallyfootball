from __future__ import annotations

from collections import Counter

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Avg, Count, Q
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
    resolve_event_profile_competition_season,
    scope_queryset_to_match,
)
from ingestion.models import (
    CanonicalTeam,
    MatchEventShotSituation,
    MatchEventType,
    Provider,
    ProviderMatchGameState,
    ProviderMatchPossession,
    ProviderMatchPossessionBuild,
    ProviderMatchPossessionEvent,
    ProviderMatchTeamGameStateEpisode,
)
from ingestion.services.possession_context import block_height, public_possession_thresholds
from ingestion.state_lens import parse_state_lens, scope_team_events, state_lens_metadata


POSSESSION_CONTEXT_API_VERSION = "v2"


class TeamPossessionContextApi(APIView):
    """Public-safe possession evidence scoped by the canonical State Lens."""

    def get(self, request, canonical_team_id: int):
        try:
            competition_season = resolve_event_profile_competition_season(request)
            team = CanonicalTeam.objects.get(pk=canonical_team_id)
            match_ref = parse_optional_match(request)
            lens = parse_state_lens(request)
            calculation_version = public_possession_thresholds()["calculation_version"]
            cache_key = stable_cache_key(
                f"event-profile:{competition_season.id}:team-possession-context",
                {
                    "team": team.id,
                    "match": match_ref,
                    "state_lens": lens.cache_scope(),
                    "formula": calculation_version,
                },
            )
            match_filter = {"provider_match__competition_season": competition_season}
            source_version = joined_version(
                POSSESSION_CONTEXT_API_VERSION,
                calculation_version,
                model_version(ProviderMatchPossessionBuild, match_filter),
                model_version(ProviderMatchGameState, match_filter),
                model_version(ProviderMatchTeamGameStateEpisode, match_filter),
            )
            response, cached = get_or_build_payload_response(
                cache_key=cache_key,
                source_version=source_version,
                builder=lambda: self.build_payload(
                    competition_season, team, match_ref, lens, calculation_version
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

    def build_payload(self, competition_season, team, match_ref, lens, calculation_version):
        focal_events = event_queryset(competition_season).filter(team=team)
        match_events, matches, references = scope_queryset_to_match(
            focal_events, match_ref, team.id
        )
        match_ids = list(match_events.values_list("provider_match_id", flat=True).distinct())
        eligible_events = match_events.filter(provider_match__game_state__eligible=True)
        eligible_match_ids = eligible_events.values_list("provider_match_id", flat=True).distinct()
        possessions = ProviderMatchPossession.objects.filter(
            provider_match_id__in=eligible_match_ids,
            provider_match__provider=Provider.WHOSCORED,
            build__calculation_version=calculation_version,
            is_ambiguous=False,
        )
        metadata = state_lens_metadata(team.id, match_ids, lens)
        selected = self.build_scope(possessions, eligible_events, team, lens.selected, references)
        baseline = (
            self.build_scope(possessions, eligible_events, team, lens.baseline, references)
            if lens.baseline is not None
            else None
        )
        return {
            "team": {"id": team.id, "name": team.name},
            "competition_season": {
                "id": competition_season.id,
                "competition": competition_season.competition.short_code,
                "season": competition_season.season.label,
            },
            "selected_match_ref": match_ref,
            "matches": matches,
            "state_lens": metadata,
            "thresholds": public_possession_thresholds(),
            **selected,
            "comparison": {
                "enabled": baseline is not None,
                "baseline": baseline,
            },
        }

    @staticmethod
    def build_scope(possessions, eligible_events, team, scope, references):
        scoped_events = scope_team_events(eligible_events, team.id, scope)
        scoped_event_ids = scoped_events.values("id")
        own = possessions.filter(team=team)
        counters = own.filter(
            is_counter_launch=True,
            event_links__sequence=0,
            event_links__event_id__in=scoped_event_ids,
        )
        counter_totals = counters.aggregate(
            launches=Count("id"),
            final_third_arrivals=Count("id", filter=Q(counter_final_third_arrival=True)),
            box_arrivals=Count("id", filter=Q(counter_box_arrival=True)),
            shots=Count("id", filter=Q(counter_shot=True)),
        )
        observed_fast_break_shots = scoped_events.filter(
            event_type=MatchEventType.SHOT,
            shot_situation=MatchEventShotSituation.FAST_BREAK,
            possession_link__possession__in=own,
        ).count()
        settled_actions = ProviderMatchPossessionEvent.objects.filter(
            possession__in=possessions.exclude(team=team),
            event__team=team,
            event_id__in=scoped_event_ids,
            is_settled_defensive_action=True,
        )
        settled_groups = list(
            settled_actions.values("possession_id")
            .annotate(action_count=Count("id"), average_x=Avg("event__x"))
            .order_by("possession_id")
        )
        block_distribution = Counter(
            block_height(round(group["average_x"]))
            for group in settled_groups
            if group["average_x"] is not None
        )
        state_counts: Counter[str] = Counter()
        for segments in counters.values_list("state_segments", flat=True):
            state_counts.update(
                segment["state"] for segment in segments if segment.get("state")
            )
        evidence = []
        for possession in counters.prefetch_related("participants").order_by(
            "provider_match__kickoff_at", "provider_match_id", "possession_index"
        )[:100]:
            evidence.append(
                {
                    "possession_id": possession.identity,
                    "match_ref": references[possession.provider_match_id],
                    "start_second": possession.start_second,
                    "duration_seconds": possession.duration_seconds,
                    "start": [
                        possession.start_x / 100 if possession.start_x is not None else None,
                        possession.start_y / 100 if possession.start_y is not None else None,
                    ],
                    "forward_metres": float(possession.counter_forward_metres or 0),
                    "elapsed_seconds": possession.counter_elapsed_seconds,
                    "speed_mps": (
                        float(possession.counter_speed_mps)
                        if possession.counter_speed_mps is not None else None
                    ),
                    "final_third_arrival": possession.counter_final_third_arrival,
                    "box_arrival": possession.counter_box_arrival,
                    "shot": possession.counter_shot,
                    "outcome": possession.counter_outcome,
                    "participant_player_ids": sorted(
                        participant.player_id
                        for participant in possession.participants.all()
                        if participant.player_id is not None
                    ),
                    "state_segments": possession.state_segments,
                }
            )
        return {
            "counters": {
                **counter_totals,
                "outcomes": dict(Counter(counters.values_list("counter_outcome", flat=True))),
                "state_episode_evidence_counts": dict(state_counts),
                "evidence": evidence,
                "evidence_limit": 100,
                "evidence_truncated": counter_totals["launches"] > 100,
            },
            "provider_observed": {
                "provider": "whoscored",
                "metric": "fast_break_shots",
                "count": observed_fast_break_shots,
                "substitutes_for_derived_counters": False,
            },
            "settled_defending": {
                "opponent_settled_possessions_with_actions": len(settled_groups),
                "defensive_actions": sum(group["action_count"] for group in settled_groups),
                "block_height_possessions": {
                    "high": block_distribution["high"],
                    "mid": block_distribution["mid"],
                    "low": block_distribution["low"],
                },
                "transition_actions_included": False,
            },
        }
