#!/usr/bin/env python3
"""
Temporary league ingestion runner + coverage reporter.

Run from the backend directory:

    python run_league_ingestion_coverage.py

or from repo root:

    backend/venv/bin/python backend/run_league_ingestion_coverage.py

What it does:
- Seeds configured competition-season slices from the manifest.
- Runs player provider ingestion for every active configured slice.
- Runs merge + derived stats materialization.
- Writes a JSON report focused on thin / failed slices.

Notes:
- This intentionally does not materialize galaxy embeddings; coverage only needs
  provider ingestion, player merge, and derived stats.
- The script continues after slice failures so one bad provider/season does not
  block the full league report.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
sys.path.insert(0, str(BASE_DIR))


import django  # noqa: E402

django.setup()


from django.conf import settings  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.utils import timezone  # noqa: E402

from ingestion.derived_definitions import (  # noqa: E402
    CORE_METRIC_MIN_COVERAGE,
    METRIC_DEFINITIONS,
    SCORE_COMPONENT_METRICS,
    SCORE_COMPONENT_MIN_COVERAGE,
    SCORE_PENALTY_METRICS,
    STYLE_METRIC_MIN_COVERAGE,
    STYLE_PROXY_METRICS,
)
from ingestion.models import (  # noqa: E402
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    IngestionRunStatus,
    PlayerDataMode,
)
from ingestion.services.derived import materialize_derived_stats  # noqa: E402
from ingestion.services.ingest import (  # noqa: E402
    ingest_sofascore_slice,
    ingest_understat_slice,
    run_merge_job,
)


DEFAULT_OUTPUT_PATH = BASE_DIR / "league_ingestion_coverage_report.json"
SOFASCORE_ONLY_MIN_ELIGIBLE_OUTFIELD = 25
FULL_MERGE_MIN_ELIGIBLE_OUTFIELD = 100


@dataclass
class StepResult:
    kind: str
    status: str
    run_id: int | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    error_detail: str = ""


@dataclass
class SliceReport:
    competition_season_id: int
    competition: str
    season: str
    player_data_mode: str
    steps: list[StepResult] = field(default_factory=list)
    metric_availability: dict[str, Any] = field(default_factory=dict)
    thin_reasons: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.competition} {self.season}"

    @property
    def is_thin(self) -> bool:
        return bool(self.thin_reasons)


def create_run(kind: str, competition_season: CompetitionSeason) -> IngestionRun:
    return IngestionRun.objects.create(
        kind=kind,
        competition_season=competition_season,
        status=IngestionRunStatus.PENDING,
    )


def run_step(
    *,
    kind: str,
    competition_season: CompetitionSeason,
    fn,
) -> StepResult:
    run = create_run(kind, competition_season)
    try:
        fn(competition_season, run=run)
    except Exception as exc:  # noqa: BLE001
        run.refresh_from_db()
        if run.status != IngestionRunStatus.FAILED:
            run.status = IngestionRunStatus.FAILED
            run.finished_at = timezone.now()
            run.error_detail = f"{exc}\n\n{traceback.format_exc()}"[:8000]
            run.save(update_fields=["status", "finished_at", "error_detail"])
    run.refresh_from_db()
    return StepResult(
        kind=kind,
        status=run.status,
        run_id=run.id,
        stats=run.stats or {},
        error_detail=run.error_detail or "",
    )


def last_success_stats(competition_season: CompetitionSeason, kind: str) -> dict[str, Any]:
    run = (
        IngestionRun.objects.filter(
            competition_season=competition_season,
            kind=kind,
            status=IngestionRunStatus.SUCCESS,
        )
        .order_by("-finished_at", "-id")
        .first()
    )
    return run.stats if run and isinstance(run.stats, dict) else {}


def is_metric_relevant_for_mode(metric_name: str, player_data_mode: str) -> bool:
    if player_data_mode == PlayerDataMode.FULL_MERGE:
        return True

    definition = METRIC_DEFINITIONS.get(metric_name, {})
    sources = set(definition.get("sources_used") or [])

    if not sources:
        return True

    if sources == {"understat"}:
        return False

    intentionally_skipped_sofascore_only = {
        # current formula depends on Understat shots/key passes even though it also uses Sofascore big-chance data.
        "chance_involvement_per_90",
    }
    if metric_name in intentionally_skipped_sofascore_only:
        return False

    return "sofascore" in sources


def minimum_coverage_for_metric(metric_name: str) -> float:
    if metric_name in SCORE_COMPONENT_METRICS or metric_name in SCORE_PENALTY_METRICS:
        return SCORE_COMPONENT_MIN_COVERAGE
    if metric_name in STYLE_PROXY_METRICS:
        return STYLE_METRIC_MIN_COVERAGE
    return CORE_METRIC_MIN_COVERAGE


def coverage_failures(metric_availability: dict[str, Any], player_data_mode: str) -> list[str]:
    failures: list[str] = []
    coverage = metric_availability.get("coverage") or {}
    if not isinstance(coverage, dict):
        return ["missing coverage map"]

    for metric_name, raw_coverage in sorted(coverage.items()):
        if not is_metric_relevant_for_mode(metric_name, player_data_mode):
            continue

        try:
            metric_coverage = float(raw_coverage)
        except (TypeError, ValueError):
            failures.append(f"{metric_name} coverage is not numeric: {raw_coverage!r}")
            continue

        minimum = minimum_coverage_for_metric(metric_name)
        if metric_coverage < minimum:
            failures.append(
                f"{metric_name} coverage {metric_coverage:.1%} below {minimum:.0%}"
            )

    return failures


def analyze_slice(report: SliceReport) -> None:
    failed_steps = [step for step in report.steps if step.status != IngestionRunStatus.SUCCESS]
    for step in failed_steps:
        detail = f": {step.error_detail}" if step.error_detail else ""
        report.thin_reasons.append(f"{step.kind} {step.status}{detail}")

    availability = report.metric_availability or {}
    player_rows = availability.get("player_rows") or {}

    merged_current = player_rows.get("merged_current")
    eligible_outfield = player_rows.get("eligible_outfield")

    if merged_current in (None, 0):
        report.thin_reasons.append("no current merged player rows")
    elif isinstance(merged_current, int) and merged_current < 200:
        report.thin_reasons.append(f"low merged row count: {merged_current}")

    min_eligible = (
        FULL_MERGE_MIN_ELIGIBLE_OUTFIELD
        if report.player_data_mode == PlayerDataMode.FULL_MERGE
        else SOFASCORE_ONLY_MIN_ELIGIBLE_OUTFIELD
    )
    if eligible_outfield in (None, 0):
        report.thin_reasons.append("no eligible outfield rows")
    elif isinstance(eligible_outfield, int) and eligible_outfield < min_eligible:
        report.thin_reasons.append(
            f"low eligible outfield count: {eligible_outfield} below {min_eligible}"
        )

    report.thin_reasons.extend(
        coverage_failures(availability, report.player_data_mode)
    )

    deduped: list[str] = []
    seen: set[str] = set()
    for reason in report.thin_reasons:
        if reason in seen:
            continue
        seen.add(reason)
        deduped.append(reason)
    report.thin_reasons = deduped


def should_run_provider(
    *,
    competition_season: CompetitionSeason,
    kind: str,
    force: bool,
) -> bool:
    if force:
        return True
    return not IngestionRun.objects.filter(
        competition_season=competition_season,
        kind=kind,
        status=IngestionRunStatus.SUCCESS,
    ).exists()


def run_slice(
    competition_season: CompetitionSeason,
    *,
    force: bool,
    providers_only: bool,
) -> SliceReport:
    report = SliceReport(
        competition_season_id=competition_season.id,
        competition=competition_season.competition.short_code,
        season=competition_season.season.label,
        player_data_mode=competition_season.player_data_mode,
    )

    print(f"\n=== {report.key} [{report.player_data_mode}] ===", flush=True)

    if competition_season.supports_understat:
        if should_run_provider(
            competition_season=competition_season,
            kind=IngestionKind.UNDERSTAT,
            force=force,
        ):
            print("Running Understat ingestion...", flush=True)
            report.steps.append(
                run_step(
                    kind=IngestionKind.UNDERSTAT,
                    competition_season=competition_season,
                    fn=ingest_understat_slice,
                )
            )
        else:
            stats = last_success_stats(competition_season, IngestionKind.UNDERSTAT)
            print("Skipping Understat ingestion; existing success found.", flush=True)
            report.steps.append(
                StepResult(
                    kind=IngestionKind.UNDERSTAT,
                    status=IngestionRunStatus.SUCCESS,
                    stats=stats,
                )
            )

    if competition_season.supports_sofascore:
        if should_run_provider(
            competition_season=competition_season,
            kind=IngestionKind.SOFASCORE,
            force=force,
        ):
            print("Running Sofascore ingestion...", flush=True)
            report.steps.append(
                run_step(
                    kind=IngestionKind.SOFASCORE,
                    competition_season=competition_season,
                    fn=ingest_sofascore_slice,
                )
            )
        else:
            stats = last_success_stats(competition_season, IngestionKind.SOFASCORE)
            print("Skipping Sofascore ingestion; existing success found.", flush=True)
            report.steps.append(
                StepResult(
                    kind=IngestionKind.SOFASCORE,
                    status=IngestionRunStatus.SUCCESS,
                    stats=stats,
                )
            )

    provider_failed = any(
        step.status != IngestionRunStatus.SUCCESS
        for step in report.steps
        if step.kind in {IngestionKind.UNDERSTAT, IngestionKind.SOFASCORE}
    )

    if not providers_only and not provider_failed:
        print("Running player merge...", flush=True)
        report.steps.append(
            run_step(
                kind=IngestionKind.MERGE,
                competition_season=competition_season,
                fn=run_merge_job,
            )
        )

        merge_failed = report.steps[-1].status != IngestionRunStatus.SUCCESS
        if not merge_failed:
            print("Running derived stats materialization...", flush=True)
            report.steps.append(
                run_step(
                    kind=IngestionKind.DERIVED,
                    competition_season=competition_season,
                    fn=materialize_derived_stats,
                )
            )

    competition_season.refresh_from_db()
    report.metric_availability = competition_season.metric_availability or {}
    analyze_slice(report)

    if report.is_thin:
        print(f"Thin / failed: {report.key}", flush=True)
        for reason in report.thin_reasons:
            print(f"  - {reason}", flush=True)
    else:
        print(f"Healthy coverage: {report.key}", flush=True)

    return report


def parse_csv_filter(value: str | None) -> set[str] | None:
    if not value:
        return None
    return {part.strip().upper() for part in value.split(",") if part.strip()}


def serialize_step(step: StepResult) -> dict[str, Any]:
    return {
        "kind": step.kind,
        "status": step.status,
        "run_id": step.run_id,
        "stats": step.stats,
        "error_detail": step.error_detail,
    }


def serialize_slice(report: SliceReport) -> dict[str, Any]:
    return {
        "competition_season_id": report.competition_season_id,
        "competition": report.competition,
        "season": report.season,
        "player_data_mode": report.player_data_mode,
        "steps": [serialize_step(step) for step in report.steps],
        "metric_availability": report.metric_availability,
        "thin_reasons": report.thin_reasons,
    }


def build_queryset(
    *,
    competitions: set[str] | None,
    seasons: set[str] | None,
):
    qs = (
        CompetitionSeason.objects.filter(is_active=True)
        .select_related("competition", "season")
        .order_by("competition__short_code", "season__sort_order", "id")
    )

    if competitions:
        qs = qs.filter(competition__short_code__in=competitions)

    if seasons:
        qs = qs.filter(season__label__in=seasons)

    return qs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run league ingestion and write a thin-slice coverage report."
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help=f"JSON output path. Default: {DEFAULT_OUTPUT_PATH}",
    )
    parser.add_argument(
        "--competitions",
        default="",
        help="Comma-separated competition codes to run, e.g. ENG1,ITA1. Default: all active.",
    )
    parser.add_argument(
        "--seasons",
        default="",
        help="Comma-separated season labels to run, e.g. 2024-25,2025-26. Default: all active.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run provider ingestion even when a previous successful run exists.",
    )
    parser.add_argument(
        "--providers-only",
        action="store_true",
        help="Only run provider ingestion; skip merge and derived materialization.",
    )
    parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Do not run seed_competition_slices before ingestion.",
    )
    args = parser.parse_args()

    if not args.skip_seed:
        print("Seeding competition slices from manifest...", flush=True)
        call_command("seed_competition_slices")

    competitions = parse_csv_filter(args.competitions)
    seasons = parse_csv_filter(args.seasons)

    reports: list[SliceReport] = []
    qs = build_queryset(competitions=competitions, seasons=seasons)
    total = qs.count()

    print(f"Found {total} active slices to process.", flush=True)

    previous_competition_code = ""
    slice_sleep_seconds = float(
        getattr(settings, "STATBALLER_BATCH_SLICE_SLEEP_SECONDS", 20.0)
    )
    league_sleep_seconds = float(
        getattr(settings, "STATBALLER_BATCH_LEAGUE_SLEEP_SECONDS", 120.0)
    )

    for index, competition_season in enumerate(qs, start=1):
        current_competition_code = competition_season.competition.short_code
        if index > 1:
            is_new_league = previous_competition_code != current_competition_code
            sleep_seconds = league_sleep_seconds if is_new_league else slice_sleep_seconds
            if sleep_seconds > 0:
                boundary = "league" if is_new_league else "slice"
                print(
                    f"\nSleeping {sleep_seconds:.1f}s before next {boundary}...",
                    flush=True,
                )
                time.sleep(sleep_seconds)

        previous_competition_code = current_competition_code

        print(f"\nProgress: {index}/{total}", flush=True)
        reports.append(
            run_slice(
                competition_season,
                force=args.force,
                providers_only=args.providers_only,
            )
        )

    thin_reports = [report for report in reports if report.is_thin]

    payload = {
        "generated_at": timezone.now().isoformat(),
        "filters": {
            "competitions": sorted(competitions) if competitions else None,
            "seasons": sorted(seasons) if seasons else None,
            "force": args.force,
            "providers_only": args.providers_only,
        },
        "summary": {
            "total_slices_processed": len(reports),
            "healthy_slices": len(reports) - len(thin_reports),
            "thin_or_failed_slices": len(thin_reports),
        },
        "thin_slices": [serialize_slice(report) for report in thin_reports],
        "all_slices": [serialize_slice(report) for report in reports],
    }

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print("\n=== Coverage run complete ===", flush=True)
    print(f"Output: {output_path}", flush=True)
    print(f"Thin / failed slices: {len(thin_reports)}", flush=True)

    if thin_reports:
        print("\nThin / failed slice keys:", flush=True)
        for report in thin_reports:
            print(f"- {report.key}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
