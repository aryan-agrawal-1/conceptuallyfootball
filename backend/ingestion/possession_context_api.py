from __future__ import annotations

from collections import Counter

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q, Sum
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.derived_api import _resolve_competition_season
from ingestion.models import CanonicalTeam, Provider, ProviderMatchPossession
from ingestion.services.possession_context import public_possession_thresholds


class TeamPossessionContextApi(APIView):
    """Public-safe derived counter and settled-block evidence for one team."""

    def get(self, request, canonical_team_id: int):
        competition_season = _resolve_competition_season(request)
        try:
            team = CanonicalTeam.objects.get(pk=canonical_team_id)
        except CanonicalTeam.DoesNotExist as error:
            raise DjangoValidationError("Unknown canonical team.") from error
        base = ProviderMatchPossession.objects.filter(
            provider_match__competition_season=competition_season,
            provider_match__provider=Provider.WHOSCORED,
            build__calculation_version=public_possession_thresholds()["calculation_version"],
            is_ambiguous=False,
        )
        own = base.filter(team=team)
        opponent = base.exclude(team=team).filter(
            event_links__event__team=team,
            event_links__is_settled_defensive_action=True,
        ).distinct()
        counters = own.filter(is_counter_launch=True)
        counter_totals = counters.aggregate(
            launches=Count("id"),
            final_third_arrivals=Count("id", filter=Q(counter_final_third_arrival=True)),
            box_arrivals=Count("id", filter=Q(counter_box_arrival=True)),
            shots=Count("id", filter=Q(counter_shot=True)),
        )
        observed_fast_break_shots = own.aggregate(
            count=Sum("provider_fast_break_shot_count")
        )["count"] or 0
        block_distribution = Counter(
            opponent.exclude(settled_block_height__isnull=True)
            .values_list("settled_block_height", flat=True)
        )
        state_counts: Counter[str] = Counter()
        for segments in counters.values_list("state_segments", flat=True):
            state_counts.update(
                segment["state"] for segment in segments if segment.get("state")
            )
        evidence = []
        for possession in counters.prefetch_related("participants").order_by(
            "provider_match__kickoff_at", "possession_index"
        )[:100]:
            evidence.append(
                {
                    "possession_id": possession.identity,
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
        return Response(
            {
                "team": {"id": team.id, "name": team.name},
                "competition_season": {
                    "id": competition_season.id,
                    "competition": competition_season.competition.short_code,
                    "season": competition_season.season.label,
                },
                "thresholds": public_possession_thresholds(),
                "counters": {
                    **counter_totals,
                    "outcomes": dict(Counter(counters.values_list("counter_outcome", flat=True))),
                    "state_episode_evidence_counts": dict(state_counts),
                    "evidence": evidence,
                    "evidence_limit": 100,
                },
                "provider_observed": {
                    "provider": "whoscored",
                    "metric": "fast_break_shots",
                    "count": observed_fast_break_shots,
                    "substitutes_for_derived_counters": False,
                },
                "settled_defending": {
                    "opponent_settled_possessions_with_actions": opponent.count(),
                    "defensive_actions": sum(
                        opponent.values_list("settled_defensive_action_count", flat=True)
                    ),
                    "block_height_possessions": {
                        "high": block_distribution["high"],
                        "mid": block_distribution["mid"],
                        "low": block_distribution["low"],
                    },
                    "transition_actions_included": False,
                },
            }
        )
