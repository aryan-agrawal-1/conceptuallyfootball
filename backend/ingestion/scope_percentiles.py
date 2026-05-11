from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.exceptions import FieldDoesNotExist
from django.db.models import QuerySet

from ingestion.api_cache import get_or_build_payload, joined_version, model_version, stable_cache_key
from ingestion.models import CompetitionSeason

BIG_FIVE_COMPETITION_CODES = ("ENG1", "GER1", "SPA1", "FRA1", "ITA1")
AGGREGATE_SCOPE_CODES = ("BIG5", "ALL")


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

    rows = CompetitionSeason.objects.select_related("competition", "season").filter(
        is_active=True,
        season__label__iexact=season_label,
    )
    if code == "BIG5":
        rows = rows.filter(competition__short_code__in=BIG_FIVE_COMPETITION_CODES)
    elif code == "ALL":
        pass
    else:
        rows = rows.filter(competition__short_code__iexact=code)

    seasons = list(rows.order_by("competition__short_code"))
    if not seasons:
        raise DjangoValidationError("Unknown percentile scope and season combination.")
    return seasons


def scope_context(scope_code: str, season_label: str, competition_seasons: Iterable[CompetitionSeason]) -> dict:
    seasons = list(competition_seasons)
    return {
        "competition_code": scope_code.strip().upper(),
        "season_label": season_label,
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
    row_ids = {row.id for row in row_list}
    relevant_positions = {getattr(row, "position_group", "GK") for row in row_list}

    if not row_list or not relevant_positions:
        return {}

    try:
        scope_queryset.model._meta.get_field("position_group")
        scope_queryset = scope_queryset.filter(position_group__in=relevant_positions)
    except FieldDoesNotExist:
        pass

    season_ids = list(scope_queryset.order_by("competition_season_id").values_list("competition_season_id", flat=True).distinct())
    cache_key = stable_cache_key(
        "scope-percentiles",
        {
            "model": scope_queryset.model._meta.label_lower,
            "competition_season_ids": season_ids,
            "fields": fields,
            "percentile_fields": sorted(fields_with_percentiles),
        },
    )
    source_version = joined_version(
        "scope-percentiles",
        scope_queryset.model._meta.label_lower,
        model_version(scope_queryset.model, {"is_current": True}),
    )
    cached_payload, _ = get_or_build_payload(
        cache_key=cache_key,
        source_version=source_version,
        builder=lambda: _build_all_scope_percentiles(
            scope_queryset=scope_queryset,
            fields=fields,
            fields_with_percentiles=fields_with_percentiles,
        ),
    )
    return {
        row_id: cached_payload.get(str(row_id), {field: None for field in fields})
        for row_id in row_ids
    }


def _build_all_scope_percentiles(
    *,
    scope_queryset: QuerySet,
    fields: list[str],
    fields_with_percentiles: set[str],
) -> dict[str, dict[str, float | None]]:
    scope_rows = list(scope_queryset)
    distributions: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in scope_rows:
        if not row.percentiles_eligible:
            continue
        for field in fields:
            if field not in fields_with_percentiles:
                continue
            value = getattr(row, field)
            if value is not None:
                distributions[(getattr(row, "position_group", "GK"), field)].append(float(value))

    out: dict[str, dict[str, float | None]] = {}
    for row in scope_rows:
        payload: dict[str, float | None] = {}
        for field in fields:
            payload[field] = None
            if field not in fields_with_percentiles or not row.percentiles_eligible:
                continue
            value = getattr(row, field)
            values = distributions.get((getattr(row, "position_group", "GK"), field)) or []
            if value is None or not values:
                continue
            payload[field] = percentile_rank(float(value), values)
        out[str(row.id)] = payload
    return out
