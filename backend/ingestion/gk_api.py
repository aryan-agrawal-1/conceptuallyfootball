from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.derived_definitions import MIN_ELIGIBLE_MINUTES
from ingestion.gk_definitions import (
    FORMULA_VERSION_GK,
    GK_METRIC_DEFINITIONS,
    GK_METRIC_FIELDS,
    GK_METRIC_GROUPS,
    GK_METRICS_WITH_PERCENTILE,
    LIST_SORT_FIELDS_GK,
)
from ingestion.derived_api import _resolve_competition_scope
from ingestion.models import CompetitionSeason, PlayerSeasonGkDerivedStats
from ingestion.secondary_teams import secondary_teams_payload
from ingestion.scope_percentiles import (
    build_scope_percentiles,
    is_aggregate_scope,
    requested_include,
    resolve_scope_seasons,
    scope_context,
)


def _requested_meta(request) -> bool:
    return requested_include(request, "meta")


def _requested_scope_percentiles(request) -> bool:
    return requested_include(request, "scope_percentiles")


def _gk_meta_payload() -> dict:
    return {
        "formula_version": FORMULA_VERSION_GK,
        "minimum_eligible_minutes": MIN_ELIGIBLE_MINUTES,
        "metric_groups": GK_METRIC_GROUPS,
        "metrics": GK_METRIC_DEFINITIONS,
    }


def _resolve_competition_season(request) -> CompetitionSeason:
    competition_season_id = request.query_params.get("competition_season")
    if competition_season_id:
        try:
            return CompetitionSeason.objects.select_related("competition", "season").get(
                pk=int(competition_season_id)
            )
        except (CompetitionSeason.DoesNotExist, ValueError) as exc:
            raise DjangoValidationError("Unknown competition_season.") from exc

    competition_code = request.query_params.get("competition")
    season_label = request.query_params.get("season")
    if not competition_code or not season_label:
        raise DjangoValidationError(
            "Provide either competition_season or both competition and season."
        )
    try:
        return CompetitionSeason.objects.select_related("competition", "season").get(
            competition__short_code__iexact=competition_code,
            season__label__iexact=season_label,
        )
    except CompetitionSeason.DoesNotExist as exc:
        raise DjangoValidationError("Unknown competition and season combination.") from exc


def _base_queryset(competition_season: CompetitionSeason) -> QuerySet[PlayerSeasonGkDerivedStats]:
    return _base_queryset_for_seasons([competition_season])


def _base_queryset_for_seasons(competition_seasons: list[CompetitionSeason]) -> QuerySet[PlayerSeasonGkDerivedStats]:
    return (
        PlayerSeasonGkDerivedStats.objects.filter(
            competition_season__in=competition_seasons,
            is_current=True,
        )
        .select_related(
            "canonical_player",
            "canonical_display_team",
            "competition_season",
            "competition_season__competition",
            "competition_season__season",
            "derived_ingestion_run",
            "merged_player_season",
        )
    )


def _apply_filters(request, queryset: QuerySet[PlayerSeasonGkDerivedStats]) -> QuerySet[PlayerSeasonGkDerivedStats]:
    team = request.query_params.get("team")
    if team:
        queryset = queryset.filter(canonical_display_team_id=team)

    min_minutes = request.query_params.get("min_minutes")
    if min_minutes:
        try:
            queryset = queryset.filter(minutes__gte=int(min_minutes))
        except ValueError as exc:
            raise DjangoValidationError("min_minutes must be an integer.") from exc
    return queryset


def _apply_sorting(request, queryset: QuerySet[PlayerSeasonGkDerivedStats]) -> QuerySet[PlayerSeasonGkDerivedStats]:
    sort = request.query_params.get("sort", "canonical_player_name")
    descending = sort.startswith("-")
    key = sort[1:] if descending else sort
    field_name = LIST_SORT_FIELDS_GK.get(key)
    if not field_name:
        raise DjangoValidationError(f"Unsupported sort field '{sort}'.")
    order_by = f"-{field_name}" if descending else field_name
    if field_name != "canonical_player__display_name":
        queryset = queryset.order_by(order_by, "canonical_player__display_name")
    else:
        queryset = queryset.order_by(order_by)
    return queryset


