from django.core.management.base import BaseCommand, CommandError

from ingestion.models import CompetitionSeason, IngestionKind, IngestionRun, IngestionRunStatus
from ingestion.services.ingest import run_team_merge_job


class Command(BaseCommand):
    help = "Rebuild merged team-season rows from the current Sofascore team source slice."

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
            kind=IngestionKind.TEAM_MERGE,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )
        run_team_merge_job(cs, run=run)
        run.refresh_from_db()
        if run.status != IngestionRunStatus.SUCCESS:
            raise CommandError(run.error_detail or "Team merge failed")
        self.stdout.write(self.style.SUCCESS(f"Team merge run {run.id} succeeded ({run.stats})"))
