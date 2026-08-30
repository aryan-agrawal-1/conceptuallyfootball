from django.test import SimpleTestCase

from ingestion.models import MatchEventGameState, MatchEventShotOutcome, MatchStateDrawProvenance
from ingestion.services.player_role_aggregation import ExposureInterval, ExposureIntervalIndex
from ingestion.services.player_role_score_events import score_event_index_from_rows


class PlayerRoleScoreEventIndexTests(SimpleTestCase):
    def test_indexes_goals_and_assists_once_with_team_and_exposure_isolation(self):
        exposure = ExposureIntervalIndex([
            ExposureInterval(1, 10, 100, 0, 90, "drawing", 0),
            ExposureInterval(1, 10, 101, 0, 90, "drawing", 0),
            ExposureInterval(1, 11, 100, 0, 90, "drawing", 0),
        ])
        events = [
            {"id": 1, "provider_match_id": 1, "event_index": 5, "team_id": 10,
             "player_id": 101, "timeline_seconds": 70, "shot_outcome": None,
             "is_goal_disallowed": False, "is_deleted_event": False,
             "is_intentional_assist": True, "game_state_before": MatchEventGameState.DRAWING},
            {"id": 2, "provider_match_id": 1, "event_index": 6, "team_id": 10,
             "player_id": 100, "timeline_seconds": 80, "shot_outcome": MatchEventShotOutcome.GOAL,
             "is_goal_disallowed": False, "is_deleted_event": False,
             "is_intentional_assist": False, "game_state_before": MatchEventGameState.DRAWING},
            {"id": 3, "provider_match_id": 1, "event_index": 7, "team_id": 10,
             "player_id": 100, "timeline_seconds": 90, "shot_outcome": MatchEventShotOutcome.GOAL,
             "is_goal_disallowed": False, "is_deleted_event": False,
             "is_intentional_assist": False, "game_state_before": MatchEventGameState.WINNING},
        ]
        context = {2: {"transition": "drawing_to_winning",
                       "draw_provenance": MatchStateDrawProvenance.RESTORED,
                       "clutch_eligible": True}}
        index = score_event_index_from_rows(
            events, exposure, context, {(100, 10), (101, 10), (100, 11)}
        )

        scorer = index.evidence(100, 10)
        assister = index.evidence(101, 10)
        self.assertEqual(scorer["goals"], 1)
        self.assertEqual(scorer["state_changing_goals"], 1)
        self.assertEqual(scorer["restored_draw_winning_goals"], 1)
        self.assertEqual(assister["intentional_assists"], 1)
        self.assertEqual(assister["state_changing_assists"], 1)
        self.assertEqual(index.evidence(100, 11)["goals"], 0)
