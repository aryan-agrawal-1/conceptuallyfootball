import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ingestion.models import CompetitionSeason
from ingestion.services.player_role_aggregation import DEFAULT_MATCH_BATCH_SIZE
from ingestion.services.player_role_benchmark import (
    DEFAULT_BASELINE_PATH,
    DEFAULT_SCALE_MATCH_COUNTS,
    load_baseline,
    run_player_role_scale_gate,
)


class Command(BaseCommand):
    help = "Run the read-only full-season player-role scale and equivalence gate."

    def add_arguments(self, parser) -> None:
        parser.add_argument("competition_season_id", type=int, help="CompetitionSeason primary key.")
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_MATCH_BATCH_SIZE,
            help=f"Fixed match batch size (1-{DEFAULT_MATCH_BATCH_SIZE}; default: {DEFAULT_MATCH_BATCH_SIZE}).",
        )
        parser.add_argument(
            "--match-count",
            action="append",
            type=int,
            dest="match_counts",
            help=(
                "Scale-curve match count. Repeat to add points; the complete season is "
                "always included. Defaults to "
                + ", ".join(str(count) for count in DEFAULT_SCALE_MATCH_COUNTS)
                + "."
            ),
        )
        parser.add_argument(
            "--baseline",
            type=Path,
            default=DEFAULT_BASELINE_PATH,
            help="Legacy benchmark JSON used for the peak-RSS comparison.",
        )
        parser.add_argument("--output", type=Path, help="Write the gate report to this path.")

    def handle(self, *args, **options) -> None:
        try:
            competition_season = CompetitionSeason.objects.get(pk=options["competition_season_id"])
        except CompetitionSeason.DoesNotExist as exc:
            raise CommandError("Unknown competition-season.") from exc

        try:
            baseline = load_baseline(options["baseline"])
            report = run_player_role_scale_gate(
                competition_season,
                batch_size=options["batch_size"],
                scale_match_counts=tuple(options["match_counts"] or DEFAULT_SCALE_MATCH_COUNTS),
                baseline=baseline,
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
        if options["output"]:
            options["output"].parent.mkdir(parents=True, exist_ok=True)
            options["output"].write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            self.stdout.write(self.style.SUCCESS(f"Wrote scale-gate report to {options['output']}"))

        failed = [name for name, passed in report["gates"].items() if not passed]
        if failed:
            raise CommandError(f"Scale gate failed: {', '.join(failed)}")
        self.stdout.write(self.style.SUCCESS("Player-role scale gate passed."))
