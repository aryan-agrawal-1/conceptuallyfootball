import gzip
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import PropertyMock, patch

from django.core.management import call_command
from django.test import TestCase

from ingestion.models import (
    Competition,
    CompetitionSeason,
    Provider,
    ProviderMatch,
    ProviderMatchPayload,
    ProviderPayloadLifecycle,
    ProviderPayloadStorage,
    Season,
)
from ingestion.services.whoscored_normalization import canonical_raw_payload_bytes


class BackfillGameStateFoundationsCommandTests(TestCase):
    def setUp(self):
        competition = Competition.objects.create(
            name="Premier League", short_code="ENG1"
        )
        season = Season.objects.create(label="2025-26", sort_order=2026)
        competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
            is_active=True,
        )
        self.match = ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id="state-backfill-1",
            competition_season=competition_season,
            kickoff_at=datetime(2026, 1, 1, 15, tzinfo=timezone.utc),
            home_provider_team_id="home",
            away_provider_team_id="away",
        )
        wrapped = canonical_raw_payload_bytes(
            {
                "home": {"teamId": "home", "name": "Home"},
                "away": {"teamId": "away", "name": "Away"},
                "events": [],
            }
        )
        ProviderMatchPayload.objects.create(
            provider_match=self.match,
            storage_backend=ProviderPayloadStorage.DATABASE,
            payload_gzip=gzip.compress(wrapped),
            payload_sha256="a" * 64,
            payload_size_bytes=len(wrapped),
            uncompressed_size_bytes=len(wrapped),
            lifecycle_state=ProviderPayloadLifecycle.FINAL,
            final_sha256="a" * 64,
            final_fetched_at="2026-01-01T00:00:00Z",
            fetched_at="2026-01-01T00:00:00Z",
        )

    @patch(
        "ingestion.management.commands.backfill_game_state_foundations.replace_match_events"
    )
    @patch(
        "ingestion.management.commands.backfill_game_state_foundations.parse_match_payload"
    )
    def test_rebuilds_all_state_dependent_foundations(
        self, parse_payload, replace_events
    ):
        parse_payload.return_value.clock = {"valid": True, "periods": []}
        audit = type("Audit", (), {"eligible": True, "episode_count": 4})()
        possession_manager = type("Manager", (), {"count": lambda self: 3})()
        with patch.object(ProviderMatch, "refresh_from_db"), patch.object(
            ProviderMatch, "game_state", new_callable=PropertyMock, return_value=audit
        ), patch(
            "ingestion.management.commands.backfill_game_state_foundations.ProviderMatchPlayerStateExposure.objects.filter"
        ) as player_filter, patch.object(
            ProviderMatch,
            "possessions",
            new_callable=PropertyMock,
            return_value=possession_manager,
        ):
            player_filter.return_value.count.return_value = 2
            output = StringIO()

            call_command(
                "backfill_game_state_foundations",
                competition="ENG1",
                season="2025-26",
                stdout=output,
            )
        replace_events.assert_called_once()
        self.assertEqual(replace_events.call_args.args[0], self.match)
        self.assertIn(
            "1 eligible, 4 episodes, 2 player exposures, 3 possessions",
            output.getvalue(),
        )
