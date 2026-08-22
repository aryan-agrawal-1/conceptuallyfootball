from __future__ import annotations

from django.test import SimpleTestCase

from ingestion.models import MatchEventBodyPart, MatchEventType
from ingestion.services.carry_derivation import (
    MAX_CARRY_METRES,
    MAX_CARRY_SECONDS,
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
    period: int = 1,
    match_seconds: int | None = None,
    body_part: int = MatchEventBodyPart.UNKNOWN,
    is_set_piece: bool = False,
):
    from ingestion.models import ProviderMatchEvent

    return ProviderMatchEvent(
        event_index=event_index,
        provider_team_id=provider_team_id,
        provider_player_id=provider_player_id,
        team_id=team_id,
        player_id=player_id,
        event_type=event_type,
        period=period,
        minute=10,
        second=event_index * 2,
        match_seconds=600 + event_index * 2 if match_seconds is None else match_seconds,
        outcome_successful=outcome_successful,
        x=None if x is None else round(x * 100),
        y=None if y is None else round(y * 100),
        end_x=None if end_x is None else round(end_x * 100),
        end_y=None if end_y is None else round(end_y * 100),
        is_touch=is_touch,
        body_part=body_part,
        is_set_piece=is_set_piece,
    )


class CarryDistanceTest(SimpleTestCase):
    def test_five_metres_along_x(self):
        five_metres_in_scaled_units = round(5.0 / (105.0 / 10_000))
        distance = carry_distance_metres((5000, 5000), (5000 + five_metres_in_scaled_units, 5000))
        self.assertAlmostEqual(distance, 5.0, places=1)

    def test_zero_distance(self):
        self.assertEqual(carry_distance_metres((5000, 5000), (5000, 5000)), 0.0)


