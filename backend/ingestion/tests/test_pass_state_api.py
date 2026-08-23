from datetime import datetime, timezone

from django.test import TestCase
from rest_framework.test import APIClient

from ingestion.models import (
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    MatchEventPeriod,
    MatchEventShotOutcome,
    MatchEventType,
    MergedTeamSeason,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchPayload,
    ProviderMatchStatus,
    ProviderPayloadLifecycle,
    Season,
)
from ingestion.services.event_profiles import materialize_event_profiles
from ingestion.services.game_state import materialize_match_game_state


CLOCK = {
    "periods": [
        {"period": 1, "start_second": 0, "end_second": 47 * 60},
        {"period": 2, "start_second": 47 * 60, "end_second": 95 * 60},
    ],
    "supported_end_second": 95 * 60,
}


class TeamPassStateApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        competition = Competition.objects.create(name="Test League", short_code="TST")
        season = Season.objects.create(label="2025-26", sort_order=2026)
        cls.competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
            has_whoscored=True,
            whoscored_league="test",
            whoscored_season="2025-26",
            whoscored_expected_match_count=2,
            expected_team_count=2,
            refresh_enabled=True,
            is_published=True,
        )
        cls.home = CanonicalTeam.objects.create(name="Home")
        cls.away = CanonicalTeam.objects.create(name="Away")
        MergedTeamSeason.objects.create(
            competition_season=cls.competition_season,
            canonical_team=cls.home,
            matches=2,
        )
        cls.match = cls.create_match("eligible", home_score=1, away_score=0)
        ProviderMatchPayload.objects.create(
            provider_match=cls.match,
            payload_gzip=b"payload",
            payload_sha256="a" * 64,
            payload_size_bytes=7,
            uncompressed_size_bytes=7,
            schema_version=1,
            lifecycle_state=ProviderPayloadLifecycle.FINAL,
            final_sha256="a" * 64,
            final_fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        cls.create_event(1, 300, completed=True, x=1000, end_x=2000)
        cls.create_event(
            2,
            600,
            event_type=MatchEventType.SHOT,
            shot_outcome=MatchEventShotOutcome.GOAL,
            completed=None,
            x=9000,
            end_x=None,
            end_y=None,
        )
        cls.create_event(3, 601, completed=False, x=2000, end_x=5000)
        cls.create_event(4, 900, completed=True, x=4000, end_x=3000)
        materialize_match_game_state(cls.match, clock=CLOCK)

        # This match has normalized pass data but no verified state audit. It
        # must be disclosed and excluded from both numerator and exposure.
        excluded = cls.create_match("excluded", home_score=0, away_score=0)
        cls.create_event(5, 300, provider_match=excluded, completed=True, x=0, end_x=10_000)

        run = IngestionRun.objects.create(
            kind=IngestionKind.EVENT_PROFILES,
            competition_season=cls.competition_season,
        )
        materialize_event_profiles(cls.competition_season, run=run)

    @classmethod
    def create_match(cls, provider_id, *, home_score, away_score):
        return ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id=provider_id,
            competition_season=cls.competition_season,
            kickoff_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            status=ProviderMatchStatus.COMPLETED,
            home_provider_team_id="home",
            away_provider_team_id="away",
            home_team=cls.home,
            away_team=cls.away,
            home_score=home_score,
            away_score=away_score,
        )

    @classmethod
    def create_event(
        cls,
        index,
        timeline_seconds,
        *,
        provider_match=None,
        event_type=MatchEventType.PASS,
        completed=True,
        shot_outcome=MatchEventShotOutcome.UNKNOWN,
        x=1000,
        end_x=2000,
        end_y=1000,
    ):
        return ProviderMatchEvent.objects.create(
            provider_match=provider_match or cls.match,
            event_index=index,
            provider_event_sequence_id=str(index),
            provider_team_id="home",
            team=cls.home,
            period=(
                MatchEventPeriod.FIRST_HALF
                if timeline_seconds < 47 * 60
                else MatchEventPeriod.SECOND_HALF
            ),
            minute=timeline_seconds // 60,
            second=timeline_seconds % 60,
            match_seconds=timeline_seconds,
            timeline_seconds=timeline_seconds,
            event_type=event_type,
            outcome_successful=completed,
            x=x,
            y=1000,
            end_x=end_x,
            end_y=end_y,
            shot_outcome=shot_outcome,
            is_progressive_pass=event_type == MatchEventType.PASS and end_x is not None and end_x > x,
        )

    @property
    def url(self):
        return f"/api/v1/team-seasons/event-profile/{self.home.id}/pass-state"

    def request(self, **scope):
        return APIClient().get(
            self.url,
            {"competition": "TST", "season": "2025-26", **scope},
        )

    def test_public_contract_uses_eligible_state_exposure_and_discloses_exclusion(self):
        response = self.request()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["selected"]["summary"]["attempts"], 3)
        self.assertEqual(payload["selected"]["exposure_seconds"], 95 * 60)
        self.assertEqual(payload["selected"]["evidence"]["source_pass_events"], 3)
        self.assertEqual(payload["state_lens"]["evidence"]["matches_included"], 1)
        self.assertEqual(payload["state_lens"]["evidence"]["matches_excluded"], 1)
        self.assertTrue(payload["state_lens"]["evidence"]["exclusion_reasons"])

    def test_state_age_is_half_open_and_rates_use_clipped_exposure(self):
        fresh = self.request(
            state="winning",
            minimum_state_age_seconds=0,
            maximum_state_age_seconds=300,
        ).json()
        aged = self.request(state="winning", minimum_state_age_seconds=300).json()

        self.assertEqual(fresh["selected"]["exposure_seconds"], 300)
        self.assertEqual(fresh["selected"]["summary"]["attempts"], 1)
        self.assertEqual(fresh["selected"]["summary"]["attempts_per_state_minute"], 0.2)
        self.assertEqual(aged["selected"]["exposure_seconds"], 4_800)
        self.assertEqual(aged["selected"]["summary"]["attempts"], 1)
        self.assertEqual(aged["selected"]["summary"]["attempts_per_state_minute"], 0.0125)

    def test_match_scope_uses_only_selected_match_exposure(self):
        excluded_match = self.request(match=1).json()

        self.assertEqual(excluded_match["selected"]["summary"]["attempts"], 0)
        self.assertEqual(excluded_match["selected"]["exposure_seconds"], 0)
        self.assertIsNone(
            excluded_match["selected"]["summary"]["attempts_per_state_minute"]
        )
        self.assertEqual(
            excluded_match["state_lens"]["evidence"]["matches_excluded"], 1
        )

    def test_missing_coordinates_count_for_volume_and_execution_not_spatial_flow(self):
        self.create_event(
            6,
            1_000,
            completed=False,
            x=None,
            end_x=None,
            end_y=None,
        )

        payload = self.request(state="winning").json()["selected"]

        self.assertEqual(payload["summary"]["attempts"], 3)
        self.assertEqual(payload["summary"]["completions"], 1)
        self.assertEqual(payload["summary"]["completion_rate"], 0.3333)
        self.assertEqual(payload["evidence"]["located_pass_events"], 2)
        self.assertEqual(payload["evidence"]["excluded_missing_coordinates"], 1)
        self.assertEqual(sum(row["attempts"] for row in payload["flow"]), 2)

    def test_comparison_returns_full_baseline_and_null_safe_delta(self):
        response = self.request(state="winning", baseline_state="drawing")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["state_lens"]["comparison"]["enabled"])
        self.assertEqual(payload["selected"]["summary"]["attempts"], 2)
        self.assertEqual(payload["comparison"]["baseline"]["summary"]["attempts"], 1)
        self.assertAlmostEqual(
            payload["comparison"]["delta"]["attempts_per_state_minute"],
            -0.0765,
            places=4,
        )

    def test_invalid_shared_scope_returns_public_400(self):
        response = self.request(state="winning", goal_difference=-1)

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid State Lens parameter", response.json()["detail"])
