from datetime import timedelta

from celery import current_app, shared_task

from ingestion.models import (
    CompetitionSeason,
    IngestionBatchItem,
    IngestionKind,
    IngestionRun,
    IngestionRunStatus,
    PlayerDataMode,
)
from pathlib import Path

from django.conf import settings

from ingestion.services.ingest import (
    ingest_sofascore_slice,
    ingest_sofascore_team_slice,
    ingest_understat_slice,
    run_merge_job,
    run_team_merge_job,
)
from ingestion.services.orchestration import (
    enqueue_due_daily_batch,
    execute_batch_item,
    finalize_batch_if_complete,
)
from ingestion.services.reep_csv import sync_reep_from_csv_dir
from ingestion.services.reep_sync import default_reep_path, sync_reep_from_path


def _run_player_materialization_chain(cs: CompetitionSeason) -> dict:
    from ingestion.services.derived import materialize_derived_stats
    from ingestion.services.galaxy import materialize_galaxy_embeddings

    run = IngestionRun.objects.create(
        kind=IngestionKind.MERGE,
        competition_season=cs,
        status=IngestionRunStatus.PENDING,
    )
    run_merge_job(cs, run=run)
    run.refresh_from_db()
    if run.status != IngestionRunStatus.SUCCESS:
        return {"ok": False, "run_id": run.id, "error": run.error_detail}

    derived_run = IngestionRun.objects.create(
        kind=IngestionKind.DERIVED,
        competition_season=cs,
        status=IngestionRunStatus.PENDING,
    )
    materialize_derived_stats(cs, run=derived_run)
    derived_run.refresh_from_db()
    if derived_run.status != IngestionRunStatus.SUCCESS:
        return {"ok": False, "run_id": derived_run.id, "error": derived_run.error_detail}

    galaxy_run = IngestionRun.objects.create(
        kind=IngestionKind.GALAXY,
        competition_season=cs,
        status=IngestionRunStatus.PENDING,
    )
    materialize_galaxy_embeddings(cs, run=galaxy_run)
    galaxy_run.refresh_from_db()
    galaxy_nonfatal = (
        cs.player_data_mode == PlayerDataMode.SOFASCORE_ONLY
        and galaxy_run.status != IngestionRunStatus.SUCCESS
    )
    return {
        "ok": galaxy_run.status == IngestionRunStatus.SUCCESS or galaxy_nonfatal,
        "run_id": galaxy_run.id,
        "error": galaxy_run.error_detail,
        "galaxy_nonfatal": galaxy_nonfatal,
    }


@shared_task
def task_sync_reep() -> dict:
    csv_dir = (getattr(settings, "STATBALLER_REEP_CSV_DIR", "") or "").strip()
    if csv_dir:
        p = Path(csv_dir).expanduser()
        if not p.is_dir():
            return {"ok": False, "error": f"STATBALLER_REEP_CSV_DIR not a directory: {p}"}
        stats = sync_reep_from_csv_dir(p)
        return {"ok": True, "stats": stats, "source": "csv"}
    path = default_reep_path()
    if not path or not path.is_file():
        return {"ok": False, "error": "Set STATBALLER_REEP_CSV_DIR or STATBALLER_REEP_DATA_PATH"}
    stats = sync_reep_from_path(path)
    return {"ok": True, "stats": stats, "source": "json"}


@shared_task
def task_ingest_understat(competition_season_id: int) -> dict:
    cs = CompetitionSeason.objects.get(pk=competition_season_id)
    run = IngestionRun.objects.create(
        kind=IngestionKind.UNDERSTAT,
        competition_season=cs,
        status=IngestionRunStatus.PENDING,
    )
    ingest_understat_slice(cs, run=run)
    run.refresh_from_db()
    return {"ok": run.status == IngestionRunStatus.SUCCESS, "run_id": run.id, "error": run.error_detail}


@shared_task
def task_ingest_sofascore(competition_season_id: int) -> dict:
    cs = CompetitionSeason.objects.get(pk=competition_season_id)
    run = IngestionRun.objects.create(
        kind=IngestionKind.SOFASCORE,
        competition_season=cs,
        status=IngestionRunStatus.PENDING,
    )
    ingest_sofascore_slice(cs, run=run)
    run.refresh_from_db()
    return {"ok": run.status == IngestionRunStatus.SUCCESS, "run_id": run.id, "error": run.error_detail}


