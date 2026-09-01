from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.utils import timezone as django_timezone
from django.core.management import call_command
from django.core.management.base import CommandError
from celery.exceptions import Retry

from backend import settings
from ingestion.models import (
    Competition,
    CompetitionSeason,
    IngestionBatch,
    IngestionBatchItemStatus,
    IngestionLease,
    IngestionRun,
    IngestionRunStatus,
    Provider,
    ProviderMatch,
    ProviderMatchPayload,
    ProviderMatchStatus,
    ProviderPayloadLifecycle,
    Season,
)
from ingestion.services.ingestion_leases import (
    acquire_lease,
    release_lease,
    renew_lease,
)
from ingestion.services.whoscored_client import SourceMatch
from ingestion.services.whoscored_weekly import (
    CORRECTION_REASON,
    NEW_REASON,
    SETTLEMENT_REASON,
    WeeklyCandidate,
    candidate_reason,
    due_settlement_matches,
    execute_weekly_item,
    materialize_changed_entities,
    plan_weekly_batch,
    select_weekly_candidates,
)
from ingestion.tasks import (
    task_plan_due_whoscored_settlements,
    task_refresh_competition_season_item,
)


NOW = datetime(2026, 9, 1, 7, 30, tzinfo=timezone.utc)


def source_match(match_id: int, *, age: timedelta, status="completed") -> SourceMatch:
    return SourceMatch(
        match_id=match_id,
        kickoff_at=NOW - age,
        status=status,
        home_team_id=match_id * 10,
        away_team_id=match_id * 10 + 1,
        home_team_name="Home",
        away_team_name="Away",
        home_score=1,
        away_score=0,
        source_league="GER-Bundesliga",
        source_season="2025-26",
    )


class WhoScoredWeeklyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        competition = Competition.objects.create(
            name="Bundesliga",
            short_code="GER1",
            country="Germany",
        )
        season = Season.objects.create(label="2025-26", sort_order=2026)
        cls.competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
            has_whoscored=True,
            whoscored_league="GER-Bundesliga",
            whoscored_season="2025-26",
            is_active=True,
            is_published=True,
        )

    def provider_match(self, match_id: int, *, age: timedelta) -> ProviderMatch:
        return ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id=str(match_id),
            competition_season=self.competition_season,
            kickoff_at=NOW - age,
            status=ProviderMatchStatus.COMPLETED,
            home_provider_team_id=str(match_id * 10),
            away_provider_team_id=str(match_id * 10 + 1),
            home_score=1,
            away_score=0,
        )

    def payload(self, match, *, lifecycle, fetched_at):
        checksum = str(match.provider_match_id).zfill(64)
        return ProviderMatchPayload.objects.create(
            provider_match=match,
            payload_gzip=b"x",
            payload_sha256=checksum,
            payload_size_bytes=1,
            uncompressed_size_bytes=1,
            lifecycle_state=lifecycle,
            preliminary_sha256=(
                checksum if lifecycle == ProviderPayloadLifecycle.PRELIMINARY else None
            ),
            preliminary_fetched_at=(
                fetched_at
                if lifecycle == ProviderPayloadLifecycle.PRELIMINARY
                else None
            ),
            final_sha256=(
                checksum if lifecycle == ProviderPayloadLifecycle.FINAL else None
            ),
            final_fetched_at=(
                fetched_at if lifecycle == ProviderPayloadLifecycle.FINAL else None
            ),
            fetched_at=fetched_at,
        )

    def test_candidate_boundaries_are_bounded_and_status_safe(self):
        recent = source_match(1, age=timedelta(hours=4))
        too_recent = source_match(2, age=timedelta(hours=2, minutes=59))
        old_missing = source_match(3, age=timedelta(days=28, seconds=1))
        live = source_match(4, age=timedelta(hours=4), status="live")

        self.assertEqual(candidate_reason(recent, None, now=NOW), NEW_REASON)
        self.assertIsNone(candidate_reason(too_recent, None, now=NOW))
        self.assertIsNone(candidate_reason(old_missing, None, now=NOW))
        self.assertIsNone(candidate_reason(live, None, now=NOW))

    def test_preliminary_settlement_and_final_correction_windows(self):
        due = self.provider_match(10, age=timedelta(days=60))
        self.payload(
            due,
            lifecycle=ProviderPayloadLifecycle.PRELIMINARY,
            fetched_at=NOW - timedelta(hours=12),
        )
        fresh = self.provider_match(11, age=timedelta(days=1))
        self.payload(
            fresh,
            lifecycle=ProviderPayloadLifecycle.PRELIMINARY,
            fetched_at=NOW - timedelta(hours=11, minutes=59),
        )
        recent_final = self.provider_match(12, age=timedelta(days=14))
        self.payload(
            recent_final,
            lifecycle=ProviderPayloadLifecycle.FINAL,
            fetched_at=NOW - timedelta(days=1),
        )
        old_final = self.provider_match(13, age=timedelta(days=14, seconds=1))
        self.payload(
            old_final,
            lifecycle=ProviderPayloadLifecycle.FINAL,
            fetched_at=NOW - timedelta(days=1),
        )

        self.assertEqual(
            candidate_reason(
                source_match(10, age=timedelta(days=60)), due, now=NOW
            ),
            SETTLEMENT_REASON,
        )
        self.assertIsNone(
            candidate_reason(source_match(11, age=timedelta(days=1)), fresh, now=NOW)
        )
        self.assertEqual(
            candidate_reason(
                source_match(12, age=timedelta(days=14)), recent_final, now=NOW
            ),
            CORRECTION_REASON,
        )
        self.assertIsNone(
            candidate_reason(
                source_match(13, age=timedelta(days=14, seconds=1)),
                old_final,
                now=NOW,
            )
        )
        recent_final.payload.final_fetched_at = NOW
        recent_final.payload.fetched_at = NOW
        recent_final.payload.save(update_fields=["final_fetched_at", "fetched_at"])
        self.assertIsNone(
            candidate_reason(
                source_match(12, age=timedelta(days=14)),
                recent_final,
                now=NOW + timedelta(hours=1),
                correction_cutoff=NOW - timedelta(minutes=1),
            )
        )
        self.assertEqual(due_settlement_matches(self.competition_season, now=NOW), [due])

    def test_selection_upserts_only_selected_schedule_rows(self):
        lifecycle = Mock()

        def upsert(source):
            return self.provider_match(source.match_id, age=NOW - source.kickoff_at)

        lifecycle.upsert_match.side_effect = upsert
        selected = select_weekly_candidates(
            self.competition_season,
            [
                source_match(1, age=timedelta(days=2)),
                source_match(2, age=timedelta(days=40)),
                source_match(3, age=timedelta(hours=1)),
            ],
            lifecycle,
            now=NOW,
        )

        self.assertEqual([candidate.reason for candidate in selected], [NEW_REASON])
        self.assertEqual(lifecycle.upsert_match.call_count, 1)
        self.assertEqual(ProviderMatch.objects.count(), 1)

    def test_expiring_leases_require_the_owner_and_recover(self):
        first = acquire_lease("heavy-maintenance", ttl=timedelta(minutes=5), now=NOW)
        self.assertIsNotNone(first)
        self.assertIsNone(
            acquire_lease("heavy-maintenance", ttl=timedelta(minutes=5), now=NOW)
        )
        self.assertTrue(renew_lease(first, ttl=timedelta(minutes=10), now=NOW))
        self.assertFalse(release_lease(type(first)(first.key, "wrong-owner")))
        recovered = acquire_lease(
            "heavy-maintenance",
            ttl=timedelta(minutes=5),
            now=NOW + timedelta(minutes=11),
        )
        self.assertIsNotNone(recovered)
        self.assertNotEqual(recovered.owner_token, first.owner_token)
        self.assertTrue(release_lease(recovered))
        self.assertFalse(IngestionLease.objects.exists())

    @override_settings(STATBALLER_WHOSCORED_WEEKLY_ENABLED=False)
    def test_disabled_automatic_batch_is_recorded_as_skipped(self):
        batch = plan_weekly_batch(day=NOW.date())

        self.assertEqual(batch.status, "skipped")
        self.assertEqual(batch.items.count(), 0)

    @override_settings(STATBALLER_WHOSCORED_WEEKLY_ENABLED=True)
    def test_weekly_batch_is_idempotent_and_contains_published_slices(self):
        first = plan_weekly_batch(day=NOW.date())
        second = plan_weekly_batch(day=NOW.date())

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.items.count(), 1)
        self.assertEqual(first.items.get().competition_season, self.competition_season)

    @patch("ingestion.services.whoscored_weekly.materialize_changed_entities")
    @patch("ingestion.services.whoscored_weekly.run_weekly_acquisition")
    def test_weekly_item_completes_cached_no_op(self, acquisition, materialize):
        batch = plan_weekly_batch(day=NOW.date(), manual=True)
        item = batch.items.get()
        run = IngestionRun.objects.create(
            kind="whoscored_fetch",
            competition_season=self.competition_season,
            status=IngestionRunStatus.SUCCESS,
        )
        acquisition.return_value = (
            run,
            {"events_changed": False, "match_actions": {"reused_final": 20}},
        )
        materialize.return_value = {"outcome": "no_op"}

        result = execute_weekly_item(item.id)

        item.refresh_from_db()
        self.assertTrue(result["ok"])
        self.assertEqual(item.status, IngestionBatchItemStatus.SUCCESS)
        self.assertEqual(item.stage_stats["materialization"]["outcome"], "no_op")

    @patch("ingestion.services.whoscored_weekly.materialize_changed_entities")
    @patch("ingestion.services.whoscored_weekly.run_weekly_acquisition")
    def test_partial_acquisition_materializes_successes_before_retry(
        self,
        acquisition,
        materialize,
    ):
        batch = plan_weekly_batch(day=NOW.date(), manual=True)
        item = batch.items.get()
        run = IngestionRun.objects.create(
            kind="whoscored_fetch",
            competition_season=self.competition_season,
            status=IngestionRunStatus.FAILED,
            error_detail="one failed match",
        )
        stats = {
            "events_changed": True,
            "affected_player_ids": [1],
            "affected_team_ids": [2],
            "failures": [{"match_id": "failed"}],
        }
        acquisition.return_value = (run, stats)
        materialize.return_value = {"outcome": "rebuilt"}

        result = execute_weekly_item(item.id)

        item.refresh_from_db()
        self.assertFalse(result["ok"])
        materialize.assert_called_once_with(self.competition_season, stats)
        self.assertEqual(item.stage_stats["materialization"]["outcome"], "rebuilt")
        self.assertEqual(item.status, IngestionBatchItemStatus.FAILED)

    @patch("ingestion.services.whoscored_weekly.materialize_changed_entities")
    @patch("ingestion.services.whoscored_weekly.run_weekly_acquisition")
    def test_materialization_failure_resumes_without_refetch(
        self,
        acquisition,
        materialize,
    ):
        batch = plan_weekly_batch(day=NOW.date(), manual=True)
        item = batch.items.get()
        prior = {
            "events_changed": True,
            "affected_player_ids": [1],
            "affected_team_ids": [2],
            "failures": [],
        }
        item.stage_stats = {"acquisition": prior}
        item.save(update_fields=["stage_stats"])
        materialize.return_value = {"outcome": "rebuilt"}

        result = execute_weekly_item(item.id)

        self.assertTrue(result["ok"])
        acquisition.assert_not_called()
        materialize.assert_called_once_with(self.competition_season, prior)

    @patch("ingestion.services.whoscored_weekly.run_player_role_materialization")
    @patch("ingestion.services.whoscored_weekly.materialize_event_profiles")
    def test_changed_entities_feed_narrow_profile_and_role_scopes(
        self,
        profiles,
        roles,
    ):
        def publish_profiles(_competition_season, *, run, **_kwargs):
            run.status = IngestionRunStatus.SUCCESS
            run.save(update_fields=["status"])
            return Mock(player_rows=4, team_rows=2)

        profiles.side_effect = publish_profiles
        roles.return_value = {"run_id": 9, "scoring": {"published_roles": 20}}

        result = materialize_changed_entities(
            self.competition_season,
            {
                "events_changed": True,
                "affected_player_ids": [1, 2],
                "affected_team_ids": [3, 4],
            },
        )

        self.assertEqual(result["outcome"], "rebuilt")
        self.assertEqual(profiles.call_args.kwargs["affected_player_ids"], [1, 2])
        self.assertEqual(roles.call_args.kwargs["affected_team_ids"], [3, 4])

    def test_celery_schedule_is_tuesday_and_queues_are_separate(self):
        weekly = settings.CELERY_BEAT_SCHEDULE["plan-weekly-whoscored"]

        self.assertEqual(str(weekly["schedule"]), "<crontab: 30 7 * * tuesday (m/h/dM/MY/d)>")
        self.assertEqual(
            settings.CELERY_TASK_ROUTES[
                "ingestion.tasks.task_run_weekly_whoscored_item"
            ]["queue"],
            "whoscored",
        )

    @override_settings(STATBALLER_WHOSCORED_WEEKLY_ENABLED=False)
    @patch("celery.current_app.send_task")
    def test_manual_command_requires_force_and_can_requeue(self, send_task):
        with self.assertRaisesMessage(CommandError, "pass --force"):
            call_command(
                "orchestrate_whoscored_refresh",
                "--enqueue",
                "--competition",
                "GER1",
            )
        call_command(
            "orchestrate_whoscored_refresh",
            "--enqueue",
            "--competition",
            "GER1",
            "--force",
        )
        item = IngestionBatch.objects.get(manual=True).items.get()
        item.status = IngestionBatchItemStatus.FAILED
        item.save(update_fields=["status"])
        item.batch.status = "failed"
        item.batch.save(update_fields=["status"])

        call_command(
            "orchestrate_whoscored_refresh",
            "--requeue-item",
            str(item.id),
            "--force",
        )

        item.refresh_from_db()
        item.batch.refresh_from_db()
        self.assertEqual(item.status, IngestionBatchItemStatus.PENDING)
        self.assertEqual(item.batch.status, "running")
        self.assertEqual(send_task.call_count, 2)

    @override_settings(STATBALLER_WHOSCORED_WEEKLY_ENABLED=True)
    @patch("celery.current_app.send_task")
    def test_settlement_planner_deduplicates_queued_scope(self, send_task):
        match = self.provider_match(50, age=timedelta(days=1))
        self.payload(
            match,
            lifecycle=ProviderPayloadLifecycle.PRELIMINARY,
            fetched_at=django_timezone.now() - timedelta(hours=13),
        )

        first = task_plan_due_whoscored_settlements.run()
        second = task_plan_due_whoscored_settlements.run()

        self.assertEqual(first["items"], 1)
        self.assertEqual(second["items"], 0)
        self.assertEqual(send_task.call_count, 1)
        self.assertTrue(
            IngestionLease.objects.filter(
                key=f"whoscored-settlement-queued:{self.competition_season.id}"
            ).exists()
        )

    def test_daily_worker_retries_while_heavy_lease_is_active(self):
        batch = IngestionBatch.objects.create(
            scheduled_for_date=NOW.date(),
            status="running",
        )
        item = batch.items.create(
            competition_season=self.competition_season,
            planned_order=1,
        )
        acquire_lease("heavy-maintenance", ttl=timedelta(minutes=5))

        with self.assertRaises(Retry):
            task_refresh_competition_season_item.run(item.id)

        item.refresh_from_db()
        self.assertEqual(item.status, IngestionBatchItemStatus.PENDING)
