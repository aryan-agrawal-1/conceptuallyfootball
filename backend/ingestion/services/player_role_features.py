"""Extract expensive, versioned player-team-season role evidence.

The scorer deliberately consumes only the JSON snapshot produced here. This
keeps taxonomy calibration cohort-complete and cheap without weakening the
ordinary production materialization path.
"""

from __future__ import annotations

from math import hypot
from typing import Iterable

from django.db import models, transaction
from django.utils import timezone

from ingestion.models import (
    EventProfileSplitType,
    MatchEventGameState,
    MatchEventShotOutcome,
    MatchEventShotSituation,
    MatchEventType,
    MatchStateDrawProvenance,
    PlayerSeasonDerivedStats,
    PlayerSeasonEventProfile,
    PlayerSeasonRoleFeatureSnapshot,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchPlayerStateExposure,
    ProviderMatchTeamGameStateEpisode,
)
from ingestion.services.event_profiles import FORMULA_VERSION as EVENT_PROFILE_VERSION
from ingestion.services.game_state import GAME_STATE_CALCULATION_VERSION
from ingestion.services.player_role_definitions import ROLE_FEATURE_VERSION
from ingestion.services.player_state_comparison import (
    action_context,
    carry_in_segments,
    event_in_segments,
    exposure_segments,
    player_state_evidence,
    possession_context,
    position_group,
    state_event_rows,
    team_matched_context,
    team_relative_shares,
)
from ingestion.services.possession_context import POSSESSION_CALCULATION_VERSION
from ingestion.services.player_participation import PARTICIPATION_FORMULA_VERSION
from ingestion.state_lens import StateLensScope


STATE_NAMES = ("losing", "drawing", "winning")
SET_PIECE_SHOT_SITUATIONS = {
    MatchEventShotSituation.SET_PIECE,
    MatchEventShotSituation.CORNER,
    MatchEventShotSituation.DIRECT_FREE_KICK,
    MatchEventShotSituation.PENALTY,
}


def ratio(numerator: int | float, denominator: int | float) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def per90(count: int | float, exposure_seconds: int) -> float | None:
    return round(count * 5400 / exposure_seconds, 4) if exposure_seconds else None


def is_open_play_event(event) -> bool:
    if event.is_set_piece or event.is_corner or event.is_free_kick or event.is_throw_in:
        return False
    if event.event_type == MatchEventType.SHOT and event.shot_situation in SET_PIECE_SHOT_SITUATIONS:
        return False
    return True


def line_breaking_pass(event) -> bool:
    if (
        event.event_type != MatchEventType.PASS
        or event.outcome_successful is not True
        or event.is_cross
        or None in (event.x, event.end_x)
    ):
        return False
    forward_distance = event.end_x - event.x
    crosses_line = (event.x < 3300 <= event.end_x) or (event.x < 6600 <= event.end_x)
    return event.is_through_ball or (forward_distance >= 1200 and crosses_line)


def central_location(event) -> bool:
    return event.y is not None and 2500 <= event.y <= 7500


def box_location(event) -> bool:
    return None not in (event.x, event.y) and event.x >= 8300 and 2100 <= event.y <= 7900


