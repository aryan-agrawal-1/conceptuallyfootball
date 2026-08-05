from __future__ import annotations

from types import SimpleNamespace

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Sum
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
from ingestion.derived_api import _resolve_competition_scope, _resolve_competition_season
from ingestion.models import CanonicalTeam, CompetitionSeason, MergedPlayerSeason, MergedTeamSeason
from ingestion.profile_modes import (
    available_profile_modes,
    profile_component_seasons,
    requested_profile_mode,
    resolved_profile_mode,
)
from ingestion.team_definitions import (
    MERGED_TEAM_SEASON_STAT_FIELDS,
    TEAM_STAT_DIRECTION,
    team_meta_payload,
    team_sections_for_row,
)


def _requested_meta(request) -> bool:
    include = request.query_params.get("include", "")
    return "meta" in {part.strip() for part in include.split(",") if part.strip()}


def _values_equal(a, b) -> bool:
    if a is None or b is None:
        return False
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    return a == b


def _is_percentage_like(field: str) -> bool:
    return field.endswith("_percentage") or field == "average_ball_possession"


def _squad_us_xg_xa_by_team(competition_season_id: int) -> dict[int, tuple[float | None, float | None]]:
    """Sum Understat xG/xA across merged player rows per display team (fallback when Sofascore team feed omits xG/xA)."""
    rows = (
        MergedPlayerSeason.objects.filter(
            competition_season_id=competition_season_id,
            is_current=True,
            canonical_display_team_id__isnull=False,
        )
        .values("canonical_display_team_id")
        .annotate(sxg=Sum("us_xg"), sxa=Sum("us_xa"))
    )
    out: dict[int, tuple[float | None, float | None]] = {}
    for r in rows:
        tid = r["canonical_display_team_id"]
        sxg, sxa = r["sxg"], r["sxa"]
        out[tid] = (
            float(sxg) if sxg is not None else None,
            float(sxa) if sxa is not None else None,
        )
    return out


def _squad_us_xg_xa_by_team_for_seasons(competition_season_ids: list[int]) -> dict[int, tuple[float | None, float | None]]:
    rows = (
        MergedPlayerSeason.objects.filter(
            competition_season_id__in=competition_season_ids,
            is_current=True,
            canonical_display_team_id__isnull=False,
        )
        .values("canonical_display_team_id")
        .annotate(sxg=Sum("us_xg"), sxa=Sum("us_xa"))
    )
    out: dict[int, tuple[float | None, float | None]] = {}
    for r in rows:
        tid = r["canonical_display_team_id"]
        sxg, sxa = r["sxg"], r["sxa"]
        out[tid] = (
            float(sxg) if sxg is not None else None,
            float(sxa) if sxa is not None else None,
        )
    return out


def _season_stat_scalar(
    row: MergedTeamSeason,
    field: str,
    squad_sums: dict[int, tuple[float | None, float | None]],
) -> float | int | None:
    """Season value used for ranks and API `stats` (Sofascore team stat or Σ players' us_xg / us_xa)."""
    if field == "expected_goals":
        if row.expected_goals is not None:
            return row.expected_goals
        sxg, _ = squad_sums.get(row.canonical_team_id, (None, None))
        return sxg
    if field == "expected_assists":
        if row.expected_assists is not None:
            return row.expected_assists
        _, sxa = squad_sums.get(row.canonical_team_id, (None, None))
        return sxa
    return getattr(row, field)


def _per_match_value_for_rank(
    row: MergedTeamSeason,
    field: str,
    squad_sums: dict[int, tuple[float | None, float | None]],
) -> float | None:
    """Comparable rate for ranking (per match); aligns with frontend Per 90 toggle."""
    raw = _season_stat_scalar(row, field, squad_sums)
    if raw is None:
        return None
    if _is_percentage_like(field):
        return float(raw)
    m = row.matches
    if m is None or m <= 0:
        return None
    if field in ("rank", "matches"):
        return float(raw)
    return float(raw) / float(m)


def _rank_scalar(
    row: MergedTeamSeason,
    field: str,
    *,
    per_match: bool,
    squad_sums: dict[int, tuple[float | None, float | None]],
) -> float | int | None:
    if per_match:
        return _per_match_value_for_rank(row, field, squad_sums)
    return _season_stat_scalar(row, field, squad_sums)


