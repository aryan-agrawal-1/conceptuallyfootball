"""Comparison cohort discovery shared by public player profile APIs."""

from __future__ import annotations

from ingestion.competition_scope import BIG_FIVE_COMPETITION_CODES
from ingestion.models import CompetitionSeason, CompetitionType


def comparison_scope_options(
    *,
    selected: CompetitionSeason,
    canonical_player_id: int,
    row_model,
) -> tuple[list[str], str | None]:
    """Return the concrete domestic cohort plus eligible aggregate cohorts.

    A player can have more than one domestic membership after a transfer. The
    selected concrete domestic slice wins; otherwise the first published code
    is the deterministic source cohort. Continental competitions are never
    exposed here because their comparison semantics remain deliberately
    undefined.
    """
    domestic_rows = list(
        row_model.objects.filter(
            canonical_player_id=canonical_player_id,
            competition_season__season_id=selected.season_id,
            competition_season__is_active=True,
            competition_season__is_published=True,
            competition_season__competition__competition_type=CompetitionType.DOMESTIC_LEAGUE,
            is_current=True,
        )
        .select_related("competition_season__competition")
        .order_by("competition_season__competition__short_code", "competition_season_id")
    )
    if not domestic_rows:
        return [], None

    rows_by_code = {
        row.competition_season.competition.short_code: row
        for row in domestic_rows
    }
    selected_code = selected.competition.short_code
    source_code = selected_code if selected_code in rows_by_code else next(iter(rows_by_code))
    scopes = [source_code]

    aggregate_rows = [
        row
        for row in domestic_rows
        if row.competition_season.competition.include_in_domestic_aggregates
    ]
    if any(
        row.competition_season.competition.short_code in BIG_FIVE_COMPETITION_CODES
        for row in aggregate_rows
    ):
        scopes.append("BIG5")
    if aggregate_rows:
        scopes.append("ALL")
    return scopes, source_code


def resolved_comparison_scope(requested: str | None, available: list[str]) -> str | None:
    if not available:
        return None
    normalized = (requested or "").strip().upper()
    if normalized in available:
        return normalized
    return available[0]


def comparison_source_code(
    *,
    selected: CompetitionSeason,
    canonical_player_id: int,
    row_model,
    comparison_scope: str | None,
    default_code: str | None,
) -> str | None:
    """Pick a concrete membership that actually belongs to the chosen scope."""
    if comparison_scope is None:
        return None
    codes = list(
        row_model.objects.filter(
            canonical_player_id=canonical_player_id,
            competition_season__season_id=selected.season_id,
            competition_season__is_active=True,
            competition_season__is_published=True,
            competition_season__competition__competition_type=CompetitionType.DOMESTIC_LEAGUE,
            competition_season__competition__include_in_domestic_aggregates=True,
            is_current=True,
        )
        .order_by("competition_season__competition__short_code")
        .values_list("competition_season__competition__short_code", flat=True)
        .distinct()
    )
    if comparison_scope == "BIG5":
        eligible = [code for code in codes if code in BIG_FIVE_COMPETITION_CODES]
        return default_code if default_code in eligible else (eligible[0] if eligible else None)
    if comparison_scope == "ALL":
        return default_code if default_code in codes else (codes[0] if codes else None)
    return comparison_scope if comparison_scope in codes else None
