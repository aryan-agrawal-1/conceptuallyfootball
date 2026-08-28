"""Verified player game-state cohorts and matched team evidence.

The player-facing State Lens has a stricter denominator than the team views:
an event is eligible only when it falls inside a verified player interval and
the corresponding verified team state episode.  This module keeps that rule
in one place for the event-profile and comparison APIs.  It intentionally
uses the already-materialized exposure rows; it does not rebuild possession
chains or infer participation from event presence.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import median
from typing import Iterable

from django.db.models import Count, Prefetch

from ingestion.models import (
    MatchEventGameState,
    MatchEventShotOutcome,
    MatchEventType,
    MatchGameStateExclusionReason,
    PlayerSeasonDerivedStats,
    PlayerSeasonGkDerivedStats,
    ProviderMatch,
    ProviderMatchCarry,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchPlayerParticipation,
    ProviderMatchPlayerStateExposure,
    ProviderMatchPossession,
    ProviderMatchPossessionEvent,
    ProviderMatchPossessionParticipant,
    ProviderMatchTeamGameStateEpisode,
    Provider,
)
from ingestion.services.possession_context import POSSESSION_CALCULATION_VERSION
from ingestion.services.defensive_territory import FAMILY_BY_TYPE, defensive_family
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
PLAYER_TRANSITION_EVIDENCE_LIMIT = 25
DEFENSIVE_ACTION_FAMILIES = tuple(dict.fromkeys(FAMILY_BY_TYPE.values()))


@dataclass(frozen=True, slots=True)
class PlayerExposureSegment:
    match_id: int
    team_id: int | None
    start_second: int
    end_second: int
    episode_index: int

    @property
    def duration_seconds(self) -> int:
        return max(0, self.end_second - self.start_second)


def scope_age_bounds(row: ProviderMatchPlayerStateExposure, scope: StateLensScope) -> tuple[int, int] | None:
    """Return the intersection of an exposure row and a State Lens scope."""

    state = STATE_VALUES.get(scope.state)
    if state is not None and row.coarse_state != state:
        return None
    if scope.goal_difference is not None and row.goal_difference != scope.goal_difference:
        return None
    if scope.phase is not None and row.phase != scope.phase:
        return None
    if scope.draw_provenance is not None and row.provenance != scope.draw_provenance:
        return None
    start = row.start_second
    end = row.end_second
    entry = row.team_episode.state_entry_second
    if scope.minimum_state_age_seconds is not None:
        start = max(start, entry + scope.minimum_state_age_seconds)
    if scope.maximum_state_age_seconds is not None:
        end = min(end, entry + scope.maximum_state_age_seconds)
    if end <= start:
        return None
    return start, end


def participation_queryset(profile, match_ids: Iterable[int] | None = None):
    queryset = ProviderMatchPlayerParticipation.objects.filter(
        provider_match__competition_season=profile.competition_season,
        player_id=profile.player_id,
    ).select_related("provider_match", "team")
    if profile.team_id is not None:
        queryset = queryset.filter(team_id=profile.team_id)
    if match_ids is not None:
        queryset = queryset.filter(provider_match_id__in=list(match_ids))
    return queryset


def exposure_queryset(profile, match_ids: Iterable[int] | None = None):
    queryset = ProviderMatchPlayerStateExposure.objects.filter(
        player_interval__participation__provider_match__competition_season=profile.competition_season,
        player_interval__participation__player_id=profile.player_id,
        player_interval__participation__status="verified",
        player_interval__participation__confidence="verified",
        player_interval__confidence="verified",
    ).select_related(
        "player_interval__participation",
        "player_interval__participation__team",
        "team_episode",
    )
    if profile.team_id is not None:
        queryset = queryset.filter(player_interval__participation__team_id=profile.team_id)
    if match_ids is not None:
        queryset = queryset.filter(player_interval__participation__provider_match_id__in=list(match_ids))
    return queryset.order_by(
        "player_interval__participation__provider_match_id",
        "start_second",
        "end_second",
        "id",
    )


def exposure_segments(profile, scope: StateLensScope, match_ids: Iterable[int] | None = None) -> list[PlayerExposureSegment]:
    segments: list[PlayerExposureSegment] = []
    for row in exposure_queryset(profile, match_ids):
        bounds = scope_age_bounds(row, scope)
        if bounds is None:
            continue
        participation = row.player_interval.participation
        segments.append(
            PlayerExposureSegment(
                match_id=participation.provider_match_id,
                team_id=participation.team_id,
                start_second=bounds[0],
                end_second=bounds[1],
                episode_index=row.team_episode.episode_index,
            )
        )
    return segments


def event_second(event) -> int | None:
    # State exposure uses the canonical timeline clock.  Falling back to the
    # provider match clock would silently re-introduce events whose timeline
    # could not be verified, so those events remain excluded.
    return event.timeline_seconds


ANY_TEAM = object()


def value_in_segments(
    value,
    match_id: int,
    segments: Iterable[PlayerExposureSegment],
    team_id: int | None | object = ANY_TEAM,
) -> bool:
    """Check a timestamp against verified segments.

    ``ANY_TEAM`` is intentionally distinct from ``None``.  Player events with
    no canonical team must not pass a player's verified-team denominator, while
    goalkeeper shot-facing evidence may intentionally match either side's
    event stream.
    """

    if value is None:
        return False
    return any(
        segment.match_id == match_id
        and (team_id is ANY_TEAM or segment.team_id == team_id)
        and segment.start_second <= value < segment.end_second
        for segment in segments
    )


def event_in_segments(
    event,
    segments: Iterable[PlayerExposureSegment],
    team_id: int | None | object = ANY_TEAM,
) -> bool:
    return value_in_segments(event_second(event), event.provider_match_id, segments, team_id)


def carry_in_segments(
    carry,
    segments: Iterable[PlayerExposureSegment],
    team_id: int | None | object = ANY_TEAM,
) -> bool:
    # Carries are derived from normalized on-ball events and retain the
    # canonical match clock even though they do not carry a timeline field.
    return value_in_segments(carry.match_seconds, carry.provider_match_id, segments, team_id)


def verified_event_ids(queryset, profile, scope: StateLensScope, match_ids: Iterable[int] | None = None) -> list[int]:
    segments = exposure_segments(profile, scope, match_ids)
    if not segments:
        return []
    events = list(queryset)
    return [
        event.id
        for event in events
        if event_in_segments(event, segments, event.team_id)
    ]


def scope_player_events(queryset, profile, scope: StateLensScope, match_ids: Iterable[int] | None = None):
    """Return only player events supported by verified exposure for ``scope``."""

    ids = verified_event_ids(queryset, profile, scope, match_ids)
    if not ids:
        return queryset.none()
    return queryset.filter(pk__in=ids)


def player_event_scope_segments(profile, scope: StateLensScope, match_ids: Iterable[int] | None = None):
    return exposure_segments(profile, scope, match_ids)


def scope_player_carries(carries: Iterable, profile, scope: StateLensScope, match_ids: Iterable[int] | None = None) -> list:
    segments = exposure_segments(profile, scope, match_ids)
    return [
        carry
        for carry in carries
        if carry_in_segments(carry, segments, carry.team_id)
    ]


def scope_match_ids(profile, match_ref: int | None = None) -> tuple[list[int], dict[int, int]]:
    """Resolve match references from the player's full event universe."""

    match_ids = list(
        ProviderMatchEvent.objects.filter(
            provider_match__competition_season=profile.competition_season,
            player_id=profile.player_id,
            **({"team_id": profile.team_id} if profile.team_id is not None else {}),
        ).values_list("provider_match_id", flat=True).distinct()
    )
    matches = list(
        ProviderMatch.objects.filter(pk__in=match_ids).order_by("kickoff_at", "id")
    )
    references = {match.id: index for index, match in enumerate(matches)}
    selected = [
        match.id for match in matches
        if match_ref is None or references[match.id] == match_ref
    ]
    return selected, references


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