def event_geometry(events: list, exposure_seconds: int, *, goalkeeper: bool) -> dict:
    open_events = [event for event in events if is_open_play_event(event)]
    passes = [event for event in open_events if event.event_type == MatchEventType.PASS]
    completed_passes = [event for event in passes if event.outcome_successful is True]
    touches = [event for event in open_events if event.is_touch]
    defensive = [
        event for event in open_events
        if event.event_type in {
            MatchEventType.BALL_RECOVERY,
            MatchEventType.TACKLE,
            MatchEventType.INTERCEPTION,
            MatchEventType.CLEARANCE,
            MatchEventType.BLOCKED_PASS,
            MatchEventType.AERIAL,
            MatchEventType.CHALLENGE,
        } and (event.event_type not in {MatchEventType.AERIAL, MatchEventType.CHALLENGE} or event.is_defensive)
    ]
    line_breaks = [event for event in completed_passes if line_breaking_pass(event)]
    build_up_passes = [event for event in passes if event.x is not None and event.x <= 4500]
    build_up_progressive = [event for event in build_up_passes if event.is_progressive_pass]
    central_progressive = [event for event in passes if event.is_progressive_pass and central_location(event)]
    advanced_actions = [event for event in open_events if event.x is not None and event.x >= 6000]
    advanced_touches = [event for event in touches if event.x is not None and event.x >= 6000]
    central_touches = [event for event in touches if central_location(event)]
    box_touches = [event for event in touches if box_location(event)]
    shots = [event for event in open_events if event.event_type == MatchEventType.SHOT]
    key_passes = [event for event in passes if event.is_key_pass or event.is_shot_assist]
    dangerous_entries = [event for event in passes if event.is_final_third_entry or event.is_box_entry]
    deep_defensive = [event for event in defensive if event.x is not None and event.x <= 4000]
    protective = [
        event for event in deep_defensive
        if event.event_type in {MatchEventType.CLEARANCE, MatchEventType.BLOCKED_PASS, MatchEventType.AERIAL}
    ]
    ball_wins = [
        event for event in defensive
        if event.event_type in {
            MatchEventType.BALL_RECOVERY,
            MatchEventType.TACKLE,
            MatchEventType.INTERCEPTION,
            MatchEventType.CHALLENGE,
        }
    ]
    tackles_interceptions = [
        event for event in defensive
        if event.event_type in {MatchEventType.TACKLE, MatchEventType.INTERCEPTION}
    ]
    aerials = [event for event in open_events if event.event_type == MatchEventType.AERIAL]
    turnovers = [
        event for event in open_events
        if event.event_type == MatchEventType.DISPOSSESSED
        or (event.event_type == MatchEventType.TAKE_ON and event.outcome_successful is False)
    ]
    long_progressive = [event for event in passes if event.is_long_ball or event.is_progressive_pass]
    defensive_x = [event.x / 100 for event in defensive if event.x is not None]
    sweeper_actions = [
        event for event in open_events
        if goalkeeper
        and event.x is not None
        and event.x >= 1800
        and event.event_type in {
            MatchEventType.PASS,
            MatchEventType.BALL_RECOVERY,
            MatchEventType.CLEARANCE,
        }
    ]
    saves = [event for event in open_events if event.event_type == MatchEventType.SAVE]
    close_saves = [event for event in saves if event.x is not None and event.x <= 1800]
    set_piece_events = [
        event for event in events
        if event.is_set_piece or event.is_corner or event.is_free_kick
    ]
    set_piece_creation = [event for event in set_piece_events if event.is_key_pass or event.is_shot_assist]
    return {
        "open_play_events": len(open_events),
        "touches": len(touches),
        "passes": len(passes),
        "completed_passes": len(completed_passes),
        "pass_completion": ratio(len(completed_passes), len(passes)),
        "central_touches": len(central_touches),
        "central_touch_share": ratio(len(central_touches), len(touches)),
        "advanced_actions": len(advanced_actions),
        "advanced_touches": len(advanced_touches),
        "advanced_touch_share": ratio(len(advanced_touches), len(touches)),
        "box_touches": len(box_touches),
        "box_touch_share": ratio(len(box_touches), len(touches)),
        "shots": len(shots),
        "key_passes": len(key_passes),
        "line_breaking_passes": len(line_breaks),
        "line_break_frequency": ratio(len(line_breaks), len(passes)),
        "build_up_passes": len(build_up_passes),
        "build_up_progressive_passes": len(build_up_progressive),
        "central_progressive_passes": len(central_progressive),
        "dangerous_entries": len(dangerous_entries),
        "long_progressive_passes": len(long_progressive),
        "defensive_actions": len(defensive),
        "deep_defensive_actions": len(deep_defensive),
        "protective_interventions": len(protective),
        "ball_wins": len(ball_wins),
        "tackles_interceptions": len(tackles_interceptions),
        "defensive_height": round(sum(defensive_x) / len(defensive_x), 4) if defensive_x else None,
        "aerials": len(aerials),
        "turnovers": len(turnovers),
        "set_piece_actions": len(set_piece_events),
        "set_piece_creation": len(set_piece_creation),
        "sweeper_actions": len(sweeper_actions),
        "sweeper_height": round(sum(event.x / 100 for event in sweeper_actions) / len(sweeper_actions), 4) if sweeper_actions else None,
        "saves": len(saves),
        "close_range_saves": len(close_saves),
        "rates_per90": {
            "touches": per90(len(touches), exposure_seconds),
            "passes": per90(len(passes), exposure_seconds),
            "line_breaking_passes": per90(len(line_breaks), exposure_seconds),
            "box_touches": per90(len(box_touches), exposure_seconds),
            "shots": per90(len(shots), exposure_seconds),
            "key_passes": per90(len(key_passes), exposure_seconds),
            "defensive_actions": per90(len(defensive), exposure_seconds),
            "ball_wins": per90(len(ball_wins), exposure_seconds),
            "deep_defensive_actions": per90(len(deep_defensive), exposure_seconds),
            "aerials": per90(len(aerials), exposure_seconds),
            "turnovers": per90(len(turnovers), exposure_seconds),
            "sweeper_actions": per90(len(sweeper_actions), exposure_seconds),
            "saves": per90(len(saves), exposure_seconds),
        },
    }


