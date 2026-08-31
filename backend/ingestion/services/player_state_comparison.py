"""Verified player game-state cohorts and matched team evidence.

The player-facing State Lens has a stricter denominator than the team views:
an event is eligible only when it falls inside a verified player interval and
the corresponding verified team state episode.  This module keeps that rule
in one place for the event-profile and comparison APIs.  It intentionally
uses the already-materialized exposure rows; it does not rebuild possession
chains or infer participation from event presence.
"""

from __future__ import annotations

from collections import Counter
from statistics import median
from typing import Iterable

from django.db.models import Count

from ingestion.models import (
    MatchEventGameState,
    MatchEventShotOutcome,
    MatchEventType,
    MatchGameStateExclusionReason,
    PlayerSeasonDerivedStats,
    PlayerSeasonGkDerivedStats,
    ProviderMatchCarry,
    ProviderMatchEvent,
    ProviderMatchGameState,
    Provider,
)
from ingestion.services.defensive_territory import FAMILY_BY_TYPE, defensive_family
from ingestion.services.player_state_scope import (
    ANY_TEAM,
    PlayerExposureSegment,
    carry_in_segments,
    event_in_segments,
    event_second,
    exposure_queryset,
    exposure_segments,
    participation_queryset,
    player_event_scope_segments,
    scope_age_bounds,
    scope_match_ids,
    scope_player_carries,
    scope_player_events,
    value_in_segments,
    verified_event_ids,
)
from ingestion.services.player_transition_evidence import possession_context
from ingestion.services.whoscored_normalization import (
    ACTION_GRID_COLUMNS,
    ACTION_GRID_ROWS,
    action_grid_assignment,
    is_action_event,
    is_defensive_event,
)
from ingestion.state_lens import (
    GAME_STATE_CALCULATION_VERSION,
    STATE_VALUES,
    StateLens,
    StateLensScope,
)


PLAYER_STATE_COMPARISON_VERSION = "player_state_comparison_v3"
DEFENSIVE_ACTION_FAMILIES = tuple(dict.fromkeys(FAMILY_BY_TYPE.values()))


def player_state_evidence(profile, match_ids: Iterable[int], scope: StateLensScope) -> dict:
    match_ids = list(dict.fromkeys(int(value) for value in match_ids))
    segments = exposure_segments(profile, scope, match_ids)
    exposure_seconds = sum(segment.duration_seconds for segment in segments)
    episode_keys = {(segment.match_id, segment.episode_index) for segment in segments}
    segment_match_ids = {segment.match_id for segment in segments}
    participation_rows = list(participation_queryset(profile, match_ids))
    candidate_match_ids = {row.provider_match_id for row in participation_rows}
    included_participation_match_ids = {
        row.provider_match_id
        for row in participation_rows
        if row.status == "verified" and row.confidence == "verified"
    }
    excluded_match_ids = candidate_match_ids - included_participation_match_ids
    reasons: Counter[str] = Counter()
    for row in participation_rows:
        if row.provider_match_id in excluded_match_ids:
            reasons[row.exclusion_reason or "participation_unverified"] += 1
    if included_participation_match_ids - segment_match_ids:
        reasons["no_selected_state_exposure"] += len(included_participation_match_ids - segment_match_ids)
    audits = ProviderMatchGameState.objects.filter(provider_match_id__in=match_ids)
    for row in audits.filter(eligible=False).values("exclusion_reason").annotate(count=Count("id")):
        reasons[str(row["exclusion_reason"] or MatchGameStateExclusionReason.INVALID_SCORE_REPLAY)] += row["count"]
    audit_ids = set(audits.values_list("provider_match_id", flat=True))
    if missing := set(match_ids) - audit_ids:
        reasons[str(MatchGameStateExclusionReason.INVALID_SCORE_REPLAY)] += len(missing)
    matches_included = len(included_participation_match_ids & segment_match_ids)
    matches_excluded = max(0, len(candidate_match_ids) - matches_included)
    return {
        "exposure_seconds": exposure_seconds,
        "exposure_minutes": round(exposure_seconds / 60, 2),
        "episode_count": len(episode_keys),
        "match_count": len(segment_match_ids),
        "matches_included": matches_included,
        "matches_excluded": matches_excluded,
        "exclusion_reasons": dict(sorted(reasons.items())),
        "formula_version": GAME_STATE_CALCULATION_VERSION,
        "empty": exposure_seconds == 0,
        "reliability": {
            "eligible_only": True,
            "verified_player_intervals_only": True,
            "timeline": "half_open_played_seconds",
            "shootouts_included": False,
        },
    }


