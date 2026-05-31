from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    GalaxyPlayerEmbedding,
    GalaxySimilarity,
    GalaxySnapshot,
    IngestionKind,
    IngestionRun,
    IngestionRunStatus,
    PlayerSeasonDerivedStats,
    PositionGroup,
    Season,
    SofascorePlayerSeasonSource,
)
from ingestion.services.galaxy import materialize_galaxy_scope


class GalaxyV2Tests(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")
        self.season = Season.objects.create(label="2025-26", sort_order=2026)
        self.eng = self._competition_season("Premier League", "ENG1")
        self.spa = self._competition_season("La Liga", "SPA1")
        self.eng_team = CanonicalTeam.objects.create(name="Arsenal")
        self.spa_team = CanonicalTeam.objects.create(name="Barcelona")
        self.shared = CanonicalPlayer.objects.create(display_name="Shared Player")

        self._create_player_row(self.eng, self.eng_team, self.shared, idx=1, position=PositionGroup.FWD)
        self._create_player_row(self.spa, self.spa_team, self.shared, idx=2, position=PositionGroup.FWD)
        self.no_sofascore = CanonicalPlayer.objects.create(display_name="No Sofascore Player")
        self._create_player_row(
            self.eng,
            self.eng_team,
            self.no_sofascore,
            idx=101,
            position=PositionGroup.DEF,
            create_sofascore_source=False,
        )
        for idx in range(2, 14):
            self._create_player_row(
                self.eng,
                self.eng_team,
                CanonicalPlayer.objects.create(display_name=f"ENG Player {idx}"),
                idx=idx,
                position=PositionGroup.FWD if idx < 8 else PositionGroup.MID,
            )
            self._create_player_row(
                self.spa,
                self.spa_team,
                CanonicalPlayer.objects.create(display_name=f"SPA Player {idx}"),
                idx=idx + 20,
                position=PositionGroup.FWD if idx < 8 else PositionGroup.DEF,
            )
        self._create_player_row(
            self.eng,
            self.eng_team,
            CanonicalPlayer.objects.create(display_name="Low Minute Player"),
            idx=99,
            position=PositionGroup.FWD,
            minutes=120,
        )
        self._create_player_row(
            self.eng,
            self.eng_team,
            CanonicalPlayer.objects.create(display_name="Goalkeeper"),
            idx=100,
            position=PositionGroup.GK,
        )

    def _competition_season(self, name: str, code: str) -> CompetitionSeason:
        competition = Competition.objects.create(name=name, short_code=code)
        return CompetitionSeason.objects.create(
            competition=competition,
            season=self.season,
            has_understat=False,
            has_sofascore=True,
            sofascore_unique_tournament_id=1,
            sofascore_season_id=1,
        )

    def _create_player_row(
        self,
        competition_season: CompetitionSeason,
        team: CanonicalTeam,
        player: CanonicalPlayer,
        *,
        idx: int,
        position: str,
        minutes: int = 900,
        create_sofascore_source: bool = True,
    ) -> None:
        PlayerSeasonDerivedStats.objects.create(
            competition_season=competition_season,
            canonical_player=player,
            canonical_display_team=team,
            formula_version="test",
            position_group=position,
            native_position=position,
            minutes=minutes,
            xg_per_90=0.08 + idx * 0.005,
            goals_per_90=0.06 + idx * 0.004,
            shots_per_90=1.2 + idx * 0.03,
            assists_per_90=0.05 + idx * 0.003,
            xa_per_90=0.07 + idx * 0.004,
            key_passes_per_90=0.8 + idx * 0.02,
            big_chances_created_per_90=0.1 + idx * 0.004,
            chance_involvement_per_90=2.0 + idx * 0.04,
            completed_passes_per_90=25.0 + idx,
            pass_accuracy=75.0 + (idx % 10),
            accurate_crosses_per_90=0.2 + idx * 0.01,
            accurate_long_balls_per_90=0.8 + idx * 0.02,
            inaccurate_pass_rate=0.15 + idx * 0.001,
            successful_dribbles_per_90=0.5 + idx * 0.02,
            successful_dribbles_percentage=45.0 + (idx % 20),
            tackles_per_90=0.7 + idx * 0.02,
            interceptions_per_90=0.5 + idx * 0.02,
            clearances_per_90=0.4 + idx * 0.03,
            blocks_per_90=0.1 + idx * 0.005,
            ball_recoveries_per_90=3.0 + idx * 0.04,
            ground_duels_won_per_90=2.0 + idx * 0.03,
            aerial_duels_won_per_90=0.7 + idx * 0.02,
            tackles_won_percentage=50.0 + (idx % 30),
            fouls_per_90=0.4 + idx * 0.004,
            errors_lead_to_goal_per_90=0.0,
            is_current=True,
        )
        if create_sofascore_source:
            SofascorePlayerSeasonSource.objects.create(
                competition_season=competition_season,
                ingestion_run=IngestionRun.objects.create(
                    kind=IngestionKind.SOFASCORE,
                    competition_season=competition_season,
                    status=IngestionRunStatus.SUCCESS,
                ),
                provider_player_id=f"ss-{competition_season.id}-{player.id}",
                provider_team_id=f"team-{team.id}",
                player_name=player.display_name,
                team_name=team.name,
                position_raw=position,
                canonical_player=player,
                canonical_team=team,
                accurate_passes=500,
                accurate_passes_percentage=80.0,
                total_passes=625,
                tackles=20,
                interceptions=10,
                clearances=15,
                outfielder_blocks=5,
                ball_recoveries=40,
                ground_duels_won=30,
                aerial_duels_won=12,
                tackles_won_percentage=60.0,
                big_chances_created=2,
            )

    def _materialize_all(self) -> GalaxySnapshot:
        run = IngestionRun.objects.create(
            kind=IngestionKind.GALAXY,
            status=IngestionRunStatus.PENDING,
        )
        snapshot = materialize_galaxy_scope("ALL", "2025-26", run=run)
        run.refresh_from_db()
        self.assertEqual(run.status, IngestionRunStatus.SUCCESS, run.error_detail)
        self.assertIsNotNone(snapshot)
        return snapshot

    def _materialize_scope(self, scope: str) -> GalaxySnapshot:
        run = IngestionRun.objects.create(
            kind=IngestionKind.GALAXY,
            status=IngestionRunStatus.PENDING,
        )
        snapshot = materialize_galaxy_scope(scope, "2025-26", run=run)
        run.refresh_from_db()
        self.assertEqual(run.status, IngestionRunStatus.SUCCESS, run.error_detail)
        self.assertIsNotNone(snapshot)
        return snapshot

    def test_materializes_real_all_snapshot_with_composite_player_ids(self):
        snapshot = self._materialize_all()

        self.assertEqual(snapshot.scope_code, "ALL")
        self.assertEqual(snapshot.feature_profile, "broad_sofascore")
        self.assertEqual(set(snapshot.included_competition_season_ids), {self.eng.id, self.spa.id})
        self.assertFalse(
            GalaxyPlayerEmbedding.objects.filter(snapshot=snapshot, minutes__lt=450).exists()
        )
        self.assertFalse(
            GalaxyPlayerEmbedding.objects.filter(snapshot=snapshot, position_group=PositionGroup.GK).exists()
        )

        shared_rows = list(
            GalaxyPlayerEmbedding.objects.filter(snapshot=snapshot, canonical_player=self.shared)
            .order_by("competition_season_id")
            .values_list("galaxy_player_id", flat=True)
        )
        self.assertEqual(shared_rows, [f"{self.eng.id}:{self.shared.id}", f"{self.spa.id}:{self.shared.id}"])
        self.assertEqual(
            GalaxySimilarity.objects.filter(snapshot=snapshot).values("source_embedding").distinct().count(),
            GalaxyPlayerEmbedding.objects.filter(snapshot=snapshot).count(),
        )

    def test_api_requires_galaxy_player_id_when_canonical_player_is_ambiguous(self):
        snapshot = self._materialize_all()

        response = self.client.get(
            "/api/v1/galaxy/similar",
            {"competition": "ALL", "season": "2025-26", "player": self.shared.id},
        )
        self.assertEqual(response.status_code, 400)

        embedding = GalaxyPlayerEmbedding.objects.get(
            snapshot=snapshot,
            galaxy_player_id=f"{self.eng.id}:{self.shared.id}",
        )
        response = self.client.get(
            "/api/v1/galaxy/similar",
            {
                "competition": "ALL",
                "season": "2025-26",
                "galaxy_player_id": embedding.galaxy_player_id,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["selected_player"]["galaxy_player_id"], embedding.galaxy_player_id)
        self.assertIn("profile_match_score", payload["edges"][0])

    def test_galaxy_list_clamps_minutes_to_model_floor(self):
        self._materialize_all()

        response = self.client.get(
            "/api/v1/galaxy",
            {"competition": "ALL", "season": "2025-26", "min_minutes": "0"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["model_meta"]["effective_min_minutes"], 450)
        self.assertTrue(all(point["minutes"] >= 450 for point in payload["points"]))

    def test_missing_sofascore_source_is_excluded_from_broad_galaxy(self):
        snapshot = self._materialize_all()

        self.assertFalse(
            GalaxyPlayerEmbedding.objects.filter(
                snapshot=snapshot,
                canonical_player=self.no_sofascore,
            ).exists()
        )
        self.assertEqual(
            snapshot.diagnostics["excluded_players"]["missing_sofascore_source"],
            1,
        )

    def test_low_coverage_position_family_is_excluded_without_dropping_league(self):
        PlayerSeasonDerivedStats.objects.filter(
            competition_season=self.spa,
            position_group=PositionGroup.DEF,
        ).update(tackles_per_90=None)

        snapshot = self._materialize_scope("SPA1")

        self.assertTrue(
            GalaxyPlayerEmbedding.objects.filter(
                snapshot=snapshot,
                competition_season=self.spa,
                position_group=PositionGroup.FWD,
            ).exists()
        )
        self.assertFalse(
            GalaxyPlayerEmbedding.objects.filter(
                snapshot=snapshot,
                competition_season=self.spa,
                position_group=PositionGroup.DEF,
            ).exists()
        )
        self.assertIn(self.spa.id, snapshot.included_competition_season_ids)
        self.assertTrue(
            any(
                item.get("competition") == "SPA1"
                and item.get("position_group") == PositionGroup.DEF
                and item.get("reason") == "low_broad_profile_coverage"
                for item in snapshot.excluded_competitions
            )
        )

    def test_partial_missing_values_are_imputed_not_treated_as_zero_performance(self):
        partial_player = CanonicalPlayer.objects.create(display_name="Partial Missing Player")
        self._create_player_row(
            self.spa,
            self.spa_team,
            partial_player,
            idx=102,
            position=PositionGroup.DEF,
            create_sofascore_source=True,
        )
        PlayerSeasonDerivedStats.objects.filter(canonical_player=partial_player).update(
            pass_accuracy=None,
            completed_passes_per_90=None,
            tackles_per_90=None,
        )
        snapshot = self._materialize_all()

        embedding = GalaxyPlayerEmbedding.objects.get(
            snapshot=snapshot,
            canonical_player=partial_player,
        )
        self.assertIsNone(embedding.feature_values["pass_accuracy"])
        self.assertIsNone(embedding.feature_values["completed_passes_per_90"])
        self.assertIsNone(embedding.feature_values["tackles_per_90"])
        self.assertIn("pass_accuracy", embedding.imputed_features)
        self.assertIn("completed_passes_per_90", embedding.imputed_features)
        self.assertNotEqual(embedding.scaled_features["pass_accuracy"], -5.0)

    def test_broad_sofascore_materializes_without_xg_or_xa(self):
        PlayerSeasonDerivedStats.objects.filter(competition_season=self.spa).update(
            xg_per_90=None,
            xa_per_90=None,
        )

        snapshot = self._materialize_scope("SPA1")

        self.assertEqual(snapshot.feature_profile, "broad_sofascore")
        self.assertNotIn("xg_per_90", snapshot.feature_names)
        self.assertNotIn("xa_per_90", snapshot.feature_names)
        self.assertEqual(snapshot.diagnostics["coverage"]["xg_per_90"], 0)
        self.assertEqual(snapshot.diagnostics["coverage"]["xa_per_90"], 0)
