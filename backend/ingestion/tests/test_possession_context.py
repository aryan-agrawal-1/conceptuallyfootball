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
    MatchGameStateStatus,
    MatchStateDrawProvenance,
    MatchStatePhase,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchGameState,
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

    def add_verified_state(self, match=None):
        match = match or self.match
        ProviderMatchGameState.objects.create(
            provider_match=match,
            status=MatchGameStateStatus.VERIFIED,
            eligible=True,
            calculation_version="team_game_state_v1",
            calculated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        for index, start, end, state, difference, provenance in (
            (0, 0, 20, MatchEventGameState.DRAWING, 0, MatchStateDrawProvenance.NEUTRAL),
            (1, 20, 100, MatchEventGameState.WINNING, 1, MatchStateDrawProvenance.NONE),
        ):
            ProviderMatchTeamGameStateEpisode.objects.create(
                provider_match=match,
                focal_team=self.home,
                focal_is_home=True,
                episode_index=index,
                period=1,
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

    def possession_request(self, **parameters):
        return self.client.get(
            f"/api/v1/team-seasons/possession-context/{self.home.id}",
            {"competition_season": self.cs.id, **parameters},
        )

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
        self.add_verified_state()
        self.add_event(1, "away", MatchEventType.PASS, outcome_successful=False)
        self.add_event(2, "home", MatchEventType.BALL_RECOVERY, x=3000)
        self.add_event(5, "home", MatchEventType.PASS, x=3000, end_x=7000)
        replace_match_possessions(self.match)
        response = self.possession_request()
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["provider_observed"]["substitutes_for_derived_counters"])
        self.assertNotIn("provider_team_id", response.content.decode())
        self.assertNotIn("provider_player_id", response.content.decode())

    def test_public_payload_scopes_launches_fast_breaks_and_baseline_to_state(self):
        self.add_verified_state()
        self.add_event(2, "home", MatchEventType.BALL_RECOVERY, x=3000)
        self.add_event(5, "home", MatchEventType.PASS, x=3000, end_x=7000)
        self.add_event(20, "away", MatchEventType.PASS, x=3000, end_x=4000)
        self.add_event(25, "home", MatchEventType.BALL_RECOVERY, x=3000)
        self.add_event(28, "home", MatchEventType.PASS, x=3000, end_x=7000)
        self.add_event(
            30,
            "home",
            MatchEventType.SHOT,
            x=8500,
            shot_outcome=MatchEventShotOutcome.SAVED,
            shot_situation=MatchEventShotSituation.FAST_BREAK,
        )
        replace_match_possessions(self.match)

        response = self.possession_request(state="winning", baseline_state="drawing")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["state_lens"]["selected"]["state"], "winning")
        self.assertEqual(payload["state_lens"]["evidence"]["exposure_seconds"], 80)
        self.assertEqual(payload["counters"]["launches"], 1)
        self.assertEqual(payload["counters"]["evidence"][0]["start_second"], 25)
        self.assertEqual(payload["counters"]["evidence"][0]["match_ref"], 0)
        self.assertEqual(payload["provider_observed"]["count"], 1)
        self.assertTrue(payload["comparison"]["enabled"])
        self.assertEqual(payload["comparison"]["baseline"]["counters"]["launches"], 1)
        self.assertEqual(payload["comparison"]["baseline"]["provider_observed"]["count"], 0)

        age_window = self.possession_request(
            state="winning", minimum_state_age_seconds=8, maximum_state_age_seconds=15
        ).json()
        self.assertEqual(age_window["state_lens"]["evidence"]["exposure_seconds"], 7)
        self.assertEqual(age_window["counters"]["launches"], 0)
        self.assertEqual(age_window["provider_observed"]["count"], 1)

        refined_drawing = self.possession_request(
            state="drawing",
            goal_difference=0,
            phase="first_half",
            draw_provenance="neutral",
        ).json()
        self.assertEqual(refined_drawing["counters"]["launches"], 1)
        self.assertEqual(refined_drawing["provider_observed"]["count"], 0)

    def test_public_payload_scopes_settled_defensive_actions_to_focal_state(self):
        self.add_verified_state()
        self.add_event(1, "away", MatchEventType.PASS)
        self.add_event(5, "away", MatchEventType.PASS)
        self.add_event(10, "away", MatchEventType.BALL_TOUCH)
        self.add_event(11, "home", MatchEventType.CLEARANCE, x=8000)
        self.add_event(21, "away", MatchEventType.PASS)
        self.add_event(25, "away", MatchEventType.PASS)
        self.add_event(30, "away", MatchEventType.BALL_TOUCH)
        self.add_event(31, "home", MatchEventType.CLEARANCE, x=2000)
        replace_match_possessions(self.match)

        drawing = self.possession_request(state="drawing").json()
        winning = self.possession_request(state="winning").json()
        self.assertEqual(drawing["settled_defending"]["defensive_actions"], 1)
        self.assertEqual(drawing["settled_defending"]["block_height_possessions"]["high"], 1)
        self.assertEqual(drawing["settled_defending"]["block_height_possessions"]["low"], 0)
        self.assertEqual(winning["settled_defending"]["defensive_actions"], 1)
        self.assertEqual(winning["settled_defending"]["block_height_possessions"]["high"], 0)
        self.assertEqual(winning["settled_defending"]["block_height_possessions"]["low"], 1)

    def test_public_payload_excludes_unverified_matches_and_composes_match_reference(self):
        self.add_verified_state()
        self.add_event(2, "home", MatchEventType.BALL_RECOVERY, x=3000)
        self.add_event(5, "home", MatchEventType.PASS, x=3000, end_x=7000)
        replace_match_possessions(self.match)
        unverified_match = ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id="112-unverified",
            competition_season=self.cs,
            kickoff_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            status=ProviderMatchStatus.COMPLETED,
            home_provider_team_id="home",
            away_provider_team_id="away",
            home_team=self.home,
            away_team=self.away,
            home_score=0,
            away_score=0,
        )
        self.add_event(2, "home", MatchEventType.BALL_RECOVERY, provider_match=unverified_match)
        self.add_event(5, "home", MatchEventType.PASS, provider_match=unverified_match)
        replace_match_possessions(unverified_match)

        season_payload = self.possession_request().json()
        self.assertEqual(season_payload["counters"]["launches"], 1)
        self.assertEqual(season_payload["state_lens"]["evidence"]["matches_excluded"], 1)
        self.assertEqual(len(season_payload["matches"]), 2)

        excluded_payload = self.possession_request(match=1).json()
        self.assertEqual(excluded_payload["selected_match_ref"], 1)
        self.assertEqual(excluded_payload["counters"]["launches"], 0)
        self.assertEqual(excluded_payload["state_lens"]["evidence"]["exposure_seconds"], 0)
        self.assertEqual(excluded_payload["state_lens"]["evidence"]["matches_excluded"], 1)

    def test_public_payload_rejects_invalid_scopes_and_separates_cached_cohorts(self):
        self.add_verified_state()
        self.add_event(2, "home", MatchEventType.BALL_RECOVERY, x=3000)
        self.add_event(5, "home", MatchEventType.PASS, x=3000, end_x=7000)
        replace_match_possessions(self.match)

        first = self.possession_request(state="drawing")
        repeated = self.possession_request(state="drawing")
        winning = self.possession_request(state="winning")
        self.assertEqual(first["X-Materialized-Payload"], "miss")
        self.assertEqual(repeated["X-Materialized-Payload"], "hit")
        self.assertEqual(winning["X-Materialized-Payload"], "miss")
        self.assertEqual(first.json()["counters"]["launches"], 1)
        self.assertEqual(winning.json()["counters"]["launches"], 0)

        incompatible = self.possession_request(state="winning", goal_difference=-1)
        unavailable_match = self.possession_request(match=9)
        aggregate_scope = self.client.get(
            f"/api/v1/team-seasons/possession-context/{self.home.id}",
            {"competition": "BIG5", "season": "2025-26"},
        )
        self.assertEqual(incompatible.status_code, 400)
        self.assertIn("goal_difference", incompatible.json()["detail"])
        self.assertEqual(unavailable_match.status_code, 400)
        self.assertEqual(aggregate_scope.status_code, 400)