@shared_task
def task_ingest_sofascore_teams(competition_season_id: int) -> dict:
    cs = CompetitionSeason.objects.get(pk=competition_season_id)
    run = IngestionRun.objects.create(
        kind=IngestionKind.SOFASCORE_TEAM,
        competition_season=cs,
        status=IngestionRunStatus.PENDING,
    )
    ingest_sofascore_team_slice(cs, run=run)
    run.refresh_from_db()
    if run.status != IngestionRunStatus.SUCCESS:
        return {"ok": False, "run_id": run.id, "error": run.error_detail}

    merge_run = IngestionRun.objects.create(
        kind=IngestionKind.TEAM_MERGE,
        competition_season=cs,
        status=IngestionRunStatus.PENDING,
    )
    run_team_merge_job(cs, run=merge_run)
    merge_run.refresh_from_db()
    return {
        "ok": merge_run.status == IngestionRunStatus.SUCCESS,
        "run_id": merge_run.id,
        "error": merge_run.error_detail,
    }


@shared_task
def task_run_merge(competition_season_id: int) -> dict:
    cs = CompetitionSeason.objects.get(pk=competition_season_id)
    return _run_player_materialization_chain(cs)


@shared_task
def task_run_team_merge(competition_season_id: int) -> dict:
    cs = CompetitionSeason.objects.get(pk=competition_season_id)
    run = IngestionRun.objects.create(
        kind=IngestionKind.TEAM_MERGE,
        competition_season=cs,
        status=IngestionRunStatus.PENDING,
    )
    run_team_merge_job(cs, run=run)
    run.refresh_from_db()
    return {"ok": run.status == IngestionRunStatus.SUCCESS, "run_id": run.id, "error": run.error_detail}


@shared_task(queue="ingestion")
def task_materialize_player_season_roles(
    competition_season_id: int,
    affected_player_ids: list[int] | None = None,
    affected_team_ids: list[int] | None = None,
    score_only: bool = False,
    score_events_only: bool = False,
) -> dict:
    """Refresh role snapshots and scores after event-profile publication commits."""

    from ingestion.services.player_role_orchestration import run_player_role_materialization

    competition_season = CompetitionSeason.objects.get(pk=competition_season_id)
    return {
        "ok": True,
        **run_player_role_materialization(
            competition_season,
            affected_player_ids=affected_player_ids,
            affected_team_ids=affected_team_ids,
            score_only=score_only,
            score_events_only=score_events_only,
        ),
    }


@shared_task
def task_repair_slice_materializations(competition_season_id: int) -> dict:
    cs = CompetitionSeason.objects.get(pk=competition_season_id)
    team_run = IngestionRun.objects.create(
        kind=IngestionKind.TEAM_MERGE,
        competition_season=cs,
        status=IngestionRunStatus.PENDING,
    )
    run_team_merge_job(cs, run=team_run)
    team_run.refresh_from_db()
    if team_run.status != IngestionRunStatus.SUCCESS:
        return {"ok": False, "run_id": team_run.id, "error": team_run.error_detail}

    result = _run_player_materialization_chain(cs)
    result["team_merge_run_id"] = team_run.id
    return result


@shared_task
def task_plan_daily_refresh() -> dict:
    return enqueue_due_daily_batch()


def ingestion_lease_ttl() -> timedelta:
    seconds = int(getattr(settings, "STATBALLER_INGESTION_LEASE_TTL_SECONDS", 9000))
    return timedelta(seconds=seconds)


def acquire_whoscored_task_leases(task, competition_season_id: int):
    from ingestion.services.ingestion_leases import acquire_lease, release_lease

    heavy = acquire_lease("heavy-maintenance", ttl=ingestion_lease_ttl())
    if heavy is None:
        raise task.retry(countdown=300)
    scope = acquire_lease(
        f"whoscored:{competition_season_id}",
        ttl=ingestion_lease_ttl(),
    )
    if scope is None:
        release_lease(heavy)
        raise task.retry(countdown=300)
    return heavy, scope


