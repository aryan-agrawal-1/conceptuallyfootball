from datetime import datetime, timezone
from copy import deepcopy
import json
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIRequestFactory

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
    CanonicalPlayer,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchPossession,
    ProviderMatchPossessionBuild,
    ProviderMatchPossessionEvent,
    ProviderMatchPlayerInterval,
    ProviderMatchPlayerParticipation,
    ProviderMatchPlayerParticipationBuild,
    ProviderMatchStatus,
    Season,
)
from ingestion.services.transition_leverage import (
    _ladder_for_observations,
    _build_scope,
    classify_state_transition,
    possession_observation,
)
from ingestion.state_lens import StateLensScope
from ingestion.transition_leverage_api import TeamTransitionLeverageApi


class LinkManager:
    def __init__(self, links):
        self.links = links

    def all(self):
        return self.links


def fake_event(index, team="home", event_type=MatchEventType.PASS, **overrides):
    values = {
        "event_index": index,
        "provider_team_id": team,
        "team_id": 10 if team == "home" else 20,
        "team": SimpleNamespace(name="Home" if team == "home" else "Away"),
        "player_id": index,
        "player": SimpleNamespace(name=f"Player {index}"),
        "period": MatchEventPeriod.FIRST_HALF,
        "timeline_seconds": index,
        "match_seconds": index,
        "event_type": event_type,
        "outcome_successful": True,
        "is_deleted_event": False,
        "is_goal_disallowed": False,
        "game_state_before": MatchEventGameState.DRAWING,
        "game_state_after": MatchEventGameState.DRAWING,
        "home_score_before": 0,
        "away_score_before": 0,
        "home_score_after": 0,
        "away_score_after": 0,
        "x": 3000,
        "y": 5000,
        "end_x": 3500,
        "end_y": 5000,
        "shot_outcome": MatchEventShotOutcome.UNKNOWN,
        "shot_situation": MatchEventShotSituation.OPEN_PLAY,
        "is_progressive_pass": False,
        "is_final_third_entry": False,
        "is_box_entry": False,
        "is_key_pass": False,
        "is_shot_assist": False,
        "is_intentional_assist": False,
        "is_big_chance": False,
        "is_set_piece": False,
        "is_throw_in": False,
        "is_corner": False,
        "is_free_kick": False,
        "is_through_ball": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def fake_possession(events, *, provider_team_id="home", **overrides):
    values = {
        "identity": "possession-1",
        "provider_team_id": provider_team_id,
        "team_id": 10 if provider_team_id == "home" else 20,
        "team": SimpleNamespace(name="Home" if provider_team_id == "home" else "Away"),
        "period": MatchEventPeriod.FIRST_HALF,
        "start_second": events[0].timeline_seconds,
        "end_second": events[-1].timeline_seconds,
        "duration_seconds": events[-1].timeline_seconds - events[0].timeline_seconds,
        "start_x": events[0].x,
        "start_y": events[0].y,
        "end_x": events[-1].x,
        "end_y": events[-1].y,
        "launch_type": "turnover_recovery",
        "termination_reason": "goal",
        "is_ambiguous": False,
    }
    values.update(overrides)
    links = [
        SimpleNamespace(
            sequence=index,
            event=event,
            is_control_action=event.provider_team_id == provider_team_id,
            is_settled_defensive_action=False,
        )
        for index, event in enumerate(events)
    ]
    return SimpleNamespace(event_links=LinkManager(links), **values)


class TransitionLeverageRuleTests(SimpleTestCase):
    match = SimpleNamespace(
        home_team_id=10,
        away_team_id=20,
        home_provider_team_id="home",
        away_provider_team_id="away",
    )
    focal_team = SimpleNamespace(id=10, name="Home")

    def test_named_state_transition_shapes_retain_exact_score_boundaries(self):
        self.assertEqual(
            classify_state_transition("losing", "drawing", before_goal_difference=-1, after_goal_difference=0)["classification"],
            "losing_to_drawing",
        )
        self.assertEqual(
            classify_state_transition("drawing", "winning", before_goal_difference=0, after_goal_difference=1)["classification"],
            "drawing_to_winning",
        )
        self.assertEqual(
            classify_state_transition("winning", "drawing", before_goal_difference=1, after_goal_difference=0)["classification"],
            "winning_to_drawing",
        )
        self.assertEqual(
            classify_state_transition("winning", "winning", before_goal_difference=1, after_goal_difference=2)["classification"],
            "one_goal_to_multi_goal_lead",
        )

    def test_trace_preserves_assist_contest_penalty_and_goal_boundary(self):
        events = [
            fake_event(1, event_type=MatchEventType.BALL_RECOVERY),
            fake_event(
                2,
                event_type=MatchEventType.PASS,
                is_progressive_pass=True,
                is_final_third_entry=True,
                end_x=7000,
            ),
            fake_event(
                3,
                team="away",
                event_type=MatchEventType.CHALLENGE,
                outcome_successful=False,
                player_id=None,
                player=None,
            ),
            fake_event(
                4,
                event_type=MatchEventType.PASS,
                is_shot_assist=True,
                is_intentional_assist=True,
                is_box_entry=True,
                end_x=9000,
                end_y=5000,
            ),
            fake_event(
                5,
                event_type=MatchEventType.SHOT,
                shot_situation=MatchEventShotSituation.PENALTY,
                shot_outcome=MatchEventShotOutcome.GOAL,
                is_big_chance=True,
                game_state_before=MatchEventGameState.DRAWING,
                game_state_after=MatchEventGameState.WINNING,
                home_score_after=1,
            ),
        ]
        observation = possession_observation(
            fake_possession(events),
            match=self.match,
            focal_team=self.focal_team,
            match_ref=0,
        )
        self.assertEqual(observation["outcome_tier"], "goal")
        self.assertTrue(observation["outcome_ladder"]["box_entry"]["reached"])
        self.assertEqual(observation["score"]["situation"], "penalty")
        self.assertEqual(observation["state_transition"]["classification"], "drawing_to_winning")
        self.assertEqual(len(observation["possession_trace"]), 5)
        self.assertEqual(observation["possession_trace"][0]["role"], "origin_recovery")
        self.assertEqual(observation["possession_trace"][2]["role"], "contest")
        self.assertEqual(observation["possession_trace"][3]["role"], "creation")
        self.assertEqual(observation["possession_trace"][-1]["role"], "terminal")
        self.assertTrue(observation["possession_trace"][2]["flags"]["contested"])

    def test_own_goal_is_against_focal_and_not_an_attacking_goal(self):
        own_goal = fake_event(
            12,
            event_type=MatchEventType.OWN_GOAL,
            game_state_before=MatchEventGameState.WINNING,
            game_state_after=MatchEventGameState.DRAWING,
            home_score_before=1,
            away_score_before=0,
            home_score_after=1,
            away_score_after=1,
        )
        observation = possession_observation(
            fake_possession([own_goal]),
            match=self.match,
            focal_team=self.focal_team,
            match_ref=0,
        )
        self.assertEqual(observation["score"]["goal_type"], "own_goal")
        self.assertEqual(observation["score"]["perspective"], "against")
        self.assertEqual(observation["direction_ladder"]["goal"], False)
        self.assertEqual(observation["state_transition"]["classification"], "winning_to_drawing")
        self.assertEqual(
            observation["state_transition"]["directional_classification"],
            "winning_to_drawing_against",
        )
        concession = _ladder_for_observations([observation], direction="concession")
        self.assertEqual(concession["opportunities"], 1)
        self.assertEqual(concession["outcome_ladder"][0]["count"], 0)
        self.assertEqual(concession["outcome_ladder"][-1]["count"], 1)

    def test_opponent_contest_cannot_advance_the_owning_team_ladder(self):
        events = [
            fake_event(1, event_type=MatchEventType.BALL_RECOVERY),
            fake_event(
                2,
                team="away",
                event_type=MatchEventType.CHALLENGE,
                outcome_successful=False,
                x=9000,
                end_x=9500,
            ),
        ]
        observation = possession_observation(
            fake_possession(events),
            match=self.match,
            focal_team=self.focal_team,
            match_ref=0,
        )
        self.assertEqual(observation["outcome_tier"], "possession")
        self.assertFalse(observation["outcome_ladder"]["territorial_entry"]["reached"])
        self.assertEqual(observation["possession_trace"][1]["role"], "contest")

    def test_restart_and_rapid_turnover_metadata_stay_inspectable(self):
        restart = possession_observation(
            fake_possession(
                [fake_event(1, event_type=MatchEventType.PASS, is_set_piece=True)],
                launch_type="restart",
                termination_reason="restart",
            ),
            match=self.match,
            focal_team=self.focal_team,
            match_ref=0,
        )
        self.assertEqual(restart["launch_type"], "restart")
        self.assertEqual(restart["termination_reason"], "restart")
        self.assertTrue(restart["possession_trace"][0]["flags"]["restart"])

        rapid = possession_observation(
            fake_possession(
                [
                    fake_event(2, event_type=MatchEventType.BALL_RECOVERY),
                    fake_event(3, event_type=MatchEventType.PASS, end_x=8000),
                ],
                is_counter_launch=True,
                counter_elapsed_seconds=1,
                counter_forward_metres=24.5,
                counter_speed_mps=24.5,
                counter_outcome="final_third_arrival",
                diagnostics={"qualifies_counter_progress": True},
            ),
            match=self.match,
            focal_team=self.focal_team,
            match_ref=0,
        )
        self.assertEqual(
            rapid["rapid_transition"],
            {
                "is_counter_launch": True,
                "qualifies_forward_progress": True,
                "elapsed_seconds": 1,
                "forward_metres": 24.5,
                "speed_mps": 24.5,
                "outcome": "final_third_arrival",
            },
        )

    def test_player_evidence_references_bounded_shared_traces(self):
        events = [
            fake_event(index, event_type=MatchEventType.BALL_TOUCH)
            for index in range(1, 9)
        ]
        template = possession_observation(
            fake_possession(events),
            match=self.match,
            focal_team=self.focal_team,
            match_ref=0,
        )
        observations = []
        for index in range(100):
            observation = deepcopy(template)
            observation["possession_id"] = f"bounded-{index}"
            observation["observation_ref"] = f"0:bounded-{index}"
            observations.append(observation)

        class IntervalManager(LinkManager):
            pass

        players = []
        for player_id in range(1, 9):
            players.append(
                SimpleNamespace(
                    player_id=player_id,
                    team_id=10,
                    player=SimpleNamespace(display_name=f"Player {player_id}"),
                    intervals=IntervalManager(
                        [
                            SimpleNamespace(
                                start_second=0,
                                end_second=120,
                                duration_seconds=120,
                                confidence="verified",
                            )
                        ]
                    ),
                    status="verified",
                    confidence="verified",
                    roster_role="starter",
                )
            )
        scope = _build_scope(
            observations,
            matches=[SimpleNamespace(id=1)],
            all_matches=[SimpleNamespace(id=1)],
            focal_team=self.focal_team,
            scope=StateLensScope(),
            episodes_by_match={1: []},
            participation_by_match={1: players},
            excluded_match_reasons={},
            eligible_match_ids={1},
            excluded_reasons={},
            ambiguous_count=0,
        )
        serialized = json.dumps(scope, separators=(",", ":"))
        self.assertLess(len(serialized), 2_000_000)
        self.assertEqual(len(scope["observations"]), 100)
        self.assertTrue(scope["players"])
        self.assertTrue(scope["players"][0]["evidence"])
        self.assertTrue(
            all("possession_trace" not in evidence for row in scope["players"] for evidence in row["evidence"])
        )
        self.assertTrue(
            all(
                evidence["observation_ref"] in {row["observation_ref"] for row in scope["observations"]}
                for row in scope["players"]
                for evidence in row["evidence"]
            )
        )


class TeamTransitionLeverageApiTests(TestCase):
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
        cls.player = CanonicalPlayer.objects.create(display_name="Verified Player")
        cls.match = ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id="transition-api-test",
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
        from ingestion.models import ProviderMatchTeamGameStateEpisode

        ProviderMatchTeamGameStateEpisode.objects.create(
            provider_match=cls.match,
            focal_team=cls.home,
            focal_is_home=True,
            episode_index=0,
            period=MatchEventPeriod.FIRST_HALF,
            phase=MatchStatePhase.FIRST_HALF,
            start_second=0,
            end_second=5400,
            duration_seconds=5400,
            focal_score=1,
            opponent_score=0,
            goal_difference=1,
            state=MatchEventGameState.WINNING,
            draw_provenance=MatchStateDrawProvenance.NONE,
            state_entry_second=0,
            state_age_seconds_at_start=0,
            calculation_version="team_game_state_v1",
        )
        event = ProviderMatchEvent.objects.create(
            provider_match=cls.match,
            event_index=1,
            provider_event_sequence_id="1",
            provider_team_id="home",
            team=cls.home,
            period=MatchEventPeriod.FIRST_HALF,
            minute=1,
            second=0,
            timeline_seconds=60,
            match_seconds=60,
            event_type=MatchEventType.PASS,
            outcome_successful=True,
            x=3000,
            y=5000,
            end_x=7000,
            end_y=5000,
            is_progressive_pass=True,
            is_final_third_entry=True,
        )
        event.player = cls.player
        event.provider_player_id = "home-player"
        event.save(update_fields=["player", "provider_player_id"])
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
            identity="transition-api-possession",
            provider_team_id="home",
            team=cls.home,
            period=MatchEventPeriod.FIRST_HALF,
            start_second=60,
            end_second=60,
            duration_seconds=0,
            start_x=3000,
            start_y=5000,
            end_x=7000,
            end_y=5000,
            action_count=1,
            termination_reason="period_end",
            launch_type="turnover_recovery",
        )
        ProviderMatchPossessionEvent.objects.create(
            possession=possession,
            event=event,
            sequence=0,
            is_control_action=True,
        )
        participation_build = ProviderMatchPlayerParticipationBuild.objects.create(
            provider_match=cls.match,
            status="verified",
            formula_version="player_participation_v1",
            participant_count=1,
            verified_participant_count=1,
            verified_seconds=5400,
            calculated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        participant = ProviderMatchPlayerParticipation.objects.create(
            build=participation_build,
            provider_match=cls.match,
            provider_team_id="home",
            team=cls.home,
            provider_player_id="home-player",
            player=cls.player,
            roster_role="starter",
            position_role="outfield",
            status="verified",
            confidence="verified",
            on_pitch_seconds=5400,
            interval_count=1,
        )
        ProviderMatchPlayerInterval.objects.create(
            participation=participant,
            sequence=0,
            start_second=0,
            end_second=5400,
            duration_seconds=5400,
            start_evidence="lineup_starter",
            end_evidence="match_end",
            confidence="verified",
        )

    def request(self, **params):
        request = APIRequestFactory().get(
            "/api/v1/team-seasons/transition-leverage/1",
            {"competition": "TST", "season": "2025-26", **params},
        )
        response = TeamTransitionLeverageApi.as_view()(request, canonical_team_id=self.home.id)
        return response

    def test_api_is_cached_and_keeps_attack_and_concession_separate(self):
        first = self.request()
        repeated = self.request()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first["X-Materialized-Payload"], "miss")
        self.assertEqual(repeated["X-Materialized-Payload"], "hit")
        payload = json.loads(first.content)
        self.assertEqual(payload["selected"]["attacking"]["opportunities"], 1)
        self.assertEqual(payload["selected"]["concession"]["opportunities"], 0)
        player = payload["selected"]["player_involvement"][0]
        self.assertEqual(player["opportunities"], 1)
        self.assertEqual(player["involved_possessions"], 1)
        self.assertEqual(player["sequence_stages"]["origin_recovery"]["possessions"], 1)
        self.assertEqual(player["coverage"]["selected_verified_seconds"], 5400)
        self.assertEqual(
            player["evidence"][0]["observation_ref"],
            payload["selected"]["observations"][0]["observation_ref"],
        )
        self.assertNotIn("possession_trace", player["evidence"][0])
        self.assertEqual(payload["selected"]["observations"][0]["possession_trace"][0]["event_type"], "pass")
        self.assertNotIn("action_evidence", payload["selected"]["observations"][0])
        self.assertNotIn("provider_team_id", first.content.decode())
