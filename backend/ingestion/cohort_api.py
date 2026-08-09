from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import F
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.derived_api import (
    _apply_filters as apply_outfield_filters,
    _base_queryset_for_seasons as outfield_scope_queryset,
    _meta_payload,
    _resolve_competition_scope,
)
from ingestion.derived_definitions import METRIC_FIELDS
from ingestion.gk_api import (
    _apply_filters as apply_gk_filters,
    _base_queryset_for_seasons as gk_scope_queryset,
    _gk_meta_payload,
)
from ingestion.gk_definitions import GK_METRIC_FIELDS, GK_METRICS_WITH_PERCENTILE
from ingestion.models import PlayerSeasonDerivedStats, PlayerSeasonGkDerivedStats
from ingestion.scope_percentiles import build_scope_percentiles, is_aggregate_scope, scope_context

MAX_COHORT_ROWS = 20_000
MAX_COHORT_METRICS = 40
MAX_COHORT_CELLS = 250_000


def requested_metrics(request, allowed: set[str]) -> list[str]:
    entries = request.query_params.getlist("metric")
    if len(entries) == 1 and "," in entries[0]:
        entries = entries[0].split(",")
    metrics = list(dict.fromkeys(entry.strip() for entry in entries if entry.strip()))
    if not metrics:
        raise DjangoValidationError("Provide at least one metric.")
    if len(metrics) > MAX_COHORT_METRICS:
        raise DjangoValidationError(f"No more than {MAX_COHORT_METRICS} metrics may be requested.")
    unknown = [metric for metric in metrics if metric not in allowed]
    if unknown:
        raise DjangoValidationError(f"Unsupported metrics: {', '.join(unknown)}.")
    return metrics


def projected_queryset(model, competition_seasons, metrics: list[str], percentile_fields: list[str]):
    fields = [
        "id",
        "canonical_player_id",
        "canonical_player__display_name",
        "canonical_display_team_id",
        "canonical_display_team__name",
        "competition_season_id",
        "competition_season__competition__short_code",
        "competition_season__season__label",
        "competition_season__competition__minimum_eligible_minutes",
        "minutes",
        "percentiles_eligible",
        "percentiles_ineligibility_reason",
        *metrics,
        *percentile_fields,
    ]
    if model is PlayerSeasonDerivedStats:
        fields.extend(
            [
                "position_group",
                "native_position",
                "scores_eligible",
                "scores_ineligibility_reason",
            ]
        )
    return (
        model.objects.filter(competition_season__in=competition_seasons, is_current=True)
        .select_related(
            "canonical_player",
            "canonical_display_team",
            "competition_season",
            "competition_season__competition",
            "competition_season__season",
        )
        .only(*fields)
    )


def row_payload(
    row,
    metrics: list[str],
    scope_percentiles: dict[int, dict] | None,
    *,
    is_gk: bool,
    include_percentiles: bool,
) -> dict:
    stored_percentiles = {}
    for metric in metrics:
        percentile_field = f"{metric}_percentile"
        stored_percentiles[metric] = (
            getattr(row, percentile_field, None) if hasattr(row, percentile_field) else None
        ) if include_percentiles else None
    position_group = "GK" if is_gk else row.position_group
    payload = {
        "canonical_player_id": row.canonical_player_id,
        "canonical_player_name": row.canonical_player.display_name,
        "canonical_team_id": row.canonical_display_team_id,
        "canonical_team_name": row.canonical_display_team.name if row.canonical_display_team else None,
        "secondary_teams": [],
        "competition_season": row.competition_season_id,
        "competition_code": row.competition_season.competition.short_code,
        "season_label": row.competition_season.season.label,
        "position_group": position_group,
        "native_position": "GK" if is_gk else row.native_position,
        "minutes": row.minutes,
        "formula_version": "projected",
        "derived_run_id": None,
        "eligibility": {
            "minimum_eligible_minutes": row.competition_season.minimum_eligible_minutes,
            "percentiles_eligible": row.percentiles_eligible,
            "percentiles_ineligibility_reason": row.percentiles_ineligibility_reason or None,
            "scores_eligible": False if is_gk else row.scores_eligible,
            "scores_ineligibility_reason": "goalkeeper_matrix" if is_gk else (row.scores_ineligibility_reason or None),
        },
        "metrics": {metric: getattr(row, metric) for metric in metrics},
        "percentiles": stored_percentiles,
        "scores": {},
        "score_raw": {},
    }
    if scope_percentiles is not None:
        payload["scope_percentiles"] = scope_percentiles.get(
            row.id,
            {metric: None for metric in metrics},
        )
    return payload


