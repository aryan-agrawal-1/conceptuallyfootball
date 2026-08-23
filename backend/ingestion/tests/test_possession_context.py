from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter

from django.test import SimpleTestCase, TestCase

from ingestion.models import (
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    MatchEventGameState,
    MatchEventPeriod,
    MatchEventShotOutcome,
    MatchEventShotSituation,
    MatchEventType,
    MatchStateDrawProvenance,
    MatchStatePhase,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchPossession,
    ProviderMatchStatus,
    ProviderMatchTeamGameStateEpisode,
    Season,
)
from ingestion.services.possession_context import (
    POSSESSION_CALCULATION_VERSION,
    derive_possessions,
    replace_match_possessions,
)


def memory_event(index, team="home", event_type=MatchEventType.PASS, **overrides):
    values = {
        "event_index": index,
        "provider_team_id": team,
        "team_id": 1 if team == "home" else 2,
        "provider_player_id": f"{team}-p{index % 4}",
        "player_id": None,
        "period": 1,
        "timeline_seconds": index,
        "match_seconds": index,
        "event_type": event_type,
        "is_deleted_event": False,
        "outcome_successful": True,
        "is_set_piece": False,
        "is_throw_in": False,
        "is_corner": False,
        "is_free_kick": False,
        "x": 3000 + index * 10,
        "y": 5000,
        "end_x": 3500 + index * 10,
        "end_y": 5000,
        "shot_outcome": MatchEventShotOutcome.UNKNOWN,
    }
    values.update(overrides)
    return type("Event", (), values)()


class PossessionRuleTests(SimpleTestCase):
    def test_failed_opponent_defence_does_not_change_control_and_restart_does(self):
        events = [
            memory_event(1),
            memory_event(2, "away", MatchEventType.CHALLENGE, outcome_successful=False),
            memory_event(3),
            memory_event(4, is_throw_in=True),
        ]
        result = derive_possessions(events)
        self.assertEqual(len(result.possessions), 2)
        self.assertEqual([event.event_index for event in result.possessions[0].events], [1, 2, 3])
        self.assertEqual(result.possessions[0].termination_reason, "restart")
        self.assertEqual(result.possessions[1].launch_type, "restart")

    def test_unknown_event_is_explicitly_ambiguous_and_never_double_assigned(self):
        unknown = memory_event(2, event_type=MatchEventType.UNKNOWN)
        result = derive_possessions([memory_event(1), unknown, memory_event(3)])
        self.assertEqual(result.excluded, ({"event_index": 2, "reason": "ambiguous_control"},))
        assigned = [event.event_index for possession in result.possessions for event in possession.events]
        self.assertEqual(assigned, [1, 3])
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertTrue(result.possessions[0].ambiguous)

    def test_pilot_scale_derivation_is_linear_and_under_one_second(self):
        events = []
        for match_offset in range(20):
            for index in range(1500):
                absolute = match_offset * 1500 + index
                events.append(memory_event(absolute, team="home" if index % 10 < 5 else "away"))
        started = perf_counter()
        result = derive_possessions(events)
        elapsed = perf_counter() - started
        self.assertEqual(sum(len(row.events) for row in result.possessions), 30_000)
        self.assertLess(elapsed, 1.0)


