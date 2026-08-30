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
    ProviderMatch,
    ProviderMatchCarry,
    ProviderMatchEvent,
    ProviderMatchPlayerStateExposure,
    ProviderMatchPossession,
    ProviderMatchPossessionEvent,
    ProviderMatchPossessionParticipant,
    ProviderMatchTeamGameStateEpisode,
)
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
FLOAT_ABSOLUTE_TOLERANCE = 1e-6
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
    return {
        "primary_archetype": assignment["primary_archetype"],
        "primary_fit": assignment["primary_fit"],
        "secondary_archetype": assignment["secondary_archetype"],
        "secondary_fit": assignment["secondary_fit"],
        "classification_shape": assignment["classification_shape"],
        "evidence_confidence": assignment["evidence_confidence"],
        "traits": assignment["traits"],
        "candidates": candidates,
    }


def persisted_role_output(role: PlayerSeasonRole) -> dict:
    return {
        "primary_archetype": role.primary_archetype,
        "primary_fit": role.primary_fit,
        "secondary_archetype": role.secondary_archetype,
        "secondary_fit": role.secondary_fit,
        "classification_shape": role.classification_shape,
        "evidence_confidence": role.evidence_confidence,
        "traits": role.traits,
        "candidates": role.candidates,
    }


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
        if not isinstance(expected, (int, float)) or not isinstance(actual, (int, float)):
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
