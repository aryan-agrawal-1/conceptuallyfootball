from __future__ import annotations

from collections import defaultdict
from math import floor
from statistics import mean, pstdev

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from ingestion.api_cache import invalidate_materialized_api_payloads
from ingestion.derived_definitions import (
    CORE_METRIC_MIN_COVERAGE,
    ELIGIBLE_OUTFIELD_POSITIONS,
    FORMULA_VERSION,
    METRIC_DEFINITIONS,
    METRIC_FIELDS,
    MIN_ELIGIBLE_MINUTES,
    SCORE_COMPONENT_METRICS,
    SCORE_COMPONENT_MIN_COVERAGE,
    SCORE_DEFINITIONS,
    SCORE_FIELDS,
    SCORE_PENALTY_METRICS,
    STYLE_METRIC_MIN_COVERAGE,
    STYLE_PROXY_METRICS,
    WINSORIZE_LOWER,
    WINSORIZE_UPPER,
)
from ingestion.models import (
    CompetitionSeason,
    IngestionRun,
    IngestionRunStatus,
    MergedPlayerSeason,
    PlayerDataMode,
    PlayerSeasonDerivedStats,
    PositionGroup,
    SofascorePlayerSeasonSource,
)
from ingestion.services.gk_derived import materialize_gk_derived_stats

# Shrinkage prior for finishing score: shots / (shots + prior)
FINISHING_SHOT_PRIOR = 35.0
SOFASCORE_SOURCE_FIELDS = (
    "summary_goals",
    "summary_assists",
    "summary_expected_goals",
    "summary_expected_assists",
    "total_shots",
    "summary_successful_dribbles",
    "summary_accurate_passes_percentage",
    "tackles",
    "interceptions",
    "clearances",
    "error_lead_to_goal",
    "outfielder_blocks",
    "big_chances_created",
    "accurate_passes",
    "inaccurate_passes",
    "total_passes",
    "key_passes",
    "tackles_won",
    "tackles_won_percentage",
    "shots_on_target",
    "shots_off_target",
    "aerial_duels_won",
    "ground_duels_won",
    "ball_recoveries",
    "successful_dribbles_percentage",
    "fouls",
    "offsides",
    "accurate_passes_percentage",
    "accurate_crosses",
    "accurate_long_balls",
)


def _finishing_shrunk_delta_per_shot(
    goals_minus_npxg: float | None,
    shots: int | float | None,
) -> float | None:
    if goals_minus_npxg is None or shots is None or shots <= 0:
        return None
    s = float(shots)
    delta_per_shot = float(goals_minus_npxg) / s
    reliability = s / (s + FINISHING_SHOT_PRIOR)
    return delta_per_shot * reliability


def _sot_rate(
    sot: int | float | None,
    off: int | float | None,
    shots: int | float | None,
) -> float | None:
    """On-target share; fallback to on-target ÷ Understat shots when split is missing."""
    if sot is not None and off is not None:
        denom = float(sot) + float(off)
        if denom > 0:
            return float(sot) / denom
    if sot is not None and shots and shots > 0:
        return min(1.0, float(sot) / float(shots))
    return None


def _mark_run_start(run: IngestionRun) -> None:
    run.status = IngestionRunStatus.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])


def _mark_run_success(run: IngestionRun, stats: dict | None = None) -> None:
    run.status = IngestionRunStatus.SUCCESS
    run.finished_at = timezone.now()
    run.error_detail = ""
    if stats is not None:
        run.stats = stats
    run.save(update_fields=["status", "finished_at", "error_detail", "stats"])


def _mark_run_failed(run: IngestionRun, message: str) -> None:
    run.status = IngestionRunStatus.FAILED
    run.finished_at = timezone.now()
    run.error_detail = message[:8000]
    run.save(update_fields=["status", "finished_at", "error_detail"])


def _per90(total: int | float | None, minutes: int | None) -> float | None:
    if total is None or not minutes:
        return None
    if minutes <= 0:
        return None
    return float(total) * 90.0 / float(minutes)


