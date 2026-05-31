from django.core.management.base import BaseCommand, CommandError

from ingestion.models import CompetitionSeason, IngestionKind, IngestionRun, IngestionRunStatus
from ingestion.services.derived import materialize_derived_stats


class Command(BaseCommand):
    help = "Materialize stable player-season derived stats for a competition season."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "competition_season_id",
            type=int,
            nargs="?",
            help="Primary key of ingestion.CompetitionSeason",
        )
        parser.add_argument("--competition", help="Competition code, e.g. ENG1.")
        parser.add_argument("--season", help="Season label, e.g. 2025-26.")

    def handle(self, *args, **options) -> None:
        cid = options["competition_season_id"]
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
        else:
            try:
                competition_season = CompetitionSeason.objects.select_related("competition", "season").get(
                    competition__short_code__iexact=competition,
                    season__label__iexact=season,
                    is_active=True,
                )
            except CompetitionSeason.DoesNotExist as exc:
                raise CommandError(f"Unknown active competition-season {competition} {season}") from exc

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
                f"Derived stats {competition_season.competition.short_code} "
                f"{competition_season.season.label} run {run.id} succeeded ({run.stats})"
            )
        )
