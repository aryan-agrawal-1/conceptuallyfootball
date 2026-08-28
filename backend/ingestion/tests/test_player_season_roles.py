from unittest.mock import patch

from django.test import SimpleTestCase

from ingestion.services.player_season_roles import (
    CLOSE_ROLE_MARGIN,
    ROLE_MEANINGS,
    RoleCandidate,
    assign_role,
    score_role_candidates,
    weighted_average,
)


def state(exposure_seconds=18_000, **summary_changes):
    summary = {
        "touches": 120,
        "actions": 180,
        "pass_attempts": 100,
        "pass_completions": 85,
        "progressive_passes": 12,
        "progressive_carries": 6,
        "progressive_actions": 18,
        "carries": 20,
        "shots": 10,
        "goals": 2,
        "defensive_actions": 15,
    } | summary_changes
    shares = {
        key: {"share": value}
        for key, value in {
            "touches": 0.12,
            "passes": 0.13,
            "progressive_actions": 0.15,
            "progressive_carries": 0.18,
            "shots": 0.2,
            "defensive_actions": 0.1,
        }.items()
    }
    return {
        "exposure_seconds": exposure_seconds,
        "summary": summary,
        "passing": {"completion_rate": summary["pass_completions"] / summary["pass_attempts"]},
        "carrying": {"mean_forward_metres": 7.0},
        "team_action_shares": shares,
        "touch_location": {"x": 50.0, "y": 50.0, "sample_size": summary["touches"]},
        "team_touch_location": {"x": 50.0, "y": 50.0, "sample_size": 500},
        "touch_grid": [
            {"share": 0.6},
            {"share": 0.4},
        ],
    }


def features(**changes):
    rows = {name: state() for name in ("losing", "drawing", "winning")}
    return {
        "position_group": "FWD",
        "states": rows,
        "state_coverage": {name: {"exposure_seconds": row["exposure_seconds"]} for name, row in rows.items()},
        "winning_goals": 2,
        "state_changing_goals": 2,
        "total_goals": 6,
        "transition_exposure_seconds": rows["losing"]["exposure_seconds"] + rows["drawing"]["exposure_seconds"],
    } | changes


class PlayerSeasonRoleScoringTests(SimpleTestCase):
    def candidate(self, rows, label):
        return next(row for row in score_role_candidates(rows) if row.label == label)

    def test_every_role_has_one_explicit_score_contract(self):
        candidates = score_role_candidates(features())
        self.assertEqual({candidate.label for candidate in candidates}, set(ROLE_MEANINGS))
        self.assertTrue(all(candidate.components for candidate in candidates))

    def test_closer_requires_two_actual_winning_state_goals(self):
        one_goal = self.candidate(features(winning_goals=1), "Closer")
        two_goals = self.candidate(features(winning_goals=2), "Closer")
        self.assertFalse(one_goal.eligible)
        self.assertIsNone(one_goal.score)
        self.assertTrue(two_goals.eligible)
        self.assertIsNotNone(two_goals.score)

    def test_clutch_requires_two_actual_state_changing_goals(self):
        one_goal = self.candidate(features(state_changing_goals=1), "Clutch response")
        two_goals = self.candidate(features(state_changing_goals=2), "Clutch response")
        self.assertFalse(one_goal.eligible)
        self.assertTrue(two_goals.eligible)

    def test_near_tie_keeps_winner_runner_up_and_mixed_confidence(self):
        candidates = [
            RoleCandidate("Unlocker", 0.8, True, {"signal": 0.8}),
            RoleCandidate("Outlet", 0.8 - CLOSE_ROLE_MARGIN / 2, True, {"signal": 0.7}),
        ]
        with patch("ingestion.services.player_season_roles.score_role_candidates", return_value=candidates):
            result = assign_role(features())
        self.assertEqual(result["primary_role"], "Unlocker")
        self.assertEqual(result["runner_up_role"], "Outlet")
        self.assertEqual(result["confidence"], "mixed")

    def test_no_role_is_explicit_when_evidence_is_insufficient(self):
        sparse = features()
        for row in sparse["state_coverage"].values():
            row["exposure_seconds"] = 60
        with patch(
            "ingestion.services.player_season_roles.score_role_candidates",
            return_value=[RoleCandidate("Unlocker", None, False, {}, "unsupported")],
        ):
            result = assign_role(sparse)
        self.assertIsNone(result["primary_role"])
        self.assertEqual(result["confidence"], "insufficient")
        self.assertIn("Role not established", result["explanation"])

    def test_multi_team_stint_shares_are_exposure_weighted(self):
        self.assertAlmostEqual(weighted_average([(0.1, 900), (0.3, 2700)]), 0.25)
