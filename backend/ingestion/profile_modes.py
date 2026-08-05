"""Request-time season profile mode discovery shared by public profile APIs."""

from __future__ import annotations

from django.core.exceptions import ValidationError

from ingestion.competition_scope import BIG_FIVE_COMPETITION_CODES
from ingestion.models import CompetitionSeason, CompetitionType

PROFILE_MODES = ("domestic", "europe", "combined")


def requested_profile_mode(request) -> str | None:
    value = request.query_params.get("mode")
    if value is None:
        return None
    mode = value.strip().lower()
    if mode not in PROFILE_MODES:
        raise ValidationError("mode must be one of: domestic, europe, combined.")
    return mode


def profile_component_seasons(selected: CompetitionSeason, mode: str) -> list[CompetitionSeason]:
    """Return published, deterministic season slices for an explicit profile mode."""
    seasons = CompetitionSeason.objects.filter(
        season_id=selected.season_id,
        is_active=True,
        is_published=True,
    ).select_related("competition", "season")
    if mode == "domestic":
        seasons = seasons.filter(competition__competition_type=CompetitionType.DOMESTIC_LEAGUE)
    elif mode == "europe":
        seasons = seasons.filter(competition__competition_type=CompetitionType.CONTINENTAL_CUP)
    else:
        seasons = seasons.filter(competition__competition_type__in=(
            CompetitionType.DOMESTIC_LEAGUE,
            CompetitionType.CONTINENTAL_CUP,
        ))
    return list(seasons.order_by("competition__short_code", "pk"))


def available_profile_modes(*, has_domestic: bool, has_europe: bool) -> list[str]:
    available: list[str] = []
    if has_domestic:
        available.append("domestic")
    if has_europe:
        available.append("europe")
    # Combined includes every available eligible slice. For domestic-only and
    # Europe-only entities it deterministically equals the available mode.
    if has_domestic or has_europe:
        available.append("combined")
    return available


def resolved_profile_mode(requested: str, available: list[str]) -> str:
    """Normalize an unavailable valid mode so direct links stay deterministic."""
    if requested in available:
        return requested
    for fallback in ("domestic", "europe", "combined"):
        if fallback in available:
            return fallback
    raise ValidationError("No season profile data is available for this entity.")


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
