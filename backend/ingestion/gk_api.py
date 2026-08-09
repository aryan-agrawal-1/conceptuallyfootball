from __future__ import annotations

from types import SimpleNamespace

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ExpressionWrapper, F, FloatField, QuerySet
from django.db.models.functions import NullIf
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.api_cache import (
    canonical_query_params,
    get_or_build_payload,
    joined_version,
    model_version,
    stable_cache_key,
)
from ingestion.api_pagination import page_bounds, pagination_payload, parse_page
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
    comparison_source_code,
    comparison_scope_options,
    resolved_comparison_scope,
)
from ingestion.profile_distributions import (
    PROFILE_DISTRIBUTION_CACHE_VERSION,
    build_profile_distributions,
)
from ingestion.secondary_teams import secondary_teams_payload
from ingestion.scope_percentiles import (
    SCOPE_PERCENTILES_CACHE_VERSION,
    build_rate_adjusted_scope_percentiles,
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

    team_names = [name.strip() for name in request.query_params.getlist("team_name") if name.strip()]
    if team_names:
        queryset = queryset.filter(canonical_display_team__name__in=team_names)

    min_minutes = request.query_params.get("min_minutes")
    if min_minutes:
        try:
            minimum = int(min_minutes)
        except ValueError as exc:
            raise DjangoValidationError("min_minutes must be an integer.") from exc
        if minimum > 0:
            queryset = queryset.filter(minutes__gte=minimum)
    return queryset


def _apply_sorting(request, queryset: QuerySet[PlayerSeasonGkDerivedStats]) -> QuerySet[PlayerSeasonGkDerivedStats]:
    sort = request.query_params.get("sort", "canonical_player_name")
    descending = sort.startswith("-")
    key = sort[1:] if descending else sort
    rate_mode = request.query_params.get("rate_mode", "per90")
    if rate_mode not in {"per90", "full"}:
        raise DjangoValidationError("rate_mode must be 'per90' or 'full'.")
    field_name = LIST_SORT_FIELDS_GK.get(key)
    if not field_name:
        raise DjangoValidationError(f"Unsupported sort field '{sort}'.")

    full_api = {
        "saves_per_90": "saves",
        "saved_shots_inside_box_per_90": "saved_shots_inside_box",
        "runs_out_per_90": "runs_out",
    }
    full_derived = {"completed_passes_per_90", "accurate_long_balls_per_90"}
    per90_totals = {"clean_sheets", "penalty_saves"}
    if rate_mode == "full" and key in full_api:
        field_name = full_api[key]
    elif rate_mode == "full" and key in full_derived:
        queryset = queryset.annotate(
            matrix_sort_value=ExpressionWrapper(F(key) * F("minutes"), output_field=FloatField())
        )
        field_name = "matrix_sort_value"
    elif rate_mode == "per90" and key in per90_totals:
        queryset = queryset.annotate(
            matrix_sort_value=ExpressionWrapper(
                F(key) / NullIf(F("minutes"), 0),
                output_field=FloatField(),
            )
        )
        field_name = "matrix_sort_value"

    order_by = f"-{field_name}" if descending else field_name
    if field_name != "canonical_player__display_name":
        queryset = queryset.order_by(
            F(field_name).desc(nulls_last=True) if descending else F(field_name).asc(nulls_last=True),
            "canonical_player__display_name",
            "competition_season_id",
            "id",
        )
    else:
        queryset = queryset.order_by(order_by, "competition_season_id", "id")
    return queryset


def _team_facets(queryset: QuerySet[PlayerSeasonGkDerivedStats]) -> list[str]:
    return list(
        queryset.exclude(canonical_display_team__name__isnull=True)
        .order_by("canonical_display_team__name")
        .values_list("canonical_display_team__name", flat=True)
        .distinct()
    )


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


def _attach_gk_comparison_context(
    request,
    *,
    payload: dict,
    selected_season: CompetitionSeason,
    canonical_player_id: int,
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
    eligible = bool(payload.get("minutes")) and payload["minutes"] >= minimum
    reason = None if eligible else "below_minutes_threshold"
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
    if _requested_profile_distributions(request):
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
        try:
            payload = self._build_payload(request)
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)

    def _build_payload(self, request) -> dict:
        try:
            competition_code, season_label, competition_seasons = _resolve_competition_scope(request)
            scope_queryset = _base_queryset_for_seasons(competition_seasons)
            facets = _team_facets(scope_queryset)
            queryset = scope_queryset
            queryset = _apply_filters(request, queryset)
            queryset = _apply_sorting(request, queryset)
            page, page_size = parse_page(request)
        except DjangoValidationError as exc:
            raise

        count = queryset.count()
        start, stop = page_bounds(page, page_size)
        rows = list(queryset[start:stop])
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
            rate_mode = request.query_params.get("rate_mode", "per90")
            adjusted_fields = (
                {"clean_sheets", "penalty_saves"}
                if rate_mode == "per90"
                else {"completed_passes_per_90", "accurate_long_balls_per_90"}
            )
            adjusted_percentiles = build_rate_adjusted_scope_percentiles(
                scope_queryset=_base_queryset_for_seasons(scope_seasons),
                rows=rows,
                metric_fields=adjusted_fields,
                rate_mode=rate_mode,
                integer_fields=adjusted_fields if rate_mode == "full" else (),
            )
            for row_id, values in adjusted_percentiles.items():
                scope_percentiles.setdefault(row_id, {}).update(values)

        payload = {
            **pagination_payload(count=count, page=page, page_size=page_size),
            "competition_season": competition_seasons[0].id if len(competition_seasons) == 1 else 0,
            "competition_code": competition_code,
            "season_label": season_label,
            "matrix_kind": "gk",
            "facets": {"teams": facets},
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
        _attach_gk_comparison_context(
            request,
            payload=payload,
            selected_season=competition_season,
            canonical_player_id=canonical_player_id,
        )
        if _requested_meta(request):
            payload["meta"] = _gk_meta_payload([competition_season])
        return payload
