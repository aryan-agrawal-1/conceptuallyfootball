from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from statistics import median
from typing import Any

import numpy as np
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from ingestion.derived_api import BIG_FIVE_COMPETITION_CODES
from ingestion.derived_definitions import MIN_ELIGIBLE_MINUTES
from ingestion.models import (
    CompetitionSeason,
    GalaxyArchetype,
    GalaxyPlayerEmbedding,
    GalaxySimilarity,
    GalaxySnapshot,
    IngestionRun,
    IngestionRunStatus,
    PlayerSeasonDerivedStats,
    PositionGroup,
    SofascorePlayerSeasonSource,
)

MODEL_VERSION = "galaxy_v2"
DEFAULT_MIN_MINUTES = 900
TOP_K_SIMILARS = 15
MIN_COMPETITION_ELIGIBLE_PLAYERS = 10
MIN_CLUSTER_SIZE = 12
MIN_CLUSTER_FAMILY_PLAYERS = MIN_CLUSTER_SIZE * 2
CORE_COVERAGE_THRESHOLD = 0.8
BROAD_COMPETITION_COVERAGE_THRESHOLD = 0.6
MISSING_FLAG_THRESHOLD = 0.05

ARCHETYPE_COLORS = [
    "#4A9EF5",
    "#1FD17C",
    "#F0A832",
    "#A855F7",
    "#EF4444",
    "#22D3EE",
    "#F472B6",
    "#C0FF4D",
    "#F97316",
    "#14B8A6",
    "#EAB308",
    "#8B5CF6",
    "#10B981",
    "#FB7185",
    "#38BDF8",
    "#A3E635",
]

GROUP_LABELS = {
    "attacking_threat": "attacking threat",
    "creation": "chance creation",
    "possession_buildup": "build-up play",
    "carrying": "carrying",
    "defending_duels": "defensive activity",
    "discipline_errors": "discipline/errors",
    "missingness": "data coverage",
}

GROUP_WEIGHTS = {
    "attacking_threat": 0.20,
    "creation": 0.20,
    "possession_buildup": 0.22,
    "carrying": 0.12,
    "defending_duels": 0.22,
    "discipline_errors": 0.04,
}

ARCHETYPE_GROUP_WEIGHTS = {
    PositionGroup.FWD: {
        "attacking_threat": 0.30,
        "creation": 0.26,
        "possession_buildup": 0.14,
        "carrying": 0.18,
        "defending_duels": 0.10,
        "discipline_errors": 0.02,
    },
    PositionGroup.MID: {
        "attacking_threat": 0.12,
        "creation": 0.24,
        "possession_buildup": 0.26,
        "carrying": 0.12,
        "defending_duels": 0.22,
        "discipline_errors": 0.04,
    },
    PositionGroup.DEF: {
        "attacking_threat": 0.06,
        "creation": 0.14,
        "possession_buildup": 0.28,
        "carrying": 0.08,
        "defending_duels": 0.38,
        "discipline_errors": 0.06,
    },
}

POSITION_DISTANCE_MULTIPLIERS = {
    ("FWD", "FWD"): 1.00,
    ("MID", "MID"): 1.00,
    ("DEF", "DEF"): 1.00,
    ("FWD", "MID"): 1.08,
    ("MID", "FWD"): 1.08,
    ("MID", "DEF"): 1.10,
    ("DEF", "MID"): 1.10,
    ("FWD", "DEF"): 1.18,
    ("DEF", "FWD"): 1.18,
}


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    group: str
    required: bool = True
    profiles: tuple[str, ...] = ("broad_sofascore", "full_understat")
    provider: str = "mixed"


FEATURE_SPECS = [
    FeatureSpec("xg_per_90", "attacking_threat", required=False),
    FeatureSpec("goals_per_90", "attacking_threat"),
    FeatureSpec("shots_per_90", "attacking_threat"),
    FeatureSpec("assists_per_90", "creation"),
    FeatureSpec("xa_per_90", "creation", required=False),
    FeatureSpec("key_passes_per_90", "creation"),
    FeatureSpec("big_chances_created_per_90", "creation", provider="sofascore"),
    FeatureSpec("chance_involvement_per_90", "creation"),
    FeatureSpec("completed_passes_per_90", "possession_buildup", provider="sofascore"),
    FeatureSpec("pass_accuracy", "possession_buildup", provider="sofascore"),
    FeatureSpec("accurate_crosses_per_90", "creation", provider="sofascore"),
    FeatureSpec("accurate_long_balls_per_90", "possession_buildup", provider="sofascore"),
    FeatureSpec("inaccurate_pass_rate", "possession_buildup", provider="sofascore"),
    FeatureSpec("successful_dribbles_per_90", "carrying", provider="sofascore"),
    FeatureSpec("successful_dribbles_percentage", "carrying", provider="sofascore"),
    FeatureSpec("tackles_per_90", "defending_duels", provider="sofascore"),
    FeatureSpec("interceptions_per_90", "defending_duels", provider="sofascore"),
    FeatureSpec("clearances_per_90", "defending_duels", provider="sofascore"),
    FeatureSpec("blocks_per_90", "defending_duels", provider="sofascore"),
    FeatureSpec("ball_recoveries_per_90", "defending_duels", provider="sofascore"),
    FeatureSpec("ground_duels_won_per_90", "defending_duels", provider="sofascore"),
    FeatureSpec("aerial_duels_won_per_90", "defending_duels", provider="sofascore"),
    FeatureSpec("tackles_won_percentage", "defending_duels", provider="sofascore"),
    FeatureSpec("fouls_per_90", "discipline_errors", provider="sofascore"),
    FeatureSpec("errors_lead_to_goal_per_90", "discipline_errors", provider="sofascore"),
    FeatureSpec("npxg_per_90", "attacking_threat", profiles=("full_understat",)),
    FeatureSpec("npxg_per_shot", "attacking_threat", profiles=("full_understat",)),
    FeatureSpec("goals_minus_npxg", "attacking_threat", profiles=("full_understat",)),
    FeatureSpec("finishing_shrunk_delta_per_shot", "attacking_threat", profiles=("full_understat",)),
    FeatureSpec("sot_rate", "attacking_threat", profiles=("full_understat",)),
    FeatureSpec("xa_per_key_pass", "creation", profiles=("full_understat",)),
    FeatureSpec("xgchain_per_90", "possession_buildup", profiles=("full_understat",)),
    FeatureSpec("xgbuildup_per_90", "possession_buildup", profiles=("full_understat",)),
    FeatureSpec("buildup_share", "possession_buildup", profiles=("full_understat",)),
]


