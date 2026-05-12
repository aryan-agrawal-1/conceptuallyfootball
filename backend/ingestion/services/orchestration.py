from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from celery import current_app
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone

from ingestion.api_cache import invalidate_materialized_api_payloads
from ingestion.models import (
    CompetitionSeason,
    IngestionBatch,
    IngestionBatchItem,
    IngestionBatchItemStatus,
    IngestionBatchStatus,
    IngestionKind,
    IngestionRun,
    IngestionRunStatus,
)
from ingestion.services.ingest import (
    ingest_sofascore_slice,
    ingest_sofascore_team_slice,
    ingest_understat_slice,
    run_merge_job,
    run_team_merge_job,
)
from ingestion.services.sofascore_client import (
    reset_request_metrics,
    set_request_cap,
    snapshot_request_metrics,
)

FINAL_ITEM_STATUSES = {
    IngestionBatchItemStatus.SUCCESS,
    IngestionBatchItemStatus.FAILED,
    IngestionBatchItemStatus.SKIPPED,
    IngestionBatchItemStatus.CANCELLED,
}
FINAL_BATCH_STATUSES = {
    IngestionBatchStatus.SUCCESS,
    IngestionBatchStatus.PARTIAL_SUCCESS,
    IngestionBatchStatus.FAILED,
    IngestionBatchStatus.SKIPPED,
    IngestionBatchStatus.CANCELLED,
}
DAILY_REFRESH_KIND = IngestionBatch.KIND_DAILY_REFRESH


@dataclass(frozen=True)
class PlannedSlice:
    competition_season: CompetitionSeason
    planned_order: int
    delay_seconds: int
    eta: datetime


def daily_refresh_enabled() -> bool:
    return bool(getattr(settings, "STATBALLER_DAILY_REFRESH_ENABLED", True))


def _refresh_timezone() -> ZoneInfo:
    return ZoneInfo(getattr(settings, "STATBALLER_DAILY_REFRESH_TIME_ZONE", "Europe/London"))


def _refresh_localdate(value: datetime | None = None) -> date:
    return timezone.localdate(value=value, timezone=_refresh_timezone())


def default_refresh_date() -> date:
    return _refresh_localdate()


def _refresh_window_for(day: date) -> tuple[datetime, datetime]:
    start_hour = int(getattr(settings, "STATBALLER_DAILY_REFRESH_START_HOUR", 1))
    end_hour = int(getattr(settings, "STATBALLER_DAILY_REFRESH_END_HOUR", 7))
    tz = _refresh_timezone()
    start = timezone.make_aware(datetime.combine(day, time(hour=start_hour)), timezone=tz)
    end = timezone.make_aware(datetime.combine(day, time(hour=end_hour)), timezone=tz)
    return start, end


def random_planned_start(day: date) -> datetime:
    start, end = _refresh_window_for(day)
    span_seconds = max(0, int((end - start).total_seconds()))
    return start + timedelta(seconds=random.randint(0, span_seconds))


def selected_refresh_slices() -> list[CompetitionSeason]:
    return list(
        CompetitionSeason.objects.select_related("competition", "season")
        .filter(refresh_enabled=True)
        .order_by("competition__short_code", "season__sort_order")
    )


def rotated_refresh_slices(day: date | None = None) -> list[CompetitionSeason]:
    slices = selected_refresh_slices()
    if not slices:
        return []
    target_day = day or _refresh_localdate()
    offset = target_day.timetuple().tm_yday % len(slices)
    return slices[offset:] + slices[:offset]


def validate_refresh_selection(slices: list[CompetitionSeason]) -> None:
    if not slices:
        raise ValueError("No CompetitionSeason rows have refresh_enabled=True.")
    season_labels = {cs.season.label for cs in slices}
    if len(season_labels) != 1:
        raise ValueError(
            "Daily refresh requires all refresh-enabled slices to share one season label; "
            f"found {sorted(season_labels)}."
        )
    for cs in slices:
        if not cs.supports_sofascore:
            raise ValueError(f"{cs} is refresh-enabled but missing Sofascore configuration.")


