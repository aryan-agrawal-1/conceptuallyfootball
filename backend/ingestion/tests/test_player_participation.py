from __future__ import annotations

from datetime import datetime, timezone

from django.db import models
from django.test import SimpleTestCase, TestCase

from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    MatchEventGameState,
    MatchEventPeriod,
    Provider,
    ProviderMatch,
    ProviderMatchPlayedPeriod,
    ProviderMatchPlayerInterval,
    ProviderMatchPlayerParticipation,
    ProviderMatchPlayerStateExposure,
    ProviderMatchStatus,
    ProviderMatchTeamGameStateEpisode,
    ProviderPlayerMapping,
    ProviderTeamMapping,
    Season,
)
from ingestion.services.player_participation import (
    materialize_match_player_participation,
    reconstruct_player_intervals,
    split_exposure_by_state_age,
)


def lineup(team_id: str, prefix: str, *, substitutes: int = 1) -> list[dict]:
    return [
        {
            "provider_team_id": team_id,
            "provider_player_id": f"{prefix}-{index}",
            "roster_index": index,
            "roster_role": "starter" if index < 11 else "substitute",
            "position_role": "goalkeeper" if index in {0, 11} else "outfield",
        }
        for index in range(11 + substitutes)
    ]


def event(
    index: int,
    team_id: str,
    player_id: str | None,
    second: int,
    action: str = "none",
    *,
    sequence: str | None = None,
    related_sequence: str | None = None,
    related_player: str | None = None,
    dismissal: str = "none",
) -> dict:
    return {
        "event_index": index,
        "provider_team_id": team_id,
        "provider_player_id": player_id,
        "timeline_seconds": second,
        "participation_action": action,
        "dismissal_type": dismissal,
        "provider_event_sequence_id": sequence,
        "related_provider_event_sequence_id": related_sequence,
        "related_provider_player_id": related_player,
    }


