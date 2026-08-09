from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from typing import Iterable

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.exceptions import FieldDoesNotExist
from django.db.models import QuerySet

from ingestion.competition_scope import (
    AGGREGATE_SCOPE_CODES,
    resolve_public_scope,
)
from ingestion.models import CompetitionSeason
from ingestion.services.season_labels import aggregate_season_label

SCOPE_PERCENTILES_CACHE_VERSION = "v2"


def requested_include(request, key: str) -> bool:
    include = request.query_params.get("include", "")
    return key in {part.strip() for part in include.split(",") if part.strip()}


def is_aggregate_scope(scope_code: str | None) -> bool:
    return (scope_code or "").strip().upper() in AGGREGATE_SCOPE_CODES


def percentile_rank(value: float, values: list[float]) -> float:
    if not values:
        raise ValueError("Cannot compute percentile on empty values.")
    less = sum(1 for other in values if other < value)
    less_or_equal = sum(1 for other in values if other <= value)
    return ((less + less_or_equal) / 2.0) / len(values) * 100.0


def resolve_scope_seasons(scope_code: str, season_label: str) -> list[CompetitionSeason]:
    code = scope_code.strip().upper()
    if not code or not season_label:
        raise DjangoValidationError("Provide percentile_scope and season for scope percentiles.")

    try:
        return resolve_public_scope(code, season_label)
    except DjangoValidationError as exc:
        raise DjangoValidationError("Unknown percentile scope and season combination.") from exc


def scope_context(scope_code: str, season_label: str, competition_seasons: Iterable[CompetitionSeason]) -> dict:
    seasons = list(competition_seasons)
    code = scope_code.strip().upper()
    return {
        "competition_code": code,
        "season_label": aggregate_season_label(season_label) if is_aggregate_scope(code) else season_label,
        "competition_season_ids": [cs.id for cs in seasons],
    }


def build_scope_percentiles(
    *,
    scope_queryset: QuerySet,
    rows: Iterable,
    metric_fields: Iterable[str],
    percentile_metric_fields: Iterable[str] | None = None,
) -> dict[int, dict[str, float | None]]:
    fields = list(metric_fields)
    fields_with_percentiles = set(percentile_metric_fields or fields)
    row_list = list(rows)
    relevant_positions = {getattr(row, "position_group", "GK") for row in row_list}

    if not row_list or not relevant_positions:
        return {}

    has_position_group = True
    try:
        scope_queryset.model._meta.get_field("position_group")
        scope_queryset = scope_queryset.filter(position_group__in=relevant_positions)
    except FieldDoesNotExist:
        has_position_group = False

    return _build_selected_scope_percentiles(
        scope_queryset=scope_queryset,
        rows=row_list,
        fields=fields,
        fields_with_percentiles=fields_with_percentiles,
        has_position_group=has_position_group,
    )


def build_rate_adjusted_scope_percentiles(
    *,
    scope_queryset: QuerySet,
    rows: Iterable,
    metric_fields: Iterable[str],
    rate_mode: str,
    integer_fields: Iterable[str] = (),
) -> dict[int, dict[str, float | None]]:
    """Rank matrix-only values whose displayed rate is derived from minutes."""
    fields = list(metric_fields)
    integer_field_set = set(integer_fields)
    row_list = list(rows)
    relevant_positions = {getattr(row, "position_group", "GK") for row in row_list}
    if not row_list or not fields or not relevant_positions:
        return {}

    has_position_group = True
    try:
        scope_queryset.model._meta.get_field("position_group")
        scope_queryset = scope_queryset.filter(position_group__in=relevant_positions)
    except FieldDoesNotExist:
        has_position_group = False

    value_fields = ["percentiles_eligible", "minutes", *fields]
    if has_position_group:
        value_fields.append("position_group")
    value_fields = list(dict.fromkeys(value_fields))

    def adjusted_value(source, field: str) -> float | None:
        value = source.get(field) if isinstance(source, dict) else getattr(source, field)
        minutes = source.get("minutes") if isinstance(source, dict) else getattr(source, "minutes")
        if value is None or minutes is None or minutes <= 0:
            return None
        if rate_mode == "per90":
            adjusted = float(value) * 90.0 / float(minutes)
        else:
            adjusted = float(value) * float(minutes) / 90.0
        return float(round(adjusted)) if field in integer_field_set else adjusted

    distributions: dict[tuple[str, str], list[float]] = defaultdict(list)
    for scope_row in scope_queryset.values(*value_fields).iterator(chunk_size=2000):
        if not scope_row["percentiles_eligible"]:
            continue
        position_group = scope_row.get("position_group", "GK")
        for field in fields:
            value = adjusted_value(scope_row, field)
            if value is not None:
                distributions[(position_group, field)].append(value)
    for values in distributions.values():
        values.sort()

    out: dict[int, dict[str, float | None]] = {}
    for row in row_list:
        position_group = getattr(row, "position_group", "GK")
        eligible = getattr(row, "percentiles_eligible", False)
        payload: dict[str, float | None] = {}
        for field in fields:
            payload[field] = None
            value = adjusted_value(row, field)
            values = distributions.get((position_group, field)) or []
            if not eligible or value is None or not values:
                continue
            less = bisect_left(values, value)
            less_or_equal = bisect_right(values, value)
            payload[field] = ((less + less_or_equal) / 2.0) / len(values) * 100.0
        out[row.id] = payload
    return out


def _build_selected_scope_percentiles(
    *,
    scope_queryset: QuerySet,
    rows: list,
    fields: list[str],
    fields_with_percentiles: set[str],
    has_position_group: bool,
) -> dict[int, dict[str, float | None]]:
    base_fields = ["id", "percentiles_eligible"]
    if has_position_group:
        base_fields.append("position_group")
    value_fields = list(dict.fromkeys([*base_fields, *fields]))
    distributions: dict[tuple[str, str], list[float]] = defaultdict(list)
    for scope_row in scope_queryset.values(*value_fields).iterator(chunk_size=2000):
        if not scope_row["percentiles_eligible"]:
            continue
        position_group = scope_row.get("position_group", "GK")
        for field in fields:
            if field not in fields_with_percentiles:
                continue
            value = scope_row.get(field)
            if value is not None:
                distributions[(position_group, field)].append(float(value))

    for values in distributions.values():
        values.sort()

    out: dict[int, dict[str, float | None]] = {}
    for row in rows:
        payload: dict[str, float | None] = {}
        position_group = getattr(row, "position_group", "GK")
        eligible = getattr(row, "percentiles_eligible", False)
        for field in fields:
            payload[field] = None
            if field not in fields_with_percentiles or not eligible:
                continue
            value = getattr(row, field)
            values = distributions.get((position_group, field)) or []
            if value is None or not values:
                continue
            numeric = float(value)
            less = bisect_left(values, numeric)
            less_or_equal = bisect_right(values, numeric)
            payload[field] = ((less + less_or_equal) / 2.0) / len(values) * 100.0
        out[row.id] = payload
    return out
