from __future__ import annotations

from collections.abc import Iterable

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet

from ingestion.models import CompetitionSeason, CompetitionType
from ingestion.services.season_labels import (
    aggregate_constituent_season_labels,
    candidate_season_labels,
)


BIG_FIVE_COMPETITION_CODES = ("ENG1", "GER1", "SPA1", "FRA1", "ITA1")
AGGREGATE_SCOPE_CODES = ("BIG5", "ALL")


def public_competition_seasons() -> QuerySet[CompetitionSeason]:
    return CompetitionSeason.objects.filter(is_active=True, is_published=True)


def domestic_aggregate_seasons(queryset: QuerySet[CompetitionSeason]) -> QuerySet[CompetitionSeason]:
    return queryset.filter(
        competition__competition_type=CompetitionType.DOMESTIC_LEAGUE,
        competition__include_in_domestic_aggregates=True,
    )


def resolve_public_scope(scope_code: str, season_label: str) -> list[CompetitionSeason]:
    code = scope_code.strip().upper()
    if not code or not season_label:
        raise DjangoValidationError("Provide competition and season.")

    requested_labels = (
        aggregate_constituent_season_labels(season_label)
        if code in AGGREGATE_SCOPE_CODES
        else candidate_season_labels(code, season_label)
    )

    rows = public_competition_seasons().select_related("competition", "season")
    rows = rows.filter(season__label__in=requested_labels)
    if code in AGGREGATE_SCOPE_CODES:
        rows = domestic_aggregate_seasons(rows)
        if code == "BIG5":
            rows = rows.filter(competition__short_code__in=BIG_FIVE_COMPETITION_CODES)
    else:
        rows = rows.filter(competition__short_code__iexact=code)

    seasons = list(rows.order_by("competition__short_code", "season__label"))
    if code not in AGGREGATE_SCOPE_CODES and len(seasons) > 1:
        raise DjangoValidationError(
            f"Ambiguous {code} season label {season_label!r}; both canonical and legacy slices exist."
        )
    if not seasons:
        raise DjangoValidationError("Unknown competition and season combination.")
    return seasons


def resolve_public_competition_season(
    competition_code: str,
    season_label: str,
) -> CompetitionSeason:
    code = competition_code.strip().upper()
    candidate_labels = candidate_season_labels(code, season_label)
    rows = list(
        public_competition_seasons().select_related("competition", "season").filter(
            competition__short_code__iexact=code,
            season__label__in=candidate_labels,
        ).order_by("season__label")
    )
    if len(rows) > 1:
        raise DjangoValidationError(
            f"Ambiguous {code} season label {season_label!r}; both canonical and legacy slices exist."
        )
    if not rows:
        raise DjangoValidationError("Unknown competition and season combination.")
    return rows[0]


def resolve_active_competition_season(
    competition_code: str,
    season_label: str,
) -> CompetitionSeason:
    code = competition_code.strip().upper()
    candidate_labels = candidate_season_labels(code, season_label)
    rows = list(
        CompetitionSeason.objects.select_related("competition", "season").filter(
            competition__short_code__iexact=code,
            season__label__in=candidate_labels,
            is_active=True,
        ).order_by("season__label")
    )
    if len(rows) > 1:
        raise DjangoValidationError(
            f"Ambiguous {code} season label {season_label!r}; both canonical and legacy slices exist."
        )
    if not rows:
        raise DjangoValidationError("Unknown active competition and season combination.")
    return rows[0]


def eligibility_thresholds(competition_seasons: Iterable[CompetitionSeason]) -> dict[str, int]:
    return {
        season.competition.short_code: season.minimum_eligible_minutes
        for season in competition_seasons
    }


def scope_minimum_eligible_minutes(competition_seasons: Iterable[CompetitionSeason]) -> int:
    thresholds = set(eligibility_thresholds(competition_seasons).values())
    if not thresholds:
        return 450
    return min(thresholds)