def compact_transition(context: dict) -> dict:
    leverage = context.get("transition_leverage", {})
    stages = leverage.get("sequence_stages", {})
    return {
        "available": bool(context.get("available")),
        "opportunities": leverage.get("opportunities", 0),
        "involved_possessions": context.get("involved_possessions", 0),
        "counter_possessions": context.get("counter_possessions", 0),
        "shot_producing_possessions": context.get("shot_producing_possessions", 0),
        "final_third_possessions": context.get("final_third_possessions", 0),
        "advancement_actions": stages.get("advancement", {}).get("actions", 0),
        "escape_actions": stages.get("escape", {}).get("actions", 0),
    }


def state_context(
    profile,
    state: str,
    match_ids: list[int],
    *,
    all_player_events: list,
    all_team_events: list,
    all_player_carries: list,
    all_team_carries: list,
) -> dict:
    scope = StateLensScope(state=state)
    segments = exposure_segments(profile, scope, match_ids)
    player_events = [
        event for event in all_player_events
        if event_in_segments(event, segments, event.team_id)
    ]
    team_events = [
        event for event in all_team_events
        if event_in_segments(event, segments, event.team_id)
    ]
    carries = [
        carry for carry in all_player_carries
        if carry_in_segments(carry, segments, carry.team_id)
    ]
    team_carries = [
        carry for carry in all_team_carries
        if carry_in_segments(carry, segments, carry.team_id)
    ]
    evidence = player_state_evidence(profile, match_ids, scope)
    open_player_events = [event for event in player_events if is_open_play_event(event)]
    open_team_events = [event for event in team_events if is_open_play_event(event)]
    player = action_context(open_player_events, carries, evidence["exposure_seconds"], include_defensive_families=False)
    team = team_matched_context(open_team_events, team_carries, segments, evidence["exposure_seconds"])
    return {
        "exposure_seconds": evidence["exposure_seconds"],
        "match_count": evidence["match_count"],
        "episode_count": evidence["episode_count"],
        "summary": player["summary"],
        "rates": player["rates"],
        "passing": player["passing"],
        "carrying": player["carrying"],
        "touch_location": player["touch_location"],
        "touch_grid": player["touch_grid"],
        "team_touch_location": team["touch_location"],
        "team_action_shares": team_relative_shares(player["summary"], team["summary"]),
    }


def direct_assist_events(all_events: list) -> dict[tuple[int, int], list[tuple[object, object]]]:
    """Resolve at most one final intentional-assist event for each goal."""

    events_by_match_team = {}
    for event in all_events:
        if event.team_id is not None and event.timeline_seconds is not None and not event.is_deleted_event:
            events_by_match_team.setdefault((event.provider_match_id, event.team_id), []).append(event)
    resolved = {}
    used_assist_ids = set()
    for rows in events_by_match_team.values():
        goals = [
            event for event in rows
            if event.shot_outcome == MatchEventShotOutcome.GOAL and not event.is_goal_disallowed
        ]
        assist_candidates = [
            event for event in rows
            if event.player_id is not None and event.is_intentional_assist
        ]
        for goal in goals:
            candidates = [
                event for event in assist_candidates
                if event.id not in used_assist_ids
                and 0 <= goal.timeline_seconds - event.timeline_seconds <= 20
            ]
            if not candidates:
                continue
            assist = max(candidates, key=lambda event: (event.timeline_seconds, event.event_index))
            used_assist_ids.add(assist.id)
            resolved.setdefault((assist.player_id, assist.team_id), []).append((assist, goal))
    return resolved


