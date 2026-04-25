from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from ingestion.models import CanonicalTeam, Competition, CompetitionSeason, MergedPlayerSeason, MergedTeamSeason, Season


def _cs() -> CompetitionSeason:
    comp = Competition.objects.create(name="Premier League", short_code="EPL", country="England")
    season = Season.objects.create(label="2025-26", sort_order=2026)
    return CompetitionSeason.objects.create(
        competition=comp,
        season=season,
        understat_league="EPL",
        understat_season_year="2025",
        sofascore_unique_tournament_id=17,
        sofascore_season_id=76986,
        expected_team_count=2,
        min_merged_team_count=1,
        min_team_stats_coverage_count=1,
    )


class TeamPublicApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.cs = _cs()
        self.t1 = CanonicalTeam.objects.create(name="Alpha FC", reep_id="a1")
        self.t2 = CanonicalTeam.objects.create(name="Beta FC", reep_id="b1")
        MergedTeamSeason.objects.create(
            competition_season=self.cs,
            canonical_team=self.t1,
            rank=1,
            points=70,
            goals_for=60,
            goals_against=20,
            average_ball_possession=60.0,
            matches=10,
            wins=8,
            draws=1,
            losses=1,
            goal_difference=40,
            clean_sheets=5,
            shots=100,
            shots_on_target=40,
            shots_against=50,
            big_chances=20,
            big_chances_against=10,
            accurate_passes_percentage=85.0,
            total_passes=5000,
            tackles=200,
            saves=30,
            corners=40,
            yellow_cards=20,
            red_cards=1,
        )
        MergedTeamSeason.objects.create(
            competition_season=self.cs,
            canonical_team=self.t2,
            rank=2,
            points=65,
            goals_for=50,
            goals_against=25,
            average_ball_possession=55.0,
            matches=10,
            wins=7,
            draws=2,
            losses=1,
            goal_difference=25,
            clean_sheets=4,
            shots=90,
            shots_on_target=35,
            shots_against=55,
            big_chances=15,
            big_chances_against=12,
            accurate_passes_percentage=82.0,
            total_passes=4800,
            tackles=190,
            saves=35,
            corners=38,
            yellow_cards=22,
            red_cards=2,
        )

    def test_team_stats_returns_ranks_and_sections(self):
        r = self.client.get(
            f"/api/v1/team-seasons/stats/{self.t1.id}",
            {"competition": "EPL", "season": "2025-26"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["canonical_team_name"], "Alpha FC")
        self.assertIn("stats", body)
        self.assertEqual(body["stats"]["goals_for"], 60)
        self.assertEqual(body["ranks"]["goals_for"], 1)
        self.assertEqual(body["ranks"]["goals_against"], 1)
        self.assertIn("ranks_per_match", body)
        self.assertEqual(body["ranks_per_match"]["goals_for"], 1)
        self.assertIn("sections", body)
        m0 = next(m for m in body["sections"]["table"]["metrics"] if m["key"] == "matches")
        self.assertIn("rank_per_match", m0)

    def test_team_stats_list_returns_league_rows(self):
        r = self.client.get(
            "/api/v1/team-seasons/stats",
            {"competition": "EPL", "season": "2025-26", "include": "meta"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["count"], 2)
        self.assertEqual(body["results"][0]["canonical_team_name"], "Alpha FC")
        self.assertEqual(body["results"][0]["stats"]["goals_for"], 60)
        self.assertEqual(body["results"][0]["ranks"]["goals_for"], 1)
        self.assertEqual(body["results"][1]["ranks_per_match"]["goals_for"], 2)
        self.assertIn("meta", body)
        self.assertIn("ranked_keys", body["meta"])

    def test_team_stats_404_no_merged_row_for_slice(self):
        """Team exists globally but has no merged row in this competition-season."""
        orphan = CanonicalTeam.objects.create(name="No Data FC", reep_id="orphan")
        r = self.client.get(
            f"/api/v1/team-seasons/stats/{orphan.id}",
            {"competition": "EPL", "season": "2025-26"},
        )
        self.assertEqual(r.status_code, 404)
        self.assertIn("detail", r.json())

    def test_squad_order(self):
        from ingestion.models import CanonicalPlayer

        p_gk = CanonicalPlayer.objects.create(display_name="Z Keeper")
        p_def = CanonicalPlayer.objects.create(display_name="A Defender")
        MergedPlayerSeason.objects.create(
            competition_season=self.cs,
            canonical_player=p_gk,
            canonical_display_team=self.t1,
            position_group="GK",
            minutes=900,
        )
        MergedPlayerSeason.objects.create(
            competition_season=self.cs,
            canonical_player=p_def,
            canonical_display_team=self.t1,
            position_group="DEF",
            minutes=1800,
        )
        r = self.client.get(
            f"/api/v1/team-seasons/squad/{self.t1.id}",
            {"competition": "EPL", "season": "2025-26"},
        )
        self.assertEqual(r.status_code, 200)
        rows = r.json()["results"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["position_group"], "GK")
        self.assertEqual(rows[1]["position_group"], "DEF")