def player_state_lens_metadata(profile, match_ids: Iterable[int], lens: StateLens) -> dict:
    match_ids = list(dict.fromkeys(int(value) for value in match_ids))
    all_exposures = list(exposure_queryset(profile, match_ids))
    refinement_states = {
        value for value, code in STATE_VALUES.items()
        if any(row.coarse_state == code for row in all_exposures)
    }
    goal_differences = sorted({row.goal_difference for row in all_exposures})
    phases = sorted({row.phase for row in all_exposures})
    provenances = sorted({row.provenance for row in all_exposures})
    maximum_age = max(
        (row.team_episode.end_second - row.team_episode.state_entry_second for row in all_exposures),
        default=None,
    )
    selected = player_state_evidence(profile, match_ids, lens.selected)
    baseline = (
        player_state_evidence(profile, match_ids, lens.baseline)
        if lens.baseline is not None else None
    )
    return {
        "contract_version": PLAYER_STATE_COMPARISON_VERSION,
        "selected": lens.selected.public(),
        "evidence": selected,
        "eligible_refinements": {
            "states": sorted(refinement_states),
            "goal_differences": goal_differences,
            "phases": phases,
            "draw_provenances": provenances,
            "state_age_seconds": {"minimum": 0 if all_exposures else None, "maximum": maximum_age},
        },
        "comparison": {
            "enabled": lens.comparison_enabled,
            "baseline": lens.baseline.public() if lens.baseline else None,
            "baseline_evidence": baseline,
            "comparison": lens.selected.public(),
            "comparison_evidence": selected,
        },
    }


def metric_rate(count: int, exposure_seconds: int) -> dict:
    per_minute = count / (exposure_seconds / 60) if exposure_seconds > 0 else None
    per_90 = count * 5400 / exposure_seconds if exposure_seconds > 0 else None
    return {
        "count": count,
        "per_state_minute": round(per_minute, 4) if per_minute is not None else None,
        "per_90": round(per_90, 4) if per_90 is not None else None,
    }


