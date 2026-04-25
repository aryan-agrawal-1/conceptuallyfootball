from django.core.management.base import BaseCommand, CommandError

from ingestion.models import CompetitionSeason, IngestionKind, IngestionRun, IngestionRunStatus
from ingestion.services.ingest import run_merge_job


class Command(BaseCommand):
    help = "Rebuild merged player-season rows after both provider ingestions succeeded."

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

        run = IngestionRun.objects.create(
            kind=IngestionKind.MERGE,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )
        run_merge_job(cs, run=run)
        run.refresh_from_db()
        if run.status != IngestionRunStatus.SUCCESS:
            raise CommandError(run.error_detail or "Merge failed")
        self.stdout.write(self.style.SUCCESS(f"Merge run {run.id} succeeded ({run.stats})"))

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
