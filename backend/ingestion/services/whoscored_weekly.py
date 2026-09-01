from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from time import monotonic
from typing import Iterable

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ingestion.models import (
    CompetitionSeason,
    IngestionBatch,
    IngestionBatchItem,
    IngestionBatchItemStatus,
    IngestionBatchStatus,
    IngestionKind,
    IngestionRun,
    IngestionRunStatus,
    Provider,
    ProviderMatch,
    ProviderMatchStatus,
    ProviderPayloadLifecycle,
)
from ingestion.services.event_profiles import materialize_event_profiles
from ingestion.services.player_role_orchestration import run_player_role_materialization
from ingestion.services.whoscored_client import (
    SoccerdataWhoScoredClient,
    SourceMatch,
    WhoScoredProviderClient,
    WhoScoredSourceConfig,
    safe_failure_evidence,
)
from ingestion.services.whoscored_lifecycle import (
    WhoScoredAccessCutoffError,
    WhoScoredLifecycleService,
    WhoScoredMatchResult,
    WhoScoredRequestController,
)


NEW_REASON = "new_completed"
SETTLEMENT_REASON = "settlement_due"
CORRECTION_REASON = "correction_window"


@dataclass(frozen=True)
class WeeklyCandidate:
    provider_match: ProviderMatch
    reason: str
    force: bool


def completion_grace() -> timedelta:
    return timedelta(
        hours=int(getattr(settings, "STATBALLER_WHOSCORED_COMPLETION_GRACE_HOURS", 3))
    )


def correction_window() -> timedelta:
    return timedelta(
        days=int(getattr(settings, "STATBALLER_WHOSCORED_CORRECTION_WINDOW_DAYS", 14))
    )


def recovery_window() -> timedelta:
    return timedelta(
        days=int(getattr(settings, "STATBALLER_WHOSCORED_RECOVERY_WINDOW_DAYS", 28))
    )


def settlement_delay() -> timedelta:
    return timedelta(
        hours=int(getattr(settings, "STATBALLER_WHOSCORED_SETTLEMENT_DELAY_HOURS", 12))
    )


def candidate_reason(
    source_match: SourceMatch,
    provider_match: ProviderMatch | None,
    *,
    now,
    correction_cutoff=None,
) -> str | None:
    if source_match.status.strip().lower() != ProviderMatchStatus.COMPLETED:
        return None
    if source_match.kickoff_at is None or source_match.kickoff_at + completion_grace() > now:
        return None
    if provider_match is None or not hasattr(provider_match, "payload"):
        return NEW_REASON if source_match.kickoff_at >= now - recovery_window() else None
    payload = provider_match.payload
    if payload.lifecycle_state == ProviderPayloadLifecycle.PRELIMINARY:
        if payload.preliminary_fetched_at is None:
            return SETTLEMENT_REASON
        return (
            SETTLEMENT_REASON
            if payload.preliminary_fetched_at + settlement_delay() <= now
            else None
        )
    if (
        source_match.kickoff_at >= now - correction_window()
        and (
            correction_cutoff is None
            or payload.final_fetched_at is None
            or payload.final_fetched_at < correction_cutoff
        )
    ):
        return CORRECTION_REASON
    return None


def due_settlement_matches(
    competition_season: CompetitionSeason,
    *,
    now=None,
) -> list[ProviderMatch]:
    current = now or timezone.now()
    return list(
        ProviderMatch.objects.filter(
            competition_season=competition_season,
            provider=Provider.WHOSCORED,
            status=ProviderMatchStatus.COMPLETED,
            payload__lifecycle_state=ProviderPayloadLifecycle.PRELIMINARY,
            payload__preliminary_fetched_at__lte=current - settlement_delay(),
        )
        .select_related("payload")
        .order_by("kickoff_at", "provider_match_id")
    )


def select_weekly_candidates(
    competition_season: CompetitionSeason,
    source_matches: Iterable[SourceMatch],
    lifecycle: WhoScoredLifecycleService,
    *,
    now=None,
    correction_cutoff=None,
) -> list[WeeklyCandidate]:
    current = now or timezone.now()
    existing = {
        match.provider_match_id: match
        for match in ProviderMatch.objects.filter(
            competition_season=competition_season,
            provider=Provider.WHOSCORED,
        ).select_related("payload")
    }
    selected: list[WeeklyCandidate] = []
    for source_match in sorted(
        source_matches,
        key=lambda match: (match.kickoff_at or current, match.match_id),
    ):
        persisted = existing.get(str(source_match.match_id))
        reason = candidate_reason(
            source_match,
            persisted,
            now=current,
            correction_cutoff=correction_cutoff,
        )
        if reason is None:
            continue
        persisted = lifecycle.upsert_match(source_match)
        selected.append(
            WeeklyCandidate(
                provider_match=persisted,
                reason=reason,
                force=reason == CORRECTION_REASON,
            )
        )
    return selected


