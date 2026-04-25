from django.core.management.base import BaseCommand, CommandError

from ingestion.models import CompetitionSeason, IngestionKind, IngestionRun, IngestionRunStatus
from ingestion.services.ingest import ingest_sofascore_slice


class Command(BaseCommand):
    help = "Full refresh Sofascore player-season source rows for a competition-season slice."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "competition_season_id",
            type=int,
            help="Primary key of ingestion.CompetitionSeason",
        )

    def handle(self, *args, **options) -> None:
        cid = options["competition_season_id"]
        try:
            cs = CompetitionSeason.objects.get(pk=cid)
        except CompetitionSeason.DoesNotExist as exc:
            raise CommandError(f"Unknown CompetitionSeason id={cid}") from exc

        run = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )
        ingest_sofascore_slice(cs, run=run)
        run.refresh_from_db()
        if run.status != IngestionRunStatus.SUCCESS:
            raise CommandError(run.error_detail or "Sofascore ingestion failed")
        self.stdout.write(self.style.SUCCESS(f"Sofascore run {run.id} succeeded ({run.stats})"))
