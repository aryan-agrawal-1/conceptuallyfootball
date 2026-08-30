from django.test import SimpleTestCase

from ingestion.models import MatchEventGameState, MatchEventType
from ingestion.services.player_role_aggregation import CompactMatchBatch, PlayerRoleFeatureAccumulator
from ingestion.services.player_role_transition_aggregation import aggregate_transition_batch


class PlayerRoleTransitionAggregationTests(SimpleTestCase):
    def test_formats_one_possession_and_projects_only_verified_participants(self):
        match = {"id": 1, "home_team_id": 10, "away_team_id": 11,
                 "home_provider_team_id": "h", "away_provider_team_id": "a"}
        event = {
            "id": 20, "provider_match_id": 1, "event_index": 5,
            "provider_team_id": "h", "team_id": 10, "player_id": 100,
            "timeline_seconds": 30, "match_seconds": 30, "event_type": MatchEventType.PASS,
            "outcome_successful": True, "x": 3000, "y": 5000, "end_x": 7000,
            "end_y": 5000, "is_progressive_pass": True, "is_final_third_entry": True,
            "is_box_entry": False, "is_key_pass": False, "is_shot_assist": False,
            "is_intentional_assist": False, "is_through_ball": False,
            "is_big_chance": False, "is_goal_disallowed": False,
            "is_deleted_event": False, "event_type": MatchEventType.PASS,
            "game_state_before": MatchEventGameState.DRAWING,
            "game_state_after": MatchEventGameState.DRAWING,
            "home_score_before": 0, "away_score_before": 0,
            "home_score_after": 0, "away_score_after": 0,
        }
        possession = {
            "id": 30, "provider_match_id": 1, "possession_index": 1,
            "identity": "1:1", "provider_team_id": "h", "team_id": 10,
            "start_second": 30, "end_second": 31, "is_ambiguous": False,
            "is_counter_launch": True, "counter_final_third_arrival": True,
            "counter_box_arrival": False, "counter_shot": False,
            "counter_outcome": "final_third_arrival", "state_segments": [],
        }
        exposure = {
            "id": 40, "player_interval__participation__provider_match_id": 1,
            "player_interval__participation__team_id": 10,
            "player_interval__participation__player_id": 100,
            "team_episode__episode_index": 0, "start_second": 0, "end_second": 90,
            "coarse_state": MatchEventGameState.DRAWING,
        }
        batch = CompactMatchBatch(
            matches=(match,), events=(event,), exposures=(exposure,), possessions=(possession,),
            possession_events=({"id": 50, "possession_id": 30, "event_id": 20,
                                "sequence": 0, "is_control_action": True,
                                "is_settled_defensive_action": False},),
            possession_participants=({"id": 60, "possession_id": 30, "player_id": 100,
                                      "first_event_index": 5, "action_count": 1},),
        )
        accumulator = PlayerRoleFeatureAccumulator(100, 10, 1)
        aggregate_transition_batch(batch, {(100, 10): accumulator}, match_refs={1: 0})

        transition = accumulator.transition
        self.assertEqual(transition.counters["opportunities"], 1)
        self.assertEqual(transition.counters["involved_possessions"], 1)
        self.assertEqual(transition.counters["counter_possessions"], 1)
        self.assertEqual(transition.counters["final_third_possessions"], 1)
        self.assertEqual(transition.stage_actions["origin_recovery"], 1)
        self.assertEqual(len(transition.evidence.to_json()), 1)

    def test_ambiguous_possession_never_formats_detailed_evidence(self):
        batch = CompactMatchBatch(
            matches=({"id": 1, "home_team_id": 10, "away_team_id": 11},),
            possessions=({"id": 1, "provider_match_id": 1, "possession_index": 1,
                          "identity": "p", "team_id": 10, "is_ambiguous": True},),
            possession_participants=({"id": 1, "possession_id": 1, "player_id": 100,
                                      "first_event_index": 1, "action_count": 1},),
        )
        accumulator = PlayerRoleFeatureAccumulator(100, 10, 1)
        aggregate_transition_batch(batch, {(100, 10): accumulator})
        self.assertEqual(accumulator.transition.counters["ambiguous_excluded"], 1)
        self.assertEqual(accumulator.transition.counters["involved_possessions"], 0)
        self.assertEqual(accumulator.transition.evidence.to_json(), [])
