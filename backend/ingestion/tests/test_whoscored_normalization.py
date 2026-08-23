from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase, SimpleTestCase

from ingestion.models import (
    Competition,
    CompetitionSeason,
    MatchEventBodyPart,
    MatchEventPeriod,
    MatchEventShotOutcome,
    MatchEventShotSituation,
    MatchEventType,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchStatus,
    Season,
)
from ingestion.services.whoscored_normalization import (
    NORMALIZATION_SCHEMA_VERSION,
    RAW_PAYLOAD_SCHEMA_VERSION,
    NormalizationDiagnostics,
    NormalizationPolicy,
    WhoScoredNormalizationError,
    action_grid_assignment,
    box_entry,
    canonical_raw_payload_bytes,
    decode_coordinate,
    encode_coordinate,
    final_third_entry,
    is_action_event,
    is_defensive_event,
    normalize_match_clock,
    normalized_timeline_seconds,
    parse_match_payload,
    progressive_pass,
    replace_match_events,
    team_zone_assignment,
    unwrap_raw_payload,
    wrap_raw_payload,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "whoscored"
FIXTURE_POLICY = NormalizationPolicy(minimum_event_count=0)


def load_fixture(name: str) -> dict:
    with (FIXTURE_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def add_exact_test_clock(payload: dict) -> None:
    payload["periodEndMinutes"] = {"1": 45, "2": 90}
    payload["expandedMaxMinute"] = 90
    payload["expandedMinutes"] = {
        "1": {str(minute): minute for minute in range(46)},
        "2": {str(minute): minute for minute in range(45, 91)},
    }
    for source_event in payload["events"]:
        source_event["expandedMinute"] = source_event["minute"]
    team_id = payload["home"]["teamId"]
    payload["events"].extend(
        [
            {
                "id": 99001 + index,
                "eventId": 99001 + index,
                "minute": minute,
                "second": 0,
                "expandedMinute": expanded_minute,
                "teamId": team_id,
                "period": {"value": period, "displayName": period_name},
                "type": {"value": 30, "displayName": event_name},
                "outcomeType": {"value": 1, "displayName": "Successful"},
                "qualifiers": [],
            }
            for index, (
                event_name,
                period,
                period_name,
                minute,
                expanded_minute,
            ) in enumerate(
                (
                    ("Start", 1, "FirstHalf", 0, 0),
                    ("End", 1, "FirstHalf", 45, 45),
                    ("Start", 2, "SecondHalf", 45, 45),
                    ("End", 2, "SecondHalf", 90, 90),
                )
            )
        ]
    )


class WhoScoredNormalizationHelperTests(SimpleTestCase):
    def test_exact_period_boundaries_compress_breaks_out_of_played_time(self):
        payload = {
            "periodEndMinutes": {"1": 45, "2": 90},
            "expandedMaxMinute": 91,
            "expandedMinutes": {"1": {"45": 45}, "2": {"90": 91}},
            "events": [
                {
                    "type": {"displayName": event_name},
                    "period": {"value": period},
                    "expandedMinute": minute,
                    "second": second,
                }
                for event_name, period, minute, second in (
                    ("Start", 1, 0, 0),
                    ("End", 1, 45, 59),
                    ("Start", 2, 46, 0),
                    ("End", 2, 91, 17),
                )
            ],
        }

        clock = normalize_match_clock(payload, NormalizationDiagnostics())

        self.assertTrue(clock["valid"])
        self.assertEqual(
            [
                (period["start_second"], period["end_second"])
                for period in clock["periods"]
            ],
            [(0, 45 * 60 + 59), (45 * 60 + 59, 91 * 60 + 16)],
        )
        self.assertEqual(clock["supported_end_second"], 91 * 60 + 16)
        self.assertEqual(
            normalized_timeline_seconds(
                {
                    "period": {"value": 2},
                    "expandedMinute": 46,
                    "second": 0,
                },
                clock,
            ),
            45 * 60 + 59,
        )

    def test_coordinate_encode_decode_boundaries_and_rounding(self):
        self.assertEqual(encode_coordinate(0), 0)
        self.assertEqual(encode_coordinate("12.345"), 1235)
        self.assertEqual(encode_coordinate(100), 10000)
        self.assertEqual(decode_coordinate(0), 0)
        self.assertEqual(decode_coordinate(1235), 12.35)
        self.assertEqual(decode_coordinate(10000), 100)

        for invalid in (-0.01, 100.01, True, "not-a-number", float("nan")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                encode_coordinate(invalid)
        for invalid in (-1, 10001, True, 1.5):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                decode_coordinate(invalid)

    def test_progressive_pass_thresholds_for_all_three_zones(self):
        cases = (
            ((1000, 5000, 3857, 5000), False),
            ((1000, 5000, 3858, 5000), True),
            ((4000, 5000, 5428, 5000), False),
            ((4000, 5000, 5429, 5000), True),
            ((7000, 5000, 7952, 5000), False),
            ((7000, 5000, 7953, 5000), True),
        )
        for coordinates, expected in cases:
            with self.subTest(coordinates=coordinates):
                self.assertIs(progressive_pass(*coordinates), expected)

    def test_final_third_and_box_boundaries(self):
        self.assertTrue(final_third_entry(True, 6669, 6670))
        self.assertFalse(final_third_entry(False, 6669, 6670))
        self.assertFalse(final_third_entry(True, 6670, 8000))
        self.assertFalse(final_third_entry(True, 5000, 6669))

        self.assertTrue(box_entry(True, 8349, 2110, 8350, 2110))
        self.assertTrue(box_entry(True, 5000, 5000, 8350, 7890))
        self.assertFalse(box_entry(True, 8350, 2110, 9000, 5000))
        self.assertFalse(box_entry(True, 5000, 5000, 8350, 2109))
        self.assertFalse(box_entry(True, 5000, 5000, 8350, 7891))
        self.assertFalse(box_entry(False, 5000, 5000, 9000, 5000))

    def test_grid_assignment_boundaries(self):
        self.assertEqual(action_grid_assignment(0, 0), (0, 0, 0))
        self.assertEqual(action_grid_assignment(416, 624), (0, 0, 0))
        self.assertEqual(action_grid_assignment(417, 625), (1, 1, 17))
        self.assertEqual(action_grid_assignment(10000, 10000), (23, 15, 383))

        self.assertEqual(team_zone_assignment(0, 0), (0, 0, 0))
        self.assertEqual(team_zone_assignment(1999, 3333), (0, 0, 0))
        self.assertEqual(team_zone_assignment(2000, 3334), (1, 1, 4))
        self.assertEqual(team_zone_assignment(10000, 10000), (4, 2, 14))

    def test_action_and_defensive_event_classification(self):
        self.assertTrue(is_action_event(MatchEventType.PASS))
        self.assertTrue(is_action_event(MatchEventType.SHOT))
        self.assertFalse(is_action_event(MatchEventType.FOUL))
        self.assertFalse(is_action_event(MatchEventType.AERIAL))
        self.assertTrue(
            is_action_event(MatchEventType.AERIAL, defensive_qualifier=True)
        )
        self.assertTrue(is_defensive_event(MatchEventType.TACKLE))
        self.assertFalse(is_defensive_event(MatchEventType.PASS))
        self.assertTrue(
            is_defensive_event(MatchEventType.CHALLENGE, defensive_qualifier=True)
        )

    def test_raw_wrapper_version_and_checksum_are_stable(self):
        payload = load_fixture("match_9000001.json")
        reordered = dict(reversed(list(payload.items())))
        wrapped = wrap_raw_payload(payload)

        self.assertEqual(wrapped["schema_version"], RAW_PAYLOAD_SCHEMA_VERSION)
        self.assertEqual(unwrap_raw_payload(wrapped), payload)
        self.assertEqual(
            canonical_raw_payload_bytes(payload),
            canonical_raw_payload_bytes(reordered),
        )
        with self.assertRaisesMessage(ValueError, "Unsupported"):
            unwrap_raw_payload(
                {
                    "schema_version": RAW_PAYLOAD_SCHEMA_VERSION + 1,
                    "provider": "whoscored",
                    "payload": payload,
                }
            )


class WhoScoredParserTests(SimpleTestCase):
    def setUp(self):
        self.payload = load_fixture("match_9000001.json")

    def test_fixture_normalizes_all_v1_families_and_typed_fields(self):
        result = parse_match_payload(self.payload, policy=FIXTURE_POLICY)

        self.assertEqual(result.schema_version, NORMALIZATION_SCHEMA_VERSION)
        self.assertEqual(len(result.events), len(self.payload["events"]))
        self.assertTrue(result.diagnostics.valid)
        self.assertEqual(
            result.diagnostics.unknown_event_types,
            {"999:SyntheticUnknownEvent": 1},
        )
        self.assertEqual(
            result.diagnostics.unknown_qualifiers,
            {"999:SyntheticUnknownQualifier": 1},
        )

        first = result.events[0]
        self.assertEqual(first.provider_event_id, "93001")
        self.assertEqual(first.provider_team_id, "9101")
        self.assertEqual(first.provider_player_id, "9201")
        self.assertEqual(first.period, MatchEventPeriod.FIRST_HALF)
        self.assertEqual(first.match_seconds, 65)
        self.assertEqual(first.event_type, MatchEventType.PASS)
        self.assertEqual(
            (first.x, first.y, first.end_x, first.end_y), (2250, 5000, 7100, 4800)
        )
        self.assertTrue(first.outcome_successful)
        self.assertTrue(first.is_touch)
        self.assertTrue(first.is_cross)
        self.assertTrue(first.is_through_ball)
        self.assertTrue(first.is_free_kick)
        self.assertTrue(first.is_progressive_pass)
        self.assertTrue(first.is_final_third_entry)
        self.assertFalse(first.is_box_entry)

        event_types = {event.event_type for event in result.events}
        self.assertTrue(
            {
                MatchEventType.PASS,
                MatchEventType.BALL_TOUCH,
                MatchEventType.TAKE_ON,
                MatchEventType.SHOT,
                MatchEventType.BALL_RECOVERY,
                MatchEventType.TACKLE,
                MatchEventType.INTERCEPTION,
                MatchEventType.CLEARANCE,
                MatchEventType.BLOCKED_PASS,
                MatchEventType.AERIAL,
                MatchEventType.CHALLENGE,
                MatchEventType.DISPOSSESSED,
                MatchEventType.FOUL,
                MatchEventType.OFFSIDE,
                MatchEventType.CARD,
                MatchEventType.SUBSTITUTION,
                MatchEventType.ADMINISTRATIVE,
                MatchEventType.UNKNOWN,
            }.issubset(event_types)
        )

        shots = {
            event.provider_event_id: event
            for event in result.events
            if event.event_type == MatchEventType.SHOT
        }
        self.assertEqual(shots["93003"].shot_outcome, MatchEventShotOutcome.GOAL)
        self.assertEqual(shots["93003"].shot_situation, MatchEventShotSituation.PENALTY)
        self.assertEqual(shots["93003"].goal_mouth_y, 4810)
        self.assertEqual(shots["93004"].shot_outcome, MatchEventShotOutcome.OFF_TARGET)
        self.assertEqual(shots["93004"].body_part, MatchEventBodyPart.HEAD)
        self.assertEqual(shots["93005"].shot_outcome, MatchEventShotOutcome.SAVED)
        self.assertTrue(shots["93005"].is_big_chance)
        self.assertEqual(shots["93005"].blocked_x, 9600)
        self.assertEqual(shots["93006"].shot_outcome, MatchEventShotOutcome.WOODWORK)
        self.assertEqual(shots["93006"].body_part, MatchEventBodyPart.RIGHT_FOOT)
        self.assertEqual(shots["93008"].body_part, MatchEventBodyPart.OTHER)

        missing_player = next(
            event for event in result.events if event.provider_event_id == "93024"
        )
        self.assertIsNone(missing_player.provider_player_id)
        substitutions = [
            event
            for event in result.events
            if event.event_type == MatchEventType.SUBSTITUTION
        ]
        self.assertEqual(len(substitutions), 2)
        aerial = next(
            event for event in result.events if event.provider_event_id == "93016"
        )
        challenge = next(
            event for event in result.events if event.provider_event_id == "93017"
        )
        self.assertTrue(is_defensive_event(aerial.event_type, defensive_qualifier=True))
        self.assertTrue(
            is_defensive_event(challenge.event_type, defensive_qualifier=True)
        )

    def test_state_clock_lineups_relations_and_dismissals_are_normalized(self):
        payload = copy.deepcopy(self.payload)
        add_exact_test_clock(payload)
        payload["home"]["players"] = [
            {
                "playerId": 1000 + index,
                "isFirstEleven": index < 11,
                "position": "GK" if index in {0, 11} else "MC",
            }
            for index in range(12)
        ]
        payload["away"]["players"] = [
            {
                "playerId": 2000 + index,
                "isFirstEleven": index < 11,
                "position": "GK" if index in {0, 11} else "DC",
            }
            for index in range(12)
        ]
        substitutions = [
            source_event
            for source_event in payload["events"]
            if source_event["type"]["displayName"]
            in {"SubstitutionOff", "SubstitutionOn"}
        ]
        substitutions[0]["relatedEventId"] = substitutions[1]["eventId"]
        substitutions[0]["relatedPlayerId"] = substitutions[1]["playerId"]
        substitutions[1]["relatedEventId"] = substitutions[0]["eventId"]
        substitutions[1]["relatedPlayerId"] = substitutions[0]["playerId"]
        card = next(
            source_event
            for source_event in payload["events"]
            if source_event["type"]["displayName"] == "Card"
        )
        card["cardType"] = {"value": 33, "displayName": "Red"}

        result = parse_match_payload(payload, policy=FIXTURE_POLICY)

        self.assertTrue(result.clock["valid"])
        self.assertEqual(result.clock["supported_end_second"], 90 * 60)
        first_pass = next(
            event for event in result.events if event.provider_event_id == "93001"
        )
        self.assertEqual(first_pass.timeline_seconds, 65)
        self.assertEqual(len(result.players), 24)
        self.assertEqual(
            sum(player.roster_role == "starter" for player in result.players),
            22,
        )
        normalized_substitutions = [
            event
            for event in result.events
            if event.event_type == MatchEventType.SUBSTITUTION
        ]
        self.assertNotEqual(
            normalized_substitutions[0].provider_event_id,
            normalized_substitutions[0].provider_event_sequence_id,
        )
        self.assertEqual(
            normalized_substitutions[0].related_provider_event_sequence_id,
            normalized_substitutions[1].provider_event_sequence_id,
        )
        self.assertEqual(
            normalized_substitutions[0].related_provider_player_id,
            normalized_substitutions[1].provider_player_id,
        )
        normalized_card = next(
            event
            for event in result.events
            if event.provider_event_id == str(card["id"])
        )
        self.assertEqual(normalized_card.dismissal_type, "red")

    def test_own_goal_is_not_normalized_as_a_shot(self):
        own_goal = copy.deepcopy(
            next(
                event
                for event in self.payload["events"]
                if event["type"]["displayName"] == "Goal"
            )
        )
        own_goal["id"] = 99901
        own_goal["eventId"] = 99901
        own_goal["qualifiers"].append({"type": {"value": 28, "displayName": "OwnGoal"}})
        own_goal["qualifiers"].append(
            {"type": {"value": 999, "displayName": "GoalDisallowed"}}
        )
        own_goal["qualifiers"].append(
            {
                "type": {"value": 55, "displayName": "RelatedEventId"},
                "value": "93003",
            }
        )
        self.payload["events"].append(own_goal)

        result = parse_match_payload(self.payload, policy=FIXTURE_POLICY)
        normalized = next(
            event for event in result.events if event.provider_event_id == "99901"
        )

        self.assertEqual(normalized.event_type, MatchEventType.OWN_GOAL)
        self.assertFalse(is_action_event(normalized.event_type))
        self.assertTrue(normalized.is_goal_disallowed)
        self.assertEqual(normalized.related_provider_event_sequence_id, "93001")

    def test_current_match_centre_omissions_and_known_qualifiers_are_accepted(self):
        payload = copy.deepcopy(self.payload)
        payload.pop("matchId")
        offside = payload["events"][0]
        offside["type"] = {"displayName": "OffsideGiven", "value": 10000}
        offside.pop("second")
        offside["qualifiers"] = [
            {"type": {"displayName": "Offensive", "value": 286}},
            {"type": {"displayName": "StandingSave", "value": 178}},
        ]

        result = parse_match_payload(payload, policy=FIXTURE_POLICY)

        self.assertTrue(result.diagnostics.valid)
        self.assertEqual(result.events[0].second, 0)
        self.assertNotIn("286:Offensive", result.diagnostics.unknown_qualifiers)
        self.assertNotIn("178:StandingSave", result.diagnostics.unknown_qualifiers)

    def test_missing_optional_fields_and_qualifiers_are_allowed(self):
        event = self.payload["events"][0]
        event.pop("playerId")
        event.pop("expandedMinute", None)
        event.pop("endX")
        event.pop("endY")
        event.pop("qualifiers")

        result = parse_match_payload(self.payload, policy=FIXTURE_POLICY)
        normalized = result.events[0]
        self.assertIsNone(normalized.provider_player_id)
        self.assertIsNone(normalized.expanded_minute)
        self.assertIsNone(normalized.end_x)
        self.assertFalse(normalized.is_progressive_pass)

    def test_blocked_shot_and_root_assist_flags_are_typed(self):
        blocked_shot = next(
            event for event in self.payload["events"] if event["id"] == 93005
        )
        blocked_shot["qualifiers"].append(
            {"type": {"value": 82, "displayName": "Blocked"}}
        )
        pass_event = self.payload["events"][0]
        pass_event["isKeyPass"] = True
        pass_event["isShotAssist"] = True
        pass_event["isGoalAssist"] = True

        result = parse_match_payload(self.payload, policy=FIXTURE_POLICY)
        normalized_pass = next(
            event for event in result.events if event.provider_event_id == "93001"
        )
        normalized_shot = next(
            event for event in result.events if event.provider_event_id == "93005"
        )
        self.assertTrue(normalized_pass.is_key_pass)
        self.assertTrue(normalized_pass.is_shot_assist)
        self.assertTrue(normalized_pass.is_intentional_assist)
        self.assertEqual(
            normalized_shot.shot_outcome,
            MatchEventShotOutcome.BLOCKED,
        )

    def test_defensive_qualifier_is_preserved_in_normalized_model_values(self):
        defensive = copy.deepcopy(self.payload["events"][0])
        defensive["id"] = 999001
        defensive["eventId"] = 999001
        defensive["type"] = {"value": 10, "displayName": "Aerial"}
        defensive["qualifiers"] = [{"type": {"value": 777, "displayName": "Defensive"}}]
        regular = copy.deepcopy(defensive)
        regular["id"] = 999002
        regular["eventId"] = 999002
        regular["qualifiers"] = []
        payload = copy.deepcopy(self.payload)
        payload["events"] = [defensive, regular]

        result = parse_match_payload(payload, policy=FIXTURE_POLICY)
        by_id = {event.provider_event_id: event for event in result.events}
        self.assertTrue(by_id["999001"].is_defensive)
        self.assertTrue(by_id["999001"].model_values()["is_defensive"])
        self.assertFalse(by_id["999002"].is_defensive)
        self.assertFalse(by_id["999002"].model_values()["is_defensive"])

    def test_ordering_and_canonical_normalized_bytes_are_deterministic(self):
        first = parse_match_payload(self.payload, policy=FIXTURE_POLICY)
        second = parse_match_payload(copy.deepcopy(self.payload), policy=FIXTURE_POLICY)
        reversed_payload = copy.deepcopy(self.payload)
        reversed_payload["events"].reverse()
        reordered = parse_match_payload(reversed_payload, policy=FIXTURE_POLICY)

        self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
        self.assertEqual(
            [event.provider_event_id for event in first.events],
            [event.provider_event_id for event in reordered.events],
        )
        self.assertEqual(
            [event.event_index for event in first.events],
            list(range(len(first.events))),
        )

    def test_normalized_values_never_include_commentary_or_qualifier_arrays(self):
        self.payload["events"][0]["commentary"] = "private source commentary"
        result = parse_match_payload(self.payload, policy=FIXTURE_POLICY)
        rendered = result.canonical_bytes().decode()

        self.assertNotIn("commentary", rendered)
        self.assertNotIn("qualifiers", rendered)
        self.assertNotIn("private source commentary", rendered)

    def test_structural_coordinate_and_clock_errors_are_diagnostic(self):
        cases = (
            ("missing match field", lambda payload: payload.pop("home")),
            (
                "coordinate",
                lambda payload: payload["events"][0].__setitem__("x", 100.01),
            ),
            (
                "clock",
                lambda payload: payload["events"][0].__setitem__("second", 60),
            ),
            (
                "required event field",
                lambda payload: payload["events"][0].pop("teamId"),
            ),
        )
        for label, mutation in cases:
            malformed = copy.deepcopy(self.payload)
            mutation(malformed)
            with self.subTest(label=label), self.assertRaises(
                WhoScoredNormalizationError
            ) as raised:
                parse_match_payload(malformed, policy=FIXTURE_POLICY)
            self.assertFalse(raised.exception.diagnostics.valid)
            self.assertTrue(raised.exception.diagnostics.errors)

    def test_validation_rejects_low_empty_changed_and_excessive_unknowns(self):
        with self.assertRaises(WhoScoredNormalizationError) as low:
            parse_match_payload(self.payload)
        self.assertEqual(
            low.exception.diagnostics.errors[-1]["code"],
            "implausibly_low_event_count",
        )

        empty = copy.deepcopy(self.payload)
        empty["events"] = []
        with self.assertRaises(WhoScoredNormalizationError) as changed:
            parse_match_payload(empty, policy=FIXTURE_POLICY, changed_payload=True)
        self.assertIn(
            "changed_payload_empty",
            [error["code"] for error in changed.exception.diagnostics.errors],
        )

        drifted = copy.deepcopy(self.payload)
        for index in range(6):
            unknown = copy.deepcopy(drifted["events"][-1])
            unknown["id"] = 95000 + index
            unknown["eventId"] = 100 + index
            drifted["events"].append(unknown)
        with self.assertRaises(WhoScoredNormalizationError) as drift:
            parse_match_payload(drifted, policy=FIXTURE_POLICY)
        codes = [error["code"] for error in drift.exception.diagnostics.errors]
        self.assertIn("unknown_event_tolerance_exceeded", codes)

    def test_shot_orientation_failure_is_structured(self):
        reversed_shots = copy.deepcopy(self.payload)
        for event in reversed_shots["events"]:
            if event["type"]["displayName"] in {
                "Goal",
                "MissedShots",
                "SavedShot",
                "ShotOnPost",
            }:
                event["x"] = 15
        with self.assertRaises(WhoScoredNormalizationError) as raised:
            parse_match_payload(reversed_shots, policy=FIXTURE_POLICY)
        self.assertIn(
            "shot_orientation_failed",
            [error["code"] for error in raised.exception.diagnostics.errors],
        )


class WhoScoredEventReplacementTests(TestCase):
    def setUp(self):
        competition = Competition.objects.create(
            name="Premier League",
            short_code="ENG1",
            country="England",
        )
        season = Season.objects.create(label="2025-26", sort_order=2026)
        competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
            has_whoscored=True,
            whoscored_league="ENG-Premier League",
            whoscored_season="2526",
            whoscored_expected_match_count=380,
        )
        self.provider_match = ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id="9000001",
            competition_season=competition_season,
            kickoff_at=datetime(2025, 8, 16, 14, 0, tzinfo=timezone.utc),
            status=ProviderMatchStatus.COMPLETED,
            home_provider_team_id="9101",
            away_provider_team_id="9102",
            home_score=2,
            away_score=1,
        )
        ProviderMatchEvent.objects.create(
            provider_match=self.provider_match,
            event_index=0,
            provider_team_id="old",
            minute=0,
            second=0,
            event_type=MatchEventType.ADMINISTRATIVE,
        )
        self.normalized = parse_match_payload(
            load_fixture("match_9000001.json"),
            policy=FIXTURE_POLICY,
        )

    def test_replacement_is_complete_and_repeatable(self):
        first_count = replace_match_events(self.provider_match, self.normalized)
        first_values = list(
            self.provider_match.events.order_by("event_index").values(
                *[
                    field.name
                    for field in ProviderMatchEvent._meta.fields
                    if field.name != "id"
                ]
            )
        )
        second_count = replace_match_events(self.provider_match, self.normalized)
        second_values = list(
            self.provider_match.events.order_by("event_index").values(
                *[
                    field.name
                    for field in ProviderMatchEvent._meta.fields
                    if field.name != "id"
                ]
            )
        )

        self.assertEqual(first_count, len(self.normalized.events))
        self.assertEqual(second_count, len(self.normalized.events))
        self.assertEqual(first_values, second_values)
        self.assertNotIn("old", {event["provider_team_id"] for event in second_values})

    def test_database_failure_rolls_back_deleted_event_set(self):
        with patch.object(
            ProviderMatchEvent.objects,
            "bulk_create",
            side_effect=DatabaseError("synthetic database failure"),
        ):
            with self.assertRaises(DatabaseError):
                replace_match_events(self.provider_match, self.normalized)

        rows = list(
            self.provider_match.events.values_list("provider_team_id", flat=True)
        )
        self.assertEqual(rows, ["old"])

    def test_parser_failure_never_touches_existing_events(self):
        malformed = load_fixture("match_9000001.json")
        malformed["events"][0]["x"] = -1
        with self.assertRaises(WhoScoredNormalizationError):
            parsed = parse_match_payload(malformed, policy=FIXTURE_POLICY)
            replace_match_events(self.provider_match, parsed)

        rows = list(
            self.provider_match.events.values_list("provider_team_id", flat=True)
        )
        self.assertEqual(rows, ["old"])
