from datetime import datetime, timezone
import json
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIRequestFactory

from ingestion.lead_control_api import TeamLeadControlApi
from ingestion.models import (
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    MatchEventGameState,
    MatchEventPeriod,
    MatchEventShotOutcome,
    MatchEventShotSituation,
    MatchEventType,
    MatchGameStateStatus,
    MatchStateDrawProvenance,
    MatchStatePhase,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchPossession,
    ProviderMatchPossessionBuild,
    ProviderMatchPossessionEvent,
    ProviderMatchTeamGameStateEpisode,
    ProviderMatchStatus,
    Season,
)
from ingestion.services.lead_control import (
    LEAD_BAND_MULTI_GOAL,
    LEAD_BAND_ONE_GOAL,
    StateLens,
    StateLensScope,
    build_lead_control_payload,
    build_lead_windows,
    build_matched_baseline_windows,
    lead_band,
    quadrant_for,
)


def episode(
    match_id,
    index,
    *,
    state="winning",
    goal_difference=1,
    phase="second_half",
    start=1800,
    end=3600,
    entry=1800,
    entry_event_index=None,
):
    return SimpleNamespace(
        provider_match_id=match_id,
        episode_index=index,
        state=state,
        goal_difference=goal_difference,
        phase=phase,
        start_second=start,
        end_second=end,
        duration_seconds=end - start,
        state_entry_second=entry,
        state_age_seconds_at_start=start - entry,
        state_entry_event_index=entry_event_index,
        entry_event_index=entry_event_index,
        draw_provenance="none" if state == "winning" else "neutral",
    )