class PlayerIntervalReconstructionTests(SimpleTestCase):
    def test_starter_and_substitute_use_half_open_substitution_boundary(self):
        players = lineup("home", "h") + lineup("away", "a", substitutes=0)
        events = [
            event(
                1,
                "home",
                "h-0",
                3600,
                "substitution_off",
                sequence="10",
                related_sequence="11",
                related_player="h-11",
            ),
            event(
                2,
                "home",
                "h-11",
                3600,
                "substitution_on",
                sequence="11",
                related_sequence="10",
                related_player="h-0",
            ),
        ]

        result = reconstruct_player_intervals(
            lineup_players=players,
            events=events,
            match_start_second=0,
            match_end_second=6000,
            valid_team_ids=("home", "away"),
        )
        by_player = {item.provider_player_id: item for item in result.participants}

        self.assertEqual(result.status, "verified")
        self.assertEqual(
            (
                by_player["h-0"].intervals[0].start_second,
                by_player["h-0"].intervals[0].end_second,
            ),
            (0, 3600),
        )
        self.assertEqual(
            (
                by_player["h-11"].intervals[0].start_second,
                by_player["h-11"].intervals[0].end_second,
            ),
            (3600, 6000),
        )

    def test_unmatched_substitute_is_excluded_without_full_match_fallback(self):
        players = lineup("home", "h") + lineup("away", "a", substitutes=0)
        result = reconstruct_player_intervals(
            lineup_players=players,
            events=[
                event(
                    1,
                    "home",
                    "h-11",
                    5401,
                    "substitution_on",
                    sequence="20",
                )
            ],
            match_start_second=0,
            match_end_second=6000,
            valid_team_ids=("home", "away"),
        )
        substitute = next(
            item for item in result.participants if item.provider_player_id == "h-11"
        )

        self.assertEqual(substitute.status, "excluded")
        self.assertEqual(substitute.exclusion_reason, "unmatched_substitution_event")
        self.assertEqual(substitute.on_pitch_seconds, 599)
        self.assertNotEqual(substitute.on_pitch_seconds, 90 * 60)

    def test_known_dismissal_ends_interval_and_missing_player_excludes_team(self):
        players = lineup("home", "h", substitutes=0) + lineup(
            "away", "a", substitutes=0
        )
        known = reconstruct_player_intervals(
            lineup_players=players,
            events=[event(1, "home", "h-3", 4200, dismissal="red")],
            match_start_second=0,
            match_end_second=6000,
            valid_team_ids=("home", "away"),
        )
        dismissed = next(
            item for item in known.participants if item.provider_player_id == "h-3"
        )
        self.assertEqual(dismissed.intervals[0].end_second, 4200)
        self.assertEqual(dismissed.intervals[0].end_evidence, "dismissal_red")

        unknown = reconstruct_player_intervals(
            lineup_players=players,
            events=[event(1, "home", None, 4200, dismissal="red")],
            match_start_second=0,
            match_end_second=6000,
            valid_team_ids=("home", "away"),
        )
        home_players = [
            item for item in unknown.participants if item.provider_team_id == "home"
        ]
        self.assertTrue(all(item.status == "excluded" for item in home_players))
        self.assertTrue(
            all(
                item.exclusion_reason == "dismissal_player_missing"
                for item in home_players
            )
        )

    def test_goalkeeper_substitution_in_extra_time_uses_supported_match_end(self):
        players = lineup("home", "h") + lineup("away", "a", substitutes=0)
        result = reconstruct_player_intervals(
            lineup_players=players,
            events=[
                event(
                    1,
                    "home",
                    "h-0",
                    7200,
                    "substitution_off",
                    sequence="30",
                    related_sequence="31",
                ),
                event(
                    2,
                    "home",
                    "h-11",
                    7200,
                    "substitution_on",
                    sequence="31",
                    related_sequence="30",
                ),
            ],
            match_start_second=0,
            match_end_second=7500,
            valid_team_ids=("home", "away"),
        )
        substitute = next(
            item for item in result.participants if item.provider_player_id == "h-11"
        )

        self.assertEqual(substitute.position_role, "goalkeeper")
        self.assertEqual(substitute.on_pitch_seconds, 300)
        self.assertEqual(substitute.intervals[0].end_second, 7500)

    def test_deleted_dismissal_is_cancelled_and_duplicate_substitution_is_collapsed(
        self,
    ):
        players = lineup("home", "h") + lineup("away", "a", substitutes=0)
        deleted_card = event(
            1,
            "home",
            "h-3",
            1800,
            sequence="50",
            dismissal="red",
        )
        correction = event(2, "home", None, 1801, sequence="51") | {
            "related_provider_event_sequence_id": "50",
            "is_deleted_event": True,
        }
        off = event(
            3,
            "home",
            "h-0",
            3600,
            "substitution_off",
            sequence="60",
            related_sequence="61",
        )
        duplicate_off = off | {"event_index": 4}
        on = event(
            5,
            "home",
            "h-11",
            3600,
            "substitution_on",
            sequence="61",
            related_sequence="60",
        )
        result = reconstruct_player_intervals(
            lineup_players=players,
            events=[deleted_card, correction, off, duplicate_off, on],
            match_start_second=0,
            match_end_second=6000,
            valid_team_ids=("home", "away"),
        )
        by_player = {item.provider_player_id: item for item in result.participants}

        self.assertEqual(by_player["h-3"].on_pitch_seconds, 6000)
        self.assertEqual(by_player["h-0"].status, "verified")
        self.assertIn(
            "duplicate_participation_event",
            {warning["code"] for warning in result.diagnostics["warnings"]},
        )

    def test_event_sequence_ids_are_scoped_to_the_team(self):
        players = lineup("home", "h") + lineup("away", "a")
        events = [
            event(
                1,
                "home",
                "h-0",
                3000,
                "substitution_off",
                sequence="10",
                related_sequence="11",
            ),
            event(
                2,
                "home",
                "h-11",
                3000,
                "substitution_on",
                sequence="11",
                related_sequence="10",
            ),
            event(
                3,
                "away",
                "a-0",
                3600,
                "substitution_off",
                sequence="10",
                related_sequence="11",
            ),
            event(
                4,
                "away",
                "a-11",
                3600,
                "substitution_on",
                sequence="11",
                related_sequence="10",
            ),
        ]

        result = reconstruct_player_intervals(
            lineup_players=players,
            events=events,
            match_start_second=0,
            match_end_second=6000,
            valid_team_ids=("home", "away"),
        )

        self.assertEqual(result.status, "verified")
        self.assertFalse(
            any(
                player.exclusion_reason == "conflicting_event_sequence_id"
                for player in result.participants
            )
        )

    def test_state_age_intersection_splits_at_public_boundaries(self):
        segments = split_exposure_by_state_age(
            start_second=200,
            end_second=1200,
            episode_start_second=0,
            episode_state_age_at_start=0,
        )

        self.assertEqual(
            segments,
            [
                (200, 300, 200, 300, "0_5_minutes"),
                (300, 900, 300, 900, "5_15_minutes"),
                (900, 1200, 900, 1200, "15_plus_minutes"),
            ],
        )


