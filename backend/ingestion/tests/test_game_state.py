from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from ingestion.models import (
    MatchEventGameState,
    MatchEventPeriod,
    MatchEventShotOutcome,
    MatchEventType,
    MatchGameStateExclusionReason,
    MatchGameStateStatus,
    MatchStateDrawProvenance,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchPayload,
    ProviderMatchTeamGameStateEpisode,
    ProviderMatchStatus,
    ProviderPayloadLifecycle,
    Season,
)
from ingestion.services.game_state import (
    materialize_match_game_state,
    public_game_state_metadata,
    replay_match_game_state,
    scope_events_to_focal_state,
    state_context_for_event,
)


CLOCK = {
    "periods": [
        {"period": 1, "start_second": 0, "end_second": 47 * 60},
        {"period": 2, "start_second": 47 * 60, "end_second": 95 * 60},
    ],
    "supported_end_second": 95 * 60,
}


def match(home_score, away_score, **overrides):
    values = dict(
        pk=None,
        status=ProviderMatchStatus.COMPLETED,
        home_provider_team_id="home",
        away_provider_team_id="away",
        home_team_id=10,
        away_team_id=20,
        home_score=home_score,
        away_score=away_score,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def event(
    index,
    second,
    team="home",
    *,
    own=False,
    period=1,
    disallowed=False,
    deleted=False,
    related=None,
    goal=True,
):
    return SimpleNamespace(
        event_index=index,
        provider_event_sequence_id=str(index),
        related_provider_event_sequence_id=str(related) if related else None,
        provider_event_id=f"id-{index}",
        related_provider_event_id=None,
        provider_team_id=team,
        period=period,
        timeline_seconds=second,
        event_type=(MatchEventType.OWN_GOAL if own else MatchEventType.SHOT),
        shot_outcome=(
            MatchEventShotOutcome.GOAL if goal else MatchEventShotOutcome.OFF_TARGET
        ),
        is_goal_disallowed=disallowed,
        is_deleted_event=deleted,
    )


class GameStateReplayTests(SimpleTestCase):
    def test_two_focal_timelines_are_gap_free_inverse_and_half_open(self):
        replay = replay_match_game_state(
            match(1, 1),
            [event(1, 600), event(2, 1200, team="away")],
            clock=CLOCK,
        )
        self.assertTrue(replay.eligible)
        self.assertEqual(replay.status, MatchGameStateStatus.VERIFIED)
        for team_id in (10, 20):
            episodes = [
                episode
                for episode in replay.episodes
                if episode.focal_team_id == team_id
            ]
            self.assertEqual(episodes[0].start_second, 0)
            self.assertEqual(episodes[-1].end_second, 95 * 60)
            self.assertTrue(
                all(
                    left.end_second == right.start_second
                    for left, right in zip(episodes, episodes[1:])
                )
            )
            self.assertEqual(
                sum(episode.duration_seconds for episode in episodes), 95 * 60
            )
        home_at_goal = next(
            e
            for e in replay.episodes
            if e.focal_team_id == 10 and e.start_second == 600
        )
        away_at_goal = next(
            e
            for e in replay.episodes
            if e.focal_team_id == 20 and e.start_second == 600
        )
        self.assertEqual(home_at_goal.state, MatchEventGameState.WINNING)
        self.assertEqual(away_at_goal.state, MatchEventGameState.LOSING)
        self.assertEqual(home_at_goal.goal_difference, -away_at_goal.goal_difference)

    def test_equaliser_draw_provenance_is_focal(self):
        replay = replay_match_game_state(
            match(1, 1), [event(1, 600), event(2, 1200, team="away")], clock=CLOCK
        )
        home_draw = next(
            e
            for e in replay.episodes
            if e.focal_team_id == 10 and e.start_second == 1200
        )
        away_draw = next(
            e
            for e in replay.episodes
            if e.focal_team_id == 20 and e.start_second == 1200
        )
        self.assertEqual(
            home_draw.draw_provenance, MatchStateDrawProvenance.SURRENDERED
        )
        self.assertEqual(away_draw.draw_provenance, MatchStateDrawProvenance.RESTORED)
        self.assertEqual(home_draw.previous_state, MatchEventGameState.WINNING)
        self.assertEqual(away_draw.previous_state, MatchEventGameState.LOSING)

    def test_state_age_carries_across_period_and_same_coarse_state_goal(self):
        replay = replay_match_game_state(
            match(2, 0), [event(1, 600), event(2, 900)], clock=CLOCK
        )
        second_half = next(
            e
            for e in replay.episodes
            if e.focal_team_id == 10 and e.start_second == 47 * 60
        )
        self.assertEqual(second_half.state_entry_second, 600)
        self.assertEqual(second_half.entry_event_index, 1)
        self.assertEqual(second_half.state_age_seconds_at_start, 47 * 60 - 600)

    def test_own_deleted_and_disallowed_goals(self):
        events = [
            event(1, 600, own=True),
            event(2, 700, disallowed=True),
            event(3, 800),
            event(4, 900, deleted=True, related=3, goal=False),
        ]
        replay = replay_match_game_state(match(0, 1), events, clock=CLOCK)
        self.assertEqual(
            (replay.replayed_home_score, replay.replayed_away_score), (0, 1)
        )
        self.assertEqual(replay.ignored_goal_event_count, 2)
        self.assertEqual(replay.goal_event_count, 3)

    def test_deleted_event_sequence_ids_are_scoped_to_the_team(self):
        replay = replay_match_game_state(
            match(1, 0),
            [
                event(1, 600),
                event(
                    2,
                    700,
                    team="away",
                    deleted=True,
                    related=1,
                    goal=False,
                ),
            ],
            clock=CLOCK,
        )

        self.assertTrue(replay.eligible)
        self.assertEqual(
            (replay.replayed_home_score, replay.replayed_away_score),
            (1, 0),
        )

    def test_shootout_is_audited_but_never_exposed(self):
        replay = replay_match_game_state(
            match(1, 0),
            [
                event(1, 600),
                event(2, 96 * 60, period=MatchEventPeriod.PENALTY_SHOOTOUT),
            ],
            clock=CLOCK,
        )
        self.assertEqual(replay.status, MatchGameStateStatus.VERIFIED_WITH_SHOOTOUT)
        self.assertEqual(replay.shootout_goal_event_count, 1)
        self.assertEqual(
            sum(e.exposure_seconds for e in replay.exposures if e.focal_team_id == 10),
            95 * 60,
        )

    def test_score_mismatch_missing_clock_and_incomplete_are_excluded(self):
        mismatch = replay_match_game_state(match(0, 0), [event(1, 600)], clock=CLOCK)
        self.assertFalse(mismatch.eligible)
        self.assertEqual(
            mismatch.exclusion_reason, MatchGameStateExclusionReason.SCORE_MISMATCH
        )
        self.assertFalse(mismatch.episodes)
        missing = replay_match_game_state(match(0, 0), [], clock=None)
        self.assertEqual(
            missing.exclusion_reason,
            MatchGameStateExclusionReason.CLOCK_METADATA_MISSING,
        )
        incomplete = replay_match_game_state(
            match(0, 0, status=ProviderMatchStatus.LIVE), [], clock=CLOCK
        )
        self.assertEqual(
            incomplete.exclusion_reason, MatchGameStateExclusionReason.NOT_COMPLETED
        )

    def test_rebuild_content_is_deterministic(self):
        rows = [event(1, 600), event(2, 1200, team="away")]
        first = replay_match_game_state(match(1, 1), rows, clock=CLOCK)
        second = replay_match_game_state(match(1, 1), list(reversed(rows)), clock=CLOCK)
        self.assertEqual(first.episodes, second.episodes)
        self.assertEqual(first.exposures, second.exposures)
        self.assertEqual(first.diagnostics, second.diagnostics)


class GameStateMaterializationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        competition = Competition.objects.create(
            name="Test League", short_code="TST", country="Test"
        )
        season = Season.objects.create(label="2025-26", sort_order=2026)
        cls.competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
            has_whoscored=True,
            whoscored_league="test",
            whoscored_season="2025-26",
            whoscored_expected_match_count=1,
        )
        cls.home = CanonicalTeam.objects.create(name="Home")
        cls.away = CanonicalTeam.objects.create(name="Away")

    def setUp(self):
        self.match = ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id="state-test",
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
        ProviderMatchPayload.objects.create(
            provider_match=self.match,
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
        self.goal = ProviderMatchEvent.objects.create(
            provider_match=self.match,
            event_index=1,
            provider_event_sequence_id="1",
            provider_team_id="home",
            team=self.home,
            period=MatchEventPeriod.FIRST_HALF,
            minute=10,
            second=0,
            match_seconds=600,
            timeline_seconds=600,
            event_type=MatchEventType.SHOT,
            shot_outcome=MatchEventShotOutcome.GOAL,
        )
        self.opponent_event = ProviderMatchEvent.objects.create(
            provider_match=self.match,
            event_index=2,
            provider_event_sequence_id="2",
            provider_team_id="away",
            team=self.away,
            period=MatchEventPeriod.FIRST_HALF,
            minute=10,
            second=0,
            match_seconds=600,
            timeline_seconds=600,
            event_type=MatchEventType.PASS,
        )

    def test_materializes_rows_helpers_and_public_safe_metadata(self):
        audit = materialize_match_game_state(self.match, clock=CLOCK)
        self.assertTrue(audit.eligible)
        self.assertEqual(audit.exposure_seconds, 95 * 60)
        self.assertEqual(audit.focal_team_count, 2)
        self.assertEqual(
            sum(
                episode.duration_seconds
                for episode in ProviderMatchTeamGameStateEpisode.objects.filter(
                    provider_match=self.match, focal_team=self.home
                )
            ),
            95 * 60,
        )
        context = state_context_for_event(self.opponent_event, self.home)
        self.assertEqual(context["state"], MatchEventGameState.WINNING)
        scoped_ids = set(
            scope_events_to_focal_state(
                ProviderMatchEvent.objects.filter(provider_match=self.match),
                self.home,
                state=MatchEventGameState.WINNING,
            ).values_list("event_index", flat=True)
        )
        self.assertEqual(scoped_ids, {1, 2})
        fresh_state_ids = set(
            scope_events_to_focal_state(
                ProviderMatchEvent.objects.filter(provider_match=self.match),
                self.home,
                state=MatchEventGameState.WINNING,
                maximum_state_age_seconds=1,
            ).values_list("event_index", flat=True)
        )
        self.assertEqual(fresh_state_ids, {1, 2})
        aged_state_ids = set(
            scope_events_to_focal_state(
                ProviderMatchEvent.objects.filter(provider_match=self.match),
                self.home,
                state=MatchEventGameState.WINNING,
                minimum_state_age_seconds=1,
            ).values_list("event_index", flat=True)
        )
        self.assertEqual(aged_state_ids, set())
        metadata = public_game_state_metadata(self.home, [self.match])
        self.assertEqual(metadata["exposure_seconds"], 95 * 60)
        self.assertEqual(metadata["matches_included"], 1)
        self.assertNotIn("diagnostics", metadata)

    def test_failed_rebuild_rolls_back_prior_complete_materialization(self):
        first = materialize_match_game_state(self.match, clock=CLOCK)
        prior_ids = list(
            ProviderMatchTeamGameStateEpisode.objects.filter(
                provider_match=self.match
            ).values_list("id", flat=True)
        )
        with patch.object(
            ProviderMatchTeamGameStateEpisode.objects,
            "bulk_create",
            side_effect=RuntimeError("stop"),
        ):
            with self.assertRaises(RuntimeError):
                materialize_match_game_state(self.match, clock=CLOCK)
        self.assertEqual(
            list(
                ProviderMatchTeamGameStateEpisode.objects.filter(
                    provider_match=self.match
                ).values_list("id", flat=True)
            ),
            prior_ids,
        )
        self.assertEqual(self.match.game_state.pk, first.pk)
