from datetime import datetime, timezone

from django.test import TestCase
from rest_framework.test import APIClient

from ingestion.event_profile_api import PASS_RESPONSE_LIMIT
from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    MaterializedApiPayload,
    MatchEventShotOutcome,
    MatchEventType,
    PlayerSeasonDerivedStats,
    PlayerSeasonEventProfile,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchStatus,
    Season,
    TeamSeasonEventProfile,
)
from ingestion.services.event_profiles import materialize_event_profiles


class EventProfileApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        competition = Competition.objects.create(name="Test League", short_code="TST")
        season = Season.objects.create(label="2025-26", sort_order=2026)
        self.competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
            has_whoscored=True,
            whoscored_league="test-league",
            whoscored_season="2025-2026",
            whoscored_expected_match_count=1,
            expected_team_count=2,
            is_published=True,
        )
        self.home = CanonicalTeam.objects.create(name="Home")
        self.away = CanonicalTeam.objects.create(name="Away")
        self.player = CanonicalPlayer.objects.create(display_name="Profile Player")
        self.opponent = CanonicalPlayer.objects.create(display_name="Opponent Player")
        PlayerSeasonDerivedStats.objects.create(
            competition_season=self.competition_season,
            canonical_player=self.player,
            canonical_display_team=self.home,
            minutes=90,
        )
        self.match = ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id="provider-match-1",
            competition_season=self.competition_season,
            kickoff_at=datetime(2026, 1, 2, 15, 0, tzinfo=timezone.utc),
            status=ProviderMatchStatus.COMPLETED,
            home_provider_team_id="home-provider-id",
            away_provider_team_id="away-provider-id",
            home_team=self.home,
            away_team=self.away,
            home_score=2,
            away_score=1,
        )
        self.add_event(
            1,
            outcome_successful=True,
            is_touch=True,
            is_progressive_pass=True,
            is_final_third_entry=True,
            is_box_entry=True,
            is_key_pass=True,
            is_cross=True,
            is_long_ball=True,
        )
        self.add_event(2, outcome_successful=False, x=3000, y=4000, end_x=5000, end_y=6000)
        self.add_event(
            3,
            event_type=MatchEventType.SHOT,
            x=9000,
            y=4500,
            end_x=None,
            end_y=None,
            shot_outcome=MatchEventShotOutcome.GOAL,
            is_big_chance=True,
        )
        self.add_event(
            4,
            team=self.away,
            player=self.opponent,
            event_type=MatchEventType.SHOT,
            x=8500,
            y=5000,
            end_x=None,
            end_y=None,
            shot_outcome=MatchEventShotOutcome.SAVED,
        )
        run = IngestionRun.objects.create(
            kind=IngestionKind.EVENT_PROFILES,
            competition_season=self.competition_season,
        )
        self.assertIsNotNone(materialize_event_profiles(self.competition_season, run=run))

    def add_event(self, index, *, team=None, player=None, **values):
        event_team = team or self.home
        event_player = player or self.player
        defaults = {
            "provider_match": self.match,
            "event_index": index,
            "provider_team_id": str(event_team.id),
            "team": event_team,
            "provider_player_id": str(event_player.id),
            "player": event_player,
            "minute": 20,
            "second": index % 60,
            "match_seconds": 1200 + index,
            "event_type": MatchEventType.PASS,
            "x": 1000,
            "y": 2000,
            "end_x": 8000,
            "end_y": 7000,
        }
        defaults.update(values)
        return ProviderMatchEvent.objects.create(**defaults)

    @property
    def player_url(self):
        return f"/api/v1/player-seasons/event-profile/{self.player.id}"

    @property
    def passes_url(self):
        return f"{self.player_url}/passes"

    @property
    def team_url(self):
        return f"/api/v1/team-seasons/event-profile/{self.home.id}"

    @property
    def scope(self):
        return {"competition": "TST", "season": "2025-26"}

    def test_player_main_response_has_contract_and_no_pass_lines(self):
        response = self.client.get(self.player_url, self.scope)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["canonical_player_name"], "Profile Player")
        self.assertIsNone(payload["canonical_team_id"])
        self.assertEqual(payload["coverage"]["observed_matches"], 1)
        self.assertEqual(payload["availability"]["pass_map"], {"available": True, "sparse": True})
        self.assertEqual(payload["average_touch_location"]["sample_size"], 1)
        self.assertEqual(len(payload["action_grid"]), 96)
        self.assertEqual(len(payload["shots"]), 1)
        self.assertEqual(payload["shots"][0]["match_ref"], 0)
        self.assertEqual(payload["matches"][0]["ref"], 0)
        self.assertNotIn("passes", payload)
        self.assertNotIn("pass_rows", payload)

    def test_player_team_split_and_missing_split(self):
        response = self.client.get(self.player_url, {**self.scope, "team": self.home.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["split_type"], "team")
        self.assertEqual(response.json()["canonical_team_name"], "Home")

        missing = self.client.get(self.player_url, {**self.scope, "team": self.away.id})
        self.assertEqual(missing.status_code, 404)

    def test_scope_profile_and_derived_prerequisites(self):
        for competition in ("BIG5", "ALL"):
            with self.subTest(competition=competition):
                response = self.client.get(
                    self.player_url,
                    {"competition": competition, "season": "2025-26"},
                )
                self.assertEqual(response.status_code, 400)

        self.assertEqual(self.client.get(self.player_url).status_code, 400)

        PlayerSeasonEventProfile.objects.filter(player=self.player, is_current=True).update(is_current=False)
        self.assertEqual(self.client.get(self.player_url, self.scope).status_code, 404)
        PlayerSeasonEventProfile.objects.update(is_current=True)

        PlayerSeasonDerivedStats.objects.filter(canonical_player=self.player).update(is_current=False)
        self.assertEqual(self.client.get(self.player_url, self.scope).status_code, 404)

    def test_every_pass_filter_and_compact_match_references(self):
        expected_counts = {
            "completed": 1,
            "progressive": 1,
            "final_third_entry": 1,
            "box_entry": 1,
            "key_pass": 1,
            "cross": 1,
            "long_ball": 1,
            "failed": 1,
        }
        for pass_filter, expected in expected_counts.items():
            with self.subTest(pass_filter=pass_filter):
                response = self.client.get(
                    self.passes_url,
                    {**self.scope, "filter": pass_filter},
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["filter"], pass_filter)
                self.assertEqual(payload["total_matching_count"], expected)
                self.assertEqual(len(payload["passes"]), expected)
                self.assertEqual(payload["passes"][0]["match_ref"], payload["matches"][0]["ref"])
                self.assertNotIn("provider_match_id", str(payload))

        invalid = self.client.get(self.passes_url, {**self.scope, "filter": "sampled"})
        self.assertEqual(invalid.status_code, 400)

    def test_pass_response_cap_reports_total_and_never_samples(self):
        existing = ProviderMatchEvent.objects.count()
        events = []
        for offset in range(PASS_RESPONSE_LIMIT + 1):
            index = existing + offset + 100
            events.append(
                ProviderMatchEvent(
                    provider_match=self.match,
                    event_index=index,
                    provider_team_id=str(self.home.id),
                    team=self.home,
                    provider_player_id=str(self.player.id),
                    player=self.player,
                    minute=30,
                    second=index % 60,
                    match_seconds=1800 + index,
                    event_type=MatchEventType.PASS,
                    outcome_successful=False,
                    x=1000,
                    y=2000,
                    end_x=3000,
                    end_y=4000,
                )
            )
        ProviderMatchEvent.objects.bulk_create(events)

        response = self.client.get(self.passes_url, {**self.scope, "filter": "failed"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_matching_count"], PASS_RESPONSE_LIMIT + 2)
        self.assertEqual(len(payload["passes"]), PASS_RESPONSE_LIMIT)
        self.assertTrue(payload["truncated"])
        self.assertEqual(
            [row["event_index"] for row in payload["passes"]],
            sorted(row["event_index"] for row in payload["passes"]),
        )

    def test_team_response_contains_complete_matrices_and_shots(self):
        response = self.client.get(self.team_url, self.scope)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["canonical_team_name"], "Home")
        self.assertEqual(len(payload["pass_flow"]), 225)
        self.assertEqual(len(payload["action_grid"]), 96)
        self.assertEqual(len(payload["opponent_action_grid"]), 96)
        self.assertEqual(len(payload["shots_for"]), 1)
        self.assertEqual(len(payload["shots_against"]), 1)
        self.assertEqual(payload["shots_for"][0]["match_ref"], 0)
        self.assertEqual(payload["shots_against"][0]["match_ref"], 0)

    def test_cache_hits_are_stable_and_profile_version_invalidates(self):
        first = self.client.get(self.player_url, self.scope)
        second = self.client.get(self.player_url, self.scope)
        self.assertEqual(first.content, second.content)
        self.assertEqual(first["ETag"], second["ETag"])
        self.assertEqual(
            MaterializedApiPayload.objects.filter(
                cache_key__startswith=f"event-profile:{self.competition_season.id}:player:"
            ).count(),
            1,
        )

        profile = PlayerSeasonEventProfile.objects.get(
            competition_season=self.competition_season,
            player=self.player,
            team__isnull=True,
            is_current=True,
        )
        profile.formula_version = "event_profiles_v2"
        profile.save(update_fields=["formula_version"])
        third = self.client.get(self.player_url, self.scope)
        self.assertEqual(third.status_code, 200)
        self.assertNotEqual(first["ETag"], third["ETag"])
        cached = MaterializedApiPayload.objects.filter(
            cache_key__startswith=f"event-profile:{self.competition_season.id}:player:"
        ).order_by("-id").first()
        self.assertIsNotNone(cached)
        self.assertIn("event_profiles_v2", cached.source_version)

    def test_public_json_excludes_raw_payload_and_provider_fields(self):
        forbidden = (
            "payload_gzip",
            "object_key",
            "payload_sha256",
            "checksum",
            "commentary",
            "qualifiers",
            "provider_match_id",
            "provider_player_id",
            "provider_team_id",
        )
        for url, query in (
            (self.player_url, self.scope),
            (self.passes_url, self.scope),
            (self.team_url, self.scope),
        ):
            with self.subTest(url=url):
                response = self.client.get(url, query)
                self.assertEqual(response.status_code, 200)
                rendered = response.content.decode("utf-8")
                for field in forbidden:
                    self.assertNotIn(field, rendered)
