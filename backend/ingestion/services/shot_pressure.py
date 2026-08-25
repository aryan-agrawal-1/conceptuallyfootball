"""Deterministic, exposure-aware team shot-pressure evidence."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ingestion.models import (
    MatchEventShotOutcome,
    MatchEventShotSituation,
)
from ingestion.state_lens import StateLensScope, episode_rows


SHOT_PRESSURE_FORMULA_VERSION = "team_shot_pressure_v1"
PITCH_COLUMNS = 6
PITCH_ROWS = 4
PENALTY_MODES = {"exclude", "include", "only"}
SET_PIECE_SITUATIONS = {
    MatchEventShotSituation.SET_PIECE,
    MatchEventShotSituation.CORNER,
    MatchEventShotSituation.DIRECT_FREE_KICK,
}
ON_TARGET_OUTCOMES = {
    MatchEventShotOutcome.GOAL,
    MatchEventShotOutcome.SAVED,
}
OUTCOME_NAMES = {
    MatchEventShotOutcome.GOAL: "goal",
    MatchEventShotOutcome.SAVED: "saved",
    MatchEventShotOutcome.BLOCKED: "blocked",
    MatchEventShotOutcome.OFF_TARGET: "off_target",
    MatchEventShotOutcome.WOODWORK: "woodwork",
    MatchEventShotOutcome.UNKNOWN: "unknown",
}


@dataclass(frozen=True, slots=True)
class ShotObservation:
    event: object
    perspective: str
    episode_key: tuple[int, int]
    seconds_from_state_entry: int


def penalty_mode_shots(shots, penalty_mode: str):
    if penalty_mode == "include":
        return list(shots)
    if penalty_mode == "only":
        return [shot for shot in shots if shot.shot_situation == MatchEventShotSituation.PENALTY]
    return [shot for shot in shots if shot.shot_situation != MatchEventShotSituation.PENALTY]


def clipped_episodes(focal_team_id: int, match_ids: list[int], scope: StateLensScope):
    result = []
    for episode in episode_rows(focal_team_id, match_ids, scope).order_by(
        "provider_match_id", "episode_index"
    ):
        start = episode.start_second
        end = episode.end_second
        if scope.minimum_state_age_seconds is not None:
            start = max(start, episode.state_entry_second + scope.minimum_state_age_seconds)
        if scope.maximum_state_age_seconds is not None:
            end = min(end, episode.state_entry_second + scope.maximum_state_age_seconds)
        if end > start:
            result.append((episode, start, end))
    return result


def observations_for(shots, episodes, focal_team_id: int) -> list[ShotObservation]:
    episode_by_match: dict[int, list[tuple]] = {}
    for episode, start, end in episodes:
        episode_by_match.setdefault(episode.provider_match_id, []).append((episode, start, end))
    result = []
    for shot in shots:
        if shot.timeline_seconds is None:
            continue
        for episode, start, end in episode_by_match.get(shot.provider_match_id, []):
            if start <= shot.timeline_seconds < end:
                result.append(
                    ShotObservation(
                        event=shot,
                        perspective="for" if shot.team_id == focal_team_id else "against",
                        episode_key=(episode.provider_match_id, episode.episode_index),
                        seconds_from_state_entry=shot.timeline_seconds - episode.state_entry_second,
                    )
                )
                break
    return result


def safe_rate(count: int, exposure_seconds: int, scale_seconds: int = 60):
    if exposure_seconds <= 0:
        return None
    return round(count * scale_seconds / exposure_seconds, 4)


def is_box_shot(shot) -> bool:
    # Opta coordinates are 0..10000 with the acting team attacking x=10000.
    return (
        shot.x is not None
        and shot.y is not None
        and shot.x >= 8300
        and 2110 <= shot.y <= 7890
    )


def breakdown(observations: list[ShotObservation], exposure_seconds: int) -> dict:
    shots = [value.event for value in observations]
    outcomes = Counter(OUTCOME_NAMES.get(shot.shot_outcome, "unknown") for shot in shots)

    def metric(count: int) -> dict:
        return {
            "count": count,
            "per_minute": safe_rate(count, exposure_seconds),
            "per_90": safe_rate(count, exposure_seconds, 5400),
        }

    categories = {
        "shots": len(shots),
        "open_play": sum(
            shot.shot_situation
            in {MatchEventShotSituation.OPEN_PLAY, MatchEventShotSituation.FAST_BREAK}
            for shot in shots
        ),
        "set_piece": sum(shot.shot_situation in SET_PIECE_SITUATIONS for shot in shots),
        "penalty": sum(
            shot.shot_situation == MatchEventShotSituation.PENALTY for shot in shots
        ),
        "provider_tagged_fast_break": sum(
            shot.shot_situation == MatchEventShotSituation.FAST_BREAK for shot in shots
        ),
        "big_chance": sum(shot.is_big_chance for shot in shots),
        "box": sum(is_box_shot(shot) for shot in shots),
        "on_target": sum(shot.shot_outcome in ON_TARGET_OUTCOMES for shot in shots),
    }
    return {
        "metrics": {name: metric(count) for name, count in categories.items()},
        "outcomes": {
            name: metric(outcomes.get(name, 0))
            for name in ("goal", "saved", "blocked", "off_target", "woodwork", "unknown")
        },
        "observed_conversion": round(outcomes.get("goal", 0) / len(shots), 4) if shots else None,
    }


def first_shot_evidence(observations, episodes, perspective: str) -> dict:
    first_by_episode: dict[tuple[int, int], int] = {}
    for value in observations:
        if value.perspective != perspective:
            continue
        previous = first_by_episode.get(value.episode_key)
        if previous is None or value.seconds_from_state_entry < previous:
            first_by_episode[value.episode_key] = value.seconds_from_state_entry
    total_episodes = len(episodes)
    values = sorted(first_by_episode.values())
    return {
        "episode_count": total_episodes,
        "episodes_with_shot": len(values),
        "zero_shot_episodes": total_episodes - len(values),
        "mean_seconds_from_state_entry": (
            round(sum(values) / len(values), 2) if values else None
        ),
        "median_seconds_from_state_entry": (
            values[len(values) // 2]
            if len(values) % 2
            else round((values[len(values) // 2 - 1] + values[len(values) // 2]) / 2, 2)
            if values
            else None
        ),
    }


def pitch_surface(observations: list[ShotObservation], exposure_seconds: int) -> dict:
    counts = Counter()
    goals = Counter()
    located = 0
    for value in observations:
        shot = value.event
        if shot.x is None or shot.y is None:
            continue
        column = min(PITCH_COLUMNS - 1, shot.x * PITCH_COLUMNS // 10001)
        row = min(PITCH_ROWS - 1, shot.y * PITCH_ROWS // 10001)
        counts[(column, row)] += 1
        goals[(column, row)] += shot.shot_outcome == MatchEventShotOutcome.GOAL
        located += 1
    cells = []
    for row in range(PITCH_ROWS):
        for column in range(PITCH_COLUMNS):
            count = counts[(column, row)]
            cells.append(
                {
                    "column": column,
                    "row": row,
                    "shot_count": count,
                    "shots_per_90": safe_rate(count, exposure_seconds, 5400),
                    "location_share": round(count / located, 4) if located else None,
                    "observed_conversion": (
                        round(goals[(column, row)] / count, 4) if count else None
                    ),
                }
            )
    return {
        "columns": PITCH_COLUMNS,
        "rows": PITCH_ROWS,
        "located_shots": located,
        "unlocated_shots": len(observations) - located,
        "cells": cells,
    }


def cohort_payload(
    *,
    focal_team_id: int,
    match_ids: list[int],
    scoped_shots,
    scope: StateLensScope,
    evidence: dict,
) -> dict:
    episodes = clipped_episodes(focal_team_id, match_ids, scope)
    observations = observations_for(scoped_shots, episodes, focal_team_id)
    shots_for = [value for value in observations if value.perspective == "for"]
    shots_against = [value for value in observations if value.perspective == "against"]
    exposure_seconds = evidence["exposure_seconds"]
    for_payload = breakdown(shots_for, exposure_seconds)
    against_payload = breakdown(shots_against, exposure_seconds)
    openness_count = len(shots_for) + len(shots_against)
    return {
        "scope": scope.public(),
        "evidence": {
            **evidence,
            "zero_shot_episodes_for": len(episodes)
            - len({value.episode_key for value in shots_for}),
            "zero_shot_episodes_against": len(episodes)
            - len({value.episode_key for value in shots_against}),
        },
        "frequency": {
            "for": for_payload["metrics"],
            "against": against_payload["metrics"],
            "openness": {
                "shot_count": openness_count,
                "shots_per_minute": safe_rate(openness_count, exposure_seconds),
                "shots_per_90": safe_rate(openness_count, exposure_seconds, 5400),
            },
        },
        "outcomes": {
            "for": for_payload["outcomes"],
            "against": against_payload["outcomes"],
            "observed_conversion_for": for_payload["observed_conversion"],
            "observed_conversion_against": against_payload["observed_conversion"],
        },
        "first_shot": {
            "for": first_shot_evidence(observations, episodes, "for"),
            "against": first_shot_evidence(observations, episodes, "against"),
        },
        "location": {
            "for": pitch_surface(shots_for, exposure_seconds),
            "against": pitch_surface(shots_against, exposure_seconds),
        },
    }
