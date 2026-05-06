from __future__ import annotations

from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    IngestionRunStatus,
    MergedTeamSeason,
    Provider,
    ReepPlayerRow,
    ReepTeamRow,
    Season,
    SofascorePlayerSeasonSource,
    SofascoreTeamSeasonSource,
    UnderstatPlayerSeasonSource,
    UnmatchedProviderTeam,
)
from ingestion.services.ingest import ingest_sofascore_team_slice, run_team_merge_job


def _slice() -> CompetitionSeason:
    comp = Competition.objects.create(name="Premier League", short_code="EPL", country="England")
    season = Season.objects.create(label="2025-26", sort_order=2026)
    return CompetitionSeason.objects.create(
        competition=comp,
        season=season,
        understat_league="EPL",
        understat_season_year="2025",
        sofascore_unique_tournament_id=17,
        sofascore_season_id=76986,
        expected_team_count=1,
        min_merged_team_count=1,
        min_team_stats_coverage_count=1,
    )


def _team_row(provider_team_id: str = "42", team_name: str = "Arsenal", **overrides):
    row = {
        "provider_team_id": provider_team_id,
        "team_name": team_name,
        "standings_row_json": {"position": 1, "points": 70, "matches": 33},
        "overall_stats_json": {"averageBallPossession": 56.0, "corners": 196},
        "has_overall_stats": True,
        "matches": 33,
        "rank": 1,
        "points": 70,
        "wins": 21,
        "draws": 7,
        "losses": 5,
        "goals_for": 63,
        "goals_against": 26,
        "goal_difference": 37,
        "average_ball_possession": 56.06,
        "corners": 196,
        "corners_against": 110,
        "shots": 479,
        "shots_on_target": 160,
        "shots_against": 265,
        "accurate_passes": 12971,
        "total_passes": 15441,
        "accurate_passes_percentage": 84.0,
        "ball_recovery": 1495,
        "tackles": 548,
        "interceptions": 234,
        "clearances": 794,
        "saves": 53,
        "duels_won": 1667,
        "duels_won_percentage": 52.08,
        "aerial_duels_won": 539,
        "aerial_duels_won_percentage": 51.68,
        "ground_duels_won": 1128,
        "ground_duels_won_percentage": 52.27,
        "successful_dribbles": 238,
        "fouls": 340,
        "yellow_cards": 43,
        "red_cards": 0,
        "offsides": 51,
        "penalties_taken": 4,
        "penalty_goals": 4,
        "goals_from_inside_the_box": 50,
        "goals_from_outside_the_box": 9,
        "headed_goals": 14,
        "hit_woodwork": 10,
    }
    row.update(overrides)
    return row


class TeamSourceIngestTests(TestCase):
    @patch("ingestion.services.ingest.build_team_season_rows")
    def test_ingest_persists_team_source_row_with_canonical_team(self, mock_build_rows):
        cs = _slice()
        ReepTeamRow.objects.create(reep_id="rt1", name="Arsenal", sofascore_team_id="42")
        mock_build_rows.return_value = [_team_row()]
        run = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE_TEAM,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )

        ingest_sofascore_team_slice(cs, run=run)

        run.refresh_from_db()
        self.assertEqual(run.status, IngestionRunStatus.SUCCESS)
        src = SofascoreTeamSeasonSource.objects.get(competition_season=cs, provider_team_id="42")
        self.assertEqual(src.canonical_team.name, "Arsenal")
        self.assertTrue(src.has_overall_stats)
        self.assertEqual(src.rank, 1)
        self.assertEqual(src.corners, 196)
        self.assertEqual(src.overall_stats_json["corners"], 196)

    @patch("ingestion.services.ingest.build_team_season_rows")
    def test_ingest_creates_provider_native_team_fallback_and_keeps_audit_row(self, mock_build_rows):
        cs = _slice()
        mock_build_rows.return_value = [_team_row(provider_team_id="999", team_name="Mystery FC")]
        run = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE_TEAM,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )

        ingest_sofascore_team_slice(cs, run=run)

        run.refresh_from_db()
        self.assertEqual(run.status, IngestionRunStatus.SUCCESS)
        src = SofascoreTeamSeasonSource.objects.get(provider_team_id="999")
        self.assertIsNotNone(src.canonical_team)
        self.assertEqual(src.canonical_team.name, "Mystery FC")
        quarantine = UnmatchedProviderTeam.objects.get(
            competition_season=cs,
            provider=Provider.SOFASCORE,
            provider_team_id="999",
        )
        self.assertEqual(quarantine.team_name, "Mystery FC")
        self.assertEqual(quarantine.resolved_team, src.canonical_team)
        self.assertIsNotNone(quarantine.resolved_at)


