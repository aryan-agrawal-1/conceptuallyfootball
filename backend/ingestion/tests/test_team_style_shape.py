from types import SimpleNamespace
from datetime import datetime, timezone
import json

from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIRequestFactory

from ingestion.models import (
    MatchEventShotSituation,
    MatchEventType,
    Competition,
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    MatchEventGameState,
    MatchEventPeriod,
    MatchGameStateStatus,
    MatchStateDrawProvenance,
    MatchStatePhase,
    CanonicalTeam,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchStatus,
    ProviderMatchTeamGameStateEpisode,
    Season,
    TeamSeasonEventProfile,
)
from ingestion.team_style_shape_api import TeamStyleShapeApi
from ingestion.services.team_style_shape import (
    DEFAULT_AXIS_KEYS,
    STYLE_PERCENTILE_VERSION,
    attach_cohort_distributions,
    build_style_cohort,
    percentile_rank,
    signed_shift,
)
from ingestion.state_lens import StateLens, StateLensScope


def event(event_type, index=1, **values):
    defaults = {
        "event_type": event_type,
        "event_index": index,
        "provider_match_id": 1,
        "x": 2000,
        "y": 5000,
        "end_x": 5000,
        "end_y": 5000,
        "outcome_successful": True,
        "is_progressive_pass": False,
        "is_box_entry": False,
        "is_defensive": False,
        "shot_situation": MatchEventShotSituation.OPEN_PLAY,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


class TeamStyleShapeTests(SimpleTestCase):
    def test_axes_reuse_physical_pass_and_qualified_defensive_contracts(self):
        passes = [
            event(
                MatchEventType.PASS,
                index=index,
                end_x=5000 + index * 10,
                is_progressive_pass=index <= 15,
                is_box_entry=index <= 4,
            )
            for index in range(1, 36)
        ]
        passes[0].outcome_successful = False
        defensive = [
            event(MatchEventType.BALL_RECOVERY, index=100 + index, x=2500 + index * 10)
            for index in range(10)
        ]
        defensive.extend(
            event(
                MatchEventType.CHALLENGE,
                index=200 + index,
                x=7000,
                is_defensive=True,
            )
            for index in range(20)
        )
        carries = [
            SimpleNamespace(
                is_progressive_carry=index <= 5,
                is_box_entry=index <= 2,
                is_final_third_entry=index <= 4,
            )
            for index in range(10)
        ]
        possessions = [
            {
                "is_counter_launch": True,
                "counter_final_third_arrival": index <= 2,
                "counter_shot": index == 1,
                "counter_speed_mps": 3.0 + index,
                "provider_fast_break_shot_count": 0,
            }
            for index in range(5)
        ]
        settled_blocks = [
            {"settled_defensive_average_x": 4200 + index * 100}
            for index in range(5)
        ]

        payload = build_style_cohort(
            passes + defensive + [event(MatchEventType.SHOT, index=300)]
            + [event(MatchEventType.SHOT, index=301, shot_situation=MatchEventShotSituation.PENALTY)],
            exposure_seconds=1800,
            carries=carries,
            possessions=possessions,
            settled_blocks=settled_blocks,
            scope={"state": "all"},
            match_count=4,
            episode_count=8,
        )

        self.assertEqual(set(payload["axes"]), set(DEFAULT_AXIS_KEYS))
        self.assertEqual(payload["axes"]["pass_directness"]["raw"]["forward_attempts"], 35)
        self.assertEqual(payload["axes"]["circulation_security"]["raw"]["completed_passes"], 34)
        self.assertEqual(payload["axes"]["carry_progression"]["value"], 0.6)
        self.assertEqual(payload["axes"]["shot_frequency"]["raw"]["excluded_penalty_shots"], 1)
        self.assertEqual(payload["axes"]["settled_block_height"]["raw"]["settled_block_possessions"], 5)
        self.assertEqual(payload["axes"]["counter_arrival"]["value"], 0.6)
        self.assertEqual(payload["axes"]["defensive_action_height"]["reliability"], "verified")

    def test_sparse_axes_keep_raw_value_but_withhold_percentile_eligibility(self):
        payload = build_style_cohort(
            [event(MatchEventType.PASS)],
            exposure_seconds=60,
            scope={"state": "winning"},
        )

        axis = payload["axes"]["circulation_security"]
        self.assertEqual(axis["value"], 1.0)
        self.assertEqual(axis["reliability"], "sparse")
        self.assertFalse(axis["percentile_eligible"])
        self.assertIsNone(axis["percentile"])

    def test_percentile_is_midrank_and_distribution_is_prevalence_not_quality(self):
        self.assertEqual(percentile_rank(2, [1, 2, 3]), 50.0)
        self.assertEqual(percentile_rank(2, [2]), 50.0)
        first = build_style_cohort(
            [event(MatchEventType.PASS, index=index) for index in range(35)],
            exposure_seconds=1800,
            scope={"state": "all"},
        )
        second = build_style_cohort(
            [event(MatchEventType.PASS, index=index, end_x=7000) for index in range(35)],
            exposure_seconds=1800,
            scope={"state": "all"},
        )
        third = build_style_cohort(
            [event(MatchEventType.PASS, index=index, end_x=1000) for index in range(35)],
            exposure_seconds=1800,
            scope={"state": "all"},
        )
        cohorts = {1: first, 2: second, 3: third}
        distributions = attach_cohort_distributions(
            cohorts,
            target_team_id=1,
            team_names={1: "One", 2: "Two", 3: "Three"},
        )
        row = distributions["pass_length"]
        self.assertEqual(row["percentile_version"], STYLE_PERCENTILE_VERSION)
        self.assertEqual(row["higher_means"], "prevalence")
        self.assertEqual(row["sample_size"], 3)
        self.assertEqual(cohorts[1]["axes"]["pass_length"]["percentile"], 50.0)
        self.assertTrue(any(member["target"] for member in row["members"]))

    def test_signed_shift_is_raw_and_robustly_normalised(self):
        selected = build_style_cohort(
            [event(MatchEventType.PASS, index=index, end_x=7000) for index in range(35)],
            exposure_seconds=1800,
            scope={"state": "winning"},
        )
        baseline = build_style_cohort(
            [event(MatchEventType.PASS, index=index, end_x=1000) for index in range(35)],
            exposure_seconds=1800,
            scope={"state": "drawing"},
        )
        distributions = attach_cohort_distributions(
            {1: selected, 2: baseline},
            target_team_id=1,
        )
        shifts = signed_shift(selected, baseline, distributions)
        directness = shifts["pass_directness"]
        self.assertGreater(directness["raw_delta"], 0)
        self.assertIsNotNone(directness["normalised_delta"])
        self.assertEqual(directness["direction"], "prevalence")


class TeamStyleShapeApiTests(TestCase):
    def setUp(self):
        competition = Competition.objects.create(name="Test League", short_code="TST")
        season = Season.objects.create(label="2025-26", sort_order=2026)
        self.competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
            has_whoscored=True,
            whoscored_league="test",
            whoscored_season="2025-26",
            whoscored_expected_match_count=1,
            expected_team_count=1,
            refresh_enabled=True,
            is_published=True,
        )
        self.team = CanonicalTeam.objects.create(name="Focal")
        self.match = ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id="style-1",
            competition_season=self.competition_season,
            kickoff_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            status=ProviderMatchStatus.COMPLETED,
            home_provider_team_id="focal",
            away_provider_team_id="opponent",
            home_team=self.team,
            away_team=self.team,
            home_score=1,
            away_score=0,
        )
        run = IngestionRun.objects.create(
            kind=IngestionKind.EVENT_PROFILES,
            competition_season=self.competition_season,
        )
        self.profile = TeamSeasonEventProfile.objects.create(
            competition_season=self.competition_season,
            team=self.team,
            materialized_ingestion_run=run,
            observed_match_count=1,
        )
        ProviderMatchGameState.objects.create(
            provider_match=self.match,
            status=MatchGameStateStatus.VERIFIED,
            eligible=True,
            calculation_version="team_game_state_v1",
            exposure_seconds=1800,
            episode_count=2,
            focal_team_count=1,
            calculated_at=datetime.now(timezone.utc),
        )
        self.episode(0, 0, 900, MatchEventGameState.DRAWING, 0, MatchStateDrawProvenance.NEUTRAL)
        self.episode(1, 900, 1800, MatchEventGameState.WINNING, 1, MatchStateDrawProvenance.NONE)
        for index in range(1, 71):
            state_offset = 0 if index <= 35 else 900
            self.event(index, ((index - 1) % 35) * 25 + state_offset, end_x=5000, progressive=index <= 12)
        for index in range(100, 105):
            self.event(index, 1000 + index, event_type=MatchEventType.SHOT, end_x=None)

    def episode(self, index, start, end, state, difference, provenance):
        ProviderMatchTeamGameStateEpisode.objects.create(
            provider_match=self.match,
            focal_team=self.team,
            focal_is_home=True,
            episode_index=index,
            period=MatchEventPeriod.FIRST_HALF,
            phase=MatchStatePhase.FIRST_HALF,
            start_second=start,
            end_second=end,
            duration_seconds=end - start,
            focal_score=max(difference, 0),
            opponent_score=max(-difference, 0),
            goal_difference=difference,
            state=state,
            draw_provenance=provenance,
            state_entry_second=start,
            state_age_seconds_at_start=0,
            calculation_version="team_game_state_v1",
        )

    def event(self, index, seconds, *, event_type=MatchEventType.PASS, end_x=5000, progressive=False):
        return ProviderMatchEvent.objects.create(
            provider_match=self.match,
            event_index=index,
            provider_event_sequence_id=str(index),
            provider_team_id="focal",
            team=self.team,
            period=MatchEventPeriod.FIRST_HALF,
            minute=seconds // 60,
            second=seconds % 60,
            match_seconds=seconds,
            timeline_seconds=seconds,
            event_type=event_type,
            outcome_successful=True if event_type == MatchEventType.PASS else None,
            x=2000,
            y=5000,
            end_x=end_x,
            end_y=5000 if end_x is not None else None,
            is_progressive_pass=progressive,
            shot_situation=(
                MatchEventShotSituation.OPEN_PLAY
                if event_type == MatchEventType.SHOT
                else MatchEventShotSituation.UNKNOWN
            ),
        )

    def call(self, query):
        request = APIRequestFactory().get("/api/v1/team-seasons/style-shape/1", query)
        return TeamStyleShapeApi.as_view()(request, canonical_team_id=self.team.id)

    def test_public_contract_contains_overall_selected_baseline_and_state_shift(self):
        response = self.call({"competition": "TST", "season": "2025-26", "state": "winning", "baseline_state": "drawing"})
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["contract_version"], "v1")
        self.assertEqual(payload["selected"]["scope"]["state"], "winning")
        self.assertEqual(payload["baseline"]["scope"]["state"], "drawing")
        self.assertEqual(payload["overall"]["scope"]["state"], "all")
        self.assertIn("pass_length", payload["axis_definitions"][0]["key"])
        self.assertIn("selected_minus_baseline", payload["comparison"])
        self.assertEqual(payload["comparison"]["selected_minus_baseline"]["pass_directness"]["direction"], "prevalence")
        self.assertEqual(payload["state_lens"]["evidence"]["exposure_seconds"], 900)

    def test_axis_selection_validation_and_materialized_cache_are_deterministic(self):
        params = {"competition": "TST", "season": "2025-26", "axes": "pass_length,shot_frequency"}
        first = self.call(params)
        second = self.call(params)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first["X-Materialized-Payload"], "miss")
        self.assertEqual(second["X-Materialized-Payload"], "hit")
        self.assertEqual(set(json.loads(first.content)["selected"]["axes"]), {"pass_length", "shot_frequency"})
        invalid = self.call({"competition": "TST", "season": "2025-26", "axes": "pass_length,nope"})
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("Unknown Team Style Shape axis", str(invalid.data["detail"]))

    def test_full_season_cohort_load_is_query_bounded(self):
        lens = StateLens(StateLensScope(), StateLensScope(state="drawing"))

        def build_and_count():
            with CaptureQueriesContext(connection) as queries:
                payload = TeamStyleShapeApi().build_payload(
                    TeamSeasonEventProfile.objects.get(pk=self.profile.id),
                    None,
                    lens,
                )
            return len(queries), payload

        initial_queries, initial_payload = build_and_count()
        run = IngestionRun.objects.get(pk=self.profile.materialized_ingestion_run_id)
        for index in range(4):
            team = CanonicalTeam.objects.create(name=f"Cohort {index}")
            TeamSeasonEventProfile.objects.create(
                competition_season=self.competition_season,
                team=team,
                materialized_ingestion_run=run,
                observed_match_count=0,
            )
        expanded_queries, expanded_payload = build_and_count()

        self.assertLessEqual(initial_queries, 30)
        self.assertLessEqual(expanded_queries, initial_queries + 2)
        self.assertNotIn("distribution", initial_payload["overall"]["axes"]["pass_length"])
        self.assertLess(len(json.dumps(expanded_payload, separators=(",", ":"))), 250_000)
