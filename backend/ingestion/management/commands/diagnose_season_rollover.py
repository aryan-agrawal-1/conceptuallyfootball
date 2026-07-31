from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from ingestion.models import CompetitionSeason
from ingestion.services.rollover_diagnostics import diagnose_season_rollover


class Command(BaseCommand):
    help = (
        "Run read-only team identity and domestic-membership checks before publishing "
        "a competition-season rollover. For a genuine provider-ID change, map the new "
        "ProviderTeamMapping to the existing CanonicalTeam with match_method=manual in "
        "Django admin, run reprocess_slice_identities for the target slice, and rerun "
        "this preflight."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "competition_season_id",
            type=int,
            help="Primary key of the target ingestion.CompetitionSeason.",
        )
        parser.add_argument(
            "--previous-competition-season-id",
            type=int,
            help="Prior slice to compare for provider ID and name changes.",
        )
        parser.add_argument(
            "--candidate-file",
            type=Path,
            help=(
                "Optional JSON file containing an unpersisted list of Sofascore team rows "
                "(or an object with a 'rows' list)."
            ),
        )
        parser.add_argument(
            "--fail-on-anomaly",
            action="store_true",
            help="Exit non-zero when the report contains an error or review item.",
        )

    def competition_season(self, value: int, label: str) -> CompetitionSeason:
        try:
            return CompetitionSeason.objects.select_related("competition", "season").get(pk=value)
        except CompetitionSeason.DoesNotExist as exc:
            raise CommandError(f"Unknown {label} CompetitionSeason id={value}") from exc

    def candidate_rows(self, path: Path | None) -> list[dict[str, object]] | None:
        if path is None:
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Unable to read candidate JSON: {exc}") from exc
        rows = payload.get("rows") if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise CommandError(
                "Candidate JSON must be a list of objects or an object with a 'rows' list."
            )
        return rows

    def handle(self, *args: Any, **options: Any) -> None:
        competition_season = self.competition_season(
            options["competition_season_id"],
            "target",
        )
        previous_id = options["previous_competition_season_id"]
        previous = (
            self.competition_season(previous_id, "previous")
            if previous_id is not None
            else None
        )
        rows = self.candidate_rows(options["candidate_file"])
        report = diagnose_season_rollover(
            competition_season,
            previous_competition_season=previous,
            candidate_rows=rows,
        )
        self.stdout.write(json.dumps(report.as_dict(), indent=2, sort_keys=True))
        if options["fail_on_anomaly"] and not report.ready_for_publication:
            raise CommandError(
                f"Season-rollover preflight found {len(report.anomalies)} anomaly/anomalies."
            )
        if report.ready_for_publication:
            self.stdout.write(self.style.SUCCESS("Season-rollover preflight passed."))
