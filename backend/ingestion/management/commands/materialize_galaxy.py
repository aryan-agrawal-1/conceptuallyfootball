from django.core.management.base import BaseCommand, CommandError

from ingestion.models import CompetitionSeason, IngestionKind, IngestionRun, IngestionRunStatus


class Command(BaseCommand):
    help = "Materialize 3D player embeddings and top-5 similarity links for galaxy."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "competition_season_id",
            type=int,
            nargs="?",
            help="Primary key of ingestion.CompetitionSeason",
        )
        parser.add_argument("--competition", help="Competition scope code, e.g. ENG1, BIG5, ALL.")
        parser.add_argument("--season", help="Season label, e.g. 2025-26.")
        parser.add_argument("--min-minutes", type=int, default=450)

    def handle(self, *args, **options) -> None:
        from ingestion.services.galaxy import materialize_galaxy_embeddings, materialize_galaxy_scope

        cid = options.get("competition_season_id")
        competition = (options.get("competition") or "").strip()
        season = (options.get("season") or "").strip()

        if cid and (competition or season):
            raise CommandError("Use either competition_season_id or --competition/--season, not both.")
        if not cid and not (competition and season):
            raise CommandError("Provide competition_season_id or both --competition and --season.")

        if cid:
            try:
                competition_season = CompetitionSeason.objects.select_related("competition", "season").get(pk=cid)
            except CompetitionSeason.DoesNotExist as exc:
                raise CommandError(f"Unknown CompetitionSeason id={cid}") from exc
            run = IngestionRun.objects.create(
                kind=IngestionKind.GALAXY,
                competition_season=competition_season,
                status=IngestionRunStatus.PENDING,
            )
            materialize_galaxy_embeddings(competition_season, run=run)
            scope_label = f"{competition_season.competition.short_code} {competition_season.season.label}"
        else:
            run = IngestionRun.objects.create(
                kind=IngestionKind.GALAXY,
                competition_season=None,
                status=IngestionRunStatus.PENDING,
            )
            materialize_galaxy_scope(
                competition,
                season,
                run=run,
                min_minutes=options["min_minutes"],
            )
            scope_label = f"{competition.upper()} {season}"
        run.refresh_from_db()

        if run.status != IngestionRunStatus.SUCCESS:
            raise CommandError(run.error_detail or "Galaxy materialization failed")

        self.stdout.write(self.style.SUCCESS(f"Galaxy {scope_label} run {run.id} succeeded ({run.stats})"))
