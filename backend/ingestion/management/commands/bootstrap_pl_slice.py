import os

from django.core.management.base import BaseCommand

from ingestion.models import Competition, CompetitionSeason, Season


class Command(BaseCommand):
    help = (
        "Create ENG1 Premier League + 2025-26 CompetitionSeason if missing. "
        "Prefer seed_competition_slices for full manifest-driven setup."
    )

    def handle(self, *args, **options) -> None:
        comp, _ = Competition.objects.get_or_create(
            short_code="ENG1",
            defaults={"name": "Premier League", "country": "England"},
        )
        season, _ = Season.objects.get_or_create(
            label="2025-26",
            defaults={"sort_order": 2026},
        )
        ut = int(os.environ.get("SOFASCORE_PL_UNIQUE_TOURNAMENT_ID", "17"))
        sid = int(os.environ.get("SOFASCORE_PL_SEASON_ID", "76986"))
        us_year = os.environ.get("UNDERSTAT_PL_SEASON_YEAR", "2025")
        cs, created = CompetitionSeason.objects.get_or_create(
            competition=comp,
            season=season,
            defaults={
                "understat_league": "EPL",
                "understat_season_year": us_year,
                "sofascore_unique_tournament_id": ut,
                "sofascore_season_id": sid,
                "expected_team_count": 20,
                "min_merged_team_count": 18,
                "min_team_stats_coverage_count": 18,
                "is_active": True,
            },
        )
        action = "created" if created else "exists"
        self.stdout.write(self.style.SUCCESS(f"CompetitionSeason id={cs.pk} ({action})"))
