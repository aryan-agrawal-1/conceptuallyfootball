"""Compact one-pass score-event indexing for player role snapshots."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from ingestion.models import (
    MatchEventGameState,
    MatchEventShotOutcome,
    MatchStateDrawProvenance,
    ProviderMatchEvent,
    ProviderMatchPlayerStateExposure,
)
from ingestion.services.player_role_aggregation import ExposureInterval, ExposureIntervalIndex


SCORE_EVENT_INDEX_COLUMNS = (
    "id", "provider_match_id", "event_index", "team_id", "player_id",
    "timeline_seconds", "shot_outcome", "is_goal_disallowed", "is_deleted_event",
    "is_intentional_assist", "game_state_before",
)


@dataclass(slots=True)
class ScoreEventIndex:
    """Score evidence keyed by isolated player-team stint."""

    rows: dict[tuple[int, int], Counter] = field(default_factory=dict)

    def evidence(self, player_id: int, team_id: int) -> dict:
        from ingestion.services.player_role_aggregation import SCORE_EVENT_FIELDS

        values = self.rows.get((player_id, team_id), Counter())
        return {name: values[name] for name in SCORE_EVENT_FIELDS}


def score_exposure_index(competition_season, target_pairs: set[tuple[int, int]]) -> ExposureIntervalIndex:
    """Load only verified scalar exposure rows needed by the score index."""

    player_ids = {player_id for player_id, _team_id in target_pairs}
    team_ids = {team_id for _player_id, team_id in target_pairs}
    rows = ProviderMatchPlayerStateExposure.objects.filter(
        player_interval__participation__provider_match__competition_season=competition_season,
        player_interval__participation__player_id__in=player_ids,
        player_interval__participation__team_id__in=team_ids,
        player_interval__participation__status="verified",
        player_interval__participation__confidence="verified",
        player_interval__confidence="verified",
    ).values_list(
        "player_interval__participation__provider_match_id",
        "player_interval__participation__team_id",
        "player_interval__participation__player_id",
        "start_second", "end_second", "coarse_state", "team_episode__episode_index",
    ).iterator(chunk_size=2000)
    return ExposureIntervalIndex(
        ExposureInterval(
            match_id=int(match_id), team_id=int(team_id), player_id=int(player_id),
            start_second=int(start_second), end_second=int(end_second), state=str(state),
            episode_index=int(episode_index),
        )
        for match_id, team_id, player_id, start_second, end_second, state, episode_index in rows
        if (int(player_id), int(team_id)) in target_pairs
    )


def add_clutch_counts(counter: Counter, context: Mapping, suffix: str) -> None:
    transition = context.get("transition")
    provenance = context.get("draw_provenance")
    if transition == "losing_to_drawing":
        counter[f"equalising_{suffix}"] += 1
    elif transition == "drawing_to_winning":
        if provenance == MatchStateDrawProvenance.RESTORED:
            counter[f"restored_draw_winning_{suffix}"] += 1
        elif provenance == MatchStateDrawProvenance.SURRENDERED:
            counter[f"surrendered_draw_winning_{suffix}"] += 1
        elif provenance == MatchStateDrawProvenance.NEUTRAL:
            counter[f"neutral_draw_winning_{suffix}_excluded"] += 1


def score_event_index_from_rows(
    event_rows: Iterable[Mapping],
    exposure_index: ExposureIntervalIndex,
    goal_context: Mapping[int, Mapping],
    target_pairs: set[tuple[int, int]],
) -> ScoreEventIndex:
    """Build score evidence during one deterministic ordered event pass."""

    result = ScoreEventIndex({pair: Counter() for pair in target_pairs})
    assist_candidates: dict[tuple[int, int], deque[Mapping]] = {}
    used_assist_ids: set[int] = set()
    for event in event_rows:
        match_id = int(event["provider_match_id"])
        team_id = event.get("team_id")
        timeline = event.get("timeline_seconds")
        if team_id is None or timeline is None or event.get("is_deleted_event"):
            continue
        team_id = int(team_id)
        group_key = (match_id, team_id)
        candidates = assist_candidates.setdefault(group_key, deque())
        while candidates and int(timeline) - int(candidates[0]["timeline_seconds"]) > 20:
            candidates.popleft()
        player_id = event.get("player_id")
        if event.get("is_intentional_assist") and player_id is not None:
            candidates.append(event)
        if event.get("shot_outcome") != MatchEventShotOutcome.GOAL or event.get("is_goal_disallowed"):
            continue

        context = goal_context.get(int(event["id"]), {})
        if player_id is not None:
            pair = (int(player_id), team_id)
            interval = exposure_index.find(match_id, team_id, int(player_id), int(timeline))
            if pair in target_pairs and interval is not None:
                counter = result.rows[pair]
                counter["goals"] += 1
                counter["state_changing_goals"] += context.get("clutch_eligible") is True
                counter["winning_state_goals"] += event.get("game_state_before") == MatchEventGameState.WINNING
                add_clutch_counts(counter, context, "goals")

        eligible_assists = [
            candidate for candidate in candidates
            if int(candidate["id"]) not in used_assist_ids
            and 0 <= int(timeline) - int(candidate["timeline_seconds"]) <= 20
        ]
        if not eligible_assists:
            continue
        assist = max(
            eligible_assists,
            key=lambda row: (int(row["timeline_seconds"]), int(row["event_index"])),
        )
        used_assist_ids.add(int(assist["id"]))
        assist_player_id = int(assist["player_id"])
        pair = (assist_player_id, team_id)
        interval = exposure_index.find(match_id, team_id, assist_player_id, int(assist["timeline_seconds"]))
        if pair not in target_pairs or interval is None:
            continue
        counter = result.rows[pair]
        counter["intentional_assists"] += 1
        counter["state_changing_assists"] += context.get("clutch_eligible") is True
        counter["winning_state_assists"] += event.get("game_state_before") == MatchEventGameState.WINNING
        add_clutch_counts(counter, context, "assists")
    return result


def build_score_event_index(competition_season, target_pairs: set[tuple[int, int]], goal_context) -> ScoreEventIndex:
    """Read compact rows once instead of scanning a season for every snapshot."""

    if not target_pairs:
        return ScoreEventIndex()
    exposure_index = score_exposure_index(competition_season, target_pairs)
    rows = ProviderMatchEvent.objects.filter(
        provider_match__competition_season=competition_season,
    ).values(*SCORE_EVENT_INDEX_COLUMNS).order_by(
        "provider_match_id", "team_id", "timeline_seconds", "event_index", "id"
    ).iterator(chunk_size=2000)
    return score_event_index_from_rows(rows, exposure_index, goal_context, target_pairs)
