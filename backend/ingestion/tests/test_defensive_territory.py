from datetime import datetime, timezone

from django.test import TestCase

from ingestion.models import (
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    MatchEventGameState,
    MatchEventPeriod,
    MatchEventType,
    MatchGameStateStatus,
    MatchStateDrawProvenance,
    MatchStatePhase,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchStatus,
    ProviderMatchTeamGameStateEpisode,
    Season,
)
from ingestion.services.event_profiles import materialize_event_profiles


class DefensiveTerritoryApiTests(TestCase):
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
        cls.focal = CanonicalTeam.objects.create(name="Focal")
        cls.opponent = CanonicalTeam.objects.create(name="Opponent")
        cls.home_match = cls.create_match("home", True, datetime(2026, 1, 1, tzinfo=timezone.utc))
        cls.away_match = cls.create_match("away", False, datetime(2026, 1, 8, tzinfo=timezone.utc))

        cls.add_event(cls.home_match, 1, 599, MatchEventType.BALL_RECOVERY, 2000, 2000)
        cls.add_event(cls.home_match, 2, 600, MatchEventType.CLEARANCE, 1000, 3000)
        cls.add_event(cls.home_match, 3, 700, MatchEventType.AERIAL, 7000, 4000, is_defensive=True)
        cls.add_event(cls.home_match, 4, 800, MatchEventType.AERIAL, 9000, 5000)
        cls.add_event(cls.home_match, 5, 900, MatchEventType.TACKLE, 4000, None)
        cls.add_event(cls.home_match, 6, 1000, MatchEventType.BLOCKED_PASS, 5000, 6000)
        cls.add_event(cls.away_match, 1, 300, MatchEventType.BALL_RECOVERY, 2000, 8000)

        run = IngestionRun.objects.create(
            kind=IngestionKind.EVENT_PROFILES,
            competition_season=cls.competition_season,
        )
        assert materialize_event_profiles(cls.competition_season, run=run) is not None
        cls.add_state(cls.home_match, True, split=True)
        cls.add_state(cls.away_match, False, split=False)

    @classmethod
    def create_match(cls, suffix, focal_home, kickoff):
        return ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id=f"defensive-{suffix}",
            competition_season=cls.competition_season,
            kickoff_at=kickoff,
            status=ProviderMatchStatus.COMPLETED,
            home_provider_team_id="focal" if focal_home else "opponent",
            away_provider_team_id="opponent" if focal_home else "focal",
            home_team=cls.focal if focal_home else cls.opponent,
            away_team=cls.opponent if focal_home else cls.focal,
            home_score=1 if focal_home else 0,
            away_score=0 if focal_home else 0,
        )

    @classmethod
    def add_event(cls, match, index, second, event_type, x, y, **values):
        return ProviderMatchEvent.objects.create(
            provider_match=match,
            event_index=index,
            provider_team_id="focal",
            team=cls.focal,
            period=MatchEventPeriod.FIRST_HALF,
            minute=second // 60,
            second=second % 60,
            match_seconds=second,
            timeline_seconds=second,
            event_type=event_type,
            x=x,
            y=y,
            **values,
        )

    @classmethod
    def add_state(cls, match, focal_home, split):
        ProviderMatchGameState.objects.create(
            provider_match=match,
            status=MatchGameStateStatus.VERIFIED,
            eligible=True,
            calculation_version="team_game_state_v1",
            exposure_seconds=1200,
            episode_count=2 if split else 1,
            focal_team_count=2,
            calculated_at=datetime.now(timezone.utc),
        )
        episodes = [
            (0, 0, 600 if split else 1200, MatchEventGameState.DRAWING, 0, MatchStateDrawProvenance.NEUTRAL),
        ]
        if split:
            episodes.append((1, 600, 1200, MatchEventGameState.WINNING, 1, MatchStateDrawProvenance.NONE))
        for index, start, end, state, difference, provenance in episodes:
            ProviderMatchTeamGameStateEpisode.objects.create(
                provider_match=match,
                focal_team=cls.focal,
                focal_is_home=focal_home,
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
                state_entry_second=start,
                state_age_seconds_at_start=0,
                calculation_version="team_game_state_v1",
            )

    @property
    def url(self):
        return f"/api/v1/team-seasons/event-profile/{self.focal.id}/defensive-territory"

    @property
    def scope(self):
        return {"competition": "TST", "season": "2025-26"}

    def test_contract_inclusion_orientation_clearances_and_missing_locations(self):
        response = self.client.get(self.url, self.scope)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        evidence = payload["selected"]
        self.assertEqual(evidence["counts"], {
            "included": 6,
            "with_location": 5,
            "without_location": 1,
            "non_clearance": 5,
            "clearance": 1,
            "recovery": 2,
        })
        self.assertEqual(evidence["heights"]["recovery"]["median"], 20.0)
        self.assertEqual(evidence["heights"]["clearance"]["median"], 10.0)
        self.assertEqual(evidence["heights"]["non_clearance_action"]["median"], 35.0)
        self.assertTrue(evidence["orientation"]["home_away_invariant"])
        self.assertEqual(len(evidence["grid"]["cells"]), 96)
        self.assertEqual(
            sum(cell["all"]["count"] for cell in evidence["grid"]["cells"]), 5
        )
        self.assertEqual(
            sum(
                cell["families"]["recovery"]["count"]
                for cell in evidence["grid"]["cells"]
            ),
            2,
        )
        self.assertEqual(
            sum(
                cell["families"]["tackle"]["count"]
                for cell in evidence["grid"]["cells"]
            ),
            0,
        )
        self.assertEqual(evidence["family_evidence"]["recovery"]["height"]["mean"], 20.0)
        self.assertEqual(evidence["family_evidence"]["clearance"]["rate_per_state_minute"], 0.025)
        self.assertEqual(
            evidence["evidence"]["exclusions"]["attacking_or_unqualified_aerial_challenge"], 1
        )
        self.assertTrue(evidence["evidence"]["sparse"])
        self.assertIn("not proof", evidence["disclaimer"])
        self.assertNotIn("block_height", str(payload))

    def test_state_boundary_rates_comparison_and_cached_materialization(self):
        params = {
            **self.scope,
            "state": "winning",
            "baseline_state": "drawing",
        }
        first = self.client.get(self.url, params)
        second = self.client.get(self.url, params)

        self.assertEqual(first.status_code, 200)
        payload = first.json()
        self.assertEqual(payload["state_lens"]["evidence"]["exposure_seconds"], 600)
        self.assertEqual(payload["selected"]["counts"]["included"], 4)
        self.assertEqual(payload["selected"]["counts"]["clearance"], 1)
        self.assertEqual(payload["selected"]["rates_per_state_minute"]["all"], 0.4)
        self.assertEqual(payload["baseline"]["counts"]["included"], 2)
        self.assertEqual(payload["baseline"]["heights"]["recovery"]["median"], 20.0)
        self.assertEqual(first["X-Materialized-Payload"], "miss")
        self.assertEqual(second["X-Materialized-Payload"], "hit")

        winning_episode = ProviderMatchTeamGameStateEpisode.objects.get(
            provider_match=self.home_match,
            focal_team=self.focal,
            episode_index=1,
        )
        winning_episode.end_second = 1100
        winning_episode.duration_seconds = 500
        winning_episode.delete()
        winning_episode.pk = None
        winning_episode.save(force_insert=True)
        rebuilt = self.client.get(self.url, params)
        self.assertEqual(rebuilt["X-Materialized-Payload"], "miss")
        self.assertEqual(rebuilt.json()["state_lens"]["evidence"]["exposure_seconds"], 500)

    def test_match_filter_and_state_lens_validation(self):
        away = self.client.get(self.url, {**self.scope, "match": 1})
        self.assertEqual(away.status_code, 200)
        self.assertEqual(away.json()["selected"]["heights"]["recovery"]["median"], 20.0)

        invalid = self.client.get(self.url, {**self.scope, "state": "winning", "goal_difference": -1})
        self.assertEqual(invalid.status_code, 400)