class PlayerSeasonCohortApi(APIView):
    """Width- and row-bounded player cohort projection for charts and analytical tools."""

    def get(self, request):
        try:
            payload = self.build_payload(request)
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)

    def build_payload(self, request) -> dict:
        competition_code, season_label, competition_seasons = _resolve_competition_scope(request)
        is_gk = request.query_params.get("kind") == "gk"
        include_percentiles = request.query_params.get("include_percentiles", "1") != "0"
        allowed = set(GK_METRIC_FIELDS if is_gk else METRIC_FIELDS)
        metrics = requested_metrics(request, allowed)
        percentile_metric_fields = [
            metric
            for metric in metrics
            if not is_gk or metric in GK_METRICS_WITH_PERCENTILE
        ]
        percentile_fields = (
            [f"{metric}_percentile" for metric in percentile_metric_fields]
            if include_percentiles
            else []
        )
        model = PlayerSeasonGkDerivedStats if is_gk else PlayerSeasonDerivedStats
        scope_queryset = projected_queryset(model, competition_seasons, metrics, percentile_fields)
        facets = list(
            scope_queryset.exclude(canonical_display_team__name__isnull=True)
            .order_by("canonical_display_team__name")
            .values_list("canonical_display_team__name", flat=True)
            .distinct()
        )
        queryset = scope_queryset
        queryset = apply_gk_filters(request, queryset) if is_gk else apply_outfield_filters(request, queryset)
        queryset = queryset.order_by(
            "canonical_player_id",
            F("minutes").desc(nulls_last=True),
            "competition_season_id",
            "id",
        )
        source_count = queryset.count()
        if source_count > MAX_COHORT_ROWS:
            raise DjangoValidationError(
                f"Cohort contains {source_count} rows; narrow it below {MAX_COHORT_ROWS}."
            )
        if source_count * len(metrics) > MAX_COHORT_CELLS:
            raise DjangoValidationError(
                f"Cohort projection contains {source_count * len(metrics)} metric cells; "
                f"narrow it below {MAX_COHORT_CELLS}."
            )
        rows_by_player = {}
        for row in queryset:
            rows_by_player.setdefault(row.canonical_player_id, row)
        rows = sorted(
            rows_by_player.values(),
            key=lambda row: (row.canonical_player.display_name.casefold(), row.competition_season_id, row.id),
        )
        count = len(rows)

        scope_percentile_payload = None
        if include_percentiles and is_aggregate_scope(competition_code):
            source_queryset = (
                gk_scope_queryset(competition_seasons)
                if is_gk
                else outfield_scope_queryset(competition_seasons)
            )
            scope_percentile_payload = build_scope_percentiles(
                scope_queryset=source_queryset,
                rows=rows,
                metric_fields=metrics,
                percentile_metric_fields=percentile_metric_fields,
            )

        payload = {
            "competition_season": competition_seasons[0].id if len(competition_seasons) == 1 else 0,
            "competition_code": competition_code,
            "season_label": season_label,
            "count": count,
            "facets": {"teams": facets},
            "results": [
                row_payload(
                    row,
                    metrics,
                    scope_percentile_payload,
                    is_gk=is_gk,
                    include_percentiles=include_percentiles,
                )
                for row in rows
            ],
            "meta": _gk_meta_payload(competition_seasons) if is_gk else _meta_payload(competition_seasons),
        }
        if scope_percentile_payload is not None:
            payload["scope_percentile_context"] = scope_context(
                competition_code,
                season_label,
                competition_seasons,
            )
        return payload
