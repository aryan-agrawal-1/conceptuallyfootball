from django.core.management.base import BaseCommand, CommandError

from ingestion.models import CompetitionSeason, IngestionKind, IngestionRun, IngestionRunStatus
from ingestion.services.ingest import run_merge_job, run_team_merge_job


class Command(BaseCommand):
    help = "Rebuild team and player materializations for a competition-season slice."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "competition_season_id",
            type=int,
            help="Primary key of ingestion.CompetitionSeason",
        )

    def handle(self, *args, **options) -> None:
        from ingestion.services.derived import materialize_derived_stats
        from ingestion.services.galaxy import materialize_galaxy_embeddings

        cid = options["competition_season_id"]
        try:
            cs = CompetitionSeason.objects.get(pk=cid)
        except CompetitionSeason.DoesNotExist as exc:
            raise CommandError(f"Unknown CompetitionSeason id={cid}") from exc

        team_run = IngestionRun.objects.create(
            kind=IngestionKind.TEAM_MERGE,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )
        run_team_merge_job(cs, run=team_run)
        team_run.refresh_from_db()
        if team_run.status != IngestionRunStatus.SUCCESS:
            raise CommandError(team_run.error_detail or "Team merge failed")
        self.stdout.write(self.style.SUCCESS(f"Team merge run {team_run.id} succeeded ({team_run.stats})"))

        merge_run = IngestionRun.objects.create(
            kind=IngestionKind.MERGE,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )
        run_merge_job(cs, run=merge_run)
        merge_run.refresh_from_db()
        if merge_run.status != IngestionRunStatus.SUCCESS:
            raise CommandError(merge_run.error_detail or "Player merge failed")
        self.stdout.write(self.style.SUCCESS(f"Merge run {merge_run.id} succeeded ({merge_run.stats})"))

        derived_run = IngestionRun.objects.create(
            kind=IngestionKind.DERIVED,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )
        materialize_derived_stats(cs, run=derived_run)
        derived_run.refresh_from_db()
        if derived_run.status != IngestionRunStatus.SUCCESS:
            raise CommandError(derived_run.error_detail or "Derived materialization failed")
        self.stdout.write(self.style.SUCCESS(f"Derived run {derived_run.id} succeeded ({derived_run.stats})"))

        galaxy_run = IngestionRun.objects.create(
            kind=IngestionKind.GALAXY,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )
        materialize_galaxy_embeddings(cs, run=galaxy_run)
        galaxy_run.refresh_from_db()
        if galaxy_run.status != IngestionRunStatus.SUCCESS:
            raise CommandError(galaxy_run.error_detail or "Galaxy materialization failed")
        self.stdout.write(self.style.SUCCESS(f"Galaxy run {galaxy_run.id} succeeded ({galaxy_run.stats})"))
