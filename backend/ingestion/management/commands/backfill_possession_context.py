from time import perf_counter

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management.base import BaseCommand, CommandError

from ingestion.competition_scope import resolve_active_competition_season
from ingestion.models import Provider, ProviderMatch
from ingestion.services.possession_context import replace_match_possessions


class Command(BaseCommand):
    help = "Rebuild versioned possession context for a WhoScored competition-season or match."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--competition", required=True)
        parser.add_argument("--season", required=True)
        parser.add_argument("--match-id", action="append", default=[])

    def handle(self, *args, **options) -> None:
        try:
            competition_season = resolve_active_competition_season(
                options["competition"], options["season"]
            )
        except DjangoValidationError as error:
            raise CommandError("Unknown active competition-season.") from error
        matches = ProviderMatch.objects.filter(
            provider=Provider.WHOSCORED,
            competition_season=competition_season,
        ).order_by("provider_match_id")
        match_ids = options["match_id"]
        if match_ids:
            matches = matches.filter(provider_match_id__in=match_ids)
            if matches.count() != len(set(match_ids)):
                raise CommandError("Unknown affected WhoScored match id.")
        started = perf_counter()
        match_count = possession_count = event_count = 0
        for provider_match in matches.iterator():
            possession_count += replace_match_possessions(provider_match)
            event_count += provider_match.events.count()
            match_count += 1
        elapsed = perf_counter() - started
        self.stdout.write(
            self.style.SUCCESS(
                f"Rebuilt {possession_count} possessions from {event_count} events "
                f"across {match_count} matches in {elapsed:.3f}s."
            )
        )