def event(
    match_id,
    index,
    second,
    *,
    team_id=10,
    provider_team_id="home",
    event_type=MatchEventType.PASS,
    x=4000,
    end_x=5000,
    is_touch=False,
    is_box_entry=False,
    is_big_chance=False,
    outcome_successful=True,
    **overrides,
):
    values = dict(
        provider_match_id=match_id,
        event_index=index,
        timeline_seconds=second,
        match_seconds=second,
        team_id=team_id,
        provider_team_id=provider_team_id,
        event_type=event_type,
        x=x,
        y=5000,
        end_x=end_x,
        end_y=5000,
        is_touch=is_touch,
        is_box_entry=is_box_entry,
        is_big_chance=is_big_chance,
        outcome_successful=outcome_successful,
        is_deleted_event=False,
        is_defensive=False,
        is_progressive_pass=False,
        shot_outcome=MatchEventShotOutcome.UNKNOWN,
        shot_situation=MatchEventShotSituation.OPEN_PLAY,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def possession(match_id, index, second, *, team_id=10, start_x=2000, end_x=7000, counter=False):
    return SimpleNamespace(
        provider_match_id=match_id,
        possession_index=index,
        start_second=second,
        end_second=second + 15,
        team_id=team_id,
        provider_team_id="home" if team_id == 10 else "away",
        start_x=start_x,
        end_x=end_x,
        is_counter_launch=counter,
        is_ambiguous=False,
    )


class LeadControlRuleTests(SimpleTestCase):
    def test_lead_bands_and_clock_goal_difference_matching_are_explicit(self):
        self.assertEqual(lead_band(1), LEAD_BAND_ONE_GOAL)
        self.assertEqual(lead_band(2), LEAD_BAND_MULTI_GOAL)
        self.assertIsNone(lead_band(0))

        lead = episode(1, 4, start=1800, end=2700, goal_difference=1)
        same_clock_draw = episode(
            2,
            7,
            state="drawing",
            goal_difference=0,
            start=1800,
            end=2700,
        )
        wrong_goal_difference = episode(
            3,
            8,
            state="drawing",
            goal_difference=0,
            phase="first_half",
            start=1800,
            end=2700,
        )
        lead_windows = build_lead_windows([lead])
        baseline_windows = build_matched_baseline_windows(
            lead_windows,
            [same_clock_draw, wrong_goal_difference],
        )
        self.assertEqual(len(lead_windows), 1)
        self.assertEqual(len(baseline_windows), 1)
        self.assertEqual(baseline_windows[0].match_id, 2)
        self.assertEqual(baseline_windows[0].goal_difference, 0)
        self.assertEqual(baseline_windows[0].phase, "second_half")

    def test_components_and_process_evidence_are_decomposable(self):
        lead_episode = episode(1, 0, start=1800, end=2700, entry_event_index=1)
        draw_episode = episode(
            2,
            0,
            state="drawing",
            goal_difference=0,
            start=1800,
            end=2700,
        )
        events = [
            # The entry goal is explicitly excluded from post-lead behaviour.
            event(1, 1, 1800, event_type=MatchEventType.SHOT, is_box_entry=True),
            event(1, 2, 1850, x=3000, end_x=6000, is_touch=True),
            event(1, 3, 1900, x=3200, end_x=7000, is_box_entry=True),
            event(1, 4, 2000, event_type=MatchEventType.CLEARANCE, x=1800),
            event(1, 5, 2050, event_type=MatchEventType.SHOT, x=8500),
            event(
                1,
                6,
                2100,
                team_id=20,
                provider_team_id="away",
                event_type=MatchEventType.SHOT,
                x=8200,
                is_big_chance=True,
            ),
            event(2, 2, 1850, x=6000, end_x=7000, is_touch=True),
            event(2, 3, 1900, x=6000, end_x=7000),
            event(2, 4, 2000, event_type=MatchEventType.SHOT, x=8000),
        ]
        payload = build_lead_control_payload(
            events,
            [lead_episode, draw_episode],
            [possession(1, 0, 1850, counter=True), possession(2, 0, 1850)],
            focal_team_id=10,
            team_name="Home",
            focal_provider_by_match={1: "home", 2: "home"},
            matches=[
                SimpleNamespace(pk=1, home_team_id=10, home_score=1, away_score=0),
                SimpleNamespace(pk=2, home_team_id=10, home_score=0, away_score=0),
            ],
            match_references={1: 0, 2: 1},
        )
        gravity = payload["selected"]["gravity"]["components"]
        ownership = payload["selected"]["ownership"]["components"]
        self.assertEqual(payload["selected"]["episode_count"], 1)
        self.assertEqual(payload["selected"]["event_count"], 5)
        self.assertEqual(gravity["pass_origin_height"]["count"], 2)
        self.assertEqual(gravity["clearances"]["count"], 1)
        self.assertEqual(ownership["opponent_shots"]["count"], 1)
        self.assertEqual(ownership["own_counters"]["count"], 1)
        self.assertEqual(ownership["opponent_shots"]["baseline_value"] is not None, True)
        self.assertEqual(payload["selected"]["lead_band_breakdown"]["one_goal"]["episode_count"], 1)
        self.assertEqual(payload["selected"]["lead_band_breakdown"]["multi_goal"]["episode_count"], 0)
        self.assertEqual(payload["episodes"][0]["time_to_first_meaningful_opponent_attack_seconds"], 300)
        self.assertEqual(payload["comparison"]["baseline_goal_difference"], 0)

    def test_sparse_sample_withholds_quadrant_label_but_keeps_raw_components(self):
        lead_episode = episode(1, 0, start=0, end=600, entry=0, goal_difference=1)
        draw_episode = episode(2, 0, state="drawing", goal_difference=0, start=0, end=600)
        payload = build_lead_control_payload(
            [event(1, 2, 20, x=3000, end_x=6000), event(2, 2, 20, x=6000, end_x=7000)],
            [lead_episode, draw_episode],
            [],
            focal_team_id=10,
            focal_provider_by_match={1: "home", 2: "home"},
        )
        self.assertFalse(payload["quadrant"]["placement"]["available"])
        self.assertIsNone(payload["quadrant"]["placement"]["label"])
        self.assertEqual(payload["selected"]["gravity"]["components"]["pass_origin_height"]["count"], 1)

    def test_quadrant_labels_are_descriptive_and_not_strength_claims(self):
        axes = {
            "behavioral_retreat": {"value": 20},
            "process_control": {"value": 80},
        }
        placement = quadrant_for(axes, eligible=True)
        self.assertEqual(placement["label"], "assertive controllers")
        self.assertIn("not a causal", placement["note"])


class TeamLeadControlApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        competition = Competition.objects.create(name="Test League", short_code="TST")
        season = Season.objects.create(label="2025-26", sort_order=2026)
        cls.competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
            has_whoscored=True,
            whoscored_league="test",
            whoscored_season="2526",
            is_published=True,
        )
        cls.home = CanonicalTeam.objects.create(name="Home")
        cls.away = CanonicalTeam.objects.create(name="Away")
        cls.match = ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id="lead-control-api-test",
            competition_season=cls.competition_season,
            kickoff_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            status=ProviderMatchStatus.COMPLETED,
            home_provider_team_id="home",
            away_provider_team_id="away",
            home_team=cls.home,
            away_team=cls.away,
            home_score=1,
            away_score=0,
        )
        ProviderMatchGameState.objects.create(
            provider_match=cls.match,
            status=MatchGameStateStatus.VERIFIED,
            eligible=True,
            calculation_version="team_game_state_v1",
            calculated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        ProviderMatchTeamGameStateEpisode.objects.create(
            provider_match=cls.match,
            focal_team=cls.home,
            focal_is_home=True,
            episode_index=0,
            period=MatchEventPeriod.SECOND_HALF,
            phase=MatchStatePhase.SECOND_HALF,
            start_second=1800,
            end_second=3600,
            duration_seconds=1800,
            focal_score=1,
            opponent_score=0,
            goal_difference=1,
            state=MatchEventGameState.WINNING,
            draw_provenance=MatchStateDrawProvenance.NONE,
            state_entry_second=1800,
            state_age_seconds_at_start=0,
            calculation_version="team_game_state_v1",
        )
        ProviderMatchEvent.objects.create(
            provider_match=cls.match,
            event_index=1,
            provider_event_sequence_id="1",
            provider_team_id="home",
            team=cls.home,
            period=MatchEventPeriod.SECOND_HALF,
            minute=30,
            second=0,
            timeline_seconds=1810,
            match_seconds=1810,
            event_type=MatchEventType.PASS,
            outcome_successful=True,
            x=3000,
            y=5000,
            end_x=6000,
            end_y=5000,
        )
        build = ProviderMatchPossessionBuild.objects.create(
            provider_match=cls.match,
            calculation_version="possession_context_v1",
            possession_count=1,
            included_event_count=1,
            calculated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        possession = ProviderMatchPossession.objects.create(
            build=build,
            provider_match=cls.match,
            possession_index=0,
            identity="lead-control-possession",
            provider_team_id="home",
            team=cls.home,
            period=MatchEventPeriod.SECOND_HALF,
            start_second=1810,
            end_second=1810,
            duration_seconds=0,
            start_x=3000,
            start_y=5000,
            end_x=6000,
            end_y=5000,
            action_count=1,
            termination_reason="period_end",
            launch_type="turnover_recovery",
            is_counter_launch=True,
        )
        ProviderMatchPossessionEvent.objects.create(
            possession=possession,
            event=ProviderMatchEvent.objects.get(provider_match=cls.match),
            sequence=0,
            is_control_action=True,
        )

    def request(self, **params):
        request = APIRequestFactory().get(
            "/api/v1/team-seasons/lead-control/1",
            {"competition": "TST", "season": "2025-26", **params},
        )
        return TeamLeadControlApi.as_view()(request, canonical_team_id=self.home.id)

    def test_api_is_cached_and_returns_public_contract(self):
        first = self.request()
        repeated = self.request()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first["X-Materialized-Payload"], "miss")
        self.assertEqual(repeated["X-Materialized-Payload"], "hit")
        payload = json.loads(first.content)
        self.assertEqual(payload["team"]["name"], "Home")
        self.assertIn("gravity", payload["selected"])
        self.assertIn("ownership", payload["selected"])
        self.assertIn("clock_matching", payload["comparison"])
        self.assertNotIn("provider_team_id", first.content.decode())

    def test_api_reuses_state_lens_validation(self):
        response = self.request(state="winning", goal_difference=-1)
        self.assertEqual(response.status_code, 400)
        self.assertIn("goal_difference", str(response.data["detail"]))
