from django.core.management.base import BaseCommand, CommandError

from ingestion.models import CompetitionSeason, IngestionKind, IngestionRun, IngestionRunStatus
from ingestion.services.derived import materialize_derived_stats


class Command(BaseCommand):
    help = "Materialize stable player-season derived stats for a competition season."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "competition_season_id",
            type=int,
            help="Primary key of ingestion.CompetitionSeason",
        )

    def handle(self, *args, **options) -> None:
        cid = options["competition_season_id"]
        try:
            competition_season = CompetitionSeason.objects.get(pk=cid)
        except CompetitionSeason.DoesNotExist as exc:
            raise CommandError(f"Unknown CompetitionSeason id={cid}") from exc

        run = IngestionRun.objects.create(
            kind=IngestionKind.DERIVED,
            competition_season=competition_season,
            status=IngestionRunStatus.PENDING,
        )
        materialize_derived_stats(competition_season, run=run)
        run.refresh_from_db()

        if run.status != IngestionRunStatus.SUCCESS:
            raise CommandError(run.error_detail or "Derived stats materialization failed")

        self.stdout.write(
            self.style.SUCCESS(
                f"Derived stats run {run.id} succeeded ({run.stats})"
            )
        )
