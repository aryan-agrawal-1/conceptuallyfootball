from __future__ import annotations

from datetime import datetime, timezone

from django.test import TestCase

from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    MatchEventGameState,
    MatchEventPeriod,
    PlayerSeasonDerivedStats,
    Provider,
    ProviderMatch,
    ProviderMatchPlayerInterval,
    ProviderMatchPlayerParticipation,
    ProviderMatchPlayerParticipationBuild,
    ProviderMatchPlayerStateExposure,
    ProviderMatchStatus,
    ProviderMatchTeamGameStateEpisode,
    Season,
)


class PlayerStateExposureApiTests(TestCase):
    def setUp(self):
        competition = Competition.objects.create(
            name="Test League", short_code="TST", country="Test"
        )
        season = Season.objects.create(label="2025-26", sort_order=2026)
        self.competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
            is_published=True,
            has_whoscored=True,
            whoscored_league="test-league",
            whoscored_season="2526",
            whoscored_expected_match_count=1,
        )
        self.home = CanonicalTeam.objects.create(name="Home")
        self.away = CanonicalTeam.objects.create(name="Away")
        self.player = CanonicalPlayer.objects.create(display_name="State Player")
        self.derived = PlayerSeasonDerivedStats.objects.create(
            competition_season=self.competition_season,
            canonical_player=self.player,
            canonical_display_team=self.home,
            minutes=777,
        )
        self.match = self.create_match(
            "included", datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        build = self.create_build(self.match, "verified")
        participant = ProviderMatchPlayerParticipation.objects.create(
            build=build,
            provider_match=self.match,
            provider_team_id="home",
            team=self.home,
            provider_player_id="player",
            player=self.player,
            roster_role="starter",
            position_role="outfield",
            status="verified",
            confidence="verified",
            on_pitch_seconds=600,
            interval_count=1,
        )
        interval = ProviderMatchPlayerInterval.objects.create(
            participation=participant,
            sequence=0,
            start_second=0,
            end_second=600,
            duration_seconds=600,
            start_evidence="lineup_starter",
            end_evidence="substitution_off",
            confidence="verified",
        )
        episode = ProviderMatchTeamGameStateEpisode.objects.create(
            provider_match=self.match,
            focal_team=self.home,
            focal_is_home=True,
            episode_index=0,
            period=MatchEventPeriod.FIRST_HALF,
            phase="first_half",
            start_second=0,
            end_second=600,
            duration_seconds=600,
            focal_score=0,
            opponent_score=0,
            goal_difference=0,
            state=MatchEventGameState.DRAWING,
            draw_provenance="neutral",
            state_entry_second=0,
            state_age_seconds_at_start=0,
            calculation_version="episodes-test-v1",
        )
        ProviderMatchPlayerStateExposure.objects.create(
            player_interval=interval,
            team_episode=episode,
            start_second=0,
            end_second=600,
            duration_seconds=600,
            coarse_state=MatchEventGameState.DRAWING,
            goal_difference=0,
            phase="first_half",
            provenance="neutral",
            state_age_bucket="0_5_minutes",
            state_age_start_seconds=0,
            state_age_end_seconds=600,
            formula_version="player_state_exposure_v1",
        )

        excluded_match = self.create_match(
            "excluded", datetime(2026, 1, 8, tzinfo=timezone.utc)
        )
        excluded_build = self.create_build(excluded_match, "partial")
        ProviderMatchPlayerParticipation.objects.create(
            build=excluded_build,
            provider_match=excluded_match,
            provider_team_id="home",
            team=self.home,
            provider_player_id="player",
            player=self.player,
            roster_role="starter",
            position_role="outfield",
            status="excluded",
            confidence="unverified",
            exclusion_reason="dismissal_player_missing",
        )

    def create_match(self, suffix, kickoff):
        return ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id=f"state-{suffix}",
            competition_season=self.competition_season,
            kickoff_at=kickoff,
            status=ProviderMatchStatus.COMPLETED,
            home_provider_team_id="home",
            away_provider_team_id="away",
            home_team=self.home,
            away_team=self.away,
            home_score=1,
            away_score=0,
        )

    def create_build(self, match, build_status):
        return ProviderMatchPlayerParticipationBuild.objects.create(
            provider_match=match,
            status=build_status,
            formula_version="player_participation_v1",
            source_payload_sha256="a" * 64,
            match_clock_version="clock-test-v1",
            team_episode_version="episodes-test-v1",
            participant_count=1,
            verified_participant_count=build_status == "verified",
            excluded_participant_count=build_status != "verified",
            interval_count=build_status == "verified",
            verified_seconds=600 if build_status == "verified" else 0,
            calculated_at=datetime.now(tz=timezone.utc),
        )

    def test_endpoint_exposes_verified_seconds_and_safe_coverage_metadata(self):
        response = self.client.get(
            f"/api/v1/player-seasons/state-exposure/{self.player.id}",
            {"competition": "TST", "season": "2025-26"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.data
        self.assertEqual(payload["coverage"]["included_match_count"], 1)
        self.assertEqual(payload["coverage"]["excluded_match_count"], 1)
        self.assertEqual(payload["coverage"]["exposure_seconds"], 600)
        self.assertEqual(payload["coverage"]["excluded_candidate_seconds"], 0)
        self.assertEqual(payload["coverage"]["confidence"], "partial")
        self.assertEqual(
            payload["coverage"]["exclusion_reasons"],
            {"dismissal_player_missing": 1},
        )
        self.assertEqual(payload["dimensions"][0]["exposure_seconds"], 600)
        self.assertNotIn("provider_match_id", str(payload))
        self.assertNotIn("provider_player_id", str(payload))
        self.assertNotIn("diagnostics", str(payload))

    def test_state_exposure_does_not_redefine_existing_season_minutes(self):
        response = self.client.get(
            f"/api/v1/player-seasons/state-exposure/{self.player.id}",
            {"competition_season": self.competition_season.id},
        )

        self.assertEqual(response.status_code, 200)
        self.derived.refresh_from_db()
        self.assertEqual(self.derived.minutes, 777)

    def test_unpublished_or_unmaterialized_player_returns_public_404(self):
        stranger = CanonicalPlayer.objects.create(display_name="No Exposure")
        response = self.client.get(
            f"/api/v1/player-seasons/state-exposure/{stranger.id}",
            {"competition_season": self.competition_season.id},
        )

        self.assertEqual(response.status_code, 404)
