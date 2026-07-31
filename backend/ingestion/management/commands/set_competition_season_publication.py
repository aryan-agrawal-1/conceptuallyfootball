from django.core.management.base import BaseCommand, CommandError

from ingestion.models import CompetitionSeason
from ingestion.services.publication import set_competition_season_published


class Command(BaseCommand):
    help = "Intentionally publish or hide a competition-season after checking derived-data readiness."

    def add_arguments(self, parser) -> None:
        parser.add_argument("competition_season_id", type=int)
        action = parser.add_mutually_exclusive_group(required=True)
        action.add_argument("--publish", action="store_true")
        action.add_argument("--hide", action="store_true")

    def handle(self, *args, **options) -> None:
        try:
            competition_season = CompetitionSeason.objects.select_related(
                "competition", "season"
            ).get(pk=options["competition_season_id"])
        except CompetitionSeason.DoesNotExist as exc:
            raise CommandError("Unknown competition-season.") from exc

        published = bool(options["publish"])
        try:
            readiness = set_competition_season_published(
                competition_season,
                published=published,
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        state = "published" if published else "hidden"
        self.stdout.write(
            self.style.SUCCESS(
                f"{competition_season} is {state}; "
                f"current player rows={readiness.current_outfield_rows + readiness.current_goalkeeper_rows}."
            )
        )
