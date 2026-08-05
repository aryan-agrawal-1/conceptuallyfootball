from __future__ import annotations

from types import SimpleNamespace

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.api_cache import (
    canonical_query_params,
    get_or_build_payload,
    get_or_build_payload_response,
    joined_version,
    model_version,
    stable_cache_key,
)
from ingestion.competition_scope import (
    eligibility_thresholds,
    public_competition_seasons,
    resolve_public_competition_season,
    scope_minimum_eligible_minutes,
)
from ingestion.derived_definitions import METRIC_META_CACHE_VERSION
from ingestion.gk_definitions import (
    FORMULA_VERSION_GK,
    GK_METRIC_DEFINITIONS,
    GK_METRIC_FIELDS,
    GK_METRIC_GROUPS,
    GK_METRICS_WITH_PERCENTILE,
    LIST_SORT_FIELDS_GK,
)
from ingestion.derived_api import _resolve_competition_scope
from ingestion.models import CanonicalTeam, CompetitionSeason, PlayerSeasonGkDerivedStats
from ingestion.profile_modes import (
    available_profile_modes,
    comparison_source_code,
    comparison_scope_options,
    profile_component_seasons,
    requested_profile_mode,
    resolved_comparison_scope,
    resolved_profile_mode,
)
from ingestion.profile_distributions import (
    PROFILE_DISTRIBUTION_CACHE_VERSION,
    build_profile_distributions,
)
from ingestion.secondary_teams import secondary_teams_payload
from ingestion.scope_percentiles import (
    SCOPE_PERCENTILES_CACHE_VERSION,
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


def _requested_profile_distributions(request) -> bool:
    return requested_include(request, "profile_distributions")


def _gk_meta_payload(competition_seasons: list[CompetitionSeason]) -> dict:
    return {
        "formula_version": FORMULA_VERSION_GK,
        "minimum_eligible_minutes": scope_minimum_eligible_minutes(competition_seasons),
        "eligibility_thresholds": eligibility_thresholds(competition_seasons),
        "metric_groups": GK_METRIC_GROUPS,
        "metrics": GK_METRIC_DEFINITIONS,
    }


def _resolve_competition_season(request) -> CompetitionSeason:
    competition_season_id = request.query_params.get("competition_season")
    if competition_season_id:
        try:
            return public_competition_seasons().select_related("competition", "season").get(
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
    return resolve_public_competition_season(competition_code, season_label)


def _base_queryset(competition_season: CompetitionSeason) -> QuerySet[PlayerSeasonGkDerivedStats]:
    return _base_queryset_for_seasons([competition_season])


def _base_queryset_for_seasons(competition_seasons: list[CompetitionSeason]) -> QuerySet[PlayerSeasonGkDerivedStats]:
    metric_value_fields = []
    for metric in GK_METRIC_FIELDS:
        metric_value_fields.append(metric)
        if metric != "appearances":
            metric_value_fields.append(f"{metric}_percentile")
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
            "merged_player_season",
        )
        .only(
            "id",
            "canonical_player_id",
            "canonical_player__display_name",
            "canonical_display_team_id",
            "canonical_display_team__name",
            "merged_player_season_id",
            "merged_player_season__secondary_display_team_ids",
            "competition_season_id",
            "competition_season__competition__short_code",
            "competition_season__season__label",
            "minutes",
            "appearances",
            "formula_version",
            "derived_ingestion_run_id",
            "percentiles_eligible",
            "percentiles_ineligibility_reason",
            *metric_value_fields,
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


def _secondary_team_names_for_rows(rows: list[PlayerSeasonGkDerivedStats]) -> dict[int, str]:
    team_ids: set[int] = set()
    for row in rows:
        merged = row.merged_player_season
        if merged and merged.secondary_display_team_ids:
            team_ids.update(int(pk) for pk in merged.secondary_display_team_ids)
    if not team_ids:
        return {}
    return dict(CanonicalTeam.objects.filter(pk__in=team_ids).values_list("pk", "name"))


def _row_payload(row: PlayerSeasonGkDerivedStats, secondary_team_names: dict[int, str] | None = None) -> dict:
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
        "secondary_teams": secondary_teams_payload(row.merged_player_season, secondary_team_names),
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
            "minimum_eligible_minutes": row.competition_season.minimum_eligible_minutes,
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


def _gk_component_payload(row: PlayerSeasonGkDerivedStats, secondary_names: dict[int, str]) -> dict:
    return {
        "competition_season": row.competition_season_id,
        "competition_code": row.competition_season.competition.short_code,
        "competition_type": row.competition_season.competition.competition_type,
        "season_label": row.competition_season.season.label,
        "canonical_team_id": row.canonical_display_team_id,
        "canonical_team_name": row.canonical_display_team.name if row.canonical_display_team else None,
        "secondary_teams": secondary_teams_payload(row.merged_player_season, secondary_names),
        "minutes": row.minutes,
        "metrics": {metric: getattr(row, metric) for metric in GK_METRIC_FIELDS},
    }


def _gk_per_90_total(rows: list[PlayerSeasonGkDerivedStats], metric: str) -> float | None:
    values = [(getattr(row, metric), row.minutes) for row in rows]
    if any(value is None or minutes is None for value, minutes in values):
        return None
    return sum(float(value) * float(minutes) / 90.0 for value, minutes in values)


def _aggregate_gk_metrics(rows: list[PlayerSeasonGkDerivedStats]) -> tuple[int | None, dict]:
    minutes = sum(row.minutes for row in rows) if all(row.minutes is not None for row in rows) else None
    metrics: dict[str, float | int | None] = {}
    for metric, definition in GK_METRIC_DEFINITIONS.items():
        values = [getattr(row, metric) for row in rows]
        if definition["unit"] == "total":
            metrics[metric] = None if any(value is None for value in values) else sum(values)
        elif definition["unit"] == "per90":
            total = _gk_per_90_total(rows, metric)
            metrics[metric] = (
                None
                if total is None or minutes is None or minutes <= 0
                else total * 90.0 / float(minutes)
            )
        else:
            metrics[metric] = None

    appearances = metrics["appearances"]
    clean_sheets = metrics["clean_sheets"]
    metrics["clean_sheet_rate"] = (
        None
        if appearances is None or clean_sheets is None or appearances <= 0
        else float(clean_sheets) * 100.0 / float(appearances)
    )
    completed_passes = _gk_per_90_total(rows, "completed_passes_per_90")
    total_passes = 0.0
    for row in rows:
        component_completed = _gk_per_90_total([row], "completed_passes_per_90")
        if component_completed is None or row.pass_accuracy is None or row.pass_accuracy <= 0:
            total_passes = -1.0
            break
        total_passes += component_completed / (float(row.pass_accuracy) / 100.0)
    metrics["pass_accuracy"] = (
        None
        if completed_passes is None or total_passes <= 0
        else completed_passes * 100.0 / total_passes
    )
    return minutes, metrics


def _attach_gk_comparison_context(
    request,
    *,
    payload: dict,
    selected_season: CompetitionSeason,
    canonical_player_id: int,
    mode: str,
) -> None:
    available, source_code = comparison_scope_options(
        selected=selected_season,
        canonical_player_id=canonical_player_id,
        row_model=PlayerSeasonGkDerivedStats,
    )
    comparison_scope = resolved_comparison_scope(
        request.query_params.get("comparison_scope"),
        available,
    )
    payload["comparison_available_scopes"] = available
    payload["comparison_scope"] = comparison_scope
    payload["comparison_source_competition"] = comparison_source_code(
        selected=selected_season,
        canonical_player_id=canonical_player_id,
        row_model=PlayerSeasonGkDerivedStats,
        comparison_scope=comparison_scope,
        default_code=source_code,
    )
    if comparison_scope is None:
        payload["comparison_percentiles"] = {metric: None for metric in GK_METRIC_FIELDS}
        payload["comparison_eligibility"] = {
            "minimum_eligible_minutes": None,
            "percentiles_eligible": False,
            "percentiles_ineligibility_reason": "comparison_cohort_unavailable",
            "scores_eligible": False,
            "scores_ineligibility_reason": "goalkeeper_matrix",
        }
        return

    scope_seasons = resolve_scope_seasons(comparison_scope, selected_season.season.label)
    minimum = scope_minimum_eligible_minutes(scope_seasons)
    eligible = mode != "combined" and bool(payload.get("minutes")) and payload["minutes"] >= minimum
    reason = None if eligible else ("combined_profile_mode" if mode == "combined" else "below_minutes_threshold")
    proxy = SimpleNamespace(
        id=-canonical_player_id,
        percentiles_eligible=eligible,
        **payload["metrics"],
    )
    scope_queryset = _base_queryset_for_seasons(scope_seasons)
    percentiles = build_scope_percentiles(
        scope_queryset=scope_queryset,
        rows=[proxy],
        metric_fields=GK_METRIC_FIELDS,
        percentile_metric_fields=GK_METRICS_WITH_PERCENTILE,
    )
    payload["comparison_percentiles"] = percentiles[proxy.id]
    payload["comparison_eligibility"] = {
        "minimum_eligible_minutes": minimum,
        "percentiles_eligible": eligible,
        "percentiles_ineligibility_reason": reason,
        "scores_eligible": False,
        "scores_ineligibility_reason": "goalkeeper_matrix",
    }
    if _requested_profile_distributions(request) and mode != "combined":
        payload["comparison_profile_distributions"] = {
            **build_profile_distributions(
                scope_queryset=scope_queryset,
                row=proxy,
                metric_fields=GK_METRIC_FIELDS,
                percentile_metric_fields=GK_METRICS_WITH_PERCENTILE,
            ),
            "context": scope_context(
                comparison_scope,
                selected_season.season.label,
                scope_seasons,
            ),
        }


class GkDerivedPlayerSeasonListApi(APIView):
    def get(self, request):
        cache_key = stable_cache_key(
            "gk-derived-player-season-list",
            {
                "path": request.path,
                "query": canonical_query_params(
                    request,
                    include={
                        "competition_season",
                        "competition",
                        "season",
                        "team",
                        "min_minutes",
                        "sort",
                        "include",
                        "percentile_scope",
                        "mode",
                        "comparison_scope",
                    },
                ),
            },
        )
        source_version = joined_version(
            "gk-derived-list",
            METRIC_META_CACHE_VERSION,
            SCOPE_PERCENTILES_CACHE_VERSION,
            model_version(PlayerSeasonGkDerivedStats, {"is_current": True}),
            model_version(CompetitionSeason),
        )
        try:
            response, _ = get_or_build_payload_response(
                cache_key=cache_key,
                source_version=source_version,
                builder=lambda: self._build_payload(request),
            )
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return response

    def _build_payload(self, request) -> dict:
        try:
            competition_code, season_label, competition_seasons = _resolve_competition_scope(request)
            queryset = _base_queryset_for_seasons(competition_seasons)
            queryset = _apply_filters(request, queryset)
            queryset = _apply_sorting(request, queryset)
        except DjangoValidationError as exc:
            raise

        rows = list(queryset)
        secondary_team_names = _secondary_team_names_for_rows(rows)
        scope_percentiles = None
        if _requested_scope_percentiles(request):
            scope_code = request.query_params.get("percentile_scope") or competition_code
            try:
                scope_seasons = resolve_scope_seasons(scope_code, season_label)
            except DjangoValidationError as exc:
                raise
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
            row_payload = _row_payload(row, secondary_team_names)
            if scope_percentiles is not None:
                _attach_scope_percentiles(row_payload, row, scope_percentiles)
            payload["results"].append(row_payload)
        if scope_percentiles is not None:
            payload["scope_percentile_context"] = scope_context(scope_code, season_label, scope_seasons)
        if _requested_meta(request):
            payload["meta"] = _gk_meta_payload(competition_seasons)
        return payload


class GkDerivedPlayerSeasonDetailApi(APIView):
    def get(self, request, canonical_player_id: int):
        cache_key = stable_cache_key(
            "gk-derived-player-season-detail",
            {
                "path": request.path,
                "player": canonical_player_id,
                "query": canonical_query_params(
                    request,
                    include={
                        "competition_season",
                        "competition",
                        "season",
                        "include",
                        "percentile_scope",
                        "mode",
                        "comparison_scope",
                    },
                ),
            },
        )
        source_version = joined_version(
            "gk-derived-detail",
            METRIC_META_CACHE_VERSION,
            PROFILE_DISTRIBUTION_CACHE_VERSION,
            SCOPE_PERCENTILES_CACHE_VERSION,
            model_version(PlayerSeasonGkDerivedStats, {"is_current": True}),
            model_version(CompetitionSeason),
        )
        try:
            payload, _ = get_or_build_payload(
                cache_key=cache_key,
                source_version=source_version,
                builder=lambda: self._build_payload(request, canonical_player_id),
            )
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PlayerSeasonGkDerivedStats.DoesNotExist:
            return Response({"detail": "GK derived player-season not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(payload)

    def _build_payload(self, request, canonical_player_id: int) -> dict:
        try:
            competition_season = _resolve_competition_season(request)
            mode = requested_profile_mode(request)
            if mode is not None:
                return self._build_mode_payload(
                    request,
                    competition_season,
                    canonical_player_id,
                    mode,
                )
            queryset = _base_queryset(competition_season)
            row = queryset.get(canonical_player_id=canonical_player_id)
            scope_percentiles = None
            scope_seasons = None
            scope_queryset = None
            if _requested_scope_percentiles(request):
                scope_code = request.query_params.get("percentile_scope") or (
                    request.query_params.get("competition") if is_aggregate_scope(request.query_params.get("competition")) else None
                )
                if not scope_code:
                    raise DjangoValidationError("Provide percentile_scope for scope percentiles.")
                scope_seasons = resolve_scope_seasons(scope_code, competition_season.season.label)
                scope_queryset = _base_queryset_for_seasons(scope_seasons)
                scope_percentiles = build_scope_percentiles(
                    scope_queryset=scope_queryset,
                    rows=[row],
                    metric_fields=GK_METRIC_FIELDS,
                    percentile_metric_fields=GK_METRICS_WITH_PERCENTILE,
                )
        except DjangoValidationError as exc:
            raise
        except PlayerSeasonGkDerivedStats.DoesNotExist:
            raise

        payload = _row_payload(row)
        if scope_percentiles is not None:
            _attach_scope_percentiles(payload, row, scope_percentiles)
            payload["scope_percentile_context"] = scope_context(scope_code, competition_season.season.label, scope_seasons)
        if _requested_profile_distributions(request):
            league_seasons = [competition_season]
            payload["profile_distributions"] = {
                **build_profile_distributions(
                    scope_queryset=_base_queryset(competition_season),
                    row=row,
                    metric_fields=GK_METRIC_FIELDS,
                    percentile_metric_fields=GK_METRICS_WITH_PERCENTILE,
                ),
                "context": scope_context(
                    competition_season.competition.short_code,
                    competition_season.season.label,
                    league_seasons,
                ),
            }
            if scope_queryset is not None and scope_seasons is not None:
                payload["scope_profile_distributions"] = {
                    **build_profile_distributions(
                        scope_queryset=scope_queryset,
                        row=row,
                        metric_fields=GK_METRIC_FIELDS,
                        percentile_metric_fields=GK_METRICS_WITH_PERCENTILE,
                    ),
                    "context": scope_context(
                        scope_code,
                        competition_season.season.label,
                        scope_seasons,
                    ),
                }
        if _requested_meta(request):
            payload["meta"] = _gk_meta_payload([competition_season])
        return payload

    def _build_mode_payload(
        self,
        request,
        selected_season: CompetitionSeason,
        canonical_player_id: int,
        requested_mode: str,
    ) -> dict:
        component_seasons = profile_component_seasons(selected_season, "combined")
        rows = list(
            _base_queryset_for_seasons(component_seasons)
            .filter(canonical_player_id=canonical_player_id)
            .order_by("competition_season__competition__short_code", "competition_season_id")
        )
        if not rows:
            raise PlayerSeasonGkDerivedStats.DoesNotExist
        domestic = [
            row for row in rows
            if row.competition_season.competition.competition_type == "domestic_league"
        ]
        europe = [
            row for row in rows
            if row.competition_season.competition.competition_type == "continental_cup"
        ]
        available = available_profile_modes(
            has_domestic=bool(domestic),
            has_europe=bool(europe),
        )
        mode = resolved_profile_mode(requested_mode, available)
        selected_rows = domestic if mode == "domestic" else europe if mode == "europe" else rows
        secondary_names = _secondary_team_names_for_rows(selected_rows)
        components = [_gk_component_payload(row, secondary_names) for row in selected_rows]

        if len(selected_rows) == 1:
            row = selected_rows[0]
            payload = _row_payload(row, secondary_names)
            if mode == "combined":
                payload["percentiles"] = {metric: None for metric in GK_METRIC_FIELDS}
        else:
            minutes, metrics = _aggregate_gk_metrics(selected_rows)
            representative = selected_rows[0]
            payload = {
                "canonical_player_id": canonical_player_id,
                "canonical_player_name": representative.canonical_player.display_name,
                "canonical_team_id": None,
                "canonical_team_name": None,
                "secondary_teams": [],
                "competition_season": selected_season.id,
                "competition_code": selected_season.competition.short_code,
                "season_label": selected_season.season.label,
                "position_group": "GK",
                "native_position": "GK",
                "minutes": minutes,
                "appearances": metrics["appearances"],
                "formula_version": representative.formula_version,
                "derived_run_id": None,
                "eligibility": {
                    "minimum_eligible_minutes": None,
                    "percentiles_eligible": False,
                    "percentiles_ineligibility_reason": "aggregate_profile_mode",
                    "scores_eligible": False,
                    "scores_ineligibility_reason": "goalkeeper_matrix",
                },
                "metrics": metrics,
                "percentiles": {metric: None for metric in GK_METRIC_FIELDS},
                "scores": {},
                "score_raw": {},
            }
        payload.update({
            "mode": mode,
            "available_modes": available,
            "components": components,
        })
        _attach_gk_comparison_context(
            request,
            payload=payload,
            selected_season=selected_season,
            canonical_player_id=canonical_player_id,
            mode=mode,
        )
        if _requested_meta(request):
            payload["meta"] = _gk_meta_payload(
                [row.competition_season for row in selected_rows]
            )
        return payload
