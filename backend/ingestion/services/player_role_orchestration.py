"""Production entry point for exclusive, observable player-role runs."""

from __future__ import annotations

from contextlib import contextmanager
from time import monotonic
from uuid import uuid4

from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from ingestion.models import IngestionKind, IngestionRun, IngestionRunStatus
from ingestion.services.player_role_aggregation import DEFAULT_MATCH_BATCH_SIZE
from ingestion.services.player_role_diagnostics import record_stage, sample_memory


ROLE_LOCK_NAMESPACE = 1_221_005
ROLE_LOCK_TIMEOUT_SECONDS = 6 * 60 * 60


class RoleMaterializationAlreadyRunning(RuntimeError):
    pass


class QueryCounter:
    def __init__(self):
        self.count = 0

    def __call__(self, execute, sql, params, many, context):
        self.count += 1
        return execute(sql, params, many, context)


@contextmanager
def competition_season_role_lock(competition_season_id: int):
    """Use a PostgreSQL session lock in production and cache locking in tests."""

    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock(%s, %s)",
                [ROLE_LOCK_NAMESPACE, competition_season_id],
            )
            acquired = bool(cursor.fetchone()[0])
        if not acquired:
            raise RoleMaterializationAlreadyRunning(
                f"A player-role job is already running for competition-season {competition_season_id}."
            )
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_unlock(%s, %s)",
                    [ROLE_LOCK_NAMESPACE, competition_season_id],
                )
        return

    key = f"player-role-materialization:{competition_season_id}"
    token = uuid4().hex
    if not cache.add(key, token, timeout=ROLE_LOCK_TIMEOUT_SECONDS):
        raise RoleMaterializationAlreadyRunning(
            f"A player-role job is already running for competition-season {competition_season_id}."
        )
    try:
        yield
    finally:
        if cache.get(key) == token:
            cache.delete(key)


def requested_mode(*, score_only: bool, score_events_only: bool, affected: bool) -> str:
    if score_only:
        return "score_only"
    if score_events_only:
        return "score_events_only"
    return "affected" if affected else "full"


def run_player_role_materialization(
    competition_season,
    *,
    affected_player_ids=None,
    affected_team_ids=None,
    score_only: bool = False,
    score_events_only: bool = False,
    batch_size: int = DEFAULT_MATCH_BATCH_SIZE,
    run: IngestionRun | None = None,
) -> dict:
    """Run one role job, persist diagnostics, and reject same-season overlap."""

    if score_only and score_events_only:
        raise ValueError("score_only and score_events_only are mutually exclusive.")
    affected_player_ids = (
        tuple(int(value) for value in affected_player_ids)
        if affected_player_ids is not None else None
    )
    affected_team_ids = (
        tuple(int(value) for value in affected_team_ids)
        if affected_team_ids is not None else None
    )
    if run is None:
        run = IngestionRun.objects.create(
            kind=IngestionKind.PLAYER_ROLES,
            competition_season=competition_season,
            status=IngestionRunStatus.PENDING,
        )
    if run.kind != IngestionKind.PLAYER_ROLES:
        raise ValueError("Player-role materialization requires a player-role ingestion run.")
    if run.competition_season_id != competition_season.pk:
        raise ValueError("Player-role run belongs to another competition season.")

    affected = affected_player_ids is not None or affected_team_ids is not None
    diagnostics = {
        "requested_mode": requested_mode(
            score_only=score_only,
            score_events_only=score_events_only,
            affected=affected,
        ),
        "requested_affected_player_count": len(set(affected_player_ids or [])),
        "requested_affected_team_count": len(set(affected_team_ids or [])),
        "match_batch_size": batch_size,
        "stage_timings_seconds": {},
        "rows_processed": {},
        "rss_samples_mb": {},
    }
    started_at = monotonic()
    sample_memory(diagnostics, "start")
    try:
        with competition_season_role_lock(competition_season.pk):
            run.status = IngestionRunStatus.RUNNING
            run.started_at = timezone.now()
            run.stats = diagnostics
            run.save(update_fields=["status", "started_at", "stats"])
            query_counter = QueryCounter()
            from ingestion.services.player_season_roles import materialize_player_season_roles

            with connection.execute_wrapper(query_counter):
                result = materialize_player_season_roles(
                    competition_season,
                    affected_player_ids=affected_player_ids,
                    affected_team_ids=affected_team_ids,
                    score_only=score_only,
                    score_events_only=score_events_only,
                    batch_size=batch_size,
                    diagnostics=diagnostics,
                )
            diagnostics["query_count"] = query_counter.count
            diagnostics["result"] = result
            record_stage(diagnostics, "total", started_at)
            run.status = IngestionRunStatus.SUCCESS
            run.finished_at = timezone.now()
            run.error_detail = ""
            run.stats = diagnostics
            run.save(update_fields=["status", "finished_at", "error_detail", "stats"])
            return {"run_id": run.id, **result, "diagnostics": diagnostics}
    except Exception as exc:
        diagnostics["error_type"] = type(exc).__name__
        diagnostics["error"] = str(exc)
        record_stage(diagnostics, "total", started_at)
        run.status = IngestionRunStatus.FAILED
        run.finished_at = timezone.now()
        run.error_detail = str(exc)
        run.stats = diagnostics
        run.save(update_fields=["status", "finished_at", "error_detail", "stats"])
        raise