def release_whoscored_task_leases(heavy, scope) -> None:
    from ingestion.services.ingestion_leases import release_lease

    release_lease(scope)
    release_lease(heavy)


@shared_task(bind=True, max_retries=None)
def task_refresh_competition_season_item(self, batch_item_id: int) -> dict:
    from ingestion.services.ingestion_leases import acquire_lease, release_lease

    lease = acquire_lease("heavy-maintenance", ttl=ingestion_lease_ttl())
    if lease is None:
        raise self.retry(countdown=300)
    try:
        return execute_batch_item(batch_item_id)
    finally:
        release_lease(lease)


@shared_task
def task_finalize_daily_refresh_batch(batch_id: int) -> dict:
    return finalize_batch_if_complete(batch_id)


@shared_task
def task_plan_weekly_whoscored() -> dict:
    from ingestion.services.whoscored_weekly import plan_weekly_batch

    batch = plan_weekly_batch()
    if batch.status != "running":
        return {"ok": False, "batch_id": batch.id, "status": batch.status}
    pending = list(batch.items.filter(status="pending").order_by("planned_order"))
    for item in pending:
        current_app.send_task(
            "ingestion.tasks.task_run_weekly_whoscored_item",
            args=[item.id],
            queue="whoscored",
        )
    return {"ok": True, "batch_id": batch.id, "items": len(pending)}


@shared_task(bind=True, max_retries=None, soft_time_limit=6900, time_limit=7200)
def task_run_weekly_whoscored_item(self, batch_item_id: int) -> dict:
    from ingestion.services.whoscored_weekly import execute_weekly_item

    item = IngestionBatchItem.objects.select_related("competition_season").get(
        pk=batch_item_id
    )
    heavy, scope = acquire_whoscored_task_leases(
        self,
        item.competition_season_id,
    )
    try:
        return execute_weekly_item(batch_item_id)
    finally:
        release_whoscored_task_leases(heavy, scope)


@shared_task
def task_plan_due_whoscored_settlements(manual: bool = False) -> dict:
    from ingestion.services.ingestion_leases import acquire_lease
    from ingestion.services.whoscored_weekly import (
        due_settlement_matches,
        weekly_competition_seasons,
        weekly_refresh_enabled,
    )

    if not manual and not weekly_refresh_enabled():
        return {"ok": False, "status": "disabled", "items": 0}
    queued = []
    for competition_season in weekly_competition_seasons():
        if not due_settlement_matches(competition_season):
            continue
        lease = acquire_lease(
            f"whoscored-settlement-queued:{competition_season.id}",
            ttl=ingestion_lease_ttl(),
        )
        if lease is None:
            continue
        current_app.send_task(
            "ingestion.tasks.task_run_due_whoscored_settlements",
            args=[competition_season.id, lease.owner_token],
            queue="whoscored",
        )
        queued.append(competition_season.id)
    return {"ok": True, "items": len(queued), "competition_season_ids": queued}


@shared_task(bind=True, max_retries=None, soft_time_limit=6900, time_limit=7200)
def task_run_due_whoscored_settlements(
    self,
    competition_season_id: int,
    queued_owner_token: str,
) -> dict:
    from ingestion.services.ingestion_leases import LeaseHandle, release_lease
    from ingestion.services.whoscored_weekly import (
        materialize_changed_entities,
        run_due_settlements,
    )

    queued = LeaseHandle(
        f"whoscored-settlement-queued:{competition_season_id}",
        queued_owner_token,
    )
    heavy, scope = acquire_whoscored_task_leases(self, competition_season_id)
    try:
        competition_season = CompetitionSeason.objects.get(pk=competition_season_id)
        run, stats = run_due_settlements(competition_season)
        materialization = materialize_changed_entities(competition_season, stats)
        return {
            "ok": run is None or run.status == IngestionRunStatus.SUCCESS,
            "run_id": run.id if run else None,
            "stats": stats,
            "materialization": materialization,
        }
    finally:
        release_whoscored_task_leases(heavy, scope)
        release_lease(queued)
