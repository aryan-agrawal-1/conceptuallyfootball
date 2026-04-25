from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from ingestion.models import (
    CompetitionSeason,
    IngestionRun,
    IngestionRunStatus,
    PlayerSeasonDerivedStats,
    PlayerSeasonEmbedding,
    PlayerSeasonSimilarity,
)

FEATURE_FIELDS = [
    "npxg_per_90",
    "xa_per_90",
    "xgchain_per_90",
    "xgbuildup_per_90",
    "npxg_per_shot",
    "goals_minus_xg",
    "tackles_per_90",
    "interceptions_per_90",
    "tackles_won_percentage",
    "key_passes_per_90",
    "pass_accuracy",
]
# These aggregate scores (0–100 scale, produced by the derived-stats pipeline)
# are what we reason about when naming an archetype. We deliberately name based
# on composite scores rather than raw metrics because the scores already
# blend multiple signals (e.g. `finishing_score` accounts for both volume and
# efficiency of shots) — that gives much steadier labels than any single stat.
SCORE_FIELDS = [
    "finishing_score",
    "creation_score",
    "buildup_score",
    "ball_winning_score",
    "involvement_score",
]
TOP_K_SIMILARS = 5
CLUSTER_COUNT = 8


@dataclass(frozen=True)
class _PlayerVector:
    canonical_player_id: int
    canonical_display_team_id: int | None
    position_group: str
    minutes: int
    feature_vector: list[float]
    scores: dict[str, float | None]


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


def _build_vectors(competition_season: CompetitionSeason) -> list[_PlayerVector]:
    rows = (
        PlayerSeasonDerivedStats.objects.filter(
            competition_season=competition_season,
            is_current=True,
            minutes__gt=0,
        )
        .select_related("canonical_display_team")
        .order_by("canonical_player_id")
    )
    vectors: list[_PlayerVector] = []
    for row in rows:
        feature_values: list[float] = []
        for field in FEATURE_FIELDS:
            value = getattr(row, field)
            if value is None:
                feature_values.append(0.0)
            else:
                feature_values.append(float(value))
        scores = {field: getattr(row, field) for field in SCORE_FIELDS}
        vectors.append(
            _PlayerVector(
                canonical_player_id=row.canonical_player_id,
                canonical_display_team_id=row.canonical_display_team_id,
                position_group=row.position_group,
                minutes=row.minutes or 0,
                feature_vector=feature_values,
                scores=scores,
            )
        )
    return vectors


def _project_to_3d(feature_matrix):
    from sklearn.decomposition import PCA

    if len(feature_matrix) < 4:
        return PCA(n_components=3, random_state=42).fit_transform(feature_matrix)

    try:
        from umap import UMAP
    except Exception:  # noqa: BLE001
        return PCA(n_components=3, random_state=42).fit_transform(feature_matrix)

    n_neighbors = min(20, max(3, len(feature_matrix) - 1))
    # `min_dist` pushes nearby points apart in the low-dim embedding; `spread`
    # stretches the overall layout. Larger values = stars that don't pile on
    # top of each other.
    return UMAP(
        n_components=3,
        n_neighbors=n_neighbors,
        min_dist=0.55,
        spread=2.0,
        metric="cosine",
        random_state=42,
    ).fit_transform(feature_matrix)


def _cluster(projection):
    import numpy as np
    from sklearn.cluster import KMeans

    clusters = min(CLUSTER_COUNT, len(projection))
    if clusters <= 1:
        return np.zeros(len(projection), dtype=int)
    model = KMeans(n_clusters=clusters, random_state=42, n_init=10)
    return model.fit_predict(projection)


# Readable labels for the archetypes. We pick based on the cluster's dominant
# score; the dominant position group lets us refine (e.g. finishing-dominant
# but mostly defenders reads more like "set-piece threat" than "striker").
_SCORE_LABELS: dict[str, dict[str, str]] = {
    "finishing_score": {
        "FWD": "Finisher",
        "MID": "Shot-Taking Mid",
        "DEF": "Set-Piece Threat",
        "GK": "Goalkeeper",
        "UNK": "Shot-Taker",
    },
    "creation_score": {
        "FWD": "Creative Forward",
        "MID": "Creator",
        "DEF": "Creative Defender",
        "GK": "Goalkeeper",
        "UNK": "Creator",
    },
    "buildup_score": {
        "FWD": "Linking Forward",
        "MID": "Playmaker",
        "DEF": "Deep Playmaker",
        "GK": "Sweeper-Keeper",
        "UNK": "Playmaker",
    },
    "ball_winning_score": {
        "FWD": "Pressing Forward",
        "MID": "Ball-Winner",
        "DEF": "Defensive Anchor",
        "GK": "Goalkeeper",
        "UNK": "Ball-Winner",
    },
    "involvement_score": {
        "FWD": "All-Action Forward",
        "MID": "Engine",
        "DEF": "Ball-Playing Defender",
        "GK": "Goalkeeper",
        "UNK": "All-Involved",
    },
}


