import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ingestion.models import CompetitionSeason
from ingestion.services.player_role_benchmark import (
    DEFAULT_CORPUS_PATH,
    benchmark_player_role_features,
    compare_oracle,
    create_oracle,
    load_corpus,
)


class Command(BaseCommand):
    help = "Read-only benchmark and equivalence check for player role feature construction."

    def add_arguments(self, parser) -> None:
        parser.add_argument("competition_season_id", type=int, help="CompetitionSeason primary key.")
        parser.add_argument(
            "--corpus",
            type=Path,
            default=DEFAULT_CORPUS_PATH,
            help="Representative corpus manifest (defaults to the committed season-4 corpus).",
        )
        parser.add_argument(
            "--match-count",
            action="append",
            type=int,
            dest="match_counts",
            help="Benchmark the earliest N matches. Repeat for a size curve; omit for the full season.",
        )
        parser.add_argument("--oracle", type=Path, help="Compare the full-season candidate output to this oracle.")
        parser.add_argument("--write-oracle", type=Path, help="Write accepted current feature/role rows as an oracle.")
        parser.add_argument("--output", type=Path, help="Write the JSON benchmark report to this path.")

    def handle(self, *args, **options) -> None:
        try:
            competition_season = CompetitionSeason.objects.get(pk=options["competition_season_id"])
        except CompetitionSeason.DoesNotExist as exc:
            raise CommandError("Unknown competition-season.") from exc

        try:
            corpus = load_corpus(options["corpus"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CommandError(f"Invalid corpus: {exc}") from exc

        if options["write_oracle"]:
            oracle = create_oracle(competition_season, corpus)
            self.write_json(options["write_oracle"], oracle)
            self.stdout.write(self.style.SUCCESS(f"Wrote equivalence oracle to {options['write_oracle']}"))

        match_counts = options["match_counts"] or [None]
        if options["oracle"] and match_counts != [None]:
            raise CommandError("Oracle comparison requires a full-season run; omit --match-count.")

        reports = []
        candidate_profiles = None
        for match_count in match_counts:
            report, candidate_profiles = benchmark_player_role_features(
                competition_season,
                corpus,
                match_count=match_count,
            )
            reports.append(report)
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))

        result = {"benchmarks": reports}
        if options["oracle"]:
            try:
                oracle = json.loads(options["oracle"].read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise CommandError(f"Invalid oracle: {exc}") from exc
            differences = compare_oracle(oracle, candidate_profiles)
            result["equivalence"] = {
                "oracle": str(options["oracle"]),
                "differences": differences,
                "matches": not differences,
            }
            if differences:
                preview = "\n".join(differences[:20])
                raise CommandError(
                    f"Equivalence check found {len(differences)} differences. First differences:\n{preview}"
                )
            self.stdout.write(self.style.SUCCESS("Feature and role output matches the equivalence oracle."))

        if options["output"]:
            self.write_json(options["output"], result)
            self.stdout.write(self.style.SUCCESS(f"Wrote benchmark report to {options['output']}"))

    @staticmethod
    def write_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
