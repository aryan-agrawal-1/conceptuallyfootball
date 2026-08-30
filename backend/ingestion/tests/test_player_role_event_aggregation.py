from types import SimpleNamespace

from django.test import SimpleTestCase

from ingestion.models import MatchEventGameState, MatchEventType
from ingestion.services.player_role_aggregation import CompactMatchBatch, PlayerRoleFeatureAccumulator
from ingestion.services.player_role_event_aggregation import aggregate_non_possession_batch
from ingestion.services.player_state_comparison import action_context


class PlayerRoleEventAggregationTests(SimpleTestCase):
    def test_batch_matches_legacy_action_context_and_shares_team_work(self):
        base = {
            "provider_match_id": 1, "team_id": 10, "timeline_seconds": 20,
            "event_type": MatchEventType.PASS, "outcome_successful": True,
            "x": 2000, "y": 5000, "end_x": 7000, "end_y": 5000,
            "is_touch": True, "is_progressive_pass": True,
            "is_final_third_entry": True, "is_box_entry": False,
            "is_key_pass": True, "is_shot_assist": False, "is_cross": False,
            "is_long_ball": False, "is_through_ball": False, "is_throw_in": False,
            "is_corner": False, "is_free_kick": False, "is_set_piece": False,
            "is_big_chance": False, "is_defensive": False, "shot_situation": None,
            "shot_outcome": None,
        }
        events = [base | {"id": 1, "event_index": 1, "player_id": 100},
                  base | {"id": 2, "event_index": 2, "player_id": 101, "timeline_seconds": 21}]
        exposures = tuple({
            "id": player_id, "player_interval__participation__provider_match_id": 1,
            "player_interval__participation__team_id": 10,
            "player_interval__participation__player_id": player_id,
            "team_episode__episode_index": 0, "start_second": 0, "end_second": 90,
            "coarse_state": MatchEventGameState.DRAWING,
        } for player_id in (100, 101))
        accumulators = {
            (player_id, 10): PlayerRoleFeatureAccumulator(player_id, 10, 1)
            for player_id in (100, 101)
        }
        batch = CompactMatchBatch(
            matches=({"id": 1},), events=tuple(events), exposures=exposures,
        )
        aggregate_non_possession_batch(batch, accumulators)

        legacy_event = SimpleNamespace(**events[0])
        legacy = action_context([legacy_event], [], 90, include_defensive_families=False)
        player = accumulators[(100, 10)].overall_player.to_context(90)
        self.assertEqual(player["summary"], legacy["summary"])
        self.assertEqual(player["passing"], legacy["passing"])
        self.assertEqual(player["touch_location"], legacy["touch_location"])
        self.assertEqual(accumulators[(100, 10)].overall_team.counters["pass_attempts"], 2)
        self.assertEqual(accumulators[(101, 10)].overall_team.counters["pass_attempts"], 2)
        self.assertEqual(accumulators[(100, 10)].states["drawing"].exposure.seconds, 90)

    def test_half_open_exposure_excludes_boundary_event(self):
        accumulator = PlayerRoleFeatureAccumulator(100, 10, 1)
        event = {
            "id": 1, "provider_match_id": 1, "event_index": 1, "team_id": 10,
            "player_id": 100, "timeline_seconds": 90, "event_type": MatchEventType.PASS,
            "is_set_piece": False, "is_corner": False, "is_free_kick": False,
            "is_throw_in": False, "shot_situation": None,
        }
        exposure = {
            "id": 1, "player_interval__participation__provider_match_id": 1,
            "player_interval__participation__team_id": 10,
            "player_interval__participation__player_id": 100,
            "team_episode__episode_index": 0, "start_second": 0, "end_second": 90,
            "coarse_state": MatchEventGameState.DRAWING,
        }
        aggregate_non_possession_batch(
            CompactMatchBatch(matches=({"id": 1},), events=(event,), exposures=(exposure,)),
            {(100, 10): accumulator},
        )
        self.assertEqual(accumulator.overall_player.counters["pass_attempts"], 0)
