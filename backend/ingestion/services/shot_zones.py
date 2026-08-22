"""Goal-mouth zone aggregation for shooter and goalkeeper views.

The goal mouth spans ``y`` 44.62..55.38 in Opta pitch coordinates (7.32m wide
on a 68m pitch, centred at 50). Zones are three equal columns across the
mouth crossed with two height bands.

``GoalMouthZ`` runs 0..100 across roughly 6.8 metres of height, so the
crossbar (2.44m) sits near z=38 — empirically confirmed: no on-target shot in
the stored data exceeds z=36.7, while off-target shots that cleared the bar
range up to 100. The low band is therefore the bottom half of the goal
(z <= 19). Note WhoScored also emits a placeholder z of exactly 19.0 for a
small share of shots where no precise height was recorded.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ingestion.models import MatchEventShotOutcome, MatchEventShotSituation

GRID_COLUMNS = 3
GRID_ROWS = 2

# Pitch-coordinate extent of the goal mouth (7.32m / 68m centred on 50).
GOAL_Y_MIN = 50.0 - (7.32 / 68.0 / 2.0 * 100.0)
GOAL_Y_MAX = 50.0 + (7.32 / 68.0 / 2.0 * 100.0)

# Crossbar height on the GoalMouthZ scale.
GOAL_CROSSBAR_Z = 38.0

# Boundary between the low and high bands: the halfway height of the goal.
Z_LOW_MAX = GOAL_CROSSBAR_Z / 2.0

ON_TARGET_OUTCOMES = frozenset(
    {MatchEventShotOutcome.GOAL, MatchEventShotOutcome.SAVED}
)


@dataclass(frozen=True)
class ShotPlacement:
    outcome: int
    situation: int
    goal_mouth_y: float | None
    goal_mouth_z: float | None


def grid_metadata() -> dict:
    return {
        "columns": GRID_COLUMNS,
        "rows": GRID_ROWS,
        "y_min": round(GOAL_Y_MIN, 2),
        "y_max": round(GOAL_Y_MAX, 2),
        "z_low_max": Z_LOW_MAX,
    }


def placement_to_zone(y: float, z: float) -> tuple[int, int] | None:
    """Map a goal-mouth coordinate to ``(column, row)``, or None if outside."""
    if not GOAL_Y_MIN <= y <= GOAL_Y_MAX or not 0 <= z <= 100:
        return None
    span = GOAL_Y_MAX - GOAL_Y_MIN
    column = min(GRID_COLUMNS - 1, int((y - GOAL_Y_MIN) / span * GRID_COLUMNS))
    # Anything above the crossbar cannot be on target; bin it high rather
    # than dropping it so stray measurements stay visible.
    row = 1 if z > Z_LOW_MAX else 0
    return column, row


def empty_cells() -> dict[tuple[int, int], dict]:
    return {
        (column, row): {"shots": 0, "goals": 0, "saves": 0}
        for column in range(GRID_COLUMNS)
        for row in range(GRID_ROWS)
    }


def _is_penalty(placement: ShotPlacement) -> bool:
    return (
        placement.situation == MatchEventShotSituation.PENALTY
    )


def shooter_variant(placements: Sequence[ShotPlacement]) -> dict:
    """Aggregate shots for one filter variant (all vs penalties excluded)."""
    cells = empty_cells()
    totals = {
        "shots": 0,
        "goals": 0,
        "on_target": 0,
        "off_target": 0,
        "blocked": 0,
        "woodwork": 0,
        "unknown_target": 0,
    }
    for placement in placements:
        totals["shots"] += 1
        if placement.outcome == MatchEventShotOutcome.GOAL:
            totals["goals"] += 1
        if placement.outcome in ON_TARGET_OUTCOMES:
            totals["on_target"] += 1
        elif placement.outcome == MatchEventShotOutcome.BLOCKED:
            totals["blocked"] += 1
        elif placement.outcome == MatchEventShotOutcome.WOODWORK:
            totals["woodwork"] += 1
        else:
            totals["off_target"] += 1
        if placement.goal_mouth_y is None or placement.goal_mouth_z is None:
            if placement.outcome in ON_TARGET_OUTCOMES:
                totals["unknown_target"] += 1
            continue
        zone = placement_to_zone(placement.goal_mouth_y, placement.goal_mouth_z)
        if zone is None:
            if placement.outcome in ON_TARGET_OUTCOMES:
                totals["unknown_target"] += 1
            continue
        if placement.outcome not in ON_TARGET_OUTCOMES:
            continue
        cell = cells[zone]
        cell["shots"] += 1
        if placement.outcome == MatchEventShotOutcome.GOAL:
            cell["goals"] += 1
        else:
            cell["saves"] += 1
    return _variant_payload(cells, totals)


def keeper_variant(placements: Sequence[ShotPlacement]) -> dict:
    """Aggregate shots faced (goals + saves only) for one filter variant."""
    cells = empty_cells()
    totals = {"shots_faced": 0, "saves": 0, "goals_conceded": 0, "unknown_target": 0}
    for placement in placements:
        if placement.outcome not in ON_TARGET_OUTCOMES:
            continue
        totals["shots_faced"] += 1
        if placement.goal_mouth_y is None or placement.goal_mouth_z is None:
            totals["unknown_target"] += 1
            continue
        zone = placement_to_zone(placement.goal_mouth_y, placement.goal_mouth_z)
        if zone is None:
            totals["unknown_target"] += 1
            continue
        cell = cells[zone]
        cell["shots"] += 1
        if placement.outcome == MatchEventShotOutcome.GOAL:
            cell["goals"] += 1
            totals["goals_conceded"] += 1
        else:
            cell["saves"] += 1
            totals["saves"] += 1
    return _variant_payload(cells, totals, rate_key="save_rate")


def _variant_payload(
    cells: dict[tuple[int, int], dict],
    totals: dict,
    *,
    rate_key: str = "conversion",
) -> dict:
    """Build the payload for one variant.

    ``conversion`` is goals / on-target shots per cell; ``save_rate`` is
    saves / shots faced per cell. Both denominators are the cell's shot count.
    """
    numerator_key = "saves" if rate_key == "save_rate" else "goals"
    cell_rows = []
    for (column, row), value in sorted(cells.items()):
        cell_rows.append({
            "column": column,
            "row": row,
            "shots": value["shots"],
            "goals": value["goals"],
            rate_key: (
                round(value[numerator_key] / value["shots"], 4)
                if value["shots"]
                else None
            ),
        })
    faced = totals.get("shots_faced", totals.get("on_target", 0))
    overall_numerator = totals.get("saves", 0) if rate_key == "save_rate" else totals.get("goals", 0)
    overall = round(overall_numerator / faced, 4) if faced else None
    return {"cells": cell_rows, "totals": {**totals, rate_key: overall}}


def split_variants(
    placements: Iterable[ShotPlacement],
    aggregator,
) -> dict[str, dict]:
    values = list(placements)
    open_play = [
        placement for placement in values if not _is_penalty(placement)
    ]
    penalties_only = [
        placement for placement in values if _is_penalty(placement)
    ]
    return {
        "all": aggregator(values),
        "open_play": aggregator(open_play),
        "penalties_only": aggregator(penalties_only),
    }
