from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.derived_definitions import (
    FORMULA_VERSION,
    LIST_SORT_FIELDS,
    METRIC_DEFINITIONS,
    METRIC_FIELDS,
    METRIC_GROUPS,
    MIN_ELIGIBLE_MINUTES,
    SCORE_DEFINITIONS,
    SCORE_FIELDS,
)
from ingestion.models import CompetitionSeason, PlayerSeasonDerivedStats
from ingestion.secondary_teams import secondary_teams_payload

BIG_FIVE_COMPETITION_CODES = ("ENG1", "GER1", "SPA1", "FRA1", "ITA1")


def _has_metric_value(row: PlayerSeasonDerivedStats, metric: str) -> bool:
    return getattr(row, metric) is not None


def _requested_meta(request) -> bool:
    include = request.query_params.get("include", "")
    return "meta" in {part.strip() for part in include.split(",") if part.strip()}


def _meta_payload() -> dict:
    return {
        "formula_version": FORMULA_VERSION,
        "minimum_eligible_minutes": MIN_ELIGIBLE_MINUTES,
        "metric_groups": METRIC_GROUPS,
        "metrics": METRIC_DEFINITIONS,
        "scores": SCORE_DEFINITIONS,
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


def _resolve_competition_scope(request) -> tuple[str, str, list[CompetitionSeason]]:
    competition_season_id = request.query_params.get("competition_season")
    if competition_season_id:
        competition_season = _resolve_competition_season(request)
        return (
            competition_season.competition.short_code,
            competition_season.season.label,
            [competition_season],
        )

    competition_code = (request.query_params.get("competition") or "").strip().upper()
    season_label = (request.query_params.get("season") or "").strip()
    if not competition_code or not season_label:
        raise DjangoValidationError(
            "Provide either competition_season or both competition and season."
        )

    rows = CompetitionSeason.objects.select_related("competition", "season").filter(
        is_active=True,
        season__label__iexact=season_label,
    )
    if competition_code == "BIG5":
        rows = rows.filter(competition__short_code__in=BIG_FIVE_COMPETITION_CODES)
    elif competition_code == "ALL":
        pass
    else:
        return (competition_code, season_label, [_resolve_competition_season(request)])

    seasons = list(rows.order_by("competition__short_code"))
    if not seasons:
        raise DjangoValidationError("Unknown competition and season combination.")
    return (competition_code, seasons[0].season.label, seasons)


def _base_queryset(competition_season: CompetitionSeason) -> QuerySet[PlayerSeasonDerivedStats]:
    return _base_queryset_for_seasons([competition_season])


def _base_queryset_for_seasons(competition_seasons: list[CompetitionSeason]) -> QuerySet[PlayerSeasonDerivedStats]:
    return (
        PlayerSeasonDerivedStats.objects.filter(
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


def _apply_filters(request, queryset: QuerySet[PlayerSeasonDerivedStats]) -> QuerySet[PlayerSeasonDerivedStats]:
    team = request.query_params.get("team")
    if team:
        queryset = queryset.filter(canonical_display_team_id=team)

    position_group = request.query_params.get("position_group")
    if position_group:
        queryset = queryset.filter(position_group__iexact=position_group)

    min_minutes = request.query_params.get("min_minutes")
    if min_minutes:
        try:
            queryset = queryset.filter(minutes__gte=int(min_minutes))
        except ValueError as exc:
            raise DjangoValidationError("min_minutes must be an integer.") from exc
    return queryset


def _apply_sorting(request, queryset: QuerySet[PlayerSeasonDerivedStats]) -> QuerySet[PlayerSeasonDerivedStats]:
    sort = request.query_params.get("sort", "canonical_player_name")
    descending = sort.startswith("-")
    key = sort[1:] if descending else sort
    field_name = LIST_SORT_FIELDS.get(key)
    if not field_name:
        raise DjangoValidationError(f"Unsupported sort field '{sort}'.")
    order_by = f"-{field_name}" if descending else field_name
    if field_name != "canonical_player__display_name":
        queryset = queryset.order_by(order_by, "canonical_player__display_name")
    else:
        queryset = queryset.order_by(order_by)
    return queryset


def _row_payload(row: PlayerSeasonDerivedStats) -> dict:
    return {
        "canonical_player_id": row.canonical_player_id,
        "canonical_player_name": row.canonical_player.display_name,
        "canonical_team_id": row.canonical_display_team_id,
        "canonical_team_name": row.canonical_display_team.name if row.canonical_display_team else None,
        "secondary_teams": secondary_teams_payload(row.merged_player_season),
        "competition_season": row.competition_season_id,
        "competition_code": row.competition_season.competition.short_code,
        "season_label": row.competition_season.season.label,
        "position_group": row.position_group,
        "native_position": row.native_position,
        "minutes": row.minutes,
        "formula_version": row.formula_version,
        "derived_run_id": row.derived_ingestion_run_id,
        "eligibility": {
            "percentiles_eligible": row.percentiles_eligible,
            "percentiles_ineligibility_reason": row.percentiles_ineligibility_reason or None,
            "scores_eligible": row.scores_eligible,
            "scores_ineligibility_reason": row.scores_ineligibility_reason or None,
        },
        "metrics": {metric: getattr(row, metric) for metric in METRIC_FIELDS},
        "percentiles": {metric: getattr(row, f"{metric}_percentile") for metric in METRIC_FIELDS},
        "scores": {score: getattr(row, score) for score in SCORE_FIELDS},
        "score_raw": {score: getattr(row, f"{score}_raw") for score in SCORE_FIELDS},
    }


def _detail_sections(row: PlayerSeasonDerivedStats) -> dict[str, dict]:
    sections: dict[str, dict] = {}
    for group_key, group_label in METRIC_GROUPS.items():
        entries = []
        for metric, definition in METRIC_DEFINITIONS.items():
            if definition["group"] != group_key:
                continue
            if not _has_metric_value(row, metric):
                continue
            entries.append(
                {
                    "key": metric,
                    "label": definition["label"],
                    "value": getattr(row, metric),
                    "percentile": getattr(row, f"{metric}_percentile"),
                }
            )
        sections[group_key] = {
            "label": group_label,
            "metrics": entries,
        }
    return sections


class DerivedPlayerSeasonListApi(APIView):
    def get(self, request):
        try:
            competition_code, season_label, competition_seasons = _resolve_competition_scope(request)
            queryset = _base_queryset_for_seasons(competition_seasons)
            queryset = _apply_filters(request, queryset)
            queryset = _apply_sorting(request, queryset)
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            "competition_season": competition_seasons[0].id if len(competition_seasons) == 1 else 0,
            "competition_code": competition_code,
            "season_label": season_label,
            "count": queryset.count(),
            "results": [_row_payload(row) for row in queryset],
        }
        if _requested_meta(request):
            payload["meta"] = _meta_payload()
        return Response(payload)


class DerivedPlayerSeasonDetailApi(APIView):
    def get(self, request, canonical_player_id: int):
        try:
            competition_season = _resolve_competition_season(request)
            queryset = _base_queryset(competition_season)
            row = queryset.get(canonical_player_id=canonical_player_id)
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PlayerSeasonDerivedStats.DoesNotExist:
            return Response({"detail": "Derived player-season not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = _row_payload(row)
        payload["sections"] = _detail_sections(row)
        if _requested_meta(request):
            payload["meta"] = _meta_payload()
        return Response(payload)
