from types import SimpleNamespace

from django.test import SimpleTestCase

from ingestion.models import MatchEventShotOutcome

from ingestion.services.player_role_definitions import (
    ARCHETYPE_DEFINITIONS,
    ESTABLISHED_EXPOSURE_SECONDS,
    HYBRID_MARGIN,
    PROVISIONAL_EXPOSURE_SECONDS,
    TRAIT_DEFINITIONS,
)
from ingestion.services.player_season_roles import (
    assign_classification,
    raw_candidates,
    score_candidate_cohort,
    score_traits,
    trait_raw,
)
from ingestion.services.player_role_features import clutch_context_counts, direct_assist_events


def state(exposure_seconds=12_000):
    return {
        "exposure_seconds": exposure_seconds,
        "rates": {
            "touches": {"per_90": 50.0},
            "pass_attempts": {"per_90": 35.0},
            "progressive_actions": {"per_90": 7.0},
            "defensive_actions": {"per_90": 5.0},
        },
        "touch_location": {"x": 50.0, "y": 50.0, "sample_size": 40},
        "team_touch_location": {"x": 50.0, "y": 50.0, "sample_size": 300},
        "touch_grid": [{"share": 0.6}, {"share": 0.4}],
    }


def features(*, group="MID", exposure_seconds=ESTABLISHED_EXPOSURE_SECONDS, multiplier=1.0):
    def count(number):
        return round(number * multiplier)

    geometry = {
        "open_play_events": count(800), "touches": count(500), "passes": count(350),
        "completed_passes": count(300), "pass_completion": 0.86,
        "central_touches": count(300), "central_touch_share": 0.6,
        "advanced_actions": count(120), "advanced_touches": count(100), "advanced_touch_share": 0.2,
        "box_touches": count(30), "box_touch_share": 0.06, "shots": count(18),
        "key_passes": count(15), "line_breaking_passes": count(25), "line_break_frequency": 0.07,
        "build_up_passes": count(180), "build_up_progressive_passes": count(30),
        "central_progressive_passes": count(35), "dangerous_entries": count(30),
        "long_progressive_passes": count(60), "defensive_actions": count(70),
        "deep_defensive_actions": count(35), "protective_interventions": count(15),
        "ball_wins": count(45), "tackles_interceptions": count(25), "defensive_height": 48.0,
        "aerials": count(30), "turnovers": count(12), "set_piece_actions": count(20),
        "set_piece_creation": count(5), "sweeper_actions": count(10), "sweeper_height": 25.0,
        "saves": count(25), "close_range_saves": count(12),
        "rates_per90": {
            "touches": 50 * multiplier, "passes": 35 * multiplier,
            "line_breaking_passes": 2.5 * multiplier, "box_touches": 3 * multiplier,
            "shots": 2 * multiplier, "key_passes": 1.5 * multiplier,
            "defensive_actions": 7 * multiplier, "ball_wins": 4.5 * multiplier,
            "deep_defensive_actions": 3.5 * multiplier, "aerials": 3 * multiplier,
            "turnovers": 1.2 * multiplier, "sweeper_actions": 1 * multiplier,
            "saves": 2.5 * multiplier,
        },
    }
    team_geometry = {key: item * 5 if isinstance(item, int) else item for key, item in geometry.items()}
    return {
        "position": {"group": group, "recorded": "Central Midfielder", "average_touch": {"x": 48.0, "y": 50.0}},
        "exposure": {"verified_seconds": exposure_seconds, "matches": 20, "episodes": 50},
        "overall": {
            "summary": {
                "progressive_passes": count(55), "progressive_carries": count(20),
                "progressive_actions": count(75), "carries": count(70),
            },
            "passing": {},
            "carrying": {"mean_forward_metres": 8.0, "final_third_entries": count(12), "box_entries": count(4)},
            "geometry": geometry,
            "team_geometry": team_geometry,
            "team_action_shares": {
                "touches": {"share": 0.12}, "passes": {"share": 0.14},
                "progressive_actions": {"share": 0.18}, "progressive_carries": {"share": 0.2},
                "shots": {"share": 0.15}, "defensive_actions": {"share": 0.1},
            },
        },
        "states": {name: state() for name in ("losing", "drawing", "winning")},
        "state_spatial": {
            "observed_states": ["losing", "drawing", "winning"], "mean_centroid_movement": 3.0,
            "mean_relative_movement": 9.0, "mean_heatmap_overlap": 0.9, "location_samples": 120,
        },
        "transitions": {
            "available": True, "opportunities": 100, "involved_possessions": count(25),
            "advancement_actions": count(12), "escape_actions": count(8),
        },
        "score_events": {
            "state_changing_goals": 3, "state_changing_assists": 1,
            "winning_state_goals": 2, "winning_state_assists": 1,
        },
    }


