"""Deterministic, state-conditioned defensive event territory evidence.

Locations are factual event positions in the normalized acting-team frame. They
must not be interpreted as pressing intensity or an organised block shape.
"""
from __future__ import annotations

from collections import Counter
from math import sqrt
from statistics import median
from typing import Iterable

from ingestion.models import MatchEventType, ProviderMatchEvent


DEFENSIVE_TERRITORY_VERSION = "defensive_territory_v2"
DEFENSIVE_GRID_COLUMNS = 12
DEFENSIVE_GRID_ROWS = 8
SPARSE_LOCATED_SAMPLE = 20

ALWAYS_DEFENSIVE_TYPES = frozenset(
    {
        MatchEventType.BALL_RECOVERY,
        MatchEventType.TACKLE,
        MatchEventType.INTERCEPTION,
        MatchEventType.BLOCKED_PASS,
        MatchEventType.CLEARANCE,
    }
)
QUALIFIED_DEFENSIVE_TYPES = frozenset(
    {MatchEventType.AERIAL, MatchEventType.CHALLENGE}
)

FAMILY_BY_TYPE = {
    MatchEventType.BALL_RECOVERY: "recovery",
    MatchEventType.TACKLE: "tackle",
    MatchEventType.INTERCEPTION: "interception",
    MatchEventType.BLOCKED_PASS: "blocked_pass",
    MatchEventType.AERIAL: "defensive_aerial",
    MatchEventType.CHALLENGE: "defensive_challenge",
    MatchEventType.CLEARANCE: "clearance",
}


def defensive_family(event: ProviderMatchEvent) -> str | None:
    if event.event_type in ALWAYS_DEFENSIVE_TYPES:
        return FAMILY_BY_TYPE[event.event_type]
    if event.event_type in QUALIFIED_DEFENSIVE_TYPES and event.is_defensive:
        return FAMILY_BY_TYPE[event.event_type]
    return None


def focal_defensive_location(event: ProviderMatchEvent) -> tuple[int | None, int | None]:
    """Return distance from the focal team's own goal in normalized units.

    WhoScored's normalized event frame is acting-team relative, so this is
    intentionally identical for a focal team playing home or away.
    """
    return event.x, event.y


