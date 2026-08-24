from datetime import datetime, timezone

from django.test import TestCase
from rest_framework.test import APIClient

from ingestion.models import (
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    MatchEventGameState,
    MatchEventPeriod,
    MatchEventShotOutcome,
    MatchEventShotSituation,
    MatchEventType,
    MatchGameStateStatus,
    MatchStateDrawProvenance,
    MatchStatePhase,
    MaterializedApiPayload,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchStatus,
    ProviderMatchTeamGameStateEpisode,
    Season,
    TeamSeasonEventProfile,
)


class TeamShotPressureApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        competition = Competition.objects.create(name="Test League", short_code="TST")
        season = Season.objects.create(label="2025-26", sort_order=2026)
        self.competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
            has_whoscored=True,
            whoscored_league="test",
            whoscored_season="2025",
            is_published=True,
        )
        self.home = CanonicalTeam.objects.create(name="Home")
        self.away = CanonicalTeam.objects.create(name="Away")
        self.match = ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id="shot-pressure-1",
            competition_season=self.competition_season,
            kickoff_at=datetime(2026, 1, 1, 15, tzinfo=timezone.utc),
            status=ProviderMatchStatus.COMPLETED,
            home_provider_team_id="home",
            away_provider_team_id="away",
            home_team=self.home,
            away_team=self.away,
            home_score=2,
            away_score=1,
        )
        run = IngestionRun.objects.create(
            kind=IngestionKind.EVENT_PROFILES,
            competition_season=self.competition_season,
        )
        for team in (self.home, self.away):
            TeamSeasonEventProfile.objects.create(
                competition_season=self.competition_season,
                team=team,
                materialized_ingestion_run=run,
                observed_match_count=1,
            )
        ProviderMatchGameState.objects.create(
            provider_match=self.match,
            status=MatchGameStateStatus.VERIFIED,
            eligible=True,
            calculation_version="team_game_state_v1",
            exposure_seconds=6000,
            episode_count=6,
            focal_team_count=2,
            calculated_at=datetime.now(timezone.utc),
        )
        self.episode(self.home, 0, 0, 601, MatchEventGameState.DRAWING, 0)
        self.episode(self.home, 1, 601, 1200, MatchEventGameState.WINNING, 1)
        self.episode(
            self.home,
            2,
            5400,
            6000,
            MatchEventGameState.WINNING,
            1,
            period=MatchEventPeriod.FIRST_EXTRA_TIME,
            phase=MatchStatePhase.FIRST_EXTRA_TIME,
        )
        self.episode(self.away, 0, 0, 601, MatchEventGameState.DRAWING, 0)
        self.episode(self.away, 1, 601, 1200, MatchEventGameState.LOSING, -1)
        self.episode(
            self.away,
            2,
            5400,
            6000,
            MatchEventGameState.LOSING,
            -1,
            period=MatchEventPeriod.FIRST_EXTRA_TIME,
            phase=MatchStatePhase.FIRST_EXTRA_TIME,
        )
        self.shot(
            1,
            self.home,
            100,
            MatchEventShotSituation.OPEN_PLAY,
            MatchEventShotOutcome.SAVED,
            x=9000,
            y=5000,
            is_big_chance=True,
        )
        self.shot(
            2,
            self.home,
            200,
            MatchEventShotSituation.PENALTY,
            MatchEventShotOutcome.GOAL,
        )
        self.shot(
            3,
            self.away,
            300,
            MatchEventShotSituation.FAST_BREAK,
            MatchEventShotOutcome.BLOCKED,
            x=7000,
            y=1000,
        )
        ProviderMatchEvent.objects.create(
            provider_match=self.match,
            event_index=4,
            provider_team_id="away",
            team=self.away,
            period=MatchEventPeriod.FIRST_HALF,
            minute=6,
            second=40,
            timeline_seconds=400,
            event_type=MatchEventType.OWN_GOAL,
            shot_outcome=MatchEventShotOutcome.GOAL,
        )
        # A scoring shot belongs to the episode it terminates under [start, end).
        self.shot(
            5,
            self.home,
            600,
            MatchEventShotSituation.SET_PIECE,
            MatchEventShotOutcome.GOAL,
        )

    @property
    def scope(self):
        return {"competition": "TST", "season": "2025-26"}

    def url(self, team):
        return f"/api/v1/team-seasons/shot-pressure/{team.id}"

    def episode(
        self,
        team,
        index,
        start,
        end,
        state,
        difference,
        *,
        period=MatchEventPeriod.FIRST_HALF,
        phase=MatchStatePhase.FIRST_HALF,
    ):
        ProviderMatchTeamGameStateEpisode.objects.create(
            provider_match=self.match,
            focal_team=team,
            focal_is_home=team == self.home,
            episode_index=index,
            period=period,
            phase=phase,
            start_second=start,
            end_second=end,
            duration_seconds=end - start,
            focal_score=max(difference, 0),
            opponent_score=max(-difference, 0),
            goal_difference=difference,
            state=state,
            draw_provenance=(
                MatchStateDrawProvenance.NEUTRAL
                if state == MatchEventGameState.DRAWING
                else MatchStateDrawProvenance.NONE
            ),
            state_entry_second=start,
            state_age_seconds_at_start=0,
            calculation_version="team_game_state_v1",
        )

    def shot(self, index, team, seconds, situation, outcome, *, x=8800, y=4500, **extra):
        return ProviderMatchEvent.objects.create(
            provider_match=self.match,
            event_index=index,
            provider_team_id="home" if team == self.home else "away",
            team=team,
            period=MatchEventPeriod.FIRST_HALF,
            minute=seconds // 60,
            second=seconds % 60,
            match_seconds=seconds,
            timeline_seconds=seconds,
            event_type=MatchEventType.SHOT,
            shot_situation=situation,
            shot_outcome=outcome,
            x=x,
            y=y,
            **extra,
        )

    def test_default_rates_breakdowns_boundaries_and_zero_shot_episodes(self):
        response = self.client.get(
            self.url(self.home),
            {**self.scope, "state": "drawing", "draw_provenance": "neutral"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        selected = payload["selected"]
        self.assertEqual(payload["penalty_mode"], "exclude")
        self.assertEqual(payload["state_lens"]["selected"]["state"], "drawing")
        self.assertIn("draw_provenances", payload["state_lens"]["eligible_refinements"])
        self.assertEqual(
            payload["state_lens"]["evidence"]["exposure_seconds"],
            selected["evidence"]["exposure_seconds"],
        )
        self.assertEqual(selected["evidence"]["exposure_seconds"], 601)
        self.assertEqual(selected["frequency"]["for"]["shots"]["count"], 2)
        self.assertEqual(selected["frequency"]["against"]["shots"]["count"], 1)
        self.assertEqual(selected["frequency"]["against"]["open_play"]["count"], 1)
        self.assertEqual(selected["frequency"]["for"]["set_piece"]["count"], 1)
        self.assertEqual(selected["frequency"]["against"]["provider_tagged_fast_break"]["count"], 1)
        self.assertEqual(selected["frequency"]["for"]["box"]["count"], 2)
        self.assertEqual(selected["frequency"]["for"]["on_target"]["count"], 2)
        self.assertAlmostEqual(selected["frequency"]["for"]["shots"]["per_minute"], 0.1997)
        self.assertEqual(selected["outcomes"]["for"]["goal"]["count"], 1)
        self.assertEqual(selected["first_shot"]["for"]["mean_seconds_from_state_entry"], 100)
        self.assertEqual(selected["evidence"]["zero_shot_episodes_for"], 0)
        self.assertEqual(len(selected["location"]["for"]["cells"]), 24)
        def nested_keys(value):
            if isinstance(value, dict):
                return set(value) | set().union(
                    *(nested_keys(item) for item in value.values()), set()
                )
            if isinstance(value, list):
                return set().union(*(nested_keys(item) for item in value), set())
            return set()

        self.assertFalse({key for key in nested_keys(payload) if "xg" in key.lower()})

    def test_penalties_require_explicit_mode_and_cache_is_separated(self):
        included = self.client.get(
            self.url(self.home), {**self.scope, "penalty_mode": "include"}
        ).json()
        only = self.client.get(
            self.url(self.home), {**self.scope, "penalty_mode": "only"}
        ).json()
        self.assertEqual(included["selected"]["frequency"]["for"]["shots"]["count"], 3)
        self.assertEqual(only["selected"]["frequency"]["for"]["shots"]["count"], 1)
        self.assertEqual(only["selected"]["frequency"]["for"]["penalty"]["count"], 1)
        self.assertGreaterEqual(
            MaterializedApiPayload.objects.filter(
                cache_key__startswith=f"shot-pressure:{self.competition_season.id}:team:"
            ).count(),
            2,
        )
        invalid = self.client.get(
            self.url(self.home), {**self.scope, "penalty_mode": "sometimes"}
        )
        self.assertEqual(invalid.status_code, 400)

    def test_perspective_inverts_without_counting_own_goals_as_shots(self):
        home = self.client.get(self.url(self.home), self.scope).json()["selected"]
        away = self.client.get(self.url(self.away), self.scope).json()["selected"]
        self.assertEqual(
            home["frequency"]["for"]["shots"]["count"],
            away["frequency"]["against"]["shots"]["count"],
        )
        self.assertEqual(
            home["frequency"]["against"]["shots"]["count"],
            away["frequency"]["for"]["shots"]["count"],
        )
        self.assertEqual(home["frequency"]["openness"]["shot_count"], 3)

    def test_extra_time_empty_and_comparison_rate_surfaces(self):
        response = self.client.get(
            self.url(self.home),
            {
                **self.scope,
                "state": "winning",
                "phase": "first_extra_time",
                "baseline_state": "drawing",
                "baseline_draw_provenance": "neutral",
            },
        )
        payload = response.json()
        self.assertTrue(payload["selected"]["evidence"]["empty"] is False)
        self.assertEqual(payload["selected"]["evidence"]["exposure_seconds"], 600)
        self.assertEqual(payload["selected"]["evidence"]["zero_shot_episodes_for"], 1)
        self.assertIsNone(
            payload["selected"]["first_shot"]["for"]["mean_seconds_from_state_entry"]
        )
        self.assertTrue(payload["comparison"]["enabled"])
        cells = payload["comparison"]["selected_minus_baseline"]["location"]["for"]
        self.assertEqual(len(cells), 24)
        self.assertIn("shots_per_90_delta", cells[0])

        empty = self.client.get(
            self.url(self.home), {**self.scope, "state": "losing"}
        ).json()["selected"]
        self.assertTrue(empty["evidence"]["empty"])
        self.assertIsNone(empty["frequency"]["for"]["shots"]["per_minute"])
