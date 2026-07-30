from django.test import SimpleTestCase

from ingestion.derived_definitions import METRIC_DEFINITIONS
from ingestion.gk_definitions import GK_METRIC_DEFINITIONS


class MetricSemanticColorTests(SimpleTestCase):
    def test_negative_metric_exceptions_are_explicit(self):
        expected = {
            "fouls",
            "fouls_per_90",
            "errors_lead_to_goal_per_90",
            "inaccurate_pass_rate",
            "shots_off_target",
            "offsides",
            "offsides_per_90",
        }

        self.assertEqual(
            {
                key
                for key, definition in METRIC_DEFINITIONS.items()
                if definition["semantic_color"] == "negative"
            },
            expected,
        )

    def test_contextual_metric_exceptions_are_explicit(self):
        expected_outfield = {
            "clearances_per_90",
            "blocks_per_90",
            "defensive_action_density",
        }
        expected_goalkeeper = {"runs_out", "runs_out_per_90"}

        self.assertEqual(
            {
                key
                for key, definition in METRIC_DEFINITIONS.items()
                if definition["semantic_color"] == "contextual"
            },
            expected_outfield,
        )
        self.assertEqual(
            {
                key
                for key, definition in GK_METRIC_DEFINITIONS.items()
                if definition["semantic_color"] == "contextual"
            },
            expected_goalkeeper,
        )

    def test_positive_is_the_default_for_every_other_metric(self):
        allowed = {"positive", "negative", "contextual"}
        all_definitions = {
            **METRIC_DEFINITIONS,
            **{f"gk:{key}": value for key, value in GK_METRIC_DEFINITIONS.items()},
        }

        self.assertTrue(all_definitions)
        self.assertEqual(
            {definition["semantic_color"] for definition in all_definitions.values()} - allowed,
            set(),
        )
        self.assertEqual(METRIC_DEFINITIONS["xg_per_90"]["semantic_color"], "positive")
        self.assertEqual(GK_METRIC_DEFINITIONS["saves_per_90"]["semantic_color"], "positive")