def process_candidates(
    competition_season: CompetitionSeason,
    candidates: Iterable[WeeklyCandidate],
    *,
    client: WhoScoredProviderClient,
    request_controller: WhoScoredRequestController | None = None,
    run: IngestionRun,
) -> dict:
    diagnostics: dict = {}
    lifecycle = WhoScoredLifecycleService(
        competition_season=competition_season,
        client=client,
        request_controller=request_controller,
        run=run,
        diagnostics=diagnostics,
    )
    results: list[WhoScoredMatchResult] = []
    failures: list[dict] = []
    reasons: dict[str, int] = {}
    access_cutoff = False
    for candidate in candidates:
        reasons[candidate.reason] = reasons.get(candidate.reason, 0) + 1
        try:
            results.append(
                lifecycle.process_match(
                    candidate.provider_match,
                    historical=False,
                    force=candidate.force,
                )
            )
        except WhoScoredAccessCutoffError as error:
            failures.append(
                {
                    "match_id": candidate.provider_match.provider_match_id,
                    **safe_failure_evidence(error, stage="match_navigation", headless=True),
                }
            )
            access_cutoff = True
            break
        except Exception as error:  # isolate one match from its neighbours
            failures.append(
                {
                    "match_id": candidate.provider_match.provider_match_id,
                    **safe_failure_evidence(error, stage="match_processing", headless=True),
                }
            )

    actions: dict[str, int] = {}
    affected_players: set[int] = set()
    affected_teams: set[int] = set()
    for result in results:
        actions[result.action] = actions.get(result.action, 0) + 1
        if result.events_replaced:
            affected_players.update(result.affected_player_ids)
            affected_teams.update(result.affected_team_ids)
    controller_stats = lifecycle.request_controller.stats
    return {
        "selected": sum(reasons.values()),
        "selection_reasons": reasons,
        "match_actions": actions,
        "match_detail_requests": controller_stats.requests,
        "retries": controller_stats.retries,
        "access_cutoff": access_cutoff,
        "failures": failures,
        "affected_player_ids": sorted(affected_players),
        "affected_team_ids": sorted(affected_teams),
        "events_changed": any(result.events_replaced for result in results),
        "normalized_event_count": sum(result.normalized_event_count for result in results),
        "pipeline": diagnostics,
    }


def default_client(competition_season: CompetitionSeason) -> SoccerdataWhoScoredClient:
    return SoccerdataWhoScoredClient(
        WhoScoredSourceConfig(
            league=competition_season.whoscored_league,
            season=competition_season.whoscored_season,
            headless=True,
        )
    )


def run_weekly_acquisition(
    competition_season: CompetitionSeason,
    *,
    client: WhoScoredProviderClient | None = None,
    request_controller: WhoScoredRequestController | None = None,
    now=None,
    correction_cutoff=None,
) -> tuple[IngestionRun, dict]:
    current = now or timezone.now()
    run = IngestionRun.objects.create(
        kind=IngestionKind.WHOSCORED_FETCH,
        competition_season=competition_season,
        status=IngestionRunStatus.RUNNING,
        started_at=current,
    )
    started = monotonic()
    try:
        active_client = client or default_client(competition_season)
        source_matches = active_client.list_matches()
        selector_lifecycle = WhoScoredLifecycleService(
            competition_season=competition_season,
            client=active_client,
            request_controller=request_controller,
            run=run,
        )
        candidates = select_weekly_candidates(
            competition_season,
            source_matches,
            selector_lifecycle,
            now=current,
            correction_cutoff=correction_cutoff,
        )
        maximum_matches = int(
            getattr(settings, "STATBALLER_WHOSCORED_MAX_MATCHES_PER_RUN", 50)
        )
        if len(candidates) > maximum_matches:
            raise ValueError(
                f"Weekly WhoScored selected {len(candidates)} matches, above the "
                f"configured cap of {maximum_matches}."
            )
        stats = process_candidates(
            competition_season,
            candidates,
            client=active_client,
            request_controller=selector_lifecycle.request_controller,
            run=run,
        )
        stats["schedule_requests"] = 1
        stats["elapsed_seconds"] = round(monotonic() - started, 3)
        run.status = (
            IngestionRunStatus.FAILED if stats["failures"] else IngestionRunStatus.SUCCESS
        )
        run.error_detail = (
            f"{len(stats['failures'])} match failure(s); successful matches were retained."
            if stats["failures"]
            else ""
        )
        run.stats = stats
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_detail", "stats", "finished_at"])
        return run, stats
    except Exception as error:
        run.status = IngestionRunStatus.FAILED
        run.error_detail = safe_failure_evidence(
            error, stage="schedule_navigation", headless=True
        )["message"]
        run.stats = {"elapsed_seconds": round(monotonic() - started, 3)}
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_detail", "stats", "finished_at"])
        raise


