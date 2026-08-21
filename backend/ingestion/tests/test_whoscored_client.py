from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

from ingestion.services.whoscored_client import (
    RetrievedMatchPayload,
    SoccerdataWhoScoredClient,
    SourceMatch,
    WhoScoredSourceConfig,
    canonical_json_bytes,
    coordinate_range_errors,
    payload_sha256,
    safe_failure_evidence,
    shot_orientation_gate,
    shot_orientation_summary,
    summarize_match_payload,
    _validated_json_document,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "whoscored"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


class FakeWhoScoredReader:
    def __init__(self, *, schedule, payloads, **kwargs) -> None:
        self.schedule = schedule
        self.payloads = payloads
        self.data_dir = Path(kwargs["data_dir"])
        self.options = kwargs
        self._driver = object()
        self.calls: list[dict[str, Any]] = []

    def read_schedule(self, force_cache: bool = False):
        self.calls.append({"method": "schedule", "force_cache": force_cache})
        return pd.DataFrame(self.schedule).set_index(["league", "season", "game"])

    def read_events(self, **kwargs):
        self.calls.append({"method": "events", **kwargs})
        match_id = int(kwargs["match_id"])
        schedule_row = next(row for row in self.schedule if row["game_id"] == match_id)
        path = (
            self.data_dir
            / "events"
            / f"{schedule_row['league']}_{schedule_row['season']}"
            / f"{match_id}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.payloads[match_id]), encoding="utf-8")
        # Deliberately mimic soccerdata 1.9's events-only "raw" return shape.
        # The adapter must ignore it and read the complete cache file.
        return {match_id: self.payloads[match_id]["events"]}


class WhoScoredClientFoundationTests(SimpleTestCase):
    def setUp(self) -> None:
        self.schedule_fixture = load_fixture("schedule.json")
        self.match_one = load_fixture("match_9000001.json")
        self.match_two = load_fixture("match_9000002.json")

    def test_canonical_checksum_is_stable_across_mapping_order(self) -> None:
        reordered = dict(reversed(list(self.match_one.items())))

        self.assertEqual(canonical_json_bytes(self.match_one), canonical_json_bytes(reordered))
        self.assertEqual(payload_sha256(self.match_one), payload_sha256(reordered))
        self.assertEqual(len(payload_sha256(self.match_one)), 64)

    def test_source_config_and_reader_invocation_are_headless_by_default(self) -> None:
        readers: list[FakeWhoScoredReader] = []

        def factory(**kwargs):
            reader = FakeWhoScoredReader(
                schedule=self.schedule_fixture["matches"],
                payloads={9000001: self.match_one, 9000002: self.match_two},
                **kwargs,
            )
            readers.append(reader)
            return reader

        with tempfile.TemporaryDirectory() as tmp:
            config = WhoScoredSourceConfig(
                league="ENG-Premier League",
                season="2025-26",
                data_dir=Path(tmp),
            )
            client = SoccerdataWhoScoredClient(config, reader_factory=factory)
            client.list_matches()

        self.assertTrue(config.headless)
        self.assertTrue(readers[0].options["headless"])

    def test_reader_initialization_fails_closed_without_a_browser_driver(self) -> None:
        class ReaderWithoutDriver:
            def __init__(self, **kwargs):
                self.options = kwargs

        with tempfile.TemporaryDirectory() as tmp:
            client = SoccerdataWhoScoredClient(
                WhoScoredSourceConfig(
                    league="ENG-Premier League",
                    season="2025-26",
                    data_dir=Path(tmp),
                ),
                reader_factory=ReaderWithoutDriver,
            )

            with self.assertRaisesRegex(RuntimeError, "browser failed to initialize"):
                client.list_matches()

    def test_failure_evidence_is_categorical_and_does_not_retain_private_details(self) -> None:
        secret = "https://user:password@example.test/match?token=private cookie=session"
        cases = (
            (RuntimeError(f"Cloudflare captcha at {secret}"), "anti_bot_challenge"),
            (TimeoutError(secret), "navigation_failure"),
            (json.JSONDecodeError(secret, "", 0), "parser_failure"),
            (ValueError(f"schema drift {secret}"), "source_change"),
            (FileNotFoundError(secret), "payload_extraction_failure"),
        )

        for error, category in cases:
            with self.subTest(category=category):
                evidence = safe_failure_evidence(
                    error,
                    stage="match_processing",
                    headless=True,
                )
                rendered = json.dumps(evidence)
                self.assertEqual(evidence["category"], category)
                self.assertTrue(evidence["headless"])
                self.assertNotIn("password", rendered)
                self.assertNotIn("token", rendered)
                self.assertNotIn("cookie", rendered)

    def test_data_endpoint_compatibility_extracts_json_and_rejects_html(self) -> None:
        payload = '{"tournaments":[{"matches":[]}]}'

        self.assertEqual(
            _validated_json_document(
                "https://www.whoscored.com/tournaments/24533/data/?d=202508",
                payload,
            ),
            payload,
        )
        with self.assertRaises(json.JSONDecodeError):
            _validated_json_document(
                "https://www.whoscored.com/tournaments/24533/data/?d=202508",
                "<html>challenge</html>",
            )
        with self.assertRaises(ValueError):
            _validated_json_document("https://www.whoscored.com/", payload)

    def test_fixture_coordinates_and_acting_team_orientation(self) -> None:
        self.assertEqual(coordinate_range_errors(self.match_one), [])
        orientation = shot_orientation_summary(self.match_one)

        self.assertEqual({row["team_id"] for row in orientation}, {"9101", "9102"})
        self.assertTrue(all(row["assessed"] for row in orientation))
        self.assertTrue(all(row["attacks_toward_x100"] for row in orientation))
        self.assertTrue(all(row["median_x"] >= 80 for row in orientation))

    def test_coordinate_validation_reports_field_and_event(self) -> None:
        malformed = {"events": [{"type": {"displayName": "Pass"}, "x": 101, "y": "wide"}]}
        self.assertEqual(
            coordinate_range_errors(malformed),
            [
                "events[0].x=101 is outside 0..100",
                "events[0].y is not numeric",
            ],
        )

    def test_safe_summary_contains_no_raw_events_or_player_dictionary(self) -> None:
        summary = summarize_match_payload(9000001, self.match_one)

        self.assertEqual(summary["match_id"], 9000001)
        self.assertEqual(summary["event_count"], len(self.match_one["events"]))
        self.assertEqual(summary["missing_player_id_count"], 1)
        self.assertEqual(summary["coordinate_error_count"], 0)
        self.assertNotIn("events", summary)
        self.assertNotIn("playerIdNameDictionary", summary)

    def test_orientation_gate_requires_a_meaningful_assessed_sample(self) -> None:
        assessed_report = summarize_match_payload(9000001, self.match_one)
        unassessed_report = summarize_match_payload(9000002, self.match_two)

        passed = shot_orientation_gate([assessed_report])
        self.assertTrue(passed["passed"])
        self.assertEqual(passed["assessed_team_sides"], 2)

        unassessed = shot_orientation_gate([unassessed_report])
        self.assertFalse(unassessed["passed"])
        self.assertEqual(unassessed["assessed_team_sides"], 0)

        reversed_report = {
            "shot_orientation": [
                {
                    "team_id": "9101",
                    "assessed": True,
                    "attacks_toward_x100": False,
                },
                {
                    "team_id": "9102",
                    "assessed": True,
                    "attacks_toward_x100": True,
                },
            ]
        }
        reversed_gate = shot_orientation_gate([reversed_report])
        self.assertFalse(reversed_gate["passed"])
        self.assertEqual(reversed_gate["failed_team_sides"], 1)

    def test_fixture_set_covers_v1_families_unknowns_and_transfer(self) -> None:
        event_names = {
            event["type"]["displayName"] for event in self.match_one["events"]
        }
        expected = {
            "Pass",
            "Goal",
            "MissedShots",
            "SavedShot",
            "ShotOnPost",
            "BallTouch",
            "TakeOn",
            "BallRecovery",
            "Tackle",
            "Interception",
            "Clearance",
            "BlockedPass",
            "Aerial",
            "Challenge",
            "Dispossessed",
            "Foul",
            "Card",
            "OffsideGiven",
            "SubstitutionOff",
            "SubstitutionOn",
            "SyntheticUnknownEvent",
        }
        self.assertTrue(self.match_one["_fixture"]["sanitized"])
        self.assertTrue(self.match_one["_fixture"]["synthetic"])
        self.assertTrue(expected.issubset(event_names))
        self.assertTrue(
            any(event.get("playerId") is None for event in self.match_one["events"])
        )
        self.assertTrue(
            any(
                qualifier["type"]["displayName"] == "SyntheticUnknownQualifier"
                for event in self.match_one["events"]
                for qualifier in event.get("qualifiers", [])
            )
        )
        self.assertIn("9201", self.match_one["playerIdNameDictionary"])
        self.assertIn("9201", self.match_two["playerIdNameDictionary"])
        self.assertNotEqual(
            self.match_one["home"]["teamId"],
            self.match_two["home"]["teamId"],
        )

    def test_adapter_normalizes_schedule_and_reads_full_cached_payload(self) -> None:
        schedule = self.schedule_fixture["matches"]
        payloads = {9000001: self.match_one, 9000002: self.match_two}
        readers: list[FakeWhoScoredReader] = []

        def factory(**kwargs):
            reader = FakeWhoScoredReader(schedule=schedule, payloads=payloads, **kwargs)
            readers.append(reader)
            return reader

        with tempfile.TemporaryDirectory() as tmp:
            client = SoccerdataWhoScoredClient(
                WhoScoredSourceConfig(
                    league="ENG-Premier League",
                    season="2025-26",
                    data_dir=Path(tmp),
                    headless=True,
                ),
                reader_factory=factory,
            )
            matches = client.list_matches(force_cache=True)
            retrieved = client.fetch_match_payload(9000001)

        self.assertEqual([match.match_id for match in matches], [9000001, 9000002, 9000003])
        self.assertEqual([match.status for match in matches], ["completed", "completed", "scheduled"])
        self.assertEqual(matches[0].home_score, 2)
        self.assertEqual(matches[0].away_score, 1)
        self.assertEqual(matches[0].kickoff_at.isoformat(), "2025-08-16T14:00:00+00:00")
        self.assertEqual(retrieved.payload["home"]["teamId"], 9101)
        self.assertIn("playerIdNameDictionary", retrieved.payload)
        self.assertEqual(retrieved.sha256, payload_sha256(self.match_one))
        event_call = next(call for call in readers[0].calls if call["method"] == "events")
        self.assertIsNone(event_call["output_fmt"])
        self.assertTrue(event_call["force_cache"])
        self.assertFalse(event_call["live"])

    def test_forced_event_refetch_reuses_discovered_schedule(self) -> None:
        schedule = self.schedule_fixture["matches"]
        payloads = {9000001: self.match_one, 9000002: self.match_two}
        readers: list[FakeWhoScoredReader] = []

        def factory(**kwargs):
            reader = FakeWhoScoredReader(schedule=schedule, payloads=payloads, **kwargs)
            readers.append(reader)
            return reader

        with tempfile.TemporaryDirectory() as tmp:
            client = SoccerdataWhoScoredClient(
                WhoScoredSourceConfig(
                    league="ENG-Premier League",
                    season="2025-26",
                    data_dir=Path(tmp),
                    headless=True,
                ),
                reader_factory=factory,
            )
            client.list_matches(force_cache=False)
            client.fetch_match_payload(9000001, force=True)

        schedule_calls = [
            call for call in readers[0].calls if call["method"] == "schedule"
        ]
        self.assertEqual(schedule_calls, [{"method": "schedule", "force_cache": False}])
        event_call = next(call for call in readers[0].calls if call["method"] == "events")
        self.assertTrue(event_call["force_cache"])
        self.assertTrue(event_call["live"])

    def _source_match(self, match_id: int) -> SourceMatch:
        return SourceMatch(
            match_id=match_id,
            kickoff_at=datetime(2025, 8, 16, 14, 0, tzinfo=timezone.utc),
            status="completed",
            home_team_id=9101,
            away_team_id=9102,
            home_team_name="Synthetic A",
            away_team_name="Synthetic B",
            home_score=2,
            away_score=1,
            source_league="ENG-Premier League",
            source_season="2526",
        )

    @patch(
        "ingestion.management.commands.probe_whoscored_source."
        "SoccerdataWhoScoredClient"
    )
    def test_probe_command_outputs_only_safe_diagnostics(self, client_class) -> None:
        client = client_class.return_value
        client.list_matches.return_value = [self._source_match(9000001)]
        canonical = canonical_json_bytes(self.match_one)
        client.fetch_match_payload.return_value = RetrievedMatchPayload(
            match_id=9000001,
            payload=self.match_one,
            canonical_bytes=canonical,
            sha256=payload_sha256(self.match_one),
            cache_path=Path("/private/cache/9000001.json"),
        )
        stdout = StringIO()

        call_command(
            "probe_whoscored_source",
            match_id=[9000001],
            match_count=1,
            stdout=stdout,
        )

        rendered = stdout.getvalue()
        source_config = client_class.call_args.args[0]
        self.assertTrue(source_config.headless)
        self.assertIn("WhoScored source probe passed.", rendered)
        self.assertIn('"mode": "headless"', rendered)
        self.assertIn('"passed": true', rendered)
        self.assertNotIn("playerIdNameDictionary", rendered)
        self.assertNotIn("Synthetic Player One", rendered)
        self.assertNotIn('"qualifiers"', rendered)

    @patch(
        "ingestion.management.commands.probe_whoscored_source."
        "SoccerdataWhoScoredClient"
    )
    def test_probe_command_rejects_an_unassessed_orientation_sample(
        self,
        client_class,
    ) -> None:
        client = client_class.return_value
        client.list_matches.return_value = [self._source_match(9000002)]
        canonical = canonical_json_bytes(self.match_two)
        client.fetch_match_payload.return_value = RetrievedMatchPayload(
            match_id=9000002,
            payload=self.match_two,
            canonical_bytes=canonical,
            sha256=payload_sha256(self.match_two),
            cache_path=Path("/private/cache/9000002.json"),
        )

        with self.assertRaisesMessage(
            CommandError,
            "orientation gate did not pass",
        ):
            call_command(
                "probe_whoscored_source",
                match_id=[9000002],
                match_count=1,
                headless=True,
            )
