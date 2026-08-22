from __future__ import annotations

from django.test import SimpleTestCase

from ingestion.models import MatchEventShotOutcome, MatchEventShotSituation
from ingestion.services.shot_zones import (
    GOAL_Y_MAX,
    GOAL_Y_MIN,
    Z_LOW_MAX,
    keeper_variant,
    placement_to_zone,
    shooter_variant,
    split_variants,
)
from ingestion.shot_zones_api import ShotPlacement


def placement(outcome, *, y=50.0, z=10.0, situation=MatchEventShotSituation.OPEN_PLAY):
    return ShotPlacement(
        outcome=outcome,
        situation=situation,
        goal_mouth_y=y,
        goal_mouth_z=z,
    )


class PlacementToZoneTest(SimpleTestCase):
    def test_left_low(self):
        self.assertEqual(placement_to_zone(GOAL_Y_MIN + 0.1, 5), (0, 0))

    def test_centre_high(self):
        self.assertEqual(placement_to_zone(50.0, Z_LOW_MAX + 5), (1, 1))

    def test_right_low_boundary(self):
        self.assertEqual(placement_to_zone(GOAL_Y_MAX, 5), (2, 0))

    def test_outside_mouth_is_unknown(self):
        self.assertIsNone(placement_to_zone(GOAL_Y_MIN - 1, 5))
        self.assertIsNone(placement_to_zone(50.0, 150))


class ShooterVariantTest(SimpleTestCase):
    def test_cells_and_conversion(self):
        variant = shooter_variant(
            [
                placement(MatchEventShotOutcome.GOAL, y=GOAL_Y_MIN + 1),
                placement(MatchEventShotOutcome.SAVED, y=GOAL_Y_MIN + 2),
                placement(MatchEventShotOutcome.GOAL, y=GOAL_Y_MIN + 3),
            ]
        )
        left_low = next(cell for cell in variant["cells"] if (cell["column"], cell["row"]) == (0, 0))
        self.assertEqual(left_low["shots"], 3)
        self.assertEqual(left_low["goals"], 2)
        self.assertAlmostEqual(left_low["conversion"], round(2 / 3, 4))
        totals = variant["totals"]
        self.assertEqual(totals["shots"], 3)
        self.assertEqual(totals["on_target"], 3)

    def test_blocked_and_off_target_excluded_from_cells_but_counted(self):
        variant = shooter_variant(
            [
                placement(MatchEventShotOutcome.GOAL),
                placement(MatchEventShotOutcome.BLOCKED),
                placement(MatchEventShotOutcome.OFF_TARGET),
                placement(MatchEventShotOutcome.WOODWORK),
            ]
        )
        total_cell_shots = sum(cell["shots"] for cell in variant["cells"])
        self.assertEqual(total_cell_shots, 1)
        totals = variant["totals"]
        self.assertEqual(totals["blocked"], 1)
        self.assertEqual(totals["woodwork"], 1)
        self.assertEqual(totals["off_target"], 1)
        self.assertEqual(totals["on_target"], 1)

    def test_on_target_without_coordinates_is_unknown(self):
        variant = shooter_variant(
            [placement(MatchEventShotOutcome.GOAL, y=None, z=None)]
        )
        self.assertEqual(variant["totals"]["unknown_target"], 1)


class KeeperVariantTest(SimpleTestCase):
    def test_only_faced_outcomes_counted_with_save_rates(self):
        variant = keeper_variant(
            [
                placement(MatchEventShotOutcome.SAVED),
                placement(MatchEventShotOutcome.GOAL),
                placement(MatchEventShotOutcome.BLOCKED),
                placement(MatchEventShotOutcome.OFF_TARGET),
            ]
        )
        total_cell_shots = sum(cell["shots"] for cell in variant["cells"])
        self.assertEqual(total_cell_shots, 2)
        totals = variant["totals"]
        self.assertEqual(totals["shots_faced"], 2)
        self.assertEqual(totals["saves"], 1)
        self.assertEqual(totals["goals_conceded"], 1)
        self.assertAlmostEqual(totals["save_rate"], 0.5)


class SplitVariantsTest(SimpleTestCase):
    def test_penalties_split_from_open_play(self):
        placements = [
            placement(MatchEventShotOutcome.GOAL),
            placement(
                MatchEventShotOutcome.GOAL,
                situation=MatchEventShotSituation.PENALTY,
            ),
            placement(MatchEventShotOutcome.GOAL, situation=MatchEventShotSituation.DIRECT_FREE_KICK),
        ]
        variants = split_variants(placements, shooter_variant)
        self.assertEqual(variants["all"]["totals"]["shots"], 3)
        # Direct free kicks are not penalties and remain in the open-play view.
        self.assertEqual(variants["open_play"]["totals"]["shots"], 2)
        self.assertEqual(variants["penalties_only"]["totals"]["shots"], 1)
