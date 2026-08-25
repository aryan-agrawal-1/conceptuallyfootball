"""Deterministic, bounded passing evidence for a team game-state cohort."""

from __future__ import annotations

from collections import Counter, defaultdict
from math import hypot
from typing import Iterable

from ingestion.models import MatchEventType, ProviderMatchEvent
from ingestion.services.event_profiles import PASS_FLOW_COLUMNS, PASS_FLOW_ROWS
from ingestion.services.whoscored_normalization import grid_assignment

PASS_STATE_FORMULA_VERSION = "pass_state_v1"
PITCH_LENGTH_METRES = 105.0
PITCH_WIDTH_METRES = 68.0
LATERAL_DIRECTION_THRESHOLD_METRES = 1.0
LENGTH_BANDS = (("short", 0.0, 15.0), ("medium", 15.0, 30.0), ("long", 30.0, None))
PASS_STATE_EVENT_LIMIT = 50_000


def physical_vector(event: ProviderMatchEvent) -> tuple[float, float, float]:
    """Return forward, lateral and total metres from 0..10000 Opta coordinates."""
    forward = (event.end_x - event.x) * PITCH_LENGTH_METRES / 10_000
    lateral = (event.end_y - event.y) * PITCH_WIDTH_METRES / 10_000
    return forward, lateral, hypot(forward, lateral)


def direction(forward_metres: float) -> str:
    if forward_metres > LATERAL_DIRECTION_THRESHOLD_METRES:
        return "forward"
    if forward_metres < -LATERAL_DIRECTION_THRESHOLD_METRES:
        return "backward"
    return "lateral"


def length_band(length_metres: float) -> str:
    for name, minimum, maximum in LENGTH_BANDS:
        if length_metres >= minimum and (maximum is None or length_metres < maximum):
            return name
    raise AssertionError("length bands must cover every non-negative distance")


def rate(count: int, exposure_seconds: int) -> float | None:
    return round(count * 60 / exposure_seconds, 4) if exposure_seconds else None


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def category_rows(attempts: Counter, completions: Counter, order: Iterable[str]) -> list[dict]:
    total = sum(attempts.values())
    return [
        {
            "category": category,
            "attempts": attempts[category],
            "completions": completions[category],
            "incompletions": attempts[category] - completions[category],
            "attempt_share": ratio(attempts[category], total),
            "completion_rate": ratio(completions[category], attempts[category]),
        }
        for category in order
    ]