@dataclass
class GalaxyRow:
    derived: PlayerSeasonDerivedStats
    competition_code: str
    galaxy_player_id: str
    values: dict[str, float | None]
    imputed_features: list[str] = field(default_factory=list)
    scaled_values: dict[str, float] = field(default_factory=dict)
    vector: np.ndarray | None = None
    projection_vector: np.ndarray | None = None
    archetype_vector: np.ndarray | None = None
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    archetype_key: str = ""
    archetype_label: str = ""
    archetype_confidence: float | None = None
    secondary_archetype_key: str = ""
    secondary_archetype_label: str = ""
    secondary_archetype_confidence: float | None = None
    archetype_margin: float | None = None
    archetype_diagnostics: dict[str, Any] = field(default_factory=dict)


def _mark_run_start(run: IngestionRun) -> None:
    run.status = IngestionRunStatus.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])


def _mark_run_success(run: IngestionRun, stats: dict | None = None) -> None:
    run.status = IngestionRunStatus.SUCCESS
    run.finished_at = timezone.now()
    run.error_detail = ""
    if stats is not None:
        run.stats = stats
    run.save(update_fields=["status", "finished_at", "error_detail", "stats"])


def _mark_run_failed(run: IngestionRun, message: str) -> None:
    run.status = IngestionRunStatus.FAILED
    run.finished_at = timezone.now()
    run.error_detail = message[:8000]
    run.save(update_fields=["status", "finished_at", "error_detail"])


def _mark_run_progress(run: IngestionRun, stats: dict) -> None:
    run.stats = {**(run.stats or {}), **stats}
    run.save(update_fields=["stats"])


def _setting_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is not None:
        return value
    return str(getattr(settings, name, default))


