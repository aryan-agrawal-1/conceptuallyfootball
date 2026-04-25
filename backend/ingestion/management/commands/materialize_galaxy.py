from django.core.management.base import BaseCommand, CommandError

from ingestion.models import CompetitionSeason, IngestionKind, IngestionRun, IngestionRunStatus


class Command(BaseCommand):
    help = "Materialize 3D player embeddings and top-5 similarity links for galaxy."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "competition_season_id",
            type=int,
            help="Primary key of ingestion.CompetitionSeason",
        )

    def handle(self, *args, **options) -> None:
        from ingestion.services.galaxy import materialize_galaxy_embeddings

        cid = options["competition_season_id"]
        try:
            competition_season = CompetitionSeason.objects.get(pk=cid)
        except CompetitionSeason.DoesNotExist as exc:
            raise CommandError(f"Unknown CompetitionSeason id={cid}") from exc

        run = IngestionRun.objects.create(
            kind=IngestionKind.GALAXY,
            competition_season=competition_season,
            status=IngestionRunStatus.PENDING,
        )
        materialize_galaxy_embeddings(competition_season, run=run)
        run.refresh_from_db()

        if run.status != IngestionRunStatus.SUCCESS:
            raise CommandError(run.error_detail or "Galaxy materialization failed")

        self.stdout.write(self.style.SUCCESS(f"Galaxy run {run.id} succeeded ({run.stats})"))
