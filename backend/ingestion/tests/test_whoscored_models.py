from __future__ import annotations

from datetime import datetime, timezone

from django.contrib import admin
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from ingestion.admin import ProviderMatchPayloadAdmin
from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    EventProfileSplitType,
    IngestionKind,
    IngestionRun,
    MatchEventType,
    PlayerSeasonEventProfile,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchPayload,
    ProviderMatchStatus,
    ProviderPayloadLifecycle,
    Season,
    TeamSeasonEventProfile,
)


def _competition_season() -> CompetitionSeason:
    competition = Competition.objects.create(
        name="Premier League",
        short_code="ENG1",
        country="England",
    )
    season = Season.objects.create(label="2025-26", sort_order=2026)
    return CompetitionSeason.objects.create(
        competition=competition,
        season=season,
        has_whoscored=True,
        whoscored_league="ENG-Premier League",
        whoscored_season="2526",
        whoscored_expected_match_count=380,
    )


def _provider_match(competition_season: CompetitionSeason, match_id: str = "1912345") -> ProviderMatch:
    return ProviderMatch.objects.create(
        provider=Provider.WHOSCORED,
        provider_match_id=match_id,
        competition_season=competition_season,
        kickoff_at=datetime(2026, 5, 17, 15, 0, tzinfo=timezone.utc),
        status=ProviderMatchStatus.COMPLETED,
        home_provider_team_id="13",
        away_provider_team_id="32",
        home_score=2,
        away_score=1,
    )