class PlayerSeasonRoleScoringTests(SimpleTestCase):
    def test_neutral_draw_winner_is_excluded_from_clutch_context(self):
        restored = SimpleNamespace(id=1)
        neutral = SimpleNamespace(id=2)
        counts = clutch_context_counts(
            [restored, neutral],
            {
                1: {"transition": "drawing_to_winning", "draw_provenance": "restored", "clutch_eligible": True},
                2: {"transition": "drawing_to_winning", "draw_provenance": "neutral", "clutch_eligible": False},
            },
            "goals",
        )
        self.assertEqual(counts["restored_draw_winning_goals"], 1)
        self.assertEqual(counts["neutral_draw_winning_goals_excluded"], 1)

    def test_direct_assist_resolution_uses_only_the_final_flagged_pass(self):
        def event(event_id, second, *, player_id, assist=False, goal=False):
            return SimpleNamespace(
                id=event_id, provider_match_id=1, team_id=10, player_id=player_id,
                timeline_seconds=second, event_index=event_id, is_deleted_event=False,
                is_intentional_assist=assist, is_goal_disallowed=False,
                shot_outcome=MatchEventShotOutcome.GOAL if goal else MatchEventShotOutcome.UNKNOWN,
            )

        early = event(1, 80, player_id=100, assist=True)
        direct = event(2, 95, player_id=200, assist=True)
        goal = event(3, 100, player_id=300, goal=True)
        resolved = direct_assist_events([early, direct, goal])
        self.assertNotIn((100, 10), resolved)
        self.assertEqual(resolved[(200, 10)][0], (direct, goal))

    def test_every_archetype_has_an_explicit_candidate_contract(self):
        labels = {candidate.label for candidate in raw_candidates(features())}
        self.assertEqual(labels, set(ARCHETYPE_DEFINITIONS))
        self.assertTrue(all(definition["components"] for definition in ARCHETYPE_DEFINITIONS.values()))
        self.assertTrue(all(definition["minimum_evidence"] for definition in ARCHETYPE_DEFINITIONS.values()))

    def test_goalkeeper_and_outfield_candidate_pools_are_separate(self):
        outfield = {row.label for row in raw_candidates(features()) if row.eligible}
        goalkeeper = {row.label for row in raw_candidates(features(group="GK")) if row.eligible}
        self.assertFalse(outfield & {"Sweeper Keeper", "Goalkeeper Distributor", "Shot Stopper"})
        self.assertTrue(goalkeeper)
        self.assertLessEqual(goalkeeper, {"Sweeper Keeper", "Goalkeeper Distributor", "Shot Stopper"})

    def test_line_breaking_playmaker_requires_geometric_pass_evidence(self):
        supported = next(row for row in raw_candidates(features()) if row.label == "Line-Breaking Playmaker")
        sparse = features()
        sparse["overall"]["geometry"]["line_breaking_passes"] = 9
        unsupported = next(row for row in raw_candidates(sparse) if row.label == "Line-Breaking Playmaker")
        self.assertTrue(supported.eligible)
        self.assertFalse(unsupported.eligible)

    def test_cohort_percentiles_do_not_apply_distribution_quotas(self):
        rows = [features(multiplier=0.7), features(multiplier=1.0), features(multiplier=1.3)]
        scored = score_candidate_cohort(rows)
        connectors = [next(candidate for candidate in row if candidate["archetype"] == "Connector") for row in scored]
        self.assertLess(connectors[0]["fit"], connectors[-1]["fit"])
        self.assertEqual(len(connectors), 3)

    def test_evidence_confidence_is_separate_from_hybrid_shape(self):
        candidates = [
            {"archetype": "Connector", "fit": 0.80},
            {"archetype": "Line-Breaking Playmaker", "fit": 0.80 - HYBRID_MARGIN / 2},
        ]
        provisional = assign_classification(features(exposure_seconds=PROVISIONAL_EXPOSURE_SECONDS), candidates, [])
        established = assign_classification(features(exposure_seconds=ESTABLISHED_EXPOSURE_SECONDS), candidates, [])
        self.assertEqual(provisional["classification_shape"], "hybrid")
        self.assertEqual(provisional["evidence_confidence"], "provisional")
        self.assertEqual(established["classification_shape"], "hybrid")
        self.assertEqual(established["evidence_confidence"], "established")

    def test_under_450_minutes_is_honestly_unclassified(self):
        result = assign_classification(
            features(exposure_seconds=PROVISIONAL_EXPOSURE_SECONDS - 1),
            [{"archetype": "Connector", "fit": 0.99}],
            [],
        )
        self.assertIsNone(result["primary_archetype"])
        self.assertEqual(result["classification_shape"], "unclassified")
        self.assertEqual(result["evidence_confidence"], "insufficient")

    def test_clutch_and_lead_extender_are_independent_traits(self):
        labels = {row["trait"] for row in score_traits([features()])[0]}
        self.assertIn("Clutch", labels)
        self.assertIn("Lead Extender", labels)

    def test_adaptive_and_state_resilient_can_both_be_supported(self):
        contracts = trait_raw(features())
        self.assertTrue(contracts["Adaptive"]["eligible"])
        self.assertTrue(contracts["State-resilient"]["eligible"])
        self.assertGreater(contracts["Adaptive"]["raw"], 0)
        self.assertGreater(contracts["State-resilient"]["raw"], 0)

    def test_every_trait_has_plain_language_meaning(self):
        self.assertEqual(set(trait_raw(features())), set(TRAIT_DEFINITIONS))
        self.assertTrue(all(TRAIT_DEFINITIONS.values()))
