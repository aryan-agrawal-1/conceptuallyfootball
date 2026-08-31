from __future__ import annotations

import json
from pathlib import Path

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management.base import BaseCommand, CommandError

from ingestion.competition_scope import resolve_active_competition_season
from ingestion.services.whoscored_pipeline_benchmark import (
    benchmark_stage,
    benchmark_stored_payload_parse,
    report_header,
    scope_inventory,
)


class Command(BaseCommand):
    help = "Run read-only WhoScored pipeline inventory and stored-payload parsing benchmarks."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--competition", required=True)
        parser.add_argument("--season", required=True)
        parser.add_argument(
            "--stage",
            action="append",
            choices=("inventory", "stored-payload-parse"),
            help="Stage to run; repeat as needed. Defaults to both stages.",
        )
        parser.add_argument(
            "--match-limit",
            type=int,
            help="Limit stored-payload parsing to the earliest N matches.",
        )
        parser.add_argument("--output", type=Path)

    def handle(self, *args, **options) -> None:
        if options["match_limit"] is not None and options["match_limit"] <= 0:
            raise CommandError("--match-limit must be positive.")
        try:
            competition_season = resolve_active_competition_season(
                options["competition"], options["season"]
            )
        except DjangoValidationError as error:
            raise CommandError("Unknown active competition-season.") from error
        if not competition_season.supports_whoscored:
            raise CommandError("WhoScored is not configured for this competition-season.")

        selected = options["stage"] or ["inventory", "stored-payload-parse"]
        report = report_header(competition_season)
        report["stages"] = []
        if "inventory" in selected:
            report["stages"].append(
                benchmark_stage("inventory", lambda: scope_inventory(competition_season))
            )
        if "stored-payload-parse" in selected:
            report["stages"].append(
                benchmark_stage(
                    "stored-payload-parse",
                    lambda: benchmark_stored_payload_parse(
                        competition_season,
                        limit=options["match_limit"],
                    ),
                )
            )

        rendered = json.dumps(report, indent=2, sort_keys=True)
        self.stdout.write(rendered)
        if options["output"]:
            options["output"].parent.mkdir(parents=True, exist_ok=True)
            options["output"].write_text(rendered + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Wrote benchmark report to {options['output']}"))
