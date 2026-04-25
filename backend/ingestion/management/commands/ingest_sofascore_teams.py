from django.core.management.base import BaseCommand, CommandError

from ingestion.models import CompetitionSeason, IngestionKind, IngestionRun, IngestionRunStatus
from ingestion.services.ingest import ingest_sofascore_team_slice, run_team_merge_job


class Command(BaseCommand):
    help = "Full refresh Sofascore team-season source rows for a competition-season slice."

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

        source_run = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE_TEAM,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )
        ingest_sofascore_team_slice(cs, run=source_run)
        source_run.refresh_from_db()
        if source_run.status != IngestionRunStatus.SUCCESS:
            raise CommandError(source_run.error_detail or "Sofascore team ingestion failed")
        self.stdout.write(
            self.style.SUCCESS(f"Sofascore team run {source_run.id} succeeded ({source_run.stats})")
        )

        merge_run = IngestionRun.objects.create(
            kind=IngestionKind.TEAM_MERGE,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )
        run_team_merge_job(cs, run=merge_run)
        merge_run.refresh_from_db()
        if merge_run.status != IngestionRunStatus.SUCCESS:
            raise CommandError(merge_run.error_detail or "Team merge failed")
        self.stdout.write(self.style.SUCCESS(f"Team merge run {merge_run.id} succeeded ({merge_run.stats})"))
