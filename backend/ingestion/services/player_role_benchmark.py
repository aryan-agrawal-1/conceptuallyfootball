"""Read-only benchmark and equivalence tools for player role materialization."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
import json
from math import isclose
from pathlib import Path
import resource
from time import perf_counter
from typing import Any, Iterator

from django.db import connection
from django.db.models.signals import post_init
from django.test.utils import CaptureQueriesContext

from ingestion.models import (
    EventProfileSplitType,
    PlayerSeasonEventProfile,
    PlayerSeasonRole,
    PlayerSeasonRoleFeatureSnapshot,
    Provider,
    ProviderMatch,
    ProviderMatchCarry,
    ProviderMatchEvent,
    ProviderMatchPlayerStateExposure,
    ProviderMatchPossession,
    ProviderMatchPossessionEvent,
    ProviderMatchPossessionParticipant,
    ProviderMatchTeamGameStateEpisode,
)
from ingestion.services.player_role_diagnostics import resident_memory_mb, sample_memory
from ingestion.services.player_role_definitions import ROLE_FEATURE_VERSION, ROLE_SCORING_VERSION
from ingestion.services.player_role_features import (
    build_feature_snapshot,
    direct_assist_events,
    goal_transition_context,
)
from ingestion.services.player_season_roles import (
    assign_classification,
    score_candidate_cohort,
    score_traits,
)


DEFAULT_CORPUS_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "player_role_corpus_v1.json"
DEFAULT_BASELINE_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "player_role_baseline_2026-08-30.json"
FLOAT_ABSOLUTE_TOLERANCE = 1e-6
DEFAULT_SCALE_MATCH_COUNTS = (10, 50, 100)
RAW_EVIDENCE_MODELS = (
    ProviderMatchEvent,
    ProviderMatchCarry,
    ProviderMatchPlayerStateExposure,
    ProviderMatchPossession,
    ProviderMatchPossessionEvent,
    ProviderMatchPossessionParticipant,
    ProviderMatchTeamGameStateEpisode,
)
REQUIRED_CORPUS_CLASSES = {
    "goalkeeper",
    "high_minute_outfield",
    "low_minute_substitute",
    "transfer_multiple_team",
    "sparse_exposure",
    "all_game_states",
    "goals_assists",
    "transition_involvement",
}
ROLE_OUTPUT_FIELDS = (
    "primary_archetype",
    "primary_fit",
    "secondary_archetype",
    "secondary_fit",
    "classification_shape",
    "evidence_confidence",
    "traits",
    "candidates",
)


@dataclass(frozen=True, slots=True)
class CorpusEntry:
    player_id: int
    team_id: int
    label: str
    covers: tuple[str, ...]


class BenchmarkWriteError(RuntimeError):
    """Raised if benchmark code attempts to mutate the database."""


def load_corpus(path: Path = DEFAULT_CORPUS_PATH) -> list[CorpusEntry]:
    payload = json.loads(path.read_text())
    entries = [
        CorpusEntry(
            player_id=int(row["player_id"]),
            team_id=int(row["team_id"]),
            label=row["label"],
            covers=tuple(row["covers"]),
        )
        for row in payload["profiles"]
    ]
    covered = {category for entry in entries for category in entry.covers}
    missing = sorted(REQUIRED_CORPUS_CLASSES - covered)
    if missing:
        raise ValueError(f"Corpus does not cover required classes: {', '.join(missing)}")
    keys = [(entry.player_id, entry.team_id) for entry in entries]
    if len(keys) != len(set(keys)):
        raise ValueError("Corpus contains duplicate player-team profiles.")
    return entries


def peak_rss_mb() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports KiB.
    divisor = 1024 * 1024 if value > 10_000_000 else 1024
    return round(value / divisor, 3)


@contextmanager
def read_only_queries() -> Iterator[None]:
    def guard(execute, sql, params, many, context):
        operation = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
        if operation not in {"SELECT", "WITH", "EXPLAIN", "SHOW", "SET"}:
            raise BenchmarkWriteError(f"Benchmark attempted a database write: {operation or 'unknown SQL'}")
        return execute(sql, params, many, context)

    with connection.execute_wrapper(guard):
        yield


@contextmanager
def count_model_instances() -> Iterator[Counter]:
    counts = Counter()

    def count(sender, **kwargs):
        counts[sender.__name__] += 1

    dispatch_uid = "player-role-benchmark-model-count"
    post_init.connect(count, weak=False, dispatch_uid=dispatch_uid)
    try:
        yield counts
    finally:
        post_init.disconnect(dispatch_uid=dispatch_uid)


def timed(timings: dict[str, float], name: str, function, *args, **kwargs):
    started = perf_counter()
    result = function(*args, **kwargs)
    timings[name] = round(perf_counter() - started, 6)
    return result


def role_output(features: dict, candidates: list[dict], traits: list[dict]) -> dict:
    assignment = assign_classification(features, candidates, traits)
    assignment["candidates"] = candidates
    return {field: assignment[field] for field in ROLE_OUTPUT_FIELDS}


def persisted_role_output(role: PlayerSeasonRole) -> dict:
    return {field: getattr(role, field) for field in ROLE_OUTPUT_FIELDS}


def benchmark_player_role_features(
    competition_season,
    corpus: list[CorpusEntry],
    *,
    match_count: int | None = None,
) -> tuple[dict, dict]:
    """Build corpus features and score them without publishing any rows."""

    benchmark_started = perf_counter()
    timings: dict[str, float] = {}
    rss_at_start = peak_rss_mb()
    keys = {(entry.player_id, entry.team_id) for entry in corpus}
    player_ids = {player_id for player_id, team_id in keys}
    team_ids = {team_id for player_id, team_id in keys}

    with CaptureQueriesContext(connection) as queries, count_model_instances() as model_rows, read_only_queries():
        profiles = timed(
            timings,
            "load_profiles",
            list,
            PlayerSeasonEventProfile.objects.filter(
                competition_season=competition_season,
                split_type=EventProfileSplitType.TEAM,
                is_current=True,
                player_id__in=player_ids,
                team_id__in=team_ids,
            ).select_related("player", "team", "competition_season").order_by("player_id", "team_id"),
        )
        profiles = [profile for profile in profiles if (profile.player_id, profile.team_id) in keys]
        found_keys = {(profile.player_id, profile.team_id) for profile in profiles}
        missing = sorted(keys - found_keys)
        if missing:
            raise ValueError(f"Corpus profiles are missing or not current: {missing}")

        match_ids = timed(
            timings,
            "load_matches",
            list,
            ProviderMatch.objects.filter(competition_season=competition_season)
            .order_by("kickoff_at", "id")
            .values_list("id", flat=True),
        )
        if match_count is not None:
            if match_count < 1:
                raise ValueError("match_count must be positive.")
            match_ids = match_ids[:match_count]

        all_events = timed(
            timings,
            "load_events",
            list,
            ProviderMatchEvent.objects.filter(provider_match_id__in=match_ids).select_related("player", "team"),
        )
        resolved_assists = timed(timings, "resolve_assists", direct_assist_events, all_events)
        goal_context = timed(
            timings,
            "load_goal_context",
            goal_transition_context,
            competition_season,
            match_ids=match_ids,
        )

        built_features = {}
        started = perf_counter()
        for profile in profiles:
            profile_started = perf_counter()
            key = (profile.player_id, profile.team_id)
            built_features[key] = build_feature_snapshot(
                profile,
                match_ids,
                all_events,
                resolved_assists,
                goal_context,
            )
            timings[f"profile:{profile.player_id}:{profile.team_id}"] = round(
                perf_counter() - profile_started,
                6,
            )
        timings["build_features"] = round(perf_counter() - started, 6)

        snapshots = timed(
            timings,
            "load_scoring_cohort",
            list,
            PlayerSeasonRoleFeatureSnapshot.objects.filter(
                competition_season=competition_season,
                is_current=True,
            ).order_by("player_id", "team_id"),
        )
        cohort_features = [
            built_features.get((snapshot.player_id, snapshot.team_id), snapshot.features)
            for snapshot in snapshots
        ]
        scoring_started = perf_counter()
        candidate_rows = score_candidate_cohort(cohort_features)
        trait_rows = score_traits(cohort_features)
        timings["score_cohort"] = round(perf_counter() - scoring_started, 6)
        scored = {
            (snapshot.player_id, snapshot.team_id): role_output(features, candidates, traits)
            for snapshot, features, candidates, traits in zip(
                snapshots,
                cohort_features,
                candidate_rows,
                trait_rows,
            )
            if (snapshot.player_id, snapshot.team_id) in keys
        }

    total_seconds = round(perf_counter() - benchmark_started, 6)
    peak = peak_rss_mb()
    output = {
        f"{entry.player_id}:{entry.team_id}": {
            "label": entry.label,
            "features": built_features[(entry.player_id, entry.team_id)],
            "role": scored[(entry.player_id, entry.team_id)],
        }
        for entry in corpus
    }
    report = {
        "competition_season_id": competition_season.pk,
        "feature_version": ROLE_FEATURE_VERSION,
        "scoring_version": ROLE_SCORING_VERSION,
        "match_count": len(match_ids),
        "profile_count": len(profiles),
        "wall_time_seconds": total_seconds,
        "component_timings_seconds": timings,
        "query_count": len(queries),
        "rows_loaded_by_model": dict(sorted(model_rows.items())),
        "rss_at_start_mb": rss_at_start,
        "peak_rss_mb": peak,
        "peak_rss_growth_mb": round(max(0.0, peak - rss_at_start), 3),
    }
    return report, output


def create_oracle(competition_season, corpus: list[CorpusEntry]) -> dict:
    keys = {(entry.player_id, entry.team_id) for entry in corpus}
    snapshots = {
        (row.player_id, row.team_id): row
        for row in PlayerSeasonRoleFeatureSnapshot.objects.filter(
            competition_season=competition_season,
            is_current=True,
        )
        if (row.player_id, row.team_id) in keys
    }
    roles = {
        (row.player_id, row.team_id): row
        for row in PlayerSeasonRole.objects.filter(
            competition_season=competition_season,
            is_current=True,
        )
        if (row.player_id, row.team_id) in keys
    }
    missing = sorted(keys - snapshots.keys())
    missing_roles = sorted(keys - roles.keys())
    if missing or missing_roles:
        raise ValueError(f"Current oracle rows missing; features={missing}, roles={missing_roles}")
    return {
        "contract": {
            "feature_version": ROLE_FEATURE_VERSION,
            "scoring_version": ROLE_SCORING_VERSION,
            "exact": "Objects, arrays, strings, booleans, nulls, and integer values must match exactly.",
            "floats": {"absolute_tolerance": FLOAT_ABSOLUTE_TOLERANCE, "relative_tolerance": 0},
        },
        "competition_season_id": competition_season.pk,
        "profiles": {
            f"{entry.player_id}:{entry.team_id}": {
                "label": entry.label,
                "features": snapshots[(entry.player_id, entry.team_id)].features,
                "role": persisted_role_output(roles[(entry.player_id, entry.team_id)]),
            }
            for entry in corpus
        },
    }


def compare_values(expected: Any, actual: Any, *, path: str = "$", differences: list[str] | None = None) -> list[str]:
    differences = differences if differences is not None else []
    if isinstance(expected, bool) or isinstance(actual, bool):
        if expected != actual or type(expected) is not type(actual):
            differences.append(f"{path}: expected {expected!r}, got {actual!r}")
        return differences
    if isinstance(expected, float) or isinstance(actual, float):
        if not isinstance(expected, float) or not isinstance(actual, float):
            differences.append(f"{path}: expected {expected!r}, got {actual!r}")
        elif not isclose(expected, actual, rel_tol=0, abs_tol=FLOAT_ABSOLUTE_TOLERANCE):
            differences.append(f"{path}: expected {expected!r}, got {actual!r}")
        return differences
    if type(expected) is not type(actual):
        differences.append(f"{path}: expected {type(expected).__name__}, got {type(actual).__name__}")
    elif isinstance(expected, dict):
        for key in sorted(expected.keys() | actual.keys()):
            if key not in expected:
                differences.append(f"{path}.{key}: unexpected key")
            elif key not in actual:
                differences.append(f"{path}.{key}: missing key")
            else:
                compare_values(expected[key], actual[key], path=f"{path}.{key}", differences=differences)
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            differences.append(f"{path}: expected {len(expected)} items, got {len(actual)}")
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            compare_values(expected_item, actual_item, path=f"{path}[{index}]", differences=differences)
    elif expected != actual:
        differences.append(f"{path}: expected {expected!r}, got {actual!r}")
    return differences


def compare_oracle(oracle: dict, candidate_profiles: dict) -> list[str]:
    return compare_values(oracle["profiles"], candidate_profiles)


def persisted_role_output_values(row: dict) -> dict:
    return {field: row[field] for field in ROLE_OUTPUT_FIELDS}


def current_role_output_rows(competition_season) -> tuple[list[dict], list[dict]]:
    snapshot_rows = list(PlayerSeasonRoleFeatureSnapshot.objects.filter(
        competition_season=competition_season,
        is_current=True,
    ).values("player_id", "team_id", "features").order_by("player_id", "team_id"))
    role_rows = list(PlayerSeasonRole.objects.filter(
        competition_season=competition_season,
        is_current=True,
    ).values(
        "player_id", "team_id", "primary_archetype", "primary_fit",
        "secondary_archetype", "secondary_fit", "classification_shape",
        "evidence_confidence", "traits", "candidates",
    ).order_by("player_id", "team_id"))
    return snapshot_rows, role_rows


def score_role_output_rows(snapshot_rows: list[dict]) -> dict[tuple[int, int], dict]:
    feature_rows = [row["features"] for row in snapshot_rows]
    candidate_rows = score_candidate_cohort(feature_rows)
    trait_rows = score_traits(feature_rows)
    return {
        (int(row["player_id"]), int(row["team_id"])): role_output(
            row["features"], candidates, traits
        )
        for row, candidates, traits in zip(snapshot_rows, candidate_rows, trait_rows)
    }


def raw_evidence_query_count(queries) -> int:
    table_names = {model._meta.db_table.lower() for model in RAW_EVIDENCE_MODELS}
    return sum(
        any(table_name in query["sql"].lower() for table_name in table_names)
        for query in queries
    )


def score_only_shadow(competition_season) -> dict:
    started_at = perf_counter()
    rss_at_start = resident_memory_mb()
    with CaptureQueriesContext(connection) as queries, read_only_queries():
        snapshot_rows, role_rows = current_role_output_rows(competition_season)
        candidate_roles = score_role_output_rows(snapshot_rows)
    accepted_roles = {
        (int(row["player_id"]), int(row["team_id"])): persisted_role_output_values(row)
        for row in role_rows
    }
    differences = compare_values(accepted_roles, candidate_roles)
    return {
        "wall_time_seconds": round(perf_counter() - started_at, 6),
        "query_count": len(queries),
        "raw_evidence_query_count": raw_evidence_query_count(queries),
        "snapshot_count": len(snapshot_rows),
        "role_differences": len(differences),
        "rss_at_start_mb": rss_at_start,
        "peak_rss_mb": resident_memory_mb(),
        "difference_preview": differences[:20],
    }


def load_baseline(path: Path = DEFAULT_BASELINE_PATH) -> dict:
    return json.loads(path.read_text())


def run_player_role_scale_gate(
    competition_season,
    *,
    batch_size: int = 5,
    scale_match_counts: tuple[int, ...] | None = None,
    baseline: dict | None = None,
) -> dict:
    """Run the read-only all-profile scale and equivalence gate."""

    from ingestion.services.player_role_materialization import (
        build_bounded_feature_rows,
        feature_extraction_scope,
    )

    rss_at_start = resident_memory_mb()
    with CaptureQueriesContext(connection) as setup_queries, read_only_queries():
        scope = feature_extraction_scope(
            competition_season,
            affected_player_ids=None,
            affected_team_ids=None,
        )
        snapshot_rows, role_rows = current_role_output_rows(competition_season)
        match_ids = tuple(ProviderMatch.objects.filter(
            competition_season=competition_season,
            provider=Provider.WHOSCORED,
        ).order_by("kickoff_at", "id").values_list("id", flat=True))

    profile_keys = {(int(row["player_id"]), int(row["team_id"])) for row in snapshot_rows}
    scope_keys = {(int(row["player_id"]), int(row["team_id"])) for row in scope.profiles}
    if scope.mode != "full":
        raise ValueError("Scale gate requires the complete current feature scope.")
    if len(snapshot_rows) != len(role_rows) or scope_keys != profile_keys:
        raise ValueError(
            "Current feature and role cohorts are incomplete: "
            f"profiles={len(scope.profiles)}, snapshots={len(snapshot_rows)}, roles={len(role_rows)}"
        )
    if not match_ids:
        raise ValueError("Scale gate requires at least one WhoScored match.")

    requested_counts = (
        scale_match_counts
        if scale_match_counts is not None
        else tuple(min(count, len(match_ids)) for count in DEFAULT_SCALE_MATCH_COUNTS)
    )
    counts = sorted({int(count) for count in requested_counts} | {len(match_ids)})
    if any(count < 1 or count > len(match_ids) for count in counts):
        raise ValueError(f"Scale match counts must be between 1 and {len(match_ids)}.")

    scale_curve = []
    full_features = None
    full_diagnostics = None
    full_query_count = 0
    full_point_started_at = None
    for count in counts:
        diagnostics = {"stage_timings_seconds": {}, "rows_processed": {}, "rss_samples_mb": {}}
        sample_memory(diagnostics, "start")
        point_started_at = perf_counter()
        with CaptureQueriesContext(connection) as point_queries, read_only_queries():
            feature_rows, exposure_seconds = build_bounded_feature_rows(
                competition_season,
                tuple(scope.profiles),
                batch_size=batch_size,
                match_ids=match_ids[:count],
                diagnostics=diagnostics,
            )
        sample_memory(diagnostics, "complete")
        point = {
            "match_count": count,
            "profile_count": len(feature_rows),
            "verified_exposure_seconds": exposure_seconds,
            "wall_time_seconds": round(perf_counter() - point_started_at, 6),
            "query_count": len(point_queries),
            "rss_at_start_mb": diagnostics["rss_samples_mb"]["start"],
            "peak_rss_mb": diagnostics["peak_rss_mb"],
            "peak_rss_growth_mb": round(
                max(0.0, diagnostics["peak_rss_mb"] - diagnostics["rss_samples_mb"]["start"]),
                3,
            ),
            "component_timings_seconds": diagnostics["stage_timings_seconds"],
            "rows_processed": diagnostics["rows_processed"],
        }
        scale_curve.append(point)
        if count == len(match_ids):
            full_features = feature_rows
            full_diagnostics = diagnostics
            full_query_count = len(point_queries)
            full_point_started_at = point_started_at

    feature_by_key = {
        (
            int(features["identity"]["player_id"]),
            int(features["identity"]["team_id"]),
        ): features
        for features in full_features or []
    }
    expected_features = {
        (int(row["player_id"]), int(row["team_id"])): row["features"]
        for row in snapshot_rows
    }
    feature_differences = compare_values(expected_features, feature_by_key)
    candidate_roles = score_role_output_rows([
        {**row, "features": feature_by_key[(int(row["player_id"]), int(row["team_id"]))]}
        for row in snapshot_rows
    ])
    accepted_roles = {
        (int(row["player_id"]), int(row["team_id"])): persisted_role_output_values(row)
        for row in role_rows
    }
    role_differences = compare_values(accepted_roles, candidate_roles)
    shadow_wall_time = round(perf_counter() - full_point_started_at, 6)
    score_only = score_only_shadow(competition_season)
    baseline = baseline or load_baseline()
    baseline_peak = max(
        observation.get("peak_rss_mb", 0)
        for observation in baseline.get("observations", [])
    )
    full_peak = (scale_curve[-1] if scale_curve else {}).get("peak_rss_mb", resident_memory_mb())
    warmup_peak = max(
        (point["peak_rss_mb"] for point in scale_curve[:-1]),
        default=full_peak,
    )
    scale_rss_flat = full_peak <= warmup_peak * 1.10
    return {
        "competition_season_id": competition_season.pk,
        "feature_version": ROLE_FEATURE_VERSION,
        "scoring_version": ROLE_SCORING_VERSION,
        "batch_size": batch_size,
        "dataset": {
            "matches": len(match_ids),
            "current_profiles": len(scope.profiles),
            "current_feature_snapshots": len(snapshot_rows),
            "current_roles": len(role_rows),
        },
        "shadow": {
            "publication_performed": False,
            "wall_time_seconds": shadow_wall_time,
            "feature_build_seconds": scale_curve[-1]["wall_time_seconds"],
            "query_count": len(setup_queries) + full_query_count,
            "rss_at_start_mb": rss_at_start,
            "peak_rss_mb": full_peak,
            "peak_rss_growth_mb": round(max(0.0, full_peak - rss_at_start), 3),
            "component_timings_seconds": full_diagnostics["stage_timings_seconds"],
            "rows_processed": full_diagnostics["rows_processed"],
            "feature_differences": len(feature_differences),
            "role_and_trait_differences": len(role_differences),
            "feature_difference_preview": feature_differences[:20],
            "role_difference_preview": role_differences[:20],
        },
        "scale_curve": scale_curve,
        "score_only": score_only,
        "baseline": {
            "path": str(DEFAULT_BASELINE_PATH),
            "peak_rss_mb": baseline_peak,
            "peak_rss_reduction_mb": round(baseline_peak - full_peak, 3),
        },
        "scale_memory": {
            "warmup_peak_rss_mb": warmup_peak,
            "full_peak_rss_mb": full_peak,
            "allowed_growth_ratio": 0.10,
            "peak_rss_flat_after_warmup": scale_rss_flat,
        },
        "gates": {
            "complete_cohort": len(scope.profiles) == len(snapshot_rows) == len(role_rows),
            "feature_equivalence": not feature_differences,
            "role_equivalence": not role_differences,
            "peak_rss_within_baseline": full_peak <= baseline_peak,
            "peak_rss_flat_after_warmup": scale_rss_flat,
            "score_only_no_raw_evidence": score_only["raw_evidence_query_count"] == 0,
            "score_only_equivalence": score_only["role_differences"] == 0,
            "under_fifteen_minutes": shadow_wall_time < 15 * 60,
        },
    }
