from __future__ import annotations

from dataclasses import asdict, dataclass

from django.db import transaction

from ingestion.models import CompetitionSeason
from ingestion.services.orchestration import validate_refresh_selection
from ingestion.services.publication import publication_readiness


@dataclass(frozen=True)
class RefreshCutoverPlan:
    from_season: str
    to_season: str
    pilot_competition: str
    source_ids: tuple[int, ...]
    source_competitions: tuple[str, ...]
    target_ids: tuple[int, ...]
    target_competitions: tuple[str, ...]
    preserved_ids: tuple[int, ...]
    preserved_competitions: tuple[str, ...]
    preserved_season_labels: tuple[str, ...]
    expected_refresh_ids: tuple[int, ...]
    pilot_target_id: int
    pilot_published: bool
    applied: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _build_plan(
    *,
    from_season: str,
    to_season: str,
    pilot_competition: str,
    lock_rows: bool = False,
) -> RefreshCutoverPlan:
    if from_season == to_season:
        raise ValueError("--from-season and --to-season must be different seasons.")

    enabled_queryset = CompetitionSeason.objects.filter(refresh_enabled=True).select_related(
        "competition",
        "season",
    )
    if lock_rows:
        enabled_queryset = enabled_queryset.select_for_update()
    enabled_rows = list(
        enabled_queryset.order_by("competition__short_code", "competition_id", "id")
    )
    source_rows = [row for row in enabled_rows if row.season.label == from_season]
    if not source_rows:
        raise ValueError(f"No refresh-enabled source slices found for {from_season}.")

    targets: list[CompetitionSeason] = []
    for source_row in source_rows:
        target_queryset = CompetitionSeason.objects.filter(
            competition_id=source_row.competition_id,
            season__label=to_season,
            is_active=True,
        ).select_related("competition", "season")
        if lock_rows:
            target_queryset = target_queryset.select_for_update()
        target_rows = list(target_queryset.order_by("id"))
        if len(target_rows) != 1:
            raise ValueError(
                "Expected exactly one active target slice for "
                f"{source_row.competition.short_code} {to_season}; found {len(target_rows)}."
            )
        target = target_rows[0]
        if not target.supports_sofascore:
            raise ValueError(f"Target {target} is missing configured Sofascore provider IDs.")
        targets.append(target)

    source_codes = tuple(row.competition.short_code for row in source_rows)
    target_codes = tuple(target.competition.short_code for target in targets)
    pilot_matches = [
        target
        for target in targets
        if target.competition.short_code.upper() == pilot_competition.upper()
    ]
    if len(pilot_matches) != 1:
        raise ValueError(
            f"Pilot competition {pilot_competition} must identify exactly one transitioning target; "
            f"available targets are {list(target_codes)}."
        )
    pilot_target = pilot_matches[0]
    readiness = publication_readiness(pilot_target)
    if not readiness.ready:
        raise ValueError(f"Pilot target {pilot_target} is not ready: {readiness.reason}")

    source_ids = {row.id for row in source_rows}
    preserved_rows = [row for row in enabled_rows if row.id not in source_ids]
    resulting_rows = [*preserved_rows, *targets]
    resulting_rows.sort(
        key=lambda row: (row.competition.short_code, row.competition_id, row.id),
    )
    validate_refresh_selection(resulting_rows)
    expected_refresh_ids = tuple(sorted({row.id for row in preserved_rows} | {row.id for row in targets}))
    return RefreshCutoverPlan(
        from_season=from_season,
        to_season=to_season,
        pilot_competition=pilot_competition.upper(),
        source_ids=tuple(row.id for row in source_rows),
        source_competitions=source_codes,
        target_ids=tuple(row.id for row in targets),
        target_competitions=target_codes,
        preserved_ids=tuple(row.id for row in preserved_rows),
        preserved_competitions=tuple(row.competition.short_code for row in preserved_rows),
        preserved_season_labels=tuple(row.season.label for row in preserved_rows),
        expected_refresh_ids=expected_refresh_ids,
        pilot_target_id=pilot_target.id,
        pilot_published=pilot_target.is_published,
    )


def plan_season_refresh_cutover(
    *,
    from_season: str = "2025-26",
    to_season: str = "2026-27",
    pilot_competition: str = "ENG1",
) -> RefreshCutoverPlan:
    return _build_plan(
        from_season=from_season,
        to_season=to_season,
        pilot_competition=pilot_competition,
    )


@transaction.atomic
def apply_season_refresh_cutover(
    *,
    from_season: str = "2025-26",
    to_season: str = "2026-27",
    pilot_competition: str = "ENG1",
) -> RefreshCutoverPlan:
    plan = _build_plan(
        from_season=from_season,
        to_season=to_season,
        pilot_competition=pilot_competition,
        lock_rows=True,
    )
    CompetitionSeason.objects.filter(pk__in=plan.source_ids).update(refresh_enabled=False)
    CompetitionSeason.objects.filter(pk__in=plan.target_ids).update(refresh_enabled=True)
    resulting_refresh_rows = list(
        CompetitionSeason.objects.select_related("competition", "season")
        .filter(refresh_enabled=True)
        .order_by("competition__short_code", "competition_id", "id")
    )
    validate_refresh_selection(resulting_refresh_rows)
    resulting_ids = {row.id for row in resulting_refresh_rows}
    if resulting_ids != set(plan.expected_refresh_ids):
        raise ValueError(
            "Applied refresh selection does not match the planned target/preserved IDs: "
            f"expected {list(plan.expected_refresh_ids)}, found {sorted(resulting_ids)}."
        )
    return RefreshCutoverPlan(**{**plan.as_dict(), "applied": True})
