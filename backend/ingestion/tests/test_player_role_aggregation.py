from copy import deepcopy
from decimal import Decimal
from itertools import permutations

from django.test import SimpleTestCase

from ingestion.services.player_role_aggregation import (
    CompactMatchBatch,
    BoundedEvidenceAccumulator,
    DecimalMeasure,
    ExposureInterval,
    ExposureIntervalIndex,
    PlayerRoleFeatureAccumulator,
)


def batch_accumulator(seed: int) -> PlayerRoleFeatureAccumulator:
    accumulator = PlayerRoleFeatureAccumulator(
        player_id=10,
        team_id=20,
        competition_season_id=30,
        position_group="MID",
        recorded_position="Central Midfielder",
        supporting_metrics={
            "native_position": "Central Midfielder",
            "position_group": "MID",
            "minutes": 900,
            "xg_per_90": 0.1,
            "xa_per_90": 0.2,
            "key_passes_per_90": 1.5,
            "successful_dribbles_per_90": 0.8,
        },
    )
    accumulator.exposure.add(seed, seed, 0, 100 + seed)
    accumulator.overall_player.counters.update({
        "touches": seed, "actions": seed, "pass_attempts": seed,
        "pass_completions": seed, "progressive_passes": seed,
        "progressive_actions": seed, "key_passes": seed,
    })
    accumulator.overall_player.pass_lengths.add(seed + 0.25)
    accumulator.overall_player.pass_forward.add(seed - 2)
    accumulator.overall_player.touch_location.add(seed * 10, seed * 20)
    accumulator.overall_player.touch_grid.add(seed)
    accumulator.overall_team.counters.update({
        "touches": seed * 5, "actions": seed * 5, "pass_attempts": seed * 5,
        "pass_completions": seed * 4, "progressive_passes": seed * 2,
        "progressive_actions": seed * 2, "key_passes": seed * 2,
    })
    accumulator.overall_team.touch_location.add(seed * 12, seed * 18)
    accumulator.player_geometry.counters.update({
        "open_play_events": seed, "touches": seed, "passes": seed,
        "completed_passes": seed, "central_touches": seed,
        "advanced_touches": seed, "box_touches": seed,
        "line_breaking_passes": seed,
    })
    accumulator.player_geometry.defensive_x.add(seed * 2)
    accumulator.team_geometry.counters.update({"touches": seed * 5, "passes": seed * 5})
    state = accumulator.states[("losing", "drawing", "winning")[seed - 1]]
    state.exposure.add(seed, seed, 0, 100 + seed)
    state.player.counters.update(accumulator.overall_player.counters)
    state.player.touch_location.add(seed * 10, seed * 20)
    state.team.counters.update(accumulator.overall_team.counters)
    state.team.touch_location.add(seed * 12, seed * 18)
    accumulator.transition.counters.update({
        "candidate_possessions": 1, "opportunities": seed,
        "involved_possessions": seed, "ambiguous_excluded": seed,
    })
    accumulator.transition.stage_actions["advancement"] += seed
    accumulator.transition.stage_possessions["advancement"] += 1
    accumulator.transition.evidence.add((seed, seed, seed, f"p{seed}"), {"seed": seed})
    accumulator.score_events["goals"] += seed
    return accumulator


class PlayerRoleAggregationContractTests(SimpleTestCase):
    def test_exact_linear_total_identifies_both_valid_rounding_ties(self):
        measure = DecimalMeasure()
        measure.add(2.1150000000000007, exact_value=Decimal("2.115"))

        self.assertEqual(measure.mean(2), 2.12)
        self.assertEqual(measure.mean(2, exact=True, tie_direction="floor"), 2.11)
        self.assertEqual(measure.mean(2, exact=True, tie_direction="ceiling"), 2.12)

    def test_compact_batch_rejects_oversized_or_cross_match_rows(self):
        batch = CompactMatchBatch(matches=tuple({"id": value} for value in range(1, 6)))
        self.assertEqual(batch.match_ids, (1, 2, 3, 4, 5))
        with self.assertRaises(ValueError):
            CompactMatchBatch(matches=tuple({"id": value} for value in range(1, 7)))
        with self.assertRaises(ValueError):
            CompactMatchBatch(matches=({"id": 1},), events=({"provider_match_id": 2},))

    def test_interval_lookup_is_half_open_and_isolates_team_and_player(self):
        index = ExposureIntervalIndex([
            ExposureInterval(1, 20, 10, 0, 30, "drawing", 0),
            ExposureInterval(1, 20, 10, 30, 60, "winning", 1),
            ExposureInterval(1, 21, 10, 0, 60, "losing", 0),
            ExposureInterval(1, 20, 11, 0, 60, "drawing", 0),
        ])

        self.assertEqual(index.find(1, 20, 10, 0).state, "drawing")
        self.assertEqual(index.find(1, 20, 10, 29).state, "drawing")
        self.assertEqual(index.find(1, 20, 10, 30).state, "winning")
        self.assertIsNone(index.find(1, 20, 10, 60))
        self.assertEqual(index.find(1, 21, 10, 10).state, "losing")
        self.assertEqual(index.find(1, 20, 11, 10).state, "drawing")

    def test_merge_order_does_not_change_feature_output(self):
        batches = [batch_accumulator(seed) for seed in (1, 2, 3)]
        outputs = []
        for ordering in permutations(batches):
            combined = deepcopy(ordering[0])
            for batch in ordering[1:]:
                combined.merge(deepcopy(batch))
            outputs.append(combined.to_feature_json())

        self.assertTrue(all(output == outputs[0] for output in outputs[1:]))
        left = deepcopy(batches[0]).merge(deepcopy(batches[1])).merge(deepcopy(batches[2]))
        self.assertEqual(left.transition.evidence.to_json(), [{"seed": 1}, {"seed": 2}, {"seed": 3}])
        self.assertEqual(left.transition.counters["ambiguous_excluded"], 6)
        transition = left.transition.to_evidence_json()
        self.assertEqual(transition["sequence_stages"]["advancement"]["possessions"], 3)
        self.assertEqual(transition["exclusions"]["ambiguous_possessions"], 6)
        self.assertTrue(transition["evidence_truncated"])

    def test_bounded_evidence_is_deterministic_across_merge_order(self):
        first = BoundedEvidenceAccumulator(limit=2)
        second = BoundedEvidenceAccumulator(limit=2)
        first.add((3, 1, 1, "c"), {"id": "c"})
        first.add((1, 1, 1, "a"), {"id": "a"})
        second.add((2, 1, 1, "b"), {"id": "b"})
        second.add((4, 1, 1, "d"), {"id": "d"})

        forward = deepcopy(first).merge(deepcopy(second)).to_json()
        reverse = deepcopy(second).merge(deepcopy(first)).to_json()
        self.assertEqual(forward, reverse)
        self.assertEqual(forward, [{"id": "a"}, {"id": "b"}])

    def test_merge_rejects_cross_team_or_metadata_contamination(self):
        source = batch_accumulator(1)
        other_team = batch_accumulator(2)
        other_team.team_id = 99
        with self.assertRaises(ValueError):
            source.merge(other_team)

        source = batch_accumulator(1)
        changed_metadata = batch_accumulator(2)
        changed_metadata.position_group = "FWD"
        with self.assertRaises(ValueError):
            source.merge(changed_metadata)
