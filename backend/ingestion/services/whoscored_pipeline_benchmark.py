from __future__ import annotations

import gzip
import hashlib
import json
import platform
import resource
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Callable, Iterator

from django import get_version as django_version
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, models

from ingestion.models import (
    PlayerSeasonEventProfile,
    PlayerSeasonRole,
    PlayerSeasonRoleFeatureSnapshot,
    IngestionKind,
    IngestionRun,
    Provider,
    ProviderMatch,
    ProviderMatchCarry,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchPayload,
    ProviderMatchPlayerInterval,
    ProviderMatchPlayerParticipation,
    ProviderMatchPlayerStateExposure,
    ProviderMatchPossession,
    ProviderMatchPossessionEvent,
    ProviderMatchPossessionParticipant,
    ProviderMatchTeamGameStateEpisode,
    ProviderMatchTeamGameStateExposure,
    TeamSeasonEventProfile,
)
from ingestion.services.whoscored_normalization import parse_match_payload


REPORT_VERSION = 1


class BenchmarkWriteError(RuntimeError):
    pass


def peak_rss_mb() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return round(value / divisor, 3)


@dataclass
class QueryMetrics:
    count: int = 0
    elapsed_seconds: float = 0.0


@contextmanager
def measured_read_only_queries(metrics: QueryMetrics) -> Iterator[None]:
    def wrapper(execute, sql, params, many, context):
        operation = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
        if operation not in {"SELECT", "WITH", "EXPLAIN", "SHOW", "SET"}:
            raise BenchmarkWriteError(
                f"Benchmark attempted a database write: {operation or 'unknown SQL'}"
            )
        started = perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            metrics.count += 1
            metrics.elapsed_seconds += perf_counter() - started

    with connection.execute_wrapper(wrapper):
        yield


def benchmark_stage(name: str, operation: Callable[[], dict]) -> dict:
    metrics = QueryMetrics()
    rss_before = peak_rss_mb()
    started = perf_counter()
    with measured_read_only_queries(metrics):
        result = operation()
    return {
        "name": name,
        "wall_seconds": round(perf_counter() - started, 6),
        "peak_rss_mb": peak_rss_mb(),
        "rss_before_mb": rss_before,
        "database_queries": metrics.count,
        "database_query_seconds": round(metrics.elapsed_seconds, 6),
        "result": result,
    }


def scope_inventory(competition_season) -> dict:
    matches = ProviderMatch.objects.filter(
        provider=Provider.WHOSCORED,
        competition_season=competition_season,
    )
    match_filter = {"provider_match__in": matches}
    participation_filter = {
        "participation__provider_match__in": matches,
    }
    counts = {
        "matches": matches.count(),
        "payloads": ProviderMatchPayload.objects.filter(**match_filter).count(),
        "events": ProviderMatchEvent.objects.filter(**match_filter).count(),
        "game_state_audits": ProviderMatchGameState.objects.filter(**match_filter).count(),
        "team_state_episodes": ProviderMatchTeamGameStateEpisode.objects.filter(**match_filter).count(),
        "team_state_exposures": ProviderMatchTeamGameStateExposure.objects.filter(**match_filter).count(),
        "player_participations": ProviderMatchPlayerParticipation.objects.filter(**match_filter).count(),
        "player_intervals": ProviderMatchPlayerInterval.objects.filter(**participation_filter).count(),
        "player_state_exposures": ProviderMatchPlayerStateExposure.objects.filter(
            player_interval__participation__provider_match__in=matches
        ).count(),
        "carries": ProviderMatchCarry.objects.filter(**match_filter).count(),
        "possessions": ProviderMatchPossession.objects.filter(**match_filter).count(),
        "possession_events": ProviderMatchPossessionEvent.objects.filter(
            possession__provider_match__in=matches
        ).count(),
        "possession_participants": ProviderMatchPossessionParticipant.objects.filter(
            possession__provider_match__in=matches
        ).count(),
        "player_event_profiles": PlayerSeasonEventProfile.objects.filter(
            competition_season=competition_season
        ).count(),
        "team_event_profiles": TeamSeasonEventProfile.objects.filter(
            competition_season=competition_season
        ).count(),
        "player_role_feature_snapshots": PlayerSeasonRoleFeatureSnapshot.objects.filter(
            competition_season=competition_season
        ).count(),
        "player_roles": PlayerSeasonRole.objects.filter(
            competition_season=competition_season
        ).count(),
    }
    payloads = ProviderMatchPayload.objects.filter(**match_filter)
    payload_totals = payloads.aggregate(
        compressed_bytes=models.Sum("payload_size_bytes"),
        uncompressed_bytes=models.Sum("uncompressed_size_bytes"),
    )
    return {
        "row_counts": counts,
        "payload_bytes": {key: int(value or 0) for key, value in payload_totals.items()},
        "database_storage": database_storage(),
    }


def database_storage() -> dict:
    if connection.vendor != "postgresql":
        return {"vendor": connection.vendor, "available": False}
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database(), pg_database_size(current_database())")
        database_name, database_bytes = cursor.fetchone()
        cursor.execute(
            """
            SELECT relname, pg_total_relation_size(relid),
                   pg_relation_size(relid), pg_indexes_size(relid), n_live_tup
            FROM pg_stat_user_tables
            WHERE relname LIKE 'ingestion_%'
            ORDER BY pg_total_relation_size(relid) DESC, relname
            """
        )
        relations = [
            {
                "relation": row[0],
                "total_bytes": row[1],
                "table_bytes": row[2],
                "index_bytes": row[3],
                "estimated_live_rows": row[4],
            }
            for row in cursor.fetchall()
        ]
    return {
        "vendor": connection.vendor,
        "available": True,
        "database": database_name,
        "database_bytes": database_bytes,
        "ingestion_relations_total_bytes": sum(row["total_bytes"] for row in relations),
        "relations": relations,
    }


