from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from ingestion.models import (
    CompetitionSeason,
    IngestionRun,
    IngestionRunStatus,
    IngestionKind,
    SofascoreTeamSeasonSource,
    SofascorePlayerSeasonSource,
    UnderstatPlayerSeasonSource,
)


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    message: str = ""


def _configured_min_rows(explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    return int(getattr(settings, "STATBALLER_INGEST_MIN_ROWS", 200))


def validate_understat_slice(
    competition_season: CompetitionSeason,
    *,
    min_rows: int | None = None,
    min_match_rate: float = 0.25,
) -> ValidationResult:
    min_rows = _configured_min_rows(min_rows)
    qs = UnderstatPlayerSeasonSource.objects.filter(competition_season=competition_season)
    total = qs.count()
    if total < min_rows:
        return ValidationResult(
            False,
            f"Understat row count {total} is below minimum threshold {min_rows} (possible systemic fetch failure).",
        )
    matched = qs.filter(canonical_player__isnull=False).count()
    rate = matched / total if total else 0.0
    if rate < min_match_rate:
        return ValidationResult(
            False,
            f"Understat identity match rate {rate:.2%} is below threshold {min_match_rate:.0%} (check reep subset).",
        )
    return ValidationResult(True, "")


def validate_sofascore_slice(
    competition_season: CompetitionSeason,
    *,
    min_rows: int | None = None,
    min_match_rate: float = 0.25,
) -> ValidationResult:
    min_rows = _configured_min_rows(min_rows)
    qs = SofascorePlayerSeasonSource.objects.filter(competition_season=competition_season)
    total = qs.count()
    if total < min_rows:
        return ValidationResult(
            False,
            f"Sofascore row count {total} is below minimum threshold {min_rows}.",
        )
    matched = qs.filter(canonical_player__isnull=False).count()
    rate = matched / total if total else 0.0
    if rate < min_match_rate:
        return ValidationResult(
            False,
            f"Sofascore identity match rate {rate:.2%} is below threshold {min_match_rate:.0%}.",
        )
    return ValidationResult(True, "")


def latest_success_run(competition_season: CompetitionSeason, kind: str) -> IngestionRun | None:
    return (
        IngestionRun.objects.filter(
            competition_season=competition_season,
            kind=kind,
            status=IngestionRunStatus.SUCCESS,
        )
        .order_by("-finished_at", "-id")
        .first()
    )


def can_merge_slice(competition_season: CompetitionSeason) -> ValidationResult:
    u = latest_success_run(competition_season, IngestionKind.UNDERSTAT)
    s = latest_success_run(competition_season, IngestionKind.SOFASCORE)
    if not u or not s:
        return ValidationResult(
            False,
            "Merge requires successful Understat and Sofascore ingestion runs for the same competition season.",
        )
    return ValidationResult(True, "")


def validate_sofascore_team_candidate(
    competition_season: CompetitionSeason,
    rows: list[dict],
) -> ValidationResult:
    total = len(rows)
    expected = competition_season.expected_team_count
    if total < expected:
        return ValidationResult(
            False,
            f"Sofascore team row count {total} is below expected threshold {expected}.",
        )
    coverage = sum(1 for row in rows if row.get("has_overall_stats"))
    if coverage < competition_season.min_team_stats_coverage_count:
        return ValidationResult(
            False,
            "Sofascore team overall-stat coverage "
            f"{coverage} is below threshold {competition_season.min_team_stats_coverage_count}.",
        )
    return ValidationResult(True, "")


def validate_sofascore_team_slice(competition_season: CompetitionSeason) -> ValidationResult:
    qs = SofascoreTeamSeasonSource.objects.filter(competition_season=competition_season)
    total = qs.count()
    expected = competition_season.expected_team_count
    if total < expected:
        return ValidationResult(
            False,
            f"Sofascore team row count {total} is below expected threshold {expected}.",
        )
    coverage = qs.filter(has_overall_stats=True).count()
    if coverage < competition_season.min_team_stats_coverage_count:
        return ValidationResult(
            False,
            "Sofascore team overall-stat coverage "
            f"{coverage} is below threshold {competition_season.min_team_stats_coverage_count}.",
        )
    return ValidationResult(True, "")


def validate_team_merge_candidate(
    competition_season: CompetitionSeason,
    rows: list[SofascoreTeamSeasonSource],
) -> ValidationResult:
    total = len(rows)
    if total < competition_season.min_merged_team_count:
        return ValidationResult(
            False,
            "Merged team row count "
            f"{total} is below threshold {competition_season.min_merged_team_count}.",
        )
    coverage = sum(1 for row in rows if row.has_overall_stats)
    if coverage < competition_season.min_team_stats_coverage_count:
        return ValidationResult(
            False,
            "Merged team overall-stat coverage "
            f"{coverage} is below threshold {competition_season.min_team_stats_coverage_count}.",
        )
    return ValidationResult(True, "")


def can_merge_team_slice(competition_season: CompetitionSeason) -> ValidationResult:
    s = latest_success_run(competition_season, IngestionKind.SOFASCORE_TEAM)
    if not s:
        return ValidationResult(
            False,
            "Team merge requires a successful Sofascore team ingestion run for the same competition season.",
        )
    return ValidationResult(True, "")