def quantile(values: list[int], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def public_height(value: float | None) -> float | None:
    return round(value / 100, 2) if value is not None else None


def height_summary(values: list[int]) -> dict:
    if not values:
        return {
            "sample_size": 0,
            "median": None,
            "mean": None,
            "spread": {"p10": None, "p90": None, "p10_p90": None, "standard_deviation": None},
        }
    mean = sum(values) / len(values)
    p10, p90 = quantile(values, 0.1), quantile(values, 0.9)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return {
        "sample_size": len(values),
        "median": public_height(float(median(values))),
        "mean": public_height(mean),
        "spread": {
            "p10": public_height(p10),
            "p90": public_height(p90),
            "p10_p90": public_height(p90 - p10),
            "standard_deviation": public_height(sqrt(variance)),
        },
    }


def pitch_band(x: int) -> str:
    if x < 3333:
        return "defensive_third"
    if x < 6667:
        return "middle_third"
    return "attacking_third"


def distribution(values: list[int]) -> list[dict]:
    counts = Counter(pitch_band(value) for value in values)
    total = len(values)
    return [
        {"band": band, "count": counts[band], "share": round(counts[band] / total, 6) if total else 0.0}
        for band in ("defensive_third", "middle_third", "attacking_third")
    ]


def density_bins(rows: list[tuple[ProviderMatchEvent, str]], exposure_minutes: float) -> list[dict]:
    counts: Counter[tuple[int, int, str]] = Counter()
    totals: Counter[str] = Counter()
    for event, family in rows:
        x, y = focal_defensive_location(event)
        if x is None or y is None:
            continue
        column = min(DEFENSIVE_GRID_COLUMNS - 1, x * DEFENSIVE_GRID_COLUMNS // 10_001)
        row = min(DEFENSIVE_GRID_ROWS - 1, y * DEFENSIVE_GRID_ROWS // 10_001)
        group = "clearance" if family == "clearance" else "non_clearance"
        counts[(column, row, "all")] += 1
        counts[(column, row, group)] += 1
        counts[(column, row, family)] += 1
        totals["all"] += 1
        totals[group] += 1
        totals[family] += 1
    result = []
    for column in range(DEFENSIVE_GRID_COLUMNS):
        for row in range(DEFENSIVE_GRID_ROWS):
            item = {"column": column, "row": row}
            for group in ("all", "non_clearance", "clearance"):
                count = counts[(column, row, group)]
                item[group] = {
                    "count": count,
                    "share": round(count / totals[group], 6) if totals[group] else 0.0,
                    "per_state_minute": round(count / exposure_minutes, 6) if exposure_minutes else None,
                }
            item["families"] = {}
            for family in FAMILY_BY_TYPE.values():
                count = counts[(column, row, family)]
                item["families"][family] = {
                    "count": count,
                    "share": round(count / totals[family], 6) if totals[family] else 0.0,
                    "per_state_minute": round(count / exposure_minutes, 6) if exposure_minutes else None,
                }
            result.append(item)
    return result


def defensive_territory_payload(
    events: Iterable[ProviderMatchEvent],
    *,
    exposure_seconds: int,
    excluded_match_events: int = 0,
) -> dict:
    candidates = list(events)
    included: list[tuple[ProviderMatchEvent, str]] = []
    exclusions = Counter()
    for event in candidates:
        if event.is_deleted_event:
            exclusions["deleted_event"] += 1
            continue
        family = defensive_family(event)
        if family is None:
            if event.event_type in QUALIFIED_DEFENSIVE_TYPES:
                exclusions["attacking_or_unqualified_aerial_challenge"] += 1
            continue
        included.append((event, family))

    located = [(event, family) for event, family in included if None not in focal_defensive_location(event)]
    family_counts = Counter(family for _, family in included)
    family_located = Counter(family for _, family in located)
    all_x = [focal_defensive_location(event)[0] for event, _ in located]
    recovery_x = [focal_defensive_location(event)[0] for event, family in located if family == "recovery"]
    non_clearance_x = [focal_defensive_location(event)[0] for event, family in located if family != "clearance"]
    clearance_x = [focal_defensive_location(event)[0] for event, family in located if family == "clearance"]
    family_x = {
        family: [focal_defensive_location(event)[0] for event, row_family in located if row_family == family]
        for family in FAMILY_BY_TYPE.values()
    }
    exposure_minutes = exposure_seconds / 60

    def rate(count: int) -> float | None:
        return round(count / exposure_minutes, 4) if exposure_minutes else None

    return {
        "contract_version": DEFENSIVE_TERRITORY_VERSION,
        "orientation": {
            "frame": "focal_team_defending_perspective",
            "own_goal_x": 0,
            "opponent_goal_x": 100,
            "home_away_invariant": True,
        },
        "disclaimer": "Action height is observed event territory; it is not proof of pressing intensity or an organised high, mid, or low block.",
        "counts": {
            "included": len(included),
            "with_location": len(located),
            "without_location": len(included) - len(located),
            "non_clearance": sum(family != "clearance" for _, family in included),
            "clearance": family_counts["clearance"],
            "recovery": family_counts["recovery"],
        },
        "family_composition": [
            {
                "family": family,
                "count": family_counts[family],
                "with_location": family_located[family],
                "without_location": family_counts[family] - family_located[family],
                "share": round(family_counts[family] / len(included), 6) if included else 0.0,
            }
            for family in FAMILY_BY_TYPE.values()
        ],
        "family_evidence": {
            family: {
                "height": height_summary(family_x[family]),
                "rate_per_state_minute": rate(family_counts[family]),
            }
            for family in FAMILY_BY_TYPE.values()
        },
        "heights": {
            "recovery": height_summary(recovery_x),
            "non_clearance_action": height_summary(non_clearance_x),
            "clearance": height_summary(clearance_x),
            "all": height_summary(all_x),
        },
        "distribution": distribution(all_x),
        "rates_per_state_minute": {
            "all": rate(len(included)),
            "non_clearance": rate(sum(family != "clearance" for _, family in included)),
            "clearance": rate(family_counts["clearance"]),
            "recovery": rate(family_counts["recovery"]),
        },
        "grid": {
            "columns": DEFENSIVE_GRID_COLUMNS,
            "rows": DEFENSIVE_GRID_ROWS,
            "cells": density_bins(included, exposure_minutes),
        },
        "evidence": {
            "located_sample_size": len(located),
            "sparse": len(located) < SPARSE_LOCATED_SAMPLE,
            "sparse_threshold": SPARSE_LOCATED_SAMPLE,
            "exclusions": {
                **dict(sorted(exclusions.items())),
                "ineligible_match_events": excluded_match_events,
            },
        },
    }
