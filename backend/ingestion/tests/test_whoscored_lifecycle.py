from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from django.test import TestCase

from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    MatchGameStateExclusionReason,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchPayload,
    ProviderMatchStatus,
    ProviderMatchTeamGameStateEpisode,
    ProviderPayloadLifecycle,
    ProviderPlayerMapping,
    ProviderTeamMapping,
    Season,
)
from ingestion.services.whoscored_client import RetrievedMatchPayload, SourceMatch
from ingestion.services.whoscored_lifecycle import (
    WhoScoredAccessCutoffError,
    WhoScoredFetchPolicy,
    WhoScoredLifecycleService,
    WhoScoredRequestController,
)
from ingestion.services.whoscored_normalization import NormalizationPolicy


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "whoscored"
NOW = datetime(2026, 7, 28, 12, tzinfo=timezone.utc)


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
    for index, (event_name, period, period_name, minute) in enumerate(
        (
            ("Start", 1, "FirstHalf", 0),
            ("End", 1, "FirstHalf", 45),
            ("Start", 2, "SecondHalf", 45),
            ("End", 2, "SecondHalf", 90),
        )
    ):
        payload["events"].append(
            {
                "id": 99001 + index,
                "eventId": 99001 + index,
                "minute": minute,
                "second": 0,
                "expandedMinute": minute,
                "teamId": team_id,
                "period": {"value": period, "displayName": period_name},
                "type": {"value": 30, "displayName": event_name},
                "outcomeType": {"value": 1, "displayName": "Successful"},
                "qualifiers": [],
            }
        )


class FakeWhoScoredClient:
    def __init__(self, payloads: list[dict] | None = None) -> None:
        self.payloads = list(payloads or [])
        self.fetch_calls: list[tuple[int, bool]] = []
        self.matches: list[SourceMatch] = []

    def list_matches(self, *, force_cache: bool = False) -> list[SourceMatch]:
        del force_cache
        return self.matches

    def fetch_match_payload(
        self,
        match_id: int,
        *,
        force: bool = False,
    ) -> RetrievedMatchPayload:
        self.fetch_calls.append((match_id, force))
        value = self.payloads.pop(0)
        canonical = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return RetrievedMatchPayload(
            match_id=match_id,
            payload=value,
            canonical_bytes=canonical,
            sha256="source-client-checksum",
            cache_path=Path(f"/tmp/{match_id}.json"),
        )


class WhoScoredLifecycleTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        competition = Competition.objects.create(
            name="Premier League",
            short_code="ENG1",
            country="England",
        )
        season = Season.objects.create(label="2025-26", sort_order=2026)
        cls.competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
            has_whoscored=True,
            whoscored_league="ENG-Premier League",
            whoscored_season="2025-26",
            whoscored_expected_match_count=380,
        )

    def setUp(self) -> None:
        self.payload = json.loads(
            (FIXTURE_DIR / "match_9000001.json").read_text(encoding="utf-8")
        )
        self.client = FakeWhoScoredClient([self.payload])
        self.sleeper = Mock()
        self.request_controller = WhoScoredRequestController(
            policy=WhoScoredFetchPolicy(
                minimum_match_delay_seconds=0,
                maximum_match_delay_seconds=0,
                retry_base_delay_seconds=1,
            ),
            sleeper=self.sleeper,
        )
        self.service = WhoScoredLifecycleService(
            competition_season=self.competition_season,
            client=self.client,
            request_controller=self.request_controller,
            clock=lambda: NOW,
            normalization_policy=NormalizationPolicy(minimum_event_count=0),
        )
        self.provider_match = ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id="9000001",
            competition_season=self.competition_season,
            kickoff_at=NOW - timedelta(days=10),
            status=ProviderMatchStatus.COMPLETED,
            home_provider_team_id="101",
            away_provider_team_id="202",
            home_score=2,
            away_score=1,
        )

    def test_discovers_and_upserts_schedule_metadata(self) -> None:
        self.client.matches = [
            SourceMatch(
                match_id=9000002,
                kickoff_at=NOW - timedelta(days=1),
                status="completed",
                home_team_id=303,
                away_team_id=404,
                home_team_name="Home",
                away_team_name="Away",
                home_score=1,
                away_score=1,
                source_league="ENG-Premier League",
                source_season="2025-26",
            )
        ]

        matches = self.service.discover_matches()

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].provider_match_id, "9000002")
        self.assertEqual(matches[0].status, ProviderMatchStatus.COMPLETED)
        self.assertEqual(matches[0].home_score, 1)

    def test_historical_fetch_is_stored_as_final_with_canonical_gzip(self) -> None:
        result = self.service.process_match(self.provider_match, historical=True)

        stored = ProviderMatchPayload.objects.get(provider_match=self.provider_match)
        decoded = json.loads(gzip.decompress(stored.payload_gzip))
        self.assertEqual(result.action, "stored")
        self.assertEqual(result.lifecycle_state, ProviderPayloadLifecycle.FINAL)
        self.assertEqual(decoded["schema_version"], 1)
        self.assertEqual(decoded["provider"], "whoscored")
        self.assertEqual(decoded["payload"]["matchId"], 9000001)
        self.assertEqual(
            stored.payload_size_bytes,
            len(bytes(stored.payload_gzip)),
        )
        self.assertEqual(
            stored.uncompressed_size_bytes,
            len(gzip.decompress(stored.payload_gzip)),
        )
        self.assertEqual(
            ProviderMatchEvent.objects.filter(
                provider_match=self.provider_match
            ).count(),
            result.normalized_event_count,
        )
        game_state = ProviderMatchGameState.objects.get(
            provider_match=self.provider_match
        )
        self.assertEqual(game_state.event_count, result.normalized_event_count)

    def test_final_payload_is_reused_without_request_unless_forced(self) -> None:
        first = self.service.process_match(self.provider_match, historical=True)
        event_ids = sorted(self.provider_match.events.values_list("id", flat=True))

        second = self.service.process_match(self.provider_match, historical=True)
        self.client.payloads.append(self.payload)
        forced = self.service.process_match(
            self.provider_match,
            historical=True,
            force=True,
        )

        self.assertEqual(first.action, "stored")
        self.assertEqual(second.action, "reused_final")
        self.assertEqual(forced.action, "unchanged")
        self.assertEqual(self.client.fetch_calls, [(9000001, False), (9000001, True)])
        self.assertEqual(
            sorted(self.provider_match.events.values_list("id", flat=True)),
            event_ids,
        )

    def test_preliminary_payload_waits_until_settlement_is_due(self) -> None:
        first = self.service.process_match(self.provider_match, historical=False)

        waiting = self.service.process_match(
            self.provider_match,
            historical=False,
        )

        self.assertEqual(first.lifecycle_state, ProviderPayloadLifecycle.PRELIMINARY)
        self.assertEqual(waiting.action, "awaiting_settlement")
        self.assertEqual(len(self.client.fetch_calls), 1)

    def test_recent_completion_settles_unchanged_without_event_rewrite(self) -> None:
        home = CanonicalTeam.objects.create(name="Synthetic A")
        away = CanonicalTeam.objects.create(name="Synthetic B")
        ProviderTeamMapping.objects.create(
            provider=Provider.WHOSCORED,
            provider_team_id="9101",
            canonical_team=home,
        )
        ProviderTeamMapping.objects.create(
            provider=Provider.WHOSCORED,
            provider_team_id="9102",
            canonical_team=away,
        )
        self.provider_match.home_provider_team_id = "9101"
        self.provider_match.away_provider_team_id = "9102"
        self.provider_match.home_team = home
        self.provider_match.away_team = away
        self.provider_match.home_score = 1
        self.provider_match.away_score = 0
        self.provider_match.save(
            update_fields=[
                "home_provider_team_id",
                "away_provider_team_id",
                "home_team",
                "away_team",
                "home_score",
                "away_score",
            ]
        )
        add_exact_test_clock(self.payload)
        preliminary = self.service.process_match(
            self.provider_match,
            historical=False,
        )
        preliminary_state = ProviderMatchGameState.objects.get(
            provider_match=self.provider_match
        )
        self.assertFalse(preliminary_state.eligible)
        self.assertEqual(
            preliminary_state.exclusion_reason,
            MatchGameStateExclusionReason.NON_FINAL_PAYLOAD,
        )
        payload = ProviderMatchPayload.objects.get(provider_match=self.provider_match)
        payload.preliminary_fetched_at = NOW - timedelta(hours=12)
        payload.fetched_at = NOW - timedelta(hours=12)
        payload.save(update_fields=["preliminary_fetched_at", "fetched_at"])
        event_ids = sorted(self.provider_match.events.values_list("id", flat=True))
        self.client.payloads.append(self.payload)

        settled = self.service.process_match(
            self.provider_match,
            historical=False,
        )

        payload.refresh_from_db()
        settled_state = ProviderMatchGameState.objects.get(
            provider_match=self.provider_match
        )
        self.assertEqual(
            preliminary.lifecycle_state, ProviderPayloadLifecycle.PRELIMINARY
        )
        self.assertEqual(settled.action, "finalized_unchanged")
        self.assertEqual(payload.lifecycle_state, ProviderPayloadLifecycle.FINAL)
        self.assertEqual(payload.final_sha256, payload.preliminary_sha256)
        self.assertTrue(settled_state.eligible)
        self.assertEqual(settled_state.exposure_seconds, 90 * 60)
        self.assertTrue(
            ProviderMatchTeamGameStateEpisode.objects.filter(
                provider_match=self.provider_match
            ).exists()
        )
        self.assertEqual(
            sorted(self.provider_match.events.values_list("id", flat=True)),
            event_ids,
        )

    def test_changed_settlement_replaces_only_target_match_atomically(self) -> None:
        player = CanonicalPlayer.objects.create(display_name="Mapped Player")
        team = CanonicalTeam.objects.create(name="Mapped Team")
        ProviderPlayerMapping.objects.create(
            provider=Provider.WHOSCORED,
            provider_player_id="9201",
            canonical_player=player,
        )
        ProviderTeamMapping.objects.create(
            provider=Provider.WHOSCORED,
            provider_team_id="9101",
            canonical_team=team,
        )
        self.service.process_match(self.provider_match, historical=False)
        payload = ProviderMatchPayload.objects.get(provider_match=self.provider_match)
        payload.preliminary_fetched_at = NOW - timedelta(hours=13)
        payload.fetched_at = NOW - timedelta(hours=13)
        payload.save(update_fields=["preliminary_fetched_at", "fetched_at"])
        old_event_ids = set(self.provider_match.events.values_list("id", flat=True))
        other_match = ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id="9000999",
            competition_season=self.competition_season,
            kickoff_at=NOW - timedelta(days=2),
            status=ProviderMatchStatus.COMPLETED,
            home_provider_team_id="303",
            away_provider_team_id="404",
            home_score=0,
            away_score=0,
        )
        untouched = ProviderMatchEvent.objects.create(
            provider_match=other_match,
            event_index=0,
            provider_team_id="303",
            minute=1,
            second=0,
        )
        changed_payload = json.loads(json.dumps(self.payload))
        changed_payload["events"][0]["minute"] = 2
        self.client.payloads.append(changed_payload)

        result = self.service.process_match(self.provider_match, historical=False)

        self.assertEqual(result.action, "replaced")
        self.assertEqual(result.affected_player_ids, (player.id,))
        self.assertEqual(result.affected_team_ids, (team.id,))
        self.assertFalse(
            old_event_ids & set(self.provider_match.events.values_list("id", flat=True))
        )
        self.assertTrue(ProviderMatchEvent.objects.filter(pk=untouched.pk).exists())

    def test_malformed_changed_payload_preserves_existing_payload_and_events(
        self,
    ) -> None:
        self.service.process_match(self.provider_match, historical=True)
        stored = ProviderMatchPayload.objects.get(provider_match=self.provider_match)
        checksum = stored.payload_sha256
        event_ids = list(self.provider_match.events.values_list("id", flat=True))
        malformed = json.loads(json.dumps(self.payload))
        malformed["events"] = []
        self.client.payloads.append(malformed)

        with self.assertRaises(Exception):
            self.service.process_match(
                self.provider_match,
                historical=True,
                force=True,
            )

        stored.refresh_from_db()
        self.assertEqual(stored.payload_sha256, checksum)
        self.assertEqual(
            list(self.provider_match.events.values_list("id", flat=True)),
            event_ids,
        )

    def test_batch_isolates_malformed_match_from_successful_neighbor(self) -> None:
        malformed_match = ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id="9000002",
            competition_season=self.competition_season,
            kickoff_at=NOW - timedelta(days=9),
            status=ProviderMatchStatus.COMPLETED,
            home_provider_team_id="101",
            away_provider_team_id="202",
            home_score=0,
            away_score=0,
        )
        malformed = json.loads(json.dumps(self.payload))
        del malformed["events"]
        self.client.payloads = [self.payload, malformed]

        result = self.service.process_matches(
            [self.provider_match, malformed_match],
            historical=True,
        )

        self.assertEqual(len(result.matches), 1)
        self.assertEqual(len(result.failures), 1)
        self.assertTrue(
            ProviderMatchPayload.objects.filter(
                provider_match=self.provider_match
            ).exists()
        )
        self.assertFalse(
            ProviderMatchPayload.objects.filter(provider_match=malformed_match).exists()
        )

    def test_transient_retry_uses_increasing_delays(self) -> None:
        client = Mock()
        expected = FakeWhoScoredClient([self.payload]).fetch_match_payload(9000001)
        client.fetch_match_payload.side_effect = [
            TimeoutError("temporary timeout"),
            ConnectionError("temporary connection"),
            expected,
        ]

        result = self.request_controller.fetch(client, 9000001, force=False)

        self.assertEqual(result.match_id, 9000001)
        self.assertEqual(self.request_controller.stats.retries, 2)
        self.assertEqual(self.request_controller.stats.requests, 3)
        self.assertEqual(
            [call.args[0] for call in self.sleeper.call_args_list],
            [1, 2],
        )

    def test_five_consecutive_access_failures_stop_requests(self) -> None:
        client = Mock()
        client.fetch_match_payload.side_effect = RuntimeError("403 access denied")
        controller = WhoScoredRequestController(
            policy=WhoScoredFetchPolicy(
                maximum_attempts=8,
                minimum_match_delay_seconds=0,
                maximum_match_delay_seconds=0,
                retry_base_delay_seconds=0,
                access_failure_limit=5,
            ),
            sleeper=Mock(),
        )

        with self.assertRaises(WhoScoredAccessCutoffError):
            controller.fetch(client, 9000001, force=False)
        with self.assertRaises(WhoScoredAccessCutoffError):
            controller.fetch(client, 9000002, force=False)

        self.assertEqual(client.fetch_match_payload.call_count, 5)