def goal_transition_context(competition_season, *, match_ids: Iterable[int] | None = None) -> dict[int, dict]:
    """Describe the draw provenance immediately before each score transition."""

    episodes_query = ProviderMatchTeamGameStateEpisode.objects.filter(
        provider_match__competition_season=competition_season,
    )
    if match_ids is not None:
        episodes_query = episodes_query.filter(provider_match_id__in=match_ids)
    episodes = list(episodes_query.order_by("provider_match_id", "focal_team_id", "episode_index"))
    by_key = {
        (episode.provider_match_id, episode.focal_team_id, episode.episode_index): episode
        for episode in episodes
    }
    contexts = {}
    for episode in episodes:
        if episode.entry_event_id is None:
            continue
        if (
            episode.previous_state == MatchEventGameState.LOSING
            and episode.state == MatchEventGameState.DRAWING
        ):
            contexts[episode.entry_event_id] = {
                "transition": "losing_to_drawing",
                "draw_provenance": episode.draw_provenance,
                "clutch_eligible": True,
            }
        elif (
            episode.previous_state == MatchEventGameState.DRAWING
            and episode.state == MatchEventGameState.WINNING
        ):
            previous = by_key.get((
                episode.provider_match_id,
                episode.focal_team_id,
                episode.episode_index - 1,
            ))
            provenance = previous.draw_provenance if previous is not None else None
            contexts[episode.entry_event_id] = {
                "transition": "drawing_to_winning",
                "draw_provenance": provenance,
                "clutch_eligible": provenance in {
                    MatchStateDrawProvenance.RESTORED,
                    MatchStateDrawProvenance.SURRENDERED,
                },
            }
    return contexts


def clutch_context_counts(goals: list, goal_context: dict[int, dict], suffix: str) -> dict:
    contexts = [goal_context.get(goal.id, {}) for goal in goals]
    return {
        f"equalising_{suffix}": sum(context.get("transition") == "losing_to_drawing" for context in contexts),
        f"restored_draw_winning_{suffix}": sum(
            context.get("transition") == "drawing_to_winning"
            and context.get("draw_provenance") == MatchStateDrawProvenance.RESTORED
            for context in contexts
        ),
        f"surrendered_draw_winning_{suffix}": sum(
            context.get("transition") == "drawing_to_winning"
            and context.get("draw_provenance") == MatchStateDrawProvenance.SURRENDERED
            for context in contexts
        ),
        f"neutral_draw_winning_{suffix}_excluded": sum(
            context.get("transition") == "drawing_to_winning"
            and context.get("draw_provenance") == MatchStateDrawProvenance.NEUTRAL
            for context in contexts
        ),
    }


def assist_evidence(profile, valid_event_ids: set[int], resolved_assists: dict, goal_context: dict[int, dict]) -> dict:
    pairs = [
        pair for pair in resolved_assists.get((profile.player_id, profile.team_id), [])
        if pair[0].id in valid_event_ids
    ]
    return {
        "intentional_assists": len(pairs),
        "state_changing_assists": sum(
            goal_context.get(goal.id, {}).get("clutch_eligible") is True
            for _assist, goal in pairs
        ),
        "winning_state_assists": sum(
            goal.game_state_before == MatchEventGameState.WINNING
            for _assist, goal in pairs
        ),
        **clutch_context_counts([goal for _assist, goal in pairs], goal_context, "assists"),
    }


