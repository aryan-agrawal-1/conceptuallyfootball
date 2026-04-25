from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    IngestionRunStatus,
    PlayerSeasonDerivedStats,
    Season,
    SofascorePlayerSeasonSource,
    UnderstatPlayerSeasonSource,
)
from ingestion.services.derived import materialize_derived_stats
from ingestion.services.merge import execute_merge_for_slice


def _slice():
    competition = Competition.objects.create(name="Premier League", short_code="EPL", country="England")
    season = Season.objects.create(label="2025-26", sort_order=2026)
    return CompetitionSeason.objects.create(
        competition=competition,
        season=season,
        understat_league="EPL",
        understat_season_year="2025",
        sofascore_unique_tournament_id=17,
        sofascore_season_id=76986,
    )


class DerivedStatsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.cs = _slice()
        self.team = CanonicalTeam.objects.create(name="Alpha FC", reep_id="team-alpha")
        self.us_run = IngestionRun.objects.create(
            kind=IngestionKind.UNDERSTAT,
            competition_season=self.cs,
            status=IngestionRunStatus.SUCCESS,
        )
        self.ss_run = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE,
            competition_season=self.cs,
            status=IngestionRunStatus.SUCCESS,
        )

        self.alpha = self._create_player(
            name="Alpha Forward",
            reep_id="player-alpha",
            position="F",
            minutes=900,
            goals=12,
            npg=12,
            shots=50,
            key_passes=18,
            xg=8.0,
            npxg=7.5,
            xa=4.2,
            xgchain=15.0,
            xgbuildup=6.0,
            big_chances_created=8,
            dribbles=24,
            tackles=8,
            interceptions=4,
            clearances=5,
            blocks=1,
            accurate_passes=280,
            pass_accuracy=79.0,
        )
        self.beta = self._create_player(
            name="Beta Forward",
            reep_id="player-beta",
            position="F",
            minutes=920,
            goals=5,
            npg=5,
            shots=42,
            key_passes=10,
            xg=7.4,
            npxg=7.0,
            xa=1.5,
            xgchain=9.4,
            xgbuildup=3.0,
            big_chances_created=3,
            dribbles=11,
            tackles=5,
            interceptions=2,
            clearances=3,
            blocks=0,
            accurate_passes=210,
            pass_accuracy=74.0,
        )
        self.gamma = self._create_player(
            name="Gamma Midfielder",
            reep_id="player-gamma",
            position="M",
            minutes=1100,
            goals=4,
            npg=4,
            shots=30,
            key_passes=28,
            xg=3.0,
            npxg=2.7,
            xa=5.4,
            xgchain=16.0,
            xgbuildup=9.0,
            big_chances_created=10,
            dribbles=15,
            tackles=28,
            interceptions=19,
            clearances=12,
            blocks=4,
            accurate_passes=640,
            pass_accuracy=88.0,
        )
        self.delta = self._create_player(
            name="Delta Midfielder",
            reep_id="player-delta",
            position="M",
            minutes=300,
            goals=1,
            npg=1,
            shots=8,
            key_passes=6,
            xg=0.8,
            npxg=0.7,
            xa=1.0,
            xgchain=3.2,
            xgbuildup=1.9,
            big_chances_created=2,
            dribbles=4,
            tackles=7,
            interceptions=4,
            clearances=2,
            blocks=1,
            accurate_passes=120,
            pass_accuracy=85.0,
        )

        execute_merge_for_slice(self.cs, merge_run=None)

    def _create_player(
        self,
        *,
        name: str,
        reep_id: str,
        position: str,
        minutes: int,
        goals: int,
        npg: int,
        shots: int,
        key_passes: int,
        xg: float,
        npxg: float,
        xa: float,
        xgchain: float,
        xgbuildup: float,
        big_chances_created: int,
        dribbles: int,
        tackles: int,
        interceptions: int,
        clearances: int,
        blocks: int,
        accurate_passes: int,
        pass_accuracy: float,
    ) -> CanonicalPlayer:
        player = CanonicalPlayer.objects.create(display_name=name, reep_id=reep_id)
        UnderstatPlayerSeasonSource.objects.create(
            competition_season=self.cs,
            ingestion_run=self.us_run,
            provider_player_id=f"us-{reep_id}",
            provider_team_id="team-1",
            player_name=name,
            team_name=self.team.name,
            position_raw=position,
            games=max(minutes // 90, 1),
            minutes=minutes,
            goals=goals,
            assists=max(int(xa), 0),
            shots=shots,
            key_passes=key_passes,
            npg=npg,
            xg=xg,
            npxg=npxg,
            xa=xa,
            xgchain=xgchain,
            xgbuildup=xgbuildup,
            canonical_player=player,
            canonical_team=self.team,
        )
        sot = max(1, int(shots * 0.42))
        off_tgt = max(0, shots - sot)
        SofascorePlayerSeasonSource.objects.create(
            competition_season=self.cs,
            ingestion_run=self.ss_run,
            provider_player_id=f"ss-{reep_id}",
            provider_team_id="team-1",
            player_name=name,
            team_name=self.team.name,
            position_raw=position,
            summary_successful_dribbles=dribbles,
            tackles=tackles,
            interceptions=interceptions,
            clearances=clearances,
            outfielder_blocks=blocks,
            big_chances_created=big_chances_created,
            accurate_passes=accurate_passes,
            accurate_passes_percentage=pass_accuracy,
            key_passes=key_passes,
            shots_on_target=sot,
            shots_off_target=off_tgt,
            canonical_player=player,
            canonical_team=self.team,
        )
        return player

    def _materialize(self):
        run = IngestionRun.objects.create(
            kind=IngestionKind.DERIVED,
            competition_season=self.cs,
            status=IngestionRunStatus.PENDING,
        )
        materialize_derived_stats(self.cs, run=run)
        run.refresh_from_db()
        self.assertEqual(run.status, IngestionRunStatus.SUCCESS)
        return run

    def test_materialize_creates_current_rows_and_applies_eligibility(self):
        run = self._materialize()
        rows = PlayerSeasonDerivedStats.objects.filter(competition_season=self.cs, is_current=True)
        self.assertEqual(rows.count(), 4)

        alpha_row = rows.get(canonical_player=self.alpha)
        self.assertEqual(alpha_row.formula_version, "v3")
        self.assertEqual(alpha_row.derived_ingestion_run, run)
        self.assertTrue(alpha_row.percentiles_eligible)
        self.assertTrue(alpha_row.scores_eligible)
        self.assertIsNotNone(alpha_row.successful_dribbles_per_90)
        self.assertIsNotNone(alpha_row.npxg_per_shot)
        self.assertIsNotNone(alpha_row.creation_score_raw)
        self.assertIsNotNone(alpha_row.creation_score)
        self.assertIsNotNone(alpha_row.finishing_shrunk_delta_per_shot)
        self.assertIsNotNone(alpha_row.sot_rate)
        self.assertIsNotNone(alpha_row.finishing_score_raw)
        self.assertIsNotNone(alpha_row.finishing_score)

        delta_row = rows.get(canonical_player=self.delta)
        self.assertFalse(delta_row.percentiles_eligible)
        self.assertEqual(delta_row.percentiles_ineligibility_reason, "below_minutes_threshold")
        self.assertFalse(delta_row.scores_eligible)
        self.assertIsNone(delta_row.creation_score)

    def test_list_endpoint_returns_sorted_rows_and_optional_meta(self):
        self._materialize()

        response = self.client.get(
            "/api/v1/player-seasons/derived-stats",
            {
                "competition": "EPL",
                "season": "2025-26",
                "position_group": "FWD",
                "sort": "-creation_score",
                "include": "meta",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["results"][0]["canonical_player_name"], "Alpha Forward")
        self.assertIn("meta", payload)
        self.assertEqual(payload["meta"]["formula_version"], "v3")
        self.assertIn("npxg_per_shot", payload["meta"]["metrics"])

    def test_detail_endpoint_groups_sections(self):
        self._materialize()

        response = self.client.get(
            f"/api/v1/player-seasons/derived-stats/{self.gamma.id}",
            {
                "competition": "EPL",
                "season": "2025-26",
                "include": "meta",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["canonical_player_name"], "Gamma Midfielder")
        self.assertIn("sections", payload)
        self.assertIn("attack", payload["sections"])
        self.assertTrue(payload["sections"]["attack"]["metrics"])
        self.assertIn("scores", payload)
        self.assertIn("creation_score", payload["scores"])
        self.assertIn("finishing_score", payload["scores"])