def plan_refresh_slices(
    *,
    day: date | None = None,
    start_at: datetime | None = None,
    no_jitter: bool = False,
) -> list[PlannedSlice]:
    target_day = day or _refresh_localdate()
    start = start_at or timezone.now()
    slices = rotated_refresh_slices(target_day)
    validate_refresh_selection(slices)

    min_delay = int(getattr(settings, "STATBALLER_DAILY_REFRESH_MIN_LEAGUE_DELAY_SECONDS", 600))
    max_delay = int(getattr(settings, "STATBALLER_DAILY_REFRESH_MAX_LEAGUE_DELAY_SECONDS", 1500))
    if max_delay < min_delay:
        max_delay = min_delay

    elapsed = 0
    planned: list[PlannedSlice] = []
    for index, cs in enumerate(slices):
        if index > 0:
            elapsed += 0 if no_jitter else random.randint(min_delay, max_delay)
        planned.append(
            PlannedSlice(
                competition_season=cs,
                planned_order=index + 1,
                delay_seconds=elapsed,
                eta=start + timedelta(seconds=elapsed),
            )
        )
    return planned


def ensure_planned_daily_batch(*, day: date | None = None, manual: bool = False) -> IngestionBatch:
    target_day = day or _refresh_localdate()
    if not manual and not daily_refresh_enabled():
        batch, _ = IngestionBatch.objects.get_or_create(
            kind=DAILY_REFRESH_KIND,
            scheduled_for_date=target_day,
            manual=False,
            defaults={
                "status": IngestionBatchStatus.SKIPPED,
                "finished_at": timezone.now(),
                "error_detail": "Automatic daily refresh is disabled.",
            },
        )
        return batch
    try:
        return IngestionBatch.objects.create(
            kind=DAILY_REFRESH_KIND,
            scheduled_for_date=target_day,
            planned_start_at=timezone.now() if manual else random_planned_start(target_day),
            manual=manual,
            status=IngestionBatchStatus.PLANNED,
        )
    except IntegrityError:
        return IngestionBatch.objects.get(
            kind=DAILY_REFRESH_KIND,
            scheduled_for_date=target_day,
            manual=False,
        )


def enqueue_due_daily_batch(*, now: datetime | None = None) -> dict[str, Any]:
    current = now or timezone.now()
    today = _refresh_localdate(current)
    batch = ensure_planned_daily_batch(day=today, manual=False)
    if batch.status != IngestionBatchStatus.PLANNED:
        return {"ok": False, "batch_id": batch.id, "status": batch.status}

    _, window_end = _refresh_window_for(today)
    if current > window_end:
        batch.status = IngestionBatchStatus.SKIPPED
        batch.finished_at = current
        batch.error_detail = "Automatic planner missed the daily start window."
        batch.save(update_fields=["status", "finished_at", "error_detail", "updated_at"])
        return {"ok": False, "batch_id": batch.id, "status": batch.status}
    if batch.planned_start_at and current < batch.planned_start_at:
        return {
            "ok": False,
            "batch_id": batch.id,
            "status": batch.status,
            "planned_start_at": batch.planned_start_at.isoformat(),
        }
    return enqueue_batch(batch.id)


def enqueue_batch(batch_id: int, *, no_jitter: bool = False, send_tasks: bool = True) -> dict[str, Any]:
    with transaction.atomic():
        batch = IngestionBatch.objects.select_for_update().get(pk=batch_id)
        if batch.status != IngestionBatchStatus.PLANNED:
            return {"ok": False, "batch_id": batch.id, "status": batch.status}
        planned = plan_refresh_slices(
            day=batch.scheduled_for_date,
            start_at=timezone.now(),
            no_jitter=no_jitter,
        )
        batch.status = IngestionBatchStatus.RUNNING
        batch.started_at = timezone.now()
        batch.summary_stats = {
            "planned_items": len(planned),
            "season_label": planned[0].competition_season.season.label if planned else "",
        }
        batch.save(update_fields=["status", "started_at", "summary_stats", "updated_at"])
        items = [
            IngestionBatchItem(
                batch=batch,
                competition_season=entry.competition_season,
                status=IngestionBatchItemStatus.PENDING,
                planned_order=entry.planned_order,
                eta=entry.eta,
            )
            for entry in planned
        ]
        IngestionBatchItem.objects.bulk_create(items)

    created_items = list(batch.items.order_by("planned_order"))
    if send_tasks:
        for item in created_items:
            delay = max(0, int((item.eta - timezone.now()).total_seconds())) if item.eta else 0
            current_app.send_task(
                "ingestion.tasks.task_refresh_competition_season_item",
                args=[item.id],
                countdown=delay,
                queue="ingestion",
            )
        final_delay = max(
            [max(0, int((item.eta - timezone.now()).total_seconds())) for item in created_items] or [0]
        )
        current_app.send_task(
            "ingestion.tasks.task_finalize_daily_refresh_batch",
            args=[batch.id],
            countdown=final_delay + 60,
            queue="ingestion",
        )
    return {"ok": True, "batch_id": batch.id, "items": len(created_items)}


