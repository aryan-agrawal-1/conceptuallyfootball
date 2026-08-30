from dataclasses import replace
from datetime import datetime, timezone
import json
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIRequestFactory

from ingestion.models import (
    MatchEventGameState,
    MatchEventPeriod,
    MatchEventShotOutcome,
    MatchEventShotSituation,
    MatchEventType,
    MatchStateDrawProvenance,
    MatchStatePhase,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    MaterializedApiPayload,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchPlayedPeriod,
    ProviderMatchStatus,
    ProviderMatchTeamGameStateEpisode,
    Season,
    TeamSeasonEventProfile,
)
from ingestion.services.response_half_life import (
    ResponseMatchData,
    build_response_half_life_cohort,
    response_half_life_definitions,
)
from ingestion.response_half_life_api import TeamResponseHalfLifeApi


def make_match(home_score=1, away_score=1, *, match_id=1):
    return SimpleNamespace(
        id=match_id,
        home_team_id=10,
        away_team_id=20,
        home_provider_team_id="home",
        away_provider_team_id="away",
        home_score=home_score,
        away_score=away_score,
    )


def make_event(
    index,
    second,
    *,
    team="home",
    event_type=MatchEventType.PASS,
    x=7000,
    y=5000,
    end_x=8000,
    end_y=5000,
    completed=True,
    progressive=False,
    box=False,
    shot_outcome=MatchEventShotOutcome.UNKNOWN,
    shot_situation=MatchEventShotSituation.OPEN_PLAY,
    dismissal_type="none",
    participation_action="none",
):
    return SimpleNamespace(
        event_index=index,
        provider_event_sequence_id=str(index),
        provider_team_id=team,
        period=MatchEventPeriod.FIRST_HALF,
        minute=second // 60,
        second=second % 60,
        timeline_seconds=second,
        match_seconds=second,
        event_type=event_type,
        shot_outcome=shot_outcome,
        shot_situation=shot_situation,
        is_goal_disallowed=False,
        is_deleted_event=False,
        scoring_provider_team_id=None,
        home_score_before=None,
        away_score_before=None,
        home_score_after=None,
        away_score_after=None,
        outcome_successful=completed,
        x=x,
        y=y,
        end_x=end_x,
        end_y=end_y,
        is_progressive_pass=progressive,
        is_box_entry=box,
        is_final_third_entry=box,
        is_big_chance=False,
        is_defensive=event_type in {
            MatchEventType.BALL_RECOVERY,
            MatchEventType.TACKLE,
            MatchEventType.INTERCEPTION,
        },
        is_touch=event_type in {
            MatchEventType.PASS,
            MatchEventType.BALL_TOUCH,
            MatchEventType.TAKE_ON,
            MatchEventType.SHOT,
        },
        dismissal_type=dismissal_type,
        participation_action=participation_action,
    )


def make_goal(index, second, *, team="away"):
    return make_event(
        index,
        second,
        team=team,
        event_type=MatchEventType.SHOT,
        x=9000,
        y=5000,
        end_x=None,
        end_y=None,
        shot_outcome=MatchEventShotOutcome.GOAL,
    )


def make_episode(
    index,
    start,
    end,
    *,
    state,
    difference,
    entry,
    provenance=MatchStateDrawProvenance.NONE,
    period=MatchEventPeriod.FIRST_HALF,
    phase=MatchStatePhase.FIRST_HALF,
):
    return SimpleNamespace(
        episode_index=index,
        period=period,
        phase=phase,
        start_second=start,
        end_second=end,
        state=state,
        goal_difference=difference,
        state_entry_second=entry,
        state_age_seconds_at_start=start - entry,
        draw_provenance=provenance,
    )


def make_period(*, period=MatchEventPeriod.FIRST_HALF, start=0, end=5400):
    return SimpleNamespace(
        period=period,
        period_index=0,
        start_second=start,
        end_second=end,
    )