class DeriveCarriesTest(SimpleTestCase):
    def test_consecutive_same_player_controlled_actions_produce_carry(self):
        events = [
            make_event(1, x=50.0, y=50.0, provider_player_id="P1", player_id=1),
            make_event(2, x=54.8, y=50.0, provider_player_id="P1", player_id=1),
        ]
        carries = derive_carries(events)
        self.assertEqual(len(carries), 1)
        carry = carries[0]
        self.assertEqual(carry.start_event_index, 1)
        self.assertEqual(carry.end_event_index, 2)
        self.assertEqual(carry.provider_player_id, "P1")
        self.assertEqual(carry.player_id, 1)
        self.assertAlmostEqual(
            carry_distance_metres((carry.x, carry.y), (carry.end_x, carry.end_y)),
            5.0,
            places=1,
        )

    def test_opponent_touch_breaks_chain(self):
        events = [
            make_event(1, x=50.0, y=50.0),
            make_event(
                2,
                provider_player_id="P2",
                provider_team_id="T2",
                team_id=2,
                player_id=2,
                x=55.0,
                y=50.0,
            ),
            make_event(3, x=60.0, y=50.0, match_seconds=606),
        ]
        self.assertEqual(derive_carries(events), [])

    def test_same_second_acquisition_movement_is_rejected(self):
        events = [
            make_event(
                1,
                event_type=MatchEventType.BALL_RECOVERY,
                x=40.0,
                y=50.0,
                match_seconds=600,
                is_touch=False,
            ),
            make_event(2, event_type=MatchEventType.PASS, x=45.0, y=50.0, match_seconds=600),
        ]

        self.assertEqual(derive_carries(events), [])

    def test_implausible_one_second_acquisition_movement_is_rejected(self):
        events = [
            make_event(
                1,
                event_type=MatchEventType.BALL_RECOVERY,
                x=40.0,
                y=50.0,
                match_seconds=600,
                is_touch=False,
            ),
            make_event(2, event_type=MatchEventType.PASS, x=47.0, y=50.0, match_seconds=601),
        ]

        self.assertEqual(derive_carries(events), [])

    def test_plausible_one_second_acquisition_movement_is_low_confidence(self):
        events = [
            make_event(
                1,
                event_type=MatchEventType.SAVE,
                x=40.0,
                y=50.0,
                match_seconds=600,
                is_touch=False,
            ),
            make_event(2, event_type=MatchEventType.PASS, x=44.0, y=50.0, match_seconds=601),
        ]

        carries = derive_carries(events)

        self.assertEqual(len(carries), 1)
        self.assertTrue(carries[0].is_low_confidence)

    def test_completed_pass_uses_end_as_carry_origin(self):
        # The receiver is credited from the completed pass destination to their
        # next recorded action, rather than crediting the passer.
        events = [
            make_event(
                1,
                event_type=MatchEventType.PASS,
                x=40.0,
                y=50.0,
                end_x=50.0,
                end_y=50.0,
            ),
            make_event(3, provider_player_id="P2", player_id=2, x=52.9, y=50.0),
        ]
        carries = derive_carries(events)
        self.assertEqual(len(carries), 1)
        self.assertEqual(round(carries[0].x / 100), 50)
        self.assertEqual(carries[0].provider_player_id, "P2")

    def test_recovery_is_start_only_and_can_begin_subsequent_carry(self):
        events = [
            make_event(1, provider_player_id="P1", player_id=1, x=40.0, y=50.0),
            make_event(
                2,
                provider_player_id="P2",
                player_id=2,
                event_type=MatchEventType.BALL_RECOVERY,
                is_touch=False,
                x=50.0,
                y=50.0,
            ),
            make_event(
                3,
                provider_player_id="P2",
                player_id=2,
                event_type=MatchEventType.PASS,
                x=54.8,
                y=50.0,
                end_x=60.0,
                end_y=50.0,
            ),
        ]

        carries = derive_carries(events)
        self.assertEqual(len(carries), 1)
        self.assertEqual((carries[0].start_event_index, carries[0].end_event_index), (2, 3))

    def test_failed_action_cannot_establish_carry_origin(self):
        events = [
            make_event(
                1,
                event_type=MatchEventType.PASS,
                outcome_successful=False,
                x=40.0,
                y=70.0,
                end_x=45.0,
                end_y=65.0,
            ),
            make_event(2, event_type=MatchEventType.PASS, x=68.0, y=50.0),
        ]
        self.assertEqual(derive_carries(events), [])

    def test_save_is_start_only_and_prevents_tackle_to_pass_bridge(self):
        events = [
            make_event(1, event_type=MatchEventType.TACKLE, x=34.0, y=25.0),
            make_event(
                2,
                provider_player_id="GK",
                player_id=2,
                event_type=MatchEventType.SAVE,
                is_touch=False,
                x=4.6,
                y=20.6,
            ),
            make_event(
                3,
                provider_player_id="GK",
                player_id=2,
                event_type=MatchEventType.PASS,
                x=3.8,
                y=18.3,
            ),
        ]
        self.assertEqual(derive_carries(events), [])

    def test_offensive_aerial_interrupts_completed_pass_to_next_action(self):
        events = [
            make_event(
                1,
                event_type=MatchEventType.PASS,
                x=80.0,
                y=60.0,
                end_x=90.0,
                end_y=68.0,
            ),
            make_event(
                2,
                provider_player_id="P2",
                player_id=2,
                event_type=MatchEventType.AERIAL,
                is_touch=False,
                x=93.0,
                y=54.0,
            ),
            make_event(
                3,
                provider_player_id="P2",
                player_id=2,
                event_type=MatchEventType.PASS,
                x=90.0,
                y=59.0,
            ),
        ]
        self.assertEqual(derive_carries(events), [])

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

    def test_unlocated_action_breaks_chain(self):
        events = [
            make_event(1, x=50.0, y=50.0),
            make_event(2, x=None, y=None),
            make_event(3, x=54.8, y=50.0),
        ]
        self.assertEqual(derive_carries(events), [])

    def test_foul_breaks_chain(self):
        events = [
            make_event(1, x=50.0, y=50.0),
            make_event(2, event_type=MatchEventType.FOUL, provider_player_id="P2", team_id=2, player_id=2, is_touch=False, x=51.0, y=50.0),
            make_event(3, x=54.8, y=50.0),
        ]
        self.assertEqual(derive_carries(events), [])

    def test_period_boundary_breaks_chain(self):
        events = [
            make_event(1, period=1, match_seconds=3022, x=50.0, y=50.0),
            make_event(2, period=2, match_seconds=2700, x=54.8, y=50.0),
        ]
        self.assertEqual(derive_carries(events), [])

    def test_ten_second_gap_is_included_but_longer_gap_is_not(self):
        included = [
            make_event(1, match_seconds=600, x=50.0, y=50.0),
            make_event(2, match_seconds=600 + MAX_CARRY_SECONDS, x=54.8, y=50.0),
        ]
        excluded = [
            make_event(1, match_seconds=600, x=50.0, y=50.0),
            make_event(2, match_seconds=601 + MAX_CARRY_SECONDS, x=54.8, y=50.0),
        ]
        self.assertEqual(len(derive_carries(included)), 1)
        self.assertEqual(derive_carries(excluded), [])

    def test_restart_and_headed_shot_do_not_end_carries(self):
        restart = [
            make_event(1, x=50.0, y=50.0),
            make_event(2, x=54.8, y=50.0, is_set_piece=True),
        ]
        headed_shot = [
            make_event(1, x=50.0, y=50.0),
            make_event(
                2,
                event_type=MatchEventType.SHOT,
                x=54.8,
                y=50.0,
                body_part=MatchEventBodyPart.HEAD,
            ),
        ]
        self.assertEqual(derive_carries(restart), [])
        self.assertEqual(derive_carries(headed_shot), [])

    def test_carry_uses_pass_spatial_classifications(self):
        progressive = derive_carries(
            [
                make_event(1, x=70.0, y=50.0),
                make_event(2, x=80.0, y=50.0),
            ]
        )[0]
        box_entry_carry = derive_carries(
            [
                make_event(1, x=80.0, y=50.0),
                make_event(2, x=86.0, y=50.0),
            ]
        )[0]

        self.assertTrue(progressive.is_progressive_carry)
        self.assertFalse(progressive.is_final_third_entry)
        self.assertTrue(box_entry_carry.is_box_entry)
