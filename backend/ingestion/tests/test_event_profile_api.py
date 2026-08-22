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
    MergedTeamSeason,
    PlayerSeasonDerivedStats,
    PlayerSeasonEventProfile,
    PlayerSeasonGkDerivedStats,
    Provider,
    ProviderMatch,
    ProviderMatchCarry,
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
            whoscored_expected_match_count=380,
            expected_team_count=20,
            refresh_enabled=True,
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
        MergedTeamSeason.objects.create(
            competition_season=self.competition_season,
            canonical_team=self.home,
            matches=1,
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
            "provider_match": values.pop("provider_match", self.match),
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
        self.assertEqual(payload["coverage"]["expected_matches"], 38)
        self.assertEqual(payload["availability"]["pass_map"], {"available": True, "sparse": True})
        self.assertEqual(payload["average_touch_location"]["sample_size"], 1)
        self.assertEqual(payload["average_touch_location"]["x"], 10.0)
        self.assertEqual(payload["average_touch_location"]["y"], 20.0)
        self.assertEqual(len(payload["action_grid"]), 384)
        self.assertEqual(payload["touch_grid"], payload["action_grid"])
        self.assertEqual(sum(cell["raw_count"] for cell in payload["touch_grid"]), 1)
        self.assertEqual(len(payload["shots"]), 1)
        self.assertEqual(payload["shots"][0]["match_ref"], 0)
        self.assertEqual(payload["shots"][0]["team_id"], self.home.id)
        self.assertEqual(payload["shots"][0]["x"], 90.0)
        self.assertEqual(payload["shots"][0]["y"], 45.0)
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
            "all": 2,
            "progressive": 1,
            "final_third_entry": 1,
            "box_entry": 1,
            "key_pass": 1,
            "cross": 1,
            "long_ball": 1,
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
                self.assertEqual(payload["passes"][0]["team_id"], self.home.id)
                self.assertLessEqual(payload["passes"][0]["x"], 100)
                self.assertLessEqual(payload["passes"][0]["end_x"], 100)
                self.assertNotIn("provider_match_id", str(payload))

        completed_progressive = self.client.get(
            self.passes_url,
            {**self.scope, "filter": "progressive", "outcome": "completed"},
        )
        self.assertEqual(completed_progressive.status_code, 200)
        self.assertEqual(completed_progressive.json()["filter"], "progressive")
        self.assertEqual(completed_progressive.json()["outcome"], "completed")
        self.assertEqual(completed_progressive.json()["total_matching_count"], 1)

        incomplete = self.client.get(
            self.passes_url,
            {**self.scope, "filter": "all", "outcome": "incomplete"},
        )
        self.assertEqual(incomplete.status_code, 200)
        self.assertEqual(incomplete.json()["total_matching_count"], 1)

        legacy_failed = self.client.get(self.passes_url, {**self.scope, "filter": "failed"})
        self.assertEqual(legacy_failed.status_code, 200)
        self.assertEqual(legacy_failed.json()["filter"], "all")
        self.assertEqual(legacy_failed.json()["outcome"], "incomplete")

        invalid = self.client.get(self.passes_url, {**self.scope, "filter": "sampled"})
        self.assertEqual(invalid.status_code, 400)
        invalid_outcome = self.client.get(
            self.passes_url,
            {**self.scope, "outcome": "sometimes"},
        )
        self.assertEqual(invalid_outcome.status_code, 400)

    def test_match_filter_scopes_every_event_map_and_keeps_season_match_options(self):
        second_match = ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id="provider-match-2",
            competition_season=self.competition_season,
            kickoff_at=datetime(2026, 1, 9, 15, 0, tzinfo=timezone.utc),
            status=ProviderMatchStatus.COMPLETED,
            home_provider_team_id="home-provider-id",
            away_provider_team_id="away-provider-id",
            home_team=self.home,
            away_team=self.away,
            home_score=1,
            away_score=0,
        )
        self.add_event(
            1,
            provider_match=second_match,
            outcome_successful=True,
            is_touch=True,
            is_progressive_pass=True,
            x=2500,
            y=3500,
        )
        self.add_event(
            2,
            provider_match=second_match,
            event_type=MatchEventType.SHOT,
            x=9200,
            y=4800,
            end_x=None,
            end_y=None,
            shot_outcome=MatchEventShotOutcome.SAVED,
        )
        for provider_match, start_event_index in ((self.match, 20), (second_match, 30)):
            ProviderMatchCarry.objects.create(
                provider_match=provider_match,
                start_event_index=start_event_index,
                end_event_index=start_event_index + 1,
                provider_team_id=str(self.home.id),
                team=self.home,
                provider_player_id=str(self.player.id),
                player=self.player,
                minute=25,
                second=0,
                match_seconds=1500,
                x=2000,
                y=3000,
                end_x=2600,
                end_y=3400,
                is_progressive_carry=True,
                is_final_third_entry=True,
                is_box_entry=True,
                is_low_confidence=True,
            )
        run = IngestionRun.objects.create(
            kind=IngestionKind.EVENT_PROFILES,
            competition_season=self.competition_season,
        )
        self.assertIsNotNone(materialize_event_profiles(self.competition_season, run=run))

        player = self.client.get(self.player_url, {**self.scope, "match": 1}).json()
        self.assertEqual(len(player["matches"]), 2)
        self.assertEqual(player["selected_match_ref"], 1)
        self.assertEqual(player["summary"]["pass_attempts"], 1)
        self.assertEqual(player["summary"]["shots"], 1)
        self.assertEqual(sum(cell["raw_count"] for cell in player["touch_grid"]), 1)
        self.assertEqual({shot["match_ref"] for shot in player["shots"]}, {1})

        passes = self.client.get(
            self.passes_url,
            {**self.scope, "match": 1, "filter": "progressive", "outcome": "completed"},
        ).json()
        self.assertEqual(len(passes["matches"]), 2)
        self.assertEqual(passes["total_matching_count"], 1)
        self.assertEqual({row["match_ref"] for row in passes["passes"]}, {1})
        self.assertEqual(passes["total_carry_count"], 1)
        self.assertEqual(passes["total_all_carry_count"], 1)
        self.assertFalse(passes["carries_truncated"])
        self.assertEqual({row["match_ref"] for row in passes["carries"]}, {1})
        self.assertTrue(passes["carries"][0]["progressive"])
        self.assertTrue(passes["carries"][0]["final_third_entry"])
        self.assertTrue(passes["carries"][0]["box_entry"])
        self.assertTrue(passes["carries"][0]["low_confidence"])

        pass_only_filter = self.client.get(
            self.passes_url,
            {**self.scope, "match": 1, "filter": "key_pass"},
        ).json()
        self.assertEqual(pass_only_filter["total_carry_count"], 0)
        self.assertEqual(pass_only_filter["total_all_carry_count"], 1)
        self.assertEqual(pass_only_filter["carries"], [])

        team = self.client.get(self.team_url, {**self.scope, "match": 1}).json()
        self.assertEqual(len(team["matches"]), 2)
        self.assertEqual(team["summary"]["pass_attempts"], 1)
        self.assertEqual(team["summary"]["shots_for"], 1)
        self.assertEqual(team["summary"]["shots_against"], 0)
        self.assertEqual(team["pass_flow"][0]["completed_count"], 1)
        self.assertEqual(sum(cell["raw_count"] for cell in team["touch_grid"]), 1)

        self.assertEqual(
            self.client.get(self.player_url, {**self.scope, "match": 99}).status_code,
            400,
        )

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
        self.assertEqual(len(payload["pass_flow"]), 1)
        self.assertEqual(payload["pass_flow"][0]["completed_count"], 1)
        self.assertEqual(payload["pass_flow"][0]["column"], 0)
        self.assertEqual(payload["pass_flow"][0]["row"], 0)
        self.assertEqual(payload["pass_flow"][0]["mean_origin_x"], 10.0)
        self.assertEqual(payload["pass_flow"][0]["mean_destination_x"], 80.0)
        self.assertEqual(len(payload["action_grid"]), 384)
        self.assertEqual(len(payload["opponent_action_grid"]), 384)
        self.assertEqual(payload["touch_grid"], payload["action_grid"])
        self.assertEqual(payload["opponent_touch_grid"], payload["opponent_action_grid"])
        self.assertEqual(len(payload["shots_for"]), 1)
        self.assertEqual(len(payload["shots_against"]), 1)
        self.assertEqual(payload["shots_for"][0]["match_ref"], 0)
        self.assertEqual(payload["shots_against"][0]["match_ref"], 0)
        self.assertEqual(payload["shots_for"][0]["team_id"], self.home.id)
        self.assertEqual(payload["shots_against"][0]["team_id"], self.away.id)

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
        profile.formula_version = "event_profiles_v4"
        profile.save(update_fields=["formula_version"])
        third = self.client.get(self.player_url, self.scope)
        self.assertEqual(third.status_code, 200)
        self.assertNotEqual(first["ETag"], third["ETag"])
        cached = MaterializedApiPayload.objects.filter(
            cache_key__startswith=f"event-profile:{self.competition_season.id}:player:"
        ).order_by("-id").first()
        self.assertIsNotNone(cached)
        self.assertIn("event_profiles_v4", cached.source_version)

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

    def test_existing_detail_endpoints_expose_only_lightweight_flags(self):
        PlayerSeasonGkDerivedStats.objects.create(
            competition_season=self.competition_season,
            canonical_player=self.player,
            canonical_display_team=self.home,
            formula_version="gk-test",
            minutes=90,
            is_current=True,
        )
        player = self.client.get(
            f"/api/v1/player-seasons/derived-stats/{self.player.id}",
            self.scope,
        )
        team = self.client.get(
            f"/api/v1/team-seasons/stats/{self.home.id}",
            self.scope,
        )
        goalkeeper = self.client.get(
            f"/api/v1/player-seasons/gk-derived-stats/{self.player.id}",
            self.scope,
        )

        self.assertEqual(player.status_code, 200)
        self.assertEqual(team.status_code, 200)
        self.assertEqual(goalkeeper.status_code, 200)
        for payload in (player.json(), goalkeeper.json(), team.json()):
            flag = payload["event_profile"]
            self.assertTrue(flag["available"])
            self.assertEqual(flag["formula_version"], "event_profiles_v3")
            self.assertIn("coverage", flag)
            self.assertNotIn("action_grid", flag)
            self.assertNotIn("pass_flow", flag)
            self.assertNotIn("shots", flag)

        PlayerSeasonEventProfile.objects.filter(player=self.player).update(is_current=False)
        TeamSeasonEventProfile.objects.filter(team=self.home).update(is_current=False)
        player = self.client.get(
            f"/api/v1/player-seasons/derived-stats/{self.player.id}",
            self.scope,
        )
        team = self.client.get(
            f"/api/v1/team-seasons/stats/{self.home.id}",
            self.scope,
        )
        self.assertFalse(player.json()["event_profile"]["available"])
        self.assertFalse(team.json()["event_profile"]["available"])

    def test_incomplete_internal_pilot_profiles_remain_available_on_delivery_branch(self):
        run = PlayerSeasonEventProfile.objects.get(
            player=self.player,
            split_type="season_total",
            is_current=True,
        ).materialized_ingestion_run
        run.stats = run.stats | {
            "public_complete": False,
            "coverage": run.stats["coverage"] | {"complete": False},
        }
        run.save(update_fields=["stats"])

        for url in (self.player_url, self.passes_url, self.team_url):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url, self.scope).status_code, 200)

        player = self.client.get(
            f"/api/v1/player-seasons/derived-stats/{self.player.id}",
            self.scope,
        )
        team = self.client.get(
            f"/api/v1/team-seasons/stats/{self.home.id}",
            self.scope,
        )
        self.assertTrue(player.json()["event_profile"]["available"])
        self.assertFalse(
            player.json()["event_profile"]["coverage"]["competition_complete"]
        )
        self.assertTrue(team.json()["event_profile"]["available"])

    def test_goalkeeper_only_player_can_open_event_profile(self):
        PlayerSeasonGkDerivedStats.objects.create(
            competition_season=self.competition_season,
            canonical_player=self.player,
            canonical_display_team=self.home,
            formula_version="gk-test",
            minutes=90,
            is_current=True,
        )
        PlayerSeasonDerivedStats.objects.filter(canonical_player=self.player).delete()
        MaterializedApiPayload.objects.all().delete()

        response = self.client.get(self.player_url, self.scope)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["canonical_player_id"], self.player.id)
