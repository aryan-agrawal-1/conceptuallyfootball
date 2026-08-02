from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from ingestion.services.season_refresh_activation import (
    apply_season_refresh_activation,
    plan_season_refresh_activation,
)


class Command(BaseCommand):
    help = (
        "Preflight activation of one published, ready competition-season refresh slice; "
        "use --apply to mutate refresh flags."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("competition", help="Competition short code, e.g. SWE1.")
        parser.add_argument("season", help="Canonical season label, e.g. 2026.")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply the activation. Without this flag the command is read-only.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        planner = apply_season_refresh_activation if options["apply"] else plan_season_refresh_activation
        try:
            plan = planner(options["competition"], options["season"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(plan.as_dict(), indent=2, sort_keys=True))
        if options["apply"]:
            self.stdout.write(self.style.SUCCESS("Competition-season refresh activation applied."))
        else:
            self.stdout.write(self.style.WARNING("Preflight passed (read-only); rerun with --apply to mutate flags."))
