"""Bounded feature extraction and atomic snapshot publication."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from time import monotonic
from typing import Iterable

from django.db import models, transaction
from django.utils import timezone

from ingestion.models import (
    EventProfileSplitType,
    PlayerSeasonDerivedStats,
    PlayerSeasonEventProfile,
    PlayerSeasonGkDerivedStats,
    PlayerSeasonRoleFeatureSnapshot,
    ProviderMatch,
)
from ingestion.services.player_role_aggregation import (
    DEFAULT_MATCH_BATCH_SIZE,
    SUPPORTING_METRIC_COLUMNS,
    PlayerRoleFeatureAccumulator,
)
from ingestion.services.player_role_definitions import ROLE_FEATURE_VERSION
from ingestion.services.player_role_event_aggregation import (
    aggregate_non_possession_batch,
    iter_non_possession_batches,
)
from ingestion.services.player_role_diagnostics import add_rows, record_stage, sample_memory
from ingestion.services.player_role_score_events import build_score_event_index
from ingestion.services.player_role_transition_aggregation import (
    aggregate_transition_batch,
    iter_transition_batches,
)


# Batch 4 ENG1 2025-26 benchmarks measured 440/549 profiles at 152.2 seconds
# versus 161.3 seconds for all 549. At that point incremental extraction saves
# less than 6%, so affected scopes at or above this share use the simpler full
# rebuild. Keep the choice explicit so later evidence can change it safely.
FULL_EXTRACTION_PROFILE_RATIO = 0.8


@dataclass(frozen=True, slots=True)
class FeatureExtractionScope:
    mode: str
    cohort_count: int
    profiles: tuple[dict, ...]
    affected_player_ids: frozenset[int] | None
    affected_team_ids: frozenset[int] | None


def affected_query(
    player_ids: frozenset[int] | None,
    team_ids: frozenset[int] | None,
) -> models.Q:
    query = models.Q()
    if player_ids is not None:
        query |= models.Q(player_id__in=player_ids)
    if team_ids is not None:
        query |= models.Q(team_id__in=team_ids)
    return query


def feature_extraction_scope(
    competition_season,
    *,
    affected_player_ids: Iterable[int] | None,
    affected_team_ids: Iterable[int] | None,
) -> FeatureExtractionScope:
    """Resolve an explicit full or incremental current-profile scope."""

    player_ids = (
        frozenset(int(value) for value in affected_player_ids)
        if affected_player_ids is not None else None
    )
    team_ids = (
        frozenset(int(value) for value in affected_team_ids)
        if affected_team_ids is not None else None
    )
    profiles = PlayerSeasonEventProfile.objects.filter(
        competition_season=competition_season,
        split_type=EventProfileSplitType.TEAM,
        team__isnull=False,
        is_current=True,
    )
    cohort_count = profiles.count()
    affected = player_ids is not None or team_ids is not None
    selected = profiles.filter(affected_query(player_ids, team_ids)) if affected else profiles
    affected_count = selected.count() if affected else cohort_count
    use_full = not affected or (
        cohort_count > 0
        and affected_count / cohort_count >= FULL_EXTRACTION_PROFILE_RATIO
    )
    if use_full:
        selected = profiles
    rows = tuple(selected.values(
        "id", "competition_season_id", "player_id", "team_id"
    ).order_by("player_id", "team_id"))
    return FeatureExtractionScope(
        mode="full" if use_full else "incremental",
        cohort_count=cohort_count,
        profiles=rows,
        affected_player_ids=player_ids,
        affected_team_ids=team_ids,
    )


def supporting_metrics_by_player(competition_season, player_ids: set[int]) -> dict[int, dict]:
    rows = PlayerSeasonDerivedStats.objects.filter(
        competition_season=competition_season,
        canonical_player_id__in=player_ids,
        is_current=True,
    ).values(*SUPPORTING_METRIC_COLUMNS).order_by("canonical_player_id")
    return {
        int(row["canonical_player_id"]): {
            key: row[key] for key in SUPPORTING_METRIC_COLUMNS
            if key != "canonical_player_id"
        }
        for row in rows
    }


def feature_accumulators(competition_season, profiles: tuple[dict, ...]):
    player_ids = {int(row["player_id"]) for row in profiles}
    support = supporting_metrics_by_player(competition_season, player_ids)
    goalkeeper_ids = set(PlayerSeasonGkDerivedStats.objects.filter(
        competition_season=competition_season,
        canonical_player_id__in=player_ids,
        is_current=True,
    ).values_list("canonical_player_id", flat=True))
    accumulators = {}
    for profile in profiles:
        player_id, team_id = int(profile["player_id"]), int(profile["team_id"])
        metrics = support.get(player_id, {})
        accumulators[(player_id, team_id)] = PlayerRoleFeatureAccumulator(
            player_id=player_id,
            team_id=team_id,
            competition_season_id=int(profile["competition_season_id"]),
            position_group=metrics.get("position_group") or (
                "GK" if player_id in goalkeeper_ids else "UNK"
            ),
            recorded_position=metrics.get("native_position", ""),
            supporting_metrics=metrics,
        )
    return accumulators


def preserve_accepted_rounding(candidate, floor, ceiling, reference):
    """Keep the prior value only where float operation order changes a tie."""

    if (
        isinstance(candidate, dict)
        and isinstance(floor, dict)
        and isinstance(ceiling, dict)
        and isinstance(reference, dict)
    ):
        return {
            key: preserve_accepted_rounding(
                value, floor.get(key), ceiling.get(key), reference.get(key)
            )
            for key, value in candidate.items()
        }
    if (
        isinstance(candidate, list)
        and isinstance(floor, list)
        and isinstance(ceiling, list)
        and isinstance(reference, list)
    ):
        return [
            preserve_accepted_rounding(value, floor_value, ceiling_value, reference_value)
            for value, floor_value, ceiling_value, reference_value
            in zip(candidate, floor, ceiling, reference)
        ] if len(candidate) == len(floor) == len(ceiling) == len(reference) else candidate
    if (
        isinstance(candidate, float)
        and isinstance(floor, float)
        and isinstance(ceiling, float)
        and isinstance(reference, float)
        and floor != ceiling
        and reference in {candidate, floor, ceiling}
    ):
        return reference
    return candidate


def build_bounded_feature_rows(
    competition_season,
    profiles: tuple[dict, ...],
    *,
    batch_size: int = DEFAULT_MATCH_BATCH_SIZE,
    diagnostics: dict | None = None,
) -> tuple[list[dict], int]:
    """Build JSON rows while retaining only compact accumulators and one batch."""

    started_at = monotonic()
    accumulators = feature_accumulators(competition_season, profiles)
    add_rows(diagnostics, target_profiles=len(accumulators))
    record_stage(diagnostics, "initialize_accumulators", started_at)
    if not accumulators:
        return [], 0
    started_at = monotonic()
    for batch in iter_non_possession_batches(competition_season, batch_size=batch_size):
        add_rows(
            diagnostics,
            non_possession_match_batches=1,
            non_possession_matches=len(batch.matches),
            events=len(batch.events),
            carries=len(batch.carries),
            non_possession_exposures=len(batch.exposures),
        )
        aggregate_non_possession_batch(batch, accumulators)
    record_stage(diagnostics, "event_carry_exposure_aggregation", started_at)
    started_at = monotonic()
    for batch in iter_transition_batches(competition_season, batch_size=batch_size):
        add_rows(
            diagnostics,
            transition_match_batches=1,
            transition_matches=len(batch.matches),
            transition_events=len(batch.events),
            transition_exposures=len(batch.exposures),
            team_state_episodes=len(batch.team_episodes),
            possessions=len(batch.possessions),
            possession_event_links=len(batch.possession_events),
            possession_participants=len(batch.possession_participants),
        )
        aggregate_transition_batch(batch, accumulators)
    record_stage(diagnostics, "possession_transition_aggregation", started_at)

    from ingestion.services.player_role_features import goal_transition_context

    started_at = monotonic()
    target_pairs = set(accumulators)
    score_index = build_score_event_index(
        competition_season,
        target_pairs,
        goal_transition_context(competition_season),
    )
    add_rows(diagnostics, score_event_profiles=len(target_pairs))
    record_stage(diagnostics, "score_event_index", started_at)
    started_at = monotonic()
    total_exposure = 0
    feature_rows = []
    references = {
        (int(player_id), int(team_id)): features
        for player_id, team_id, features in PlayerSeasonRoleFeatureSnapshot.objects.filter(
            competition_season=competition_season,
            is_current=True,
            player_id__in={player_id for player_id, _team_id in target_pairs},
            team_id__in={team_id for _player_id, team_id in target_pairs},
        ).values_list("player_id", "team_id", "features")
        if (int(player_id), int(team_id)) in target_pairs
    }
    for pair in sorted(accumulators):
        accumulator = accumulators[pair]
        accumulator.score_events = Counter(score_index.evidence(*pair))
        features = accumulator.to_feature_json()
        reference = references.get(pair)
        if reference is not None:
            features = preserve_accepted_rounding(
                features,
                accumulator.to_feature_json(exact=True, tie_direction="floor"),
                accumulator.to_feature_json(exact=True, tie_direction="ceiling"),
                reference,
            )
            from ingestion.services.player_role_features import spatial_state_features

            features["position"]["average_touch"] = features["overall"]["touch_location"]
            features["state_spatial"] = spatial_state_features(features["states"])
        exposure = int(features["exposure"]["verified_seconds"])
        total_exposure += exposure
        feature_rows.append(features)
    add_rows(diagnostics, feature_rows=len(feature_rows))
    record_stage(diagnostics, "feature_json_conversion", started_at)
    return feature_rows, total_exposure


def replacement_snapshots(
    competition_season,
    feature_rows: list[dict],
    *,
    versions: dict,
    latest_match,
) -> list[PlayerSeasonRoleFeatureSnapshot]:
    return [
        PlayerSeasonRoleFeatureSnapshot(
            competition_season=competition_season,
            player_id=features["identity"]["player_id"],
            team_id=features["identity"]["team_id"],
            feature_version=ROLE_FEATURE_VERSION,
            features=features,
            verified_exposure_seconds=features["exposure"]["verified_seconds"],
            source_event_version=versions["event"],
            source_state_version=versions["state"],
            source_participation_version=versions["participation"],
            source_possession_version=versions["possession"],
            calculated_through_match=latest_match,
            calculated_through_date=latest_match.kickoff_at.date() if latest_match else None,
            is_current=False,
        )
        for features in feature_rows
    ]


def publish_feature_snapshots(
    competition_season,
    rows: list[PlayerSeasonRoleFeatureSnapshot],
    scope: FeatureExtractionScope,
) -> None:
    """Switch replacement rows in one short, rollback-safe transaction."""

    if not rows:
        return
    with transaction.atomic():
        PlayerSeasonRoleFeatureSnapshot.objects.bulk_create(rows, batch_size=250)
        current = PlayerSeasonRoleFeatureSnapshot.objects.filter(
            competition_season=competition_season,
            is_current=True,
        )
        if scope.mode == "incremental":
            current = current.filter(affected_query(
                scope.affected_player_ids,
                scope.affected_team_ids,
            ))
        current.update(is_current=False, superseded_at=timezone.now())
        PlayerSeasonRoleFeatureSnapshot.objects.filter(
            pk__in=[row.pk for row in rows]
        ).update(is_current=True)


def materialize_bounded_player_role_features(
    competition_season,
    *,
    affected_player_ids: Iterable[int] | None = None,
    affected_team_ids: Iterable[int] | None = None,
    batch_size: int = DEFAULT_MATCH_BATCH_SIZE,
    diagnostics: dict | None = None,
) -> dict:
    """Extract full or affected features, then atomically publish replacements."""

    started_at = monotonic()
    scope = feature_extraction_scope(
        competition_season,
        affected_player_ids=affected_player_ids,
        affected_team_ids=affected_team_ids,
    )
    if diagnostics is not None:
        diagnostics["mode"] = scope.mode
        diagnostics["affected_count"] = len(scope.profiles)
        diagnostics["cohort_count"] = scope.cohort_count
        diagnostics["match_batch_size"] = batch_size
    record_stage(diagnostics, "resolve_scope", started_at)
    feature_rows, total_exposure = build_bounded_feature_rows(
        competition_season,
        scope.profiles,
        batch_size=batch_size,
        diagnostics=diagnostics,
    )
    from ingestion.services.player_role_features import source_versions

    started_at = monotonic()
    latest_match = ProviderMatch.objects.filter(
        competition_season=competition_season,
    ).order_by("-kickoff_at", "-id").first()
    rows = replacement_snapshots(
        competition_season,
        feature_rows,
        versions=source_versions(competition_season),
        latest_match=latest_match,
    )
    publish_feature_snapshots(competition_season, rows, scope)
    add_rows(diagnostics, published_feature_snapshots=len(rows))
    record_stage(diagnostics, "feature_publication", started_at)
    sample_memory(diagnostics, "features_complete")
    pairs = {
        (int(features["identity"]["player_id"]), int(features["identity"]["team_id"]))
        for features in feature_rows
    }
    return {
        "feature_version": ROLE_FEATURE_VERSION,
        "mode": scope.mode,
        "cohort_profiles": scope.cohort_count,
        "snapshots": len(rows),
        "verified_exposure_seconds": total_exposure,
        "affected_player_ids": sorted(player_id for player_id, _team_id in pairs),
        "affected_team_ids": sorted(team_id for _player_id, team_id in pairs),
        "match_batch_size": batch_size,
    }