def response_data(
    *,
    match_id=1,
    goal_second=600,
    after_state=MatchEventGameState.LOSING,
    after_difference=-1,
    end_second=5400,
    extra_events=(),
    next_goals=(),
):
    events = [make_goal(1, goal_second)]
    events.extend(next_goals)
    # The first window is deliberately unlike the stable destination.  The
    # later events are placed after the 600-second stable-age threshold.
    events.append(make_event(10, goal_second + 10, x=1000, end_x=900, progressive=False, box=False))
    stable_index = 100
    for second in range(1300, min(end_second, 2500), 100):
        events.append(
            make_event(
                stable_index,
                second,
                x=7000,
                end_x=8500,
                progressive=True,
                box=True,
            )
        )
        stable_index += 1
    events.append(
        make_event(
            stable_index,
            1350,
            event_type=MatchEventType.SHOT,
            x=8000,
            y=5000,
            end_x=None,
            end_y=None,
            shot_outcome=MatchEventShotOutcome.SAVED,
        )
    )
    stable_index += 1
    events.append(
        make_event(
            stable_index,
            1450,
            event_type=MatchEventType.BALL_RECOVERY,
            x=6000,
            y=4000,
            end_x=None,
            end_y=None,
        )
    )
    events.extend(extra_events)
    events.sort(key=lambda event: (event.timeline_seconds, event.event_index))
    episodes = [
        make_episode(
            0,
            0,
            goal_second,
            state=MatchEventGameState.DRAWING,
            difference=0,
            entry=0,
            provenance=MatchStateDrawProvenance.NEUTRAL,
        ),
        make_episode(
            1,
            goal_second,
            end_second,
            state=after_state,
            difference=after_difference,
            entry=goal_second,
            provenance=(
                MatchStateDrawProvenance.SURRENDERED
                if after_state == MatchEventGameState.DRAWING
                else MatchStateDrawProvenance.NONE
            ),
        ),
    ]
    return ResponseMatchData(
        match=make_match(match_id=match_id),
        events=tuple(events),
        episodes=tuple(episodes),
        carries=(),
    )