def _setting_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        raw = getattr(settings, name, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _setting_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        raw = getattr(settings, name, default)
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def resolve_galaxy_competition_seasons(scope_code: str, season_label: str) -> list[CompetitionSeason]:
    code = scope_code.strip().upper()
    rows = CompetitionSeason.objects.select_related("competition", "season").filter(
        is_active=True,
        season__label__iexact=season_label,
    )
    if code == "BIG5":
        rows = rows.filter(competition__short_code__in=BIG_FIVE_COMPETITION_CODES)
    elif code != "ALL":
        rows = rows.filter(competition__short_code__iexact=code)
    seasons = list(rows.order_by("competition__short_code"))
    if not seasons:
        raise DjangoValidationError("Unknown competition and season combination.")
    return seasons


def latest_galaxy_snapshot(scope_code: str, season_label: str) -> GalaxySnapshot | None:
    return (
        GalaxySnapshot.objects.filter(
            scope_code=scope_code.strip().upper(),
            season_label__iexact=season_label,
            is_current=True,
        )
        .order_by("-created_at", "-id")
        .first()
    )


def _profile_specs(profile: str) -> list[FeatureSpec]:
    return [spec for spec in FEATURE_SPECS if profile in spec.profiles]


def _coverage(rows: list[GalaxyRow], specs: list[FeatureSpec]) -> dict[str, float]:
    total = len(rows)
    if not total:
        return {spec.name: 0.0 for spec in specs}
    return {
        spec.name: sum(row.values.get(spec.name) is not None for row in rows) / total
        for spec in specs
    }


def _eligible_queryset(competition_seasons: list[CompetitionSeason], min_minutes: int):
    return (
        PlayerSeasonDerivedStats.objects.filter(
            competition_season__in=competition_seasons,
            is_current=True,
            minutes__gte=min_minutes,
            position_group__in=[PositionGroup.DEF, PositionGroup.MID, PositionGroup.FWD],
        )
        .select_related(
            "canonical_player",
            "canonical_display_team",
            "competition_season",
            "competition_season__competition",
            "competition_season__season",
        )
        .order_by("competition_season__competition__short_code", "canonical_player_id")
    )


def _row_feature_values(
    row: PlayerSeasonDerivedStats,
    specs: list[FeatureSpec],
    *,
    has_sofascore_source: bool,
) -> dict[str, float | None]:
    values: dict[str, float | None] = {}
    for spec in specs:
        value = getattr(row, spec.name)
        if spec.provider == "sofascore" and not has_sofascore_source:
            value = None
        values[spec.name] = value
    return values


def _build_rows(
    competition_seasons: list[CompetitionSeason],
    *,
    min_minutes: int,
) -> tuple[list[GalaxyRow], list[dict], list[dict]]:
    all_specs = list({spec.name: spec for spec in FEATURE_SPECS}.values())
    excluded: list[dict] = []
    excluded_players: list[dict] = []
    rows: list[GalaxyRow] = []
    for cs in competition_seasons:
        cs_rows = list(_eligible_queryset([cs], min_minutes))
        sofascore_player_ids = set(
            SofascorePlayerSeasonSource.objects.filter(
                competition_season=cs,
                canonical_player__isnull=False,
            ).values_list("canonical_player_id", flat=True)
        )
        if len(cs_rows) < MIN_COMPETITION_ELIGIBLE_PLAYERS:
            excluded.append(
                {
                    "competition_season_id": cs.id,
                    "competition": cs.competition.short_code,
                    "reason": "insufficient_eligible_players",
                    "eligible_players": len(cs_rows),
                }
            )
            continue
        missing_sofascore_rows = [
            row for row in cs_rows if row.canonical_player_id not in sofascore_player_ids
        ]
        if missing_sofascore_rows:
            excluded_players.extend(
                {
                    "competition_season_id": cs.id,
                    "competition": cs.competition.short_code,
                    "canonical_player_id": row.canonical_player_id,
                    "canonical_player_name": row.canonical_player.display_name,
                    "reason": "missing_sofascore_source",
                }
                for row in missing_sofascore_rows
            )
            cs_rows = [
                row for row in cs_rows if row.canonical_player_id in sofascore_player_ids
            ]
        if len(cs_rows) < MIN_COMPETITION_ELIGIBLE_PLAYERS:
            excluded.append(
                {
                    "competition_season_id": cs.id,
                    "competition": cs.competition.short_code,
                    "reason": "insufficient_eligible_players_after_sofascore_gate",
                    "eligible_players": len(cs_rows),
                }
            )
            continue
        candidate_rows = [
            GalaxyRow(
                derived=row,
                competition_code=cs.competition.short_code,
                galaxy_player_id=f"{cs.id}:{row.canonical_player_id}",
                values=_row_feature_values(
                    row,
                    all_specs,
                    has_sofascore_source=row.canonical_player_id in sofascore_player_ids,
                ),
            )
            for row in cs_rows
        ]
        broad_specs = _profile_specs("broad_sofascore")
        cs_coverage = _coverage(candidate_rows, broad_specs)
        low_required = [
            spec.name
            for spec in broad_specs
            if spec.required and cs_coverage.get(spec.name, 0.0) < BROAD_COMPETITION_COVERAGE_THRESHOLD
        ]
        if low_required:
            excluded.append(
                {
                    "competition_season_id": cs.id,
                    "competition": cs.competition.short_code,
                    "reason": "low_broad_profile_coverage",
                    "low_features": low_required,
                }
            )
            continue
        rows.extend(candidate_rows)
    return rows, excluded, excluded_players


def _choose_profile(rows: list[GalaxyRow]) -> tuple[str, list[FeatureSpec], dict[str, float]]:
    full_specs = _profile_specs("full_understat")
    full_coverage = _coverage(rows, full_specs)
    if all(
        full_coverage.get(spec.name, 0.0) >= CORE_COVERAGE_THRESHOLD
        for spec in full_specs
        if spec.required
    ):
        return "full_understat", full_specs, full_coverage
    broad_specs = _profile_specs("broad_sofascore")
    broad_coverage = _coverage(rows, broad_specs)
    selected = [
        spec
        for spec in broad_specs
        if broad_coverage.get(spec.name, 0.0) >= CORE_COVERAGE_THRESHOLD
    ]
    if len(selected) < 8:
        raise ValueError("Not enough well-covered Galaxy features for this scope.")
    return "broad_sofascore", selected, broad_coverage


def _format_exclusion_summary(excluded_competitions: list[dict]) -> str:
    if not excluded_competitions:
        return "no eligible competition rows remained"
    parts: list[str] = []
    for item in excluded_competitions[:5]:
        competition = item.get("competition", "unknown")
        reason = item.get("reason", "unknown")
        if reason == "low_broad_profile_coverage":
            low_features = ", ".join(item.get("low_features", []))
            parts.append(f"{competition}: low broad feature coverage ({low_features})")
        elif "eligible_players" in item:
            parts.append(f"{competition}: {reason} ({item['eligible_players']} eligible players)")
        else:
            parts.append(f"{competition}: {reason}")
    remaining = len(excluded_competitions) - len(parts)
    if remaining > 0:
        parts.append(f"{remaining} more excluded competitions")
    return "; ".join(parts)


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * q
    lower = math.floor(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def _feature_weights(specs: list[FeatureSpec], group_weights: dict[str, float]) -> dict[str, float]:
    by_group: dict[str, list[str]] = {}
    for spec in specs:
        by_group.setdefault(spec.group, []).append(spec.name)
    weights: dict[str, float] = {}
    for group, names in by_group.items():
        group_weight = group_weights.get(group, 0.0)
        if group_weight <= 0 or not names:
            continue
        per_feature = group_weight / len(names)
        for name in names:
            weights[name] = per_feature
    total = sum(weights.values()) or 1.0
    return {name: value / total for name, value in weights.items()}


def _prepare_matrix(
    rows: list[GalaxyRow],
    specs: list[FeatureSpec],
) -> tuple[list[str], dict[str, float], dict[str, dict], np.ndarray, dict[str, str]]:
    base_names = [spec.name for spec in specs]
    groups = {spec.name: spec.group for spec in specs}
    imputation_values: dict[str, float] = {}
    scaling: dict[str, dict] = {}
    missing_rates: dict[str, float] = {}

    for name in base_names:
        observed = [float(row.values[name]) for row in rows if row.values.get(name) is not None]
        if not observed:
            imputation_values[name] = 0.0
            scaling[name] = {"median": 0.0, "iqr": 1.0, "q25": 0.0, "q75": 0.0}
            missing_rates[name] = 1.0
            continue
        q25 = _quantile(observed, 0.25)
        q75 = _quantile(observed, 0.75)
        iqr = q75 - q25
        if iqr <= 0:
            mean = sum(observed) / len(observed)
            variance = sum((value - mean) ** 2 for value in observed) / len(observed)
            iqr = math.sqrt(variance) or 1.0
        med = median(observed)
        imputation_values[name] = float(med)
        scaling[name] = {"median": float(med), "iqr": float(iqr), "q25": float(q25), "q75": float(q75)}
        missing_rates[name] = 1.0 - (len(observed) / len(rows))

    missing_flag_names = [
        f"{name}__missing"
        for name in base_names
        if missing_rates.get(name, 0.0) >= MISSING_FLAG_THRESHOLD
    ]
    feature_names = base_names + missing_flag_names
    for name in missing_flag_names:
        groups[name] = "missingness"

    matrix = np.zeros((len(rows), len(feature_names)), dtype=np.float64)
    for row_idx, row in enumerate(rows):
        for col_idx, name in enumerate(base_names):
            raw_value = row.values.get(name)
            value = float(raw_value) if raw_value is not None else imputation_values[name]
            if raw_value is None:
                row.imputed_features.append(name)
            scaled = (value - scaling[name]["median"]) / scaling[name]["iqr"]
            scaled = max(-5.0, min(5.0, scaled))
            row.scaled_values[name] = float(scaled)
            matrix[row_idx, col_idx] = scaled
        for flag_name in missing_flag_names:
            base_name = flag_name.removesuffix("__missing")
            matrix[row_idx, feature_names.index(flag_name)] = 1.0 if row.values.get(base_name) is None else 0.0
            row.scaled_values[flag_name] = float(matrix[row_idx, feature_names.index(flag_name)])
    return feature_names, imputation_values, scaling, matrix, groups


def _weighted_matrix(matrix: np.ndarray, feature_names: list[str], weights: dict[str, float]) -> np.ndarray:
    factors = np.array([math.sqrt(max(weights.get(name, 0.0), 0.0)) for name in feature_names])
    return matrix * factors


def _pca_project_to_3d(matrix: np.ndarray) -> np.ndarray:
    from sklearn.decomposition import PCA

    return PCA(n_components=min(3, matrix.shape[1]), random_state=42).fit_transform(matrix)


def _umap_model(row_count: int):
    from umap import UMAP

    n_neighbors = min(20, max(3, row_count - 1))
    return UMAP(
        n_components=3,
        n_neighbors=n_neighbors,
        min_dist=0.55,
        spread=2.0,
        metric="manhattan",
        random_state=42,
        low_memory=True,
        transform_queue_size=1.0,
        verbose=_setting_bool("STATBALLER_GALAXY_UMAP_VERBOSE", False),
    )


def _landmark_indices(row_count: int, sample_size: int) -> np.ndarray:
    rng = np.random.default_rng(42)
    return np.sort(rng.choice(row_count, size=sample_size, replace=False))


def _interpolate_from_landmarks(
    matrix: np.ndarray,
    landmark_indices: np.ndarray,
    landmark_projection: np.ndarray,
) -> np.ndarray:
    """Project non-landmark rows by blending nearest projected landmarks.

    UMAP's transform path can allocate enough neighbor-search state to OOM small
    production boxes. This keeps the UMAP structure from the landmark sample and
    uses lightweight feature-space interpolation for the full cohort.
    """
    projection = np.zeros((len(matrix), landmark_projection.shape[1]), dtype=np.float64)
    projection[landmark_indices] = landmark_projection

    landmark_matrix = matrix[landmark_indices]
    landmark_lookup = {int(row_idx): pos for pos, row_idx in enumerate(landmark_indices)}
    neighbor_count = min(
        _setting_int("STATBALLER_GALAXY_LANDMARK_NEIGHBORS", 8) or 8,
        len(landmark_indices),
    )
    chunk_rows = _setting_int("STATBALLER_GALAXY_LANDMARK_CHUNK_ROWS", 400) or 400
    if chunk_rows <= 0:
        chunk_rows = len(matrix)

    for start in range(0, len(matrix), chunk_rows):
        stop = min(start + chunk_rows, len(matrix))
        chunk = matrix[start:stop]
        distances = np.sum(np.abs(chunk[:, None, :] - landmark_matrix[None, :, :]), axis=2)
        for offset, row_idx in enumerate(range(start, stop)):
            landmark_pos = landmark_lookup.get(row_idx)
            if landmark_pos is not None:
                projection[row_idx] = landmark_projection[landmark_pos]
                continue
            nearest = np.argpartition(distances[offset], neighbor_count - 1)[:neighbor_count]
            nearest = nearest[np.argsort(distances[offset][nearest])]
            nearest_distances = distances[offset][nearest]
            weights = 1.0 / np.maximum(nearest_distances, 1e-6)
            projection[row_idx] = np.average(landmark_projection[nearest], axis=0, weights=weights)
    return projection


def _project_to_3d(matrix: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    row_count = len(matrix)
    if len(matrix) < 4:
        return _pca_project_to_3d(matrix), {"projection_method": "pca", "projection_reason": "too_few_rows"}

    mode = (_setting_str("STATBALLER_GALAXY_PROJECTION_MODE", "auto") or "auto").strip().lower()
    if mode == "pca":
        return _pca_project_to_3d(matrix), {"projection_method": "pca", "projection_reason": "configured"}

    try:
        full_max_rows = _setting_int("STATBALLER_GALAXY_UMAP_FULL_MAX_ROWS", 2500) or 0
        landmark_rows = _setting_int("STATBALLER_GALAXY_UMAP_LANDMARK_ROWS", 400) or 0

        if mode == "umap" or full_max_rows <= 0 or row_count <= full_max_rows:
            projection = _umap_model(row_count).fit_transform(matrix)
            return projection, {
                "projection_method": "umap",
                "projection_rows": row_count,
                "umap_full_max_rows": full_max_rows,
            }

        sample_size = min(max(4, landmark_rows), row_count)
        indices = _landmark_indices(row_count, sample_size)
        landmark_projection = _umap_model(sample_size).fit_transform(matrix[indices])
        projection = _interpolate_from_landmarks(matrix, indices, landmark_projection)
        return projection, {
            "projection_method": "landmark_umap",
            "landmark_projection_method": "nearest_landmark_interpolation",
            "projection_rows": row_count,
            "landmark_rows": sample_size,
            "landmark_neighbors": _setting_int("STATBALLER_GALAXY_LANDMARK_NEIGHBORS", 8) or 8,
            "landmark_chunk_rows": _setting_int("STATBALLER_GALAXY_LANDMARK_CHUNK_ROWS", 400) or 400,
            "umap_full_max_rows": full_max_rows,
        }
    except Exception as exc:  # noqa: BLE001
        projection = _pca_project_to_3d(matrix)
        return projection, {
            "projection_method": "pca",
            "projection_reason": "umap_failed",
            "projection_error": f"{type(exc).__name__}: {exc}",
            "projection_rows": row_count,
        }


def _position_multiplier(a: str, b: str) -> float:
    return POSITION_DISTANCE_MULTIPLIERS.get((a, b), 1.25)


def _match_context(a: str, b: str) -> str:
    if a == b:
        return "same_position"
    if "UNK" in {a, b}:
        return "unknown_position"
    if {a, b} == {"FWD", "DEF"}:
        return "cross_position"
    return "adjacent_position"


def _weighted_manhattan(a: np.ndarray, b: np.ndarray, weights_vector: np.ndarray) -> float:
    denom = float(weights_vector.sum()) or 1.0
    return float(np.sum(weights_vector * np.abs(a - b)) / denom)


def _group_differences(
    source: GalaxyRow,
    target: GalaxyRow,
    feature_names: list[str],
    weights: dict[str, float],
    groups: dict[str, str],
) -> list[tuple[str, float]]:
    totals: dict[str, float] = {}
    group_weight_totals: dict[str, float] = {}
    for name in feature_names:
        group = groups.get(name, "unknown")
        weight = weights.get(name, 0.0)
        totals[group] = totals.get(group, 0.0) + abs(
            source.scaled_values.get(name, 0.0) - target.scaled_values.get(name, 0.0)
        ) * weight
        group_weight_totals[group] = group_weight_totals.get(group, 0.0) + weight
    return sorted(
        (
            (group, totals[group] / (group_weight_totals.get(group) or 1.0))
            for group in totals
            if group != "missingness"
        ),
        key=lambda item: item[1],
    )


def _similarity_explanation(
    source: GalaxyRow,
    target: GalaxyRow,
    feature_names: list[str],
    weights: dict[str, float],
    groups: dict[str, str],
) -> dict:
    diffs = _group_differences(source, target, feature_names, weights, groups)
    shared = [
        f"similar {GROUP_LABELS.get(group, group)} profile"
        for group, _value in diffs[:3]
    ]
    differences = [
        f"different {GROUP_LABELS.get(group, group)} profile"
        for group, _value in sorted(diffs, key=lambda item: item[1], reverse=True)[:2]
    ]
    feature_deltas = sorted(
        (
            {
                "feature": name,
                "delta": round(abs(source.scaled_values.get(name, 0.0) - target.scaled_values.get(name, 0.0)), 4),
                "weight": round(weights.get(name, 0.0), 6),
                "group": groups.get(name, ""),
            }
            for name in feature_names
            if not name.endswith("__missing")
        ),
        key=lambda item: item["delta"] * item["weight"],
        reverse=True,
    )
    return {
        "shared_traits": shared,
        "differences": differences,
        "top_feature_deltas": feature_deltas[:8],
    }


def _label_for_signature(position_group: str, group_scores: dict[str, float], top_features: list[str]) -> str:
    top_group = max(group_scores, key=group_scores.get) if group_scores else ""
    feature_set = set(top_features)
    if position_group == PositionGroup.FWD:
        if top_group == "creation" and {"accurate_crosses_per_90", "key_passes_per_90"} & feature_set:
            return "Wide Creator"
        if top_group == "carrying":
            return "Direct Runner"
        if top_group == "defending_duels":
            return "Pressing Forward"
        if top_group == "possession_buildup":
            return "Linking Forward"
        if "shots_per_90" in feature_set or "npxg_per_90" in feature_set:
            return "Shot-Heavy Forward"
        return "Box Threat"
    if position_group == PositionGroup.MID:
        if top_group == "defending_duels":
            return "Ball-Winning Midfielder"
        if top_group == "possession_buildup" and {"completed_passes_per_90", "accurate_long_balls_per_90"} & feature_set:
            return "Deep Progressor"
        if top_group == "possession_buildup":
            return "Tempo Controller"
        if top_group == "attacking_threat":
            return "Final-Third Midfielder"
        if top_group == "carrying":
            return "Box-to-Box Midfielder"
        return "Advanced Creator"
    if position_group == PositionGroup.DEF:
        if top_group == "creation" and {"accurate_crosses_per_90", "key_passes_per_90"} & feature_set:
            return "Crossing Fullback"
        if top_group == "creation" or top_group == "carrying":
            return "Attacking Fullback"
        if top_group == "possession_buildup":
            return "Build-Up Defender"
        if "aerial_duels_won_per_90" in feature_set:
            return "Aerial Defender"
        if "ball_recoveries_per_90" in feature_set:
            return "Recovery Defender"
        return "Defensive Stopper"
    return "Outfielder"


def _choose_k(matrix: np.ndarray, position_group: str) -> tuple[int, dict]:
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    n = len(matrix)
    if n < MIN_CLUSTER_FAMILY_PLAYERS:
        return 1, {"reason": "insufficient_players", "players": n}
    max_target = 6 if position_group == PositionGroup.MID else 5
    candidate_ks = [
        k
        for k in range(3, max_target + 1)
        if n // k >= MIN_CLUSTER_SIZE
    ]
    if not candidate_ks:
        return 1, {"reason": "minimum_cluster_size", "players": n}
    best_k = candidate_ks[0]
    best_score = -1.0
    scores: dict[str, float] = {}
    for k in candidate_ks:
        labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(matrix)
        counts = np.bincount(labels)
        if counts.min() < max(3, MIN_CLUSTER_SIZE // 2):
            continue
        score = float(silhouette_score(matrix, labels))
        penalty = 0.015 * k
        adjusted = score - penalty
        scores[str(k)] = round(adjusted, 4)
        if adjusted > best_score:
            best_k = k
            best_score = adjusted
    if best_score < 0:
        return 1, {"reason": "weak_cluster_diagnostics", "players": n, "scores": scores}
    return best_k, {"scores": scores, "selected_score": round(best_score, 4)}


def _assign_archetypes(
    rows: list[GalaxyRow],
    feature_names: list[str],
    matrix: np.ndarray,
    groups: dict[str, str],
    base_weights: dict[str, float],
) -> dict[str, dict]:
    from sklearn.cluster import KMeans

    archetypes: dict[str, dict] = {}
    row_index = {id(row): idx for idx, row in enumerate(rows)}
    color_index = 0
    for position_group in [PositionGroup.DEF, PositionGroup.MID, PositionGroup.FWD]:
        family_rows = [row for row in rows if row.derived.position_group == position_group]
        if not family_rows:
            continue
        family_indices = [row_index[id(row)] for row in family_rows]
        family_matrix = matrix[family_indices]
        archetype_weights = _feature_weights(
            [FeatureSpec(name, groups[name]) for name in feature_names if not name.endswith("__missing")],
            ARCHETYPE_GROUP_WEIGHTS[position_group],
        )
        for name in feature_names:
            if name.endswith("__missing"):
                archetype_weights[name] = base_weights.get(name, 0.0) * 0.25
        family_weight_vector = np.array([archetype_weights.get(name, 0.0) for name in feature_names])
        weighted_family_matrix = family_matrix * np.sqrt(family_weight_vector)
        k, k_diagnostics = _choose_k(weighted_family_matrix, position_group)
        if k <= 1:
            label = {"DEF": "Defender", "MID": "Midfielder", "FWD": "Forward"}[position_group]
            key = f"{position_group}:0"
            archetypes[key] = {
                "position_group": position_group,
                "cluster_id": 0,
                "label": label,
                "color": ARCHETYPE_COLORS[color_index % len(ARCHETYPE_COLORS)],
                "size": len(family_rows),
                "centroid": {},
                "feature_signature": {},
                "representative_players": [],
                "diagnostics": k_diagnostics,
            }
            color_index += 1
            for row in family_rows:
                row.archetype_key = key
                row.archetype_label = label
                row.archetype_confidence = None
                row.archetype_diagnostics = {"reason": k_diagnostics.get("reason")}
            continue

        model = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = model.fit_predict(weighted_family_matrix)
        centers = model.cluster_centers_
        for cluster_id in range(k):
            member_positions = np.where(labels == cluster_id)[0]
            members = [family_rows[int(pos)] for pos in member_positions]
            centroid = centers[cluster_id]
            raw_centroid = np.mean(family_matrix[member_positions], axis=0)
            positive = sorted(
                (
                    (feature_names[i], float(raw_centroid[i]))
                    for i in range(len(feature_names))
                    if not feature_names[i].endswith("__missing")
                ),
                key=lambda item: item[1],
                reverse=True,
            )[:6]
            group_scores: dict[str, float] = {}
            for name, value in positive:
                group = groups.get(name, "")
                group_scores[group] = group_scores.get(group, 0.0) + max(0.0, value)
            top_features = [name for name, _value in positive]
            label = _label_for_signature(position_group, group_scores, top_features)
            key = f"{position_group}:{cluster_id}"
            distances = np.linalg.norm(weighted_family_matrix[member_positions] - centroid, axis=1)
            representative_order = np.argsort(distances)[:5]
            representatives = [
                {
                    "galaxy_player_id": members[int(idx)].galaxy_player_id,
                    "canonical_player_id": members[int(idx)].derived.canonical_player_id,
                    "canonical_player_name": members[int(idx)].derived.canonical_player.display_name,
                }
                for idx in representative_order
            ]
            archetypes[key] = {
                "position_group": position_group,
                "cluster_id": cluster_id,
                "label": label,
                "color": ARCHETYPE_COLORS[color_index % len(ARCHETYPE_COLORS)],
                "size": len(members),
                "centroid": {feature_names[i]: round(float(raw_centroid[i]), 4) for i in range(len(feature_names))},
                "feature_signature": {
                    "top_features": [{"feature": name, "z": round(value, 4)} for name, value in positive],
                    "top_groups": sorted(group_scores.items(), key=lambda item: item[1], reverse=True),
                },
                "representative_players": representatives,
                "diagnostics": k_diagnostics,
            }
            color_index += 1

        for family_pos, row in enumerate(family_rows):
            distances = np.linalg.norm(weighted_family_matrix[family_pos] - centers, axis=1)
            order = np.argsort(distances)
            primary_id = int(order[0])
            secondary_id = int(order[1]) if len(order) > 1 else primary_id
            primary_distance = float(distances[primary_id])
            secondary_distance = float(distances[secondary_id])
            spread = float(np.median(np.linalg.norm(weighted_family_matrix - centers[primary_id], axis=1))) or 1.0
            confidence = max(0.0, min(1.0, 1.0 - (primary_distance / (secondary_distance + spread + 1e-9))))
            margin = secondary_distance - primary_distance
            row.archetype_key = f"{position_group}:{primary_id}"
            row.archetype_label = archetypes[row.archetype_key]["label"]
            row.archetype_confidence = round(confidence, 4)
            row.secondary_archetype_key = f"{position_group}:{secondary_id}"
            row.secondary_archetype_label = archetypes[row.secondary_archetype_key]["label"]
            row.secondary_archetype_confidence = round(max(0.0, 1.0 - confidence), 4)
            row.archetype_margin = round(margin, 4)
            row.archetype_diagnostics = {
                "distance_to_primary": round(primary_distance, 4),
                "distance_to_secondary": round(secondary_distance, 4),
                "cluster_spread": round(spread, 4),
            }
    return archetypes


def _materialize_similarity_rows(
    snapshot: GalaxySnapshot,
    embeddings: list[GalaxyPlayerEmbedding],
    rows: list[GalaxyRow],
    feature_names: list[str],
    matrix: np.ndarray,
    weights: dict[str, float],
    groups: dict[str, str],
) -> list[GalaxySimilarity]:
    weights_vector = np.array([weights.get(name, 0.0) for name in feature_names])
    top_distances: list[float] = []
    for i in range(len(rows)):
        ranked = _top_similarity_candidates(i, rows, matrix, weights_vector, limit=5)
        top_distances.extend(item[2] for item in ranked)

    # The absolute-fit score is a guardrail, not the main ranking signal. Use a
    # loose scale from known-near top-five distances so plausible matches are
    # not crushed while genuine outliers still get capped.
    scale = (median(top_distances) * 4.0) if top_distances else 1.0
    if scale <= 0:
        scale = 1.0
    similarities: list[GalaxySimilarity] = []
    for source_idx in range(len(rows)):
        ranked = _top_similarity_candidates(source_idx, rows, matrix, weights_vector, limit=TOP_K_SIMILARS)
        total_candidates = max(len(rows) - 1, 0)
        for rank, (target_idx, base_distance, distance, multiplier, context) in enumerate(ranked[:TOP_K_SIMILARS], start=1):
            if total_candidates <= 1:
                candidate_score = 100.0
            else:
                candidate_score = 100.0 * (1.0 - ((rank - 1) / (total_candidates - 1)))
            absolute_score = 100.0 * math.exp(-distance / scale)
            profile_score = min(candidate_score, absolute_score)
            weak_absolute_fit = absolute_score < candidate_score - 10.0
            similarities.append(
                GalaxySimilarity(
                    snapshot=snapshot,
                    source_embedding=embeddings[source_idx],
                    similar_embedding=embeddings[target_idx],
                    rank=rank,
                    base_distance=base_distance,
                    distance=distance,
                    position_multiplier=multiplier,
                    candidate_percentile_score=candidate_score,
                    absolute_fit_score=absolute_score,
                    profile_match_score=profile_score,
                    weak_absolute_fit=weak_absolute_fit,
                    match_context=context,
                    explanation=_similarity_explanation(
                        rows[source_idx],
                        rows[target_idx],
                        feature_names,
                        weights,
                        groups,
                    ),
                )
            )
    return similarities


def _top_similarity_candidates(
    source_idx: int,
    rows: list[GalaxyRow],
    matrix: np.ndarray,
    weights_vector: np.ndarray,
    *,
    limit: int,
) -> list[tuple[int, float, float, float, str]]:
    source = rows[source_idx]
    candidate_count = max(0, len(rows) - 1)
    if candidate_count == 0 or limit <= 0:
        return []

    denom = float(weights_vector.sum()) or 1.0
    base_distances = np.sum(np.abs(matrix - matrix[source_idx]) * weights_vector, axis=1) / denom
    multipliers = np.array(
        [_position_multiplier(source.derived.position_group, target.derived.position_group) for target in rows],
        dtype=np.float64,
    )
    distances = base_distances * multipliers
    distances[source_idx] = np.inf

    selected_count = min(limit, candidate_count)
    selected_indices = np.argpartition(distances, selected_count - 1)[:selected_count]
    selected_indices = selected_indices[np.argsort(distances[selected_indices])]

    return [
        (
            int(target_idx),
            float(base_distances[target_idx]),
            float(distances[target_idx]),
            float(multipliers[target_idx]),
            _match_context(source.derived.position_group, rows[int(target_idx)].derived.position_group),
        )
        for target_idx in selected_indices
    ]


def materialize_galaxy_scope(
    scope_code: str,
    season_label: str,
    *,
    run: IngestionRun,
    min_minutes: int = MIN_ELIGIBLE_MINUTES,
) -> GalaxySnapshot | None:
    _mark_run_start(run)
    scope = scope_code.strip().upper()
    try:
        competition_seasons = resolve_galaxy_competition_seasons(scope, season_label)
        rows, excluded_competitions, excluded_players = _build_rows(competition_seasons, min_minutes=min_minutes)
        if len(rows) < 3:
            raise ValueError(
                "At least 3 eligible outfield players are required to materialize Galaxy "
                f"after quality gates: {_format_exclusion_summary(excluded_competitions)}."
            )
        profile, specs, coverage = _choose_profile(rows)
        feature_names, imputation_values, scaling, matrix, groups = _prepare_matrix(rows, specs)
        _mark_run_progress(
            run,
            {
                "stage": "matrix_prepared",
                "scope_code": scope,
                "season_label": season_label,
                "players": len(rows),
                "features": len(feature_names),
                "feature_profile": profile,
            },
        )

        base_feature_weights = _feature_weights(specs, GROUP_WEIGHTS)
        weights = dict(base_feature_weights)
        for name in feature_names:
            if name.endswith("__missing"):
                base_name = name.removesuffix("__missing")
                weights[name] = base_feature_weights.get(base_name, 0.0) * 0.25
        total_weight = sum(weights.values()) or 1.0
        weights = {name: value / total_weight for name, value in weights.items()}

        projection_matrix = _weighted_matrix(matrix, feature_names, weights)
        _mark_run_progress(
            run,
            {
                "stage": "projection",
                "projection_rows": len(rows),
                "projection_mode": _setting_str("STATBALLER_GALAXY_PROJECTION_MODE", "auto"),
                "umap_full_max_rows": _setting_int("STATBALLER_GALAXY_UMAP_FULL_MAX_ROWS", 2500),
                "landmark_rows": _setting_int("STATBALLER_GALAXY_UMAP_LANDMARK_ROWS", 400),
                "landmark_neighbors": _setting_int("STATBALLER_GALAXY_LANDMARK_NEIGHBORS", 8),
            },
        )
        projection, projection_diagnostics = _project_to_3d(projection_matrix)
        _mark_run_progress(run, {"stage": "projection_done", **projection_diagnostics})
        if projection.shape[1] < 3:
            projection = np.pad(projection, ((0, 0), (0, 3 - projection.shape[1])))
        for idx, row in enumerate(rows):
            row.vector = matrix[idx]
            row.projection_vector = projection_matrix[idx]
            row.x = float(projection[idx][0])
            row.y = float(projection[idx][1])
            row.z = float(projection[idx][2])

        archetype_payloads = _assign_archetypes(rows, feature_names, matrix, groups, weights)
        _mark_run_progress(run, {"stage": "archetypes_done", "archetypes": len(archetype_payloads)})

        with transaction.atomic():
            now = timezone.now()
            GalaxySnapshot.objects.filter(
                scope_code=scope,
                season_label=season_label,
                is_current=True,
            ).update(is_current=False, superseded_at=now)
            snapshot = GalaxySnapshot.objects.create(
                scope_code=scope,
                season_label=season_label,
                ingestion_run=run,
                model_version=MODEL_VERSION,
                feature_profile=profile,
                min_minutes=min_minutes,
                default_min_minutes=DEFAULT_MIN_MINUTES,
                top_k=TOP_K_SIMILARS,
                included_competition_season_ids=sorted({row.derived.competition_season_id for row in rows}),
                excluded_competitions=excluded_competitions,
                feature_names=feature_names,
                feature_weights={key: round(value, 8) for key, value in weights.items()},
                feature_groups=groups,
                imputation_values={key: round(value, 6) for key, value in imputation_values.items()},
                scaling=scaling,
                position_penalties={f"{a}:{b}": value for (a, b), value in POSITION_DISTANCE_MULTIPLIERS.items()},
                diagnostics={
                    **projection_diagnostics,
                    "coverage": {key: round(value, 4) for key, value in coverage.items()},
                    "eligible_players": len(rows),
                    "eligible_competitions": sorted({row.competition_code for row in rows}),
                    "excluded_players": {
                        "missing_sofascore_source": len(excluded_players),
                        "examples": excluded_players[:25],
                    },
                },
                is_current=True,
            )

            archetype_objects: dict[str, GalaxyArchetype] = {}
            for key, payload in archetype_payloads.items():
                archetype_objects[key] = GalaxyArchetype.objects.create(
                    snapshot=snapshot,
                    archetype_key=key,
                    position_group=payload["position_group"],
                    cluster_id=payload["cluster_id"],
                    label=payload["label"],
                    color=payload["color"],
                    size=payload["size"],
                    centroid=payload["centroid"],
                    feature_signature=payload["feature_signature"],
                    representative_players=payload["representative_players"],
                    diagnostics=payload["diagnostics"],
                )

            embedding_objects = [
                GalaxyPlayerEmbedding(
                    snapshot=snapshot,
                    galaxy_player_id=row.galaxy_player_id,
                    competition_season=row.derived.competition_season,
                    canonical_player=row.derived.canonical_player,
                    canonical_display_team=row.derived.canonical_display_team,
                    derived_stats=row.derived,
                    primary_archetype=archetype_objects.get(row.archetype_key),
                    secondary_archetype=archetype_objects.get(row.secondary_archetype_key),
                    position_group=row.derived.position_group,
                    native_position=row.derived.native_position,
                    minutes=row.derived.minutes,
                    primary_archetype_label=row.archetype_label,
                    primary_archetype_confidence=row.archetype_confidence,
                    secondary_archetype_label=row.secondary_archetype_label,
                    secondary_archetype_confidence=row.secondary_archetype_confidence,
                    archetype_margin=row.archetype_margin,
                    archetype_diagnostics=row.archetype_diagnostics,
                    feature_values={key: row.values.get(key) for key in [spec.name for spec in specs]},
                    scaled_features={key: round(value, 6) for key, value in row.scaled_values.items()},
                    imputed_features=row.imputed_features,
                    umap_x=row.x,
                    umap_y=row.y,
                    umap_z=row.z,
                )
                for row in rows
            ]
            embeddings = GalaxyPlayerEmbedding.objects.bulk_create(embedding_objects)
            similarity_objects = _materialize_similarity_rows(
                snapshot,
                embeddings,
                rows,
                feature_names,
                matrix,
                weights,
                groups,
            )
            GalaxySimilarity.objects.bulk_create(similarity_objects)
    except Exception as exc:  # noqa: BLE001
        _mark_run_failed(run, str(exc))
        return None

    _mark_run_success(
        run,
        stats={
            "model_version": MODEL_VERSION,
            "scope_code": scope,
            "season_label": season_label,
            "feature_profile": profile,
            "minimum_minutes": min_minutes,
            "players": len(rows),
            "features": len(feature_names),
            "top_k": TOP_K_SIMILARS,
            **projection_diagnostics,
            "archetypes": len(archetype_payloads),
            "included_competition_season_ids": snapshot.included_competition_season_ids,
            "excluded_competitions": excluded_competitions,
            "excluded_players": {
                "missing_sofascore_source": len(excluded_players),
            },
        },
    )
    return snapshot


def materialize_galaxy_embeddings(
    competition_season: CompetitionSeason,
    *,
    run: IngestionRun,
) -> None:
    """Backward-compatible single-slice entrypoint used by existing commands."""
    materialize_galaxy_scope(
        competition_season.competition.short_code,
        competition_season.season.label,
        run=run,
        min_minutes=MIN_ELIGIBLE_MINUTES,
    )