def _transition_scope_matches(context: dict, scope: StateLensScope) -> bool:
    """Match a #117 observation to the already-selected player State Lens."""

    if scope.state != "all" and context.get("state") != scope.state:
        return False
    if scope.goal_difference is not None and context.get("goal_difference") != scope.goal_difference:
        return False
    if scope.phase is not None and context.get("phase") != scope.phase:
        return False
    if scope.draw_provenance is not None and context.get("draw_provenance") != scope.draw_provenance:
        return False
    age = context.get("state_age_seconds")
    if scope.minimum_state_age_seconds is not None and (
        age is None or age < scope.minimum_state_age_seconds
    ):
        return False
    if scope.maximum_state_age_seconds is not None and (
        age is None or age >= scope.maximum_state_age_seconds
    ):
        return False
    return True


def _transition_player_evidence(
    profile,
    segments: list[PlayerExposureSegment],
    scope: StateLensScope,
) -> dict:
    """Project the #117 sequence contract onto verified player exposure.

    ``possession_observation`` is the shared transition-leverage formatter. It
    keeps outcome/state/sequence semantics identical to the team surface while
    this function supplies the player-specific denominator: a player event
    must be linked to the possession, have a verified timeline timestamp, and
    fall inside the player's selected team interval.
    """

    from ingestion.services.transition_leverage import (
        TRANSITION_LEVERAGE_API_VERSION,
        TRANSITION_LEVERAGE_FORMULA_VERSION,
        possession_observation,
    )

    empty_stages = {
        key: {
            "actions": 0,
            "possessions": 0,
            "rate_per_opportunity": None,
        }
        for key in (
            "origin_recovery",
            "escape",
            "advancement",
            "destabilisation",
            "creation",
            "contest",
            "terminal",
            "support",
        )
    }
    empty = {
        "available": False,
        "verified": True,
        "contract_version": TRANSITION_LEVERAGE_API_VERSION,
        "formula_version": TRANSITION_LEVERAGE_FORMULA_VERSION,
        "opportunities": 0,
        "involved_possessions": 0,
        "counter_possessions": 0,
        "shot_producing_possessions": 0,
        "box_entry_possessions": 0,
        "final_third_possessions": 0,
        "big_chance_possessions": 0,
        "goal_possessions": 0,
        "state_changing_possessions": 0,
        "sequence_stages": empty_stages,
        "sequence_evidence": [],
        "evidence_truncated": False,
        "ambiguous_excluded": 0,
        "exclusions": {
            "ambiguous_possessions": 0,
            "outside_verified_player_interval": 0,
            "state_or_team_mismatch": 0,
        },
        "matching": {
            "same_matches": True,
            "same_team": True,
            "same_state_cohort": True,
            "verified_player_on_pitch_intervals": True,
            "timeline": "half_open_played_seconds",
        },
    }
    match_ids = {segment.match_id for segment in segments}
    team_ids = {segment.team_id for segment in segments if segment.team_id is not None}
    if not match_ids or not team_ids:
        return empty

    matches = list(
        ProviderMatch.objects.filter(
            pk__in=match_ids,
            provider=Provider.WHOSCORED,
        )
        .select_related("home_team", "away_team")
        .order_by("kickoff_at", "id")
    )
    match_by_id = {match.id: match for match in matches}
    match_refs = {match.id: index for index, match in enumerate(matches)}
    episode_rows = ProviderMatchTeamGameStateEpisode.objects.filter(
        provider_match_id__in=match_ids,
        focal_team_id__in=team_ids,
    ).order_by("provider_match_id", "focal_team_id", "episode_index")
    episodes_by_match_team: dict[tuple[int, int], list] = {}
    for episode in episode_rows:
        episodes_by_match_team.setdefault(
            (int(episode.provider_match_id), int(episode.focal_team_id)), []
        ).append(episode)

    link_queryset = ProviderMatchPossessionEvent.objects.select_related(
        "event", "event__player", "event__team"
    ).order_by("sequence")
    possessions = list(
        ProviderMatchPossession.objects.filter(
            provider_match_id__in=match_ids,
            team_id__in=team_ids,
            build__calculation_version=POSSESSION_CALCULATION_VERSION,
        )
        .distinct()
        .select_related("provider_match", "team", "build")
        .prefetch_related(
            Prefetch("event_links", queryset=link_queryset),
            Prefetch(
                "participants",
                queryset=ProviderMatchPossessionParticipant.objects.filter(
                    player_id=profile.player_id
                ),
                to_attr="player_participants",
            ),
        )
        .order_by("provider_match_id", "possession_index")
    )
    candidate_possessions = [
        possession
        for possession in possessions
        if getattr(possession, "player_participants", ())
    ]
    candidate_count = len(candidate_possessions)
    ambiguous_count = sum(possession.is_ambiguous for possession in candidate_possessions)
    stages = {
        key: value.copy() for key, value in empty_stages.items()
    }
    observations: list[dict] = []
    outside_interval_count = 0
    state_or_team_mismatch_count = 0
    opportunities = 0
    for possession in possessions:
        if possession.is_ambiguous:
            continue
        match = match_by_id.get(int(possession.provider_match_id))
        team_id = getattr(possession, "team_id", None)
        if match is None or team_id is None:
            state_or_team_mismatch_count += 1
            continue
        matching_segments = [
            segment
            for segment in segments
            if segment.match_id == possession.provider_match_id
            and segment.team_id == team_id
        ]
        if not matching_segments:
            if getattr(possession, "player_participants", ()):
                state_or_team_mismatch_count += 1
            continue
        links = list(possession.event_links.all())
        links.sort(key=lambda link: (int(link.sequence), int(link.event.event_index)))
        team_sequences = [
            sequence
            for sequence, link in enumerate(links)
            if link.event.team_id == team_id
            and event_in_segments(link.event, matching_segments, link.event.team_id)
        ]
        focal_team = getattr(possession, "team", None)
        if focal_team is None:
            focal_team = (
                match.home_team
                if match.home_team_id == team_id
                else match.away_team
                if match.away_team_id == team_id
                else None
            )
        if focal_team is None:
            if getattr(possession, "player_participants", ()):
                state_or_team_mismatch_count += 1
            continue
        opportunity_observation = None
        if team_sequences:
            opportunity_observation = possession_observation(
                possession,
                match=match,
                focal_team=focal_team,
                match_ref=match_refs.get(match.id, 0),
                episodes=episodes_by_match_team.get((match.id, int(team_id)), ()),
            )
            if _transition_scope_matches(opportunity_observation["state"], scope):
                opportunities += 1
        verified_player_sequences = [
            sequence
            for sequence, link in enumerate(links)
            if link.event.player_id == profile.player_id
            and link.event.team_id == team_id
            and event_in_segments(link.event, matching_segments, link.event.team_id)
        ]
        if not verified_player_sequences:
            if getattr(possession, "player_participants", ()):
                outside_interval_count += 1
            continue
        observation = opportunity_observation or possession_observation(
            possession,
            match=match,
            focal_team=focal_team,
            match_ref=match_refs.get(match.id, 0),
            episodes=episodes_by_match_team.get((match.id, int(team_id)), ()),
        )
        if not _transition_scope_matches(observation["state"], scope):
            state_or_team_mismatch_count += 1
            continue
        # #117 deliberately exposes the richer rapid-transition outcome but
        # keeps the materialized #112 arrival flags as the source of truth for
        # the legacy player counters.  Retain those flags internally while
        # exposing the inspectable sequence below.
        observation["_counter_evidence"] = {
            "final_third_arrival": bool(getattr(possession, "counter_final_third_arrival", False)),
            "box_arrival": bool(getattr(possession, "counter_box_arrival", False)),
            "shot": bool(getattr(possession, "counter_shot", False)),
        }
        observation["verified_player_action_sequences"] = verified_player_sequences
        observation["verified_player_action_event_indexes"] = [
            links[sequence].event.event_index for sequence in verified_player_sequences
        ]
        observations.append(observation)

    role_possession_ids: dict[str, set[str]] = defaultdict(set)
    for observation in observations:
        for sequence in observation["verified_player_action_sequences"]:
            action = observation["possession_trace"][sequence]
            role = action["role"]
            stages[role]["actions"] += 1
            role_possession_ids[role].add(observation["possession_id"])
        is_counter = observation["rapid_transition"]["is_counter_launch"]
        if is_counter:
            empty["counter_possessions"] += 1
            outcome = observation["rapid_transition"].get("outcome")
            direction_ladder = observation["direction_ladder"]
            counter_evidence = observation["_counter_evidence"]
            if (
                counter_evidence["shot"]
                or direction_ladder.get("shot")
                or outcome in {"saved", "goal", "missed", "blocked", "woodwork"}
            ):
                empty["shot_producing_possessions"] += 1
            if counter_evidence["box_arrival"] or direction_ladder.get("box_entry") or outcome == "box_arrival":
                empty["box_entry_possessions"] += 1
            if (
                counter_evidence["final_third_arrival"]
                or direction_ladder.get("territorial_entry")
                or outcome == "final_third_arrival"
            ):
                empty["final_third_possessions"] += 1
        if observation["direction_ladder"].get("big_chance"):
            empty["big_chance_possessions"] += 1
        if observation["score"]["perspective"] == "for":
            empty["goal_possessions"] += 1
        if observation["state_transition"]["actual"]:
            empty["state_changing_possessions"] += 1

    involved = len(observations)
    for role, possession_ids in role_possession_ids.items():
        stages[role]["possessions"] = len(possession_ids)
        stages[role]["rate_per_opportunity"] = (
            round(len(possession_ids) / opportunities, 4) if opportunities else None
        )
    sequence_evidence = []
    for observation in observations[:PLAYER_TRANSITION_EVIDENCE_LIMIT]:
        sequence_evidence.append({
            "match_ref": observation["match_ref"],
            "possession_id": observation["possession_id"],
            "team_id": observation["team_id"],
            "state": observation["state"],
            "state_transition": observation["state_transition"],
            "outcome_tier": observation["outcome_tier"],
            "rapid_transition": observation["rapid_transition"],
            "action_stages": sorted({
                observation["possession_trace"][sequence]["stage"]
                for sequence in observation["verified_player_action_sequences"]
            }),
            "action_event_indexes": observation["verified_player_action_event_indexes"],
            "verified_player_action_sequences": observation["verified_player_action_sequences"],
            "possession_trace": observation["possession_trace"],
        })
    empty.update({
        "available": candidate_count > 0,
        "opportunities": opportunities,
        "involved_possessions": involved,
        "sequence_stages": stages,
        "sequence_evidence": sequence_evidence,
        "evidence_truncated": len(observations) > PLAYER_TRANSITION_EVIDENCE_LIMIT,
        "ambiguous_excluded": ambiguous_count,
        "exclusions": {
            "ambiguous_possessions": ambiguous_count,
            "outside_verified_player_interval": outside_interval_count,
            "state_or_team_mismatch": state_or_team_mismatch_count,
        },
    })
    return empty


