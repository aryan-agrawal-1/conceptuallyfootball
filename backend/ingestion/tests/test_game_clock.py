from types import SimpleNamespace

from django.test import SimpleTestCase

from ingestion.models import MatchEventPeriod
from ingestion.services.game_clock import (
    MatchClockError,
    match_clock_from_mapping,
    validate_event_timestamp,
)


def clock_mapping(*, extra_time=False):
    periods = [
        {"period": 1, "start_second": 0, "end_second": 47 * 60},
        {"period": 2, "start_second": 47 * 60, "end_second": 95 * 60},
    ]
    if extra_time:
        periods += [
            {"period": 3, "start_second": 95 * 60, "end_second": 111 * 60},
            {"period": 4, "start_second": 111 * 60, "end_second": 128 * 60},
        ]
    return {"periods": periods, "supported_end_second": periods[-1]["end_second"]}


class MatchClockTests(SimpleTestCase):
    def test_builds_gap_free_half_open_added_time_clock(self):
        clock = match_clock_from_mapping(clock_mapping())
        self.assertEqual(clock.exposure_seconds, 95 * 60)
        self.assertEqual(clock.boundary_seconds(), (0, 47 * 60, 95 * 60))
        self.assertEqual(
            clock.boundary_seconds(include_nominal_boundaries=True),
            (0, 45 * 60, 47 * 60, 92 * 60, 95 * 60),
        )
        self.assertFalse(clock.periods[0].is_added_time(45 * 60 - 1))
        self.assertTrue(clock.periods[0].is_added_time(45 * 60))

    def test_extra_time_is_continuous_and_breaks_consume_no_seconds(self):
        clock = match_clock_from_mapping(clock_mapping(extra_time=True))
        self.assertEqual(
            [period.duration_seconds for period in clock.periods],
            [2820, 2880, 960, 1020],
        )
        self.assertEqual(clock.supported_end_second, 128 * 60)

    def test_rejects_missing_gapped_overlapping_and_reversed_metadata(self):
        invalid = [
            {},
            {"periods": [{"period": 1, "start_second": 0, "end_second": 0}]},
            {
                "periods": [
                    {"period": 1, "start_second": 0, "end_second": 2700},
                    {"period": 2, "start_second": 2701, "end_second": 5400},
                ]
            },
            {
                "periods": [
                    {"period": 1, "start_second": 0, "end_second": 2700},
                    {"period": 2, "start_second": 2699, "end_second": 5400},
                ]
            },
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(MatchClockError):
                match_clock_from_mapping(value)

    def test_preserves_normalizer_exclusion_reason(self):
        with self.assertRaises(MatchClockError) as raised:
            match_clock_from_mapping(
                {
                    "valid": False,
                    "exclusion_reason": "clock_metadata_missing",
                    "periods": [],
                }
            )
        self.assertEqual(raised.exception.code, "clock_metadata_missing")

    def test_timestamp_membership_is_half_open_and_period_specific(self):
        clock = match_clock_from_mapping(clock_mapping())
        event = SimpleNamespace(
            event_index=1, period=MatchEventPeriod.SECOND_HALF, timeline_seconds=47 * 60
        )
        self.assertEqual(validate_event_timestamp(event, clock), 47 * 60)
        event.timeline_seconds = 95 * 60
        with self.assertRaises(MatchClockError):
            validate_event_timestamp(event, clock)

    def test_nominal_duration_never_sets_played_end(self):
        clock = match_clock_from_mapping(clock_mapping())
        self.assertNotEqual(
            clock.periods[0].end_second, clock.periods[0].nominal_end_second
        )
        self.assertEqual(clock.periods[0].end_second, 47 * 60)