class ResponseHalfLifeContractTests(SimpleTestCase):
    def test_window_contract_is_deterministic_and_destination_is_exact(self):
        data = response_data()
        cohort = build_response_half_life_cohort(
            focal_team_id=10,
            matches=[data],
            destination_matches=[data],
            periods_by_match={1: [make_period()]},
            match_refs={1: 0},
        )
        episode = cohort["episodes"][0]
        self.assertEqual(episode["destination"]["match_basis"], "state_phase_goal_difference")
        self.assertTrue(episode["qualifies"])
        self.assertEqual(episode["windows"][1]["offset_seconds"], 60)
        self.assertEqual(episode["windows"][0]["end_second"] - episode["windows"][1]["start_second"], 240)
        self.assertIn("first_five_minute_response", episode)
        self.assertTrue(episode["first_five_minute_response"]["available"])
        self.assertEqual(episode["attacking"]["status"], "recovered")
        self.assertEqual(episode["structural"]["status"], "recovered")
        self.assertEqual(cohort["qualifying_concessions"], 1)
        self.assertEqual(cohort["qualifying_matches"], 1)

    def test_period_end_added_time_extra_time_and_half_time_are_never_crossed(self):
        late = response_data(goal_second=5201, end_second=5400)
        late_cohort = build_response_half_life_cohort(
            focal_team_id=10,
            matches=[late],
            destination_matches=[late],
            periods_by_match={1: [make_period()]},
        )
        self.assertEqual(late_cohort["censor_reasons"], {"period_boundary": 1})

        half_time = response_data(goal_second=2600, end_second=2700)
        half_time_cohort = build_response_half_life_cohort(
            focal_team_id=10,
            matches=[half_time],
            destination_matches=[half_time],
            periods_by_match={1: [make_period(end=2700)]},
        )
        self.assertEqual(half_time_cohort["censor_reasons"], {"period_boundary": 1})

        added = response_data(goal_second=2500, end_second=2820)
        added_cohort = build_response_half_life_cohort(
            focal_team_id=10,
            matches=[added],
            destination_matches=[added],
            periods_by_match={1: [make_period(end=2820)]},
        )
        self.assertFalse(added_cohort["episodes"][0]["qualifies"])
        self.assertEqual(added_cohort["episodes"][0]["censor_reason"], "no_destination")
        self.assertTrue(added_cohort["episodes"][0]["windows"][0]["is_added_time"])

        extra = response_data(goal_second=1000, end_second=1800)
        extra = replace(
            extra,
            episodes=(
                make_episode(
                    0,
                    0,
                    1000,
                    state=MatchEventGameState.DRAWING,
                    difference=0,
                    entry=0,
                ),
                make_episode(
                    1,
                    1000,
                    1800,
                    state=MatchEventGameState.LOSING,
                    difference=-1,
                    entry=1000,
                    period=MatchEventPeriod.FIRST_EXTRA_TIME,
                    phase=MatchStatePhase.FIRST_EXTRA_TIME,
                ),
            ),
        )
        extra_period = make_period(period=MatchEventPeriod.FIRST_EXTRA_TIME, start=0, end=1800)
        extra_cohort = build_response_half_life_cohort(
            focal_team_id=10,
            matches=[extra],
            destination_matches=[extra],
            periods_by_match={1: [extra_period]},
        )
        self.assertEqual(extra_cohort["censor_reasons"], {"no_destination": 1})

    def test_rapid_goal_red_card_and_participation_uncertainty_are_censored(self):
        rapid = response_data(next_goals=(make_goal(2, 660),))
        rapid_cohort = build_response_half_life_cohort(
            focal_team_id=10,
            matches=[rapid],
            destination_matches=[rapid],
            periods_by_match={1: [make_period()]},
        )
        self.assertEqual(rapid_cohort["censor_reasons"], {"rapid_subsequent_goal": 1})

        red = response_data(extra_events=(make_event(20, 700, event_type=MatchEventType.CARD, dismissal_type="red"),))
        red_cohort = build_response_half_life_cohort(
            focal_team_id=10,
            matches=[red],
            destination_matches=[red],
            periods_by_match={1: [make_period()]},
        )
        self.assertEqual(red_cohort["censor_reasons"], {"red_card": 1})

        substitution = response_data(extra_events=(make_event(20, 700, event_type=MatchEventType.SUBSTITUTION, participation_action="player_off"),))
        substitution_cohort = build_response_half_life_cohort(
            focal_team_id=10,
            matches=[substitution],
            destination_matches=[substitution],
            periods_by_match={1: [make_period()]},
        )
        self.assertEqual(substitution_cohort["censor_reasons"], {"participation_uncertainty": 1})

    def test_restored_draw_multi_goal_and_no_destination_are_explicit(self):
        restored = response_data(
            after_state=MatchEventGameState.DRAWING,
            after_difference=0,
        )
        restored_cohort = build_response_half_life_cohort(
            focal_team_id=10,
            matches=[restored],
            destination_matches=[restored],
            periods_by_match={1: [make_period()]},
        )
        self.assertEqual(restored_cohort["episodes"][0]["state"]["draw_provenance"], "surrendered")

        no_destination = response_data(end_second=1500)
        no_destination_cohort = build_response_half_life_cohort(
            focal_team_id=10,
            matches=[no_destination],
            destination_matches=[no_destination],
            periods_by_match={1: [make_period(end=1500)]},
        )
        self.assertFalse(no_destination_cohort["available"])
        self.assertEqual(no_destination_cohort["censor_reasons"], {"no_destination": 1})
        self.assertIsNone(no_destination_cohort["attacking"]["half_life_seconds"]["median_seconds"])

        definitions = response_half_life_definitions()
        self.assertEqual(definitions["window_seconds"], 300)
        self.assertEqual(definitions["overlap_seconds"], 240)
        self.assertIn("goal_difference", definitions["destination"]["priority"])

    def test_multi_goal_deficit_keeps_each_resulting_goal_difference(self):
        data = response_data(
            goal_second=300,
            next_goals=(make_goal(2, 600),),
        )
        data = replace(
            data,
            episodes=(
                make_episode(
                    0,
                    0,
                    300,
                    state=MatchEventGameState.DRAWING,
                    difference=0,
                    entry=0,
                    provenance=MatchStateDrawProvenance.NEUTRAL,
                ),
                make_episode(
                    1,
                    300,
                    600,
                    state=MatchEventGameState.LOSING,
                    difference=-1,
                    entry=300,
                ),
                make_episode(
                    2,
                    600,
                    5400,
                    state=MatchEventGameState.LOSING,
                    difference=-2,
                    entry=600,
                ),
            ),
        )
        cohort = build_response_half_life_cohort(
            focal_team_id=10,
            matches=[data],
            destination_matches=[data],
            periods_by_match={1: [make_period()]},
        )
        self.assertEqual(
            [episode["score"]["after"]["focal_goal_difference"] for episode in cohort["episodes"]],
            [-1, -2],
        )
        self.assertEqual(cohort["episodes"][1]["destination"]["goal_difference"], -2)

    def test_no_recovery_is_not_replaced_with_a_fabricated_half_life(self):
        target = response_data()
        destination = response_data()
        for event in destination.events:
            if event.timeline_seconds >= 1300 and event.provider_team_id == "home":
                event.x = 1000
                event.end_x = 900
                event.is_progressive_pass = False
                event.is_box_entry = False
        for event in target.events:
            if event.timeline_seconds == 610:
                event.x = 9000
                event.end_x = 9500
                event.is_progressive_pass = True
                event.is_box_entry = True
        target = replace(
            target,
            events=target.events
            + tuple(
                make_event(
                    200 + index,
                    second,
                    x=9000,
                    end_x=9500,
                    progressive=True,
                    box=True,
                )
                for index, second in enumerate(range(700, 1500, 100))
            ),
        )
        cohort = build_response_half_life_cohort(
            focal_team_id=10,
            matches=[target],
            destination_matches=[destination],
            periods_by_match={1: [make_period()]},
        )
        episode = cohort["episodes"][0]
        self.assertEqual(episode["attacking"]["status"], "no_recovery")
        self.assertIsNone(episode["attacking"]["half_life_seconds"])