def run_due_settlements(
    competition_season: CompetitionSeason,
    *,
    client: WhoScoredProviderClient | None = None,
    request_controller: WhoScoredRequestController | None = None,
    now=None,
) -> tuple[IngestionRun | None, dict]:
    matches = due_settlement_matches(competition_season, now=now)
    if not matches:
        return None, {"selected": 0, "outcome": "no_op"}
    run = IngestionRun.objects.create(
        kind=IngestionKind.WHOSCORED_FETCH,
        competition_season=competition_season,
        status=IngestionRunStatus.RUNNING,
        started_at=now or timezone.now(),
    )
    active_client = client or default_client(competition_season)
    stats = process_candidates(
        competition_season,
        [WeeklyCandidate(match, SETTLEMENT_REASON, False) for match in matches],
        client=active_client,
        request_controller=request_controller,
        run=run,
    )
    run.status = IngestionRunStatus.FAILED if stats["failures"] else IngestionRunStatus.SUCCESS
    run.error_detail = (
        f"{len(stats['failures'])} settlement failure(s)." if stats["failures"] else ""
    )
    run.stats = stats
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "error_detail", "stats", "finished_at"])
    return run, stats


def materialize_changed_entities(
    competition_season: CompetitionSeason,
    acquisition_stats: dict,
) -> dict:
    if not acquisition_stats.get("events_changed"):
        return {"outcome": "no_op"}
    player_ids = acquisition_stats.get("affected_player_ids") or []
    team_ids = acquisition_stats.get("affected_team_ids") or []
    profile_run = IngestionRun.objects.create(
        kind=IngestionKind.EVENT_PROFILES,
        competition_season=competition_season,
        status=IngestionRunStatus.PENDING,
    )
    profile_result = materialize_event_profiles(
        competition_season,
        run=profile_run,
        affected_player_ids=player_ids,
        affected_team_ids=team_ids,
    )
    profile_run.refresh_from_db()
    if profile_result is None or profile_run.status != IngestionRunStatus.SUCCESS:
        raise RuntimeError(profile_run.error_detail or "Event-profile refresh failed.")
    role_result = run_player_role_materialization(
        competition_season,
        affected_player_ids=player_ids,
        affected_team_ids=team_ids,
    )
    return {
        "outcome": "rebuilt",
        "event_profile_run_id": profile_run.id,
        "player_profiles": profile_result.player_rows,
        "team_profiles": profile_result.team_rows,
        "player_role_run_id": role_result["run_id"],
        "roles": role_result["scoring"]["published_roles"],
    }


def weekly_refresh_enabled() -> bool:
    return bool(getattr(settings, "STATBALLER_WHOSCORED_WEEKLY_ENABLED", False))


def weekly_competition_seasons() -> list[CompetitionSeason]:
    return list(
        CompetitionSeason.objects.select_related("competition", "season")
        .filter(has_whoscored=True, is_active=True, is_published=True)
        .order_by("competition__short_code", "season__sort_order")
    )


def plan_weekly_batch(*, day=None, manual: bool = False) -> IngestionBatch:
    target_day = day or timezone.localdate()
    if not manual and not weekly_refresh_enabled():
        batch, _ = IngestionBatch.objects.get_or_create(
            kind=IngestionBatch.KIND_WEEKLY_WHOSCORED,
            scheduled_for_date=target_day,
            manual=False,
            defaults={
                "status": IngestionBatchStatus.SKIPPED,
                "finished_at": timezone.now(),
                "error_detail": "Automatic weekly WhoScored refresh is disabled.",
            },
        )
        return batch
    values = {
        "kind": IngestionBatch.KIND_WEEKLY_WHOSCORED,
        "scheduled_for_date": target_day,
        "manual": manual,
        "status": IngestionBatchStatus.RUNNING,
        "planned_start_at": timezone.now(),
        "started_at": timezone.now(),
    }
    if manual:
        batch = IngestionBatch.objects.create(**values)
        created = True
    else:
        batch, created = IngestionBatch.objects.get_or_create(
            kind=values["kind"],
            scheduled_for_date=target_day,
            manual=False,
            defaults={
                "status": values["status"],
                "planned_start_at": values["planned_start_at"],
                "started_at": values["started_at"],
            },
        )
    if created:
        slices = weekly_competition_seasons()
        IngestionBatchItem.objects.bulk_create(
            [
                IngestionBatchItem(
                    batch=batch,
                    competition_season=competition_season,
                    planned_order=index,
                    eta=timezone.now(),
                )
                for index, competition_season in enumerate(slices, start=1)
            ]
        )
        batch.summary_stats = {"planned_items": len(slices)}
        update_fields = ["summary_stats", "updated_at"]
        if not slices:
            batch.status = IngestionBatchStatus.SKIPPED
            batch.finished_at = timezone.now()
            batch.error_detail = "No published WhoScored competition-seasons."
            update_fields.extend(["status", "finished_at", "error_detail"])
        batch.save(update_fields=update_fields)
    return batch


