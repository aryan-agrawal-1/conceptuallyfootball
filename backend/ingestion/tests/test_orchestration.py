from __future__ import annotations

from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from ingestion.models import (
    Competition,
    CompetitionSeason,
    CompetitionType,
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
    materialize_aggregate_scopes,
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
    sofascore_season_id: int = 76986,
    understat_season_year: str = "2025",
) -> CompetitionSeason:
    comp = Competition.objects.create(name=code, short_code=code, country="Test")
    season, _ = Season.objects.get_or_create(
        label=season_label,
        defaults={"sort_order": int(season_label.split("-")[-1])},
    )
    return CompetitionSeason.objects.create(
        competition=comp,
        season=season,
        player_data_mode=player_data_mode,
        has_understat=has_understat,
        has_sofascore=True,
        understat_league="EPL" if has_understat else None,
        understat_season_year=understat_season_year if has_understat else None,
        sofascore_unique_tournament_id=17,
        sofascore_season_id=sofascore_season_id,
        expected_team_count=1,
        min_merged_team_count=1,
        min_team_stats_coverage_count=1,
        is_published=True,
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

    def test_mixed_refresh_enabled_seasons_are_allowed(self):
        _slice("ENG1", "2025-26", refresh_enabled=True)
        _slice("ENG2", "2024-25", refresh_enabled=True)

        validate_refresh_selection(list(CompetitionSeason.objects.select_related("season")))

    def test_refresh_selection_rejects_duplicate_competition(self):
        first = _slice("ENG1", refresh_enabled=True)
        duplicate = _slice("ENG2", "2024-25", refresh_enabled=True)
        duplicate.competition_id = first.competition_id
        duplicate.save(update_fields=["competition"])
        with self.assertRaisesMessage(ValueError, "appears more than once"):
            validate_refresh_selection([first, duplicate])

    def test_refresh_selection_rejects_inactive_unpublished_and_provider_missing(self):
        inactive = _slice("ENG1", refresh_enabled=True)
        inactive.is_active = False
        inactive.save(update_fields=["is_active"])
        with self.assertRaisesMessage(ValueError, "inactive"):
            validate_refresh_selection([inactive])

        unpublished = _slice("ENG2", refresh_enabled=True)
        unpublished.is_published = False
        unpublished.save(update_fields=["is_published"])
        with self.assertRaisesMessage(ValueError, "unpublished"):
            validate_refresh_selection([unpublished])

        missing_provider = _slice("ENG3", refresh_enabled=True)
        missing_provider.sofascore_season_id = None
        missing_provider.save(update_fields=["sofascore_season_id"])
        with self.assertRaisesMessage(ValueError, "missing Sofascore"):
            validate_refresh_selection([missing_provider])

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

    @patch("celery.current_app.send_task")
    def test_mixed_batch_metadata_has_deterministic_season_labels(self, mock_send_task):
        _slice("ENG1", "2025-26", refresh_enabled=True)
        _slice("ENG2", "2024-25", refresh_enabled=True)
        batch = IngestionBatch.objects.create(
            scheduled_for_date=timezone.localdate(),
            planned_start_at=timezone.now(),
        )

        result = enqueue_batch(batch.id, no_jitter=True, send_tasks=False)

        self.assertTrue(result["ok"])
        batch.refresh_from_db()
        self.assertEqual(batch.summary_stats["season_labels"], ["2024-25", "2025-26"])
        self.assertNotIn("season_label", batch.summary_stats)
        mock_send_task.assert_not_called()


class DailyRefreshExecutionTests(TestCase):
    season_label = "2025-26"
    sofascore_season_id = 76986
    understat_season_year = "2025"

    def setUp(self):
        self.cs = _slice(
            "ENG1",
            self.season_label,
            refresh_enabled=True,
            player_data_mode=PlayerDataMode.FULL_MERGE,
            has_understat=True,
            sofascore_season_id=self.sofascore_season_id,
            understat_season_year=self.understat_season_year,
        )
        self.batch = IngestionBatch.objects.create(
            scheduled_for_date=timezone.localdate(),
            planned_start_at=timezone.now(),
            status=IngestionBatchStatus.RUNNING,
            started_at=timezone.now(),
            summary_stats={"planned_items": 1, "season_label": self.season_label},
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
            "position_resolution",
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


class AggregateBatchTests(TestCase):
    @patch("ingestion.services.galaxy.materialize_galaxy_scope", side_effect=_succeed_aggregate)
    def test_mixed_label_aggregates_use_stable_keys_and_exclude_continental(self, mock_materialize):
        batch = IngestionBatch.objects.create(
            scheduled_for_date=timezone.localdate(),
            planned_start_at=timezone.now(),
            status=IngestionBatchStatus.RUNNING,
        )
        eng = _slice("ENG1", "2025-26", refresh_enabled=False)
        swe = _slice("SWE1", "2026", refresh_enabled=False)
        ucl = _slice("UCL", "2026-27", refresh_enabled=False)
        ucl.competition.competition_type = CompetitionType.CONTINENTAL_CUP
        ucl.competition.include_in_domestic_aggregates = False
        ucl.competition.save(update_fields=["competition_type", "include_in_domestic_aggregates"])
        for competition_season in (eng, swe, ucl):
            IngestionBatchItem.objects.create(
                batch=batch,
                competition_season=competition_season,
                status=IngestionBatchItemStatus.SUCCESS,
                planned_order=competition_season.id,
            )

        result = materialize_aggregate_scopes(batch.id)

        self.assertTrue(result["ok"])
        keys = set(result["aggregate_run_ids"])
        self.assertIn("BIG5:2025-26", keys)
        self.assertIn("ALL:2025-26", keys)
        self.assertIn("ALL:2026-27", keys)
        self.assertNotIn("ALL:2026", keys)
        self.assertEqual(
            [(call.args[0], call.args[1]) for call in mock_materialize.call_args_list],
            [("BIG5", "2025-26"), ("ALL", "2025-26"), ("ALL", "2026-27")],
        )


class NewSeasonDailyRefreshExecutionTests(DailyRefreshExecutionTests):
    """Issue #34 acceptance coverage for a configured 2026-27 target slice."""

    season_label = "2026-27"
    sofascore_season_id = 96518
    understat_season_year = "2026"


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
