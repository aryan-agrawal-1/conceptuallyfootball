from __future__ import annotations

from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from ingestion.models import (
    Competition,
    CompetitionSeason,
    IngestionBatch,
    IngestionBatchItem,
    IngestionBatchItemStatus,
    IngestionBatchStatus,
    IngestionKind,
    IngestionRun,
    IngestionRunStatus,
    MaterializedApiPayload,
    PlayerDataMode,
    Season,
)
from ingestion.services.orchestration import (
    enqueue_batch,
    execute_batch_item,
    plan_refresh_slices,
    validate_refresh_selection,
)


def _slice(
    code: str,
    season_label: str = "2025-26",
    *,
    refresh_enabled: bool = True,
    player_data_mode: str = PlayerDataMode.SOFASCORE_ONLY,
    has_understat: bool = False,
) -> CompetitionSeason:
    comp = Competition.objects.create(name=code, short_code=code, country="Test")
    season, _ = Season.objects.get_or_create(
        label=season_label,
        defaults={"sort_order": int(season_label.split("-")[1])},
    )
    return CompetitionSeason.objects.create(
        competition=comp,
        season=season,
        player_data_mode=player_data_mode,
        has_understat=has_understat,
        has_sofascore=True,
        understat_league="EPL" if has_understat else None,
        understat_season_year="2025" if has_understat else None,
        sofascore_unique_tournament_id=17,
        sofascore_season_id=76986,
        expected_team_count=1,
        min_merged_team_count=1,
        min_team_stats_coverage_count=1,
        refresh_enabled=refresh_enabled,
    )


def _succeed_stage(cs, *, run):
    run.status = IngestionRunStatus.SUCCESS
    run.stats = {"competition_season_id": cs.id}
    run.save(update_fields=["status", "stats"])


def _fail_stage(cs, *, run):
    run.status = IngestionRunStatus.FAILED
    run.error_detail = "boom"
    run.save(update_fields=["status", "error_detail"])


def _succeed_aggregate(scope, season_label, *, run):
    run.status = IngestionRunStatus.SUCCESS
    run.stats = {"scope": scope, "season_label": season_label}
    run.save(update_fields=["status", "stats"])


class DailyRefreshPlanningTests(TestCase):
    def test_plan_uses_only_refresh_enabled_current_slices(self):
        _slice("ENG1", refresh_enabled=True)
        _slice("SPA1", refresh_enabled=True)
        _slice("OLD1", "2024-25", refresh_enabled=False)

        planned = plan_refresh_slices(no_jitter=True)

        self.assertEqual(len(planned), 2)
        self.assertEqual({entry.competition_season.competition.short_code for entry in planned}, {"ENG1", "SPA1"})
        self.assertTrue(all(entry.delay_seconds == 0 for entry in planned))

    def test_mixed_refresh_enabled_seasons_are_rejected(self):
        _slice("ENG1", "2025-26", refresh_enabled=True)
        _slice("ENG2", "2024-25", refresh_enabled=True)

        with self.assertRaisesMessage(ValueError, "share one season label"):
            validate_refresh_selection(list(CompetitionSeason.objects.select_related("season")))

    @patch("celery.current_app.send_task")
    def test_enqueue_batch_creates_items_without_sending_when_disabled(self, mock_send_task):
        _slice("ENG1", refresh_enabled=True)
        _slice("SPA1", refresh_enabled=True)
        batch = IngestionBatch.objects.create(
            scheduled_for_date=timezone.localdate(),
            planned_start_at=timezone.now(),
        )

        result = enqueue_batch(batch.id, no_jitter=True, send_tasks=False)

        self.assertTrue(result["ok"])
        self.assertEqual(result["items"], 2)
        batch.refresh_from_db()
        self.assertEqual(batch.status, IngestionBatchStatus.RUNNING)
        self.assertEqual(batch.items.count(), 2)
        mock_send_task.assert_not_called()


