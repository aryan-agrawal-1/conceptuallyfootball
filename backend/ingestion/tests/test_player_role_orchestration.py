from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from ingestion.models import (
    Competition,
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    IngestionRunStatus,
    Season,
)
from ingestion.services.player_role_orchestration import (
    RoleMaterializationAlreadyRunning,
    run_player_role_materialization,
)
from ingestion.tasks import task_materialize_player_season_roles


class PlayerRoleOrchestrationTests(TestCase):
    def setUp(self):
        competition = Competition.objects.create(name="Test League", short_code="TL")
        season = Season.objects.create(label="2099-00")
        self.competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
        )
        cache.clear()

    def test_celery_role_jobs_use_the_single_lane_ingestion_queue(self):
        self.assertEqual(
            task_materialize_player_season_roles._get_exec_options()["queue"],
            "ingestion",
        )

    @patch("ingestion.services.player_season_roles.materialize_player_season_roles")
    def test_success_persists_mode_counts_timing_queries_and_rss(self, materialize):
        def result(competition_season, *, diagnostics, **options):
            CompetitionSeason.objects.get(pk=competition_season.pk)
            diagnostics["mode"] = "incremental"
            diagnostics["affected_count"] = 1
            diagnostics["cohort_count"] = 5
            diagnostics["rows_processed"]["events"] = 12
            diagnostics["stage_timings_seconds"]["event_carry_exposure_aggregation"] = 0.1
            return {
                "features": {"mode": "incremental", "snapshots": 1},
                "scoring": {"cohort_snapshots": 5, "published_roles": 5},
            }

        materialize.side_effect = result

        output = run_player_role_materialization(
            self.competition_season,
            affected_player_ids=[7],
            affected_team_ids=[9],
        )

        run = IngestionRun.objects.get(pk=output["run_id"])
        self.assertEqual(run.kind, IngestionKind.PLAYER_ROLES)
        self.assertEqual(run.status, IngestionRunStatus.SUCCESS)
        self.assertEqual(run.stats["requested_mode"], "affected")
        self.assertEqual(run.stats["mode"], "incremental")
        self.assertEqual(run.stats["affected_count"], 1)
        self.assertEqual(run.stats["cohort_count"], 5)
        self.assertEqual(run.stats["match_batch_size"], 5)
        self.assertEqual(run.stats["rows_processed"]["events"], 12)
        self.assertGreaterEqual(run.stats["query_count"], 1)
        self.assertIn("total", run.stats["stage_timings_seconds"])
        self.assertGreater(run.stats["peak_rss_mb"], 0)

    @patch(
        "ingestion.services.player_role_orchestration.competition_season_role_lock",
        side_effect=RoleMaterializationAlreadyRunning("already running"),
    )
    def test_same_season_overlap_is_rejected_and_recorded(self, lock):
        with self.assertRaises(RoleMaterializationAlreadyRunning):
            run_player_role_materialization(self.competition_season, score_only=True)

        run = IngestionRun.objects.get(kind=IngestionKind.PLAYER_ROLES)
        self.assertEqual(run.status, IngestionRunStatus.FAILED)
        self.assertEqual(run.stats["requested_mode"], "score_only")
        self.assertEqual(run.stats["error_type"], "RoleMaterializationAlreadyRunning")
        lock.assert_called_once_with(self.competition_season.pk)

    @patch("ingestion.services.player_season_roles.materialize_player_season_roles")
    def test_failed_run_releases_lock_for_verified_retry(self, materialize):
        materialize.side_effect = [RuntimeError("forced failure"), {
            "features": None,
            "scoring": {"cohort_snapshots": 0, "published_roles": 0},
        }]

        with self.assertRaisesMessage(RuntimeError, "forced failure"):
            run_player_role_materialization(self.competition_season, score_only=True)
        retry = run_player_role_materialization(self.competition_season, score_only=True)

        runs = list(IngestionRun.objects.order_by("id"))
        self.assertEqual([run.status for run in runs], [
            IngestionRunStatus.FAILED,
            IngestionRunStatus.SUCCESS,
        ])
        self.assertEqual(retry["scoring"]["published_roles"], 0)
