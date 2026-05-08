from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Sum
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.derived_api import _resolve_competition_scope, _resolve_competition_season
from ingestion.models import CanonicalTeam, MergedPlayerSeason, MergedTeamSeason
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


class TeamSeasonDetailApi(APIView):
    """
    Public: merged team-season stats for one canonical team + league ranks (season + per-match).
    Query: competition + season (same as player derived-stats).
    """

    def get(self, request, canonical_team_id: int):
        try:
            competition_season = _resolve_competition_season(request)
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if not CanonicalTeam.objects.filter(pk=canonical_team_id).exists():
            return Response({"detail": "Team not found."}, status=status.HTTP_404_NOT_FOUND)

        league_rows = list(
            MergedTeamSeason.objects.filter(
                competition_season=competition_season,
                is_current=True,
            ).select_related("canonical_team", "competition_season__competition", "competition_season__season")
        )

        row_map = {r.canonical_team_id: r for r in league_rows}
        row = row_map.get(canonical_team_id)
        if row is None:
            return Response(
                {"detail": "Merged team-season not found for this competition and season."},
                status=status.HTTP_404_NOT_FOUND,
            )

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
        return Response(payload)


class TeamSeasonListApi(APIView):
    """
    Public: all merged team-season rows for one competition-season.
    Mirrors the player list endpoint shape closely enough for cohort charting.
    """

    def get(self, request):
        try:
            competition_code, season_label, competition_seasons = _resolve_competition_scope(request)
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

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
                    "competition_season": competition_season.id,
                    "competition_code": competition_season.competition.short_code,
                    "season_label": competition_season.season.label,
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
        return Response(payload)


_POSITION_ORDER = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3, "UNK": 4}


class TeamSquadApi(APIView):
    """Public: squad list for a canonical team in a competition-season."""

    def get(self, request, canonical_team_id: int):
        try:
            competition_season = _resolve_competition_season(request)
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if not CanonicalTeam.objects.filter(pk=canonical_team_id).exists():
            return Response({"detail": "Team not found."}, status=status.HTTP_404_NOT_FOUND)

        if not MergedTeamSeason.objects.filter(
            competition_season=competition_season,
            canonical_team_id=canonical_team_id,
            is_current=True,
        ).exists():
            return Response(
                {"detail": "Merged team-season not found for this competition and season."},
                status=status.HTTP_404_NOT_FOUND,
            )

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

        return Response(
            {
                "competition_season": competition_season.id,
                "competition_code": competition_season.competition.short_code,
                "season_label": competition_season.season.label,
                "canonical_team_id": canonical_team_id,
                "results": squad,
            }
        )
