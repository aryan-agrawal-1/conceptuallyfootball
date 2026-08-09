from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from ingestion.competition_seasons_api import _aggregate_metric_availability
from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    IngestionRunStatus,
    MaterializedApiPayload,
    PlayerSeasonDerivedStats,
    PlayerSeasonGkDerivedStats,
    PositionGroup,
    Season,
    SofascorePlayerSeasonSource,
    UnderstatPlayerSeasonSource,
)
from ingestion.services.derived import materialize_derived_stats
from ingestion.services.merge import execute_merge_for_slice
from ingestion.profile_distributions import (
    PROFILE_DISTRIBUTION_BIN_COUNT,
    distribution_bins,
    quantile,
)


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
        is_published=True,
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
        total_passes = max(accurate_passes, round(accurate_passes / (pass_accuracy / 100.0)))
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
            inaccurate_passes=max(0, total_passes - accurate_passes),
            total_passes=total_passes,
            accurate_passes_percentage=pass_accuracy,
            key_passes=key_passes,
            shots_on_target=sot,
            shots_off_target=off_tgt,
            accurate_crosses=max(1, key_passes // 6),
            accurate_long_balls=max(1, accurate_passes // 24),
            ball_recoveries=max(1, tackles + interceptions),
            aerial_duels_won=max(1, clearances),
            successful_dribbles_percentage=55.0,
            fouls=max(1, tackles // 4),
            offsides=1 if position == "F" else 0,
            error_lead_to_goal=0,
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
        self.assertEqual(alpha_row.formula_version, "v4")
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

    def test_early_season_rows_still_publish_metric_availability(self):
        self.cs.competition.minimum_eligible_minutes = 5000
        self.cs.competition.save(update_fields=["minimum_eligible_minutes"])

        self._materialize()

        self.cs.refresh_from_db()
        availability = self.cs.metric_availability
        self.assertEqual(availability["player_rows"]["eligible_outfield"], 0)
        self.assertEqual(availability["player_rows"]["coverage_outfield"], 4)
        self.assertIn("xg_per_90", availability["ui_available_metrics"])
        self.assertNotIn("tackles_won", availability["ui_available_metrics"])

    def test_aggregate_availability_weights_early_season_rows(self):
        availability = _aggregate_metric_availability(
            [
                {
                    "player_rows": {"eligible_outfield": 0, "coverage_outfield": 4},
                    "coverage": {"xg_per_90": 1.0},
                },
                {
                    "player_rows": {"eligible_outfield": 2, "coverage_outfield": 2},
                    "coverage": {"xg_per_90": 0.5},
                },
            ]
        )

        self.assertEqual(availability["coverage"]["xg_per_90"], 0.8333)
        self.assertIn("xg_per_90", availability["ui_available_metrics"])

    def test_failed_rematerialization_preserves_last_good_published_rows(self):
        first_run = self._materialize()
        self.cs.is_published = True
        self.cs.save(update_fields=["is_published"])
        current_ids = set(
            PlayerSeasonDerivedStats.objects.filter(
                competition_season=self.cs,
                is_current=True,
            ).values_list("id", flat=True)
        )
        failed_run = IngestionRun.objects.create(
            kind=IngestionKind.DERIVED,
            competition_season=self.cs,
            status=IngestionRunStatus.PENDING,
        )

        with patch(
            "ingestion.services.derived.PlayerSeasonDerivedStats.objects.bulk_create",
            side_effect=RuntimeError("simulated replacement failure"),
        ):
            materialize_derived_stats(self.cs, run=failed_run)

        failed_run.refresh_from_db()
        self.cs.refresh_from_db()
        self.assertEqual(failed_run.status, IngestionRunStatus.FAILED)
        self.assertTrue(self.cs.is_published)
        self.assertSetEqual(
            set(
                PlayerSeasonDerivedStats.objects.filter(
                    competition_season=self.cs,
                    is_current=True,
                ).values_list("id", flat=True)
            ),
            current_ids,
        )
        self.assertTrue(
            PlayerSeasonDerivedStats.objects.filter(
                competition_season=self.cs,
                derived_ingestion_run=first_run,
                is_current=True,
            ).exists()
        )

    def test_absent_sofascore_fields_remain_null_and_hidden(self):
        self._materialize()

        row = PlayerSeasonDerivedStats.objects.get(
            competition_season=self.cs,
            canonical_player=self.alpha,
            is_current=True,
        )
        self.assertIsNone(row.tackles_won)
        self.assertIsNone(row.tackles_won_percentage)
        self.assertIsNone(row.ground_duels_won)
        self.assertIsNone(row.ground_duels_won_per_90)

        self.cs.refresh_from_db()
        availability = self.cs.metric_availability
        self.assertIn("tackles_won", availability["unavailable_metrics"])
        self.assertIn("ground_duels_won", availability["unavailable_metrics"])
        self.assertNotIn("tackles_won", availability["ui_available_metrics"])
        self.assertNotIn("ground_duels_won", availability["ui_available_metrics"])

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
        self.assertEqual(payload["meta"]["formula_version"], "v4")
        self.assertIn("npxg_per_shot", payload["meta"]["metrics"])

    def test_list_endpoint_ignores_unknown_query_params_without_materializing_payload_cache(self):
        self._materialize()

        common = {
            "competition": "EPL",
            "season": "2025-26",
            "position_group": "FWD",
        }
        first = self.client.get(
            "/api/v1/player-seasons/derived-stats",
            {**common, "junk": "one"},
        )
        second = self.client.get(
            "/api/v1/player-seasons/derived-stats",
            {**common, "junk": "two"},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(
            MaterializedApiPayload.objects.filter(cache_key__startswith="derived-player-season-list:").count(),
            0,
        )

    def test_list_endpoint_paginates_filters_and_rejects_oversized_pages(self):
        self._materialize()

        response = self.client.get(
            "/api/v1/player-seasons/derived-stats",
            {
                "competition": "EPL",
                "season": "2025-26",
                "position_group": "FWD",
                "sort": "-creation_score",
                "page": 1,
                "page_size": 1,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["page_size"], 1)
        self.assertEqual(payload["total_pages"], 2)
        self.assertTrue(payload["has_next"])
        self.assertEqual(len(payload["results"]), 1)
        self.assertIn("teams", payload["facets"])

        oversized = self.client.get(
            "/api/v1/player-seasons/derived-stats",
            {
                "competition": "EPL",
                "season": "2025-26",
                "page_size": 501,
            },
        )
        self.assertEqual(oversized.status_code, 400)
        self.assertIn("between 1 and 500", oversized.json()["detail"])

    def test_list_endpoint_ranks_rate_adjusted_values_against_the_full_scope(self):
        self._materialize()
        PlayerSeasonDerivedStats.objects.filter(canonical_player=self.alpha).update(
            shots_on_target=10,
            minutes=900,
        )
        PlayerSeasonDerivedStats.objects.filter(canonical_player=self.beta).update(
            shots_on_target=20,
            minutes=3000,
        )

        response = self.client.get(
            "/api/v1/player-seasons/derived-stats",
            {
                "competition": "EPL",
                "season": "2025-26",
                "position_group": "FWD",
                "include": "scope_percentiles",
                "rate_mode": "per90",
                "page_size": 1,
                "sort": "-shots_on_target",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"][0]["canonical_player_name"], "Alpha Forward")
        self.assertAlmostEqual(payload["results"][0]["scope_percentiles"]["shots_on_target"], 75.0)

    def test_projected_cohort_returns_only_requested_metrics(self):
        self._materialize()

        response = self.client.get(
            "/api/v1/player-seasons/cohort",
            {
                "competition": "EPL",
                "season": "2025-26",
                "position_group": "FWD",
                "metric": ["xg_per_90", "xa_per_90"],
                "include_percentiles": 0,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 2)
        self.assertEqual(
            set(payload["results"][0]["metrics"]),
            {"xg_per_90", "xa_per_90"},
        )
        self.assertTrue(all(value is None for value in payload["results"][0]["percentiles"].values()))

        with patch("ingestion.cohort_api.MAX_COHORT_CELLS", 1):
            oversized = self.client.get(
                "/api/v1/player-seasons/cohort",
                {
                    "competition": "EPL",
                    "season": "2025-26",
                    "position_group": "FWD",
                    "metric": ["xg_per_90", "xa_per_90"],
                },
            )
        self.assertEqual(oversized.status_code, 400)
        self.assertIn("metric cells", oversized.json()["detail"])

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

    def test_profile_distributions_are_bounded_and_match_the_league_position_cohort(self):
        self._materialize()

        response = self.client.get(
            f"/api/v1/player-seasons/derived-stats/{self.alpha.id}",
            {
                "competition": "EPL",
                "season": "2025-26",
                "include": "meta,profile_distributions",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["profile_distributions"]
        distribution = payload["metrics"]["xg_per_90"]
        self.assertEqual(payload["position_group"], "FWD")
        self.assertEqual(payload["cohort_count"], 2)
        self.assertLessEqual(len(distribution["bins"]), PROFILE_DISTRIBUTION_BIN_COUNT)
        self.assertEqual(sum(entry["count"] for entry in distribution["bins"]), distribution["count"])
        self.assertEqual(distribution["count"], 2)
        self.assertLess(distribution["p25"], distribution["p75"])
        self.assertEqual(payload["context"]["competition_code"], "EPL")
        self.assertNotIn("canonical_player_name", distribution)

    def test_distribution_helpers_cover_sparse_and_constant_values(self):
        self.assertEqual(quantile([4.0], 0.75), 4.0)
        self.assertEqual(quantile([1.0, 3.0], 0.25), 1.5)
        self.assertEqual(
            distribution_bins([2.0, 2.0, 2.0]),
            [{"start": 2.0, "end": 2.0, "count": 3}],
        )

    def test_big5_scope_percentiles_are_returned_without_replacing_league_percentiles(self):
        season = Season.objects.create(label="2026-27", sort_order=2027)
        eng = Competition.objects.create(name="English Premier League", short_code="ENG1", country="England")
        ger = Competition.objects.create(name="Bundesliga", short_code="GER1", country="Germany")
        eng_cs = CompetitionSeason.objects.create(competition=eng, season=season, is_published=True)
        ger_cs = CompetitionSeason.objects.create(competition=ger, season=season, is_published=True)
        team = CanonicalTeam.objects.create(name="Scope FC", reep_id="scope-team")

        def make_row(name: str, cs: CompetitionSeason, xg_per_90: float, stored_pct: float, minutes: int = 900):
            player = CanonicalPlayer.objects.create(display_name=name, reep_id=f"scope-{name}")
            return PlayerSeasonDerivedStats.objects.create(
                competition_season=cs,
                canonical_player=player,
                canonical_display_team=team,
                formula_version="v-test",
                position_group=PositionGroup.FWD,
                native_position="F",
                minutes=minutes,
                percentiles_eligible=minutes >= 600,
                xg_per_90=xg_per_90,
                xg_per_90_percentile=stored_pct,
                is_current=True,
            )

        low = make_row("Low Forward", eng_cs, 1.0, 99.0)
        make_row("Mid Forward", ger_cs, 2.0, 50.0)
        make_row("High Forward", ger_cs, 3.0, 75.0)
        make_row("Short Sample", eng_cs, 100.0, 100.0, minutes=200)

        response = self.client.get(
            f"/api/v1/player-seasons/derived-stats/{low.canonical_player_id}",
            {
                "competition": "ENG1",
                "season": "2026-27",
                "include": "scope_percentiles,profile_distributions",
                "percentile_scope": "BIG5",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["percentiles"]["xg_per_90"], 99.0)
        self.assertAlmostEqual(payload["scope_percentiles"]["xg_per_90"], 16.6666666667)
        self.assertEqual(payload["scope_percentile_context"]["competition_code"], "BIG5")
        self.assertEqual(payload["profile_distributions"]["cohort_count"], 1)
        self.assertEqual(payload["scope_profile_distributions"]["cohort_count"], 3)
        self.assertEqual(
            payload["scope_profile_distributions"]["context"]["competition_code"],
            "BIG5",
        )

    def test_all_scope_percentiles_cache_isolated_by_position_group(self):
        season = Season.objects.create(label="2028-29", sort_order=2029)
        eng = Competition.objects.create(name="English Premier League", short_code="ENG1", country="England")
        sco = Competition.objects.create(name="Scottish Premiership", short_code="SCO1", country="Scotland")
        eng_cs = CompetitionSeason.objects.create(competition=eng, season=season, is_published=True)
        sco_cs = CompetitionSeason.objects.create(competition=sco, season=season, is_published=True)
        team = CanonicalTeam.objects.create(name="All Scope FC", reep_id="all-scope-team")

        def make_row(
            name: str,
            cs: CompetitionSeason,
            position_group: PositionGroup,
            xg_per_90: float,
        ):
            player = CanonicalPlayer.objects.create(display_name=name, reep_id=f"all-scope-{name}")
            return PlayerSeasonDerivedStats.objects.create(
                competition_season=cs,
                canonical_player=player,
                canonical_display_team=team,
                formula_version="v-test",
                position_group=position_group,
                native_position="P",
                minutes=900,
                percentiles_eligible=True,
                xg_per_90=xg_per_90,
                is_current=True,
            )

        forward = make_row("Forward", eng_cs, PositionGroup.FWD, 1.0)
        make_row("Forward Peer", sco_cs, PositionGroup.FWD, 3.0)
        defender = make_row("Defender", eng_cs, PositionGroup.DEF, 2.0)
        make_row("Defender Peer", sco_cs, PositionGroup.DEF, 4.0)

        forward_response = self.client.get(
            f"/api/v1/player-seasons/derived-stats/{forward.canonical_player_id}",
            {
                "competition": "ENG1",
                "season": "2028-29",
                "include": "scope_percentiles",
                "percentile_scope": "ALL",
            },
        )
        defender_response = self.client.get(
            f"/api/v1/player-seasons/derived-stats/{defender.canonical_player_id}",
            {
                "competition": "ENG1",
                "season": "2028-29",
                "include": "scope_percentiles",
                "percentile_scope": "ALL",
            },
        )

        self.assertEqual(forward_response.status_code, 200)
        self.assertEqual(defender_response.status_code, 200)
        self.assertAlmostEqual(forward_response.json()["scope_percentiles"]["xg_per_90"], 25.0)
        self.assertAlmostEqual(defender_response.json()["scope_percentiles"]["xg_per_90"], 25.0)
        self.assertFalse(MaterializedApiPayload.objects.filter(cache_key__startswith="scope-percentiles:").exists())

    def test_big5_scope_percentiles_work_for_goalkeepers(self):
        season = Season.objects.create(label="2027-28", sort_order=2028)
        eng = Competition.objects.create(name="English Premier League", short_code="ENG1", country="England")
        ita = Competition.objects.create(name="Serie A", short_code="ITA1", country="Italy")
        eng_cs = CompetitionSeason.objects.create(competition=eng, season=season, is_published=True)
        ita_cs = CompetitionSeason.objects.create(competition=ita, season=season, is_published=True)
        team = CanonicalTeam.objects.create(name="Keeper FC", reep_id="keeper-team")

        def make_row(name: str, cs: CompetitionSeason, saves_per_90: float, stored_pct: float):
            player = CanonicalPlayer.objects.create(display_name=name, reep_id=f"keeper-{name}")
            return PlayerSeasonGkDerivedStats.objects.create(
                competition_season=cs,
                canonical_player=player,
                canonical_display_team=team,
                formula_version="gk-test",
                minutes=900,
                appearances=10,
                percentiles_eligible=True,
                saves_per_90=saves_per_90,
                saves_per_90_percentile=stored_pct,
                is_current=True,
            )

        low = make_row("Low Keeper", eng_cs, 2.0, 91.0)
        make_row("High Keeper", ita_cs, 4.0, 88.0)

        response = self.client.get(
            f"/api/v1/player-seasons/gk-derived-stats/{low.canonical_player_id}",
            {
                "competition": "ENG1",
                "season": "2027-28",
                "include": "scope_percentiles,profile_distributions",
                "percentile_scope": "BIG5",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["percentiles"]["saves_per_90"], 91.0)
        self.assertEqual(payload["scope_percentiles"]["appearances"], None)
        self.assertAlmostEqual(payload["scope_percentiles"]["saves_per_90"], 25.0)
        self.assertEqual(payload["profile_distributions"]["cohort_count"], 1)
        self.assertEqual(payload["scope_profile_distributions"]["cohort_count"], 2)
        self.assertNotIn(
            "appearances",
            payload["scope_profile_distributions"]["metrics"],
        )