def _row_payload(row: PlayerSeasonGkDerivedStats) -> dict:
    metrics = {metric: getattr(row, metric) for metric in GK_METRIC_FIELDS}
    percentiles = {}
    for metric in GK_METRIC_FIELDS:
        if metric == "appearances":
            percentiles[metric] = None
        else:
            percentiles[metric] = getattr(row, f"{metric}_percentile")
    return {
        "canonical_player_id": row.canonical_player_id,
        "canonical_player_name": row.canonical_player.display_name,
        "canonical_team_id": row.canonical_display_team_id,
        "canonical_team_name": row.canonical_display_team.name if row.canonical_display_team else None,
        "secondary_teams": secondary_teams_payload(row.merged_player_season),
        "competition_season": row.competition_season_id,
        "competition_code": row.competition_season.competition.short_code,
        "season_label": row.competition_season.season.label,
        "position_group": "GK",
        "native_position": "GK",
        "minutes": row.minutes,
        "appearances": row.appearances,
        "formula_version": row.formula_version,
        "derived_run_id": row.derived_ingestion_run_id,
        "eligibility": {
            "percentiles_eligible": row.percentiles_eligible,
            "percentiles_ineligibility_reason": row.percentiles_ineligibility_reason or None,
            "scores_eligible": False,
            "scores_ineligibility_reason": "goalkeeper_matrix",
        },
        "metrics": metrics,
        "percentiles": percentiles,
        "scores": {},
        "score_raw": {},
    }


def _attach_scope_percentiles(payload: dict, row: PlayerSeasonGkDerivedStats, scope_payload: dict[int, dict]) -> None:
    payload["scope_percentiles"] = scope_payload.get(row.id, {metric: None for metric in GK_METRIC_FIELDS})


class GkDerivedPlayerSeasonListApi(APIView):
    def get(self, request):
        try:
            competition_code, season_label, competition_seasons = _resolve_competition_scope(request)
            queryset = _base_queryset_for_seasons(competition_seasons)
            queryset = _apply_filters(request, queryset)
            queryset = _apply_sorting(request, queryset)
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        rows = list(queryset)
        scope_percentiles = None
        if _requested_scope_percentiles(request):
            scope_code = request.query_params.get("percentile_scope") or competition_code
            try:
                scope_seasons = resolve_scope_seasons(scope_code, season_label)
            except DjangoValidationError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            scope_percentiles = build_scope_percentiles(
                scope_queryset=_base_queryset_for_seasons(scope_seasons),
                rows=rows,
                metric_fields=GK_METRIC_FIELDS,
                percentile_metric_fields=GK_METRICS_WITH_PERCENTILE,
            )

        payload = {
            "competition_season": competition_seasons[0].id if len(competition_seasons) == 1 else 0,
            "competition_code": competition_code,
            "season_label": season_label,
            "matrix_kind": "gk",
            "count": len(rows),
            "results": [],
        }
        for row in rows:
            row_payload = _row_payload(row)
            if scope_percentiles is not None:
                _attach_scope_percentiles(row_payload, row, scope_percentiles)
            payload["results"].append(row_payload)
        if scope_percentiles is not None:
            payload["scope_percentile_context"] = scope_context(scope_code, season_label, scope_seasons)
        if _requested_meta(request):
            payload["meta"] = _gk_meta_payload()
        return Response(payload)


class GkDerivedPlayerSeasonDetailApi(APIView):
    def get(self, request, canonical_player_id: int):
        try:
            competition_season = _resolve_competition_season(request)
            queryset = _base_queryset(competition_season)
            row = queryset.get(canonical_player_id=canonical_player_id)
            scope_percentiles = None
            if _requested_scope_percentiles(request):
                scope_code = request.query_params.get("percentile_scope") or (
                    request.query_params.get("competition") if is_aggregate_scope(request.query_params.get("competition")) else None
                )
                if not scope_code:
                    raise DjangoValidationError("Provide percentile_scope for scope percentiles.")
                scope_seasons = resolve_scope_seasons(scope_code, competition_season.season.label)
                scope_percentiles = build_scope_percentiles(
                    scope_queryset=_base_queryset_for_seasons(scope_seasons),
                    rows=[row],
                    metric_fields=GK_METRIC_FIELDS,
                    percentile_metric_fields=GK_METRICS_WITH_PERCENTILE,
                )
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PlayerSeasonGkDerivedStats.DoesNotExist:
            return Response({"detail": "GK derived player-season not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = _row_payload(row)
        if scope_percentiles is not None:
            _attach_scope_percentiles(payload, row, scope_percentiles)
            payload["scope_percentile_context"] = scope_context(scope_code, competition_season.season.label, scope_seasons)
        if _requested_meta(request):
            payload["meta"] = _gk_meta_payload()
        return Response(payload)