def _competition_ranks_for_field(
    rows: list[MergedTeamSeason],
    field: str,
    *,
    per_match: bool,
    squad_sums: dict[int, tuple[float | None, float | None]],
) -> dict[int, int | None]:
    """Map canonical_team_id -> rank (1-based, competition-style ties), None if value missing."""
    direction = TEAM_STAT_DIRECTION.get(field, "higher")
    higher_is_better = direction == "higher"

    ranks_out: dict[int, int | None] = {row.canonical_team_id: None for row in rows}
    pairs: list[tuple[int, float]] = []
    for row in rows:
        val = _rank_scalar(row, field, per_match=per_match, squad_sums=squad_sums)
        if val is None:
            continue
        pairs.append((row.canonical_team_id, float(val)))

    if not pairs:
        return ranks_out

    pairs.sort(key=lambda t: ((-t[1], t[0]) if higher_is_better else (t[1], t[0])))

    for i, (tid, val) in enumerate(pairs):
        if i == 0:
            r = 1
        else:
            prev_tid, prev_val = pairs[i - 1]
            if _values_equal(val, prev_val):
                r = ranks_out[prev_tid]  # type: ignore[assignment]
            else:
                r = i + 1
        ranks_out[tid] = r

    return ranks_out


def _build_all_ranks(
    rows: list[MergedTeamSeason],
    *,
    per_match: bool,
    squad_sums: dict[int, tuple[float | None, float | None]],
) -> dict[str, dict[int, int | None]]:
    out: dict[str, dict[int, int | None]] = {}
    for field in MERGED_TEAM_SEASON_STAT_FIELDS:
        out[field] = _competition_ranks_for_field(
            rows,
            field,
            per_match=per_match,
            squad_sums=squad_sums,
        )
    return out


def _stat_values_for_team_row(
    row: MergedTeamSeason,
    squad_sums: dict[int, tuple[float | None, float | None]],
) -> dict[str, object]:
    """Public `stats` map with xG/xA filled from squad sums when Sofascore team columns are null."""
    out: dict[str, object] = {}
    for k in MERGED_TEAM_SEASON_STAT_FIELDS:
        out[k] = _season_stat_scalar(row, k, squad_sums)
    return out


TEAM_PERCENTAGE_BASES = {
    "accurate_passes_percentage": ("accurate_passes", "total_passes"),
    "accurate_long_balls_percentage": ("accurate_long_balls", "total_long_balls"),
    "accurate_crosses_percentage": ("accurate_crosses", "total_crosses"),
}

TEAM_RECONSTRUCTED_PERCENTAGE_BASES = {
    "duels_won_percentage": "duels_won",
    "aerial_duels_won_percentage": "aerial_duels_won",
    "ground_duels_won_percentage": "ground_duels_won",
}


def _aggregate_team_stats(rows: list[MergedTeamSeason]) -> dict[str, object]:
    """Aggregate counts; calculate percentages only from their source totals."""
    component_stats = [
        _stat_values_for_team_row(
            row,
            _squad_us_xg_xa_by_team(row.competition_season_id),
        )
        for row in rows
    ]
    stats: dict[str, object] = {}
    for field in MERGED_TEAM_SEASON_STAT_FIELDS:
        if field == "rank" or field == "average_ball_possession" or field.endswith("_percentage"):
            stats[field] = None
        else:
            values = [component[field] for component in component_stats]
            stats[field] = None if any(value is None for value in values) else sum(values)
    if stats["goals_for"] is not None and stats["goals_against"] is not None:
        stats["goal_difference"] = stats["goals_for"] - stats["goals_against"]
    for field, (numerator, denominator) in TEAM_PERCENTAGE_BASES.items():
        num, denom = stats[numerator], stats[denominator]
        stats[field] = None if num is None or denom is None or denom <= 0 else float(num) / float(denom) * 100.0
    for field, numerator in TEAM_RECONSTRUCTED_PERCENTAGE_BASES.items():
        attempts = 0.0
        for component in component_stats:
            won = component[numerator]
            percentage = component[field]
            if won is None or percentage is None or percentage <= 0:
                attempts = -1.0
                break
            attempts += float(won) / (float(percentage) / 100.0)
        stats[field] = (
            None
            if stats[numerator] is None or attempts <= 0
            else float(stats[numerator]) / attempts * 100.0
        )
    possession_parts = [
        (component["average_ball_possession"], component["matches"])
        for component in component_stats
    ]
    if all(value is not None and matches is not None for value, matches in possession_parts):
        total_matches = sum(float(matches) for _, matches in possession_parts)
        stats["average_ball_possession"] = (
            None
            if total_matches <= 0
            else sum(float(value) * float(matches) for value, matches in possession_parts) / total_matches
        )
    return stats