def _label_clusters(
    vectors: list[_PlayerVector], cluster_ids
) -> dict[int, str]:
    """
    Assigns a human-readable name to each cluster id by:
      1. Grouping players by cluster.
      2. If the cluster is majority-goalkeeper → "Goalkeeper".
      3. Otherwise computing the cluster's mean of each aggregate score and
         picking the top score + dominant outfield position as the label key.
      4. Disambiguating collisions with numeric suffixes ("Creator",
         "Creator II") so two clusters never share a name.
    """
    cluster_members: dict[int, list[_PlayerVector]] = {}
    for vector, cluster_id in zip(vectors, cluster_ids, strict=True):
        cluster_members.setdefault(int(cluster_id), []).append(vector)

    raw_labels: dict[int, str] = {}
    for cluster_id, members in cluster_members.items():
        position_counts: dict[str, int] = {}
        for member in members:
            position_counts[member.position_group] = (
                position_counts.get(member.position_group, 0) + 1
            )
        total = sum(position_counts.values()) or 1
        gk_share = position_counts.get("GK", 0) / total

        if gk_share >= 0.5:
            raw_labels[cluster_id] = "Goalkeeper"
            continue

        score_means: dict[str, float] = {}
        for field in SCORE_FIELDS:
            values = [
                float(member.scores.get(field))
                for member in members
                if member.scores.get(field) is not None
            ]
            score_means[field] = sum(values) / len(values) if values else 0.0

        if not any(value > 0 for value in score_means.values()):
            raw_labels[cluster_id] = f"Archetype {cluster_id + 1}"
            continue

        # Dominant outfield position only (GK already handled above).
        outfield_counts = {
            pos: count for pos, count in position_counts.items() if pos != "GK"
        }
        dominant_position = (
            max(outfield_counts, key=outfield_counts.get) if outfield_counts else "UNK"
        )
        top_score_field = max(score_means, key=score_means.get)
        raw_labels[cluster_id] = _SCORE_LABELS[top_score_field].get(
            dominant_position, _SCORE_LABELS[top_score_field]["UNK"]
        )

    # Disambiguate identical labels by appending Roman numerals in cluster-id
    # order. Stable ordering keeps labels consistent across re-runs.
    final: dict[int, str] = {}
    seen: dict[str, int] = {}
    roman = ["", "II", "III", "IV", "V", "VI", "VII", "VIII"]
    for cluster_id in sorted(raw_labels):
        label = raw_labels[cluster_id]
        count = seen.get(label, 0)
        seen[label] = count + 1
        if count == 0:
            final[cluster_id] = label
        else:
            suffix = roman[count] if count < len(roman) else str(count + 1)
            final[cluster_id] = f"{label} {suffix}"
    return final


@transaction.atomic
def materialize_galaxy_embeddings(
    competition_season: CompetitionSeason,
    *,
    run: IngestionRun,
) -> None:
    _mark_run_start(run)
    try:
        vectors = _build_vectors(competition_season)
        if len(vectors) < 3:
            raise ValueError("At least 3 players are required to materialize galaxy embeddings.")

        import numpy as np

        matrix = np.array([v.feature_vector for v in vectors], dtype=np.float64)
        from sklearn.metrics.pairwise import cosine_similarity
        from sklearn.preprocessing import StandardScaler

        standardized = StandardScaler().fit_transform(matrix)
        projection = _project_to_3d(standardized)
        cluster_ids = _cluster(projection)
        cluster_labels = _label_clusters(vectors, cluster_ids)
        similarity_matrix = cosine_similarity(standardized)

        now = timezone.now()
        PlayerSeasonEmbedding.objects.filter(
            competition_season=competition_season,
            is_current=True,
        ).update(is_current=False, superseded_at=now)
        PlayerSeasonSimilarity.objects.filter(
            competition_season=competition_season,
            is_current=True,
        ).update(is_current=False, superseded_at=now)

        embeddings: list[PlayerSeasonEmbedding] = []
        similarities: list[PlayerSeasonSimilarity] = []
        for idx, vector in enumerate(vectors):
            coords = projection[idx]
            cluster_id_int = int(cluster_ids[idx])
            embeddings.append(
                PlayerSeasonEmbedding(
                    competition_season=competition_season,
                    canonical_player_id=vector.canonical_player_id,
                    canonical_display_team_id=vector.canonical_display_team_id,
                    embedding_ingestion_run=run,
                    position_group=vector.position_group,
                    minutes=vector.minutes,
                    cluster_id=cluster_id_int,
                    cluster_label=cluster_labels.get(cluster_id_int, ""),
                    umap_x=float(coords[0]),
                    umap_y=float(coords[1]),
                    umap_z=float(coords[2]),
                    is_current=True,
                )
            )

            scores = similarity_matrix[idx]
            ranked = sorted(
                (
                    (other_idx, float(scores[other_idx]))
                    for other_idx in range(len(vectors))
                    if other_idx != idx
                ),
                key=lambda item: item[1],
                reverse=True,
            )[:TOP_K_SIMILARS]
            for rank, (other_idx, score) in enumerate(ranked, start=1):
                similarities.append(
                    PlayerSeasonSimilarity(
                        competition_season=competition_season,
                        canonical_player_id=vector.canonical_player_id,
                        similar_player_id=vectors[other_idx].canonical_player_id,
                        similarity=score,
                        rank=rank,
                        is_current=True,
                    )
                )

        PlayerSeasonEmbedding.objects.bulk_create(embeddings)
        PlayerSeasonSimilarity.objects.bulk_create(similarities)
    except Exception as exc:  # noqa: BLE001
        _mark_run_failed(run, str(exc))
        return

    _mark_run_success(
        run,
        stats={
            "players": len(vectors),
            "features": len(FEATURE_FIELDS),
            "top_k": TOP_K_SIMILARS,
            "clusters": int(min(CLUSTER_COUNT, len(vectors))),
        },
    )