def score_event_evidence(
    profile,
    player_events: list,
    resolved_assists: dict,
    goal_context: dict[int, dict],
    *,
    valid_event_ids: set[int] | None = None,
) -> dict:
    goals = [
        event for event in player_events
        if event.shot_outcome == MatchEventShotOutcome.GOAL
        and not event.is_goal_disallowed
        and not event.is_deleted_event
    ]
    state_changing_goals = sum(
        goal_context.get(event.id, {}).get("clutch_eligible") is True
        for event in goals
    )
    valid_ids = valid_event_ids if valid_event_ids is not None else {event.id for event in player_events}
    assists = assist_evidence(profile, valid_ids, resolved_assists, goal_context)
    return {
        "goals": len(goals),
        "state_changing_goals": state_changing_goals,
        "winning_state_goals": sum(event.game_state_before == MatchEventGameState.WINNING for event in goals),
        **clutch_context_counts(goals, goal_context, "goals"),
        **assists,
    }


def spatial_state_features(states: dict) -> dict:
    observed = [state for state in STATE_NAMES if states[state]["exposure_seconds"] >= 90 * 60]
    locations = [states[state]["touch_location"] for state in observed]
    movements = []
    relative_movements = []
    overlaps = []
    for first_name, second_name in zip(observed, observed[1:]):
        first = states[first_name]["touch_location"]
        second = states[second_name]["touch_location"]
        team_first = states[first_name]["team_touch_location"]
        team_second = states[second_name]["team_touch_location"]
        if None not in (first.get("x"), first.get("y"), second.get("x"), second.get("y")):
            movements.append(hypot(second["x"] - first["x"], second["y"] - first["y"]))
        if None not in (
            first.get("x"), first.get("y"), second.get("x"), second.get("y"),
            team_first.get("x"), team_first.get("y"), team_second.get("x"), team_second.get("y"),
        ):
            relative_movements.append(hypot(
                (second["x"] - first["x"]) - (team_second["x"] - team_first["x"]),
                (second["y"] - first["y"]) - (team_second["y"] - team_first["y"]),
            ))
        first_grid = states[first_name]["touch_grid"]
        second_grid = states[second_name]["touch_grid"]
        if first_grid and len(first_grid) == len(second_grid):
            difference = sum(abs(a.get("share", 0) - b.get("share", 0)) for a, b in zip(first_grid, second_grid))
            overlaps.append(max(0.0, 1 - difference / 2))
    return {
        "observed_states": observed,
        "mean_centroid_movement": round(sum(movements) / len(movements), 4) if movements else None,
        "mean_relative_movement": round(sum(relative_movements) / len(relative_movements), 4) if relative_movements else None,
        "mean_heatmap_overlap": round(sum(overlaps) / len(overlaps), 4) if overlaps else None,
        "location_samples": sum(location.get("sample_size", 0) for location in locations),
    }


def supporting_metrics(profile) -> dict:
    row = PlayerSeasonDerivedStats.objects.filter(
        competition_season=profile.competition_season,
        canonical_player_id=profile.player_id,
        is_current=True,
    ).first()
    if row is None:
        return {}
    return {
        "native_position": row.native_position,
        "position_group": row.position_group,
        "minutes": row.minutes,
        "xg_per_90": row.xg_per_90,
        "xa_per_90": row.xa_per_90,
        "key_passes_per_90": row.key_passes_per_90,
        "successful_dribbles_per_90": row.successful_dribbles_per_90,
    }