def _team_component_payload(row: MergedTeamSeason) -> dict:
    return {
        "competition_season": row.competition_season_id,
        "competition_code": row.competition_season.competition.short_code,
        "competition_type": row.competition_season.competition.competition_type,
        "season_label": row.competition_season.season.label,
        "canonical_team_id": row.canonical_team_id,
        "canonical_team_name": row.canonical_team.name,
    }


class TeamSeasonDetailApi(APIView):
    """
    Public: merged team-season stats for one canonical team + league ranks (season + per-match).
    Query: competition + season (same as player derived-stats).
    """

    def get(self, request, canonical_team_id: int):
        cache_key = stable_cache_key(
            "team-season-detail",
            {
                "path": request.path,
                "team": canonical_team_id,
                "query": canonical_query_params(
                    request,
                    include={"competition_season", "competition", "season", "include", "mode"},
                ),
            },
        )
        source_version = joined_version(
            "team-season-detail",
            model_version(MergedTeamSeason, {"is_current": True}),
            model_version(MergedPlayerSeason, {"is_current": True}),
            model_version(CompetitionSeason),
        )
        try:
            payload, _ = get_or_build_payload(
                cache_key=cache_key,
                source_version=source_version,
                builder=lambda: self._build_payload(request, canonical_team_id),
            )
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except MergedTeamSeason.DoesNotExist as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(payload)

    def _build_payload(self, request, canonical_team_id: int) -> dict:
        try:
            competition_season = _resolve_competition_season(request)
        except DjangoValidationError as exc:
            raise

        if not CanonicalTeam.objects.filter(pk=canonical_team_id).exists():
            raise MergedTeamSeason.DoesNotExist("Team not found.")

        mode = requested_profile_mode(request)
        if mode is not None:
            return self._build_mode_payload(competition_season, canonical_team_id, mode, request)

        league_rows = list(
            MergedTeamSeason.objects.filter(
                competition_season=competition_season,
                is_current=True,
            ).select_related("canonical_team", "competition_season__competition", "competition_season__season")
        )

        row_map = {r.canonical_team_id: r for r in league_rows}
        row = row_map.get(canonical_team_id)
        if row is None:
            raise MergedTeamSeason.DoesNotExist("Merged team-season not found for this competition and season.")

        squad_sums = _squad_us_xg_xa_by_team(competition_season.id)

        rank_maps_season = _build_all_ranks(league_rows, per_match=False, squad_sums=squad_sums)
        rank_maps_pm = _build_all_ranks(league_rows, per_match=True, squad_sums=squad_sums)

        stat_values = _stat_values_for_team_row(row, squad_sums)
        ranks: dict[str, int | None] = {}
        ranks_per_match: dict[str, int | None] = {}
        for k in MERGED_TEAM_SEASON_STAT_FIELDS:
            ranks[k] = rank_maps_season.get(k, {}).get(canonical_team_id)
            ranks_per_match[k] = rank_maps_pm.get(k, {}).get(canonical_team_id)

        payload = {
            "canonical_team_id": row.canonical_team_id,
            "canonical_team_name": row.canonical_team.name,
            "competition_season": competition_season.id,
            "competition_code": competition_season.competition.short_code,
            "season_label": competition_season.season.label,
            "stats": stat_values,
            "ranks": ranks,
            "ranks_per_match": ranks_per_match,
            "sections": team_sections_for_row(row, ranks, ranks_per_match, stat_values),
        }
        if _requested_meta(request):
            payload["meta"] = team_meta_payload()
        return payload

    def _build_mode_payload(self, selected_season, canonical_team_id: int, requested_mode: str, request) -> dict:
        seasons = profile_component_seasons(selected_season, "combined")
        rows = list(
            MergedTeamSeason.objects.filter(
                competition_season__in=seasons,
                canonical_team_id=canonical_team_id,
                is_current=True,
            ).select_related("canonical_team", "competition_season__competition", "competition_season__season")
            .order_by("competition_season__competition__short_code", "competition_season_id")
        )
        domestic = [r for r in rows if r.competition_season.competition.competition_type == "domestic_league"]
        europe = [r for r in rows if r.competition_season.competition.competition_type == "continental_cup"]
        available = available_profile_modes(has_domestic=bool(domestic), has_europe=bool(europe))
        mode = resolved_profile_mode(requested_mode, available)
        selected_rows = domestic if mode == "domestic" else europe if mode == "europe" else rows
        components = [_team_component_payload(row) for row in selected_rows]

        # A single concrete slice retains its established competition context
        # and ranks. Aggregate modes deliberately do not invent a cohort.
        if len(selected_rows) == 1:
            row = selected_rows[0]
            league_rows = list(MergedTeamSeason.objects.filter(competition_season=row.competition_season, is_current=True))
            squad_sums = _squad_us_xg_xa_by_team(row.competition_season_id)
            rank_maps = _build_all_ranks(league_rows, per_match=False, squad_sums=squad_sums)
            rank_maps_pm = _build_all_ranks(league_rows, per_match=True, squad_sums=squad_sums)
            stat_values = _stat_values_for_team_row(row, squad_sums)
            ranks = {key: rank_maps[key].get(canonical_team_id) for key in MERGED_TEAM_SEASON_STAT_FIELDS}
            ranks_pm = {key: rank_maps_pm[key].get(canonical_team_id) for key in MERGED_TEAM_SEASON_STAT_FIELDS}
            team_name = row.canonical_team.name
        else:
            stat_values = _aggregate_team_stats(selected_rows)
            ranks = {key: None for key in MERGED_TEAM_SEASON_STAT_FIELDS}
            ranks_pm = {key: None for key in MERGED_TEAM_SEASON_STAT_FIELDS}
            team_name = rows[0].canonical_team.name

        if mode == "combined":
            # There is no combined league table or points/rank cohort.
            stat_values["rank"] = None
            stat_values["points"] = None
            ranks = {key: None for key in MERGED_TEAM_SEASON_STAT_FIELDS}
            ranks_pm = {key: None for key in MERGED_TEAM_SEASON_STAT_FIELDS}

        payload = {
            "canonical_team_id": canonical_team_id,
            "canonical_team_name": team_name,
            "competition_season": selected_season.id,
            "competition_code": selected_season.competition.short_code,
            "season_label": selected_season.season.label,
            "mode": mode,
            "available_modes": available,
            "components": components,
            "stats": stat_values,
            "ranks": ranks,
            "ranks_per_match": ranks_pm,
            "sections": team_sections_for_row(SimpleNamespace(**stat_values), ranks, ranks_pm, stat_values),
        }
        if _requested_meta(request):
            payload["meta"] = team_meta_payload()
        return payload


