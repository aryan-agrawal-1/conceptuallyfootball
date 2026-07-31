from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from ingestion.api_cache import invalidate_materialized_api_payloads
from ingestion.models import (
    CompetitionSeason,
    IngestionRunStatus,
    PlayerSeasonDerivedStats,
    PlayerSeasonGkDerivedStats,
)


@dataclass(frozen=True)
class PublicationReadiness:
    ready: bool
    current_outfield_rows: int
    current_goalkeeper_rows: int
    reason: str


def publication_readiness(competition_season: CompetitionSeason) -> PublicationReadiness:
    current_outfield_rows = PlayerSeasonDerivedStats.objects.filter(
        competition_season=competition_season,
        is_current=True,
        derived_ingestion_run__status=IngestionRunStatus.SUCCESS,
    ).count()
    current_goalkeeper_rows = PlayerSeasonGkDerivedStats.objects.filter(
        competition_season=competition_season,
        is_current=True,
        derived_ingestion_run__status=IngestionRunStatus.SUCCESS,
    ).count()
    ready = current_outfield_rows + current_goalkeeper_rows > 0
    reason = "" if ready else "No current player rows from a successful derived materialization."
    return PublicationReadiness(
        ready=ready,
        current_outfield_rows=current_outfield_rows,
        current_goalkeeper_rows=current_goalkeeper_rows,
        reason=reason,
    )


@transaction.atomic
def set_competition_season_published(
    competition_season: CompetitionSeason,
    *,
    published: bool,
) -> PublicationReadiness:
    locked = CompetitionSeason.objects.select_for_update().get(pk=competition_season.pk)
    readiness = publication_readiness(locked)
    if published:
        if not locked.is_active:
            raise ValueError("Inactive competition-season slices cannot be published.")
        if not readiness.ready:
            raise ValueError(readiness.reason)
    if locked.is_published != published:
        locked.is_published = published
        locked.save(update_fields=["is_published"])
        invalidate_materialized_api_payloads()
    competition_season.is_published = published
    return readiness