def claim_batch_item(item_id: int) -> IngestionBatchItem | None:
    with transaction.atomic():
        item = (
            IngestionBatchItem.objects.select_for_update()
            .select_related("batch", "competition_season", "competition_season__competition", "competition_season__season")
            .get(pk=item_id)
        )
        if item.status != IngestionBatchItemStatus.PENDING:
            return None
        if item.batch.status == IngestionBatchStatus.CANCELLED:
            item.status = IngestionBatchItemStatus.CANCELLED
            item.finished_at = timezone.now()
            item.save(update_fields=["status", "finished_at", "updated_at"])
            return None
        item.status = IngestionBatchItemStatus.RUNNING
        item.started_at = timezone.now()
        item.current_stage = "starting"
        item.error_detail = ""
        item.save(update_fields=["status", "started_at", "current_stage", "error_detail", "updated_at"])
        return item


def _create_run(kind: str, cs: CompetitionSeason) -> IngestionRun:
    return IngestionRun.objects.create(
        kind=kind,
        competition_season=cs,
        status=IngestionRunStatus.PENDING,
    )


def _record_stage(item: IngestionBatchItem, stage: str, run: IngestionRun | None = None) -> None:
    item.current_stage = stage
    update_fields = ["current_stage", "updated_at"]
    if run is not None:
        run.refresh_from_db()
        run_ids = dict(item.stage_run_ids or {})
        run_ids[stage] = run.id
        stats = dict(item.stage_stats or {})
        stats[stage] = run.stats or {}
        item.stage_run_ids = run_ids
        item.stage_stats = stats
        update_fields.extend(["stage_run_ids", "stage_stats"])
    item.save(update_fields=update_fields)


def _fail_item(item: IngestionBatchItem, stage: str, message: str) -> dict[str, Any]:
    item.status = IngestionBatchItemStatus.FAILED
    item.current_stage = stage
    item.error_detail = message[:8000]
    item.finished_at = timezone.now()
    item.save(update_fields=["status", "current_stage", "error_detail", "finished_at", "updated_at"])
    finalize_batch_if_complete(item.batch_id)
    return {"ok": False, "item_id": item.id, "stage": stage, "error": message}


def _run_stage(item: IngestionBatchItem, stage: str, kind: str, fn) -> IngestionRun:
    cs = item.competition_season
    _record_stage(item, stage)
    run = _create_run(kind, cs)
    fn(cs, run=run)
    _record_stage(item, stage, run)
    run.refresh_from_db()
    if run.status != IngestionRunStatus.SUCCESS:
        raise RuntimeError(run.error_detail or f"{stage} failed")
    return run


def _remaining_cap(batch: IngestionBatch) -> int | None:
    cap = int(getattr(settings, "STATBALLER_SOFASCORE_DAILY_REQUEST_CAP", 0) or 0)
    if cap <= 0:
        return None
    used = int((batch.summary_stats or {}).get("sofascore_request_count") or 0)
    return max(0, cap - used)


def _save_sofascore_metrics(item: IngestionBatchItem) -> None:
    metrics = snapshot_request_metrics()
    item.stage_stats = {
        **(item.stage_stats or {}),
        "sofascore_http": metrics,
    }
    item.save(update_fields=["stage_stats", "updated_at"])

    batch = item.batch
    summary = dict(batch.summary_stats or {})
    summary["sofascore_request_count"] = int(summary.get("sofascore_request_count") or 0) + int(
        metrics.get("request_count") or 0
    )
    status_counts = dict(summary.get("sofascore_status_counts") or {})
    for code, count in (metrics.get("status_counts") or {}).items():
        status_counts[code] = int(status_counts.get(code) or 0) + int(count or 0)
    summary["sofascore_status_counts"] = status_counts
    summary["sofascore_retry_count"] = int(summary.get("sofascore_retry_count") or 0) + int(
        metrics.get("retry_count") or 0
    )
    summary["sofascore_blocked_count"] = int(summary.get("sofascore_blocked_count") or 0) + int(
        metrics.get("blocked_count") or 0
    )
    summary["sofascore_proxy_enabled"] = bool(
        summary.get("sofascore_proxy_enabled") or metrics.get("proxy_enabled")
    )
    batch.summary_stats = summary
    batch.save(update_fields=["summary_stats", "updated_at"])


