"""Deterministic, evidence-first Team Style Shape calculations.

The shape is a description of *prevalence* rather than performance.  It is
deliberately assembled from the Batch 9 contracts instead of introducing a
second interpretation of passes, defensive events, state exposure, or
possession context.  Raw components stay beside every derived axis so a
consumer can audit a value without treating the profile as a quality score.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from math import hypot
from statistics import median
from typing import Any, Iterable, Sequence

from ingestion.models import MatchEventShotSituation, MatchEventType
from ingestion.services.defensive_territory import (
    ALWAYS_DEFENSIVE_TYPES,
    FAMILY_BY_TYPE,
    QUALIFIED_DEFENSIVE_TYPES,
    defensive_family,
    focal_defensive_location,
)
from ingestion.services.pass_state import (
    PITCH_LENGTH_METRES,
    PITCH_WIDTH_METRES,
    direction as pass_direction,
    physical_vector,
)
from ingestion.services.shot_pressure import penalty_mode_shots


TEAM_STYLE_SHAPE_FORMULA_VERSION = "team_style_shape_v2"
STYLE_PERCENTILE_VERSION = "midrank_percentile_v1"

# A state cohort can retain raw values below these thresholds, but its
# percentile and signed-shift normalisation are withheld.  The thresholds are
# intentionally per evidence family: a rare counter sample must not inherit a
# dense pass-event threshold, and a high number of events cannot compensate for
# no verified state exposure.
MIN_STYLE_EXPOSURE_SECONDS = 900
MIN_AXIS_EVENTS = 30
MIN_CARRY_EVENTS = 10
MIN_SHOT_EVENTS = 5
MIN_RECOVERY_EVENTS = 10
MIN_SETTLED_BLOCKS = 5
MIN_COUNTER_EVENTS = 5


AXIS_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "key": "pass_length",
        "category": "build_up",
        "label": "Pass length",
        "description": "Mean physical length of attempted passes.",
        "formula": "mean(hypot(forward_metres, lateral_metres)) over located pass attempts",
        "unit": "metres per pass",
        "higher_means": "longer attempted passes are more prevalent",
        "evidence_type": "pass_attempts_with_coordinates",
        "minimum_evidence": {"exposure_seconds": MIN_STYLE_EXPOSURE_SECONDS, "events": MIN_AXIS_EVENTS},
    },
    {
        "key": "pass_directness",
        "category": "build_up",
        "label": "Pass directness",
        "description": "Share of attempted passes travelling materially forward.",
        "formula": "forward_attempts / located_pass_attempts; forward means >1 metre",
        "unit": "share of passes",
        "higher_means": "forward-directed attempts are more prevalent",
        "evidence_type": "pass_attempts_with_coordinates",
        "minimum_evidence": {"exposure_seconds": MIN_STYLE_EXPOSURE_SECONDS, "events": MIN_AXIS_EVENTS},
    },
    {
        "key": "forward_intent",
        "category": "build_up",
        "label": "Forward intent",
        "description": "Share of attempted passes tagged progressive by the normalized contract.",
        "formula": "progressive_pass_attempts / pass_attempts",
        "unit": "share of passes",
        "higher_means": "progressive pass attempts are more prevalent",
        "evidence_type": "pass_attempts",
        "minimum_evidence": {"exposure_seconds": MIN_STYLE_EXPOSURE_SECONDS, "events": MIN_AXIS_EVENTS},
    },
    {
        "key": "circulation_security",
        "category": "build_up",
        "label": "Completed pass rate",
        "description": "The share of attempted passes completed by the acting team.",
        "formula": "completed_passes / pass_attempts",
        "unit": "share of passes",
        "higher_means": "completed circulation is more prevalent",
        "evidence_type": "pass_attempts",
        "minimum_evidence": {"exposure_seconds": MIN_STYLE_EXPOSURE_SECONDS, "events": MIN_AXIS_EVENTS},
    },
    {
        "key": "progressive_actions",
        "category": "progression_attack",
        "label": "Progressive actions",
        "description": "Progressive passes and derived progressive carries per 90 verified state minutes.",
        "formula": "(progressive_passes + progressive_carries) * 5400 / exposure_seconds",
        "unit": "actions per 90 state minutes",
        "higher_means": "progressive actions are more prevalent",
        "evidence_type": "progressive_passes_and_derived_carries",
        "minimum_evidence": {"exposure_seconds": MIN_STYLE_EXPOSURE_SECONDS, "events": MIN_AXIS_EVENTS},
    },
    {
        "key": "box_entry_rate",
        "category": "progression_attack",
        "label": "Box-entry rate",
        "description": "Passes and derived carries entering the penalty box per 90 verified state minutes.",
        "formula": "(box_entry_passes + box_entry_carries) * 5400 / exposure_seconds",
        "unit": "entries per 90 state minutes",
        "higher_means": "box entries are more prevalent",
        "evidence_type": "pass_and_derived_carry_entries",
        "minimum_evidence": {"exposure_seconds": MIN_STYLE_EXPOSURE_SECONDS, "events": MIN_AXIS_EVENTS},
    },
    {
        "key": "carry_progression",
        "category": "progression_attack",
        "label": "Carry progression",
        "description": "Share of derived carries tagged progressive.",
        "formula": "progressive_carries / derived_carries",
        "unit": "share of derived carries",
        "higher_means": "progressive carries are more prevalent",
        "evidence_type": "derived_carries",
        "minimum_evidence": {"exposure_seconds": MIN_STYLE_EXPOSURE_SECONDS, "events": MIN_CARRY_EVENTS},
    },
    {
        "key": "shot_frequency",
        "category": "progression_attack",
        "label": "Shot frequency",
        "description": "Non-penalty team shots per 90 verified state minutes.",
        "formula": "non_penalty_shots * 5400 / exposure_seconds",
        "unit": "shots per 90 state minutes",
        "higher_means": "non-penalty shots are more prevalent",
        "evidence_type": "team_shots_excluding_penalties",
        "minimum_evidence": {"exposure_seconds": MIN_STYLE_EXPOSURE_SECONDS, "events": MIN_SHOT_EVENTS},
    },
    {
        "key": "defensive_action_height",
        "category": "defence",
        "label": "Defensive-action height",
        "description": "The median location of every qualified, located defensive action, including transition defending, measured from the team's own goal.",
        "formula": "median(qualified_defensive_action_x / 100)",
        "unit": "pitch x percentage",
        "higher_means": "defensive actions farther from the own goal are more prevalent",
        "evidence_type": "qualified_defensive_events_with_coordinates",
        "minimum_evidence": {"exposure_seconds": MIN_STYLE_EXPOSURE_SECONDS, "events": MIN_AXIS_EVENTS},
    },
    {
        "key": "recovery_height",
        "category": "defence",
        "label": "Recovery height",
        "description": "Median location of ball recoveries measured from the team's own goal.",
        "formula": "median(recovery_x / 100)",
        "unit": "pitch x percentage",
        "higher_means": "recoveries farther from the own goal are more prevalent",
        "evidence_type": "ball_recoveries_with_coordinates",
        "minimum_evidence": {"exposure_seconds": MIN_STYLE_EXPOSURE_SECONDS, "events": MIN_RECOVERY_EVENTS},
    },
    {
        "key": "deep_defending_concentration",
        "category": "defence",
        "label": "Deep-defending concentration",
        "description": "Share of located non-clearance defensive actions in the defensive third.",
        "formula": "non_clearance_actions_at_x<33.33 / located_non_clearance_actions",
        "unit": "share of non-clearance actions",
        "higher_means": "deep non-clearance actions are more prevalent",
        "evidence_type": "qualified_non_clearance_defensive_events_with_coordinates",
        "minimum_evidence": {"exposure_seconds": MIN_STYLE_EXPOSURE_SECONDS, "events": MIN_AXIS_EVENTS},
    },
    {
        "key": "settled_block_height",
        "category": "defence",
        "label": "Settled block height",
        "description": "The median average defensive location once an opponent possession is established; transition defending is excluded.",
        "formula": "median(mean(settled_defensive_action_x) / 100)",
        "unit": "pitch x percentage",
        "higher_means": "higher settled blocks are more prevalent",
        "evidence_type": "settled_opponent_possessions",
        "minimum_evidence": {"exposure_seconds": MIN_STYLE_EXPOSURE_SECONDS, "events": MIN_SETTLED_BLOCKS},
    },
    {
        "key": "counter_launch",
        "category": "transitions",
        "label": "Counter starts",
        "description": "Possessions that start with a non-restart recovery or control change at or behind x=60, then are tracked for 12 seconds for forward progress.",
        "formula": "counter_starts * 5400 / exposure_seconds",
        "unit": "counter starts per 90 state minutes",
        "higher_means": "counter starts are more prevalent",
        "evidence_type": "derived_possession_counters",
        "minimum_evidence": {"exposure_seconds": MIN_STYLE_EXPOSURE_SECONDS, "events": MIN_COUNTER_EVENTS},
    },
    {
        "key": "counter_arrival",
        "category": "transitions",
        "label": "Counters reaching final third",
        "description": "The share of derived counter starts that travel at least 21 metres forward within 12 seconds and reach the final third at x≥66.67.",
        "formula": "counter_final_third_arrivals / counter_starts",
        "unit": "share of counter starts",
        "higher_means": "counter starts reaching the final third are more prevalent",
        "evidence_type": "derived_possession_counters",
        "minimum_evidence": {"exposure_seconds": MIN_STYLE_EXPOSURE_SECONDS, "events": MIN_COUNTER_EVENTS},
    },
    {
        "key": "counter_speed",
        "category": "transitions",
        "label": "Counter speed",
        "description": "Mean derived counter forward speed where elapsed time is available.",
        "formula": "mean(counter_forward_metres / counter_elapsed_seconds)",
        "unit": "metres per second",
        "higher_means": "faster derived counter progress is more prevalent",
        "evidence_type": "derived_counters_with_speed",
        "minimum_evidence": {"exposure_seconds": MIN_STYLE_EXPOSURE_SECONDS, "events": MIN_COUNTER_EVENTS},
    },
    {
        "key": "counter_shot_tendency",
        "category": "transitions",
        "label": "Counters leading to shots",
        "description": "The share of derived counter starts that meet the 21-metre progress rule and contain a shot within the 12-second window.",
        "formula": "counter_shots / counter_starts",
        "unit": "share of counter starts",
        "higher_means": "counter starts leading to shots are more prevalent",
        "evidence_type": "derived_possession_counters",
        "minimum_evidence": {"exposure_seconds": MIN_STYLE_EXPOSURE_SECONDS, "events": MIN_COUNTER_EVENTS},
    },
)

AXIS_BY_KEY = {definition["key"]: definition for definition in AXIS_DEFINITIONS}
DEFAULT_AXIS_KEYS = tuple(AXIS_BY_KEY)


def axis_definitions(axis_keys: Sequence[str] | None = None) -> list[dict[str, Any]]:
    """Return a JSON-safe copy of the public axis contract."""

    keys = set(axis_keys or DEFAULT_AXIS_KEYS)
    return [
        {**definition, "direction": "prevalence", "percentile_version": STYLE_PERCENTILE_VERSION}
        for definition in AXIS_DEFINITIONS
        if definition["key"] in keys
    ]


def _round(value: float | None, places: int = 4) -> float | None:
    return round(value, places) if value is not None else None


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    return _round(float(numerator) / float(denominator)) if denominator else None


def _rate_per_90(count: int | float, exposure_seconds: int) -> float | None:
    return _round(float(count) * 5400 / exposure_seconds) if exposure_seconds else None


def _event_value(event: Any, name: str, default: Any = None) -> Any:
    if isinstance(event, dict):
        return event.get(name, default)
    return getattr(event, name, default)


def _row_value(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


def _physical_vector(row: Any) -> tuple[float, float, float]:
    """Use the Batch 9 vector contract for model rows and compact mappings."""

    if isinstance(row, dict):
        forward = (row["end_x"] - row["x"]) * PITCH_LENGTH_METRES / 10_000
        lateral = (row["end_y"] - row["y"]) * PITCH_WIDTH_METRES / 10_000
        return forward, lateral, hypot(forward, lateral)
    return physical_vector(row)


def _defensive_family(row: Any) -> str | None:
    """Dispatch the shared defensive qualifier for compact API rows."""

    if not isinstance(row, dict):
        return defensive_family(row)
    event_type = row.get("event_type")
    if event_type in ALWAYS_DEFENSIVE_TYPES:
        return FAMILY_BY_TYPE[event_type]
    if event_type in QUALIFIED_DEFENSIVE_TYPES and row.get("is_defensive"):
        return FAMILY_BY_TYPE[event_type]
    return None


def _focal_defensive_location(row: Any) -> tuple[int | None, int | None]:
    if isinstance(row, dict):
        return row.get("x"), row.get("y")
    return focal_defensive_location(row)


def _non_penalty_shots(shots: Sequence[Any]) -> list[Any]:
    """Apply the Batch 9 penalty mode to compact rows without model access."""

    if shots and isinstance(shots[0], dict):
        return [
            shot
            for shot in shots
            if shot.get("shot_situation") != MatchEventShotSituation.PENALTY
        ]
    return penalty_mode_shots(shots, "exclude")


def _axis_reliability(
    definition: Mapping[str, Any],
    *,
    exposure_seconds: int,
    evidence_count: int,
    matches_excluded: int,
    raw_value: float | None,
) -> tuple[str, bool, str | None]:
    if raw_value is None:
        return "unavailable", False, "source evidence is absent"
    minimum = definition["minimum_evidence"]
    if exposure_seconds <= 0:
        return "unavailable", False, "verified state exposure is zero"
    if exposure_seconds < minimum["exposure_seconds"] or evidence_count < minimum["events"]:
        return "sparse", False, (
            f"requires {minimum['events']} evidence events and "
            f"{minimum['exposure_seconds']} exposure seconds"
        )
    if matches_excluded:
        return "partial", True, "one or more source matches were excluded"
    return "verified", True, None


def _axis(
    definition: Mapping[str, Any],
    *,
    value: float | None,
    raw: Mapping[str, Any],
    evidence_count: int,
    exposure_seconds: int,
    matches_excluded: int,
    formula_version: str,
) -> dict[str, Any]:
    reliability, percentile_eligible, reason = _axis_reliability(
        definition,
        exposure_seconds=exposure_seconds,
        evidence_count=evidence_count,
        matches_excluded=matches_excluded,
        raw_value=value,
    )
    return {
        "key": definition["key"],
        "category": definition["category"],
        "label": definition["label"],
        "description": definition["description"],
        "formula": definition["formula"],
        "formula_version": formula_version,
        "value": value,
        "raw_value": value,
        "unit": definition["unit"],
        "direction": "prevalence",
        "raw": dict(raw),
        "evidence": {
            "count": evidence_count,
            "exposure_seconds": exposure_seconds,
            "minimum": dict(definition["minimum_evidence"]),
        },
        "reliability": reliability,
        "percentile_eligible": percentile_eligible,
        "percentile": None,
        "ineligibility_reason": reason,
    }


def _coerce_rows(rows: Iterable[Any] | None) -> list[Any]:
    return list(rows or ())


def build_style_cohort(
    events: Iterable[Any],
    *,
    exposure_seconds: int,
    possessions: Iterable[Any] | None = None,
    settled_blocks: Iterable[Any] | None = None,
    carries: Iterable[Any] | None = None,
    scope: Mapping[str, Any] | None = None,
    match_count: int = 0,
    episode_count: int = 0,
    matches_excluded: int = 0,
    axis_keys: Sequence[str] | None = None,
    formula_version: str = TEAM_STYLE_SHAPE_FORMULA_VERSION,
) -> dict[str, Any]:
    """Build raw style axes for one team and one state cohort.

    ``events`` must already be scoped to the focal team and canonical State
    Lens.  ``possessions`` should contain only the focal team's derived
    possession rows and ``settled_blocks`` contains opponent possessions where
    a persisted event link is explicitly marked settled defensive (the API
    adapter supplies that to preserve the exact #112 boundary).
    """

    selected_keys = tuple(axis_keys or DEFAULT_AXIS_KEYS)
    unknown = sorted(set(selected_keys) - set(DEFAULT_AXIS_KEYS))
    if unknown:
        raise ValueError(f"Unknown Team Style Shape axes: {', '.join(unknown)}")

    event_rows = _coerce_rows(events)
    possession_rows = _coerce_rows(possessions)
    carry_rows = _coerce_rows(carries)
    pass_rows = [row for row in event_rows if _event_value(row, "event_type") == MatchEventType.PASS]
    located_passes = [
        row for row in pass_rows
        if None not in (
            _event_value(row, "x"),
            _event_value(row, "y"),
            _event_value(row, "end_x"),
            _event_value(row, "end_y"),
        )
    ]
    pass_vectors = [_physical_vector(row) for row in located_passes]
    lengths = [vector[2] for vector in pass_vectors]
    forward_passes = sum(pass_direction(vector[0]) == "forward" for vector in pass_vectors)
    pass_completions = sum(_event_value(row, "outcome_successful") is True for row in pass_rows)
    progressive_passes = sum(bool(_event_value(row, "is_progressive_pass", False)) for row in pass_rows)

    carry_attempts = len(carry_rows)
    progressive_carries = sum(bool(_row_value(row, "is_progressive_carry", False)) for row in carry_rows)
    carry_box_entries = sum(bool(_row_value(row, "is_box_entry", False)) for row in carry_rows)
    carry_final_third_entries = sum(bool(_row_value(row, "is_final_third_entry", False)) for row in carry_rows)

    shots = [row for row in event_rows if _event_value(row, "event_type") == MatchEventType.SHOT]
    non_penalty_shot_rows = _non_penalty_shots(shots)
    penalty_shots = [
        row for row in shots
        if _event_value(row, "shot_situation") == MatchEventShotSituation.PENALTY
    ]
    non_penalty_shots = len(non_penalty_shot_rows)

    defensive_rows = []
    for row in event_rows:
        family = _defensive_family(row)
        location = _focal_defensive_location(row)
        if family is not None and location[0] is not None:
            defensive_rows.append((row, family, location[0]))
    defensive_heights = [float(item[2]) / 100 for item in defensive_rows]
    recovery_heights = [float(item[2]) / 100 for item in defensive_rows if item[1] == "recovery"]
    non_clearance = [item for item in defensive_rows if item[1] != "clearance"]
    deep_non_clearance = [item for item in non_clearance if item[2] < 3333]

    # The API adapter supplies rows from opponent possessions where an event
    # link is explicitly marked settled defensive. Keeping this input separate
    # makes it impossible to accidentally turn transition defence into an
    # organised-block claim.
    block_rows = _coerce_rows(settled_blocks)
    # Counter rows are the persisted own possessions.
    counter_rows = [
        row for row in possession_rows
        if bool(_row_value(row, "is_counter_launch", False))
    ]
    counter_arrivals = sum(bool(_row_value(row, "counter_final_third_arrival", False)) for row in counter_rows)
    counter_shots = sum(bool(_row_value(row, "counter_shot", False)) for row in counter_rows)
    counter_speeds = [
        float(_row_value(row, "counter_speed_mps"))
        for row in counter_rows
        if _row_value(row, "counter_speed_mps") is not None
    ]
    settled_heights = [
        float(_row_value(row, "settled_defensive_average_x")) / 100
        for row in block_rows
        if _row_value(row, "settled_defensive_average_x") is not None
    ]

    axis_values: dict[str, dict[str, Any]] = {}
    raw_definitions: dict[str, tuple[float | None, Mapping[str, Any], int]] = {
        "pass_length": (
            _round(sum(lengths) / len(lengths), 3) if lengths else None,
            {
                "pass_attempts": len(pass_rows),
                "located_pass_attempts": len(located_passes),
                "length_sum_metres": _round(sum(lengths), 3),
                "missing_coordinate_passes": len(pass_rows) - len(located_passes),
            },
            len(located_passes),
        ),
        "pass_directness": (
            _ratio(forward_passes, len(located_passes)),
            {
                "forward_attempts": forward_passes,
                "located_pass_attempts": len(located_passes),
                "direction_threshold_metres": 1.0,
            },
            len(located_passes),
        ),
        "forward_intent": (
            _ratio(progressive_passes, len(pass_rows)),
            {"progressive_pass_attempts": progressive_passes, "pass_attempts": len(pass_rows)},
            len(pass_rows),
        ),
        "circulation_security": (
            _ratio(pass_completions, len(pass_rows)),
            {"completed_passes": pass_completions, "pass_attempts": len(pass_rows)},
            len(pass_rows),
        ),
        "progressive_actions": (
            _rate_per_90(progressive_passes + progressive_carries, exposure_seconds),
            {
                "progressive_passes": progressive_passes,
                "progressive_carries": progressive_carries,
                "progressive_actions": progressive_passes + progressive_carries,
                "pass_attempts": len(pass_rows),
                "carry_attempts": carry_attempts,
            },
            len(pass_rows) + carry_attempts,
        ),
        "box_entry_rate": (
            _rate_per_90(
                sum(bool(_event_value(row, "is_box_entry", False)) for row in pass_rows)
                + carry_box_entries,
                exposure_seconds,
            ),
            {
                "pass_box_entries": sum(bool(_event_value(row, "is_box_entry", False)) for row in pass_rows),
                "carry_box_entries": carry_box_entries,
                "pass_attempts": len(pass_rows),
                "carry_attempts": carry_attempts,
                "final_third_carry_entries": carry_final_third_entries,
            },
            len(pass_rows) + carry_attempts,
        ),
        "carry_progression": (
            _ratio(progressive_carries, carry_attempts),
            {"progressive_carries": progressive_carries, "carry_attempts": carry_attempts},
            carry_attempts,
        ),
        "shot_frequency": (
            _rate_per_90(non_penalty_shots, exposure_seconds),
            {
                "non_penalty_shots": non_penalty_shots,
                "all_shots": len(shots),
                "excluded_penalty_shots": len(penalty_shots),
            },
            non_penalty_shots,
        ),
        "defensive_action_height": (
            _round(float(median(defensive_heights)), 2) if defensive_heights else None,
            {
                "located_defensive_actions": len(defensive_heights),
                "defensive_action_families": dict(Counter(item[1] for item in defensive_rows)),
                "location_frame": "focal_team_defending_perspective",
            },
            len(defensive_heights),
        ),
        "recovery_height": (
            _round(float(median(recovery_heights)), 2) if recovery_heights else None,
            {"located_recoveries": len(recovery_heights), "location_frame": "focal_team_defending_perspective"},
            len(recovery_heights),
        ),
        "deep_defending_concentration": (
            _ratio(len(deep_non_clearance), len(non_clearance)),
            {
                "deep_non_clearance_actions": len(deep_non_clearance),
                "located_non_clearance_actions": len(non_clearance),
                "defensive_third_boundary_x": 33.33,
            },
            len(non_clearance),
        ),
        "settled_block_height": (
            _round(float(median(settled_heights)), 2) if settled_heights else None,
            {
                "settled_block_possessions": len(settled_heights),
                "settled_block_heights": [_round(value, 2) for value in settled_heights],
                "transition_defence_included": False,
            },
            len(settled_heights),
        ),
        "counter_launch": (
            _rate_per_90(len(counter_rows), exposure_seconds),
            {
                "derived_counter_launches": len(counter_rows),
                "provider_tagged_fast_break_shots": sum(
                    _row_value(row, "provider_fast_break_shot_count", 0) or 0
                    for row in counter_rows
                ),
                "counter_definition": "possession_context_v1",
            },
            len(counter_rows),
        ),
        "counter_arrival": (
            _ratio(counter_arrivals, len(counter_rows)),
            {
                "counter_final_third_arrivals": counter_arrivals,
                "derived_counter_launches": len(counter_rows),
                "arrival_boundary": "final_third_x>=66.67",
            },
            len(counter_rows),
        ),
        "counter_speed": (
            _round(sum(counter_speeds) / len(counter_speeds), 3) if counter_speeds else None,
            {
                "counter_speed_observations": len(counter_speeds),
                "derived_counter_launches": len(counter_rows),
                "speed_values_mps": [_round(value, 3) for value in counter_speeds],
            },
            len(counter_speeds),
        ),
        "counter_shot_tendency": (
            _ratio(counter_shots, len(counter_rows)),
            {
                "counter_shots": counter_shots,
                "derived_counter_launches": len(counter_rows),
            },
            len(counter_rows),
        ),
    }
    for key in selected_keys:
        definition = AXIS_BY_KEY[key]
        value, raw, evidence_count = raw_definitions[key]
        axis_values[key] = _axis(
            definition,
            value=value,
            raw=raw,
            evidence_count=evidence_count,
            exposure_seconds=exposure_seconds,
            matches_excluded=matches_excluded,
            formula_version=formula_version,
        )

    return {
        "scope": dict(scope or {}),
        "formula_version": formula_version,
        "percentile_version": STYLE_PERCENTILE_VERSION,
        "exposure": {
            "seconds": exposure_seconds,
            "minutes": _round(exposure_seconds / 60, 2),
            "episode_count": episode_count,
            "match_count": match_count,
            "matches_excluded": matches_excluded,
        },
        "axes": axis_values,
        "evidence": {
            "event_count": len(event_rows),
            "pass_attempts": len(pass_rows),
            "located_pass_attempts": len(located_passes),
            "carry_attempts": carry_attempts,
            "shot_count": len(shots),
            "defensive_action_count": len(defensive_rows),
            "settled_block_count": len(settled_heights),
            "counter_launch_count": len(counter_rows),
            "source_event_limit": None,
            "truncated": False,
        },
        "reliability": {
            "state_exposure_verified": exposure_seconds > 0,
            "matches_excluded": matches_excluded,
            "sparse_axes": sorted(
                key for key, value in axis_values.items() if value["reliability"] == "sparse"
            ),
            "unavailable_axes": sorted(
                key for key, value in axis_values.items() if value["reliability"] == "unavailable"
            ),
        },
    }


def percentile_rank(value: float | None, values: Sequence[float | int | None]) -> float | None:
    """Return a deterministic mid-rank percentile in the inclusive 0..100 range."""

    if value is None:
        return None
    numeric = sorted(float(item) for item in values if item is not None)
    if not numeric:
        return None
    if len(numeric) == 1:
        return 50.0
    less = sum(item < value for item in numeric)
    equal = sum(item == value for item in numeric)
    rank = 100 * (less + equal / 2) / len(numeric)
    return _round(max(0.0, min(100.0, rank)), 2)


def _quantile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return _round(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def distribution(values: Sequence[float | int | None]) -> dict[str, Any]:
    numeric = sorted(float(item) for item in values if item is not None)
    return {
        "sample_size": len(numeric),
        "min": _round(numeric[0]) if numeric else None,
        "p10": _quantile(numeric, 0.10),
        "p25": _quantile(numeric, 0.25),
        "p50": _quantile(numeric, 0.50),
        "p75": _quantile(numeric, 0.75),
        "p90": _quantile(numeric, 0.90),
        "max": _round(numeric[-1]) if numeric else None,
        "iqr": _round((_quantile(numeric, 0.75) or 0) - (_quantile(numeric, 0.25) or 0)) if numeric else None,
        "values": [_round(item) for item in numeric],
    }


def attach_cohort_distributions(
    cohorts: Mapping[int, Mapping[str, Any]],
    *,
    target_team_id: int,
    axis_keys: Sequence[str] | None = None,
    team_names: Mapping[int, str] | None = None,
    comparison_available: bool = True,
) -> dict[str, Any]:
    """Attach same-season team distributions and prevalence percentiles.

    Percentiles only use axis observations that meet that axis's minimum
    evidence rule.  Sparse rows remain visible in ``members`` but cannot
    influence a team's percentile or signed shift.
    """

    selected_keys = tuple(axis_keys or DEFAULT_AXIS_KEYS)
    names = team_names or {}
    result: dict[str, Any] = {}
    for key in selected_keys:
        members = []
        values = []
        for team_id in sorted(cohorts):
            axis = cohorts[team_id].get("axes", {}).get(key)
            if axis is None:
                continue
            item = {
                "team_id": team_id,
                "team_name": names.get(team_id),
                "value": axis["value"],
                "reliability": axis["reliability"],
                "percentile_eligible": bool(axis["percentile_eligible"]),
            }
            members.append(item)
            if item["percentile_eligible"] and item["value"] is not None:
                values.append(item["value"])
        values_distribution = distribution(values)
        for member in members:
            axis = cohorts[member["team_id"]]["axes"][key]
            axis["percentile"] = (
                percentile_rank(member["value"], values)
                if comparison_available and member["percentile_eligible"]
                else None
            )
            if member["team_id"] == target_team_id:
                member["target"] = True
        result[key] = {
            "axis": key,
            "sample_size": values_distribution["sample_size"],
            "percentile_version": STYLE_PERCENTILE_VERSION,
            "higher_means": "prevalence",
            "distribution": values_distribution,
            "members": members,
        }
    return result


def signed_shift(
    selected: Mapping[str, Any],
    baseline: Mapping[str, Any] | None,
    distributions: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return raw and robustly normalised selected-minus-baseline evidence."""

    output: dict[str, Any] = {}
    distribution_rows = distributions or {}
    for key in selected.get("axes", {}):
        selected_axis = selected["axes"][key]
        baseline_axis = baseline.get("axes", {}).get(key) if baseline else None
        selected_value = selected_axis.get("value")
        baseline_value = baseline_axis.get("value") if baseline_axis else None
        delta = (
            _round(selected_value - baseline_value)
            if selected_value is not None and baseline_value is not None
            else None
        )
        scale = None
        normalised = None
        if delta is not None:
            row = distribution_rows.get(key, {})
            summary = row.get("distribution", {})
            p90, p10 = summary.get("p90"), summary.get("p10")
            if p90 is not None and p10 is not None and p90 > p10:
                scale = _round(p90 - p10)
                normalised = _round(max(-1.0, min(1.0, delta / scale)), 4)
        eligible = bool(
            baseline_axis
            and selected_axis.get("percentile_eligible")
            and baseline_axis.get("percentile_eligible")
            and delta is not None
            and normalised is not None
        )
        output[key] = {
            "selected_value": selected_value,
            "baseline_value": baseline_value,
            "raw_delta": delta,
            "unit": selected_axis.get("unit"),
            "normalised_delta": normalised if eligible else None,
            "normalized_delta": normalised if eligible else None,
            "normalisation": "raw_delta / same-axis cohort p90-minus-p10, clipped to [-1,1]",
            "normalization": "raw_delta / same-axis cohort p90-minus-p10, clipped to [-1,1]",
            "scale": scale,
            "direction": "prevalence",
            "eligible": eligible,
            "reliability": (
                "verified"
                if eligible
                else "sparse"
                if baseline_axis and (
                    selected_axis.get("reliability") == "sparse"
                    or baseline_axis.get("reliability") == "sparse"
                )
                else "unavailable"
            ),
        }
    return output


def add_prevalence_percentile(
    cohort: Mapping[str, Any],
    distribution_rows: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Compatibility helper for callers that add distributions after a build."""

    for key, axis in cohort.get("axes", {}).items():
        row = distribution_rows.get(key, {})
        values = row.get("distribution", {}).get("values", [])
        axis["percentile"] = (
            percentile_rank(axis.get("value"), values)
            if axis.get("percentile_eligible")
            else None
        )
    return cohort
