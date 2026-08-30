import gzip
import hashlib
import importlib
import json
from datetime import datetime, timezone

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase


class WhoScoredMigrationTests(TransactionTestCase):
    migrate_from = ("ingestion", "0028_providermatchevent_is_defensive")
    migrate_to = ("ingestion", "0030_finalize_whoscored_data")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps

        Competition = old_apps.get_model("ingestion", "Competition")
        Season = old_apps.get_model("ingestion", "Season")
        CompetitionSeason = old_apps.get_model("ingestion", "CompetitionSeason")
        CanonicalPlayer = old_apps.get_model("ingestion", "CanonicalPlayer")
        CanonicalTeam = old_apps.get_model("ingestion", "CanonicalTeam")
        ProviderMatch = old_apps.get_model("ingestion", "ProviderMatch")
        ProviderMatchEvent = old_apps.get_model("ingestion", "ProviderMatchEvent")
        ProviderMatchPayload = old_apps.get_model("ingestion", "ProviderMatchPayload")

        competition = Competition.objects.create(name="Migration League", short_code="MIG")
        season = Season.objects.create(label="2025-26", sort_order=2026)
        competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
        )
        team = CanonicalTeam.objects.create(name="Migration Team")
        opponent = CanonicalTeam.objects.create(name="Migration Opponent")
        player = CanonicalPlayer.objects.create(display_name="Migration Player")
        match = ProviderMatch.objects.create(
            provider="whoscored",
            provider_match_id="migration-final",
            competition_season=competition_season,
            kickoff_at=datetime(2026, 1, 1, 15, tzinfo=timezone.utc),
            status="completed",
            home_provider_team_id="home",
            away_provider_team_id="away",
            home_team=team,
            away_team=opponent,
            home_score=1,
            away_score=0,
        )
        ProviderMatchEvent.objects.create(
            provider_match=match,
            event_index=1,
            provider_event_id="pass",
            provider_team_id="home",
            provider_player_id="passer",
            team=team,
            period=1,
            minute=10,
            second=0,
            match_seconds=600,
            event_type=1,
            outcome_successful=True,
            x=3000,
            y=5000,
            end_x=4000,
            end_y=5000,
        )
        ProviderMatchEvent.objects.create(
            provider_match=match,
            event_index=2,
            provider_event_id="touch",
            provider_team_id="home",
            provider_player_id="carrier",
            player=player,
            team=team,
            period=1,
            minute=10,
            second=3,
            match_seconds=603,
            event_type=2,
            outcome_successful=True,
            x=4500,
            y=5000,
        )
        own_goal = ProviderMatchEvent.objects.create(
            provider_match=match,
            event_index=3,
            provider_event_id="own-goal",
            provider_team_id="away",
            team=opponent,
            period=1,
            minute=20,
            second=0,
            match_seconds=1200,
            event_type=4,
        )
        payload_bytes = json.dumps(
            {
                "payload": {
                    "events": [
                        {
                            "id": "own-goal",
                            "qualifiers": [
                                {"type": {"displayName": "OwnGoal"}},
                            ],
                        }
                    ]
                }
            }
        ).encode()
        compressed = gzip.compress(payload_bytes)
        checksum = hashlib.sha256(payload_bytes).hexdigest()
        fetched_at = datetime(2026, 1, 1, 17, tzinfo=timezone.utc)
        ProviderMatchPayload.objects.create(
            provider_match=match,
            payload_gzip=compressed,
            payload_sha256=checksum,
            payload_size_bytes=len(compressed),
            uncompressed_size_bytes=len(payload_bytes),
            lifecycle_state="final",
            final_sha256=checksum,
            final_fetched_at=fetched_at,
            fetched_at=fetched_at,
        )
        self.match_id = match.pk
        self.own_goal_id = own_goal.pk

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        self.apps = executor.loader.project_state([self.migrate_to]).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_upgrade_builds_only_final_schema_and_data(self):
        ProviderMatchEvent = self.apps.get_model("ingestion", "ProviderMatchEvent")
        ProviderMatchCarry = self.apps.get_model("ingestion", "ProviderMatchCarry")
        PlayerSeasonRole = self.apps.get_model("ingestion", "PlayerSeasonRole")

        own_goal = ProviderMatchEvent.objects.get(pk=self.own_goal_id)
        carry = ProviderMatchCarry.objects.get(provider_match_id=self.match_id)

        self.assertEqual(own_goal.event_type, 19)
        self.assertEqual(carry.start_event_index, 1)
        self.assertEqual(carry.end_event_index, 2)
        self.assertEqual(carry.provider_player_id, "carrier")
        self.assertFalse(carry.is_low_confidence)
        self.assertIn("team", [field.name for field in PlayerSeasonRole._meta.fields])
        with self.assertRaises(LookupError):
            self.apps.get_model("ingestion", "LegacyPlayerSeasonRole")

    def test_finalization_is_idempotent(self):
        ProviderMatchEvent = self.apps.get_model("ingestion", "ProviderMatchEvent")
        ProviderMatchCarry = self.apps.get_model("ingestion", "ProviderMatchCarry")
        before = list(
            ProviderMatchCarry.objects.filter(provider_match_id=self.match_id).values(
                "id",
                "start_event_index",
                "end_event_index",
                "provider_player_id",
                "x",
                "y",
                "end_x",
                "end_y",
                "is_progressive_carry",
                "is_final_third_entry",
                "is_box_entry",
                "is_low_confidence",
            )
        )

        migration = importlib.import_module(
            "ingestion.migrations.0030_finalize_whoscored_data"
        )
        with connection.schema_editor() as schema_editor:
            migration.finalize_whoscored_data(self.apps, schema_editor)

        after = list(
            ProviderMatchCarry.objects.filter(provider_match_id=self.match_id).values(
                "id",
                "start_event_index",
                "end_event_index",
                "provider_player_id",
                "x",
                "y",
                "end_x",
                "end_y",
                "is_progressive_carry",
                "is_final_third_entry",
                "is_box_entry",
                "is_low_confidence",
            )
        )
        self.assertEqual(after, before)
        self.assertEqual(
            ProviderMatchEvent.objects.get(pk=self.own_goal_id).event_type,
            19,
        )


class WhoScoredReplacementMigrationTests(TransactionTestCase):
    replacement = ("ingestion", "0029_whoscored_final_schema")
    final_data = ("ingestion", "0030_finalize_whoscored_data")

    def test_complete_old_chain_satisfies_replacement_schema(self):
        migration = importlib.import_module(
            "ingestion.migrations.0029_whoscored_final_schema"
        ).Migration
        recorder = MigrationRecorder(connection)
        recorder.record_unapplied(*self.final_data)
        recorder.record_unapplied(*self.replacement)
        for replaced in migration.replaces:
            recorder.record_applied(*replaced)
        try:
            loader = MigrationLoader(connection)
            self.assertIn(self.replacement, loader.applied_migrations)
            plan = loader.graph.forwards_plan(self.final_data)
            unapplied = [node for node in plan if node not in loader.applied_migrations]
            self.assertEqual(unapplied, [self.final_data])
        finally:
            for replaced in migration.replaces:
                recorder.record_unapplied(*replaced)
            recorder.record_applied(*self.replacement)
            recorder.record_applied(*self.final_data)
