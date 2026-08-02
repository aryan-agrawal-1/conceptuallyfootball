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

    source_queryset = CompetitionSeason.objects.filter(refresh_enabled=True).select_related(
        "competition",
        "season",
    )
    if lock_rows:
        source_queryset = source_queryset.select_for_update()
    source_rows = list(source_queryset.order_by("competition__short_code", "competition_id", "id"))
    if not source_rows:
        raise ValueError("No refresh-enabled source slices were found.")

    source_seasons = {row.season.label for row in source_rows}
    if source_seasons != {from_season}:
        raise ValueError(
            "All refresh-enabled source slices must share --from-season "
            f"{from_season}; found {sorted(source_seasons)}."
        )

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
            raise ValueError(
                f"Target {target} is missing configured Sofascore provider IDs."
            )
        targets.append(target)

    target_codes = tuple(target.competition.short_code for target in targets)
    pilot_matches = [
        target
        for target in targets
        if target.competition.short_code.upper() == pilot_competition.upper()
    ]
    if len(pilot_matches) != 1:
        raise ValueError(
            f"Pilot competition {pilot_competition} must identify exactly one source target; "
            f"available targets are {list(target_codes)}."
        )
    pilot_target = pilot_matches[0]
    readiness = publication_readiness(pilot_target)
    if not readiness.ready:
        raise ValueError(
            f"Pilot target {pilot_target} is not ready: {readiness.reason}"
        )

    # Keep the tuples deterministic even if a caller supplied a queryset with
    # an unusual default ordering.
    ordered_pairs = sorted(
        zip(source_rows, targets),
        key=lambda pair: (pair[0].competition.short_code, pair[0].competition_id, pair[0].id),
    )
    ordered_sources, ordered_targets = zip(*ordered_pairs)
    return RefreshCutoverPlan(
        from_season=from_season,
        to_season=to_season,
        pilot_competition=pilot_competition.upper(),
        source_ids=tuple(row.id for row in ordered_sources),
        source_competitions=tuple(row.competition.short_code for row in ordered_sources),
        target_ids=tuple(row.id for row in ordered_targets),
        target_competitions=tuple(row.competition.short_code for row in ordered_targets),
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
    resulting_ids = tuple(row.id for row in resulting_refresh_rows)
    if resulting_ids != plan.target_ids:
        raise ValueError(
            "Applied refresh selection does not match the planned target IDs: "
            f"expected {list(plan.target_ids)}, found {list(resulting_ids)}."
        )
    return RefreshCutoverPlan(**{**plan.as_dict(), "applied": True})