class TeamSeasonListApi(APIView):
    """
    Public: all merged team-season rows for one competition-season.
    Mirrors the player list endpoint shape closely enough for cohort charting.
    """

    def get(self, request):
        cache_key = stable_cache_key(
            "team-season-list",
            {
                "path": request.path,
                "query": canonical_query_params(
                    request,
                    include={"competition_season", "competition", "season", "include"},
                ),
            },
        )
        source_version = joined_version(
            "team-season-list",
            model_version(MergedTeamSeason, {"is_current": True}),
            model_version(MergedPlayerSeason, {"is_current": True}),
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
        except DjangoValidationError as exc:
            raise

        league_rows = list(
            MergedTeamSeason.objects.filter(
                competition_season__in=competition_seasons,
                is_current=True,
            )
            .select_related("canonical_team", "competition_season__competition", "competition_season__season")
            .order_by("competition_season__competition__short_code", "rank", "canonical_team__name")
        )

        squad_sums = _squad_us_xg_xa_by_team_for_seasons([cs.id for cs in competition_seasons])
        rank_maps_season = _build_all_ranks(league_rows, per_match=False, squad_sums=squad_sums)
        rank_maps_pm = _build_all_ranks(league_rows, per_match=True, squad_sums=squad_sums)

        results = []
        for row in league_rows:
            stat_values = _stat_values_for_team_row(row, squad_sums)
            ranks: dict[str, int | None] = {}
            ranks_per_match: dict[str, int | None] = {}
            for k in MERGED_TEAM_SEASON_STAT_FIELDS:
                ranks[k] = rank_maps_season.get(k, {}).get(row.canonical_team_id)
                ranks_per_match[k] = rank_maps_pm.get(k, {}).get(row.canonical_team_id)

            results.append(
                {
                    "canonical_team_id": row.canonical_team_id,
                    "canonical_team_name": row.canonical_team.name,
                    "competition_season": row.competition_season_id,
                    "competition_code": row.competition_season.competition.short_code,
                    "season_label": row.competition_season.season.label,
                    "stats": stat_values,
                    "ranks": ranks,
                    "ranks_per_match": ranks_per_match,
                }
            )

        payload = {
            "competition_season": competition_seasons[0].id if len(competition_seasons) == 1 else 0,
            "competition_code": competition_code,
            "season_label": season_label,
            "count": len(results),
            "results": results,
        }
        if _requested_meta(request):
            payload["meta"] = team_meta_payload()
        return payload


_POSITION_ORDER = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3, "UNK": 4}


