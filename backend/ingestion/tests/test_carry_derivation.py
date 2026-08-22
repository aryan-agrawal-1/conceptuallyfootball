from __future__ import annotations

from django.test import SimpleTestCase

from ingestion.models import MatchEventType
from ingestion.services.carry_derivation import (
    MAX_CARRY_METRES,
    MIN_CARRY_METRES,
    carry_distance_metres,
    derive_carries,
)


def make_event(
    event_index: int,
    *,
    provider_player_id: str = "P1",
    provider_team_id: str = "T1",
    team_id: int | None = 1,
    player_id: int | None = 1,
    event_type: int = MatchEventType.BALL_TOUCH,
    x: float | None = 50.0,
    y: float | None = 50.0,
    end_x: float | None = None,
    end_y: float | None = None,
    is_touch: bool = True,
    outcome_successful: bool | None = True,
):
    from ingestion.models import ProviderMatchEvent

    return ProviderMatchEvent(
        event_index=event_index,
        provider_team_id=provider_team_id,
        provider_player_id=provider_player_id,
        team_id=team_id,
        player_id=player_id,
        event_type=event_type,
        period=1,
        minute=10 + event_index,
        second=0,
        match_seconds=(10 + event_index) * 60,
        outcome_successful=outcome_successful,
        x=None if x is None else round(x * 100),
        y=None if y is None else round(y * 100),
        end_x=None if end_x is None else round(end_x * 100),
        end_y=None if end_y is None else round(end_y * 100),
        is_touch=is_touch,
    )


class CarryDistanceTest(SimpleTestCase):
    def test_five_metres_along_x(self):
        five_metres_in_scaled_units = round(5.0 / (105.0 / 10_000))
        distance = carry_distance_metres((5000, 5000), (5000 + five_metres_in_scaled_units, 5000))
        self.assertAlmostEqual(distance, 5.0, places=1)

    def test_zero_distance(self):
        self.assertEqual(carry_distance_metres((5000, 5000), (5000, 5000)), 0.0)


class DeriveCarriesTest(SimpleTestCase):
    def test_consecutive_same_player_touches_produce_carry(self):
        # ~5m dribble forward between two touches by the same player.
        events = [
            make_event(1, x=50.0, y=50.0),
            make_event(2, x=54.8, y=50.0),
        ]
        carries = derive_carries(events)
        self.assertEqual(len(carries), 1)
        carry = carries[0]
        self.assertEqual(carry.start_event_index, 1)
        self.assertEqual(carry.end_event_index, 2)
        self.assertAlmostEqual(
            carry_distance_metres((carry.x, carry.y), (carry.end_x, carry.end_y)),
            5.0,
            places=1,
        )

    def test_opponent_touch_breaks_chain(self):
        events = [
            make_event(1, x=50.0, y=50.0),
            make_event(2, provider_player_id="P2", team_id=2, player_id=2, x=55.0, y=50.0),
            make_event(3, x=60.0, y=50.0),
        ]
        self.assertEqual(derive_carries(events), [])

    def test_completed_pass_uses_end_as_carry_origin(self):
        # Player passes from x=40 to x=50 (the pass covers that displacement),
        # then touches again at x=53 — the carry starts at the pass destination.
        events = [
            make_event(
                1,
                event_type=MatchEventType.PASS,
                x=40.0,
                y=50.0,
                end_x=50.0,
                end_y=50.0,
            ),
            make_event(3, x=52.9, y=50.0),
        ]
        carries = derive_carries(events)
        self.assertEqual(len(carries), 1)
        self.assertEqual(round(carries[0].x / 100), 50)

    def test_short_jitter_is_not_a_carry(self):
        # Just under the 3m threshold along x.
        events = [
            make_event(1, x=50.0, y=50.0),
            make_event(2, x=50.0 + (MIN_CARRY_METRES - 0.5) / 1.05, y=50.0),
        ]
        self.assertEqual(derive_carries(events), [])

    def test_absurd_displacement_is_not_a_carry(self):
        events = [
            make_event(1, x=1.0, y=50.0),
            make_event(2, x=99.0, y=50.0),
        ]
        self.assertEqual(derive_carries(events), [])

    def test_unlocated_touches_are_skipped(self):
        events = [
            make_event(1, x=50.0, y=50.0),
            make_event(2, x=None, y=None),
            make_event(3, x=54.8, y=50.0),
        ]
        carries = derive_carries(events)
        self.assertEqual(len(carries), 1)
        self.assertEqual(carries[0].start_event_index, 1)
        self.assertEqual(carries[0].end_event_index, 3)

    def test_non_touch_events_do_not_break_chain(self):
        events = [
            make_event(1, x=50.0, y=50.0),
            make_event(2, event_type=MatchEventType.FOUL, provider_player_id="P2", team_id=2, player_id=2, is_touch=False, x=51.0, y=50.0),
            make_event(3, x=54.8, y=50.0),
        ]
        carries = derive_carries(events)
        self.assertEqual(len(carries), 1)