class DailyRefreshExecutionTests(TestCase):
    def setUp(self):
        self.cs = _slice(
            "ENG1",
            refresh_enabled=True,
            player_data_mode=PlayerDataMode.FULL_MERGE,
            has_understat=True,
        )
        self.batch = IngestionBatch.objects.create(
            scheduled_for_date=timezone.localdate(),
            planned_start_at=timezone.now(),
            status=IngestionBatchStatus.RUNNING,
            started_at=timezone.now(),
            summary_stats={"planned_items": 1, "season_label": "2025-26"},
        )
        self.item = IngestionBatchItem.objects.create(
            batch=self.batch,
            competition_season=self.cs,
            planned_order=1,
            eta=timezone.now(),
        )

    @patch("ingestion.services.orchestration.invalidate_materialized_api_payloads", return_value=1)
    @patch("ingestion.services.galaxy.materialize_galaxy_scope", side_effect=_succeed_aggregate)
    @patch("ingestion.services.galaxy.materialize_galaxy_embeddings", side_effect=_succeed_stage)
    @patch("ingestion.services.derived.materialize_derived_stats", side_effect=_succeed_stage)
    @patch("ingestion.services.orchestration.run_merge_job", side_effect=_succeed_stage)
    @patch("ingestion.services.orchestration.run_team_merge_job", side_effect=_succeed_stage)
    @patch("ingestion.services.orchestration.ingest_understat_slice", side_effect=_succeed_stage)
    @patch("ingestion.services.orchestration.ingest_sofascore_team_slice", side_effect=_succeed_stage)
    @patch("ingestion.services.orchestration.ingest_sofascore_slice", side_effect=_succeed_stage)
    def test_execute_item_runs_required_stages_and_finalizes_batch(self, *_mocks):
        MaterializedApiPayload.objects.create(cache_key="x", source_version="1", payload={"stale": True})

        result = execute_batch_item(self.item.id)

        self.assertTrue(result["ok"])
        self.item.refresh_from_db()
        self.batch.refresh_from_db()
        self.assertEqual(self.item.status, IngestionBatchItemStatus.SUCCESS)
        self.assertEqual(self.item.current_stage, "done")
        self.assertEqual(self.batch.status, IngestionBatchStatus.SUCCESS)
        for stage in (
            "sofascore",
            "sofascore_team",
            "understat",
            "team_merge",
            "merge",
            "derived",
            "galaxy",
        ):
            self.assertIn(stage, self.item.stage_run_ids)
        self.assertIn("BIG5", self.batch.aggregate_run_ids)
        self.assertIn("ALL", self.batch.aggregate_run_ids)

    @patch("ingestion.services.orchestration.invalidate_materialized_api_payloads", return_value=0)
    @patch("ingestion.services.orchestration.ingest_sofascore_team_slice", side_effect=_fail_stage)
    @patch("ingestion.services.orchestration.ingest_sofascore_slice", side_effect=_succeed_stage)
    def test_execute_item_failure_stops_league_and_marks_batch_failed(self, *_mocks):
        result = execute_batch_item(self.item.id)

        self.assertFalse(result["ok"])
        self.item.refresh_from_db()
        self.batch.refresh_from_db()
        self.assertEqual(self.item.status, IngestionBatchItemStatus.FAILED)
        self.assertEqual(self.item.current_stage, "sofascore_team")
        self.assertEqual(self.batch.status, IngestionBatchStatus.FAILED)


class DailyRefreshCommandTests(TestCase):
    @override_settings(STATBALLER_DAILY_REFRESH_ENABLED=True)
    def test_command_dry_run_outputs_plan(self):
        _slice("ENG1", refresh_enabled=True)

        call_command("orchestrate_daily_refresh", "--no-jitter")


class BackfillHistoryCommandTests(TestCase):
    @patch("ingestion.services.galaxy.materialize_galaxy_embeddings", side_effect=_succeed_stage)
    @patch("ingestion.services.derived.materialize_derived_stats", side_effect=_succeed_stage)
    @patch("ingestion.management.commands.backfill_history.run_merge_job", side_effect=_succeed_stage)
    @patch("ingestion.management.commands.backfill_history.run_team_merge_job", side_effect=_succeed_stage)
    @patch("ingestion.management.commands.backfill_history.ingest_understat_slice", side_effect=_succeed_stage)
    @patch("ingestion.management.commands.backfill_history.ingest_sofascore_team_slice", side_effect=_succeed_stage)
    @patch("ingestion.management.commands.backfill_history.ingest_sofascore_slice", side_effect=_succeed_stage)
    def test_command_runs_full_slice_chain(
        self,
        mock_sofa,
        mock_team,
        mock_understat,
        mock_team_merge,
        mock_merge,
        mock_derived,
        mock_galaxy,
    ):
        cs = _slice("ENG1", player_data_mode=PlayerDataMode.FULL_MERGE, has_understat=True)

        call_command(
            "backfill_history",
            "--skip-seed",
            "--no-sleep",
            "--competitions",
            "ENG1",
            "--seasons",
            cs.season.label,
            "--output",
            "/tmp/statballer-backfill-test.json",
        )

        self.assertEqual(mock_sofa.call_count, 1)
        self.assertEqual(mock_team.call_count, 1)
        self.assertEqual(mock_understat.call_count, 1)
        self.assertEqual(mock_team_merge.call_count, 1)
        self.assertEqual(mock_merge.call_count, 1)
        self.assertEqual(mock_derived.call_count, 1)
        self.assertEqual(mock_galaxy.call_count, 1)

    @patch("ingestion.management.commands.backfill_history.run_team_merge_job", side_effect=_succeed_stage)
    @patch("ingestion.management.commands.backfill_history.ingest_sofascore_team_slice", side_effect=_succeed_stage)
    @patch("ingestion.management.commands.backfill_history.ingest_sofascore_slice", side_effect=_succeed_stage)
    def test_command_skips_successful_provider_runs_without_force(self, mock_sofa, mock_team, _mock_team_merge):
        cs = _slice("ENG1")
        for kind in (IngestionKind.SOFASCORE, IngestionKind.SOFASCORE_TEAM):
            IngestionRun.objects.create(
                competition_season=cs,
                kind=kind,
                status=IngestionRunStatus.SUCCESS,
                finished_at=timezone.now(),
            )

        call_command(
            "backfill_history",
            "--skip-seed",
            "--providers-only",
            "--no-sleep",
            "--competitions",
            "ENG1",
            "--output",
            "/tmp/statballer-backfill-skip-test.json",
        )

        mock_sofa.assert_not_called()
        mock_team.assert_not_called()
