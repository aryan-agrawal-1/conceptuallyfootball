"""Cohort-relative scoring for versioned player-team-season role snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Iterable

from django.db import transaction
from django.utils import timezone

from ingestion.models import PlayerSeasonRole, PlayerSeasonRoleFeatureSnapshot
from ingestion.services.player_role_definitions import (
    ARCHETYPE_DEFINITIONS,
    ESTABLISHED_EXPOSURE_SECONDS,
    HYBRID_MARGIN,
    MINIMUM_PRIMARY_FIT,
    MINIMUM_SECONDARY_FIT,
    PROVISIONAL_EXPOSURE_SECONDS,
    ROLE_SCORING_VERSION,
    TRAIT_DEFINITIONS,
)
from ingestion.services.player_role_features import materialize_player_role_features, refresh_score_event_features


@dataclass(frozen=True, slots=True)
class RawCandidate:
    label: str
    eligible: bool
    components: dict[str, float | None]
    unsupported_reason: str | None = None


def ratio(numerator: int | float, denominator: int | float) -> float | None:
    return numerator / denominator if denominator else None


def value(row: dict, *path: str, default=None):
    current = row
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def percentile_rank(target: float | None, cohort: list[float]) -> float | None:
    if target is None or not cohort:
        return None
    if len(cohort) == 1:
        return 0.5
    lower = sum(item < target for item in cohort)
    equal = sum(item == target for item in cohort)
    return round((lower + max(equal - 1, 0) / 2) / max(len(cohort) - 1, 1), 6)


def weighted_score(components: dict[str, float | None], weights: dict[str, float]) -> float | None:
    observed = [(components.get(key), weight) for key, weight in weights.items() if components.get(key) is not None]
    observed_weight = sum(weight for _component, weight in observed)
    if observed_weight < 0.65:
        return None
    return round(sum(component * weight for component, weight in observed) / observed_weight, 4)


def per90(count: int | float, exposure_seconds: int) -> float | None:
    return count * 5400 / exposure_seconds if exposure_seconds else None


def central_plausibility(features: dict) -> bool:
    group = value(features, "position", "group", default="UNK")
    location = value(features, "position", "average_touch", default={})
    x = location.get("x")
    y = location.get("y")
    central = y is None or 20 <= y <= 80
    ordinary_playmaker_pool = group in {"MID", "FWD", "UNK"}
    defender_position_override = group == "DEF" and x is not None and x >= 52
    return central and (ordinary_playmaker_pool or defender_position_override)


def deep_plausibility(features: dict) -> bool:
    group = value(features, "position", "group", default="UNK")
    x = value(features, "position", "average_touch", "x")
    return group in {"DEF", "MID", "UNK"} or x is None or x <= 52


def advanced_plausibility(features: dict) -> bool:
    group = value(features, "position", "group", default="UNK")
    x = value(features, "position", "average_touch", "x")
    return group in {"FWD", "MID", "UNK"} or (x is not None and x >= 52)


def raw_candidates(features: dict) -> list[RawCandidate]:
    exposure = value(features, "exposure", "verified_seconds", default=0)
    group = value(features, "position", "group", default="UNK")
    goalkeeper = group == "GK"
    geometry = value(features, "overall", "geometry", default={})
    team_geometry = value(features, "overall", "team_geometry", default={})
    summary = value(features, "overall", "summary", default={})
    passing = value(features, "overall", "passing", default={})
    carrying = value(features, "overall", "carrying", default={})
    shares = value(features, "overall", "team_action_shares", default={})
    transitions = value(features, "transitions", default={})

    def rate(metric: str) -> float | None:
        return value(geometry, "rates_per90", metric)

    def share(metric: str) -> float | None:
        return value(shares, metric, "share")

    progressive_passes = summary.get("progressive_passes", 0)
    progressive_carries = summary.get("progressive_carries", 0)
    carry_attempts = summary.get("carries", 0)
    carry_entries = carrying.get("final_third_entries", 0) + carrying.get("box_entries", 0)
    transition_actions = transitions.get("advancement_actions", 0) + transitions.get("escape_actions", 0)
    line_breaks = geometry.get("line_breaking_passes", 0)
    defensive_actions = geometry.get("defensive_actions", 0)
    ball_wins = geometry.get("ball_wins", 0)
    deep_actions = geometry.get("deep_defensive_actions", 0)
    protective = geometry.get("protective_interventions", 0)
    candidates = [
        RawCandidate(
            "Connector",
            not goalkeeper and central_plausibility(features) and geometry.get("passes", 0) >= 80 and geometry.get("central_touches", 0) >= 40,
            {
                "pass_involvement": share("passes"),
                "central_touch_share": geometry.get("central_touch_share"),
                "completion": geometry.get("pass_completion"),
                "zone_connectivity": per90(geometry.get("dangerous_entries", 0) + line_breaks, exposure),
            },
            "Needs central territory, 80 open-play passes and 40 central touches.",
        ),
        RawCandidate(
            "Deep-Lying Playmaker",
            not goalkeeper and central_plausibility(features) and deep_plausibility(features)
            and geometry.get("build_up_passes", 0) >= 60 and progressive_passes >= 12,
            {
                "deep_pass_volume": per90(geometry.get("build_up_passes", 0), exposure),
                "build_up_origin_share": ratio(geometry.get("build_up_passes", 0), geometry.get("passes", 0)),
                "build_up_progression": per90(geometry.get("build_up_progressive_passes", 0), exposure),
                "build_up_progression_share": ratio(geometry.get("build_up_progressive_passes", 0), progressive_passes),
                "progressive_pass_share": share("progressive_actions"),
            },
            "Needs central/deep plausibility, 60 build-up passes and 12 progressive passes.",
        ),
        RawCandidate(
            "Line-Breaking Playmaker",
            not goalkeeper and central_plausibility(features) and geometry.get("passes", 0) >= 60 and line_breaks >= 10,
            {
                "line_break_volume": per90(line_breaks, exposure),
                "line_break_frequency": geometry.get("line_break_frequency"),
                "central_progression": per90(geometry.get("central_progressive_passes", 0), exposure),
                "dangerous_entries": per90(geometry.get("dangerous_entries", 0), exposure),
            },
            "Needs broad central plausibility, 60 open-play passes and 10 successful line-breaking passes.",
        ),
        RawCandidate(
            "Ball-Playing Defender",
            not goalkeeper and deep_plausibility(features) and geometry.get("build_up_passes", 0) >= 50
            and geometry.get("build_up_progressive_passes", 0) >= 10 and defensive_actions >= 20,
            {
                "build_up_progression": per90(geometry.get("build_up_progressive_passes", 0), exposure),
                "build_up_pass_volume": per90(geometry.get("build_up_passes", 0), exposure),
                "defensive_work": rate("defensive_actions"),
                "progressive_share": share("progressive_actions"),
            },
            "Needs deep/build-up plausibility, 50 build-up passes, 10 progressive build-up passes and 20 defensive actions.",
        ),
        RawCandidate(
            "Ball-Carrying Progressor",
            not goalkeeper and progressive_carries >= 12 and carry_attempts >= 30,
            {
                "progressive_carry_volume": per90(progressive_carries, exposure),
                "progressive_carry_share": share("progressive_carries"),
                "forward_carry_distance": carrying.get("mean_forward_metres"),
                "carry_entries": per90(carry_entries, exposure),
            },
            "Needs 30 carries and 12 progressive carries.",
        ),
        RawCandidate(
            "Advanced Creator",
            not goalkeeper and advanced_plausibility(features)
            and geometry.get("key_passes", 0) >= 8 and geometry.get("advanced_actions", 0) >= 20,
            {
                "key_pass_volume": rate("key_passes"),
                "shot_assist_share": ratio(geometry.get("key_passes", 0), team_geometry.get("key_passes", 0)),
                "box_entry_creation": per90(geometry.get("dangerous_entries", 0), exposure),
                "advanced_involvement": per90(geometry.get("advanced_actions", 0), exposure),
            },
            "Needs advanced plausibility, eight open-play key passes/shot assists and 20 advanced actions.",
        ),
        RawCandidate(
            "Transition Outlet",
            not goalkeeper and (advanced_plausibility(features) or (geometry.get("advanced_touch_share") or 0) >= 0.30)
            and geometry.get("advanced_touches", 0) >= 30 and transitions.get("involved_possessions", 0) >= 10,
            {
                "transition_involvement": ratio(transitions.get("involved_possessions", 0), transitions.get("opportunities", 0)),
                "advanced_touch_share": geometry.get("advanced_touch_share"),
                "transition_advancement": per90(transition_actions, exposure),
                "direct_carry_threat": per90(progressive_carries + carry_entries, exposure),
            },
            "Needs advanced/outlet territory, 30 advanced touches and ten verified transition possessions.",
        ),
        RawCandidate(
            "Box Threat",
            not goalkeeper and advanced_plausibility(features) and geometry.get("box_touches", 0) >= 20 and geometry.get("shots", 0) >= 12,
            {
                "box_touch_volume": rate("box_touches"),
                "shot_volume": rate("shots"),
                "box_touch_share": ratio(geometry.get("box_touches", 0), team_geometry.get("box_touches", 0)),
                "shot_share": share("shots"),
            },
            "Needs advanced plausibility, 20 open-play box touches and 12 open-play shots.",
        ),
        RawCandidate(
            "Ball Winner",
            not goalkeeper and ball_wins >= 35 and geometry.get("tackles_interceptions", 0) >= 10,
            {
                "ball_win_volume": rate("ball_wins"),
                "ball_win_share": ratio(ball_wins, team_geometry.get("ball_wins", 0)),
                "active_defensive_height": geometry.get("defensive_height"),
                "tackle_interception_mix": ratio(geometry.get("tackles_interceptions", 0), ball_wins),
            },
            "Needs 35 ball-winning actions and ten tackles/interceptions.",
        ),
        RawCandidate(
            "Deep Protector",
            not goalkeeper and deep_plausibility(features) and deep_actions >= 30 and protective >= 12,
            {
                "deep_defensive_volume": rate("deep_defensive_actions"),
                "protective_interventions": per90(protective, exposure),
                "defensive_share": share("defensive_actions"),
                "deep_action_share": ratio(deep_actions, defensive_actions),
            },
            "Needs deep plausibility, 30 deep defensive actions and 12 protective interventions.",
        ),
        RawCandidate(
            "Sweeper Keeper",
            goalkeeper and geometry.get("sweeper_actions", 0) >= 8,
            {
                "sweeper_actions": rate("sweeper_actions"),
                "sweeper_height": geometry.get("sweeper_height"),
                "outside_box_share": ratio(geometry.get("sweeper_actions", 0), geometry.get("open_play_events", 0)),
            },
            "Goalkeepers only; needs eight verified sweeper actions.",
        ),
        RawCandidate(
            "Goalkeeper Distributor",
            goalkeeper and geometry.get("passes", 0) >= 80 and geometry.get("long_progressive_passes", 0) >= 10,
            {
                "distribution_volume": rate("passes"),
                "progressive_distribution": per90(progressive_passes, exposure),
                "long_distribution": per90(geometry.get("long_progressive_passes", 0), exposure),
                "distribution_completion": geometry.get("pass_completion"),
            },
            "Goalkeepers only; needs 80 open-play passes and ten progressive/long distributions.",
        ),
        RawCandidate(
            "Shot Stopper",
            goalkeeper and geometry.get("saves", 0) >= 20,
            {
                "save_volume": rate("saves"),
                "save_workload_share": ratio(
                    geometry.get("saves", 0),
                    geometry.get("saves", 0) + geometry.get("passes", 0) + geometry.get("sweeper_actions", 0),
                ),
                "close_range_interventions": per90(geometry.get("close_range_saves", 0), exposure),
            },
            "Goalkeepers only; needs 20 recorded saves.",
        ),
    ]
    return [candidate if candidate.eligible else RawCandidate(candidate.label, False, candidate.components, candidate.unsupported_reason) for candidate in candidates]


def score_candidate_cohort(feature_rows: list[dict]) -> list[list[dict]]:
    raw_rows = [raw_candidates(features) for features in feature_rows]
    cohorts: dict[tuple[str, str], list[float]] = {}
    for candidates in raw_rows:
        for candidate in candidates:
            if not candidate.eligible:
                continue
            for component, component_value in candidate.components.items():
                if component_value is not None:
                    cohorts.setdefault((candidate.label, component), []).append(component_value)
    scored_rows = []
    for candidates in raw_rows:
        scored = []
        for candidate in candidates:
            percentiles = {
                component: percentile_rank(component_value, cohorts.get((candidate.label, component), []))
                for component, component_value in candidate.components.items()
            }
            fit = weighted_score(percentiles, ARCHETYPE_DEFINITIONS[candidate.label]["components"]) if candidate.eligible else None
            scored.append({
                "archetype": candidate.label,
                "eligible": candidate.eligible,
                "fit": fit,
                "components": {
                    key: {"raw": round(raw, 6) if raw is not None else None, "percentile": percentiles[key]}
                    for key, raw in candidate.components.items()
                },
                "unsupported_reason": None if candidate.eligible else candidate.unsupported_reason,
            })
        scored_rows.append(scored)
    return scored_rows


def coefficient_stability(values: list[float | None]) -> float | None:
    observed = [item for item in values if item is not None]
    if len(observed) < 2:
        return None
    centre = sum(observed) / len(observed)
    if abs(centre) < 0.01:
        return None
    variance = sum((item - centre) ** 2 for item in observed) / len(observed)
    return max(0.0, 1 - sqrt(variance) / abs(centre))


def trait_raw(features: dict) -> dict[str, dict]:
    exposure = value(features, "exposure", "verified_seconds", default=0)
    geometry = value(features, "overall", "geometry", default={})
    team_geometry = value(features, "overall", "team_geometry", default={})
    summary = value(features, "overall", "summary", default={})
    shares = value(features, "overall", "team_action_shares", default={})
    score_events = value(features, "score_events", default={})
    spatial = value(features, "state_spatial", default={})
    states = value(features, "states", default={})
    observed = spatial.get("observed_states", [])
    state_rates = []
    for metric in ("touches", "pass_attempts", "progressive_actions", "defensive_actions"):
        state_rates.append(coefficient_stability([
            value(states, state, "rates", metric, "per_90") for state in observed
        ]))
    observed_stabilities = [item for item in state_rates if item is not None]
    rate_stability = sum(observed_stabilities) / len(observed_stabilities) if observed_stabilities else None
    completion = geometry.get("pass_completion")
    turnover_rate = value(geometry, "rates_per90", "turnovers")
    ball_secure = completion - min((turnover_rate or 0) / 10, 0.5) if completion is not None else None
    clutch_points = score_events.get("state_changing_goals", 0) * 2 + score_events.get("state_changing_assists", 0)
    extender_points = score_events.get("winning_state_goals", 0) * 2 + score_events.get("winning_state_assists", 0)
    clutch_contributions = score_events.get("state_changing_goals", 0) + score_events.get("state_changing_assists", 0)
    extender_contributions = score_events.get("winning_state_goals", 0) + score_events.get("winning_state_assists", 0)
    contracts = {
        "Clutch": {"raw": clutch_points, "eligible": clutch_contributions >= 4 and clutch_points >= 7, "evidence": score_events},
        "Lead Extender": {"raw": extender_points, "eligible": extender_contributions >= 3 and extender_points >= 5, "evidence": score_events},
        "State-resilient": {
            "raw": None if rate_stability is None else (rate_stability + (spatial.get("mean_heatmap_overlap") or 0)) / 2,
            "eligible": len(observed) >= 2 and spatial.get("location_samples", 0) >= 40,
            "evidence": {"rate_stability": rate_stability, "heatmap_overlap": spatial.get("mean_heatmap_overlap"), "observed_states": observed},
        },
        "Adaptive": {
            "raw": spatial.get("mean_relative_movement"),
            "eligible": len(observed) >= 2 and spatial.get("location_samples", 0) >= 40,
            "evidence": {"relative_movement": spatial.get("mean_relative_movement"), "observed_states": observed},
        },
        "High-volume": {
            "raw": (value(shares, "touches", "share", default=0) + value(shares, "passes", "share", default=0)) / 2,
            "eligible": geometry.get("touches", 0) >= 100,
            "evidence": {"touch_share": value(shares, "touches", "share"), "pass_share": value(shares, "passes", "share")},
        },
        "Direct": {
            "raw": per90(summary.get("progressive_actions", 0) + geometry.get("long_progressive_passes", 0), exposure),
            "eligible": summary.get("progressive_actions", 0) >= 15,
            "evidence": {"progressive_actions": summary.get("progressive_actions", 0), "long_or_progressive_passes": geometry.get("long_progressive_passes", 0)},
        },
        "Ball secure": {
            "raw": ball_secure,
            "eligible": geometry.get("passes", 0) >= 80 and geometry.get("touches", 0) >= 100,
            "evidence": {"pass_completion": completion, "turnovers_per90": turnover_rate},
        },
        "Aerial specialist": {
            "raw": ratio(geometry.get("aerials", 0), team_geometry.get("aerials", 0)),
            "eligible": geometry.get("aerials", 0) >= 25,
            "evidence": {"aerials": geometry.get("aerials", 0), "team_aerials": team_geometry.get("aerials", 0)},
        },
        "Set-piece specialist": {
            "raw": ratio(geometry.get("set_piece_actions", 0), team_geometry.get("set_piece_actions", 0)),
            "eligible": geometry.get("set_piece_actions", 0) >= 15 and geometry.get("set_piece_creation", 0) >= 3,
            "evidence": {"set_piece_actions": geometry.get("set_piece_actions", 0), "set_piece_creation": geometry.get("set_piece_creation", 0)},
        },
    }
    if exposure < PROVISIONAL_EXPOSURE_SECONDS:
        for contract in contracts.values():
            contract["eligible"] = False
    return contracts


def score_traits(feature_rows: list[dict]) -> list[list[dict]]:
    raw_rows = [trait_raw(features) for features in feature_rows]
    cohorts = {
        label: [row[label]["raw"] for row in raw_rows if row[label]["eligible"] and row[label]["raw"] is not None]
        for label in TRAIT_DEFINITIONS
    }
    results = []
    for raw in raw_rows:
        traits = []
        for label, contract in raw.items():
            fixed_threshold = 2 if label in {"Clutch", "Lead Extender"} else None
            score = (
                min(contract["raw"] / 6, 1.0)
                if contract["eligible"] and fixed_threshold is not None
                else percentile_rank(contract["raw"], cohorts[label]) if contract["eligible"] else None
            )
            assigned = contract["eligible"] and (
                contract["raw"] >= fixed_threshold if fixed_threshold is not None else score is not None and score >= 0.80
            )
            if assigned:
                traits.append({
                    "trait": label,
                    "score": round(score, 4) if score is not None else 1.0,
                    "meaning": TRAIT_DEFINITIONS[label],
                    "evidence": contract["evidence"],
                })
        results.append(sorted(traits, key=lambda item: (-item["score"], item["trait"])))
    return results


def assign_classification(features: dict, candidates: list[dict], traits: list[dict]) -> dict:
    exposure = value(features, "exposure", "verified_seconds", default=0)
    evidence_confidence = (
        "established" if exposure >= ESTABLISHED_EXPOSURE_SECONDS
        else "provisional" if exposure >= PROVISIONAL_EXPOSURE_SECONDS
        else "insufficient"
    )
    ranked = sorted(
        (candidate for candidate in candidates if candidate["fit"] is not None),
        key=lambda candidate: (-candidate["fit"], candidate["archetype"]),
    )
    primary = ranked[0] if ranked and ranked[0]["fit"] >= MINIMUM_PRIMARY_FIT and evidence_confidence != "insufficient" else None
    secondary = ranked[1] if primary and len(ranked) > 1 and ranked[1]["fit"] >= MINIMUM_SECONDARY_FIT else None
    hybrid = bool(secondary and primary["fit"] - secondary["fit"] <= HYBRID_MARGIN)
    if not hybrid:
        secondary = None
    shape = "hybrid" if hybrid else "clear" if primary else "unclassified"
    if primary:
        explanation = ARCHETYPE_DEFINITIONS[primary["archetype"]]["meaning"]
        if secondary:
            explanation += f" The evidence also strongly supports {secondary['archetype']}."
    elif evidence_confidence == "insufficient":
        explanation = "No archetype yet: this stint has fewer than 450 verified minutes."
    else:
        explanation = "No archetype cleared both its football-specific evidence gate and the minimum cohort-relative fit."
    return {
        "primary_archetype": primary["archetype"] if primary else None,
        "primary_fit": primary["fit"] if primary else None,
        "secondary_archetype": secondary["archetype"] if secondary else None,
        "secondary_fit": secondary["fit"] if secondary else None,
        "classification_shape": shape,
        "evidence_confidence": evidence_confidence,
        "traits": traits,
        "explanation": explanation,
    }


@transaction.atomic
def score_player_season_roles(
    competition_season,
    *,
    affected_player_ids: Iterable[int] | None = None,
    affected_team_ids: Iterable[int] | None = None,
) -> dict:
    """Score and atomically publish the complete current season cohort.

    Affected scope applies only to feature extraction. Cohort-relative scores
    can change for any stint whenever one feature snapshot changes.
    """

    snapshots = list(PlayerSeasonRoleFeatureSnapshot.objects.filter(
        competition_season=competition_season,
        is_current=True,
    ).select_related("player", "team").order_by("player_id", "team_id"))
    feature_rows = [snapshot.features for snapshot in snapshots]
    candidate_rows = score_candidate_cohort(feature_rows)
    trait_rows = score_traits(feature_rows)
    assignments = [
        assign_classification(features, candidates, traits)
        for features, candidates, traits in zip(feature_rows, candidate_rows, trait_rows)
    ]
    selected = list(zip(snapshots, candidate_rows, assignments))
    rows = [PlayerSeasonRole(
        competition_season=competition_season,
        player_id=snapshot.player_id,
        team_id=snapshot.team_id,
        feature_snapshot=snapshot,
        primary_archetype=assignment["primary_archetype"],
        primary_fit=assignment["primary_fit"],
        secondary_archetype=assignment["secondary_archetype"],
        secondary_fit=assignment["secondary_fit"],
        classification_shape=assignment["classification_shape"],
        evidence_confidence=assignment["evidence_confidence"],
        traits=assignment["traits"],
        candidates=candidates,
        evidence={
            "explanation": assignment["explanation"],
            "position": snapshot.features.get("position", {}),
            "exposure": snapshot.features.get("exposure", {}),
            "score_events": snapshot.features.get("score_events", {}),
            "state_spatial": snapshot.features.get("state_spatial", {}),
        },
        scoring_version=ROLE_SCORING_VERSION,
        is_current=False,
    ) for snapshot, candidates, assignment in selected]
    with transaction.atomic():
        PlayerSeasonRole.objects.bulk_create(rows, batch_size=250)
        current = PlayerSeasonRole.objects.filter(
            competition_season=competition_season, is_current=True
        )
        current.exclude(pk__in=[row.pk for row in rows]).update(
            is_current=False, superseded_at=timezone.now()
        )
        PlayerSeasonRole.objects.filter(pk__in=[row.pk for row in rows]).update(is_current=True)
    distribution = {}
    confidence = {}
    classified = 0
    for _snapshot, _candidates, assignment in selected:
        label = assignment["primary_archetype"] or "Unclassified"
        distribution[label] = distribution.get(label, 0) + 1
        confidence[assignment["evidence_confidence"]] = confidence.get(assignment["evidence_confidence"], 0) + 1
        classified += assignment["primary_archetype"] is not None
    eligible = sum(assignment["evidence_confidence"] != "insufficient" for _snapshot, _candidates, assignment in selected)
    return {
        "scoring_version": ROLE_SCORING_VERSION,
        "cohort_snapshots": len(snapshots),
        "published_roles": len(rows),
        "eligible_stints": eligible,
        "classified_stints": classified,
        "eligible_coverage": round(classified / eligible, 4) if eligible else None,
        "distribution": distribution,
        "evidence_confidence": confidence,
    }


def materialize_player_season_roles(
    competition_season,
    *,
    affected_player_ids: Iterable[int] | None = None,
    affected_team_ids: Iterable[int] | None = None,
    score_only: bool = False,
    score_events_only: bool = False,
) -> dict:
    if score_only and score_events_only:
        raise ValueError("score_only and score_events_only are mutually exclusive.")
    feature_result = None
    if score_events_only:
        feature_result = refresh_score_event_features(
            competition_season,
            affected_player_ids=affected_player_ids,
            affected_team_ids=affected_team_ids,
        )
    elif not score_only:
        feature_result = materialize_player_role_features(
            competition_season,
            affected_player_ids=affected_player_ids,
            affected_team_ids=affected_team_ids,
        )
    scoring_result = score_player_season_roles(
        competition_season,
    )
    return {"features": feature_result, "scoring": scoring_result}


def serialize_season_role(row: PlayerSeasonRole | None) -> dict:
    if row is None:
        return {
            "primary_archetype": None,
            "primary_role": None,
            "classification_shape": "unclassified",
            "evidence_confidence": "pending",
            "confidence": "pending",
            "traits": [],
            "freshness": "not_materialized",
            "explanation": "Role evidence has not been materialized for this player-team stint yet.",
        }
    snapshot = row.feature_snapshot
    meaning = ARCHETYPE_DEFINITIONS.get(row.primary_archetype, {}).get("meaning")
    return {
        "team": {"id": row.team_id, "name": row.team.name},
        "primary_archetype": row.primary_archetype,
        "primary_role": row.primary_archetype,
        "primary_fit": row.primary_fit,
        "primary_score": row.primary_fit,
        "secondary_archetype": row.secondary_archetype,
        "runner_up_role": row.secondary_archetype,
        "secondary_fit": row.secondary_fit,
        "runner_up_score": row.secondary_fit,
        "fit_margin": round(row.primary_fit - row.secondary_fit, 4) if row.primary_fit is not None and row.secondary_fit is not None else None,
        "classification_shape": row.classification_shape,
        "evidence_confidence": row.evidence_confidence,
        "confidence": row.evidence_confidence,
        "traits": row.traits,
        "candidates": row.candidates,
        "freshness": "current" if row.is_current and snapshot.is_current else "stale",
        "verified_exposure_seconds": snapshot.verified_exposure_seconds,
        "calculated_through": snapshot.calculated_through_date.isoformat() if snapshot.calculated_through_date else None,
        "feature_version": snapshot.feature_version,
        "scoring_version": row.scoring_version,
        "meaning": meaning,
        "explanation": row.evidence.get("explanation"),
        "position_evidence": row.evidence.get("position", {}),
        "state_evidence": row.evidence.get("state_spatial", {}),
        "score_event_evidence": row.evidence.get("score_events", {}),
    }


def serialized_player_roles(competition_season, player_id: int, preferred_team_id: int | None = None) -> tuple[dict, list[dict]]:
    rows = list(PlayerSeasonRole.objects.filter(
        competition_season=competition_season,
        player_id=player_id,
        is_current=True,
    ).select_related("team", "feature_snapshot").order_by("team__name", "team_id"))
    preferred = next((row for row in rows if row.team_id == preferred_team_id), None)
    if preferred is None and len(rows) == 1:
        preferred = rows[0]
    return serialize_season_role(preferred), [serialize_season_role(row) for row in rows]
