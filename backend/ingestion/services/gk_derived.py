from __future__ import annotations

from django.utils import timezone

from ingestion.derived_definitions import MIN_ELIGIBLE_MINUTES
from ingestion.gk_definitions import FORMULA_VERSION_GK, GK_METRICS_WITH_PERCENTILE
from ingestion.models import (
    CompetitionSeason,
    IngestionRun,
    MergedPlayerSeason,
    PlayerSeasonGkDerivedStats,
    PositionGroup,
)


def _per90(total: int | float | None, minutes: int | None) -> float | None:
    if total is None or not minutes:
        return None
    if minutes <= 0:
        return None
    return float(total) * 90.0 / float(minutes)


def _percentile_rank(value: float, values: list[float]) -> float:
    if not values:
        raise ValueError("Cannot compute percentile on empty values.")
    less = sum(1 for other in values if other < value)
    less_or_equal = sum(1 for other in values if other <= value)
    return ((less + less_or_equal) / 2.0) / len(values) * 100.0


def _gk_eligibility(minutes: int | None) -> tuple[bool, str]:
    if not minutes or minutes < MIN_ELIGIBLE_MINUTES:
        return False, "below_minutes_threshold"
    return True, ""


def _build_gk_metric_row(merged: MergedPlayerSeason) -> dict[str, float | int | None]:
    minutes = merged.minutes
    apps = merged.ss_appearances
    saves = merged.ss_saves
    cs = merged.ss_clean_sheet
    ps = merged.ss_penalty_save
    sib = merged.ss_saved_shots_from_inside_the_box
    ro = merged.ss_runs_out

    cs_rate = None
    if apps and apps > 0 and cs is not None:
        cs_rate = float(cs) * 100.0 / float(apps)

    return {
        "rating": merged.ss_rating,
        "saves": saves,
        "saves_per_90": _per90(saves, minutes),
        "clean_sheets": cs,
        "clean_sheet_rate": cs_rate,
        "penalty_saves": ps,
        "saved_shots_inside_box": sib,
        "saved_shots_inside_box_per_90": _per90(sib, minutes),
        "runs_out": ro,
        "runs_out_per_90": _per90(ro, minutes),
        "pass_accuracy": merged.ss_accurate_passes_percentage,
        "completed_passes_per_90": _per90(merged.ss_accurate_passes, minutes),
        "accurate_long_balls_per_90": _per90(merged.ss_accurate_long_balls, minutes),
        "appearances": apps,
    }


def _assign_gk_percentiles(metric_rows: list[dict]) -> None:
    for metric_name in GK_METRICS_WITH_PERCENTILE:
        values: list[float] = []
        for row in metric_rows:
            if not row["percentiles_eligible"]:
                continue
            v = row.get(metric_name)
            if v is None:
                continue
            values.append(float(v))
        pct_key = f"{metric_name}_percentile"
        for row in metric_rows:
            row[pct_key] = None
            if not row["percentiles_eligible"]:
                continue
            v = row.get(metric_name)
            if v is None or not values:
                continue
            row[pct_key] = _percentile_rank(float(v), values)


def materialize_gk_derived_stats(competition_season: CompetitionSeason, *, derived_run: IngestionRun) -> int:
    """
    Persist goalkeeper matrix rows. Caller must run inside the same transaction as outfield derived
    (see materialize_derived_stats) so both succeed or roll back together.
    """
    gk_merged = list(
        MergedPlayerSeason.objects.filter(
            competition_season=competition_season,
            is_current=True,
            position_group=PositionGroup.GK,
        ).select_related(
            "canonical_player",
            "canonical_display_team",
        )
    )

    PlayerSeasonGkDerivedStats.objects.filter(
        competition_season=competition_season,
        is_current=True,
    ).update(is_current=False, superseded_at=timezone.now())

    if not gk_merged:
        return 0

    metric_rows: list[dict] = []
    for merged in gk_merged:
        pe, pr = _gk_eligibility(merged.minutes)
        base: dict = {
            "competition_season": competition_season,
            "canonical_player": merged.canonical_player,
            "canonical_display_team": merged.canonical_display_team,
            "merged_player_season": merged,
            "derived_ingestion_run": derived_run,
            "formula_version": FORMULA_VERSION_GK,
            "minutes": merged.minutes,
            "percentiles_eligible": pe,
            "percentiles_ineligibility_reason": pr,
        }
        base.update(_build_gk_metric_row(merged))
        metric_rows.append(base)

    _assign_gk_percentiles(metric_rows)

    to_create = []
    for row in metric_rows:
        payload = {k: v for k, v in row.items()}
        to_create.append(PlayerSeasonGkDerivedStats(**payload, is_current=True))
    PlayerSeasonGkDerivedStats.objects.bulk_create(to_create)
    return len(to_create)