def possession_context(
    profile,
    segments: list[PlayerExposureSegment],
    scope: StateLensScope = StateLensScope(),
) -> dict:
    """Return legacy counters plus the inspectable #117 player projection."""

    transition = _transition_player_evidence(profile, segments, scope)
    return {
        "available": transition["available"],
        "verified": transition["verified"],
        "involved_possessions": transition["involved_possessions"],
        "counter_possessions": transition["counter_possessions"],
        "shot_producing_possessions": transition["shot_producing_possessions"],
        "box_entry_possessions": transition["box_entry_possessions"],
        "final_third_possessions": transition["final_third_possessions"],
        "ambiguous_excluded": transition["ambiguous_excluded"],
        "big_chance_possessions": transition["big_chance_possessions"],
        "goal_possessions": transition["goal_possessions"],
        "state_changing_possessions": transition["state_changing_possessions"],
        "transition_leverage": transition,
    }


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




def build_player_state_comparison(profile, lens: StateLens, match_ids: Iterable[int], *, team_context_required: bool = True) -> dict:
    match_ids = list(dict.fromkeys(int(value) for value in match_ids))
    selected_player_events, selected_team_events, selected_carries, selected_team_carries, _events, selected_segments = state_event_rows(profile, lens.selected, match_ids)
    selected_evidence = player_state_evidence(profile, match_ids, lens.selected)
    selected_player = action_context(selected_player_events, selected_carries, selected_evidence["exposure_seconds"])
    selected_team = (
        team_matched_context(
            selected_team_events,
            selected_team_carries,
            selected_segments,
            selected_evidence["exposure_seconds"],
        )
        if team_context_required
        else None
    )
    selected_player["team_action_shares"] = (
        team_relative_shares(selected_player["summary"], selected_team["summary"])
        if selected_team is not None
        else {}
    )
    selected_player["possession"] = possession_context(
        profile,
        selected_segments,
        lens.selected,
    )
    baseline_player = baseline_team = baseline_evidence = None
    baseline_segments: list[PlayerExposureSegment] = []
    if lens.baseline is not None:
        baseline_player_events, baseline_team_events, baseline_carries, baseline_team_carries, _baseline_events, baseline_segments = state_event_rows(profile, lens.baseline, match_ids)
        baseline_evidence = player_state_evidence(profile, match_ids, lens.baseline)
        baseline_player = action_context(baseline_player_events, baseline_carries, baseline_evidence["exposure_seconds"])
        baseline_team = (
            team_matched_context(
                baseline_team_events,
                baseline_team_carries,
                baseline_segments,
                baseline_evidence["exposure_seconds"],
            )
            if team_context_required
            else None
        )
        baseline_player["team_action_shares"] = (
            team_relative_shares(baseline_player["summary"], baseline_team["summary"])
            if baseline_team is not None
            else {}
        )
        baseline_player["possession"] = possession_context(
            profile,
            baseline_segments,
            lens.baseline,
        )
    comparison = None
    roles = []
    if baseline_player is not None and baseline_evidence is not None:
        comparison = {
            "enabled": True,
            "selected_minus_baseline": {
                key: {
                    "absolute": delta_value(selected_player["rates"].get(key, {}).get("per_90"), baseline_player["rates"].get(key, {}).get("per_90")),
                    "relative": relative_delta(selected_player["rates"].get(key, {}).get("per_90"), baseline_player["rates"].get(key, {}).get("per_90")),
                    "unit": "per_90",
                }
                for key in selected_player["rates"]
            },
            "movement": {
                "player": {
                    "x": delta_value(selected_player["touch_location"]["x"], baseline_player["touch_location"]["x"]),
                    "y": delta_value(selected_player["touch_location"]["y"], baseline_player["touch_location"]["y"]),
                },
                "matched_team": (
                    {
                        "x": delta_value(
                            selected_team["touch_location"]["x"],
                            baseline_team["touch_location"]["x"],
                        ),
                        "y": delta_value(
                            selected_team["touch_location"]["y"],
                            baseline_team["touch_location"]["y"],
                        ),
                    }
                    if selected_team is not None and baseline_team is not None
                    else None
                ),
            },
            "action_share_change": (
                {
                    key: delta_value(
                        selected_player["team_action_shares"][key]["share"],
                        baseline_player["team_action_shares"][key]["share"],
                    )
                    for key in selected_player["team_action_shares"]
                }
                if team_context_required
                else {}
            ),
        }
        # The unpublished response-role experiment mixed state comparisons
        # with season archetypes. Stable identity now comes exclusively from
        # the player-team-season role materialization.
        roles = []
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
        "response_roles": roles,
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
