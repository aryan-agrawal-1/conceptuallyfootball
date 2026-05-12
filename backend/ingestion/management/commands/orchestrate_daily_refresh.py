from __future__ import annotations

from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ingestion.models import (
    CompetitionSeason,
    IngestionBatch,
    IngestionBatchItem,
    IngestionBatchStatus,
)
from ingestion.services.orchestration import (
    daily_refresh_enabled,
    default_refresh_date,
    enqueue_batch,
    ensure_planned_daily_batch,
    plan_refresh_slices,
    requeue_item,
    validate_refresh_selection,
)


class Command(BaseCommand):
    help = "Plan, enqueue, inspect, or requeue production daily refresh orchestration."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--enqueue", action="store_true", help="Create and enqueue a manual batch now.")
        parser.add_argument("--competition", help="Limit a manual enqueue/dry-run to one competition code.")
        parser.add_argument("--date", help="Batch date to inspect or plan, YYYY-MM-DD. Defaults to today.")
        parser.add_argument("--requeue-item", type=int, help="Requeue a failed/skipped/cancelled batch item id.")
        parser.add_argument("--no-jitter", action="store_true", help="Use immediate deterministic ETAs.")
        parser.add_argument("--force", action="store_true", help="Bypass the automatic-refresh kill switch.")

    def handle(self, *args, **options) -> None:
        target_date = self._parse_date(options.get("date"))

        if options.get("requeue_item"):
            if not daily_refresh_enabled() and not options["force"]:
                raise CommandError("Daily refresh kill switch is off; pass --force to requeue anyway.")
            item = requeue_item(options["requeue_item"])
            self.stdout.write(self.style.SUCCESS(f"Requeued item {item.id}"))
            return

        if options["enqueue"]:
            if not daily_refresh_enabled() and not options["force"]:
                raise CommandError("Daily refresh kill switch is off; pass --force to enqueue manually.")
            if options.get("competition"):
                self._enqueue_single_competition(options["competition"], no_jitter=options["no_jitter"])
                return
            batch = ensure_planned_daily_batch(day=target_date, manual=True)
            if batch.status != IngestionBatchStatus.PLANNED:
                raise CommandError(f"Batch {batch.id} is already {batch.status}.")
            result = enqueue_batch(batch.id, no_jitter=options["no_jitter"])
            if not result["ok"]:
                raise CommandError(f"Could not enqueue batch: {result}")
            self.stdout.write(self.style.SUCCESS(f"Enqueued batch {batch.id} with {result['items']} items."))
            return

        if options.get("competition"):
            planned = self._single_competition_plan(options["competition"], no_jitter=options["no_jitter"])
        else:
            planned = plan_refresh_slices(day=target_date, no_jitter=options["no_jitter"])
        self.stdout.write(
            f"Daily refresh enabled={daily_refresh_enabled()} "
            f"window={settings.STATBALLER_DAILY_REFRESH_START_HOUR}:00-"
            f"{settings.STATBALLER_DAILY_REFRESH_END_HOUR}:00"
        )
        for entry in planned:
            cs = entry.competition_season
            self.stdout.write(
                f"{entry.planned_order:02d}. {cs.competition.short_code} {cs.season.label} "
                f"id={cs.id} eta={entry.eta.isoformat()} delay={entry.delay_seconds}s"
            )

    def _parse_date(self, raw: str | None) -> date:
        if not raw:
            return default_refresh_date()
        try:
            return date.fromisoformat(raw)
        except ValueError as exc:
            raise CommandError("--date must be YYYY-MM-DD") from exc

    def _single_competition_plan(self, code: str, *, no_jitter: bool):
        cs = self._get_single_refresh_slice(code)
        validate_refresh_selection([cs])
        from ingestion.services.orchestration import PlannedSlice

        return [
            PlannedSlice(
                competition_season=cs,
                planned_order=1,
                delay_seconds=0,
                eta=timezone.now(),
            )
        ]

    def _enqueue_single_competition(self, code: str, *, no_jitter: bool) -> None:
        cs = self._get_single_refresh_slice(code)
        validate_refresh_selection([cs])
        batch = IngestionBatch.objects.create(
            kind=IngestionBatch.KIND_DAILY_REFRESH,
            scheduled_for_date=default_refresh_date(),
            planned_start_at=timezone.now(),
            manual=True,
            status=IngestionBatchStatus.RUNNING,
            started_at=timezone.now(),
            summary_stats={"planned_items": 1, "season_label": cs.season.label, "manual_competition": code},
        )
        item = IngestionBatchItem.objects.create(
            batch=batch,
            competition_season=cs,
            planned_order=1,
            eta=timezone.now(),
        )
        from celery import current_app

        current_app.send_task(
            "ingestion.tasks.task_refresh_competition_season_item",
            args=[item.id],
            queue="ingestion",
        )
        self.stdout.write(self.style.SUCCESS(f"Enqueued {code.upper()} item {item.id} in batch {batch.id}."))

    def _get_single_refresh_slice(self, code: str) -> CompetitionSeason:
        try:
            return (
                CompetitionSeason.objects.select_related("competition", "season")
                .filter(refresh_enabled=True, competition__short_code__iexact=code)
                .get()
            )
        except CompetitionSeason.DoesNotExist as exc:
            raise CommandError(f"No refresh-enabled slice found for competition {code!r}.") from exc
        except CompetitionSeason.MultipleObjectsReturned as exc:
            raise CommandError(f"Multiple refresh-enabled slices found for competition {code!r}.") from exc