class WhoScoredPersistenceModelTests(TestCase):
    def setUp(self):
        self.competition_season = _competition_season()
        self.player = CanonicalPlayer.objects.create(display_name="A Player")
        self.team = CanonicalTeam.objects.create(name="A Team")
        self.other_team = CanonicalTeam.objects.create(name="Another Team")
        self.run = IngestionRun.objects.create(
            kind=IngestionKind.EVENT_PROFILES,
            competition_season=self.competition_season,
        )

    def test_competition_season_support_requires_complete_source_configuration(self):
        self.assertTrue(self.competition_season.supports_whoscored)
        self.competition_season.whoscored_season = ""
        self.assertFalse(self.competition_season.supports_whoscored)
        self.competition_season.whoscored_season = "2526"
        self.competition_season.has_whoscored = False
        self.assertFalse(self.competition_season.supports_whoscored)

    def test_provider_match_and_event_natural_keys_are_unique(self):
        provider_match = _provider_match(self.competition_season)

        with self.assertRaises(IntegrityError), transaction.atomic():
            _provider_match(self.competition_season)

        ProviderMatchEvent.objects.create(
            provider_match=provider_match,
            event_index=0,
            provider_team_id="13",
            minute=0,
            second=0,
            event_type=MatchEventType.PASS,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProviderMatchEvent.objects.create(
                provider_match=provider_match,
                event_index=0,
                provider_team_id="13",
                minute=0,
                second=1,
                event_type=MatchEventType.BALL_TOUCH,
            )

    def test_event_coordinate_and_clock_constraints_are_enforced(self):
        provider_match = _provider_match(self.competition_season)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProviderMatchEvent.objects.create(
                provider_match=provider_match,
                event_index=0,
                provider_team_id="13",
                minute=1,
                second=60,
                event_type=MatchEventType.PASS,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProviderMatchEvent.objects.create(
                provider_match=provider_match,
                event_index=1,
                provider_team_id="13",
                minute=1,
                second=1,
                event_type=MatchEventType.PASS,
                x=10001,
            )

    def test_match_delete_cascades_current_payload_and_events(self):
        provider_match = _provider_match(self.competition_season)
        ProviderMatchPayload.objects.create(
            provider_match=provider_match,
            payload_gzip=b"compressed",
            payload_sha256="a" * 64,
            payload_size_bytes=10,
            uncompressed_size_bytes=100,
            lifecycle_state=ProviderPayloadLifecycle.FINAL,
            final_sha256="a" * 64,
            final_fetched_at=datetime.now(tz=timezone.utc),
            fetched_at=datetime.now(tz=timezone.utc),
        )
        ProviderMatchEvent.objects.create(
            provider_match=provider_match,
            event_index=0,
            provider_team_id="13",
            minute=0,
            second=0,
            event_type=MatchEventType.PASS,
        )

        provider_match.delete()

        self.assertFalse(ProviderMatchPayload.objects.exists())
        self.assertFalse(ProviderMatchEvent.objects.exists())

    def test_payload_storage_and_lifecycle_constraints_are_enforced(self):
        provider_match = _provider_match(self.competition_season)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProviderMatchPayload.objects.create(
                provider_match=provider_match,
                payload_gzip=b"compressed",
                object_key="also-present",
                payload_sha256="a" * 64,
                payload_size_bytes=10,
                uncompressed_size_bytes=100,
                lifecycle_state=ProviderPayloadLifecycle.FINAL,
                final_sha256="a" * 64,
                final_fetched_at=datetime.now(tz=timezone.utc),
                fetched_at=datetime.now(tz=timezone.utc),
            )

    def test_payload_lifecycle_audit_fields_must_match_current_payload(self):
        now = datetime.now(tz=timezone.utc)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProviderMatchPayload.objects.create(
                provider_match=_provider_match(self.competition_season, "1912346"),
                payload_gzip=b"compressed",
                payload_sha256="a" * 64,
                payload_size_bytes=10,
                uncompressed_size_bytes=100,
                lifecycle_state=ProviderPayloadLifecycle.FINAL,
                final_sha256="b" * 64,
                final_fetched_at=now,
                fetched_at=now,
            )

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProviderMatchPayload.objects.create(
                provider_match=_provider_match(self.competition_season, "1912347"),
                payload_gzip=b"compressed",
                payload_sha256="a" * 64,
                payload_size_bytes=10,
                uncompressed_size_bytes=100,
                lifecycle_state=ProviderPayloadLifecycle.FINAL,
                preliminary_sha256="a" * 64,
                final_sha256="a" * 64,
                final_fetched_at=now,
                fetched_at=now,
            )

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProviderMatchPayload.objects.create(
                provider_match=_provider_match(self.competition_season, "1912348"),
                payload_gzip=b"compressed",
                payload_sha256="a" * 64,
                payload_size_bytes=10,
                uncompressed_size_bytes=100,
                lifecycle_state=ProviderPayloadLifecycle.PRELIMINARY,
                preliminary_sha256="a" * 64,
                preliminary_fetched_at=now,
                final_sha256="a" * 64,
                final_fetched_at=now,
                fetched_at=now,
            )

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProviderMatchPayload.objects.create(
                provider_match=_provider_match(self.competition_season, "1912349"),
                payload_gzip=b"compressed",
                payload_sha256="a" * 64,
                payload_size_bytes=0,
                uncompressed_size_bytes=100,
                lifecycle_state=ProviderPayloadLifecycle.FINAL,
                final_sha256="a" * 64,
                final_fetched_at=now,
                fetched_at=now,
            )

    def test_preliminary_payload_can_exist_without_final_metadata(self):
        now = datetime.now(tz=timezone.utc)
        payload = ProviderMatchPayload.objects.create(
            provider_match=_provider_match(self.competition_season, "1912350"),
            payload_gzip=b"compressed",
            payload_sha256="a" * 64,
            payload_size_bytes=10,
            uncompressed_size_bytes=100,
            lifecycle_state=ProviderPayloadLifecycle.PRELIMINARY,
            preliminary_sha256="a" * 64,
            preliminary_fetched_at=now,
            fetched_at=now,
        )
        self.assertEqual(payload.lifecycle_state, ProviderPayloadLifecycle.PRELIMINARY)

    def test_current_player_profile_is_unique_per_scope_across_formulas(self):
        PlayerSeasonEventProfile.objects.create(
            competition_season=self.competition_season,
            player=self.player,
            split_type=EventProfileSplitType.SEASON_TOTAL,
            materialized_ingestion_run=self.run,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            PlayerSeasonEventProfile.objects.create(
                competition_season=self.competition_season,
                player=self.player,
                split_type=EventProfileSplitType.SEASON_TOTAL,
                formula_version="event_profiles_v2",
                materialized_ingestion_run=self.run,
            )

        PlayerSeasonEventProfile.objects.create(
            competition_season=self.competition_season,
            player=self.player,
            team=self.team,
            split_type=EventProfileSplitType.TEAM,
            materialized_ingestion_run=self.run,
        )
        PlayerSeasonEventProfile.objects.create(
            competition_season=self.competition_season,
            player=self.player,
            team=self.other_team,
            split_type=EventProfileSplitType.TEAM,
            materialized_ingestion_run=self.run,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            PlayerSeasonEventProfile.objects.create(
                competition_season=self.competition_season,
                player=self.player,
                team=self.team,
                split_type=EventProfileSplitType.TEAM,
                formula_version="event_profiles_v2",
                materialized_ingestion_run=self.run,
            )

    def test_player_profile_scope_constraint_rejects_mismatched_team(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PlayerSeasonEventProfile.objects.create(
                competition_season=self.competition_season,
                player=self.player,
                team=self.team,
                split_type=EventProfileSplitType.SEASON_TOTAL,
                materialized_ingestion_run=self.run,
            )

    def test_noncurrent_candidate_profile_can_be_built_before_publication(self):
        profile = PlayerSeasonEventProfile.objects.create(
            competition_season=self.competition_season,
            player=self.player,
            split_type=EventProfileSplitType.SEASON_TOTAL,
            materialized_ingestion_run=self.run,
            is_current=False,
        )
        self.assertIsNone(profile.superseded_at)

    def test_current_team_profile_is_unique_across_formulas(self):
        TeamSeasonEventProfile.objects.create(
            competition_season=self.competition_season,
            team=self.team,
            materialized_ingestion_run=self.run,
            expected_match_count=38,
            coverage=0.5,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            TeamSeasonEventProfile.objects.create(
                competition_season=self.competition_season,
                team=self.team,
                formula_version="event_profiles_v2",
                materialized_ingestion_run=self.run,
            )

    def test_documented_event_access_indexes_are_the_only_model_indexes(self):
        indexes = ProviderMatchEvent._meta.indexes
        self.assertEqual(
            [index.fields for index in indexes],
            [
                ["player", "event_type", "provider_match"],
                ["team", "event_type", "provider_match"],
            ],
        )
        self.assertFalse(ProviderMatchEvent._meta.get_field("provider_match").db_index)
        self.assertFalse(ProviderMatchEvent._meta.get_field("player").db_index)
        self.assertFalse(ProviderMatchEvent._meta.get_field("team").db_index)

    def test_payload_admin_never_renders_raw_blob_field(self):
        model_admin = ProviderMatchPayloadAdmin(ProviderMatchPayload, admin.site)
        self.assertIn("payload_gzip", model_admin.exclude)


class WhoScoredSchemaMigrationTests(TransactionTestCase):
    migrate_from = ("ingestion", "0025_materializedapipayload_rendered_json")
    migrate_to = ("ingestion", "0026_competitionseason_has_whoscored_and_more")

    def test_schema_migration_applies_and_reverses_cleanly(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        try:
            old_tables = set(connection.introspection.table_names())
            self.assertNotIn("ingestion_providermatch", old_tables)

            executor = MigrationExecutor(connection)
            executor.migrate([self.migrate_to])
            new_tables = set(connection.introspection.table_names())
            self.assertIn("ingestion_providermatch", new_tables)
            self.assertIn("ingestion_providermatchevent", new_tables)
            self.assertIn("ingestion_playerseasoneventprofile", new_tables)
            self.assertIn("ingestion_teamseasoneventprofile", new_tables)

            executor = MigrationExecutor(connection)
            executor.migrate([self.migrate_from])
            reversed_tables = set(connection.introspection.table_names())
            self.assertNotIn("ingestion_providermatch", reversed_tables)
            with connection.cursor() as cursor:
                columns = {
                    column.name
                    for column in connection.introspection.get_table_description(
                        cursor,
                        "ingestion_competitionseason",
                    )
                }
            self.assertNotIn("has_whoscored", columns)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate([self.migrate_to])
