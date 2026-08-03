from __future__ import annotations

from dataclasses import asdict, dataclass

from django.db import transaction

from ingestion.models import CompetitionSeason
from ingestion.services.orchestration import validate_refresh_selection
from ingestion.services.publication import publication_readiness
from ingestion.services.season_labels import canonical_season_label


@dataclass(frozen=True)
class RefreshActivationPlan:
    competition: str
    requested_season: str
    target_season: str
    target_id: int
    before_ids: tuple[int, ...]
    after_ids: tuple[int, ...]
    disabled_ids: tuple[int, ...]
    applied: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _build_plan(
    competition: str,
    season: str,
    *,
    lock_rows: bool = False,
) -> RefreshActivationPlan:
    code = competition.strip().upper()
    canonical_label = canonical_season_label(code, season)

    # Lock the global enabled set before the target, matching cutover's lock
    # order. This avoids an activation/cutover deadlock and makes the promised
    # preservation set stable for the whole transaction.
    before_queryset = CompetitionSeason.objects.select_related(
        "competition",
        "season",
    ).filter(refresh_enabled=True)
    if lock_rows:
        before_queryset = before_queryset.select_for_update()
    before_rows = list(
        before_queryset.order_by("competition__short_code", "competition_id", "id")
    )

    target_queryset = CompetitionSeason.objects.filter(
        competition__short_code__iexact=code,
        season__label__iexact=canonical_label,
        is_active=True,
    ).select_related("competition", "season")
    if lock_rows:
        target_queryset = target_queryset.select_for_update()
    targets = list(target_queryset.order_by("id"))
    if len(targets) != 1:
        raise ValueError(
            f"Expected exactly one active target for {code} {canonical_label}; found {len(targets)}."
        )
    target = targets[0]
    if not target.supports_sofascore:
        raise ValueError(f"Target {target} is missing configured Sofascore provider IDs.")
    if not target.is_published:
        raise ValueError(f"Target {target} must be published before refresh activation.")
    readiness = publication_readiness(target)
    if not readiness.ready:
        raise ValueError(f"Target {target} is not ready: {readiness.reason}")

    before_competition_rows = [
        row for row in before_rows if row.competition_id == target.competition_id
    ]
    before_ids = tuple(row.id for row in before_rows)
    after_rows = [row for row in before_rows if row.competition_id != target.competition_id]
    after_rows.append(target)
    after_rows.sort(key=lambda row: (row.competition.short_code, row.competition_id, row.id))
    validate_refresh_selection(after_rows)
    disabled_ids = tuple(row.id for row in before_competition_rows if row.id != target.id)
    return RefreshActivationPlan(
        competition=code,
        requested_season=season,
        target_season=target.season.label,
        target_id=target.id,
        before_ids=before_ids,
        after_ids=tuple(row.id for row in after_rows),
        disabled_ids=disabled_ids,
    )


def plan_season_refresh_activation(competition: str, season: str) -> RefreshActivationPlan:
    return _build_plan(competition, season)


@transaction.atomic
def apply_season_refresh_activation(competition: str, season: str) -> RefreshActivationPlan:
    plan = _build_plan(competition, season, lock_rows=True)
    target = CompetitionSeason.objects.select_for_update().get(pk=plan.target_id)
    CompetitionSeason.objects.filter(
        competition_id=target.competition_id,
        refresh_enabled=True,
    ).exclude(pk=target.pk).update(refresh_enabled=False)
    target.refresh_enabled = True
    target.save(update_fields=["refresh_enabled"])
    resulting_rows = list(
        CompetitionSeason.objects.select_related("competition", "season")
        .filter(refresh_enabled=True)
        .order_by("competition__short_code", "competition_id", "id")
    )
    validate_refresh_selection(resulting_rows)
    resulting_ids = tuple(row.id for row in resulting_rows)
    if set(resulting_ids) != set(plan.after_ids):
        raise ValueError(
            "Applied refresh selection does not match the planned activation: "
            f"expected {list(plan.after_ids)}, found {list(resulting_ids)}."
        )
    return RefreshActivationPlan(**{**plan.as_dict(), "applied": True})
