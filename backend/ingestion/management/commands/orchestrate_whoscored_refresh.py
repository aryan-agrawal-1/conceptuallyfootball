from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ingestion.models import (
    IngestionBatch,
    IngestionBatchItem,
    IngestionBatchItemStatus,
    IngestionLease,
)
from ingestion.services.whoscored_weekly import weekly_competition_seasons, weekly_refresh_enabled


class Command(BaseCommand):
    help = "Plan, enqueue, inspect, or recover weekly WhoScored refresh work."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--enqueue", action="store_true")
        parser.add_argument("--competition")
        parser.add_argument("--settlements", action="store_true")
        parser.add_argument("--requeue-item", type=int)
        parser.add_argument("--leases", action="store_true")
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options) -> None:
        if options["leases"]:
            for lease in IngestionLease.objects.order_by("key"):
                state = "expired" if lease.expires_at <= timezone.now() else "active"
                self.stdout.write(f"{lease.key} {state} expires={lease.expires_at.isoformat()}")
            return
        if options["requeue_item"]:
            self.requeue(options["requeue_item"], force=options["force"])
            return
        if options["settlements"]:
            if not weekly_refresh_enabled() and not options["force"]:
                raise CommandError(
                    "Weekly WhoScored is disabled; pass --force for a manual scan."
                )
            self.send_task(
                "ingestion.tasks.task_plan_due_whoscored_settlements",
                args=[options["force"]],
                queue="ingestion-planner",
            )
            self.stdout.write(self.style.SUCCESS("Enqueued due-settlement scan."))
            return
        slices = weekly_competition_seasons()
        if options["competition"]:
            slices = [
                competition_season
                for competition_season in slices
                if competition_season.competition.short_code.upper()
                == options["competition"].upper()
            ]
            if not slices:
                raise CommandError("No matching published WhoScored competition-season.")
        self.stdout.write(
            f"Weekly WhoScored enabled={weekly_refresh_enabled()} "
            "schedule=Tuesday 07:30 Europe/London"
        )
        for competition_season in slices:
            self.stdout.write(
                f"{competition_season.competition.short_code} "
                f"{competition_season.season.label} id={competition_season.id}"
            )
        if not options["enqueue"]:
            return
        if not weekly_refresh_enabled() and not options["force"]:
            raise CommandError("Weekly WhoScored is disabled; pass --force for a manual run.")
        batch = IngestionBatch.objects.create(
            kind=IngestionBatch.KIND_WEEKLY_WHOSCORED,
            scheduled_for_date=timezone.localdate(),
            planned_start_at=timezone.now(),
            started_at=timezone.now(),
            manual=True,
            status="running",
            summary_stats={"planned_items": len(slices)},
        )
        for order, competition_season in enumerate(slices, start=1):
            item = IngestionBatchItem.objects.create(
                batch=batch,
                competition_season=competition_season,
                planned_order=order,
                eta=timezone.now(),
            )
            self.send_task(
                "ingestion.tasks.task_run_weekly_whoscored_item",
                args=[item.id],
                queue="whoscored",
            )
        self.stdout.write(self.style.SUCCESS(f"Enqueued WhoScored batch {batch.id}."))

    def requeue(self, item_id: int, *, force: bool) -> None:
        if not weekly_refresh_enabled() and not force:
            raise CommandError("Weekly WhoScored is disabled; pass --force to requeue.")
        item = IngestionBatchItem.objects.get(pk=item_id)
        if item.batch.kind != IngestionBatch.KIND_WEEKLY_WHOSCORED:
            raise CommandError("Item does not belong to a weekly WhoScored batch.")
        if item.status not in {
            IngestionBatchItemStatus.FAILED,
            IngestionBatchItemStatus.SKIPPED,
            IngestionBatchItemStatus.CANCELLED,
        }:
            raise CommandError(f"Cannot requeue an item in {item.status} state.")
        item.status = IngestionBatchItemStatus.PENDING
        item.current_stage = ""
        item.error_detail = ""
        item.started_at = None
        item.finished_at = None
        item.save(
            update_fields=[
                "status",
                "current_stage",
                "error_detail",
                "started_at",
                "finished_at",
                "updated_at",
            ]
        )
        item.batch.status = "running"
        item.batch.finished_at = None
        item.batch.error_detail = ""
        item.batch.save(
            update_fields=["status", "finished_at", "error_detail", "updated_at"]
        )
        self.send_task(
            "ingestion.tasks.task_run_weekly_whoscored_item",
            args=[item.id],
            queue="whoscored",
        )
        self.stdout.write(self.style.SUCCESS(f"Requeued WhoScored item {item.id}."))

    @staticmethod
    def send_task(name: str, *, args=None, queue: str) -> None:
        from celery import current_app

        current_app.send_task(name, args=args or [], queue=queue)
