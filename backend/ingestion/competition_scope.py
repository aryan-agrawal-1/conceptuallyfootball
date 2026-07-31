from __future__ import annotations

from collections.abc import Iterable

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet

from ingestion.models import CompetitionSeason, CompetitionType


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

    rows = public_competition_seasons().select_related("competition", "season").filter(
        season__label__iexact=season_label,
    )
    if code in AGGREGATE_SCOPE_CODES:
        rows = domestic_aggregate_seasons(rows)
        if code == "BIG5":
            rows = rows.filter(competition__short_code__in=BIG_FIVE_COMPETITION_CODES)
    else:
        rows = rows.filter(competition__short_code__iexact=code)

    seasons = list(rows.order_by("competition__short_code"))
    if not seasons:
        raise DjangoValidationError("Unknown competition and season combination.")
    return seasons


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
