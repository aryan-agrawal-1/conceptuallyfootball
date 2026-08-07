from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from django.test.utils import override_settings

from ingestion.api_cache import invalidate_materialized_api_payloads
from ingestion.models import IngestionKind, IngestionRun, IngestionRunStatus
from ingestion.services.aggregate_season_alignment import calendar_aggregate_coverage


class Command(BaseCommand):
    help = (
        "Diagnose calendar-season aggregate coverage and optionally rematerialize every "
        "affected published ALL season."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Rematerialize all affected ALL Galaxy snapshots and invalidate API payload caches.",
        )
        parser.add_argument(
            "--fail-on-warning",
            action="store_true",
            help="Exit non-zero when any published calendar slice is missing from its intended aggregate.",
        )

    def handle(self, *args, **options) -> None:
        before = calendar_aggregate_coverage()
        report = {"before": before, "applied": False}

        if options["apply"]:
            from ingestion.services.galaxy import materialize_galaxy_scope

            run_ids = {}
            with override_settings(STATBALLER_GALAXY_PRUNE_AFTER_MATERIALIZE=False):
                for season_label in sorted(before["aggregate_counts"]):
                    run = IngestionRun.objects.create(
                        kind=IngestionKind.GALAXY,
                        competition_season=None,
                        status=IngestionRunStatus.PENDING,
                    )
                    materialize_galaxy_scope("ALL", season_label, run=run)
                    run.refresh_from_db()
                    if run.status != IngestionRunStatus.SUCCESS:
                        raise CommandError(
                            run.error_detail or f"ALL {season_label} Galaxy materialization failed."
                        )
                    run_ids[season_label] = run.id
            report.update(
                {
                    "applied": True,
                    "galaxy_run_ids": run_ids,
                    "api_cache_deleted": invalidate_materialized_api_payloads(),
                    "after": calendar_aggregate_coverage(),
                }
            )

        self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
        final_report = report.get("after", before)
        if options["fail_on_warning"] and not final_report["ok"]:
            raise CommandError("Calendar-season aggregate alignment warnings detected.")
