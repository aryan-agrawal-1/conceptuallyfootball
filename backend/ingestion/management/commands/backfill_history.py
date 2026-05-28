from __future__ import annotations

import json
import time
import traceback
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ingestion.models import CompetitionSeason, IngestionKind, IngestionRun, IngestionRunStatus
from ingestion.services.ingest import (
    ingest_sofascore_slice,
    ingest_sofascore_team_slice,
    ingest_understat_slice,
    run_merge_job,
    run_team_merge_job,
)
from ingestion.services.position_resolution import run_position_resolution_job


DEFAULT_OUTPUT_PATH = settings.BASE_DIR / "history_backfill_report.json"


class Command(BaseCommand):
    help = "Sequentially backfill provider ingestion and materializations for historical competition-season slices."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--competitions", default="", help="Comma-separated competition codes, e.g. ENG1,ITA1.")
        parser.add_argument("--seasons", default="", help="Comma-separated season labels, e.g. 2021-22,2025-26.")
        parser.add_argument("--force", action="store_true", help="Re-run provider stages even if a success exists.")
        parser.add_argument("--providers-only", action="store_true", help="Run only provider ingestion stages.")
        parser.add_argument("--skip-seed", action="store_true", help="Do not run seed_competition_slices first.")
        parser.add_argument("--stop-on-error", action="store_true", help="Stop at the first failed slice.")
        parser.add_argument("--no-sleep", action="store_true", help="Disable sleeps between slices.")
        parser.add_argument(
            "--output",
            default=str(DEFAULT_OUTPUT_PATH),
            help=f"JSON report path. Default: {DEFAULT_OUTPUT_PATH}",
        )

    def handle(self, *args, **options) -> None:
        if not options["skip_seed"]:
            self.stdout.write("Seeding competition slices from manifest...")
            call_command("seed_competition_slices")

        queryset = self._build_queryset(
            competitions=self._parse_csv_filter(options["competitions"]),
            seasons=self._parse_csv_filter(options["seasons"]),
        )
        total = queryset.count()
        if total == 0:
            raise CommandError("No active competition-season slices matched the requested filters.")

        self.stdout.write(f"Found {total} active slices to backfill.")

        reports: list[dict[str, Any]] = []
        previous_competition_code = ""
        for index, competition_season in enumerate(queryset, start=1):
            current_competition_code = competition_season.competition.short_code
            if index > 1 and not options["no_sleep"]:
                self._sleep_between_slices(previous_competition_code, current_competition_code)
            previous_competition_code = current_competition_code

            self.stdout.write(
                f"\n[{index}/{total}] {current_competition_code} {competition_season.season.label}"
            )
            report = self._run_slice(
                competition_season,
                force=options["force"],
                providers_only=options["providers_only"],
            )
            reports.append(report)

            if report["status"] != "success" and options["stop_on_error"]:
                break

        payload = {
            "generated_at": timezone.now().isoformat(),
            "filters": {
                "competitions": self._parse_csv_filter(options["competitions"]),
                "seasons": self._parse_csv_filter(options["seasons"]),
                "force": options["force"],
                "providers_only": options["providers_only"],
            },
            "summary": {
                "total_slices_processed": len(reports),
                "successful_slices": sum(1 for report in reports if report["status"] == "success"),
                "failed_slices": sum(1 for report in reports if report["status"] != "success"),
            },
            "slices": reports,
        }
        output_path = Path(options["output"]).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

        failed = payload["summary"]["failed_slices"]
        style = self.style.SUCCESS if failed == 0 else self.style.WARNING
        self.stdout.write(style(f"\nBackfill complete. Failed slices: {failed}. Report: {output_path}"))

    def _build_queryset(self, *, competitions: list[str], seasons: list[str]):
        queryset = (
            CompetitionSeason.objects.filter(is_active=True)
            .select_related("competition", "season")
            .order_by("competition__short_code", "season__sort_order", "id")
        )
        if competitions:
            queryset = queryset.filter(competition__short_code__in=competitions)
        if seasons:
            queryset = queryset.filter(season__label__in=seasons)
        return queryset

    def _parse_csv_filter(self, value: str | None) -> list[str]:
        if not value:
            return []
        return [part.strip().upper() for part in value.split(",") if part.strip()]

    def _sleep_between_slices(self, previous_competition_code: str, current_competition_code: str) -> None:
        is_new_league = previous_competition_code != current_competition_code
        sleep_seconds = float(
            getattr(
                settings,
                "STATBALLER_BATCH_LEAGUE_SLEEP_SECONDS" if is_new_league else "STATBALLER_BATCH_SLICE_SLEEP_SECONDS",
                120.0 if is_new_league else 20.0,
            )
        )
        if sleep_seconds <= 0:
            return
        boundary = "league" if is_new_league else "slice"
        self.stdout.write(f"Sleeping {sleep_seconds:.1f}s before next {boundary}...")
        time.sleep(sleep_seconds)

    def _run_slice(
        self,
        competition_season: CompetitionSeason,
        *,
        force: bool,
        providers_only: bool,
    ) -> dict[str, Any]:
        report: dict[str, Any] = {
            "competition_season_id": competition_season.id,
            "competition": competition_season.competition.short_code,
            "season": competition_season.season.label,
            "status": "success",
            "steps": [],
        }

        try:
            if competition_season.supports_sofascore:
                report["steps"].append(
                    self._run_provider_step(
                        competition_season,
                        IngestionKind.SOFASCORE,
                        ingest_sofascore_slice,
                        force=force,
                    )
                )
                self._raise_if_failed(report["steps"][-1])
                report["steps"].append(
                    self._run_provider_step(
                        competition_season,
                        IngestionKind.SOFASCORE_TEAM,
                        ingest_sofascore_team_slice,
                        force=force,
                    )
                )
                self._raise_if_failed(report["steps"][-1])

            if competition_season.supports_understat:
                report["steps"].append(
                    self._run_provider_step(
                        competition_season,
                        IngestionKind.UNDERSTAT,
                        ingest_understat_slice,
                        force=force,
                    )
                )
                self._raise_if_failed(report["steps"][-1])

            if not providers_only:
                for kind, fn in (
                    (IngestionKind.TEAM_MERGE, run_team_merge_job),
                    (IngestionKind.MERGE, run_merge_job),
                ):
                    report["steps"].append(self._run_required_step(competition_season, kind, fn))
                    self._raise_if_failed(report["steps"][-1])

                report["steps"].append(
                    self._run_required_step(
                        competition_season,
                        IngestionKind.POSITION_RESOLUTION,
                        run_position_resolution_job,
                    )
                )
                self._raise_if_failed(report["steps"][-1])
                if int((report["steps"][-1]["stats"] or {}).get("written") or 0) > 0:
                    report["steps"].append(
                        self._run_required_step(competition_season, IngestionKind.MERGE, run_merge_job)
                    )
                    self._raise_if_failed(report["steps"][-1])

                from ingestion.services.derived import materialize_derived_stats
                from ingestion.services.galaxy import materialize_galaxy_embeddings

                for kind, fn in (
                    (IngestionKind.DERIVED, materialize_derived_stats),
                    (IngestionKind.GALAXY, materialize_galaxy_embeddings),
                ):
                    report["steps"].append(self._run_required_step(competition_season, kind, fn))
                    self._raise_if_failed(report["steps"][-1])
        except Exception as exc:  # noqa: BLE001
            report["status"] = "failed"
            report["error_detail"] = str(exc)
            self.stderr.write(self.style.ERROR(f"Failed: {exc}"))

        return report

    def _run_provider_step(
        self,
        competition_season: CompetitionSeason,
        kind: str,
        fn,
        *,
        force: bool,
    ) -> dict[str, Any]:
        if not force:
            existing = (
                IngestionRun.objects.filter(
                    competition_season=competition_season,
                    kind=kind,
                    status=IngestionRunStatus.SUCCESS,
                )
                .order_by("-finished_at", "-id")
                .first()
            )
            if existing:
                self.stdout.write(f"Skipping {kind}; successful run {existing.id} already exists.")
                return self._serialize_step(kind, existing, skipped=True)
        return self._run_required_step(competition_season, kind, fn)

    def _run_required_step(self, competition_season: CompetitionSeason, kind: str, fn) -> dict[str, Any]:
        self.stdout.write(f"Running {kind}...")
        run = IngestionRun.objects.create(
            kind=kind,
            competition_season=competition_season,
            status=IngestionRunStatus.PENDING,
        )
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
        return self._serialize_step(kind, run, skipped=False)

    def _serialize_step(self, kind: str, run: IngestionRun, *, skipped: bool) -> dict[str, Any]:
        return {
            "kind": kind,
            "status": run.status,
            "run_id": run.id,
            "skipped": skipped,
            "stats": run.stats or {},
            "error_detail": run.error_detail or "",
        }

    def _raise_if_failed(self, step: dict[str, Any]) -> None:
        if step["status"] != IngestionRunStatus.SUCCESS:
            raise RuntimeError(step["error_detail"] or f"{step['kind']} failed")
