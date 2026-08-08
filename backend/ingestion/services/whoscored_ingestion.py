from __future__ import annotations

"""Orchestration for one bounded WhoScored event-ingestion run."""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone as datetime_timezone
from time import monotonic
from typing import Any, Iterable

from django.utils import timezone

from ingestion.models import (
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    IngestionRunStatus,
    Provider,
    ProviderMatch,
    ProviderMatchStatus,
)
from ingestion.services.identity import build_event_identity_report
from ingestion.services.whoscored_client import (
    SourceMatch,
    WhoScoredProviderClient,
    WhoScoredSourceConfig,
    SoccerdataWhoScoredClient,
)
from ingestion.services.whoscored_lifecycle import (
    WhoScoredAccessCutoffError,
    WhoScoredLifecycleService,
    WhoScoredMatchFailure,
    WhoScoredRequestController,
)


SAFE_REQUEST_CAP = 50


@dataclass(frozen=True)
class WhoScoredIngestionOptions:
    last_completed: int | None = None
    match_id: int | None = None
    limit: int | None = None
    from_date: date | None = None
    to_date: date | None = None
    force: bool = False
    dry_run: bool = False
    allow_over_cap: bool = False


@dataclass
class WhoScoredIngestionResult:
    run: IngestionRun | None
    stats: dict[str, Any]
    failures: list[WhoScoredMatchFailure] = field(default_factory=list)


def validate_ingestion_options(options: WhoScoredIngestionOptions) -> None:
    if options.last_completed is not None and options.last_completed <= 0:
        raise ValueError("--last-completed must be positive.")
    if options.match_id is not None and options.match_id <= 0:
        raise ValueError("--match-id must be positive.")
    if options.limit is not None and options.limit <= 0:
        raise ValueError("--limit must be positive.")
    if (options.from_date is None) != (options.to_date is None):
        raise ValueError("--from-date and --to-date must be supplied together.")
    if options.from_date and options.to_date and options.from_date > options.to_date:
        raise ValueError("--from-date cannot be later than --to-date.")
    if options.match_id is not None and any(
        value is not None
        for value in (options.last_completed, options.limit, options.from_date, options.to_date)
    ):
        raise ValueError("--match-id cannot be combined with selection filters.")
    if options.last_completed is not None and any(
        value is not None for value in (options.limit, options.from_date, options.to_date)
    ):
        raise ValueError("--last-completed cannot be combined with --limit or date filters.")


def select_completed_source_matches(
    source_matches: Iterable[SourceMatch], options: WhoScoredIngestionOptions
) -> list[SourceMatch]:
    """Return one deterministic completed-match selection from a schedule."""
    completed = sorted(
        (match for match in source_matches if match.status.strip().lower() == "completed"),
        key=lambda match: (
            match.kickoff_at or datetime.min.replace(tzinfo=datetime_timezone.utc),
            match.match_id,
        ),
    )
    if options.match_id is not None:
        return [match for match in completed if match.match_id == options.match_id]
    if options.last_completed is not None:
        return completed[-options.last_completed :]
    if options.from_date is not None and options.to_date is not None:
        start = timezone.make_aware(datetime.combine(options.from_date, time.min))
        end = timezone.make_aware(datetime.combine(options.to_date, time.max))
        completed = [
            match
            for match in completed
            if match.kickoff_at is not None and start <= match.kickoff_at <= end
        ]
    if options.limit is not None:
        completed = completed[: options.limit]
    return completed


def select_completed_provider_matches(
    provider_matches: Iterable[ProviderMatch], options: WhoScoredIngestionOptions
) -> list[ProviderMatch]:
    """Apply the same selection semantics to persisted schedule rows for dry-runs."""
    completed = sorted(
        (match for match in provider_matches if match.status == ProviderMatchStatus.COMPLETED),
        key=lambda match: (match.kickoff_at, match.provider_match_id),
    )
    if options.match_id is not None:
        return [match for match in completed if match.provider_match_id == str(options.match_id)]
    if options.last_completed is not None:
        return completed[-options.last_completed :]
    if options.from_date is not None and options.to_date is not None:
        start = timezone.make_aware(datetime.combine(options.from_date, time.min))
        end = timezone.make_aware(datetime.combine(options.to_date, time.max))
        completed = [match for match in completed if start <= match.kickoff_at <= end]
    if options.limit is not None:
        completed = completed[: options.limit]
    return completed