class PlayerParticipationMaterializationTests(TestCase):
    def setUp(self):
        competition = Competition.objects.create(
            name="Test League", short_code="TST", country="Test"
        )
        season = Season.objects.create(label="2025-26", sort_order=2026)
        self.competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
            has_whoscored=True,
            whoscored_league="test-league",
            whoscored_season="2526",
            whoscored_expected_match_count=1,
        )
        self.home = CanonicalTeam.objects.create(name="Home")
        self.away = CanonicalTeam.objects.create(name="Away")
        self.match = ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id="state-exposure-match",
            competition_season=self.competition_season,
            kickoff_at=datetime(2026, 5, 1, 15, 0, tzinfo=timezone.utc),
            status=ProviderMatchStatus.COMPLETED,
            home_provider_team_id="home",
            away_provider_team_id="away",
            home_team=self.home,
            away_team=self.away,
            home_score=2,
            away_score=1,
        )
        ProviderTeamMapping.objects.create(
            provider=Provider.WHOSCORED,
            provider_team_id="home",
            canonical_team=self.home,
        )
        ProviderTeamMapping.objects.create(
            provider=Provider.WHOSCORED,
            provider_team_id="away",
            canonical_team=self.away,
        )
        self.lineup = lineup("home", "h") + lineup("away", "a", substitutes=0)
        self.players = {}
        for item in self.lineup:
            player = CanonicalPlayer.objects.create(
                display_name=item["provider_player_id"]
            )
            self.players[item["provider_player_id"]] = player
            ProviderPlayerMapping.objects.create(
                provider=Provider.WHOSCORED,
                provider_player_id=item["provider_player_id"],
                canonical_player=player,
            )
        ProviderMatchPlayedPeriod.objects.create(
            provider_match=self.match,
            period=MatchEventPeriod.FIRST_HALF,
            period_index=0,
            start_second=0,
            end_second=3000,
            duration_seconds=3000,
            calculation_version="clock-test-v1",
        )
        ProviderMatchPlayedPeriod.objects.create(
            provider_match=self.match,
            period=MatchEventPeriod.SECOND_HALF,
            period_index=1,
            start_second=3000,
            end_second=6000,
            duration_seconds=3000,
            calculation_version="clock-test-v1",
        )
        self.add_episode(0, 0, 1200, MatchEventGameState.DRAWING, 0, "neutral")
        self.add_episode(1, 1200, 2400, MatchEventGameState.WINNING, 1, "none")
        self.add_episode(2, 2400, 4800, MatchEventGameState.DRAWING, 0, "surrendered")
        self.add_episode(3, 4800, 6000, MatchEventGameState.LOSING, -1, "none")

    def add_episode(self, index, start, end, state, difference, provenance):
        ProviderMatchTeamGameStateEpisode.objects.create(
            provider_match=self.match,
            focal_team=self.home,
            focal_is_home=True,
            episode_index=index,
            period=(
                MatchEventPeriod.FIRST_HALF
                if start < 3000
                else MatchEventPeriod.SECOND_HALF
            ),
            phase="first_half" if start < 3000 else "second_half",
            start_second=start,
            end_second=end,
            duration_seconds=end - start,
            focal_score=max(difference, 0),
            opponent_score=max(-difference, 0),
            goal_difference=difference,
            state=state,
            previous_state=None,
            draw_provenance=provenance,
            state_entry_second=start,
            state_age_seconds_at_start=0,
            calculation_version="episodes-test-v1",
        )

    def test_intersections_exclude_goals_before_entry_and_after_withdrawal(self):
        events = [
            event(
                1,
                "home",
                "h-0",
                3600,
                "substitution_off",
                sequence="10",
                related_sequence="11",
                related_player="h-11",
            ),
            event(
                2,
                "home",
                "h-11",
                3600,
                "substitution_on",
                sequence="11",
                related_sequence="10",
                related_player="h-0",
            ),
        ]
        materialize_match_player_participation(
            self.match,
            lineup_players=self.lineup,
            events=events,
        )
        withdrawn = ProviderMatchPlayerParticipation.objects.get(
            provider_match=self.match,
            provider_player_id="h-0",
        )
        substitute = ProviderMatchPlayerParticipation.objects.get(
            provider_match=self.match,
            provider_player_id="h-11",
        )

        self.assertEqual(withdrawn.on_pitch_seconds, 3600)
        self.assertEqual(substitute.on_pitch_seconds, 2400)
        withdrawn_states = set(
            ProviderMatchPlayerStateExposure.objects.filter(
                player_interval__participation=withdrawn
            ).values_list("coarse_state", flat=True)
        )
        substitute_states = set(
            ProviderMatchPlayerStateExposure.objects.filter(
                player_interval__participation=substitute
            ).values_list("coarse_state", flat=True)
        )
        self.assertNotIn(MatchEventGameState.LOSING, withdrawn_states)
        self.assertNotIn(MatchEventGameState.WINNING, substitute_states)
        self.assertEqual(
            ProviderMatchPlayerStateExposure.objects.filter(
                player_interval__participation=withdrawn
            ).aggregate(total=models.Sum("duration_seconds"))["total"],
            3600,
        )
        self.assertEqual(
            ProviderMatchPlayerStateExposure.objects.filter(
                player_interval__participation=substitute
            ).aggregate(total=models.Sum("duration_seconds"))["total"],
            2400,
        )

    def test_rebuild_is_deterministic_for_derived_content(self):
        first = materialize_match_player_participation(
            self.match,
            lineup_players=self.lineup,
            events=[],
        )
        first_values = list(
            ProviderMatchPlayerInterval.objects.filter(participation__build=first)
            .order_by("participation__provider_player_id", "sequence")
            .values(
                "participation__provider_player_id",
                "start_second",
                "end_second",
                "start_evidence",
                "end_evidence",
                "confidence",
            )
        )

        second = materialize_match_player_participation(
            self.match,
            lineup_players=self.lineup,
            events=[],
        )
        second_values = list(
            ProviderMatchPlayerInterval.objects.filter(participation__build=second)
            .order_by("participation__provider_player_id", "sequence")
            .values(
                "participation__provider_player_id",
                "start_second",
                "end_second",
                "start_evidence",
                "end_evidence",
                "confidence",
            )
        )
        self.assertEqual(first_values, second_values)
