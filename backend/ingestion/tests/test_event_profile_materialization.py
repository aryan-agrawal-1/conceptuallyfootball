from datetime import datetime, timezone
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from ingestion.models import (
    CanonicalPlayer, CanonicalTeam, Competition, CompetitionSeason, EventProfileSplitType,
    IngestionKind, IngestionRun, IngestionRunStatus, MaterializedApiPayload,
    MatchEventShotOutcome, MatchEventType, PlayerSeasonDerivedStats,
    PlayerSeasonEventProfile, Provider, ProviderMatch, ProviderMatchEvent,
    ProviderMatchStatus, Season, TeamSeasonEventProfile,
)
from ingestion.services.event_profiles import event_profile_availability, materialize_event_profiles


class EventProfileMaterializationTests(TestCase):
    """Hand-built events make the materialiser's public contract auditable."""

    def setUp(self):
        competition = Competition.objects.create(name="League", short_code="TST")
        season = Season.objects.create(label="2025-26", sort_order=1)
        self.cs = CompetitionSeason.objects.create(competition=competition, season=season, has_whoscored=True,
            whoscored_league="test", whoscored_season="25", whoscored_expected_match_count=2, expected_team_count=2)
        self.a, self.b = CanonicalTeam.objects.create(name="A"), CanonicalTeam.objects.create(name="B")
        self.player = CanonicalPlayer.objects.create(display_name="Transferred")
        self.other = CanonicalPlayer.objects.create(display_name="Other")
        PlayerSeasonDerivedStats.objects.create(competition_season=self.cs, canonical_player=self.player, minutes=180)
        PlayerSeasonDerivedStats.objects.create(competition_season=self.cs, canonical_player=self.other, minutes=180)
        self.m1 = self.match("m1", self.a, self.b)
        self.m2 = self.match("m2", self.b, self.a)

    def match(self, ident, home, away):
        return ProviderMatch.objects.create(provider=Provider.WHOSCORED, provider_match_id=ident,
            competition_season=self.cs, kickoff_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            status=ProviderMatchStatus.COMPLETED, home_provider_team_id=f"{ident}h", away_provider_team_id=f"{ident}a",
            home_team=home, away_team=away)

    def event(self, match, index, *, team=None, player=None, **values):
        values = {"provider_match": match, "event_index": index, "provider_team_id": str((team or self.a).pk),
            "team": team or self.a, "provider_player_id": str(player.pk) if player else None, "player": player,
            "minute": 90, "expanded_minute": 90, "second": 0, "event_type": MatchEventType.PASS,
            "x": 0, "y": 0, "end_x": 10000, "end_y": 10000, **values}
        return ProviderMatchEvent.objects.create(**values)

    def materialize(self, **kwargs):
        run = IngestionRun.objects.create(kind=IngestionKind.EVENT_PROFILES, competition_season=self.cs)
        result = materialize_event_profiles(self.cs, run=run, **kwargs)
        run.refresh_from_db()
        return run, result

    def seed_identity_volume(self, unmapped_count):
        """Create exactly 100 provider-player events, some without canonical players."""
        ProviderMatchEvent.objects.all().delete()
        events = []
        for index in range(100):
            mapped = index >= unmapped_count
            events.append(ProviderMatchEvent(
                provider_match=self.m1,
                event_index=index,
                provider_team_id=str(self.a.id),
                team=self.a,
                provider_player_id=f"provider-{index}",
                player=self.player if mapped else None,
                minute=90,
                expanded_minute=90,
                second=0,
                event_type=MatchEventType.PASS,
                x=0,
                y=0,
                end_x=10000,
                end_y=10000,
            ))
        ProviderMatchEvent.objects.bulk_create(events)

    def test_availability_exact_boundaries(self):
        for passes, expected in ((0, (False, True)), (1, (True, True)), (99, (True, True)), (100, (True, False))):
            self.assertEqual((event_profile_availability(passes, 0, 0)["pass_map"]["available"], event_profile_availability(passes, 0, 0)["pass_map"]["sparse"]), expected)
        for shots, expected in ((0, (False, True)), (1, (True, True)), (4, (True, True)), (5, (True, False))):
            self.assertEqual((event_profile_availability(0, shots, 0)["shot_map"]["available"], event_profile_availability(0, shots, 0)["shot_map"]["sparse"]), expected)
        for actions, expected in ((19, (False, True)), (20, (True, True)), (99, (True, True)), (100, (True, False))):
            self.assertEqual((event_profile_availability(0, 0, actions)["action_grid"]["available"], event_profile_availability(0, 0, actions)["action_grid"]["sparse"]), expected)

    def seed_hand_calculated_fixture(self):
        # Player's A spell: two passes, touch without a location, goal and defensive aerial.
        self.event(self.m1, 1, team=self.a, player=self.player, is_touch=True, outcome_successful=True, is_progressive_pass=True, is_final_third_entry=True, is_box_entry=True, is_key_pass=True, is_cross=True, is_long_ball=True)
        self.event(self.m1, 2, team=self.a, player=self.player, x=2000, y=3000, end_x=4000, end_y=4000, is_touch=True, outcome_successful=False)
        self.event(self.m1, 3, team=self.a, player=self.player, event_type=MatchEventType.BALL_TOUCH, x=None, y=None, end_x=None, end_y=None, is_touch=True)
        self.event(self.m1, 4, team=self.a, player=self.player, event_type=MatchEventType.SHOT, x=9000, y=5000, end_x=None, end_y=None, shot_outcome=MatchEventShotOutcome.GOAL, is_big_chance=True)
        self.event(self.m1, 5, team=self.a, player=self.player, event_type=MatchEventType.AERIAL, x=5000, y=5000, end_x=None, end_y=None, is_defensive=True)
        self.event(self.m1, 6, team=self.a, player=self.player, event_type=MatchEventType.AERIAL, x=5000, y=6000, end_x=None, end_y=None, is_defensive=False)
        # B spell adds a successful take-on, defensive challenge, and a pass in a distinct flow pair.
        self.event(self.m2, 1, team=self.b, player=self.player, x=2000, y=4000, end_x=8000, end_y=6000, is_touch=True, outcome_successful=True, is_progressive_pass=True)
        self.event(self.m2, 2, team=self.b, player=self.player, event_type=MatchEventType.TAKE_ON, x=6000, y=5000, end_x=None, end_y=None, is_touch=True, outcome_successful=True)
        self.event(self.m2, 3, team=self.b, player=self.player, event_type=MatchEventType.CHALLENGE, x=6000, y=6000, end_x=None, end_y=None, is_defensive=True)
        self.event(self.m1, 20, team=self.b, player=self.other, event_type=MatchEventType.SHOT, x=9000, y=4000, end_x=None, end_y=None, shot_outcome=MatchEventShotOutcome.GOAL)
        self.event(self.m2, 20, team=self.a, player=self.other, event_type=MatchEventType.SHOT, x=8000, y=4000, end_x=None, end_y=None)

    def test_player_and_team_contract_is_hand_calculated(self):
        self.seed_hand_calculated_fixture(); run, result = self.materialize()
        self.assertIsNotNone(result); self.assertEqual(run.status, IngestionRunStatus.SUCCESS)
        total = PlayerSeasonEventProfile.objects.get(player=self.player, team__isnull=True, is_current=True)
        self.assertEqual((total.split_type, total.observed_match_count, total.observed_event_minutes, total.minutes), (EventProfileSplitType.SEASON_TOTAL, 2, 180, 180))
        self.assertEqual((total.valid_location_actions, total.touches, total.pass_attempts, total.pass_completions), (7, 5, 3, 2))
        self.assertEqual((total.progressive_pass_attempts, total.progressive_pass_completions, total.final_third_entries, total.box_entries, total.key_passes, total.crosses, total.long_balls), (2, 2, 1, 1, 1, 1, 1))
        self.assertEqual((total.shots, total.goals, total.big_chance_shots, total.take_ons_attempted, total.take_ons_successful, total.defensive_actions), (1, 1, 1, 1, 1, 2))
        self.assertEqual((total.average_touch_x, total.average_touch_y), (2500, 3000))
        self.assertEqual(len(total.action_grid), 96); self.assertEqual(sum(c["raw_count"] for c in total.action_grid), 7)
        self.assertEqual(total.action_grid[0]["raw_count"], 1); self.assertEqual(total.action_grid[0]["share"], 1 / 7); self.assertEqual(total.action_grid[0]["per90_count"], .5)
        self.assertEqual(PlayerSeasonEventProfile.objects.filter(player=self.player, split_type=EventProfileSplitType.TEAM, is_current=True).count(), 2)
        self.assertEqual(PlayerSeasonEventProfile.objects.get(player=self.player, team=self.a, is_current=True).pass_attempts, 2)
        self.assertEqual(PlayerSeasonEventProfile.objects.get(player=self.player, team=self.b, is_current=True).pass_attempts, 1)
        team = TeamSeasonEventProfile.objects.get(team=self.a, is_current=True)
        self.assertEqual((team.observed_match_count, team.expected_match_count, team.coverage), (2, 2, 1.0))
        self.assertEqual((team.valid_location_actions, team.touches, team.pass_attempts, team.pass_completions, team.progressive_pass_attempts, team.progressive_pass_completions, team.final_third_entries, team.box_entries, team.key_passes, team.crosses, team.long_balls), (5, 3, 2, 1, 1, 1, 1, 1, 1, 1, 1))
        self.assertEqual((team.shots_for, team.goals_for, team.big_chance_shots_for, team.shots_against, team.goals_against, team.big_chance_shots_against, team.take_ons_attempted, team.take_ons_successful, team.defensive_actions), (2, 1, 1, 1, 1, 0, 0, 0, 1))
        self.assertEqual((len(team.action_grid), len(team.opponent_action_grid), len(team.pass_flow)), (96, 96, 225))
        self.assertEqual(sum(c["raw_count"] for c in team.action_grid), 5); self.assertEqual(sum(c["raw_count"] for c in team.opponent_action_grid), 4)
        self.assertEqual([(x["origin_zone"], x["destination_zone"]) for x in team.pass_flow], [(o, d) for o in range(15) for d in range(15)])
        flow = next(x for x in team.pass_flow if (x["origin_zone"], x["destination_zone"]) == (0, 14))
        self.assertEqual((flow["attempts"], flow["completions"], flow["completion_rate"], flow["progressive_attempts"], flow["progressive_completions"]), (1, 1, 1.0, 1, 1))
        self.assertEqual(next(x for x in team.pass_flow if (x["origin_zone"], x["destination_zone"]) == (1, 1))["attempts"], 0)

    def test_rebuild_is_deterministic_and_affected_rebuild_preserves_unaffected(self):
        self.seed_hand_calculated_fixture(); self.materialize()
        first_a = TeamSeasonEventProfile.objects.get(team=self.a, is_current=True); first_b = TeamSeasonEventProfile.objects.get(team=self.b, is_current=True)
        self.materialize(); second_a = TeamSeasonEventProfile.objects.get(team=self.a, is_current=True); second_b = TeamSeasonEventProfile.objects.get(team=self.b, is_current=True)
        self.assertEqual(first_a.action_grid, second_a.action_grid); self.assertEqual(first_a.pass_flow, second_a.pass_flow)
        self.assertEqual(TeamSeasonEventProfile.objects.filter(competition_season=self.cs, team=self.a, is_current=True).count(), 1)
        ProviderMatchEvent.objects.filter(provider_match=self.m1, event_index=1).update(outcome_successful=False)
        self.materialize(affected_player_ids=[self.player.id], affected_team_ids=[self.a.id])
        affected = TeamSeasonEventProfile.objects.get(team=self.a, is_current=True); unchanged = TeamSeasonEventProfile.objects.get(team=self.b, is_current=True)
        self.assertNotEqual(affected.id, second_a.id); self.assertEqual(unchanged.id, second_b.id); self.assertEqual(affected.pass_completions, 0)
        self.materialize(); self.assertEqual(affected.pass_completions, TeamSeasonEventProfile.objects.get(team=self.a, is_current=True).pass_completions)

    def test_affected_match_command_removes_profiles_for_deleted_identities(self):
        removed_player = CanonicalPlayer.objects.create(display_name="Removed by correction")
        self.event(self.m1, 50, team=self.a, player=removed_player)
        self.seed_hand_calculated_fixture()
        self.materialize()
        self.assertTrue(
            PlayerSeasonEventProfile.objects.filter(
                competition_season=self.cs,
                player=removed_player,
                is_current=True,
            ).exists()
        )
        ProviderMatchEvent.objects.filter(
            provider_match=self.m1,
            player=removed_player,
        ).delete()

        call_command("materialize_event_profiles", self.cs.id, "--affected-match-id", "m1")

        self.assertFalse(
            PlayerSeasonEventProfile.objects.filter(
                competition_season=self.cs,
                player=removed_player,
                is_current=True,
            ).exists()
        )

    def test_atomic_failure_retains_prior_current_and_cache_scope(self):
        self.seed_hand_calculated_fixture(); self.materialize(); prior = TeamSeasonEventProfile.objects.get(team=self.a, is_current=True)
        MaterializedApiPayload.objects.create(cache_key=f"event-profile:{self.cs.id}:player:1", source_version="1", payload={})
        MaterializedApiPayload.objects.create(cache_key="event-profile:999:player:1", source_version="1", payload={})
        MaterializedApiPayload.objects.create(cache_key="unrelated", source_version="1", payload={})
        with patch.object(PlayerSeasonEventProfile.objects, "bulk_create", side_effect=RuntimeError("boom")):
            failed, result = self.materialize()
        self.assertIsNone(result); self.assertEqual(failed.status, IngestionRunStatus.FAILED); self.assertEqual(TeamSeasonEventProfile.objects.get(team=self.a, is_current=True).id, prior.id)
        with patch("ingestion.services.event_profiles.invalidate_event_profile_api_payloads", side_effect=RuntimeError("cache boom")):
            failed, result = self.materialize()
        self.assertIsNone(result); self.assertEqual(failed.status, IngestionRunStatus.FAILED); self.assertEqual(TeamSeasonEventProfile.objects.get(team=self.a, is_current=True).id, prior.id)
        self.materialize(); self.assertFalse(MaterializedApiPayload.objects.filter(cache_key__startswith=f"event-profile:{self.cs.id}:").exists())
        self.assertTrue(MaterializedApiPayload.objects.filter(cache_key="event-profile:999:player:1").exists()); self.assertTrue(MaterializedApiPayload.objects.filter(cache_key="unrelated").exists())

    def test_public_gates_offline_and_command_scope(self):
        self.seed_hand_calculated_fixture(); self.cs.is_published = True; self.cs.whoscored_expected_match_count = 3; self.cs.save()
        internal, result = self.materialize(internal_pilot=True); self.assertIsNotNone(result); self.assertEqual(internal.status, IngestionRunStatus.SUCCESS)
        self.assertFalse(internal.stats["public_complete"])
        self.assertTrue(internal.stats["internal_pilot"])
        self.cs.whoscored_expected_match_count = 2; self.cs.save(update_fields=["whoscored_expected_match_count"])
        with patch("ingestion.services.whoscored_client.SoccerdataWhoScoredClient", side_effect=AssertionError("offline"), create=True):
            succeeded, result = self.materialize()
        self.assertIsNotNone(result); self.assertEqual(succeeded.stats["formula_version"], "event_profiles_v1")
        with self.assertRaises(CommandError): call_command("materialize_event_profiles", self.cs.id, "--affected-player-id", self.player.id)
        with self.assertRaises(CommandError): call_command("materialize_event_profiles", self.cs.id, "--affected-match-id", "missing")
        with self.assertRaises(CommandError):
            call_command("materialize_event_profiles", "--competition", "TST")
        with self.assertRaises(CommandError):
            call_command(
                "materialize_event_profiles",
                self.cs.id,
                "--competition",
                "TST",
                "--season",
                "2025-26",
            )
        for aggregate_scope in ("BIG5", "ALL"):
            with self.subTest(aggregate_scope=aggregate_scope), self.assertRaises(CommandError):
                call_command(
                    "materialize_event_profiles",
                    "--competition",
                    aggregate_scope,
                    "--season",
                    "2025-26",
                )
        with self.assertRaises(CommandError):
            call_command(
                "materialize_event_profiles",
                self.cs.id,
                "--affected-player-id",
                self.player.id,
                "--affected-team-id",
                self.a.id,
                "--affected-match-id",
                "m1",
            )
        call_command("materialize_event_profiles", self.cs.id, "--affected-match-id", "m1")

    def test_identity_warning_and_failure_thresholds_are_exact(self):
        for unmapped, warning, failure in ((1, False, False), (2, True, False), (5, True, False)):
            with self.subTest(unmapped=unmapped):
                self.seed_identity_volume(unmapped)
                run, result = self.materialize()
                self.assertIsNotNone(result)
                volume = run.stats["event_identity"]["volume"]
                self.assertEqual(volume["unmapped_player_events"], unmapped)
                self.assertEqual(volume["warning"], warning)
                self.assertEqual(volume["publication_failure"], failure)

        self.seed_identity_volume(0)
        succeeded, result = self.materialize()
        self.assertIsNotNone(result)
        prior = TeamSeasonEventProfile.objects.get(team=self.a, is_current=True)
        self.seed_identity_volume(6)
        failed, result = self.materialize()
        self.assertIsNone(result)
        self.assertEqual(failed.status, IngestionRunStatus.FAILED)
        self.assertIn("Unmapped player-event volume", failed.error_detail)
        self.assertEqual(TeamSeasonEventProfile.objects.get(team=self.a, is_current=True).id, prior.id)

    def test_published_unmapped_team_event_fails_without_replacing_current_profiles(self):
        self.seed_hand_calculated_fixture()
        succeeded, result = self.materialize()
        self.assertIsNotNone(result)
        prior = TeamSeasonEventProfile.objects.get(team=self.a, is_current=True)
        unmapped = self.event(self.m1, 99, team=self.a, player=self.other)
        ProviderMatchEvent.objects.filter(pk=unmapped.pk).update(team=None, provider_team_id="unmapped")
        self.cs.is_published = True
        self.cs.save(update_fields=["is_published"])

        failed, result = self.materialize()

        self.assertIsNone(result)
        self.assertEqual(failed.status, IngestionRunStatus.FAILED)
        self.assertIn("mapped teams", failed.error_detail)
        self.assertEqual(TeamSeasonEventProfile.objects.get(team=self.a, is_current=True).id, prior.id)

    def test_published_refresh_uses_discovered_completed_coverage(self):
        self.seed_hand_calculated_fixture()
        self.cs.is_published = True
        self.cs.refresh_enabled = True
        self.cs.whoscored_expected_match_count = 38
        self.cs.save(update_fields=["is_published", "refresh_enabled", "whoscored_expected_match_count"])

        succeeded, result = self.materialize()

        self.assertIsNotNone(result)
        self.assertTrue(succeeded.stats["coverage"]["complete"])
        self.assertTrue(succeeded.stats["public_complete"])
        prior = TeamSeasonEventProfile.objects.get(team=self.a, is_current=True)
        self.match("m3", self.a, self.b)
        failed, result = self.materialize()
        self.assertIsNone(result)
        self.assertEqual(failed.status, IngestionRunStatus.FAILED)
        self.assertFalse(failed.stats.get("coverage", {}).get("discovered_complete", True))
        self.assertEqual(TeamSeasonEventProfile.objects.get(team=self.a, is_current=True).id, prior.id)