class TeamMergeTests(TestCase):
    def setUp(self):
        self.cs = _slice()
        self.team = CanonicalTeam.objects.create(name="Arsenal", reep_id="rt1")
        self.source_run = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE_TEAM,
            competition_season=self.cs,
            status=IngestionRunStatus.SUCCESS,
        )

    def _create_source_row(self, **overrides):
        defaults = _team_row()
        defaults.update(overrides)
        return SofascoreTeamSeasonSource.objects.create(
            competition_season=self.cs,
            ingestion_run=self.source_run,
            provider_team_id=defaults["provider_team_id"],
            team_name=defaults["team_name"],
            standings_row_json=defaults["standings_row_json"],
            overall_stats_json=defaults["overall_stats_json"],
            has_overall_stats=defaults["has_overall_stats"],
            matches=defaults["matches"],
            rank=defaults["rank"],
            points=defaults["points"],
            wins=defaults["wins"],
            draws=defaults["draws"],
            losses=defaults["losses"],
            goals_for=defaults["goals_for"],
            goals_against=defaults["goals_against"],
            goal_difference=defaults["goal_difference"],
            average_ball_possession=defaults["average_ball_possession"],
            corners=defaults["corners"],
            corners_against=defaults["corners_against"],
            shots=defaults["shots"],
            shots_on_target=defaults["shots_on_target"],
            shots_against=defaults["shots_against"],
            accurate_passes=defaults["accurate_passes"],
            total_passes=defaults["total_passes"],
            accurate_passes_percentage=defaults["accurate_passes_percentage"],
            ball_recovery=defaults["ball_recovery"],
            tackles=defaults["tackles"],
            interceptions=defaults["interceptions"],
            clearances=defaults["clearances"],
            saves=defaults["saves"],
            duels_won=defaults["duels_won"],
            duels_won_percentage=defaults["duels_won_percentage"],
            aerial_duels_won=defaults["aerial_duels_won"],
            aerial_duels_won_percentage=defaults["aerial_duels_won_percentage"],
            ground_duels_won=defaults["ground_duels_won"],
            ground_duels_won_percentage=defaults["ground_duels_won_percentage"],
            successful_dribbles=defaults["successful_dribbles"],
            fouls=defaults["fouls"],
            yellow_cards=defaults["yellow_cards"],
            red_cards=defaults["red_cards"],
            offsides=defaults["offsides"],
            penalties_taken=defaults["penalties_taken"],
            penalty_goals=defaults["penalty_goals"],
            goals_from_inside_the_box=defaults["goals_from_inside_the_box"],
            goals_from_outside_the_box=defaults["goals_from_outside_the_box"],
            headed_goals=defaults["headed_goals"],
            hit_woodwork=defaults["hit_woodwork"],
            canonical_team=defaults.pop("canonical_team", self.team),
        )

    def test_team_merge_creates_current_row(self):
        self._create_source_row()
        run = IngestionRun.objects.create(
            kind=IngestionKind.TEAM_MERGE,
            competition_season=self.cs,
            status=IngestionRunStatus.PENDING,
        )

        run_team_merge_job(self.cs, run=run)

        run.refresh_from_db()
        self.assertEqual(run.status, IngestionRunStatus.SUCCESS)
        row = MergedTeamSeason.objects.get(competition_season=self.cs, canonical_team=self.team)
        self.assertTrue(row.is_current)
        self.assertEqual(row.points, 70)
        self.assertEqual(row.corners, 196)
        self.assertEqual(row.average_ball_possession, 56.06)

    def test_failed_team_merge_preserves_previous_current_rows(self):
        previous = MergedTeamSeason.objects.create(
            competition_season=self.cs,
            canonical_team=self.team,
            rank=1,
            points=70,
            is_current=True,
        )
        self.cs.min_merged_team_count = 2
        self.cs.save(update_fields=["min_merged_team_count"])
        self._create_source_row()
        run = IngestionRun.objects.create(
            kind=IngestionKind.TEAM_MERGE,
            competition_season=self.cs,
            status=IngestionRunStatus.PENDING,
        )

        run_team_merge_job(self.cs, run=run)

        run.refresh_from_db()
        previous.refresh_from_db()
        self.assertEqual(run.status, IngestionRunStatus.FAILED)
        self.assertTrue(previous.is_current)
        self.assertEqual(MergedTeamSeason.objects.filter(competition_season=self.cs).count(), 1)