class PossessionPersistenceTests(TestCase):
    def setUp(self):
        competition = Competition.objects.create(name="Test", short_code="TST")
        season = Season.objects.create(label="2025-26")
        self.cs = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
            has_whoscored=True,
            whoscored_league="test",
            whoscored_season="2526",
            is_published=True,
        )
        self.home = CanonicalTeam.objects.create(name="Home")
        self.away = CanonicalTeam.objects.create(name="Away")
        self.match = ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id="112-test",
            competition_season=self.cs,
            kickoff_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            status=ProviderMatchStatus.COMPLETED,
            home_provider_team_id="home",
            away_provider_team_id="away",
            home_team=self.home,
            away_team=self.away,
            home_score=1,
            away_score=0,
        )

    def add_event(self, index, team="home", event_type=MatchEventType.PASS, **values):
        defaults = {
            "provider_match": self.match,
            "event_index": index,
            "provider_event_sequence_id": str(index),
            "provider_team_id": team,
            "team": self.home if team == "home" else self.away,
            "provider_player_id": f"{team}-{index % 2}",
            "period": MatchEventPeriod.FIRST_HALF,
            "minute": 0,
            "second": index,
            "match_seconds": index,
            "timeline_seconds": index,
            "event_type": event_type,
            "outcome_successful": True,
            "x": 3000,
            "y": 5000,
            "end_x": 4000,
            "end_y": 5000,
        }
        defaults.update(values)
        return ProviderMatchEvent.objects.create(**defaults)

    def test_counter_thresholds_provider_evidence_and_replacement_are_deterministic(self):
        self.add_event(1, "away", MatchEventType.PASS, outcome_successful=False)
        self.add_event(2, "home", MatchEventType.BALL_RECOVERY, x=4000, end_x=4000)
        self.add_event(5, "home", MatchEventType.PASS, x=4000, end_x=6667)
        self.add_event(
            8,
            "home",
            MatchEventType.SHOT,
            x=8500,
            shot_outcome=MatchEventShotOutcome.SAVED,
            shot_situation=MatchEventShotSituation.FAST_BREAK,
        )
        first_count = replace_match_possessions(self.match)
        first = list(ProviderMatchPossession.objects.values_list("identity", flat=True))
        counter = ProviderMatchPossession.objects.get(team=self.home, is_counter_launch=True)
        self.assertTrue(counter.counter_final_third_arrival)
        self.assertTrue(counter.counter_box_arrival)
        self.assertTrue(counter.counter_shot)
        self.assertEqual(counter.provider_fast_break_shot_count, 1)
        self.assertEqual(counter.counter_outcome, "saved")
        second_count = replace_match_possessions(self.match)
        self.assertEqual(second_count, first_count)
        self.assertEqual(list(ProviderMatchPossession.objects.values_list("identity", flat=True)), first)
        self.assertEqual(self.match.possession_build.calculation_version, POSSESSION_CALCULATION_VERSION)

    def test_settled_boundary_excludes_transition_defence_and_classifies_high_block(self):
        self.add_event(1, "home", MatchEventType.PASS)
        self.add_event(2, "away", MatchEventType.CHALLENGE, outcome_successful=False, x=9000)
        self.add_event(5, "home", MatchEventType.PASS)
        self.add_event(10, "home", MatchEventType.BALL_TOUCH)
        self.add_event(11, "away", MatchEventType.CLEARANCE, x=8000)
        replace_match_possessions(self.match)
        possession = ProviderMatchPossession.objects.get(team=self.home)
        self.assertEqual(possession.establishment_second, 10)
        self.assertEqual(possession.settled_defensive_action_count, 1)
        self.assertEqual(possession.settled_block_height, "high")

    def test_counter_minimum_forward_boundary_is_inclusive_and_versioned(self):
        self.add_event(1, "home", MatchEventType.BALL_RECOVERY, x=4000, end_x=4000)
        progress = self.add_event(5, "home", MatchEventType.PASS, x=4000, end_x=6000)
        replace_match_possessions(self.match)
        counter = ProviderMatchPossession.objects.get()
        self.assertTrue(counter.diagnostics["qualifies_counter_progress"])
        self.assertEqual(float(counter.counter_forward_metres), 21.0)
        progress.end_x = 5999
        progress.save(update_fields=["end_x"])
        replace_match_possessions(self.match)
        counter = ProviderMatchPossession.objects.get()
        self.assertFalse(counter.diagnostics["qualifies_counter_progress"])
        self.assertEqual(counter.build.calculation_version, POSSESSION_CALCULATION_VERSION)

    def test_goal_terminal_uses_pre_goal_state_without_leaking(self):
        ProviderMatchTeamGameStateEpisode.objects.create(
            provider_match=self.match,
            focal_team=self.home,
            focal_is_home=True,
            episode_index=0,
            period=1,
            phase=MatchStatePhase.FIRST_HALF,
            start_second=0,
            end_second=20,
            duration_seconds=20,
            focal_score=0,
            opponent_score=0,
            goal_difference=0,
            state=MatchEventGameState.DRAWING,
            draw_provenance=MatchStateDrawProvenance.NEUTRAL,
            state_entry_second=0,
            state_age_seconds_at_start=0,
            calculation_version="team_game_state_v1",
        )
        ProviderMatchTeamGameStateEpisode.objects.create(
            provider_match=self.match,
            focal_team=self.home,
            focal_is_home=True,
            episode_index=1,
            period=1,
            phase=MatchStatePhase.FIRST_HALF,
            start_second=20,
            end_second=100,
            duration_seconds=80,
            focal_score=1,
            opponent_score=0,
            goal_difference=1,
            state=MatchEventGameState.WINNING,
            previous_state=MatchEventGameState.DRAWING,
            draw_provenance=MatchStateDrawProvenance.NONE,
            state_entry_second=20,
            state_age_seconds_at_start=0,
            calculation_version="team_game_state_v1",
        )
        self.add_event(10)
        self.add_event(
            20,
            event_type=MatchEventType.SHOT,
            shot_outcome=MatchEventShotOutcome.GOAL,
            game_state_before=MatchEventGameState.DRAWING,
            game_state_after=MatchEventGameState.WINNING,
        )
        replace_match_possessions(self.match)
        states = {row["state"] for row in ProviderMatchPossession.objects.get().state_segments}
        self.assertEqual(states, {"drawing"})

    def test_public_payload_separates_provider_observation_and_hides_provider_ids(self):
        self.add_event(1, "away", MatchEventType.PASS, outcome_successful=False)
        self.add_event(2, "home", MatchEventType.BALL_RECOVERY, x=3000)
        self.add_event(5, "home", MatchEventType.PASS, x=3000, end_x=7000)
        replace_match_possessions(self.match)
        response = self.client.get(
            f"/api/v1/team-seasons/possession-context/{self.home.id}",
            {"competition_season": self.cs.id},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["provider_observed"]["substitutes_for_derived_counters"])
        self.assertNotIn("provider_team_id", response.content.decode())
        self.assertNotIn("provider_player_id", response.content.decode())
