from __future__ import annotations

from django.core.management.base import BaseCommand

from ingestion.models import CompetitionSeason, Provider
from ingestion.services.carry_derivation import backfill_match_carries


class Command(BaseCommand):
    help = (
        "Rebuild derived carries for already-ingested WhoScored matches. "
        "New ingestions derive carries automatically; this command covers "
        "matches stored before carry derivation existed."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--competition", help="Competition short code, e.g. PL.")
        parser.add_argument("--season", help="Season label, e.g. 2025-26.")

    def handle(self, *args, **options) -> None:
        from ingestion.models import ProviderMatch

        provider_matches = ProviderMatch.objects.filter(provider=Provider.WHOSCORED)
        if options.get("competition") and options.get("season"):
            competition_season = CompetitionSeason.objects.select_related(
                "competition", "season"
            ).get(
                competition__short_code__iexact=options["competition"],
                season__label=options["season"],
            )
            provider_matches = provider_matches.filter(competition_season=competition_season)
        total = backfill_match_carries(provider_matches.iterator())
        self.stdout.write(self.style.SUCCESS(f"Derived {total} carries."))