def percentage(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def coordinate(event, attribute: str) -> float | None:
    value = getattr(event, attribute, None)
    return round(value / 100, 4) if value is not None else None


def average_location(events: Iterable, *, x_attribute: str = "x", y_attribute: str = "y") -> dict:
    points = [
        (coordinate(event, x_attribute), coordinate(event, y_attribute))
        for event in events
    ]
    points = [(x, y) for x, y in points if x is not None and y is not None]
    return {
        "x": round(sum(point[0] for point in points) / len(points), 4) if points else None,
        "y": round(sum(point[1] for point in points) / len(points), 4) if points else None,
        "sample_size": len(points),
    }


def grid(events: Iterable, exposure_seconds: int, *, defensive: bool = False) -> list[dict]:
    counts = [0] * (ACTION_GRID_COLUMNS * ACTION_GRID_ROWS)
    for event in events:
        if event.x is None or event.y is None:
            continue
        if defensive and not is_defensive_event(event.event_type, defensive_qualifier=event.is_defensive):
            continue
        if not defensive and not event.is_touch:
            continue
        _, _, index = action_grid_assignment(event.x, event.y)
        counts[index] += 1
    total = sum(counts)
    cells = []
    for column in range(ACTION_GRID_COLUMNS):
        for row in range(ACTION_GRID_ROWS):
            count = counts[column * ACTION_GRID_ROWS + row]
            cells.append({
                "column": column,
                "row": row,
                "raw_count": count,
                "per_state_minute": round(count / (exposure_seconds / 60), 4) if exposure_seconds else None,
                "per_90": round(count * 5400 / exposure_seconds, 4) if exposure_seconds else None,
                "share": round(count / total, 6) if total else 0.0,
            })
    return cells


def defensive_family_data(events: Iterable, exposure_seconds: int) -> dict:
    """Return the player defensive-action contract split by team family.

    The team defensive territory surface and player State Lens use the same
    family classifier.  Keeping the split here means the player map can offer
    the same seven action filters without changing the existing all-actions
    grid contract.
    """

    family_events = {family: [] for family in DEFENSIVE_ACTION_FAMILIES}
    for event in events:
        if event.is_deleted_event:
            continue
        family = defensive_family(event)
        if family in family_events:
            family_events[family].append(event)

    family_data = {}
    for family, rows in family_events.items():
        heights = [coordinate(event, "x") for event in rows if event.x is not None]
        heights = [value for value in heights if value is not None]
        family_data[family] = {
            "count": len(rows),
            "located_count": sum(event.x is not None and event.y is not None for event in rows),
            "rate_per_state_minute": metric_rate(len(rows), exposure_seconds)["per_state_minute"],
            "height": {
                "sample_size": len(heights),
                "mean": round(sum(heights) / len(heights), 4) if heights else None,
                "median": round(median(heights), 4) if heights else None,
            },
            "grid": grid(rows, exposure_seconds, defensive=True),
        }
    return family_data


def state_event_rows(profile, scope: StateLensScope, match_ids: Iterable[int] | None = None) -> tuple[list, list, list, list, list, list[PlayerExposureSegment]]:
    segments = exposure_segments(profile, scope, match_ids)
    ids = {segment.match_id for segment in segments}
    events = list(
        ProviderMatchEvent.objects.filter(
            provider_match__competition_season=profile.competition_season,
            provider_match__provider=Provider.WHOSCORED,
            provider_match_id__in=ids,
        ).select_related("player", "team")
    )
    player_events = [
        event for event in events
        if event.player_id == profile.player_id
        and (profile.team_id is None or event.team_id == profile.team_id)
        and event_in_segments(event, segments, event.team_id)
    ]
    team_events = [
        event for event in events
        if event.team_id is not None and event_in_segments(event, segments, event.team_id)
    ]
    carries = list(
        ProviderMatchCarry.objects.filter(
            provider_match__competition_season=profile.competition_season,
            player_id=profile.player_id,
            provider_match_id__in=ids,
        ).select_related("team")
    )
    if profile.team_id is not None:
        carries = [carry for carry in carries if carry.team_id == profile.team_id]
    carries = [carry for carry in carries if carry_in_segments(carry, segments, carry.team_id)]
    team_ids = {segment.team_id for segment in segments if segment.team_id is not None}
    team_carries = list(
        ProviderMatchCarry.objects.filter(
            provider_match__competition_season=profile.competition_season,
            provider_match__provider=Provider.WHOSCORED,
            provider_match_id__in=ids,
            team_id__in=team_ids,
        ).select_related("team")
    )
    team_carries = [
        carry for carry in team_carries
        if carry_in_segments(carry, segments, carry.team_id)
    ]
    return player_events, team_events, carries, team_carries, events, segments


def event_summary(events: Iterable, carries: Iterable = ()) -> dict:
    events = list(events)
    carries = list(carries)
    passes = [event for event in events if event.event_type == MatchEventType.PASS]
    shots = [event for event in events if event.event_type == MatchEventType.SHOT]
    defensive = [
        event for event in events
        if is_defensive_event(event.event_type, defensive_qualifier=event.is_defensive)
    ]
    touches = [event for event in events if event.is_touch]
    progressive_passes = [event for event in passes if event.is_progressive_pass]
    progressive_carries = [carry for carry in carries if carry.is_progressive_carry]
    return {
        "touches": len(touches),
        "actions": sum(
            is_action_event(event.event_type, defensive_qualifier=event.is_defensive)
            for event in events
        ),
        "pass_attempts": len(passes),
        "pass_completions": sum(event.outcome_successful is True for event in passes),
        "progressive_passes": len(progressive_passes),
        "progressive_carries": len(progressive_carries),
        "progressive_actions": len(progressive_passes) + len(progressive_carries),
        "carries": len(carries),
        "shots": len(shots),
        "goals": sum(event.shot_outcome == MatchEventShotOutcome.GOAL for event in shots),
        "big_chance_shots": sum(event.is_big_chance for event in shots),
        "take_ons": sum(event.event_type == MatchEventType.TAKE_ON for event in events),
        "final_third_entries": sum(event.is_final_third_entry for event in passes),
        "box_entries": sum(event.is_box_entry for event in passes),
        "key_passes": sum(event.is_key_pass for event in passes),
        "crosses": sum(event.is_cross for event in passes),
        "long_balls": sum(event.is_long_ball for event in passes),
        "defensive_actions": len(defensive),
        "recoveries": sum(event.event_type == MatchEventType.BALL_RECOVERY for event in defensive),
        "tackles": sum(event.event_type == MatchEventType.TACKLE for event in defensive),
        "interceptions": sum(event.event_type == MatchEventType.INTERCEPTION for event in defensive),
        "clearances": sum(event.event_type == MatchEventType.CLEARANCE for event in defensive),
    }


def distance_metres(start_x, start_y, end_x, end_y) -> float | None:
    if None in (start_x, start_y, end_x, end_y):
        return None
    delta_x = (end_x - start_x) * 0.0105
    delta_y = (end_y - start_y) * 0.0068
    return (delta_x ** 2 + delta_y ** 2) ** 0.5


def directional_metrics(events: Iterable, carries: Iterable) -> dict:
    passes = [event for event in events if event.event_type == MatchEventType.PASS]
    pass_lengths = [
        distance_metres(event.x, event.y, event.end_x, event.end_y)
        for event in passes
    ]
    pass_lengths = [value for value in pass_lengths if value is not None]
    pass_forward_metres = [
        (event.end_x - event.x) * 0.0105
        for event in passes
        if event.x is not None and event.end_x is not None
    ]
    carry_rows = list(carries)
    carry_lengths = [
        distance_metres(carry.x, carry.y, carry.end_x, carry.end_y)
        for carry in carry_rows
    ]
    carry_lengths = [value for value in carry_lengths if value is not None]
    carry_forward_metres = [
        (carry.end_x - carry.x) * 0.0105
        for carry in carry_rows
        if carry.x is not None and carry.end_x is not None
    ]
    return {
        "passing": {
            "attempts": len(passes),
            "completed": sum(event.outcome_successful is True for event in passes),
            "completion_rate": percentage(
                sum(event.outcome_successful is True for event in passes),
                len(passes),
            ),
            "progressive": sum(event.is_progressive_pass for event in passes),
            "key_passes": sum(event.is_key_pass for event in passes),
            "final_third_entries": sum(event.is_final_third_entry for event in passes),
            "box_entries": sum(event.is_box_entry for event in passes),
            "crosses": sum(event.is_cross for event in passes),
            "long_balls": sum(event.is_long_ball for event in passes),
            "mean_length_metres": (
                round(sum(pass_lengths) / len(pass_lengths), 2)
                if pass_lengths else None
            ),
            "mean_forward_metres": (
                round(sum(pass_forward_metres) / len(pass_forward_metres), 2)
                if pass_forward_metres else None
            ),
            "forward_share": percentage(
                sum(value > 0 for value in pass_forward_metres),
                len(pass_forward_metres),
            ),
        },
        "carrying": {
            "attempts": len(carry_rows),
            "progressive": sum(carry.is_progressive_carry for carry in carry_rows),
            "final_third_entries": sum(carry.is_final_third_entry for carry in carry_rows),
            "box_entries": sum(carry.is_box_entry for carry in carry_rows),
            "mean_length_metres": (
                round(sum(carry_lengths) / len(carry_lengths), 2)
                if carry_lengths else None
            ),
            "mean_forward_metres": (
                round(sum(carry_forward_metres) / len(carry_forward_metres), 2)
                if carry_forward_metres else None
            ),
            "forward_share": percentage(
                sum(value > 0 for value in carry_forward_metres),
                len(carry_forward_metres),
            ),
        },
    }


def action_context(
    events: Iterable,
    carries: Iterable,
    exposure_seconds: int,
    *,
    include_defensive_families: bool = True,
) -> dict:
    events = list(events)
    carries = list(carries)
    summary = event_summary(events, carries)
    rates = {
        key: metric_rate(value, exposure_seconds)
        for key, value in summary.items()
        if isinstance(value, int)
    }
    defensive_events = [
        event for event in events
        if is_defensive_event(event.event_type, defensive_qualifier=event.is_defensive)
        and event.x is not None
    ]
    defensive_location = average_location(defensive_events)
    heights = [coordinate(event, "x") for event in defensive_events]
    heights = [value for value in heights if value is not None]
    context = {
        "summary": summary,
        "rates": rates,
        "exposure_seconds": exposure_seconds,
        "exposure_minutes": round(exposure_seconds / 60, 2),
        **directional_metrics(events, carries),
        "touch_location": average_location([event for event in events if event.is_touch]),
        "action_location": average_location([
            event for event in events
            if is_action_event(event.event_type, defensive_qualifier=event.is_defensive)
        ]),
        "defensive_location": defensive_location,
        "touch_grid": grid(events, exposure_seconds),
        "defensive_grid": grid(events, exposure_seconds, defensive=True),
        "defensive_height": {
            "sample_size": len(heights),
            "mean": round(sum(heights) / len(heights), 4) if heights else None,
            "median": round(median(heights), 4) if heights else None,
        },
    }
    if include_defensive_families:
        context["defensive_by_family"] = defensive_family_data(events, exposure_seconds)
    return context


def team_relative_shares(player_summary: dict, team_summary: dict) -> dict:
    fields = {
        "touches": ("touches", "touches"),
        "passes": ("pass_attempts", "pass_attempts"),
        "progressive_actions": ("progressive_actions", "progressive_actions"),
        "progressive_carries": ("progressive_carries", "progressive_carries"),
        "shots": ("shots", "shots"),
        "defensive_actions": ("defensive_actions", "defensive_actions"),
    }
    return {
        name: {
            "player_count": player_summary[player_key],
            "team_count": team_summary[team_key],
            "share": percentage(player_summary[player_key], team_summary[team_key]),
            "unit": "share_of_matched_team_actions",
        }
        for name, (player_key, team_key) in fields.items()
    }


def delta_value(selected: float | int | None, baseline: float | int | None) -> float | int | None:
    if selected is None or baseline is None:
        return None
    value = selected - baseline
    return round(value, 4) if isinstance(value, float) else value


def relative_delta(selected: float | int | None, baseline: float | int | None) -> float | None:
    if selected is None or baseline in (None, 0):
        return None
    return round((selected - baseline) / abs(baseline), 4)


def team_matched_context(team_events: list, team_carries: list, segments: list[PlayerExposureSegment], exposure_seconds: int) -> dict:
    team_events = [
        event for event in team_events
        if event.team_id is not None
    ]
    # ``team_events`` already contains one focal-team row for each segment;
    # avoid treating opponent actions as the denominator when a match includes
    # both teams' normalized event stream.
    team_events = [
        event for event in team_events
        if any(segment.match_id == event.provider_match_id and segment.team_id == event.team_id for segment in segments)
    ]
    return action_context(
        team_events,
        team_carries,
        exposure_seconds,
        include_defensive_families=False,
    )


def position_group(profile) -> str:
    outfield = PlayerSeasonDerivedStats.objects.filter(
        competition_season=profile.competition_season,
        canonical_player_id=profile.player_id,
        is_current=True,
    ).values_list("position_group", flat=True).first()
    if outfield:
        return outfield
    if PlayerSeasonGkDerivedStats.objects.filter(
        competition_season=profile.competition_season,
        canonical_player_id=profile.player_id,
        is_current=True,
    ).exists():
        return "GK"
    return "UNK"


def _state_cohort(
    profile,
    scope: StateLensScope,
    match_ids: list[int],
    *,
    team_context_required: bool,
) -> tuple[dict, dict | None, dict]:
    player_events, team_events, carries, team_carries, _events, segments = state_event_rows(
        profile,
        scope,
        match_ids,
    )
    evidence = player_state_evidence(profile, match_ids, scope)
    exposure_seconds = evidence["exposure_seconds"]
    player = action_context(player_events, carries, exposure_seconds)
    team = (
        team_matched_context(team_events, team_carries, segments, exposure_seconds)
        if team_context_required
        else None
    )
    player["team_action_shares"] = (
        team_relative_shares(player["summary"], team["summary"])
        if team is not None
        else {}
    )
    player["possession"] = possession_context(profile, segments, scope)
    return player, team, evidence


def _comparison_payload(
    selected_player: dict,
    selected_team: dict | None,
    baseline_player: dict,
    baseline_team: dict | None,
) -> dict:
    def rate_delta(key: str) -> dict:
        selected = selected_player["rates"].get(key, {}).get("per_90")
        baseline = baseline_player["rates"].get(key, {}).get("per_90")
        return {
            "absolute": delta_value(selected, baseline),
            "relative": relative_delta(selected, baseline),
            "unit": "per_90",
        }

    def location_delta(selected: dict, baseline: dict) -> dict:
        return {
            axis: delta_value(selected["touch_location"][axis], baseline["touch_location"][axis])
            for axis in ("x", "y")
        }

    return {
        "enabled": True,
        "selected_minus_baseline": {
            key: rate_delta(key) for key in selected_player["rates"]
        },
        "movement": {
            "player": location_delta(selected_player, baseline_player),
            "matched_team": (
                location_delta(selected_team, baseline_team)
                if selected_team is not None and baseline_team is not None
                else None
            ),
        },
        "action_share_change": {
            key: delta_value(
                selected_player["team_action_shares"][key]["share"],
                baseline_player["team_action_shares"][key]["share"],
            )
            for key in selected_player["team_action_shares"]
        },
    }


def build_player_state_comparison(profile, lens: StateLens, match_ids: Iterable[int], *, team_context_required: bool = True) -> dict:
    match_ids = list(dict.fromkeys(int(value) for value in match_ids))
    selected_player, selected_team, selected_evidence = _state_cohort(
        profile,
        lens.selected,
        match_ids,
        team_context_required=team_context_required,
    )
    baseline_player = baseline_team = baseline_evidence = None
    if lens.baseline is not None:
        baseline_player, baseline_team, baseline_evidence = _state_cohort(
            profile,
            lens.baseline,
            match_ids,
            team_context_required=team_context_required,
        )
    comparison = (
        _comparison_payload(
            selected_player,
            selected_team,
            baseline_player,
            baseline_team,
        )
        if baseline_player is not None
        else None
    )
    return {
        "contract_version": PLAYER_STATE_COMPARISON_VERSION,
        "canonical_player_id": profile.player_id,
        "canonical_player_name": profile.player.display_name,
        "canonical_team_id": profile.team_id,
        "canonical_team_name": profile.team.name if profile.team else None,
        "position_group": position_group(profile),
        "selected": selected_player | {"evidence": selected_evidence},
        "baseline": baseline_player | {"evidence": baseline_evidence} if baseline_player is not None and baseline_evidence is not None else None,
        "comparison": comparison,
        # Compatibility-only selected-lens evidence. The stable header role is
        # supplied separately by the season-role materialization.
        "response_roles": [],
        "role_formulae": [],
        "team_context": {
            "available": team_context_required,
            "matching": "same team, matches, state cohort, and verified player on-pitch intervals",
            "selected": selected_team,
            "baseline": baseline_team,
        },
        "exclusions": {
            "unverified_player_intervals": True,
            "unverified_team_state": True,
            "timeline_missing_events": True,
            "ambiguous_possessions": True,
        },
    }
