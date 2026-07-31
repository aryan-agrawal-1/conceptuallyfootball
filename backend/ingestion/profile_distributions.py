from __future__ import annotations

from collections import defaultdict
from math import floor
from typing import Iterable

from django.core.exceptions import FieldDoesNotExist
from django.db.models import QuerySet


PROFILE_DISTRIBUTION_CACHE_VERSION = "v1"
PROFILE_DISTRIBUTION_BIN_COUNT = 16


def quantile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        raise ValueError("Cannot compute a quantile on an empty distribution.")
    if len(sorted_values) == 1:
        return sorted_values[0]

    index = (len(sorted_values) - 1) * fraction
    lower_index = floor(index)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    weight = index - lower_index
    return sorted_values[lower_index] * (1.0 - weight) + sorted_values[upper_index] * weight


def distribution_bins(
    sorted_values: list[float],
    *,
    bin_count: int = PROFILE_DISTRIBUTION_BIN_COUNT,
) -> list[dict[str, float | int]]:
    if not sorted_values:
        return []

    minimum = sorted_values[0]
    maximum = sorted_values[-1]
    if minimum == maximum:
        return [{"start": minimum, "end": maximum, "count": len(sorted_values)}]

    bounded_bin_count = max(1, min(bin_count, len(sorted_values)))
    width = (maximum - minimum) / bounded_bin_count
    counts = [0] * bounded_bin_count
    for value in sorted_values:
        index = min(int((value - minimum) / width), bounded_bin_count - 1)
        counts[index] += 1

    return [
        {
            "start": minimum + width * index,
            "end": maximum if index == bounded_bin_count - 1 else minimum + width * (index + 1),
            "count": count,
        }
        for index, count in enumerate(counts)
    ]


def distribution_summary(
    values: list[float],
    *,
    bin_count: int = PROFILE_DISTRIBUTION_BIN_COUNT,
) -> dict | None:
    sorted_values = sorted(values)
    if not sorted_values:
        return None
    return {
        "count": len(sorted_values),
        "min": sorted_values[0],
        "max": sorted_values[-1],
        "p25": quantile(sorted_values, 0.25),
        "median": quantile(sorted_values, 0.5),
        "p75": quantile(sorted_values, 0.75),
        "bins": distribution_bins(sorted_values, bin_count=bin_count),
    }


def build_profile_distributions(
    *,
    scope_queryset: QuerySet,
    row,
    metric_fields: Iterable[str],
    percentile_metric_fields: Iterable[str] | None = None,
    bin_count: int = PROFILE_DISTRIBUTION_BIN_COUNT,
) -> dict:
    fields = list(dict.fromkeys(metric_fields))
    fields_with_percentiles = set(percentile_metric_fields or fields)
    position_group = getattr(row, "position_group", "GK")

    has_position_group = True
    try:
        scope_queryset.model._meta.get_field("position_group")
        scope_queryset = scope_queryset.filter(position_group=position_group)
    except FieldDoesNotExist:
        has_position_group = False

    values_by_metric: dict[str, list[float]] = defaultdict(list)
    season_values_by_metric: dict[str, list[float]] = defaultdict(list)
    value_fields = ["percentiles_eligible", "minutes", *fields]
    if has_position_group:
        value_fields.append("position_group")

    cohort_count = 0
    for scope_row in scope_queryset.values(*dict.fromkeys(value_fields)).iterator(chunk_size=2000):
        if not scope_row["percentiles_eligible"]:
            continue
        cohort_count += 1
        for metric in fields:
            if metric not in fields_with_percentiles:
                continue
            value = scope_row.get(metric)
            if value is not None:
                numeric_value = float(value)
                values_by_metric[metric].append(numeric_value)
                minutes = scope_row.get("minutes")
                if metric.endswith("_per_90") and minutes is not None and minutes > 0:
                    season_values_by_metric[metric].append(numeric_value * float(minutes) / 90.0)

    metrics: dict[str, dict] = {}
    for metric in fields:
        summary = distribution_summary(values_by_metric.get(metric) or [], bin_count=bin_count)
        if summary is None:
            continue
        season_summary = distribution_summary(
            season_values_by_metric.get(metric) or [],
            bin_count=bin_count,
        )
        metrics[metric] = {
            **summary,
            **({"season_approx": season_summary} if season_summary is not None else {}),
        }

    return {
        "position_group": position_group,
        "cohort_count": cohort_count,
        "bin_limit": max(1, bin_count),
        "metrics": metrics,
    }
