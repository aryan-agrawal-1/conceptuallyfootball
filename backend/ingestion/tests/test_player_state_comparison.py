from datetime import datetime, timezone
import json

from django.test import TestCase
from rest_framework.test import APIRequestFactory, APIClient

from ingestion.event_profile_api import PlayerEventProfileApi
from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    MatchEventGameState,
    MatchEventPeriod,
    MatchEventType,
    MatchStateDrawProvenance,
    MatchStatePhase,
    PlayerSeasonDerivedStats,
    Provider,
    ProviderMatch,
    ProviderMatchCarry,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchPlayerInterval,
    ProviderMatchPlayerParticipation,
    ProviderMatchPlayerParticipationBuild,
    ProviderMatchPlayerStateExposure,
    ProviderMatchPossession,
    ProviderMatchPossessionBuild,
    ProviderMatchPossessionEvent,
    ProviderMatchPossessionParticipant,
    ProviderMatchStatus,
    ProviderMatchTeamGameStateEpisode,
    Season,
)
from ingestion.player_state_comparison_api import PlayerStateComparisonApi
from ingestion.services.event_profiles import materialize_event_profiles


class PlayerStateComparisonTests(TestCase):
    def setUp(self):
        competition = Competition.objects.create(name="Test League", short_code="TST")
        season = Season.objects.create(label="2025-26", sort_order=2026)
        self.competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
            is_published=True,
            has_whoscored=True,
            whoscored_league="test-league",
            whoscored_season="2526",
            whoscored_expected_match_count=1,
            expected_team_count=2,
            refresh_enabled=True,
        )
        self.home = CanonicalTeam.objects.create(name="Home")
        self.away = CanonicalTeam.objects.create(name="Away")
        self.player = CanonicalPlayer.objects.create(display_name="State Player")
        self.teammate = CanonicalPlayer.objects.create(display_name="Team Mate")
        PlayerSeasonDerivedStats.objects.create(
            competition_season=self.competition_season,
            canonical_player=self.player,
            canonical_display_team=self.home,
            minutes=60,
        )
        self.match = ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id="state-comparison-match",
            competition_season=self.competition_season,
            kickoff_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            status=ProviderMatchStatus.COMPLETED,
            home_provider_team_id="home",
            away_provider_team_id="away",
            home_team=self.home,
            away_team=self.away,
            home_score=1,
            away_score=0,
        )
        self.add_event(1, 600, self.player, x=2_000, y=2_000, end_x=4_000)
        self.add_event(2, 700, self.teammate, x=3_000, y=3_000, end_x=5_000)
        self.add_event(3, 2_000, self.player, x=7_000, y=7_000, end_x=9_000)
        self.add_event(4, 2_100, self.teammate, x=8_000, y=8_000, end_x=9_000)
        self.add_carry(10, 1_000, self.player, x=4_000, y=2_000, end_x=5_000, end_y=2_000)
        self.add_carry(11, 1_100, self.teammate, x=5_000, y=3_000, end_x=6_000, end_y=3_000)
        self.add_carry(12, 2_500, self.player, x=6_000, y=7_000, end_x=7_000, end_y=7_000)
        self.add_carry(13, 2_600, self.teammate, x=7_000, y=8_000, end_x=8_000, end_y=8_000)
        self.create_state_rows()
        self.create_possessions()
        run = IngestionRun.objects.create(
            kind=IngestionKind.EVENT_PROFILES,
            competition_season=self.competition_season,
        )
        self.assertIsNotNone(materialize_event_profiles(self.competition_season, run=run))

    def add_event(self, index, seconds, player, *, x, y, end_x):
        return ProviderMatchEvent.objects.create(
            provider_match=self.match,
            event_index=index,
            provider_event_sequence_id=str(index),
            provider_team_id="home",
            team=self.home,
            provider_player_id=str(player.id),
            player=player,
            period=MatchEventPeriod.FIRST_HALF,
            minute=seconds // 60,
            second=seconds % 60,
            match_seconds=seconds,
            timeline_seconds=seconds,
            event_type=MatchEventType.PASS,
            outcome_successful=True,
            x=x,
            y=y,
            end_x=end_x,
            end_y=y,
            is_touch=True,
            is_progressive_pass=end_x > x,
        )

    def add_carry(self, index, seconds, player, *, x, y, end_x, end_y):
        return ProviderMatchCarry.objects.create(
            provider_match=self.match,
            start_event_index=index,
            end_event_index=index + 1,
            provider_team_id="home",
            team=self.home,
            provider_player_id=str(player.id),
            player=player,
            period=MatchEventPeriod.FIRST_HALF,
            minute=seconds // 60,
            second=seconds % 60,
            match_seconds=seconds,
            x=x,
            y=y,
            end_x=end_x,
            end_y=end_y,
            is_progressive_carry=True,
        )

    def create_state_rows(self):
        ProviderMatchGameState.objects.create(
            provider_match=self.match,
            status="verified",
            eligible=True,
            calculation_version="team_game_state_v1",
            exposure_seconds=3_600,
            episode_count=2,
            focal_team_count=1,
            calculated_at=datetime.now(tz=timezone.utc),
        )
        build = ProviderMatchPlayerParticipationBuild.objects.create(
            provider_match=self.match,
            status="verified",
            formula_version="player_participation_v1",
            source_payload_sha256="a" * 64,
            match_clock_version="clock-test-v1",
            team_episode_version="team_game_state_v1",
            participant_count=1,
            verified_participant_count=1,
            interval_count=1,
            verified_seconds=3_600,
            calculated_at=datetime.now(tz=timezone.utc),
        )
        participation = ProviderMatchPlayerParticipation.objects.create(
            build=build,
            provider_match=self.match,
            provider_team_id="home",
            team=self.home,
            provider_player_id=str(self.player.id),
            player=self.player,
            roster_role="starter",
            position_role="outfield",
            status="verified",
            confidence="verified",
            on_pitch_seconds=3_600,
            interval_count=1,
        )
        interval = ProviderMatchPlayerInterval.objects.create(
            participation=participation,
            sequence=0,
            start_second=0,
            end_second=3_600,
            duration_seconds=3_600,
            start_evidence="lineup_starter",
            end_evidence="match_end",
            confidence="verified",
        )
        for index, (start, end, state, difference, provenance) in enumerate(
            (
                (0, 1_800, MatchEventGameState.DRAWING, 0, MatchStateDrawProvenance.NEUTRAL),
                (1_800, 3_600, MatchEventGameState.WINNING, 1, MatchStateDrawProvenance.NONE),
            )
        ):
            episode = ProviderMatchTeamGameStateEpisode.objects.create(
                provider_match=self.match,
                focal_team=self.home,
                focal_is_home=True,
                episode_index=index,
                period=MatchEventPeriod.FIRST_HALF,
                phase=MatchStatePhase.FIRST_HALF,
                start_second=start,
                end_second=end,
                duration_seconds=end - start,
                focal_score=difference,
                opponent_score=0,
                goal_difference=difference,
                state=state,
                draw_provenance=provenance,
                state_entry_second=start,
                state_age_seconds_at_start=0,
                calculation_version="team_game_state_v1",
            )
            ProviderMatchPlayerStateExposure.objects.create(
                player_interval=interval,
                team_episode=episode,
                start_second=start,
                end_second=end,
                duration_seconds=end - start,
                coarse_state=state,
                goal_difference=difference,
                phase=MatchStatePhase.FIRST_HALF,
                provenance=provenance,
                state_age_bucket="0_5_minutes",
                state_age_start_seconds=0,
                state_age_end_seconds=end - start,
                formula_version="player_state_exposure_v1",
            )

    def create_possessions(self):
        outside_interval = ProviderMatchEvent.objects.create(
            provider_match=self.match,
            event_index=5,
            provider_event_sequence_id="5",
            provider_team_id="home",
            team=self.home,
            provider_player_id=str(self.player.id),
            player=self.player,
            period=MatchEventPeriod.FIRST_HALF,
            minute=13,
            second=20,
            match_seconds=800,
            timeline_seconds=None,
            event_type=MatchEventType.PASS,
            outcome_successful=True,
            x=4_000,
            y=4_000,
            end_x=5_000,
            end_y=4_000,
            is_touch=True,
        )
        build = ProviderMatchPossessionBuild.objects.create(
            provider_match=self.match,
            calculation_version="possession_context_v1",
            possession_count=3,
            included_event_count=5,
            calculated_at=datetime.now(tz=timezone.utc),
        )
        drawing = ProviderMatchPossession.objects.create(
            build=build,
            provider_match=self.match,
            possession_index=0,
            identity="state-comparison-drawing-possession",
            provider_team_id="home",
            team=self.home,
            period=MatchEventPeriod.FIRST_HALF,
            start_second=600,
            end_second=701,
            duration_seconds=101,
            start_x=2_000,
            start_y=2_000,
            end_x=5_000,
            end_y=3_000,
            action_count=2,
            termination_reason="period_end",
            launch_type="turnover_recovery",
            is_counter_launch=True,
            counter_final_third_arrival=True,
            counter_box_arrival=True,
            counter_shot=True,
            counter_outcome="saved",
            counter_elapsed_seconds=100,
            diagnostics={"qualifies_counter_progress": True},
        )
        winning = ProviderMatchPossession.objects.create(
            build=build,
            provider_match=self.match,
            possession_index=1,
            identity="state-comparison-winning-possession",
            provider_team_id="home",
            team=self.home,
            period=MatchEventPeriod.FIRST_HALF,
            start_second=2_000,
            end_second=2_101,
            duration_seconds=101,
            start_x=7_000,
            start_y=7_000,
            end_x=9_000,
            end_y=8_000,
            action_count=2,
            termination_reason="period_end",
            launch_type="continued_control",
        )
        out_of_interval = ProviderMatchPossession.objects.create(
            build=build,
            provider_match=self.match,
            possession_index=2,
            identity="state-comparison-outside-interval-possession",
            provider_team_id="home",
            team=self.home,
            period=MatchEventPeriod.FIRST_HALF,
            start_second=800,
            end_second=801,
            duration_seconds=1,
            start_x=4_000,
            start_y=4_000,
            end_x=5_000,
            end_y=4_000,
            action_count=1,
            termination_reason="period_end",
            launch_type="continued_control",
        )
        events = list(
            ProviderMatchEvent.objects.filter(provider_match=self.match)
            .exclude(event_index=outside_interval.event_index)
            .order_by("event_index")
        )
        for possession, linked_events in (
            (drawing, events[:2]),
            (winning, events[2:]),
        ):
            for sequence, event in enumerate(linked_events):
                ProviderMatchPossessionEvent.objects.create(
                    possession=possession,
                    event=event,
                    sequence=sequence,
                    is_control_action=True,
                )
                ProviderMatchPossessionParticipant.objects.create(
                    possession=possession,
                    provider_player_id=str(event.player_id),
                    player=event.player,
                    first_event_index=event.event_index,
                    action_count=1,
                )
        ProviderMatchPossessionEvent.objects.create(
            possession=out_of_interval,
            event=outside_interval,
            sequence=0,
            is_control_action=True,
        )
        ProviderMatchPossessionParticipant.objects.create(
            possession=out_of_interval,
            provider_player_id=str(outside_interval.player_id),
            player=outside_interval.player,
            first_event_index=outside_interval.event_index,
            action_count=1,
        )

    @property
    def scope(self):
        return {"competition": "TST", "season": "2025-26"}

    def test_player_event_profile_scopes_events_and_carries_to_verified_state(self):
        response = APIClient().get(
            f"/api/v1/player-seasons/event-profile/{self.player.id}",
            {**self.scope, "state": "winning"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["pass_attempts"], 1)
        self.assertEqual(payload["shots"], [])
        self.assertEqual(payload["state_lens"]["evidence"]["exposure_seconds"], 1_800)
        self.assertEqual(payload["state_lens"]["evidence"]["matches_included"], 1)

        passes = APIClient().get(
            f"/api/v1/player-seasons/event-profile/{self.player.id}/passes",
            {**self.scope, "state": "drawing", "filter": "all"},
        )
        self.assertEqual(passes.status_code, 200)
        self.assertEqual(passes.json()["total_matching_count"], 1)

    def test_comparison_exposes_raw_rates_and_matched_team_share(self):
        request = APIRequestFactory().get(
            "/api/v1/player-state-comparison",
            {
                **self.scope,
                "state": "winning",
                "baseline_state": "drawing",
                "baseline_draw_provenance": "neutral",
            },
        )
        response = PlayerStateComparisonApi.as_view()(request, self.player.id)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["comparison"]["enabled"])
        self.assertEqual(payload["selected"]["summary"]["pass_attempts"], 1)
        self.assertEqual(payload["baseline"]["summary"]["pass_attempts"], 1)
        self.assertEqual(payload["selected"]["team_action_shares"]["passes"]["share"], 0.5)
        self.assertEqual(payload["baseline"]["team_action_shares"]["passes"]["share"], 0.5)
        self.assertEqual(payload["selected"]["team_action_shares"]["progressive_actions"]["player_count"], 2)
        self.assertEqual(payload["selected"]["team_action_shares"]["progressive_actions"]["team_count"], 4)
        self.assertEqual(payload["selected"]["team_action_shares"]["progressive_actions"]["share"], 0.5)
        self.assertEqual(payload["selected"]["passing"]["attempts"], 1)
        self.assertEqual(payload["selected"]["carrying"]["attempts"], 1)
        self.assertEqual(payload["selected"]["touch_location"]["sample_size"], 1)
        self.assertEqual(payload["selected"]["defensive_location"]["sample_size"], 0)
        self.assertEqual(payload["team_context"]["matching"], "same team, matches, state cohort, and verified player on-pitch intervals")
        self.assertEqual(payload["response_roles"], [])

    def test_comparison_projects_transition_leverage_onto_verified_player_actions(self):
        request = APIRequestFactory().get(
            "/api/v1/player-state-comparison",
            {
                **self.scope,
                "state": "winning",
                "baseline_state": "drawing",
                "baseline_draw_provenance": "neutral",
            },
        )
        response = PlayerStateComparisonApi.as_view()(request, self.player.id)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)

        selected = payload["selected"]["possession"]
        baseline = payload["baseline"]["possession"]
        self.assertEqual(selected["involved_possessions"], 1)
        self.assertEqual(baseline["involved_possessions"], 1)
        self.assertEqual(selected["counter_possessions"], 0)
        self.assertEqual(baseline["counter_possessions"], 1)
        self.assertEqual(baseline["shot_producing_possessions"], 1)
        self.assertEqual(baseline["box_entry_possessions"], 1)
        self.assertEqual(baseline["final_third_possessions"], 1)

        transition = baseline["transition_leverage"]
        self.assertEqual(transition["contract_version"], "transition_leverage_api_v2")
        self.assertEqual(transition["opportunities"], 1)
        self.assertEqual(transition["sequence_stages"]["origin_recovery"]["actions"], 1)
        self.assertEqual(transition["sequence_stages"]["origin_recovery"]["possessions"], 1)
        self.assertEqual(len(transition["sequence_evidence"]), 1)
        evidence = transition["sequence_evidence"][0]
        self.assertEqual(evidence["state"]["state"], "drawing")
        self.assertEqual(evidence["action_event_indexes"], [1])
        self.assertEqual(evidence["verified_player_action_sequences"], [0])
        self.assertEqual(evidence["possession_trace"][0]["player_id"], self.player.id)
        self.assertEqual(transition["matching"]["same_team"], True)
        self.assertEqual(transition["matching"]["verified_player_on_pitch_intervals"], True)
        self.assertEqual(transition["exclusions"]["outside_verified_player_interval"], 2)
