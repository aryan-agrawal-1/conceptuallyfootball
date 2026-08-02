from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from ingestion.services.season_refresh_cutover import (
    apply_season_refresh_cutover,
    plan_season_refresh_cutover,
)


class Command(BaseCommand):
    help = (
        "Preflight the configured season refresh rollover, or atomically apply it with --apply. "
        "The default mode is read-only."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--from-season",
            default="2025-26",
            help="Source season label (default: 2025-26).",
        )
        parser.add_argument(
            "--to-season",
            default="2026-27",
            help="Target season label (default: 2026-27).",
        )
        parser.add_argument(
            "--pilot-competition",
            default="ENG1",
            help="Competition code whose target materialization gates the cutover (default: ENG1).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply the validated cutover. Without this flag the command is read-only.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        plan_builder = apply_season_refresh_cutover if options["apply"] else plan_season_refresh_cutover
        try:
            plan = plan_builder(
                from_season=options["from_season"],
                to_season=options["to_season"],
                pilot_competition=options["pilot_competition"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(json.dumps(plan.as_dict(), indent=2, sort_keys=True))
        if options["apply"]:
            self.stdout.write(
                self.style.SUCCESS(
                    "Season refresh cutover applied; exactly the listed target slices are now refresh-enabled."
                )
            )
        else:
            visibility = "published" if plan.pilot_published else "unpublished"
            self.stdout.write(
                self.style.WARNING(
                    "Preflight passed (read-only). Pilot target is "
                    f"{visibility}; rerun with --apply to mutate refresh flags."
                )
            )