def build_feature_snapshot(
    profile: PlayerSeasonEventProfile,
    match_ids: list[int],
    all_events: list,
    resolved_assists: dict,
    goal_context: dict[int, dict],
) -> dict:
    overall_scope = StateLensScope(state="all")
    player_events, team_events, carries, team_carries, _events, segments = state_event_rows(profile, overall_scope, match_ids)
    evidence = player_state_evidence(profile, match_ids, overall_scope)
    open_player_events = [event for event in player_events if is_open_play_event(event)]
    open_team_events = [event for event in team_events if is_open_play_event(event)]
    overall = action_context(open_player_events, carries, evidence["exposure_seconds"], include_defensive_families=False)
    team = team_matched_context(open_team_events, team_carries, segments, evidence["exposure_seconds"])
    group = position_group(profile)
    states = {
        state: state_context(
            profile,
            state,
            match_ids,
            all_player_events=player_events,
            all_team_events=team_events,
            all_player_carries=carries,
            all_team_carries=team_carries,
        )
        for state in STATE_NAMES
    }
    support = supporting_metrics(profile)
    return {
        "identity": {
            "player_id": profile.player_id,
            "team_id": profile.team_id,
            "competition_season_id": profile.competition_season_id,
        },
        "position": {
            "group": group,
            "recorded": support.get("native_position", ""),
            "average_touch": overall["touch_location"],
        },
        "exposure": {
            "verified_seconds": evidence["exposure_seconds"],
            "matches": evidence["match_count"],
            "episodes": evidence["episode_count"],
        },
        "overall": {
            "summary": overall["summary"],
            "passing": overall["passing"],
            "carrying": overall["carrying"],
            "touch_location": overall["touch_location"],
            "team_action_shares": team_relative_shares(overall["summary"], team["summary"]),
            "geometry": event_geometry(player_events, evidence["exposure_seconds"], goalkeeper=group == "GK"),
            "team_geometry": event_geometry(team_events, evidence["exposure_seconds"], goalkeeper=False),
        },
        "states": states,
        "state_spatial": spatial_state_features(states),
        "transitions": compact_transition(possession_context(profile, segments, overall_scope)),
        "score_events": score_event_evidence(profile, player_events, resolved_assists, goal_context),
        "supporting_metrics": support,
    }


def source_versions(competition_season) -> dict:
    state_version = ProviderMatchTeamGameStateEpisode.objects.filter(
        provider_match__competition_season=competition_season,
    ).aggregate(value=models.Max("calculation_version"))["value"] or GAME_STATE_CALCULATION_VERSION
    participation_version = ProviderMatchPlayerStateExposure.objects.filter(
        player_interval__participation__provider_match__competition_season=competition_season,
    ).aggregate(value=models.Max("formula_version"))["value"] or PARTICIPATION_FORMULA_VERSION
    return {
        "event": EVENT_PROFILE_VERSION,
        "state": state_version,
        "participation": participation_version,
        "possession": POSSESSION_CALCULATION_VERSION,
    }


def materialize_player_role_features(
    competition_season,
    *,
    affected_player_ids: Iterable[int] | None = None,
    affected_team_ids: Iterable[int] | None = None,
) -> dict:
    """Extract and atomically publish current snapshots for selected stints."""

    profiles = PlayerSeasonEventProfile.objects.filter(
        competition_season=competition_season,
        split_type=EventProfileSplitType.TEAM,
        team__isnull=False,
        is_current=True,
    ).select_related("player", "team", "competition_season")
    target_player_ids = set(affected_player_ids) if affected_player_ids is not None else None
    target_team_ids = set(affected_team_ids) if affected_team_ids is not None else None
    if target_player_ids is not None or target_team_ids is not None:
        target_scope = models.Q()
        if target_player_ids is not None:
            target_scope |= models.Q(player_id__in=target_player_ids)
        if target_team_ids is not None:
            target_scope |= models.Q(team_id__in=target_team_ids)
        profiles = profiles.filter(target_scope)
    profiles = list(profiles.order_by("player_id", "team_id"))
    match_ids = list(ProviderMatch.objects.filter(competition_season=competition_season).values_list("id", flat=True))
    all_events = list(ProviderMatchEvent.objects.filter(
        provider_match__competition_season=competition_season,
    ).select_related("player", "team"))
    resolved_assists = direct_assist_events(all_events)
    goal_context = goal_transition_context(competition_season)
    latest_match = ProviderMatch.objects.filter(competition_season=competition_season).order_by("-kickoff_at", "-id").first()
    versions = source_versions(competition_season)
    rows = []
    total_exposure = 0
    for profile in profiles:
        features = build_feature_snapshot(profile, match_ids, all_events, resolved_assists, goal_context)
        exposure = features["exposure"]["verified_seconds"]
        total_exposure += exposure
        rows.append(PlayerSeasonRoleFeatureSnapshot(
            competition_season=competition_season,
            player_id=profile.player_id,
            team_id=profile.team_id,
            feature_version=ROLE_FEATURE_VERSION,
            features=features,
            verified_exposure_seconds=exposure,
            source_event_version=versions["event"],
            source_state_version=versions["state"],
            source_participation_version=versions["participation"],
            source_possession_version=versions["possession"],
            calculated_through_match=latest_match,
            calculated_through_date=latest_match.kickoff_at.date() if latest_match else None,
            is_current=False,
        ))
    pairs = {(profile.player_id, profile.team_id) for profile in profiles}
    with transaction.atomic():
        PlayerSeasonRoleFeatureSnapshot.objects.bulk_create(rows, batch_size=250)
        now = timezone.now()
        current = PlayerSeasonRoleFeatureSnapshot.objects.filter(
            competition_season=competition_season,
            is_current=True,
        )
        if target_player_ids is not None or target_team_ids is not None:
            target_scope = models.Q()
            if target_player_ids is not None:
                target_scope |= models.Q(player_id__in=target_player_ids)
            if target_team_ids is not None:
                target_scope |= models.Q(team_id__in=target_team_ids)
            current = current.filter(target_scope)
        current.exclude(pk__in=[row.pk for row in rows]).update(is_current=False, superseded_at=now)
        PlayerSeasonRoleFeatureSnapshot.objects.filter(pk__in=[row.pk for row in rows]).update(is_current=True)
    return {
        "feature_version": ROLE_FEATURE_VERSION,
        "snapshots": len(rows),
        "verified_exposure_seconds": total_exposure,
        "affected_player_ids": sorted({player_id for player_id, _team_id in pairs}),
        "affected_team_ids": sorted({team_id for _player_id, team_id in pairs}),
    }