def execute_batch_item(item_id: int) -> dict[str, Any]:
    item = claim_batch_item(item_id)
    if item is None:
        return {"ok": False, "item_id": item_id, "skipped": True}
    cs = item.competition_season
    reset_request_metrics()
    set_request_cap(_remaining_cap(item.batch))
    try:
        _run_stage(item, "sofascore", IngestionKind.SOFASCORE, ingest_sofascore_slice)
        _run_stage(item, "sofascore_team", IngestionKind.SOFASCORE_TEAM, ingest_sofascore_team_slice)
        _save_sofascore_metrics(item)
        set_request_cap(None)

        if cs.supports_understat:
            _run_stage(item, "understat", IngestionKind.UNDERSTAT, ingest_understat_slice)
        _run_stage(item, "team_merge", IngestionKind.TEAM_MERGE, run_team_merge_job)
        _run_stage(item, "merge", IngestionKind.MERGE, run_merge_job)

        from ingestion.services.derived import materialize_derived_stats
        from ingestion.services.galaxy import materialize_galaxy_embeddings

        _run_stage(item, "derived", IngestionKind.DERIVED, materialize_derived_stats)
        _run_stage(item, "galaxy", IngestionKind.GALAXY, materialize_galaxy_embeddings)
        item.current_stage = "api_cache"
        item.save(update_fields=["current_stage", "updated_at"])
        cache_deleted = invalidate_materialized_api_payloads()
        item.stage_stats = {**(item.stage_stats or {}), "api_cache": {"deleted": cache_deleted}}
        item.status = IngestionBatchItemStatus.SUCCESS
        item.current_stage = "done"
        item.finished_at = timezone.now()
        item.error_detail = ""
        item.save(
            update_fields=[
                "stage_stats",
                "status",
                "current_stage",
                "finished_at",
                "error_detail",
                "updated_at",
            ]
        )
    except Exception as exc:  # noqa: BLE001
        if "sofascore_http" not in (item.stage_stats or {}):
            _save_sofascore_metrics(item)
        set_request_cap(None)
        return _fail_item(item, item.current_stage or "unknown", str(exc))

    finalize_batch_if_complete(item.batch_id)
    return {"ok": True, "item_id": item.id}


def _mark_remaining_cap_skips(batch: IngestionBatch) -> None:
    cap = int(getattr(settings, "STATBALLER_SOFASCORE_DAILY_REQUEST_CAP", 0) or 0)
    used = int((batch.summary_stats or {}).get("sofascore_request_count") or 0)
    if cap <= 0 or used < cap:
        return
    now = timezone.now()
    batch.items.filter(status=IngestionBatchItemStatus.PENDING).update(
        status=IngestionBatchItemStatus.SKIPPED,
        current_stage="sofascore",
        error_detail="Sofascore daily request cap reached.",
        finished_at=now,
    )


def finalize_batch_if_complete(batch_id: int) -> dict[str, Any]:
    batch = IngestionBatch.objects.get(pk=batch_id)
    if batch.status in FINAL_BATCH_STATUSES:
        return {"ok": True, "batch_id": batch.id, "status": batch.status}
    _mark_remaining_cap_skips(batch)
    counts = dict(batch.items.values("status").annotate(count=Count("id")).values_list("status", "count"))
    total = sum(counts.values())
    final_count = sum(counts.get(status, 0) for status in FINAL_ITEM_STATUSES)
    if total == 0 or final_count < total:
        return {"ok": False, "batch_id": batch.id, "status": batch.status, "counts": counts}
    return finalize_batch(batch.id)


