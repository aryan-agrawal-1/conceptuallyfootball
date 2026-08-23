from types import SimpleNamespace

from django.test import SimpleTestCase

from ingestion.models import MatchEventType
from ingestion.services.pass_state import (
    PASS_STATE_EVENT_LIMIT,
    build_pass_state_evidence,
    comparison_delta,
    physical_vector,
)


def pass_event(
    x,
    y,
    end_x,
    end_y,
    *,
    completed=True,
    progressive=False,
):
    return SimpleNamespace(
        event_type=MatchEventType.PASS,
        x=x,
        y=y,
        end_x=end_x,
        end_y=end_y,
        outcome_successful=completed,
        is_progressive_pass=progressive,
    )


class PassStateEvidenceTests(SimpleTestCase):
    def test_physical_length_uses_105_by_68_pitch(self):
        forward, lateral, length = physical_vector(
            pass_event(0, 0, 10_000, 10_000)
        )

        self.assertEqual((forward, lateral), (105.0, 68.0))
        self.assertAlmostEqual(length, 125.096, places=3)

    def test_choice_execution_rate_and_distributions_are_separate(self):
        events = [
            pass_event(1000, 1000, 3000, 1000, completed=True, progressive=True),
            pass_event(1000, 1000, 3000, 1000, completed=False, progressive=True),
            pass_event(1000, 1000, 1000, 3000, completed=True),
            pass_event(3000, 1000, 1000, 1000, completed=False),
        ]

        payload = build_pass_state_evidence(events, exposure_seconds=120)

        self.assertEqual(payload["summary"]["attempts"], 4)
        self.assertEqual(payload["summary"]["completions"], 2)
        self.assertEqual(payload["summary"]["incompletions"], 2)
        self.assertEqual(payload["summary"]["attempts_per_state_minute"], 2.0)
        self.assertEqual(payload["summary"]["completion_rate"], 0.5)
        self.assertEqual(payload["summary"]["progressive_attempt_rate"], 0.5)
        self.assertEqual(payload["summary"]["progressive_completion_rate"], 0.5)
        directions = {row["category"]: row for row in payload["directions"]}
        self.assertEqual(directions["forward"]["attempts"], 2)
        self.assertEqual(directions["forward"]["completion_rate"], 0.5)
        self.assertEqual(directions["lateral"]["attempts"], 1)
        self.assertEqual(directions["backward"]["attempts"], 1)

    def test_flow_exposes_origin_volume_shape_and_completion_context(self):
        payload = build_pass_state_evidence(
            [
                pass_event(1000, 2000, 3000, 4000, completed=True),
                pass_event(1000, 2000, 5000, 2000, completed=False),
            ],
            exposure_seconds=60,
        )

        self.assertEqual(len(payload["flow"]), 1)
        flow = payload["flow"][0]
        self.assertEqual(flow["attempts"], 2)
        self.assertEqual(flow["completions"], 1)
        self.assertEqual(flow["incompletions"], 1)
        self.assertEqual(flow["attempts_per_state_minute"], 2.0)
        self.assertEqual(flow["attempt_share"], 1.0)
        self.assertEqual(flow["completion_rate"], 0.5)
        self.assertEqual((flow["mean_origin_x"], flow["mean_origin_y"]), (10.0, 20.0))
        self.assertEqual((flow["mean_destination_x"], flow["mean_destination_y"]), (40.0, 30.0))
        self.assertEqual(len(payload["origin_conditioned"]), 1)
        conditioned = payload["origin_conditioned"][0]
        self.assertEqual(conditioned["attempts"], 2)
        self.assertEqual(conditioned["directions"][0]["attempt_share"], 1.0)

    def test_empty_missing_coordinate_and_zero_exposure_are_disclosed(self):
        missing = pass_event(None, 1000, 2000, 1000)
        payload = build_pass_state_evidence([missing], exposure_seconds=0)

        self.assertFalse(payload["evidence"]["empty"])
        self.assertTrue(payload["evidence"]["spatial_empty"])
        self.assertTrue(payload["evidence"]["sparse"])
        self.assertEqual(payload["evidence"]["excluded_missing_coordinates"], 1)
        self.assertEqual(payload["summary"]["attempts"], 1)
        self.assertEqual(payload["summary"]["completions"], 1)
        self.assertEqual(payload["summary"]["completion_rate"], 1.0)
        self.assertIsNone(payload["summary"]["attempts_per_state_minute"])
        self.assertEqual(payload["flow"], [])

    def test_payload_is_bounded_and_discloses_truncation(self):
        event = pass_event(1000, 1000, 2000, 1000)
        payload = build_pass_state_evidence(
            [event] * (PASS_STATE_EVENT_LIMIT + 1),
            exposure_seconds=60,
        )

        self.assertTrue(payload["evidence"]["truncated"])
        self.assertEqual(payload["summary"]["attempts"], PASS_STATE_EVENT_LIMIT + 1)
        self.assertLessEqual(len(payload["flow"]), 24)
        self.assertLessEqual(len(payload["origin_conditioned"]), 24)

    def test_comparison_delta_is_null_safe(self):
        selected = build_pass_state_evidence(
            [pass_event(0, 0, 2000, 0)], exposure_seconds=60
        )
        baseline = build_pass_state_evidence([], exposure_seconds=60)

        delta = comparison_delta(selected, baseline)

        self.assertEqual(delta["attempts_per_state_minute"], 1.0)
        self.assertIsNone(delta["completion_rate"])
        self.assertIsNone(delta["mean_length_metres"])