class TeamSquadApi(APIView):
    """Public: squad list for a canonical team in a competition-season."""

    def get(self, request, canonical_team_id: int):
        cache_key = stable_cache_key(
            "team-squad",
            {
                "path": request.path,
                "team": canonical_team_id,
                "query": canonical_query_params(
                    request,
                    include={"competition_season", "competition", "season"},
                ),
            },
        )
        source_version = joined_version(
            "team-squad",
            model_version(MergedTeamSeason, {"is_current": True}),
            model_version(MergedPlayerSeason, {"is_current": True}),
        )
        try:
            payload, _ = get_or_build_payload(
                cache_key=cache_key,
                source_version=source_version,
                builder=lambda: self._build_payload(request, canonical_team_id),
            )
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except MergedTeamSeason.DoesNotExist as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(payload)

    def _build_payload(self, request, canonical_team_id: int) -> dict:
        try:
            competition_season = _resolve_competition_season(request)
        except DjangoValidationError as exc:
            raise

        if not CanonicalTeam.objects.filter(pk=canonical_team_id).exists():
            raise MergedTeamSeason.DoesNotExist("Team not found.")

        if not MergedTeamSeason.objects.filter(
            competition_season=competition_season,
            canonical_team_id=canonical_team_id,
            is_current=True,
        ).exists():
            raise MergedTeamSeason.DoesNotExist("Merged team-season not found for this competition and season.")

        players = (
            MergedPlayerSeason.objects.filter(
                competition_season=competition_season,
                is_current=True,
                canonical_display_team_id=canonical_team_id,
            )
            .select_related("canonical_player")
            .order_by("canonical_player__display_name")
        )

        squad = []
        for p in players:
            squad.append(
                {
                    "canonical_player_id": p.canonical_player_id,
                    "canonical_player_name": p.canonical_player.display_name,
                    "position_group": p.position_group,
                    "native_position": p.native_position or None,
                    "minutes": p.minutes,
                    "appearances": p.ss_appearances,
                }
            )

        squad.sort(
            key=lambda r: (
                _POSITION_ORDER.get(r["position_group"], 99),
                -(r["minutes"] or 0),
                r["canonical_player_name"].lower(),
            )
        )

        return {
            "competition_season": competition_season.id,
            "competition_code": competition_season.competition.short_code,
            "season_label": competition_season.season.label,
            "canonical_team_id": canonical_team_id,
            "results": squad,
        }