class TeamApiTests(TestCase):
    def setUp(self):
        self.cs = _slice()
        self.team = CanonicalTeam.objects.create(name="Arsenal", reep_id="rt1")
        self.current = MergedTeamSeason.objects.create(
            competition_season=self.cs,
            canonical_team=self.team,
            rank=1,
            points=70,
            corners=196,
            average_ball_possession=56.06,
            is_current=True,
        )
        self.historical = MergedTeamSeason.objects.create(
            competition_season=self.cs,
            canonical_team=CanonicalTeam.objects.create(name="Arsenal Old", reep_id="rt2"),
            rank=2,
            points=68,
            is_current=False,
            superseded_at=timezone.now(),
        )

    def test_list_filters_search_and_current_only_detail(self):
        client = APIClient()

        list_response = client.get(
            "/internal/api/merged-team-seasons/",
            {"competition": "EPL", "season": "2025-26", "search": "arse"},
        )
        self.assertEqual(list_response.status_code, 200)
        payload = list_response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["canonical_team_name"], "Arsenal")
        self.assertEqual(payload[0]["corners"], 196)

        detail_response = client.get(f"/internal/api/merged-team-seasons/{self.current.id}/")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["canonical_team_name"], "Arsenal")

        historical_response = client.get(f"/internal/api/merged-team-seasons/{self.historical.id}/")
        self.assertEqual(historical_response.status_code, 404)


class RepairCommandTests(TestCase):
    @patch("ingestion.services.galaxy.materialize_galaxy_embeddings")
    @patch("ingestion.services.derived.materialize_derived_stats")
    @patch("ingestion.management.commands.repair_slice_materializations.run_merge_job")
    @patch("ingestion.management.commands.repair_slice_materializations.run_team_merge_job")
    def test_repair_command_runs_team_then_player_chain(
        self,
        mock_run_team_merge_job,
        mock_run_merge_job,
        mock_materialize_derived_stats,
        mock_materialize_galaxy_embeddings,
    ):
        cs = _slice()

        def mark_success(_cs, run):
            run.status = IngestionRunStatus.SUCCESS
            run.finished_at = timezone.now()
            run.error_detail = ""
            run.stats = {"ok": True}
            run.save(update_fields=["status", "finished_at", "error_detail", "stats"])

        mock_run_team_merge_job.side_effect = mark_success
        mock_run_merge_job.side_effect = mark_success
        mock_materialize_derived_stats.side_effect = mark_success
        mock_materialize_galaxy_embeddings.side_effect = mark_success

        call_command("repair_slice_materializations", cs.id)

        run_kinds = list(
            IngestionRun.objects.filter(competition_season=cs).order_by("id").values_list("kind", flat=True)
        )
        self.assertEqual(
            run_kinds,
            [
                IngestionKind.TEAM_MERGE,
                IngestionKind.MERGE,
                IngestionKind.DERIVED,
                IngestionKind.GALAXY,
            ],
        )


class TeamMappingRepairTests(TestCase):
    def test_reattach_updates_team_source_and_player_source_team_fk(self):
        cs = _slice()
        canonical_team = CanonicalTeam.objects.create(name="Arsenal", reep_id="rt1")
        ReepTeamRow.objects.create(reep_id="rt1", name="Arsenal", sofascore_team_id="42")
        ReepPlayerRow.objects.create(
            reep_id="rp1",
            full_name="Alice",
            understat_player_id="1",
            sofascore_player_id="10",
        )
        canonical_player = CanonicalPlayer.objects.create(display_name="Alice", reep_id="rp1")
        player_run = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE,
            competition_season=cs,
            status=IngestionRunStatus.SUCCESS,
        )
        team_run = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE_TEAM,
            competition_season=cs,
            status=IngestionRunStatus.SUCCESS,
        )
        player_src = SofascorePlayerSeasonSource.objects.create(
            competition_season=cs,
            ingestion_run=player_run,
            provider_player_id="10",
            provider_team_id="42",
            player_name="Alice",
            team_name="Arsenal",
            canonical_player=canonical_player,
        )
        team_src = SofascoreTeamSeasonSource.objects.create(
            competition_season=cs,
            ingestion_run=team_run,
            provider_team_id="42",
            team_name="Arsenal",
        )

        from ingestion.services.identity import reattach_slice_identities

        reattach_slice_identities(cs)

        player_src.refresh_from_db()
        team_src.refresh_from_db()
        self.assertEqual(player_src.canonical_team, canonical_team)
        self.assertEqual(team_src.canonical_team, canonical_team)
