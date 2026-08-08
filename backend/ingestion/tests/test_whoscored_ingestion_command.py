from dataclasses import replace
from datetime import date, datetime, timezone
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from ingestion.models import (
    Competition, CompetitionSeason, IngestionRun, IngestionRunStatus, Provider,
    ProviderMatch, ProviderMatchStatus, Season,
)
from ingestion.services.whoscored_client import SourceMatch
from ingestion.services.whoscored_ingestion import (
    WhoScoredIngestionOptions,
    run_whoscored_ingestion,
    select_completed_source_matches,
)
from ingestion.services.whoscored_lifecycle import WhoScoredMatchResult


NOW = datetime(2026, 8, 1, 15, tzinfo=timezone.utc)


def source_match(match_id: int, day: int, status: str = "completed") -> SourceMatch:
    return SourceMatch(
        match_id=match_id,
        kickoff_at=NOW.replace(day=day),
        status=status,
        home_team_id=match_id * 10,
        away_team_id=match_id * 10 + 1,
        home_team_name="Home",
        away_team_name="Away",
        home_score=1,
        away_score=0,
        source_league="ENG-Premier League",
        source_season="2025-26",
    )


class FakeClient:
    def __init__(self, matches):
        self.matches = matches
        self.list_calls = []
        self.fetch_calls = []

    def list_matches(self, *, force_cache=False):
        self.list_calls.append(force_cache)
        return self.matches

    def fetch_match_payload(self, match_id, *, force=False):
        self.fetch_calls.append((match_id, force))
        raise AssertionError("dry-run must never fetch a match payload")


class WhoScoredIngestionCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        competition = Competition.objects.create(name="Premier League", short_code="ENG1", country="England")
        season = Season.objects.create(label="2025-26", sort_order=2026)
        cls.slice = CompetitionSeason.objects.create(
            competition=competition, season=season, has_whoscored=True,
            whoscored_league="ENG-Premier League", whoscored_season="2025-26",
        )

    def test_selection_is_completed_deterministic_and_supports_last_and_limit(self):
        matches = [source_match(3, 3), source_match(1, 1), source_match(2, 2), source_match(4, 4, "scheduled")]
        self.assertEqual(
            [match.match_id for match in select_completed_source_matches(matches, WhoScoredIngestionOptions(last_completed=2))],
            [2, 3],
        )
        self.assertEqual(
            [match.match_id for match in select_completed_source_matches(matches, WhoScoredIngestionOptions(limit=2))],
            [1, 2],
        )
        self.assertEqual(
            [match.match_id for match in select_completed_source_matches(matches, WhoScoredIngestionOptions(from_date=date(2026, 8, 2), to_date=date(2026, 8, 3)))],
            [2, 3],
        )

    def test_dry_run_is_database_and_detail_request_immutable(self):
        client = FakeClient([source_match(1, 1), source_match(2, 2)])
        result = run_whoscored_ingestion(
            competition_season=self.slice,
            options=WhoScoredIngestionOptions(dry_run=True, limit=1),
            client=client,
        )
        self.assertIsNone(result.run)
        self.assertEqual(result.stats["planned_match_ids"], [])
        self.assertEqual(client.list_calls, [])
        self.assertEqual(client.fetch_calls, [])
        self.assertEqual(IngestionRun.objects.count(), 0)
        self.assertEqual(self.slice.provider_matches.count(), 0)

    def test_safe_cap_requires_explicit_override_and_records_failed_run(self):
        client = FakeClient([source_match(match_id, 1) for match_id in range(1, 52)])
        with self.assertRaisesRegex(ValueError, "allow-over-cap"):
            run_whoscored_ingestion(
                competition_season=self.slice,
                options=WhoScoredIngestionOptions(),
                client=client,
            )
        run = IngestionRun.objects.get()
        self.assertEqual(run.status, IngestionRunStatus.FAILED)
        self.assertEqual(run.stats["outcome"], "fatal_configuration_failure")
        self.assertEqual(run.stats["matches_considered"], 51)

    def test_schedule_failure_records_fatal_run_status(self):
        client = FakeClient([])
        client.list_matches = lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("invalid provider configuration")
        )

        with self.assertRaisesRegex(RuntimeError, "invalid provider configuration"):
            run_whoscored_ingestion(
                competition_season=self.slice,
                options=WhoScoredIngestionOptions(),
                client=client,
            )

        run = IngestionRun.objects.get()
        self.assertEqual(run.status, IngestionRunStatus.FAILED)
        self.assertEqual(run.stats["outcome"], "fatal_configuration_failure")
        self.assertEqual(run.stats["fatal_error"], "RuntimeError")
        self.assertEqual(run.stats["schedule_requests"], 1)
        self.assertEqual(run.stats["requests"], 1)

    @patch("ingestion.services.whoscored_ingestion.WhoScoredLifecycleService")
    def test_partial_failure_records_successful_neighbours_and_counters(self, lifecycle_class):
        class Controller:
            class stats:
                requests = 3
                retries = 1

        class Lifecycle:
            def __init__(self, **kwargs):
                self.request_controller = Controller()

            def upsert_match(self, source):
                return ProviderMatch.objects.create(
                    provider=Provider.WHOSCORED,
                    provider_match_id=str(source.match_id),
                    competition_season=self_slice,
                    kickoff_at=source.kickoff_at,
                    status=ProviderMatchStatus.COMPLETED,
                    home_provider_team_id=str(source.home_team_id),
                    away_provider_team_id=str(source.away_team_id),
                )

            def process_match(self, provider_match, **kwargs):
                if provider_match.provider_match_id == "2":
                    raise ValueError("malformed payload")
                return WhoScoredMatchResult(
                    provider_match_id=provider_match.provider_match_id,
                    action="stored",
                    lifecycle_state="final",
                    payload_sha256="checksum",
                    normalized_event_count=7,
                )

        self_slice = self.slice
        lifecycle_class.side_effect = Lifecycle
        result = run_whoscored_ingestion(
            competition_season=self.slice,
            options=WhoScoredIngestionOptions(),
            client=FakeClient([source_match(1, 1), source_match(2, 2), source_match(3, 3)]),
        )
        result.run.refresh_from_db()
        self.assertEqual(result.run.status, IngestionRunStatus.FAILED)
        self.assertEqual(result.stats["outcome"], "partial_failure")
        self.assertEqual(result.stats["successful_fetches"], 2)
        self.assertEqual(result.stats["fetch_failures"], 1)
        self.assertEqual(result.stats["validation_failures"], 0)
        self.assertEqual(result.stats["normalized_event_count"], 14)

    @patch("ingestion.services.whoscored_ingestion.WhoScoredLifecycleService")
    def test_malformed_unselected_schedule_row_does_not_abort_selected_match(self, lifecycle_class):
        class Controller:
            class stats:
                requests = 1
                retries = 0

        class Lifecycle:
            def __init__(self, **kwargs):
                self.request_controller = Controller()

            def upsert_match(self, source):
                if source.match_id == 99:
                    raise ValueError("missing kickoff")
                return ProviderMatch.objects.create(
                    provider=Provider.WHOSCORED,
                    provider_match_id=str(source.match_id),
                    competition_season=self_slice,
                    kickoff_at=source.kickoff_at,
                    status=ProviderMatchStatus.COMPLETED,
                    home_provider_team_id=str(source.home_team_id),
                    away_provider_team_id=str(source.away_team_id),
                )

            def process_match(self, provider_match, **kwargs):
                return WhoScoredMatchResult(
                    provider_match_id=provider_match.provider_match_id,
                    action="stored",
                    lifecycle_state="final",
                    payload_sha256="checksum",
                    normalized_event_count=7,
                )

        self_slice = self.slice
        malformed = replace(source_match(99, 3), kickoff_at=None)
        lifecycle_class.side_effect = Lifecycle
        result = run_whoscored_ingestion(
            competition_season=self.slice,
            options=WhoScoredIngestionOptions(match_id=1),
            client=FakeClient([source_match(1, 1), malformed]),
        )

        self.assertEqual(result.run.status, IngestionRunStatus.SUCCESS)
        self.assertEqual(result.stats["successful_fetches"], 1)
        self.assertEqual(result.stats["requests"], 2)
        self.assertEqual(result.stats["schedule_requests"], 1)
        self.assertEqual(result.stats["match_detail_requests"], 1)
        self.assertEqual(result.stats["schedule_failures"][0]["match_id"], "99")
        self.assertFalse(result.stats["schedule_failures"][0]["selected"])

    @patch("ingestion.services.whoscored_ingestion.WhoScoredLifecycleService")
    def test_access_cutoff_stops_remaining_matches_and_records_outcome(self, lifecycle_class):
        class Controller:
            class stats:
                requests = 5
                retries = 3

        class Lifecycle:
            def __init__(self, **kwargs):
                self.request_controller = Controller()
                self.processed = []

            def upsert_match(self, source):
                return ProviderMatch.objects.create(
                    provider=Provider.WHOSCORED,
                    provider_match_id=str(source.match_id),
                    competition_season=self_slice,
                    kickoff_at=source.kickoff_at,
                    status=ProviderMatchStatus.COMPLETED,
                    home_provider_team_id=str(source.home_team_id),
                    away_provider_team_id=str(source.away_team_id),
                )

            def process_match(self, provider_match, **kwargs):
                from ingestion.services.whoscored_lifecycle import WhoScoredAccessCutoffError

                self.processed.append(provider_match.provider_match_id)
                raise WhoScoredAccessCutoffError("access failure cutoff reached")

        self_slice = self.slice
        lifecycle_class.side_effect = Lifecycle
        result = run_whoscored_ingestion(
            competition_season=self.slice,
            options=WhoScoredIngestionOptions(),
            client=FakeClient([source_match(1, 1), source_match(2, 2), source_match(3, 3)]),
        )

        result.run.refresh_from_db()
        self.assertEqual(result.run.status, IngestionRunStatus.FAILED)
        self.assertEqual(result.stats["outcome"], "access_cutoff")
        self.assertEqual(result.stats["requests"], 6)
        self.assertEqual(result.stats["schedule_requests"], 1)
        self.assertEqual(result.stats["match_detail_requests"], 5)
        self.assertEqual(result.stats["retries"], 3)
        self.assertEqual(result.stats["fetch_failures"], 1)
        self.assertEqual(result.stats["successful_fetches"], 0)

    def test_invalid_scope_and_mixed_selectors_raise_without_a_run(self):
        with self.assertRaises(CommandError):
            call_command("ingest_whoscored_events", "--competition", "BIG5", "--season", "2025-26")
        with self.assertRaises(CommandError):
            call_command(
                "ingest_whoscored_events", "--competition", "ENG1", "--season", "2025-26",
                "--match-id", "1", "--limit", "1",
            )
        self.assertEqual(IngestionRun.objects.count(), 0)

    @patch("ingestion.management.commands.ingest_whoscored_events.run_whoscored_ingestion")
    def test_command_parses_concrete_options(self, mock_run):
        from ingestion.services.whoscored_ingestion import WhoScoredIngestionResult

        mock_run.return_value = WhoScoredIngestionResult(run=None, stats={})
        call_command(
            "ingest_whoscored_events", "--competition", "ENG1", "--season", "2025-26",
            "--last-completed", "2", "--dry-run", "--allow-over-cap",
        )
        selected = mock_run.call_args.kwargs["options"]
        self.assertEqual(selected.last_completed, 2)
        self.assertTrue(selected.dry_run)
        self.assertTrue(selected.allow_over_cap)