def execute_weekly_item(item_id: int) -> dict:
    with transaction.atomic():
        item = (
            IngestionBatchItem.objects.select_for_update()
            .select_related("batch", "competition_season")
            .get(pk=item_id)
        )
        if item.status != IngestionBatchItemStatus.PENDING:
            return {"ok": False, "item_id": item_id, "skipped": True}
        item.status = IngestionBatchItemStatus.RUNNING
        item.current_stage = "acquisition"
        item.started_at = timezone.now()
        item.save(
            update_fields=["status", "current_stage", "started_at", "updated_at"]
        )
    try:
        prior_acquisition = item.stage_stats.get("acquisition")
        resume_materialization = bool(
            prior_acquisition
            and prior_acquisition.get("events_changed")
            and "materialization" not in item.stage_stats
        )
        if resume_materialization:
            acquisition = prior_acquisition
            acquisition_failed = bool(acquisition.get("failures"))
        else:
            run, acquisition = run_weekly_acquisition(
                item.competition_season,
                correction_cutoff=item.batch.started_at,
            )
            item.stage_run_ids = {**item.stage_run_ids, "acquisition": run.id}
            item.stage_stats = {**item.stage_stats, "acquisition": acquisition}
            acquisition_failed = run.status != IngestionRunStatus.SUCCESS
        item.current_stage = "materialization"
        item.save(
            update_fields=[
                "current_stage",
                "stage_run_ids",
                "stage_stats",
                "updated_at",
            ]
        )
        materialization = materialize_changed_entities(
            item.competition_season,
            acquisition,
        )
        item.stage_stats = {**item.stage_stats, "materialization": materialization}
        item.save(update_fields=["stage_stats", "updated_at"])
        if acquisition_failed:
            raise RuntimeError(
                "WhoScored acquisition retained successful matches but requires retry."
            )
        item.status = IngestionBatchItemStatus.SUCCESS
        item.current_stage = "done"
        item.finished_at = timezone.now()
        item.error_detail = ""
        item.save(
            update_fields=[
                "status",
                "current_stage",
                "stage_stats",
                "finished_at",
                "error_detail",
                "updated_at",
            ]
        )
    except Exception as error:
        item.status = IngestionBatchItemStatus.FAILED
        item.error_detail = str(error)[:8000]
        item.finished_at = timezone.now()
        item.save(
            update_fields=["status", "error_detail", "finished_at", "updated_at"]
        )
        finalize_weekly_batch(item.batch_id)
        return {"ok": False, "item_id": item.id, "error": item.error_detail}
    finalize_weekly_batch(item.batch_id)
    return {"ok": True, "item_id": item.id}


def finalize_weekly_batch(batch_id: int) -> dict:
    batch = IngestionBatch.objects.get(pk=batch_id)
    if batch.status in {
        IngestionBatchStatus.SUCCESS,
        IngestionBatchStatus.PARTIAL_SUCCESS,
        IngestionBatchStatus.FAILED,
        IngestionBatchStatus.SKIPPED,
        IngestionBatchStatus.CANCELLED,
    }:
        return {"ok": True, "batch_id": batch.id, "status": batch.status}
    counts = {
        status: batch.items.filter(status=status).count()
        for status in IngestionBatchItemStatus.values
    }
    pending = counts[IngestionBatchItemStatus.PENDING] + counts[IngestionBatchItemStatus.RUNNING]
    if pending:
        return {"ok": False, "batch_id": batch.id, "status": batch.status}
    successes = counts[IngestionBatchItemStatus.SUCCESS]
    failures = counts[IngestionBatchItemStatus.FAILED]
    batch.status = (
        IngestionBatchStatus.SUCCESS
        if successes and not failures
        else IngestionBatchStatus.PARTIAL_SUCCESS
        if successes
        else IngestionBatchStatus.FAILED
    )
    batch.finished_at = timezone.now()
    batch.summary_stats = {
        **batch.summary_stats,
        "items_success": successes,
        "items_failed": failures,
    }
    batch.save(update_fields=["status", "finished_at", "summary_stats", "updated_at"])
    return {"ok": successes > 0, "batch_id": batch.id, "status": batch.status}