def _ratio(numerator: int | float | None, denominator: int | float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def _available_sofascore_fields(competition_season: CompetitionSeason) -> set[str]:
    rows = SofascorePlayerSeasonSource.objects.filter(
        competition_season=competition_season,
        canonical_player__isnull=False,
    )
    counts = rows.aggregate(**{field: Count(field) for field in SOFASCORE_SOURCE_FIELDS})
    return {field for field, count in counts.items() if count}


def _source_count(
    value: int | float | None,
    source_field: str,
    available_fields: set[str],
) -> int | float | None:
    if source_field not in available_fields:
        return None
    return value if value is not None else 0


def _source_measure(
    value: int | float | None,
    source_field: str,
    available_fields: set[str],
) -> int | float | None:
    if source_field not in available_fields:
        return None
    return value


def _sum_required(*values: int | float | None) -> int | float | None:
    if any(value is None for value in values):
        return None
    return sum(float(value) for value in values)


def _quantile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("Cannot compute quantile of empty values.")
    if len(values) == 1:
        return values[0]
    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * q
    lower = floor(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def _winsorized_stats(values: list[float]) -> tuple[float, float]:
    lower = _quantile(values, WINSORIZE_LOWER)
    upper = _quantile(values, WINSORIZE_UPPER)
    clipped = [min(max(value, lower), upper) for value in values]
    return mean(clipped), pstdev(clipped)


def _winsorized_z_score(value: float, values: list[float]) -> float:
    lower = _quantile(values, WINSORIZE_LOWER)
    upper = _quantile(values, WINSORIZE_UPPER)
    clipped_value = min(max(value, lower), upper)
    avg, std = _winsorized_stats(values)
    if std == 0:
        return 0.0
    return (clipped_value - avg) / std


def _percentile_rank(value: float, values: list[float]) -> float:
    if not values:
        raise ValueError("Cannot compute percentile on empty values.")
    less = sum(1 for other in values if other < value)
    less_or_equal = sum(1 for other in values if other <= value)
    return ((less + less_or_equal) / 2.0) / len(values) * 100.0


def _eligibility(minutes: int | None, position_group: str) -> tuple[bool, str]:
    if position_group not in ELIGIBLE_OUTFIELD_POSITIONS:
        if position_group == PositionGroup.UNKNOWN:
            return False, "unknown_position_group"
        return False, "ineligible_position_group"
    if not minutes or minutes < MIN_ELIGIBLE_MINUTES:
        return False, "below_minutes_threshold"
    return True, ""


def _build_metric_row(
    merged: MergedPlayerSeason,
    sofascore: SofascorePlayerSeasonSource | None,
    sofascore_available_fields: set[str],
) -> dict[str, float | None]:
    minutes = merged.minutes
    sofascore_available_fields = sofascore_available_fields if sofascore is not None else set()
    blocks = _source_count(merged.ss_outfielder_blocks, "outfielder_blocks", sofascore_available_fields)
    tackles = _source_count(merged.ss_tackles, "tackles", sofascore_available_fields)
    interceptions = _source_count(merged.ss_interceptions, "interceptions", sofascore_available_fields)
    clearances = _source_count(merged.ss_clearances, "clearances", sofascore_available_fields)
    shots_on_target = _source_count(merged.ss_shots_on_target, "shots_on_target", sofascore_available_fields)
    shots_off_target = _source_count(merged.ss_shots_off_target, "shots_off_target", sofascore_available_fields)
    ss_total_shots = _source_count(merged.ss_total_shots, "total_shots", sofascore_available_fields)
    shots = merged.us_shots
    if shots is None:
        shots = ss_total_shots
    if shots is None and shots_on_target is not None and shots_off_target is not None:
        shots = shots_on_target + shots_off_target
    goals = (
        merged.us_goals
        if merged.us_goals is not None
        else _source_count(merged.ss_goals, "summary_goals", sofascore_available_fields)
    )
    assists = (
        merged.us_assists
        if merged.us_assists is not None
        else _source_count(merged.ss_assists, "summary_assists", sofascore_available_fields)
    )
    ss_key_passes = _source_count(merged.ss_key_passes, "key_passes", sofascore_available_fields)
    key_passes = merged.us_key_passes if merged.us_key_passes is not None else ss_key_passes
    xg = (
        merged.us_xg
        if merged.us_xg is not None
        else _source_measure(merged.ss_expected_goals, "summary_expected_goals", sofascore_available_fields)
    )
    xa = (
        merged.us_xa
        if merged.us_xa is not None
        else _source_measure(merged.ss_expected_assists, "summary_expected_assists", sofascore_available_fields)
    )
    big_chances_created = _source_count(
        merged.ss_big_chances_created,
        "big_chances_created",
        sofascore_available_fields,
    )
    successful_dribbles = _source_count(
        sofascore.summary_successful_dribbles if sofascore else None,
        "summary_successful_dribbles",
        sofascore_available_fields,
    )
    completed_passes = _source_count(merged.ss_accurate_passes, "accurate_passes", sofascore_available_fields)
    accurate_crosses = _source_count(merged.ss_accurate_crosses, "accurate_crosses", sofascore_available_fields)
    accurate_long_balls = _source_count(
        merged.ss_accurate_long_balls,
        "accurate_long_balls",
        sofascore_available_fields,
    )
    accurate_passes_total = _source_count(merged.ss_accurate_passes, "accurate_passes", sofascore_available_fields)
    inaccurate_passes = _source_count(
        merged.ss_inaccurate_passes,
        "inaccurate_passes",
        sofascore_available_fields,
    )
    total_passes = _source_count(merged.ss_total_passes, "total_passes", sofascore_available_fields)
    if total_passes is None and accurate_passes_total is not None and inaccurate_passes is not None:
        total_passes = accurate_passes_total + inaccurate_passes
    pass_accuracy = _source_measure(
        merged.ss_accurate_passes_percentage,
        "accurate_passes_percentage",
        sofascore_available_fields,
    )
    if pass_accuracy is None:
        pass_accuracy = _source_measure(
            sofascore.summary_accurate_passes_percentage if sofascore else None,
            "summary_accurate_passes_percentage",
            sofascore_available_fields,
        )
    if pass_accuracy is None:
        pass_accuracy_ratio = _ratio(accurate_passes_total, total_passes)
        pass_accuracy = None if pass_accuracy_ratio is None else pass_accuracy_ratio * 100.0

    tackles_won = _source_count(merged.ss_tackles_won, "tackles_won", sofascore_available_fields)
    tackles_won_percentage = _source_measure(
        merged.ss_tackles_won_percentage,
        "tackles_won_percentage",
        sofascore_available_fields,
    )
    if tackles_won_percentage is None:
        tackles_won_ratio = _ratio(tackles_won, tackles)
        tackles_won_percentage = None if tackles_won_ratio is None else tackles_won_ratio * 100.0
    aerial_duels_won = _source_count(merged.ss_aerial_duels_won, "aerial_duels_won", sofascore_available_fields)
    ground_duels_won = _source_count(merged.ss_ground_duels_won, "ground_duels_won", sofascore_available_fields)
    ball_recoveries = _source_count(merged.ss_ball_recoveries, "ball_recoveries", sofascore_available_fields)
    successful_dribbles_percentage = _source_measure(
        merged.ss_successful_dribbles_percentage,
        "successful_dribbles_percentage",
        sofascore_available_fields,
    )
    fouls = _source_count(merged.ss_fouls, "fouls", sofascore_available_fields)
    offsides = _source_count(merged.ss_offsides, "offsides", sofascore_available_fields)
    errors_lead_to_goal = _source_count(
        merged.ss_error_lead_to_goal,
        "error_lead_to_goal",
        sofascore_available_fields,
    )

    defensive_total = _sum_required(tackles, interceptions, clearances, blocks)
    chance_actions = _sum_required(shots, key_passes, big_chances_created)

    goals_minus_npxg_val = (
        None
        if merged.us_npg is None or merged.us_npxg is None
        else float(merged.us_npg) - float(merged.us_npxg)
    )

    return {
        "xg": xg,
        "xg_per_90": _per90(xg, minutes),
        "npxg": merged.us_npxg,
        "npxg_per_90": _per90(merged.us_npxg, minutes),
        "xa": xa,
        "xa_per_90": _per90(xa, minutes),
        "xgchain": merged.us_xgchain,
        "xgchain_per_90": _per90(merged.us_xgchain, minutes),
        "xgbuildup": merged.us_xgbuildup,
        "xgbuildup_per_90": _per90(merged.us_xgbuildup, minutes),
        "shots_per_90": _per90(shots, minutes),
        "goals_per_90": _per90(goals, minutes),
        "assists_per_90": _per90(assists, minutes),
        "key_passes_per_90": _per90(key_passes, minutes),
        "big_chances_created_per_90": _per90(big_chances_created, minutes),
        "successful_dribbles_per_90": _per90(successful_dribbles, minutes),
        "completed_passes_per_90": _per90(completed_passes, minutes),
        "goals_minus_xg": None
        if goals is None or xg is None
        else float(goals) - float(xg),
        "goals_minus_npxg": goals_minus_npxg_val,
        "finishing_shrunk_delta_per_shot": _finishing_shrunk_delta_per_shot(goals_minus_npxg_val, shots),
        "sot_rate": _sot_rate(shots_on_target, shots_off_target, shots),
        "npxg_per_shot": _ratio(merged.us_npxg, shots),
        "xa_per_key_pass": _ratio(xa, key_passes),
        "buildup_share": _ratio(merged.us_xgbuildup, merged.us_xgchain),
        "chance_involvement_per_90": _per90(chance_actions, minutes),
        "pass_accuracy": pass_accuracy,
        "tackles_per_90": _per90(tackles, minutes),
        "interceptions_per_90": _per90(interceptions, minutes),
        "clearances_per_90": _per90(clearances, minutes),
        "blocks_per_90": _per90(blocks, minutes),
        "defensive_action_density": _per90(defensive_total, minutes),
        "tackles_won": tackles_won,
        "tackles_won_percentage": tackles_won_percentage,
        "shots_on_target": shots_on_target,
        "shots_off_target": shots_off_target,
        "aerial_duels_won": aerial_duels_won,
        "ground_duels_won": ground_duels_won,
        "ball_recoveries": ball_recoveries,
        "successful_dribbles_percentage": successful_dribbles_percentage,
        "fouls": fouls,
        "offsides": offsides,
        "accurate_crosses_per_90": _per90(accurate_crosses, minutes),
        "accurate_long_balls_per_90": _per90(accurate_long_balls, minutes),
        "ball_recoveries_per_90": _per90(ball_recoveries, minutes),
        "ground_duels_won_per_90": _per90(ground_duels_won, minutes),
        "aerial_duels_won_per_90": _per90(aerial_duels_won, minutes),
        "fouls_per_90": _per90(fouls, minutes),
        "errors_lead_to_goal_per_90": _per90(errors_lead_to_goal, minutes),
        "offsides_per_90": _per90(offsides, minutes),
        "kp_share_per90": _ratio(ss_key_passes, total_passes),
        "inaccurate_pass_rate": _ratio(inaccurate_passes, total_passes),
    }


def _build_coverage_report(metric_rows: list[dict], eligible_player_ids: set[int]) -> dict[str, float]:
    if not eligible_player_ids:
        return {}
    eligible_rows = [row for row in metric_rows if row["canonical_player_id"] in eligible_player_ids]
    report: dict[str, float] = {}
    total = len(eligible_rows)
    for field_name in METRIC_FIELDS:
        populated = sum(1 for row in eligible_rows if row[field_name] is not None)
        report[field_name] = populated / total if total else 0.0
    return report


def _coverage_failures(coverage_report: dict[str, float]) -> list[str]:
    failures: list[str] = []
    for field_name, coverage in coverage_report.items():
        minimum = STYLE_METRIC_MIN_COVERAGE if field_name in STYLE_PROXY_METRICS else CORE_METRIC_MIN_COVERAGE
        if coverage < minimum:
            failures.append(
                f"{field_name} coverage {coverage:.1%} below required {minimum:.0%}"
            )
    return failures


def _metric_minimum_coverage(metric_name: str) -> float:
    return STYLE_METRIC_MIN_COVERAGE if metric_name in STYLE_PROXY_METRICS else CORE_METRIC_MIN_COVERAGE


def _metric_supported_by_slice(competition_season: CompetitionSeason, metric_name: str) -> bool:
    sources = set(METRIC_DEFINITIONS.get(metric_name, {}).get("sources_used") or [])
    if not sources:
        return True
    supported_sources = set()
    if competition_season.supports_understat:
        supported_sources.add("understat")
    if competition_season.supports_sofascore:
        supported_sources.add("sofascore")
    return bool(sources & supported_sources)


def _build_position_coverage_report(metric_rows: list[dict]) -> dict[str, dict[str, float]]:
    report: dict[str, dict[str, float]] = {}
    for position_group in ELIGIBLE_OUTFIELD_POSITIONS:
        rows = [
            row
            for row in metric_rows
            if row["position_group"] == position_group and row["percentiles_eligible"]
        ]
        total = len(rows)
        report[position_group] = {}
        for field_name in METRIC_FIELDS:
            populated = sum(1 for row in rows if row[field_name] is not None)
            report[position_group][field_name] = populated / total if total else 0.0
    return report


def _score_availability(
    position_coverage_report: dict[str, dict[str, float]],
) -> dict[str, dict]:
    scores: dict[str, dict] = {}
    for score_name, score_definition in SCORE_DEFINITIONS.items():
        positions: dict[str, bool] = {}
        missing_by_position: dict[str, list[str]] = {}
        low_coverage_by_position: dict[str, dict[str, float]] = {}

        for position_group in ELIGIBLE_OUTFIELD_POSITIONS:
            components = list(score_definition["positions"].get(position_group) or [])
            components.extend(score_definition.get("penalties", {}).get(position_group) or [])
            coverage = position_coverage_report.get(position_group, {})
            missing: list[str] = []
            low_coverage: dict[str, float] = {}

            for component in components:
                metric_name = component["metric"]
                metric_coverage = coverage.get(metric_name, 0.0)
                if metric_coverage <= 0.0:
                    missing.append(metric_name)
                elif metric_coverage < SCORE_COMPONENT_MIN_COVERAGE:
                    low_coverage[metric_name] = round(metric_coverage, 4)

            positions[position_group] = not missing and not low_coverage
            if missing:
                missing_by_position[position_group] = sorted(missing)
            if low_coverage:
                low_coverage_by_position[position_group] = dict(sorted(low_coverage.items()))

        scores[score_name] = {
            "available": any(positions.values()),
            "positions": positions,
            "missing_components": missing_by_position,
            "low_coverage_components": low_coverage_by_position,
        }
    return scores


def _slice_metric_availability(
    competition_season: CompetitionSeason,
    *,
    merged_rows: list[MergedPlayerSeason],
    eligible_player_ids: set[int],
    coverage_report: dict[str, float],
    position_coverage_report: dict[str, dict[str, float]],
) -> dict:
    available_metrics = sorted(
        metric_name
        for metric_name, coverage in coverage_report.items()
        if _metric_supported_by_slice(competition_season, metric_name) and coverage > 0.0
    )
    unavailable_metrics = sorted(
        metric_name
        for metric_name, coverage in coverage_report.items()
        if not _metric_supported_by_slice(competition_season, metric_name) or coverage <= 0.0
    )
    ui_available_metrics = sorted(
        metric_name
        for metric_name, coverage in coverage_report.items()
        if _metric_supported_by_slice(competition_season, metric_name)
        and coverage >= _metric_minimum_coverage(metric_name)
    )
    low_coverage_metrics = {
        metric_name: {
            "coverage": round(coverage, 4),
            "minimum": _metric_minimum_coverage(metric_name),
        }
        for metric_name, coverage in sorted(coverage_report.items())
        if _metric_supported_by_slice(competition_season, metric_name)
        and 0.0 < coverage < _metric_minimum_coverage(metric_name)
    }
    score_availability = _score_availability(position_coverage_report)
    return {
        "player_data_mode": competition_season.player_data_mode,
        "providers": {
            "understat": competition_season.supports_understat,
            "sofascore": competition_season.supports_sofascore,
        },
        "player_rows": {
            "merged_current": len(merged_rows),
            "eligible_outfield": len(eligible_player_ids),
        },
        "available_metrics": available_metrics,
        "ui_available_metrics": ui_available_metrics,
        "default_metrics": ui_available_metrics,
        "low_coverage_metrics": low_coverage_metrics,
        "unavailable_metrics": unavailable_metrics,
        "coverage": {key: round(value, 4) for key, value in coverage_report.items()},
        "coverage_by_position": {
            position: {key: round(value, 4) for key, value in coverage.items()}
            for position, coverage in position_coverage_report.items()
        },
        "metric_thresholds": {
            "core": CORE_METRIC_MIN_COVERAGE,
            "style": STYLE_METRIC_MIN_COVERAGE,
            "score_component": SCORE_COMPONENT_MIN_COVERAGE,
        },
        "scores": score_availability,
        "available_scores": sorted(
            score_name for score_name, payload in score_availability.items() if payload["available"]
        ),
        "unavailable_scores": sorted(
            score_name
            for score_name, payload in score_availability.items()
            if not payload["available"]
        ),
    }


def _metric_distribution_by_position(
    metric_rows: list[dict],
    metric_name: str,
) -> dict[str, list[float]]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in metric_rows:
        if not row["percentiles_eligible"]:
            continue
        value = row.get(metric_name)
        if value is None:
            continue
        buckets[row["position_group"]].append(float(value))
    return buckets


def _assign_metric_percentiles(metric_rows: list[dict]) -> None:
    for metric_name in METRIC_FIELDS:
        distributions = _metric_distribution_by_position(metric_rows, metric_name)
        percentile_key = f"{metric_name}_percentile"
        for row in metric_rows:
            row[percentile_key] = None
            if not row["percentiles_eligible"]:
                continue
            value = row.get(metric_name)
            values = distributions.get(row["position_group"]) or []
            if value is None or not values:
                continue
            row[percentile_key] = _percentile_rank(float(value), values)


def _score_distribution_input(metric_rows: list[dict], metric_name: str, position_group: str) -> list[float]:
    values: list[float] = []
    for row in metric_rows:
        if row["position_group"] != position_group or not row["scores_eligible"]:
            continue
        value = row.get(metric_name)
        if value is not None:
            values.append(float(value))
    return values


def _assign_score_raw_values(metric_rows: list[dict]) -> None:
    zscore_distributions: dict[tuple[str, str], list[float]] = {}
    score_metrics = sorted(set(SCORE_COMPONENT_METRICS + SCORE_PENALTY_METRICS))
    for position_group in ELIGIBLE_OUTFIELD_POSITIONS:
        for metric_name in score_metrics:
            values = _score_distribution_input(metric_rows, metric_name, position_group)
            if values:
                zscore_distributions[(position_group, metric_name)] = values

    for row in metric_rows:
        for score_name in SCORE_FIELDS:
            row[f"{score_name}_raw"] = None
            row[score_name] = None
        if not row["scores_eligible"]:
            continue

        for score_name, score_definition in SCORE_DEFINITIONS.items():
            components = score_definition["positions"].get(row["position_group"]) or []
            missing_component = False
            weighted_total = 0.0
            for component in components:
                metric_name = component["metric"]
                value = row.get(metric_name)
                distribution = zscore_distributions.get((row["position_group"], metric_name)) or []
                if value is None or not distribution:
                    missing_component = True
                    break
                weighted_total += _winsorized_z_score(float(value), distribution) * component["weight"]
            penalties = score_definition.get("penalties", {}).get(row["position_group"]) or []
            for penalty in penalties:
                metric_name = penalty["metric"]
                value = row.get(metric_name)
                distribution = zscore_distributions.get((row["position_group"], metric_name)) or []
                if value is None or not distribution:
                    missing_component = True
                    break
                weighted_total -= _winsorized_z_score(float(value), distribution) * penalty["weight"]
            if not missing_component:
                row[f"{score_name}_raw"] = weighted_total


def _assign_score_percentiles(metric_rows: list[dict]) -> None:
    for score_name in SCORE_FIELDS:
        raw_field = f"{score_name}_raw"
        distributions: dict[str, list[float]] = defaultdict(list)
        for row in metric_rows:
            if not row["scores_eligible"]:
                continue
            value = row.get(raw_field)
            if value is None:
                continue
            distributions[row["position_group"]].append(float(value))

        for row in metric_rows:
            row[score_name] = None
            if not row["scores_eligible"]:
                continue
            raw_value = row.get(raw_field)
            values = distributions.get(row["position_group"]) or []
            if raw_value is None or not values:
                continue
            row[score_name] = _percentile_rank(float(raw_value), values)


@transaction.atomic
def materialize_derived_stats(
    competition_season: CompetitionSeason,
    *,
    run: IngestionRun,
) -> None:
    _mark_run_start(run)
    try:
        merged_rows = list(
            MergedPlayerSeason.objects.filter(
                competition_season=competition_season,
                is_current=True,
            )
            .exclude(position_group=PositionGroup.GK)
            .select_related(
                "canonical_player",
                "canonical_display_team",
            )
            .order_by("canonical_player__display_name")
        )
        if not merged_rows:
            raise ValueError("No current merged outfield rows found for this season.")

        sofascore_sources = {
            row.canonical_player_id: row
            for row in SofascorePlayerSeasonSource.objects.filter(
                competition_season=competition_season,
                canonical_player__isnull=False,
            )
        }
        sofascore_available_fields = _available_sofascore_fields(competition_season)

        metric_rows: list[dict] = []
        eligible_player_ids: set[int] = set()
        for merged in merged_rows:
            percentiles_eligible, percentile_reason = _eligibility(merged.minutes, merged.position_group)
            scores_eligible, score_reason = _eligibility(merged.minutes, merged.position_group)
            if percentiles_eligible:
                eligible_player_ids.add(merged.canonical_player_id)

            row = {
                "competition_season": competition_season,
                "canonical_player": merged.canonical_player,
                "canonical_display_team": merged.canonical_display_team,
                "merged_player_season": merged,
                "derived_ingestion_run": run,
                "formula_version": FORMULA_VERSION,
                "position_group": merged.position_group,
                "native_position": merged.native_position,
                "minutes": merged.minutes,
                "percentiles_eligible": percentiles_eligible,
                "percentiles_ineligibility_reason": percentile_reason,
                "scores_eligible": scores_eligible,
                "scores_ineligibility_reason": score_reason,
                "canonical_player_id": merged.canonical_player_id,
            }
            row.update(
                _build_metric_row(
                    merged,
                    sofascore_sources.get(merged.canonical_player_id),
                    sofascore_available_fields,
                )
            )
            metric_rows.append(row)

        coverage_report = _build_coverage_report(metric_rows, eligible_player_ids)
        position_coverage_report = _build_position_coverage_report(metric_rows)
        coverage_warnings = (
            _coverage_failures(coverage_report)
            if competition_season.player_data_mode == PlayerDataMode.FULL_MERGE
            else []
        )
        _assign_metric_percentiles(metric_rows)
        _assign_score_raw_values(metric_rows)
        _assign_score_percentiles(metric_rows)

        PlayerSeasonDerivedStats.objects.filter(
            competition_season=competition_season,
            is_current=True,
        ).update(is_current=False, superseded_at=timezone.now())

        to_create = []
        for row in metric_rows:
            payload = {key: row.get(key) for key in row.keys() if key != "canonical_player_id"}
            to_create.append(PlayerSeasonDerivedStats(**payload, is_current=True))
        PlayerSeasonDerivedStats.objects.bulk_create(to_create)
        gk_derived_rows = materialize_gk_derived_stats(competition_season, derived_run=run)
        metric_availability = _slice_metric_availability(
            competition_season,
            merged_rows=merged_rows,
            eligible_player_ids=eligible_player_ids,
            coverage_report=coverage_report,
            position_coverage_report=position_coverage_report,
        )
        if coverage_warnings:
            metric_availability["coverage_warnings"] = coverage_warnings
        competition_season.metric_availability = metric_availability
        competition_season.save(update_fields=["metric_availability"])
        invalidate_materialized_api_payloads()
    except Exception as exc:  # noqa: BLE001
        _mark_run_failed(run, str(exc))
        return

    _mark_run_success(
        run,
        stats={
            "formula_version": FORMULA_VERSION,
            "minimum_eligible_minutes": MIN_ELIGIBLE_MINUTES,
            "derived_rows": len(metric_rows),
            "eligible_rows": len(eligible_player_ids),
            "coverage": {key: round(value, 4) for key, value in coverage_report.items()},
            "coverage_warnings": coverage_warnings,
            "gk_derived_rows": gk_derived_rows,
        },
    )
