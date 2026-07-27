from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from ingestion.services.whoscored_client import (
    SoccerdataWhoScoredClient,
    WhoScoredSourceConfig,
    shot_orientation_gate,
    summarize_match_payload,
)


class Command(BaseCommand):
    help = (
        "Run a bounded WhoScored source probe and print only sanitized schedule, "
        "checksum, event-count, coordinate, and orientation diagnostics."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--league", default="ENG-Premier League")
        parser.add_argument("--season", default="2025-26")
        parser.add_argument(
            "--match-id",
            action="append",
            type=int,
            default=[],
            help="Specific completed match ID; repeat up to five times.",
        )
        parser.add_argument(
            "--match-count",
            type=int,
            default=3,
            help="Latest completed matches to probe when --match-id is omitted (1..5).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Bypass event cache. Use sparingly; this opens match pages again.",
        )
        parser.add_argument(
            "--headless",
            action="store_true",
            help="Run Chrome headlessly. Headed mode is the soccerdata default and may be less blocked.",
        )
        parser.add_argument(
            "--output",
            type=Path,
            help="Optional path for the sanitized report. Raw payloads are never written here.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        match_ids = list(dict.fromkeys(options["match_id"]))
        match_count = options["match_count"]
        if not 1 <= match_count <= 5:
            raise CommandError("--match-count must be between 1 and 5.")
        if len(match_ids) > 5:
            raise CommandError("At most five --match-id values may be probed at once.")

        client = SoccerdataWhoScoredClient(
            WhoScoredSourceConfig(
                league=options["league"],
                season=options["season"],
                headless=options["headless"],
            )
        )
        try:
            schedule = client.list_matches(force_cache=not options["force"])
            schedule_by_id = {match.match_id: match for match in schedule}
            if match_ids:
                missing = sorted(set(match_ids) - set(schedule_by_id))
                if missing:
                    raise CommandError(f"Match IDs are absent from the configured schedule: {missing}")
                selected_ids = match_ids
            else:
                completed = [match for match in schedule if match.status == "completed"]
                selected_ids = [match.match_id for match in completed[-match_count:]]
                if len(selected_ids) < match_count:
                    raise CommandError(
                        f"Only {len(selected_ids)} completed matches were discovered; "
                        f"{match_count} requested."
                    )

            reports = []
            for match_id in selected_ids:
                retrieved = client.fetch_match_payload(match_id, force=options["force"])
                report = summarize_match_payload(match_id, retrieved.payload)
                if report["coordinate_error_count"]:
                    raise CommandError(
                        f"Match {match_id} contains out-of-range/non-numeric coordinates."
                    )
                reports.append(report)

            orientation_gate = shot_orientation_gate(reports)
            if not orientation_gate["passed"]:
                raise CommandError(
                    "The acting-team x=100 orientation gate did not pass: "
                    f"{orientation_gate['assessed_team_sides']} assessed team sides, "
                    f"{orientation_gate['failed_team_sides']} failures, "
                    f"minimum {orientation_gate['minimum_assessed_team_sides']} assessed."
                )

            safe_report = {
                "source": "soccerdata.WhoScored",
                "league": options["league"],
                "season": options["season"],
                "schedule_match_count": len(schedule),
                "completed_match_count": sum(
                    match.status == "completed" for match in schedule
                ),
                "selected_match_ids": selected_ids,
                "shot_orientation_gate": orientation_gate,
                "matches": reports,
            }
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise CommandError(
                "WhoScored probe failed. Check Chrome/driver availability, provider access, "
                "SOCCERDATA_DIR permissions, pacing, and the local soccerdata cache. "
                f"Underlying error: {exc}"
            ) from exc

        rendered = json.dumps(safe_report, indent=2, sort_keys=True)
        if options["output"]:
            output_path: Path = options["output"]
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered + "\n", encoding="utf-8")
        self.stdout.write(rendered)
        self.stdout.write(self.style.SUCCESS("WhoScored source probe passed."))