class TeamResponseHalfLifeApiTests(TestCase):
    def setUp(self):
        competition = Competition.objects.create(name="Test League", short_code="RHL")
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
            provider_match_id="response-half-life-api",
            competition_season=self.competition_season,
            kickoff_at=datetime(2026, 1, 1, 15, tzinfo=timezone.utc),
            status=ProviderMatchStatus.COMPLETED,
            home_provider_team_id="home",
            away_provider_team_id="away",
            home_team=self.home,
            away_team=self.away,
            home_score=0,
            away_score=1,
        )
        run = IngestionRun.objects.create(
            kind=IngestionKind.EVENT_PROFILES,
            competition_season=self.competition_season,
        )
        TeamSeasonEventProfile.objects.create(
            competition_season=self.competition_season,
            team=self.home,
            materialized_ingestion_run=run,
            observed_match_count=1,
        )
        ProviderMatchGameState.objects.create(
            provider_match=self.match,
            status="verified",
            eligible=True,
            calculation_version="team_game_state_v1",
            calculated_at=datetime.now(timezone.utc),
        )
        ProviderMatchPlayedPeriod.objects.create(
            provider_match=self.match,
            period=MatchEventPeriod.FIRST_HALF,
            period_index=0,
            start_second=0,
            end_second=5400,
            duration_seconds=5400,
            calculation_version="match_clock_v1",
        )
        self.episode(
            0,
            0,
            600,
            state=MatchEventGameState.DRAWING,
            difference=0,
            entry=0,
            provenance=MatchStateDrawProvenance.NEUTRAL,
        )
        self.episode(
            1,
            600,
            5400,
            state=MatchEventGameState.LOSING,
            difference=-1,
            entry=600,
        )
        ProviderMatchEvent.objects.create(
            provider_match=self.match,
            event_index=1,
            provider_event_sequence_id="1",
            provider_team_id="away",
            team=self.away,
            period=MatchEventPeriod.FIRST_HALF,
            minute=10,
            second=0,
            timeline_seconds=600,
            match_seconds=600,
            event_type=MatchEventType.SHOT,
            shot_outcome=MatchEventShotOutcome.GOAL,
            x=9000,
            y=5000,
        )
        ProviderMatchEvent.objects.create(
            provider_match=self.match,
            event_index=2,
            provider_event_sequence_id="2",
            provider_team_id="home",
            team=self.home,
            period=MatchEventPeriod.FIRST_HALF,
            minute=10,
            second=10,
            timeline_seconds=610,
            match_seconds=610,
            event_type=MatchEventType.PASS,
            outcome_successful=True,
            x=1000,
            y=5000,
            end_x=900,
            end_y=5000,
        )
        for index, second in enumerate(range(1300, 2400, 100), start=10):
            ProviderMatchEvent.objects.create(
                provider_match=self.match,
                event_index=index,
                provider_event_sequence_id=str(index),
                provider_team_id="home",
                team=self.home,
                period=MatchEventPeriod.FIRST_HALF,
                minute=second // 60,
                second=second % 60,
                timeline_seconds=second,
                match_seconds=second,
                event_type=MatchEventType.PASS,
                outcome_successful=True,
                x=7000,
                y=5000,
                end_x=8500,
                end_y=5000,
                is_progressive_pass=True,
                is_box_entry=True,
            )

    def episode(self, index, start, end, *, state, difference, entry, provenance=MatchStateDrawProvenance.NONE):
        ProviderMatchTeamGameStateEpisode.objects.create(
            provider_match=self.match,
            focal_team=self.home,
            focal_is_home=True,
            episode_index=index,
            period=MatchEventPeriod.FIRST_HALF,
            phase=MatchStatePhase.FIRST_HALF,
            start_second=start,
            end_second=end,
            duration_seconds=end - start,
            focal_score=max(difference, 0),
            opponent_score=max(-difference, 0),
            goal_difference=difference,
            state=state,
            draw_provenance=provenance,
            state_entry_second=entry,
            state_age_seconds_at_start=start - entry,
            calculation_version="team_game_state_v1",
        )

    def url(self):
        return f"/api/v1/team-seasons/response-half-life/{self.home.id}"

    def test_api_returns_inspectable_payload_and_reuses_materialized_cache(self):
        params = {"competition": "RHL", "season": "2025-26"}
        factory = APIRequestFactory()
        first = TeamResponseHalfLifeApi.as_view()(
            factory.get(self.url(), params), canonical_team_id=self.home.id
        )
        repeated = TeamResponseHalfLifeApi.as_view()(
            factory.get(self.url(), params), canonical_team_id=self.home.id
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first["X-Materialized-Payload"], "miss")
        self.assertEqual(repeated["X-Materialized-Payload"], "hit")
        payload = json.loads(first.content)
        self.assertEqual(payload["definitions"]["overlap_seconds"], 240)
        self.assertEqual(payload["selected"]["qualifying_concessions"], 1)
        self.assertEqual(payload["selected"]["episodes"][0]["destination"]["match_basis"], "state_phase_goal_difference")
        self.assertIn("attacking", payload["selected"]["episodes"][0])
        self.assertIn("structural", payload["selected"]["episodes"][0])
        self.assertTrue(payload["selected"]["episodes"][0]["windows"])
        self.assertEqual(
            MaterializedApiPayload.objects.filter(
                cache_key__startswith=f"event-profile:{self.competition_season.id}:team-response-half-life"
            ).count(),
            1,
        )