def benchmark_stored_payload_parse(competition_season, *, limit: int | None = None) -> dict:
    payloads = (
        ProviderMatchPayload.objects.filter(
            provider_match__provider=Provider.WHOSCORED,
            provider_match__competition_season=competition_season,
        )
        .select_related("provider_match")
        .order_by("provider_match__kickoff_at", "provider_match__provider_match_id")
    )
    if limit is not None:
        payloads = payloads[:limit]
    digest = hashlib.sha256()
    match_count = event_count = compressed_bytes = uncompressed_bytes = 0
    for stored in payloads.iterator(chunk_size=10):
        wrapped_bytes = gzip.decompress(bytes(stored.payload_gzip))
        normalized = parse_match_payload(json.loads(wrapped_bytes))
        digest.update(stored.provider_match.provider_match_id.encode("utf-8"))
        digest.update(b":")
        digest.update(str(len(normalized.events)).encode("ascii"))
        digest.update(b":")
        digest.update(stored.payload_sha256.encode("ascii"))
        digest.update(b"\n")
        match_count += 1
        event_count += len(normalized.events)
        compressed_bytes += int(stored.payload_size_bytes or 0)
        uncompressed_bytes += len(wrapped_bytes)
    return {
        "matches": match_count,
        "normalized_events": event_count,
        "compressed_payload_bytes": compressed_bytes,
        "uncompressed_payload_bytes": uncompressed_bytes,
        "aggregate_digest": digest.hexdigest(),
    }


def run_history(competition_season) -> dict:
    summaries = {}
    for kind in (
        IngestionKind.WHOSCORED_FETCH,
        IngestionKind.EVENT_PROFILES,
        IngestionKind.PLAYER_ROLES,
    ):
        run = (
            IngestionRun.objects.filter(
                competition_season=competition_season,
                kind=kind,
            )
            .order_by("-id")
            .first()
        )
        if run is None:
            summaries[kind] = None
            continue
        stats = run.stats or {}
        summary = {
            "run_id": run.id,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        }
        if kind == IngestionKind.WHOSCORED_FETCH:
            summary.update(
                {
                    key: stats.get(key)
                    for key in (
                        "outcome",
                        "elapsed_seconds",
                        "matches_considered",
                        "requests",
                        "successful_fetches",
                        "raw_payload_reuses",
                        "retries",
                        "normalized_event_count",
                        "coverage",
                        "pipeline",
                    )
                }
            )
            summary["event_identity"] = (stats.get("event_identity") or {}).get("volume")
        elif kind == IngestionKind.EVENT_PROFILES:
            summary.update(
                {
                    key: stats.get(key)
                    for key in (
                        "formula_version",
                        "coverage",
                        "public_complete",
                        "internal_pilot",
                        "player_profiles",
                        "team_profiles",
                        "pipeline",
                    )
                }
            )
            summary["event_identity"] = (stats.get("event_identity") or {}).get("volume")
        else:
            summary.update(
                {
                    key: stats.get(key)
                    for key in (
                        "requested_mode",
                        "match_batch_size",
                        "stage_timings_seconds",
                        "rows_processed",
                        "rss_samples_mb",
                        "peak_rss_mb",
                        "query_count",
                    )
                }
            )
        summaries[kind] = summary
    return summaries


def queryset_digest(queryset, *, order_by: tuple[str, ...], excluded: set[str]) -> dict:
    fields = [
        field.attname
        for field in queryset.model._meta.concrete_fields
        if field.name not in excluded and field.attname not in excluded
    ]
    digest = hashlib.sha256()
    count = 0
    for row in queryset.order_by(*order_by).values(*fields).iterator(chunk_size=250):
        digest.update(
            json.dumps(
                row,
                cls=DjangoJSONEncoder,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        digest.update(b"\n")
        count += 1
    return {"rows": count, "sha256": digest.hexdigest()}


def materialized_output_digests(competition_season) -> dict:
    common_excluded = {
        "id",
        "calculated_at",
        "created_at",
        "updated_at",
        "superseded_at",
        "materialized_ingestion_run",
        "materialized_ingestion_run_id",
        "is_current",
    }
    role_excluded = common_excluded | {"feature_snapshot", "feature_snapshot_id"}
    return {
        "player_event_profiles": queryset_digest(
            PlayerSeasonEventProfile.objects.filter(
                competition_season=competition_season,
                is_current=True,
            ),
            order_by=("player_id", "team_id", "split_type"),
            excluded=common_excluded,
        ),
        "team_event_profiles": queryset_digest(
            TeamSeasonEventProfile.objects.filter(
                competition_season=competition_season,
                is_current=True,
            ),
            order_by=("team_id",),
            excluded=common_excluded,
        ),
        "player_role_feature_snapshots": queryset_digest(
            PlayerSeasonRoleFeatureSnapshot.objects.filter(
                competition_season=competition_season,
                is_current=True,
            ),
            order_by=("player_id", "team_id"),
            excluded=common_excluded,
        ),
        "player_roles": queryset_digest(
            PlayerSeasonRole.objects.filter(
                competition_season=competition_season,
                is_current=True,
            ),
            order_by=("player_id", "team_id"),
            excluded=role_excluded,
        ),
    }


def report_header(competition_season) -> dict:
    return {
        "report_version": REPORT_VERSION,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "competition_season_id": competition_season.pk,
            "competition": competition_season.competition.short_code,
            "season": competition_season.season.label,
        },
        "environment": {
            "python": platform.python_version(),
            "django": django_version(),
            "platform": platform.platform(),
            "database_vendor": connection.vendor,
        },
    }
