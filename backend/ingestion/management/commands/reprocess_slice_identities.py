from django.core.management.base import BaseCommand, CommandError

from ingestion.models import CompetitionSeason
from ingestion.services.identity import reattach_slice_identities


class Command(BaseCommand):
    help = "Re-run identity resolution on provider source rows (after manual mapping changes)."

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

        u, s, t = reattach_slice_identities(cs)
        self.stdout.write(
            self.style.SUCCESS(
                f"reattached Understat={u} Sofascore={s} SofascoreTeams={t} rows"
            )
        )
