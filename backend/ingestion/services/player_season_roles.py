"""Materialize stable, explainable player roles from verified season state evidence."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import hypot
from typing import Iterable

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from ingestion.models import (
    EventProfileSplitType,
    MatchEventGameState,
    MatchEventShotOutcome,
    PlayerSeasonEventProfile,
    PlayerSeasonRole,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchPlayerStateExposure,
    ProviderMatchTeamGameStateEpisode,
)
from ingestion.services.event_profiles import FORMULA_VERSION as EVENT_PROFILE_VERSION
from ingestion.services.game_state import GAME_STATE_CALCULATION_VERSION
from ingestion.services.player_state_comparison import (
    action_context,
    player_state_evidence,
    position_group,
    state_event_rows,
    team_matched_context,
    team_relative_shares,
)
from ingestion.state_lens import StateLensScope


PLAYER_SEASON_ROLE_VERSION = "player_season_roles_v1"
PARTICIPATION_SOURCE_VERSION = "verified_player_intervals_v1"
PROVISIONAL_TOTAL_SECONDS = 450 * 60
ESTABLISHED_TOTAL_SECONDS = 900 * 60
PROVISIONAL_STATE_SECONDS = 90 * 60
ESTABLISHED_STATE_SECONDS = 180 * 60
MIN_ROLE_SCORE = 0.5
CLOSE_ROLE_MARGIN = 0.08
RATE_PRIOR_SECONDS = 30 * 60
STATE_NAMES = ("losing", "drawing", "winning")
STABILITY_ROLES = {"Territory Anchor", "State Constant"}

ROLE_MEANINGS = {
    "Unlocker": "Increases the team's ability to progress when the scoreline requires initiative.",
    "Progression Carrier": "Moves the team forward through carrying across changing game states.",
    "Stabiliser": "Preserves passing reliability and useful progression across scorelines.",
    "Territory Anchor": "Continues operating in similar areas of the pitch regardless of state.",
    "Closer": "Converts or extends a lead while the team is already winning.",
    "Clutch response": "Scores the goals that move the team from losing to drawing or drawing to winning.",
    "Outlet": "Provides a reliable attacking release point when the team is losing.",
    "Role Migrant": "Changes territory relative to teammates as the scoreline changes.",
    "State Constant": "Keeps broad output stable across winning, drawing, and losing states.",
}


@dataclass(frozen=True, slots=True)
class RoleCandidate:
    label: str
    score: float | None
    eligible: bool
    components: dict
    reason: str | None = None


def clamp(value: float | None, lower: float = 0.0, upper: float = 1.0) -> float:
    if value is None:
        return 0.0
    return max(lower, min(upper, value))


def smooth_rate(count: int, exposure_seconds: int, prior_rate: float, prior_seconds: int = RATE_PRIOR_SECONDS) -> float | None:
    if exposure_seconds <= 0:
        return None
    return (count + prior_rate * prior_seconds / 5400) * 5400 / (exposure_seconds + prior_seconds)


def relative_slope(low: float | None, high: float | None) -> float | None:
    if low is None or high is None:
        return None
    denominator = max(abs(low), 0.25)
    return (high - low) / denominator


def weighted_average(values: Iterable[tuple[float | None, int]]) -> float | None:
    observed = [(value, weight) for value, weight in values if value is not None and weight > 0]
    total = sum(weight for value, weight in observed)
    return sum(value * weight for value, weight in observed) / total if total else None


def coefficient_stability(values: Iterable[float | None]) -> float:
    observed = [value for value in values if value is not None]
    if len(observed) < 2:
        return 0.0
    centre = sum(observed) / len(observed)
    if abs(centre) < 0.01:
        return 0.0
    variance = sum((value - centre) ** 2 for value in observed) / len(observed)
    return clamp(1 - (variance ** 0.5 / abs(centre)))


def heatmap_similarity(first: list[dict], second: list[dict]) -> float | None:
    if not first or not second or len(first) != len(second):
        return None
    difference = sum(abs(a.get("share", 0.0) - b.get("share", 0.0)) for a, b in zip(first, second))
    return clamp(1 - difference / 2)


def score_role_candidates(features: dict, priors: dict | None = None) -> list[RoleCandidate]:
    """Score every role; unsupported inputs remain explicit instead of becoming zero."""

    priors = priors or {}
    states = features["states"]
    observed_states = [name for name in STATE_NAMES if states[name]["exposure_seconds"] >= PROVISIONAL_STATE_SECONDS]
    total_seconds = sum(states[name]["exposure_seconds"] for name in STATE_NAMES)
    outfield = features.get("position_group") != "GK"

    def rate(state: str, metric: str) -> float | None:
        cohort = states[state]
        count = cohort["summary"].get(metric)
        if count is None:
            return None
        return smooth_rate(count, cohort["exposure_seconds"], priors.get(state, {}).get(metric, 0.0))

    def share(state: str, metric: str) -> float | None:
        return states[state]["team_action_shares"].get(metric, {}).get("share")

    losing_progression = rate("losing", "progressive_actions")
    drawing_progression = rate("drawing", "progressive_actions")
    winning_progression = rate("winning", "progressive_actions")
    progression_slope = weighted_average([
        (relative_slope(losing_progression, drawing_progression), states["drawing"]["exposure_seconds"]),
        (relative_slope(drawing_progression, winning_progression), states["winning"]["exposure_seconds"]),
    ])
    progression_share = weighted_average([(share(name, "progressive_actions"), states[name]["exposure_seconds"]) for name in STATE_NAMES])
    unlocker_components = {
        "progressive_volume": clamp((weighted_average([(rate(name, "progressive_actions"), states[name]["exposure_seconds"]) for name in STATE_NAMES]) or 0) / 8),
        "positive_state_slope": clamp((progression_slope or 0) / 0.35),
        "matched_team_share": clamp((progression_share or 0) / 0.22),
    }

    losing_carries = rate("losing", "progressive_carries")
    winning_carries = rate("winning", "progressive_carries")
    carry_share = weighted_average([(share(name, "progressive_carries"), states[name]["exposure_seconds"]) for name in STATE_NAMES])
    forward_carry = weighted_average([(states[name]["carrying"].get("mean_forward_metres"), states[name]["summary"].get("carries", 0)) for name in STATE_NAMES])
    carrier_components = {
        "progressive_carry_volume": clamp((weighted_average([(rate(name, "progressive_carries"), states[name]["exposure_seconds"]) for name in STATE_NAMES]) or 0) / 4),
        "progressive_carry_share": clamp((carry_share or 0) / 0.25),
        "forward_carry_distance": clamp((forward_carry or 0) / 10),
        "positive_state_slope": clamp((relative_slope(losing_carries, winning_carries) or 0) / 0.35),
    }

    pass_rates = [rate(name, "pass_attempts") for name in STATE_NAMES]
    completion_rates = [states[name]["passing"].get("completion_rate") for name in STATE_NAMES]
    progression_rates = [rate(name, "progressive_actions") for name in STATE_NAMES]
    stabiliser_components = {
        "completion_stability": coefficient_stability(completion_rates),
        "progression_stability": coefficient_stability(progression_rates),
        "pass_volume": clamp((weighted_average([(value, states[name]["exposure_seconds"]) for name, value in zip(STATE_NAMES, pass_rates)]) or 0) / 35),
    }

    centroids = [states[name]["touch_location"] for name in STATE_NAMES]
    centroid_distances = [
        hypot(first["x"] - second["x"], first["y"] - second["y"])
        for first, second in zip(centroids, centroids[1:])
        if first.get("x") is not None and first.get("y") is not None and second.get("x") is not None and second.get("y") is not None
    ]
    heatmap_scores = [heatmap_similarity(states[first]["touch_grid"], states[second]["touch_grid"]) for first, second in zip(STATE_NAMES, STATE_NAMES[1:])]
    territory_components = {
        "centroid_stability": clamp(1 - (sum(centroid_distances) / len(centroid_distances) if centroid_distances else 100) / 14),
        "heatmap_overlap": weighted_average([(value, 1) for value in heatmap_scores]) or 0.0,
        "touch_share_retention": coefficient_stability([share(name, "touches") for name in STATE_NAMES]),
    }

    winning = states["winning"]
    closer_components = {
        "winning_goals": clamp(features["winning_goals"] / 4),
        "winning_goal_share": clamp(features["winning_goals"] / max(features["total_goals"], 1)),
        "winning_shot_process": clamp((rate("winning", "shots") or 0) / 4),
    }
    clutch_components = {
        "state_changing_goals": clamp(features["state_changing_goals"] / 4),
        "transition_goal_rate": clamp(features["state_changing_goals"] * 5400 / max(features["transition_exposure_seconds"], 1) / 1.2),
        "transition_process": clamp(((rate("losing", "shots") or 0) + (rate("drawing", "shots") or 0)) / 7),
    }

    losing = states["losing"]
    outlet_components = {
        "losing_touch_share": clamp((share("losing", "touches") or 0) / 0.16),
        "losing_involvement": clamp(((rate("losing", "pass_attempts") or 0) + (rate("losing", "carries") or 0)) / 45),
        "forward_actions": clamp(((rate("losing", "progressive_actions") or 0) / 8)),
    }

    relative_movements = []
    for first, second in zip(STATE_NAMES, STATE_NAMES[1:]):
        player_first, player_second = states[first]["touch_location"], states[second]["touch_location"]
        team_first, team_second = states[first]["team_touch_location"], states[second]["team_touch_location"]
        if all(row.get(axis) is not None for row in (player_first, player_second, team_first, team_second) for axis in ("x", "y")):
            relative_movements.append(hypot(
                (player_second["x"] - player_first["x"]) - (team_second["x"] - team_first["x"]),
                (player_second["y"] - player_first["y"]) - (team_second["y"] - team_first["y"]),
            ))
    migrant_components = {
        "relative_centroid_movement": clamp((sum(relative_movements) / len(relative_movements) if relative_movements else 0) / 12),
        "distribution_divergence": clamp(1 - (weighted_average([(value, 1) for value in heatmap_scores]) or 1)),
        "movement_consistency": clamp(1 - ((max(relative_movements) - min(relative_movements)) / 12 if len(relative_movements) > 1 else 1)),
    }

    broad_metrics = ("touches", "pass_attempts", "progressive_actions", "shots", "defensive_actions")
    metric_stabilities = [coefficient_stability([rate(name, metric) for name in STATE_NAMES]) for metric in broad_metrics]
    share_stabilities = [coefficient_stability([share(name, metric) for name in STATE_NAMES]) for metric in ("touches", "passes", "progressive_actions", "shots", "defensive_actions")]
    constant_components = {
        "rate_stability": sum(metric_stabilities) / len(metric_stabilities),
        "team_share_stability": sum(share_stabilities) / len(share_stabilities),
        "spatial_support": territory_components["heatmap_overlap"],
    }

    role_rows = [
        ("Unlocker", unlocker_components, outfield and min(states["losing"]["summary"]["progressive_actions"], states["winning"]["summary"]["progressive_actions"]) >= 5, "Needs progressive actions in losing and winning states."),
        ("Progression Carrier", carrier_components, outfield and min(states["losing"]["summary"]["progressive_carries"], states["winning"]["summary"]["progressive_carries"]) >= 3, "Needs carry-specific evidence in losing and winning states."),
        ("Stabiliser", stabiliser_components, sum(states[name]["summary"]["pass_attempts"] for name in STATE_NAMES) >= 100, "Needs meaningful pass volume."),
        ("Territory Anchor", territory_components, len(observed_states) == 3 and min(states[name]["touch_location"]["sample_size"] for name in STATE_NAMES) >= 20, "Needs located touches in all three states."),
        ("Closer", closer_components, outfield and features["winning_goals"] >= 2 and winning["summary"]["shots"] >= 6, "Needs at least two actual winning-state goals and meaningful shot evidence."),
        ("Clutch response", clutch_components, outfield and features["state_changing_goals"] >= 2, "Needs at least two actual losing-to-drawing or drawing-to-winning goals."),
        ("Outlet", outlet_components, losing["exposure_seconds"] >= PROVISIONAL_STATE_SECONDS and losing["summary"]["touches"] >= 25, "Needs meaningful losing-state exposure and touches."),
        ("Role Migrant", migrant_components, len(observed_states) >= 2 and len(relative_movements) >= 1 and min(states[name]["touch_location"]["sample_size"] for name in observed_states) >= 15, "Needs located-touch movement relative to the matched team."),
        ("State Constant", constant_components, len(observed_states) == 3 and sum(states[name]["summary"]["actions"] for name in STATE_NAMES) >= 100, "Needs broad action evidence in all three states."),
    ]
    evidence_confidence = clamp(total_seconds / ESTABLISHED_TOTAL_SECONDS)
    coverage_confidence = clamp(len(observed_states) / 3)
    candidates = []
    for label, components, eligible, reason in role_rows:
        weights = 1 / len(components)
        score = round(sum(value * weights for value in components.values()) * evidence_confidence * coverage_confidence, 4) if eligible else None
        candidates.append(RoleCandidate(label, score, eligible, {key: round(value, 4) for key, value in components.items()}, None if eligible else reason))
    return candidates


def assign_role(features: dict, priors: dict | None = None) -> dict:
    candidates = score_role_candidates(features, priors)
    ranked = sorted((candidate for candidate in candidates if candidate.score is not None), key=lambda candidate: candidate.score, reverse=True)
    coverage = features["state_coverage"]
    total_seconds = sum(item["exposure_seconds"] for item in coverage.values())
    provisional_states = sum(item["exposure_seconds"] >= PROVISIONAL_STATE_SECONDS for item in coverage.values())
    established_states = sum(item["exposure_seconds"] >= ESTABLISHED_STATE_SECONDS for item in coverage.values())
    top = ranked[0] if ranked and ranked[0].score >= MIN_ROLE_SCORE else None
    runner = ranked[1] if top and len(ranked) > 1 else None
    confidence = "insufficient"
    if top:
        required_established_states = 3 if top.label in STABILITY_ROLES else 2
        established = total_seconds >= ESTABLISHED_TOTAL_SECONDS and established_states >= required_established_states
        provisional = total_seconds >= PROVISIONAL_TOTAL_SECONDS and provisional_states >= 2
        confidence = "established" if established else "provisional" if provisional else "insufficient"
        if runner and top.score - runner.score < CLOSE_ROLE_MARGIN:
            confidence = "mixed"
    explanation = (
        f"{ROLE_MEANINGS[top.label]} The season score is {top.score:.2f}."
        if top and confidence != "insufficient"
        else "Role not established: verified season evidence does not yet clear the exposure and role-specific evidence gates."
    )
    if top and runner:
        explanation += f" {runner.label} is the runner-up at {runner.score:.2f}."
    return {
        "primary_role": top.label if top and confidence != "insufficient" else None,
        "primary_score": top.score if top and confidence != "insufficient" else None,
        "runner_up_role": runner.label if top and runner and confidence != "insufficient" else None,
        "runner_up_score": runner.score if top and runner and confidence != "insufficient" else None,
        "score_margin": round(top.score - runner.score, 4) if top and runner and confidence != "insufficient" else None,
        "confidence": confidence,
        "explanation": explanation,
        "scores": [
            {"role": candidate.label, "score": candidate.score, "eligible": candidate.eligible, "components": candidate.components, "unsupported_reason": candidate.reason}
            for candidate in candidates
        ],
    }


def aggregate_state_context(profile: PlayerSeasonEventProfile, state: str, match_ids: list[int]) -> dict:
    scope = StateLensScope(state=state)
    player_events, team_events, carries, team_carries, events, segments = state_event_rows(profile, scope, match_ids)
    evidence = player_state_evidence(profile, match_ids, scope)
    player = action_context(player_events, carries, evidence["exposure_seconds"], include_defensive_families=False)
    team = team_matched_context(team_events, team_carries, segments, evidence["exposure_seconds"])
    player["team_action_shares"] = team_relative_shares(player["summary"], team["summary"])
    player["team_action_shares"]["progressive_carries"] = {
        "player_count": player["summary"]["progressive_carries"],
        "team_count": team["summary"]["progressive_carries"],
        "share": player["summary"]["progressive_carries"] / team["summary"]["progressive_carries"] if team["summary"]["progressive_carries"] else None,
        "unit": "share_of_matched_team_actions",
    }
    player["team_touch_location"] = team["touch_location"]
    player["evidence"] = evidence
    return player


def player_goal_evidence(profile: PlayerSeasonEventProfile) -> dict:
    goals = ProviderMatchEvent.objects.filter(
        provider_match__competition_season=profile.competition_season,
        player_id=profile.player_id,
        shot_outcome=MatchEventShotOutcome.GOAL,
        is_goal_disallowed=False,
        is_deleted_event=False,
    )
    if profile.team_id is not None:
        goals = goals.filter(team_id=profile.team_id)
    total_goals = goals.count()
    winning_goals = goals.filter(game_state_before=MatchEventGameState.WINNING).count()
    transition_episodes = ProviderMatchTeamGameStateEpisode.objects.filter(
        provider_match__competition_season=profile.competition_season,
        entry_event__player_id=profile.player_id,
        entry_event__shot_outcome=MatchEventShotOutcome.GOAL,
        entry_event__is_goal_disallowed=False,
        entry_event__is_deleted_event=False,
    )
    if profile.team_id is not None:
        transition_episodes = transition_episodes.filter(focal_team_id=profile.team_id)
    state_changing_goals = transition_episodes.filter(
        previous_state=MatchEventGameState.LOSING,
        state=MatchEventGameState.DRAWING,
    ).count() + transition_episodes.filter(
        previous_state=MatchEventGameState.DRAWING,
        state=MatchEventGameState.WINNING,
    ).count()
    return {"total_goals": total_goals, "winning_goals": winning_goals, "state_changing_goals": state_changing_goals}


def build_player_features(profile: PlayerSeasonEventProfile, match_ids: list[int]) -> dict:
    states = {state: aggregate_state_context(profile, state, match_ids) for state in STATE_NAMES}
    stint_profiles = list(
        PlayerSeasonEventProfile.objects.filter(
            competition_season=profile.competition_season,
            player_id=profile.player_id,
            split_type=EventProfileSplitType.TEAM,
            is_current=True,
        ).select_related("team", "player", "competition_season")
    )
    if len(stint_profiles) > 1:
        for state in STATE_NAMES:
            stint_contexts = [aggregate_state_context(stint, state, match_ids) for stint in stint_profiles]
            share_keys = set().union(*(context["team_action_shares"] for context in stint_contexts))
            for key in share_keys:
                value = weighted_average([
                    (context["team_action_shares"].get(key, {}).get("share"), context["exposure_seconds"])
                    for context in stint_contexts
                ])
                states[state]["team_action_shares"].setdefault(key, {})["share"] = round(value, 4) if value is not None else None
                states[state]["team_action_shares"][key]["unit"] = "exposure_weighted_stint_share"
            states[state]["team_touch_location"] = {
                "x": weighted_average([(context["team_touch_location"].get("x"), context["exposure_seconds"]) for context in stint_contexts]),
                "y": weighted_average([(context["team_touch_location"].get("y"), context["exposure_seconds"]) for context in stint_contexts]),
                "sample_size": sum(context["team_touch_location"].get("sample_size", 0) for context in stint_contexts),
            }
            states[state]["stint_evidence"] = [
                {"team_id": stint.team_id, "exposure_seconds": context["exposure_seconds"]}
                for stint, context in zip(stint_profiles, stint_contexts)
            ]
    goals = player_goal_evidence(profile)
    return {
        "position_group": position_group(profile),
        "states": states,
        "state_coverage": {
            state: {
                "exposure_seconds": states[state]["exposure_seconds"],
                "minutes": states[state]["exposure_minutes"],
                "matches": states[state]["evidence"]["match_count"],
                "episodes": states[state]["evidence"]["episode_count"],
            }
            for state in STATE_NAMES
        },
        "transition_exposure_seconds": states["losing"]["exposure_seconds"] + states["drawing"]["exposure_seconds"],
        **goals,
    }


def season_priors(feature_rows: dict[int, dict]) -> dict:
    totals = {state: defaultdict(int) for state in STATE_NAMES}
    exposure = {state: 0 for state in STATE_NAMES}
    for features in feature_rows.values():
        for state in STATE_NAMES:
            cohort = features["states"][state]
            exposure[state] += cohort["exposure_seconds"]
            for key, value in cohort["summary"].items():
                if isinstance(value, int):
                    totals[state][key] += value
    return {
        state: {key: value * 5400 / exposure[state] if exposure[state] else 0.0 for key, value in totals[state].items()}
        for state in STATE_NAMES
    }


@transaction.atomic
def materialize_player_season_roles(
    competition_season,
    *,
    affected_player_ids: Iterable[int] | None = None,
    affected_team_ids: Iterable[int] | None = None,
) -> dict:
    """Replace current role rows for a full season or the affected team/player union."""

    profiles = PlayerSeasonEventProfile.objects.filter(
        competition_season=competition_season,
        split_type=EventProfileSplitType.SEASON_TOTAL,
        is_current=True,
    ).select_related("player", "competition_season")
    target_ids = set(affected_player_ids or [])
    if affected_team_ids:
        target_ids.update(
            PlayerSeasonEventProfile.objects.filter(
                competition_season=competition_season,
                split_type=EventProfileSplitType.TEAM,
                team_id__in=set(affected_team_ids),
                is_current=True,
            ).values_list("player_id", flat=True)
        )
    if affected_player_ids is not None or affected_team_ids is not None:
        profiles = profiles.filter(player_id__in=target_ids)
    profiles = list(profiles)
    retirement_ids = set(target_ids) if (affected_player_ids is not None or affected_team_ids is not None) else set(
        PlayerSeasonRole.objects.filter(
            competition_season=competition_season,
            is_current=True,
        ).values_list("player_id", flat=True)
    )
    retirement_ids.update(profile.player_id for profile in profiles)
    match_ids = list(ProviderMatch.objects.filter(competition_season=competition_season).values_list("id", flat=True))
    feature_rows = {profile.player_id: build_player_features(profile, match_ids) for profile in profiles}
    priors = season_priors(feature_rows)
    latest_match = ProviderMatch.objects.filter(competition_season=competition_season).order_by("-kickoff_at", "-id").first()
    state_source_version = ProviderMatchTeamGameStateEpisode.objects.filter(
        provider_match__competition_season=competition_season,
    ).aggregate(value=Max("calculation_version"))["value"] or GAME_STATE_CALCULATION_VERSION
    participation_source_version = ProviderMatchPlayerStateExposure.objects.filter(
        player_interval__participation__provider_match__competition_season=competition_season,
    ).aggregate(value=Max("formula_version"))["value"] or PARTICIPATION_SOURCE_VERSION
    created = []
    for profile in profiles:
        features = feature_rows[profile.player_id]
        assignment = assign_role(features, priors)
        team_ids = list(
            PlayerSeasonEventProfile.objects.filter(
                competition_season=competition_season,
                player_id=profile.player_id,
                split_type=EventProfileSplitType.TEAM,
                is_current=True,
            ).values_list("team_id", flat=True)
        )
        created.append(PlayerSeasonRole(
            competition_season=competition_season,
            player_id=profile.player_id,
            team_context=team_ids,
            team_context_quality="multi_team_weighted" if len(team_ids) > 1 else "single_team",
            primary_role=assignment["primary_role"],
            primary_score=assignment["primary_score"],
            runner_up_role=assignment["runner_up_role"],
            runner_up_score=assignment["runner_up_score"],
            score_margin=assignment["score_margin"],
            confidence=assignment["confidence"],
            state_coverage=features["state_coverage"],
            verified_exposure_seconds=sum(item["exposure_seconds"] for item in features["state_coverage"].values()),
            evidence={
                "meaning": ROLE_MEANINGS.get(assignment["primary_role"]),
                "explanation": assignment["explanation"],
                "role_scores": assignment["scores"],
                "state_signals": {state: {
                    "progressive_actions_per_90": features["states"][state]["rates"]["progressive_actions"]["per_90"],
                    "progressive_carries_per_90": features["states"][state]["rates"]["progressive_carries"]["per_90"],
                    "shots_per_90": features["states"][state]["rates"]["shots"]["per_90"],
                    "touch_location": features["states"][state]["touch_location"],
                } for state in STATE_NAMES},
                "goal_evidence": {
                    "winning_state_goals": features["winning_goals"],
                    "state_changing_goals": features["state_changing_goals"],
                    "total_goals": features["total_goals"],
                },
            },
            calculation_version=PLAYER_SEASON_ROLE_VERSION,
            source_event_version=EVENT_PROFILE_VERSION,
            source_state_version=state_source_version,
            source_participation_version=participation_source_version,
            calculated_through_match=latest_match,
            calculated_through_date=latest_match.kickoff_at.date() if latest_match else None,
            is_current=False,
        ))
    PlayerSeasonRole.objects.bulk_create(created, batch_size=500)
    player_ids = [profile.player_id for profile in profiles]
    now = timezone.now()
    PlayerSeasonRole.objects.filter(
        competition_season=competition_season,
        player_id__in=retirement_ids,
        is_current=True,
    ).exclude(pk__in=[row.pk for row in created if row.pk]).update(is_current=False, superseded_at=now)
    new_ids = [row.pk for row in created if row.pk]
    PlayerSeasonRole.objects.filter(pk__in=new_ids).update(is_current=True)
    return {
        "calculation_version": PLAYER_SEASON_ROLE_VERSION,
        "players": len(created),
        "affected_player_ids": sorted(player_ids),
        "affected_team_ids": sorted(set(affected_team_ids or [])),
    }


def serialize_season_role(row: PlayerSeasonRole | None) -> dict:
    if row is None:
        return {
            "primary_role": None,
            "confidence": "pending",
            "freshness": "not_materialized",
            "explanation": "Role not established because the season role materialization is not available yet.",
        }
    return {
        "primary_role": row.primary_role,
        "primary_score": row.primary_score,
        "runner_up_role": row.runner_up_role,
        "runner_up_score": row.runner_up_score,
        "score_margin": row.score_margin,
        "confidence": row.confidence,
        "freshness": "current" if row.is_current else "stale",
        "state_coverage": row.state_coverage,
        "verified_exposure_seconds": row.verified_exposure_seconds,
        "team_context_quality": row.team_context_quality,
        "calculated_through": row.calculated_through_date.isoformat() if row.calculated_through_date else None,
        "calculation_version": row.calculation_version,
        "meaning": row.evidence.get("meaning"),
        "explanation": row.evidence.get("explanation"),
        "role_scores": row.evidence.get("role_scores", []),
        "state_signals": row.evidence.get("state_signals", {}),
        "goal_evidence": row.evidence.get("goal_evidence", {}),
    }