def finalize_batch(batch_id: int) -> dict[str, Any]:
    with transaction.atomic():
        batch = IngestionBatch.objects.select_for_update().get(pk=batch_id)
        if batch.status in FINAL_BATCH_STATUSES:
            return {"ok": True, "batch_id": batch.id, "status": batch.status}
        counts = dict(batch.items.values("status").annotate(count=Count("id")).values_list("status", "count"))
        success_count = int(counts.get(IngestionBatchItemStatus.SUCCESS, 0) or 0)
        failed_count = int(counts.get(IngestionBatchItemStatus.FAILED, 0) or 0)
        skipped_count = int(counts.get(IngestionBatchItemStatus.SKIPPED, 0) or 0)
        summary = dict(batch.summary_stats or {})
        summary.update(
            {
                "items_total": sum(counts.values()),
                "items_success": success_count,
                "items_failed": failed_count,
                "items_skipped": skipped_count,
            }
        )
        batch.summary_stats = summary

        if success_count == 0:
            batch.status = IngestionBatchStatus.FAILED if failed_count else IngestionBatchStatus.SKIPPED
            batch.finished_at = timezone.now()
            batch.save(update_fields=["status", "summary_stats", "finished_at", "updated_at"])
            return {"ok": batch.status == IngestionBatchStatus.SKIPPED, "batch_id": batch.id, "status": batch.status}

    aggregate_result = materialize_aggregate_scopes(batch.id)
    batch.refresh_from_db()
    counts = dict(batch.items.values("status").annotate(count=Count("id")).values_list("status", "count"))
    if aggregate_result["ok"] and int(counts.get(IngestionBatchItemStatus.SUCCESS, 0) or 0) == sum(counts.values()):
        status = IngestionBatchStatus.SUCCESS
    elif aggregate_result["ok"]:
        status = IngestionBatchStatus.PARTIAL_SUCCESS
    else:
        status = IngestionBatchStatus.FAILED
    batch.status = status
    batch.finished_at = timezone.now()
    batch.error_detail = "" if aggregate_result["ok"] else aggregate_result.get("error", "")
    batch.save(update_fields=["status", "finished_at", "error_detail", "updated_at"])
    return {"ok": aggregate_result["ok"], "batch_id": batch.id, "status": batch.status}


def materialize_aggregate_scopes(batch_id: int) -> dict[str, Any]:
    batch = IngestionBatch.objects.get(pk=batch_id)
    successful_items = list(
        batch.items.select_related("competition_season__season").filter(status=IngestionBatchItemStatus.SUCCESS)
    )
    if not successful_items:
        return {"ok": False, "error": "No successful league items; aggregate materialisation skipped."}
    season_labels = {item.competition_season.season.label for item in successful_items}
    if len(season_labels) != 1:
        return {"ok": False, "error": f"Successful items span multiple seasons: {sorted(season_labels)}"}
    season_label = next(iter(season_labels))
    from ingestion.services.galaxy import materialize_galaxy_scope

    aggregate_run_ids = dict(batch.aggregate_run_ids or {})
    try:
        for scope in ("BIG5", "ALL"):
            run = IngestionRun.objects.create(
                kind=IngestionKind.GALAXY,
                competition_season=None,
                status=IngestionRunStatus.PENDING,
            )
            materialize_galaxy_scope(scope, season_label, run=run)
            run.refresh_from_db()
            aggregate_run_ids[scope] = run.id
            if run.status != IngestionRunStatus.SUCCESS:
                raise RuntimeError(run.error_detail or f"{scope} aggregate galaxy failed")
    except Exception as exc:  # noqa: BLE001
        batch.aggregate_run_ids = aggregate_run_ids
        batch.save(update_fields=["aggregate_run_ids", "updated_at"])
        return {"ok": False, "error": str(exc)}
    cache_deleted = invalidate_materialized_api_payloads()
    aggregate_run_ids["api_cache_deleted"] = cache_deleted
    batch.aggregate_run_ids = aggregate_run_ids
    batch.save(update_fields=["aggregate_run_ids", "updated_at"])
    return {"ok": True, "aggregate_run_ids": aggregate_run_ids}


def requeue_item(item_id: int, *, send_task: bool = True) -> IngestionBatchItem:
    item = IngestionBatchItem.objects.get(pk=item_id)
    if item.status not in {
        IngestionBatchItemStatus.FAILED,
        IngestionBatchItemStatus.SKIPPED,
        IngestionBatchItemStatus.CANCELLED,
    }:
        raise ValueError(f"Only failed/skipped/cancelled items can be requeued; got {item.status}.")
    item.status = IngestionBatchItemStatus.PENDING
    item.current_stage = ""
    item.error_detail = ""
    item.finished_at = None
    item.started_at = None
    item.save(update_fields=["status", "current_stage", "error_detail", "finished_at", "started_at", "updated_at"])
    if send_task:
        current_app.send_task(
            "ingestion.tasks.task_refresh_competition_season_item",
            args=[item.id],
            queue="ingestion",
        )
    return item
