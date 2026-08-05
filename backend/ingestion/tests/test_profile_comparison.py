from django.test import TestCase
from rest_framework.test import APIClient

from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    CompetitionType,
    MergedPlayerSeason,
    PlayerSeasonDerivedStats,
    PlayerSeasonGkDerivedStats,
    Season,
)


class ProfileComparisonApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.season = Season.objects.create(label="2025-26", sort_order=2026)
        self.domestic = self.slice("ENG1", CompetitionType.DOMESTIC_LEAGUE)
        self.europe = self.slice("UCL", CompetitionType.CONTINENTAL_CUP)
        self.team = CanonicalTeam.objects.create(name="Alpha", reep_id="alpha")
        self.player = CanonicalPlayer.objects.create(display_name="Player")
        self.add_player(self.domestic, 900, 2.0, 1.0)
        self.add_player(self.europe, 450, 1.0, 0.5)

    def slice(self, code, competition_type):
        competition = Competition.objects.create(
            name=code,
            short_code=code,
            competition_type=competition_type,
        )
        return CompetitionSeason.objects.create(
            competition=competition,
            season=self.season,
            is_published=True,
        )

    def add_player(self, competition_season, minutes, xg, xa):
        merged = MergedPlayerSeason.objects.create(
            competition_season=competition_season,
            canonical_player=self.player,
            canonical_display_team=self.team,
            minutes=minutes,
            us_xg=xg,
            us_xa=xa,
        )
        PlayerSeasonDerivedStats.objects.create(
            competition_season=competition_season,
            canonical_player=self.player,
            canonical_display_team=self.team,
            merged_player_season=merged,
            minutes=minutes,
            position_group="MID",
            percentiles_eligible=True,
            xg=xg,
            xg_per_90=xg * 90 / minutes,
            xa=xa,
            xa_per_90=xa * 90 / minutes,
        )

    def test_explicit_comparison_scope_is_independent_and_stale_values_canonicalize(self):
        response = self.client.get(
            f"/api/v1/player-seasons/derived-stats/{self.player.id}",
            {
                "competition": "UCL",
                "season": "2025-26",
                "comparison_scope": "ALL",
                "include": "profile_distributions",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["competition_code"], "UCL")
        self.assertEqual(body["metrics"]["xg"], 1.0)
        self.assertEqual(body["comparison_available_scopes"], ["ENG1", "BIG5", "ALL"])
        self.assertEqual(body["comparison_scope"], "ALL")
        self.assertEqual(body["comparison_source_competition"], "ENG1")
        self.assertTrue(body["comparison_eligibility"]["percentiles_eligible"])
        self.assertEqual(
            body["comparison_profile_distributions"]["context"]["competition_code"],
            "ALL",
        )
        self.assertNotIn("mode", body)
        self.assertNotIn("components", body)

        stale = self.client.get(
            f"/api/v1/player-seasons/derived-stats/{self.player.id}",
            {
                "competition": "ENG1",
                "season": "2025-26",
                "comparison_scope": "NOT_REAL",
            },
        )
        self.assertEqual(stale.status_code, 200)
        self.assertEqual(stale.json()["comparison_scope"], "ENG1")

    def test_goalkeeper_uses_explicit_comparison_scope_without_aggregating_performance(self):
        keeper = CanonicalPlayer.objects.create(display_name="Keeper")
        for competition_season, minutes, saves in (
            (self.domestic, 900, 30),
            (self.europe, 450, 10),
        ):
            merged = MergedPlayerSeason.objects.create(
                competition_season=competition_season,
                canonical_player=keeper,
                canonical_display_team=self.team,
                minutes=minutes,
                position_group="GK",
            )
            PlayerSeasonGkDerivedStats.objects.create(
                competition_season=competition_season,
                canonical_player=keeper,
                canonical_display_team=self.team,
                merged_player_season=merged,
                minutes=minutes,
                appearances=10,
                percentiles_eligible=True,
                saves=saves,
                saves_per_90=saves * 90 / minutes,
            )

        response = self.client.get(
            f"/api/v1/player-seasons/gk-derived-stats/{keeper.id}",
            {
                "competition": "UCL",
                "season": "2025-26",
                "comparison_scope": "ALL",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["competition_code"], "UCL")
        self.assertEqual(body["metrics"]["saves"], 10)
        self.assertEqual(body["comparison_scope"], "ALL")
        self.assertEqual(body["comparison_source_competition"], "ENG1")
        self.assertTrue(body["comparison_eligibility"]["percentiles_eligible"])
        self.assertNotIn("mode", body)
        self.assertNotIn("components", body)

    def test_player_without_domestic_membership_reports_comparison_unavailable(self):
        europe_only = CanonicalPlayer.objects.create(display_name="Europe only")
        merged = MergedPlayerSeason.objects.create(
            competition_season=self.europe,
            canonical_player=europe_only,
            canonical_display_team=self.team,
            minutes=500,
        )
        PlayerSeasonDerivedStats.objects.create(
            competition_season=self.europe,
            canonical_player=europe_only,
            canonical_display_team=self.team,
            merged_player_season=merged,
            minutes=500,
            position_group="MID",
            percentiles_eligible=True,
            xg=1.0,
        )

        response = self.client.get(
            f"/api/v1/player-seasons/derived-stats/{europe_only.id}",
            {"competition": "UCL", "season": "2025-26"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["comparison_available_scopes"], [])
        self.assertIsNone(body["comparison_scope"])
        self.assertFalse(body["comparison_eligibility"]["percentiles_eligible"])
        self.assertEqual(
            body["comparison_eligibility"]["percentiles_ineligibility_reason"],
            "comparison_cohort_unavailable",
        )

