from datetime import datetime, timezone

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class GameStateMigrationCompatibilityTests(TransactionTestCase):
    migrate_from = ("ingestion", "0034_match_game_state")
    migrate_to = ("ingestion", "0035_possession_context")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps

        Competition = old_apps.get_model("ingestion", "Competition")
        Season = old_apps.get_model("ingestion", "Season")
        CompetitionSeason = old_apps.get_model("ingestion", "CompetitionSeason")
        CanonicalTeam = old_apps.get_model("ingestion", "CanonicalTeam")
        ProviderMatch = old_apps.get_model("ingestion", "ProviderMatch")
        ProviderMatchEvent = old_apps.get_model("ingestion", "ProviderMatchEvent")
        ProviderMatchGameState = old_apps.get_model(
            "ingestion", "ProviderMatchGameState"
        )

        competition = Competition.objects.create(
            name="Migration League", short_code="MIG"
        )
        season = Season.objects.create(label="2025-26", sort_order=2026)
        competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
        )
        home = CanonicalTeam.objects.create(name="Migration Home")
        away = CanonicalTeam.objects.create(name="Migration Away")
        match = ProviderMatch.objects.create(
            provider="whoscored",
            provider_match_id="migration-0034",
            competition_season=competition_season,
            kickoff_at=datetime(2026, 1, 1, 15, tzinfo=timezone.utc),
            status="completed",
            home_provider_team_id="home",
            away_provider_team_id="away",
            home_team=home,
            away_team=away,
            home_score=1,
            away_score=0,
        )
        event = ProviderMatchEvent.objects.create(
            provider_match=match,
            event_index=1,
            provider_team_id="home",
            team=home,
            period=1,
            minute=10,
            second=0,
            event_type=4,
            home_score_before=0,
            away_score_before=0,
            home_score_after=1,
            away_score_after=0,
            game_state_before=1,
            game_state_after=2,
        )
        audit = ProviderMatchGameState.objects.create(
            provider_match=match,
            status="verified",
            calculation_version="match_game_state_v1",
            event_count=1,
            goal_event_count=1,
            replayed_home_score=1,
            replayed_away_score=0,
            calculated_at=datetime(2026, 1, 1, 17, tzinfo=timezone.utc),
        )
        self.event_id = event.pk
        self.audit_id = audit.pk

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        self.apps = executor.loader.project_state([self.migrate_to]).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_legacy_score_replay_data_survives_foundation_upgrade(self):
        ProviderMatchEvent = self.apps.get_model(
            "ingestion", "ProviderMatchEvent"
        )
        ProviderMatchGameState = self.apps.get_model(
            "ingestion", "ProviderMatchGameState"
        )

        event = ProviderMatchEvent.objects.get(pk=self.event_id)
        audit = ProviderMatchGameState.objects.get(pk=self.audit_id)

        self.assertEqual(event.home_score_after, 1)
        self.assertEqual(event.game_state_after, 2)
        self.assertEqual(event.dismissal_type, "none")
        self.assertIsNone(event.timeline_seconds)
        self.assertEqual(audit.status, "verified")
        self.assertEqual(audit.replayed_home_score, 1)
        self.assertFalse(audit.eligible)
        self.assertEqual(audit.source_checksum, "")
        self.assertEqual(audit.exposure_seconds, 0)