def build_pass_state_evidence(
    events: Iterable[ProviderMatchEvent],
    *,
    exposure_seconds: int,
    source_event_count: int | None = None,
    source_completion_count: int | None = None,
    source_progressive_attempt_count: int | None = None,
    source_progressive_completion_count: int | None = None,
    source_missing_coordinate_count: int | None = None,
) -> dict:
    """Aggregate choice, execution and flow without returning unbounded event rows."""
    pass_rows = [event for event in events if event.event_type == MatchEventType.PASS]
    processed_rows = pass_rows[:PASS_STATE_EVENT_LIMIT]
    rows = []
    processed_missing_coordinates = 0
    for event in processed_rows:
        if None in (event.x, event.y, event.end_x, event.end_y):
            processed_missing_coordinates += 1
            continue
        rows.append(event)

    attempts = source_event_count if source_event_count is not None else len(pass_rows)
    completions = (
        source_completion_count
        if source_completion_count is not None
        else sum(event.outcome_successful is True for event in pass_rows)
    )
    incompletions = attempts - completions
    located_attempts = len(rows)
    excluded_missing_coordinates = (
        source_missing_coordinate_count
        if source_missing_coordinate_count is not None
        else sum(
            None in (event.x, event.y, event.end_x, event.end_y)
            for event in pass_rows
        )
    )
    truncated = attempts > PASS_STATE_EVENT_LIMIT
    direction_attempts: Counter[str] = Counter()
    direction_completions: Counter[str] = Counter()
    length_attempts: Counter[str] = Counter()
    length_completions: Counter[str] = Counter()
    flow = defaultdict(lambda: {
        "attempts": 0, "completions": 0, "origin_x": 0.0, "origin_y": 0.0,
        "forward": 0.0, "lateral": 0.0, "length": 0.0,
    })
    origin_conditioned = defaultdict(lambda: {
        "attempts": Counter(), "completions": Counter(), "length": 0.0,
        "forward": 0.0,
    })
    length_sum = forward_sum = origin_x_sum = destination_x_sum = 0.0
    progressive_attempts = (
        source_progressive_attempt_count
        if source_progressive_attempt_count is not None
        else sum(event.is_progressive_pass for event in pass_rows)
    )
    progressive_completions = (
        source_progressive_completion_count
        if source_progressive_completion_count is not None
        else sum(
            event.is_progressive_pass and event.outcome_successful is True
            for event in pass_rows
        )
    )

    for event in rows:
        forward, lateral, length = physical_vector(event)
        event_direction = direction(forward)
        event_length_band = length_band(length)
        completed = event.outcome_successful is True
        direction_attempts[event_direction] += 1
        length_attempts[event_length_band] += 1
        direction_completions[event_direction] += int(completed)
        length_completions[event_length_band] += int(completed)
        length_sum += length
        forward_sum += forward
        origin_x_sum += event.x / 100
        destination_x_sum += event.end_x / 100
        column, row, _ = grid_assignment(event.x, event.y, PASS_FLOW_COLUMNS, PASS_FLOW_ROWS)
        cell = flow[(column, row)]
        cell["attempts"] += 1
        cell["completions"] += int(completed)
        cell["origin_x"] += event.x / 100
        cell["origin_y"] += event.y / 100
        cell["forward"] += forward
        cell["lateral"] += lateral
        cell["length"] += length
        conditioned = origin_conditioned[(column, row)]
        conditioned["attempts"][event_direction] += 1
        conditioned["completions"][event_direction] += int(completed)
        conditioned["length"] += length
        conditioned["forward"] += forward

    flow_rows = []
    conditioned_rows = []
    for column in range(PASS_FLOW_COLUMNS):
        for row in range(PASS_FLOW_ROWS):
            cell = flow[(column, row)]
            count = cell["attempts"]
            if not count:
                continue
            flow_rows.append({
                "column": column,
                "row": row,
                "attempts": count,
                "completions": cell["completions"],
                "incompletions": count - cell["completions"],
                "attempts_per_state_minute": rate(count, exposure_seconds),
                "attempt_share": ratio(count, located_attempts),
                "completion_rate": ratio(cell["completions"], count),
                "mean_origin_x": round(cell["origin_x"] / count, 4),
                "mean_origin_y": round(cell["origin_y"] / count, 4),
                "mean_forward_metres": round(cell["forward"] / count, 3),
                "mean_lateral_metres": round(cell["lateral"] / count, 3),
                "mean_length_metres": round(cell["length"] / count, 3),
                "mean_destination_x": round(cell["origin_x"] / count + cell["forward"] / count / PITCH_LENGTH_METRES * 100, 4),
                "mean_destination_y": round(cell["origin_y"] / count + cell["lateral"] / count / PITCH_WIDTH_METRES * 100, 4),
            })
            conditioned = origin_conditioned[(column, row)]
            conditioned_rows.append({
                "column": column,
                "row": row,
                "attempts": count,
                "attempt_share": ratio(count, located_attempts),
                "mean_length_metres": round(conditioned["length"] / count, 3),
                "mean_forward_metres": round(conditioned["forward"] / count, 3),
                "directions": category_rows(
                    conditioned["attempts"], conditioned["completions"],
                    ("forward", "lateral", "backward"),
                ),
            })

    return {
        "formula_version": PASS_STATE_FORMULA_VERSION,
        "pitch": {
            "length_metres": PITCH_LENGTH_METRES,
            "width_metres": PITCH_WIDTH_METRES,
            "coordinate_range": [0, 10_000],
            "orientation": "acting_team_left_to_right",
            "length_formula": "hypot((end_x-x)*105/10000, (end_y-y)*68/10000)",
        },
        "definitions": {
            "attempt": "normalized pass event; coordinates are not required for volume or execution",
            "spatial_attempt": "attempt with complete origin and destination coordinates",
            "completion": "attempt where outcome_successful is true",
            "direction": "forward > 1m; backward < -1m; otherwise lateral",
            "length_bands_metres": {"short": "[0,15)", "medium": "[15,30)", "long": "[30,+inf)"},
            "receiver_inferred": False,
            "possession_inferred": False,
            "pressure_inferred": False,
            "pass_value_inferred": False,
        },
        "exposure_seconds": exposure_seconds,
        "exposure_minutes": round(exposure_seconds / 60, 4),
        "summary": {
            "attempts": attempts,
            "completions": completions,
            "incompletions": incompletions,
            "attempts_per_state_minute": rate(attempts, exposure_seconds),
            "completions_per_state_minute": rate(completions, exposure_seconds),
            "completion_rate": ratio(completions, attempts),
            "progressive_attempts": progressive_attempts,
            "progressive_attempt_rate": ratio(progressive_attempts, attempts),
            "progressive_completion_rate": ratio(progressive_completions, progressive_attempts),
            "mean_length_metres": round(length_sum / located_attempts, 3) if located_attempts else None,
            "mean_forward_metres": round(forward_sum / located_attempts, 3) if located_attempts else None,
            "mean_origin_height": round(origin_x_sum / located_attempts, 3) if located_attempts else None,
            "mean_destination_height": round(destination_x_sum / located_attempts, 3) if located_attempts else None,
        },
        "directions": category_rows(direction_attempts, direction_completions, ("forward", "lateral", "backward")),
        "length_bands": category_rows(length_attempts, length_completions, ("short", "medium", "long")),
        "origin_conditioned": conditioned_rows,
        "flow": flow_rows,
        "evidence": {
            "source_pass_events": attempts,
            "located_pass_events": located_attempts,
            "excluded_missing_coordinates": excluded_missing_coordinates,
            "processed_missing_coordinates": processed_missing_coordinates,
            "processed_event_limit": PASS_STATE_EVENT_LIMIT,
            "truncated": truncated,
            "sparse": attempts < 30,
            "empty": attempts == 0,
            "spatial_empty": located_attempts == 0,
            "fixed_origin_bin_limit": PASS_FLOW_COLUMNS * PASS_FLOW_ROWS,
        },
    }


def comparison_delta(selected: dict, baseline: dict) -> dict:
    """Return compact, null-safe deltas while retaining both full cohorts."""
    keys = (
        "attempts_per_state_minute", "completion_rate", "progressive_attempt_rate",
        "mean_length_metres", "mean_forward_metres", "mean_origin_height",
        "mean_destination_height",
    )
    values = {}
    for key in keys:
        selected_value = selected["summary"][key]
        baseline_value = baseline["summary"][key]
        values[key] = (
            round(selected_value - baseline_value, 4)
            if selected_value is not None and baseline_value is not None else None
        )
    return values
