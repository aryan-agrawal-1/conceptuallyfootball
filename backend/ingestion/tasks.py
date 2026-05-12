from celery import shared_task

from ingestion.models import CompetitionSeason, IngestionKind, IngestionRun, IngestionRunStatus
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
    return {
        "ok": galaxy_run.status == IngestionRunStatus.SUCCESS,
        "run_id": galaxy_run.id,
        "error": galaxy_run.error_detail,
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


@shared_task
def task_refresh_competition_season_item(batch_item_id: int) -> dict:
    return execute_batch_item(batch_item_id)


@shared_task
def task_finalize_daily_refresh_batch(batch_id: int) -> dict:
    return finalize_batch_if_complete(batch_id)