def resolve_whoscored_competition_season(competition: str, season: str) -> CompetitionSeason:
    code = competition.strip().upper()
    label = season.strip()
    if not code or not label or code in {"BIG5", "ALL"}:
        raise ValueError("WhoScored ingestion requires one concrete competition and season.")
    rows = list(
        CompetitionSeason.objects.select_related("competition", "season")
        .filter(competition__short_code__iexact=code, season__label=label, is_active=True)
        .order_by("id")
    )
    if len(rows) != 1:
        raise ValueError("Unknown or ambiguous active competition and season combination.")
    if not rows[0].supports_whoscored:
        raise ValueError("WhoScored is not configured for this competition season.")
    return rows[0]


def run_whoscored_ingestion(
    *,
    competition_season: CompetitionSeason,
    options: WhoScoredIngestionOptions,
    client: WhoScoredProviderClient | None = None,
    request_controller: WhoScoredRequestController | None = None,
) -> WhoScoredIngestionResult:
    """Discover, select, and process a bounded group of completed matches.

    Dry runs deliberately use only the persisted schedule so they remain fully
    read-only and never initialize the provider client.
    """
    validate_ingestion_options(options)
    started_clock = monotonic()
    stats: dict[str, Any] = {
        "matches_considered": 0,
        "requests": 0,
        "schedule_requests": 0,
        "match_detail_requests": 0,
        "successful_fetches": 0,
        "raw_payload_reuses": 0,
        "retries": 0,
        "fetch_failures": 0,
        "validation_failures": 0,
        "normalized_event_count": 0,
        "mapped_player_events": 0,
        "unmapped_player_events": 0,
        "mapped_team_events": 0,
        "unmapped_team_events": 0,
        "coverage": {},
        "per_match_failures": [],
        "schedule_failures": [],
        "dry_run": options.dry_run,
    }
    if options.dry_run:
        selected_persisted_matches = select_completed_provider_matches(
            ProviderMatch.objects.filter(
                competition_season=competition_season,
                provider=Provider.WHOSCORED,
            ),
            options,
        )
        stats["matches_considered"] = len(selected_persisted_matches)
        stats["planned_match_ids"] = [match.provider_match_id for match in selected_persisted_matches]
        stats["elapsed_seconds"] = round(monotonic() - started_clock, 3)
        stats["outcome"] = "dry_run"
        return WhoScoredIngestionResult(run=None, stats=stats)

    run = IngestionRun.objects.create(
        kind=IngestionKind.WHOSCORED_FETCH,
        competition_season=competition_season,
        status=IngestionRunStatus.RUNNING,
        started_at=timezone.now(),
    )
    failures: list[WhoScoredMatchFailure] = []
    try:
        active_client = client or SoccerdataWhoScoredClient(
            WhoScoredSourceConfig(
                league=competition_season.whoscored_league,
                season=competition_season.whoscored_season,
            )
        )
        stats["schedule_requests"] = 1
        stats["requests"] = 1
        source_matches = active_client.list_matches(force_cache=options.force)
        selected_source_matches = select_completed_source_matches(source_matches, options)
        stats["matches_considered"] = len(selected_source_matches)
        if options.match_id is not None and not selected_source_matches:
            raise ValueError("Requested --match-id is not a completed match in this schedule.")
        if len(selected_source_matches) > SAFE_REQUEST_CAP and not options.allow_over_cap:
            raise ValueError(
                f"Selected {len(selected_source_matches)} matches, above the safe request cap "
                f"of {SAFE_REQUEST_CAP}; pass --allow-over-cap to continue."
            )

        lifecycle = WhoScoredLifecycleService(
            competition_season=competition_season,
            client=active_client,
            request_controller=request_controller,
            run=run,
        )
        # Persist the discovered schedule, but isolate malformed rows so an
        # unrelated fixture cannot prevent valid selected matches from running.
        selected_match_ids = {str(match.match_id) for match in selected_source_matches}
        local_matches: dict[str, ProviderMatch] = {}
        schedule_failures = []
        for source_match in source_matches:
            source_match_id = str(source_match.match_id)
            try:
                local_matches[source_match_id] = lifecycle.upsert_match(source_match)
            except Exception as error:
                failure = {
                    "match_id": source_match_id,
                    "error_type": "ScheduleValidationError",
                    "message": str(error)[:1000],
                    "selected": source_match_id in selected_match_ids,
                }
                schedule_failures.append(failure)
                if failure["selected"]:
                    failures.append(
                        WhoScoredMatchFailure(
                            source_match_id,
                            failure["error_type"],
                            failure["message"],
                        )
                    )
        stats["schedule_failures"] = schedule_failures
        selected_matches = [
            local_matches[str(match.match_id)]
            for match in selected_source_matches
            if str(match.match_id) in local_matches
        ]
        for provider_match in selected_matches:
            try:
                result = lifecycle.process_match(provider_match, historical=True, force=options.force)
            except WhoScoredAccessCutoffError as error:
                failures.append(WhoScoredMatchFailure(provider_match.provider_match_id, type(error).__name__, str(error)))
                stats["access_cutoff"] = True
                break
            except Exception as error:  # isolate malformed matches from their neighbours
                failures.append(WhoScoredMatchFailure(provider_match.provider_match_id, type(error).__name__, str(error)[:1000]))
                continue
            if result.action == "reused_final":
                stats["raw_payload_reuses"] += 1
            else:
                stats["successful_fetches"] += 1
            stats["normalized_event_count"] += result.normalized_event_count

        controller = lifecycle.request_controller
        stats["match_detail_requests"] = controller.stats.requests
        stats["requests"] = stats["schedule_requests"] + stats["match_detail_requests"]
        stats["retries"] = controller.stats.retries
        stats["validation_failures"] = sum(
            1 for failure in failures if "Normalization" in failure.error_type or "Validation" in failure.error_type
        )
        stats["fetch_failures"] = len(failures) - stats["validation_failures"]
        stats["per_match_failures"] = [
            {"match_id": failure.provider_match_id, "error_type": failure.error_type, "message": failure.message}
            for failure in failures
        ]
        identity_report = build_event_identity_report(competition_season)
        identity = identity_report.volume
        stats.update({
            "mapped_player_events": identity.mapped_player_events,
            "unmapped_player_events": identity.unmapped_player_events,
            "mapped_team_events": identity.mapped_team_events,
            "unmapped_team_events": identity.unmapped_team_events,
            "event_identity": identity_report.as_dict(),
        })
        completed_count = ProviderMatch.objects.filter(
            competition_season=competition_season, provider=Provider.WHOSCORED, status=ProviderMatchStatus.COMPLETED
        ).count()
        final_count = ProviderMatch.objects.filter(
            competition_season=competition_season, provider=Provider.WHOSCORED, payload__lifecycle_state="final"
        ).count()
        expected_count = competition_season.whoscored_expected_match_count
        stats["coverage"] = {
            "completed_matches": completed_count,
            "final_payloads": final_count,
            "expected_matches": expected_count,
            "completed_payload_coverage": (
                round(final_count / completed_count, 4) if completed_count else None
            ),
            "expected_match_coverage": (
                round(final_count / expected_count, 4) if expected_count else None
            ),
        }
        stats["elapsed_seconds"] = round(monotonic() - started_clock, 3)
        stats["outcome"] = (
            "success"
            if not failures
            else "access_cutoff"
            if stats.get("access_cutoff")
            else "partial_failure"
        )
        run.stats = stats
        run.status = IngestionRunStatus.SUCCESS if not failures else IngestionRunStatus.FAILED
        run.error_detail = "" if not failures else f"{len(failures)} match failure(s); successful matches were retained."
        run.finished_at = timezone.now()
        run.save(update_fields=["stats", "status", "error_detail", "finished_at"])
        return WhoScoredIngestionResult(run=run, stats=stats, failures=failures)
    except Exception as error:
        stats["elapsed_seconds"] = round(monotonic() - started_clock, 3)
        stats["outcome"] = "fatal_configuration_failure"
        stats["fatal_error"] = type(error).__name__
        run.stats = stats
        run.status = IngestionRunStatus.FAILED
        run.error_detail = str(error)[:1000]
        run.finished_at = timezone.now()
        run.save(update_fields=["stats", "status", "error_detail", "finished_at"])
        raise