def refresh_score_event_features(
    competition_season,
    *,
    affected_player_ids: Iterable[int] | None = None,
    affected_team_ids: Iterable[int] | None = None,
) -> dict:
    """Publish corrected score-event evidence without repeating spatial extraction."""

    target_player_ids = set(affected_player_ids) if affected_player_ids is not None else None
    target_team_ids = set(affected_team_ids) if affected_team_ids is not None else None
    snapshots = PlayerSeasonRoleFeatureSnapshot.objects.filter(
        competition_season=competition_season,
        is_current=True,
    ).select_related("calculated_through_match")
    if target_player_ids is not None or target_team_ids is not None:
        target_scope = models.Q()
        if target_player_ids is not None:
            target_scope |= models.Q(player_id__in=target_player_ids)
        if target_team_ids is not None:
            target_scope |= models.Q(team_id__in=target_team_ids)
        snapshots = snapshots.filter(target_scope)
    snapshots = list(snapshots.order_by("player_id", "team_id"))
    goal_context = goal_transition_context(competition_season)
    from ingestion.services.player_role_score_events import build_score_event_index

    target_pairs = {(snapshot.player_id, snapshot.team_id) for snapshot in snapshots}
    score_index = build_score_event_index(competition_season, target_pairs, goal_context)
    rows = []
    for snapshot in snapshots:
        corrected = score_index.evidence(snapshot.player_id, snapshot.team_id)
        features = snapshot.features | {
            "score_events": snapshot.features.get("score_events", {}) | corrected,
        }
        rows.append(PlayerSeasonRoleFeatureSnapshot(
            competition_season=competition_season,
            player_id=snapshot.player_id,
            team_id=snapshot.team_id,
            feature_version=ROLE_FEATURE_VERSION,
            features=features,
            verified_exposure_seconds=snapshot.verified_exposure_seconds,
            source_event_version=snapshot.source_event_version,
            source_state_version=snapshot.source_state_version,
            source_participation_version=snapshot.source_participation_version,
            source_possession_version=snapshot.source_possession_version,
            calculated_through_match=snapshot.calculated_through_match,
            calculated_through_date=snapshot.calculated_through_date,
            is_current=False,
        ))
    with transaction.atomic():
        PlayerSeasonRoleFeatureSnapshot.objects.bulk_create(rows, batch_size=250)
        now = timezone.now()
        current_ids = [snapshot.pk for snapshot in snapshots]
        PlayerSeasonRoleFeatureSnapshot.objects.filter(pk__in=current_ids).update(
            is_current=False,
            superseded_at=now,
        )
        PlayerSeasonRoleFeatureSnapshot.objects.filter(pk__in=[row.pk for row in rows]).update(is_current=True)
    return {
        "feature_version": ROLE_FEATURE_VERSION,
        "snapshots": len(rows),
        "mode": "score_events_only",
    }
