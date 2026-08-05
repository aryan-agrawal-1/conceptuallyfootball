from django.test import TestCase
from rest_framework.test import APIClient

from ingestion.models import (
    CanonicalPlayer, CanonicalTeam, Competition, CompetitionSeason, CompetitionType,
    MergedPlayerSeason, MergedTeamSeason, PlayerSeasonDerivedStats,
    PlayerSeasonGkDerivedStats, Season,
)


class ProfileModeApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.season = Season.objects.create(label="2025-26", sort_order=2026)
        self.domestic = self.slice("ENG1", CompetitionType.DOMESTIC_LEAGUE)
        self.europe = self.slice("UCL", CompetitionType.CONTINENTAL_CUP)
        self.team = CanonicalTeam.objects.create(name="Alpha", reep_id="alpha")
        self.other = CanonicalTeam.objects.create(name="Beta", reep_id="beta")
        for cs, goals, passes, accurate, duels, duels_percentage in (
            (self.domestic, 10, 100, 80, 30, 60.0),
            (self.europe, 4, 50, 25, 10, 50.0),
        ):
            MergedTeamSeason.objects.create(
                competition_season=cs,
                canonical_team=self.team,
                matches=2,
                goals_for=goals,
                goals_against=2,
                accurate_passes=accurate,
                total_passes=passes,
                duels_won=duels,
                duels_won_percentage=duels_percentage,
                rank=1,
                points=6,
            )
            MergedTeamSeason.objects.create(competition_season=cs, canonical_team=self.other, matches=2, goals_for=1, goals_against=4, rank=2, points=0)
        self.player = CanonicalPlayer.objects.create(display_name="Player")
        self.add_player(self.domestic, self.team, 900, 2.0, 1.0)
        self.add_player(self.europe, self.other, 450, 1.0, 0.5, secondary=[self.team.id])

    def slice(self, code, competition_type):
        competition = Competition.objects.create(name=code, short_code=code, competition_type=competition_type)
        return CompetitionSeason.objects.create(competition=competition, season=self.season, is_published=True)

    def add_player(self, cs, team, minutes, xg, xa, secondary=None):
        merged = MergedPlayerSeason.objects.create(
            competition_season=cs,
            canonical_player=self.player,
            canonical_display_team=team,
            minutes=minutes,
            us_xg=xg,
            us_xa=xa,
            secondary_display_team_ids=secondary or [],
        )
        PlayerSeasonDerivedStats.objects.create(
            competition_season=cs,
            canonical_player=self.player,
            canonical_display_team=team,
            merged_player_season=merged,
            minutes=minutes,
            position_group="MID",
            percentiles_eligible=True,
            xg=xg,
            xg_per_90=xg * 90 / minutes,
            xa=xa,
            xa_per_90=xa * 90 / minutes,
            shots_per_90=(xg * 4) * 90 / minutes,
            completed_passes_per_90=(xg * 100) * 90 / minutes,
            pass_accuracy=80.0 if cs == self.domestic else 50.0,
        )

    def test_player_combined_sums_totals_recomputes_per90_and_has_auditable_components(self):
        response = self.client.get(f"/api/v1/player-seasons/derived-stats/{self.player.id}", {"competition": "ENG1", "season": "2025-26", "mode": "combined"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["mode"], "combined")
        self.assertEqual(body["metrics"]["xg"], 3.0)
        self.assertEqual(body["metrics"]["xg_per_90"], 0.2)
        self.assertEqual(body["metrics"]["shots_per_90"], 0.8)
        self.assertAlmostEqual(body["metrics"]["pass_accuracy"], 300 / 450 * 100)
        self.assertEqual(body["percentiles"]["xg"], None)
        self.assertEqual([c["competition_code"] for c in body["components"]], ["ENG1", "UCL"])
        self.assertEqual([c["minutes"] for c in body["components"]], [900, 450])
        self.assertEqual(body["components"][1]["secondary_teams"][0]["canonical_team_id"], self.team.id)

    def test_team_combined_sums_counts_recomputes_percentage_and_omits_ranks(self):
        response = self.client.get(f"/api/v1/team-seasons/stats/{self.team.id}", {"competition": "ENG1", "season": "2025-26", "mode": "combined"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["stats"]["goals_for"], 14)
        self.assertEqual(body["stats"]["accurate_passes_percentage"], 70.0)
        self.assertAlmostEqual(body["stats"]["duels_won_percentage"], 40 / 70 * 100)
        self.assertIsNone(body["stats"]["rank"])
        self.assertIsNone(body["stats"]["points"])
        self.assertTrue(all(value is None for value in body["ranks"].values()))

    def test_explicit_comparison_scope_is_independent_and_stale_values_canonicalize(self):
        response = self.client.get(
            f"/api/v1/player-seasons/derived-stats/{self.player.id}",
            {
                "competition": "ENG1",
                "season": "2025-26",
                "mode": "domestic",
                "comparison_scope": "ALL",
                "include": "profile_distributions",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["comparison_available_scopes"], ["ENG1", "BIG5", "ALL"])
        self.assertEqual(body["comparison_scope"], "ALL")
        self.assertEqual(body["comparison_source_competition"], "ENG1")
        self.assertTrue(body["comparison_eligibility"]["percentiles_eligible"])
        self.assertEqual(body["comparison_profile_distributions"]["context"]["competition_code"], "ALL")

        stale = self.client.get(
            f"/api/v1/player-seasons/derived-stats/{self.player.id}",
            {
                "competition": "ENG1",
                "season": "2025-26",
                "mode": "domestic",
                "comparison_scope": "NOT_REAL",
            },
        )
        self.assertEqual(stale.status_code, 200)
        self.assertEqual(stale.json()["comparison_scope"], "ENG1")

    def test_combined_mode_never_invents_a_comparison_percentile(self):
        response = self.client.get(
            f"/api/v1/player-seasons/derived-stats/{self.player.id}",
            {
                "competition": "ENG1",
                "season": "2025-26",
                "mode": "combined",
                "comparison_scope": "BIG5",
            },
        )
        body = response.json()
        self.assertEqual(body["comparison_scope"], "BIG5")
        self.assertFalse(body["comparison_eligibility"]["percentiles_eligible"])
        self.assertEqual(body["comparison_eligibility"]["percentiles_ineligibility_reason"], "combined_profile_mode")
        self.assertTrue(all(value is None for value in body["comparison_percentiles"].values()))

    def test_goalkeeper_modes_aggregate_rates_and_use_explicit_comparison_scope(self):
        keeper = CanonicalPlayer.objects.create(display_name="Keeper")
        for cs, minutes, saves, appearances, clean_sheets in (
            (self.domestic, 900, 30, 10, 4),
            (self.europe, 450, 10, 5, 1),
        ):
            merged = MergedPlayerSeason.objects.create(
                competition_season=cs,
                canonical_player=keeper,
                canonical_display_team=self.team,
                minutes=minutes,
                position_group="GK",
            )
            PlayerSeasonGkDerivedStats.objects.create(
                competition_season=cs,
                canonical_player=keeper,
                canonical_display_team=self.team,
                merged_player_season=merged,
                minutes=minutes,
                appearances=appearances,
                percentiles_eligible=True,
                saves=saves,
                saves_per_90=saves * 90 / minutes,
                clean_sheets=clean_sheets,
                clean_sheet_rate=clean_sheets * 100 / appearances,
            )
        response = self.client.get(
            f"/api/v1/player-seasons/gk-derived-stats/{keeper.id}",
            {
                "competition": "ENG1",
                "season": "2025-26",
                "mode": "combined",
                "comparison_scope": "ALL",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["metrics"]["saves"], 40)
        self.assertAlmostEqual(body["metrics"]["saves_per_90"], 40 * 90 / 1350)
        self.assertAlmostEqual(body["metrics"]["clean_sheet_rate"], 5 * 100 / 15)
        self.assertEqual(body["comparison_scope"], "ALL")
        self.assertTrue(all(value is None for value in body["comparison_percentiles"].values()))

    def test_europe_only_mode_falls_back_deterministically_and_invalid_mode_is_400(self):
        european = CanonicalTeam.objects.create(name="Europe only", reep_id="eu")
        MergedTeamSeason.objects.create(competition_season=self.europe, canonical_team=european, matches=1)
        response = self.client.get(f"/api/v1/team-seasons/stats/{european.id}", {"competition": "ENG1", "season": "2025-26", "mode": "domestic"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "europe")
        self.assertEqual(response.json()["available_modes"], ["europe", "combined"])
        invalid = self.client.get(f"/api/v1/team-seasons/stats/{self.team.id}", {"competition": "ENG1", "season": "2025-26", "mode": "bogus"})
        self.assertEqual(invalid.status_code, 400)
