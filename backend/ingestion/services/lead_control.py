"""Inspectable Lead Gravity and Lead Ownership evidence.

Lead Gravity and Lead Ownership deliberately answer different questions:

* Gravity describes the focal team's observed change after it takes a lead.
* Ownership describes the process evidence available while that lead is held.

The service only consumes normalized WhoScored events, the verified focal-team
game-state episodes, and the persisted possession context.  It never uses a
match result as a proxy for control and it does not make causal or opponent-
strength claims.  A lead window is compared with a clock-matched drawing
window (goal difference zero, same phase, and the same 15-minute clock bucket
or a bucket within the documented tolerance).  Unmatched drawing time is not
silently added to the denominator.

The public builder is intentionally independent of Django query construction;
the API adapter supplies already-resolved rows and this module turns them into
small, decomposable component dictionaries.  That makes the matching rules
and sparse-data behaviour straightforward to test without a database.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from statistics import mean, median
from typing import Any, Iterable, Mapping, Sequence

from ingestion.models import (
    MatchEventGameState,
    MatchEventShotOutcome,
    MatchEventType,
    MatchStatePhase,
)
from ingestion.services.defensive_territory import defensive_family
from ingestion.services.possession_context import (
    BOX_X,
    FINAL_THIRD_X,
    POSSESSION_CALCULATION_VERSION,
)
from ingestion.services.pass_state import direction as pass_direction
from ingestion.services.pass_state import physical_vector
from ingestion.state_lens import StateLens, StateLensScope


LEAD_CONTROL_FORMULA_VERSION = "lead_control_v1"
LEAD_CONTROL_API_VERSION = "lead_control_api_v1"
CLOCK_BUCKET_SECONDS = 15 * 60
CLOCK_MATCH_TOLERANCE_SECONDS = CLOCK_BUCKET_SECONDS
MIN_LEAD_EPISODES = 3
MIN_LEAD_EXPOSURE_SECONDS = 15 * 60
MIN_COMPONENT_EVENTS = 5
EPISODE_EVIDENCE_LIMIT = 100
AXIS_SCALES = {
    "height_pitch_points": 15.0,
    "pass_forward_share": 0.25,
    "rate_per_90": 2.0,
    "opponent_big_chances_per_90": 1.0,
    "first_attack_seconds": 300.0,
}

LEAD_BAND_ONE_GOAL = "one_goal"
LEAD_BAND_MULTI_GOAL = "multi_goal"
LEAD_BANDS = (LEAD_BAND_ONE_GOAL, LEAD_BAND_MULTI_GOAL)

PHASE_LABELS = {
    MatchStatePhase.FIRST_HALF: "first_half",
    MatchStatePhase.SECOND_HALF: "second_half",
    MatchStatePhase.FIRST_EXTRA_TIME: "first_extra_time",
    MatchStatePhase.SECOND_EXTRA_TIME: "second_extra_time",
}

CONTROL_TYPES = frozenset(
    {
        MatchEventType.PASS,
        MatchEventType.BALL_TOUCH,
        MatchEventType.TAKE_ON,
        MatchEventType.SHOT,
        MatchEventType.BALL_RECOVERY,
        MatchEventType.TACKLE,
        MatchEventType.INTERCEPTION,
        MatchEventType.CLEARANCE,
        MatchEventType.BLOCKED_PASS,
        MatchEventType.AERIAL,
        MatchEventType.CHALLENGE,
    }
)


@dataclass(frozen=True, slots=True)
class LeadWindow:
    """A clock-bucket slice of one lead or matched baseline episode."""

    match_id: int
    episode_index: int
    phase: str
    goal_difference: int
    lead_band: str
    start_second: int
    end_second: int
    state_entry_second: int
    clock_bucket: int
    entry_event_index: int | None = None
    source: str = "lead"
    matched_lead_key: tuple[int, int] | None = None

    @property
    def key(self) -> tuple[int, int, int, str]:
        return self.match_id, self.episode_index, self.clock_bucket, self.source

    @property
    def episode_key(self) -> tuple[int, int]:
        return self.match_id, self.episode_index


def _int(value: Any, default: int | None = None) -> int | None:
    try:
        return default if value is None else int(value)
    except (TypeError, ValueError):
        return default


def _state_name(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        normalized = value.strip().lower().replace(" ", "_")
        if normalized in {"drawing", "winning", "losing"}:
            return normalized
    state = _int(value)
    return {
        MatchEventGameState.DRAWING: "drawing",
        MatchEventGameState.WINNING: "winning",
        MatchEventGameState.LOSING: "losing",
    }.get(state)


def _phase_name(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower().replace(" ", "_")
        if normalized in set(PHASE_LABELS.values()):
            return normalized
    numeric = _int(value)
    return {
        1: "first_half",
        2: "second_half",
        3: "first_extra_time",
        4: "second_extra_time",
    }.get(numeric)


def lead_band(goal_difference: Any) -> str | None:
    """Return the public one-goal/multi-goal lead band."""

    difference = _int(goal_difference)
    if difference == 1:
        return LEAD_BAND_ONE_GOAL
    if difference is not None and difference >= 2:
        return LEAD_BAND_MULTI_GOAL
    return None


def _object_id(row: Any, fallback: int = 0) -> int:
    value = getattr(row, "pk", None)
    if value is None:
        value = getattr(row, "id", None)
    return _int(value, fallback) or fallback


def _episode_index(row: Any, fallback: int = 0) -> int:
    return _int(getattr(row, "episode_index", None), fallback) or fallback


def _episode_key(row: Any, fallback: int = 0) -> tuple[int, int]:
    return _object_id(getattr(row, "provider_match", None), _int(getattr(row, "provider_match_id", None), fallback) or fallback), _episode_index(row, fallback)


def _scope_matches_episode(episode: Any, scope: StateLensScope | None) -> bool:
    if scope is None:
        return True
    state = _state_name(getattr(episode, "state", None))
    if scope.state != "all" and state != scope.state:
        return False
    goal_difference = _int(getattr(episode, "goal_difference", None))
    if scope.goal_difference is not None and goal_difference != scope.goal_difference:
        return False
    phase = _phase_name(getattr(episode, "phase", None))
    if scope.phase is not None and phase != scope.phase:
        return False
    if scope.draw_provenance is not None:
        provenance = str(getattr(episode, "draw_provenance", "") or "").lower()
        if provenance != scope.draw_provenance:
            return False
    age_at_start = _int(getattr(episode, "state_age_seconds_at_start", None), 0) or 0
    duration = _int(getattr(episode, "duration_seconds", None), 0) or 0
    if scope.maximum_state_age_seconds is not None and age_at_start >= scope.maximum_state_age_seconds:
        return False
    if scope.minimum_state_age_seconds is not None and age_at_start + duration <= scope.minimum_state_age_seconds:
        return False
    return True


def _episode_window(episode: Any, scope: StateLensScope | None, *, source: str = "lead", matched_lead_key: tuple[int, int] | None = None) -> tuple[int, int] | None:
    start = _int(getattr(episode, "start_second", None))
    end = _int(getattr(episode, "end_second", None))
    state_entry = _int(getattr(episode, "state_entry_second", None), start or 0) or 0
    if start is None or end is None:
        return None
    start = max(start, state_entry + ((scope.minimum_state_age_seconds or 0) if scope else 0))
    if scope and scope.maximum_state_age_seconds is not None:
        end = min(end, state_entry + scope.maximum_state_age_seconds)
    if end <= start:
        return None
    return start, end


def _clock_bucket(second: int) -> int:
    return max(0, int(second)) // CLOCK_BUCKET_SECONDS


def _episode_to_windows(episode: Any, scope: StateLensScope | None, *, source: str = "lead", matched_lead_key: tuple[int, int] | None = None) -> list[LeadWindow]:
    if not _scope_matches_episode(episode, scope):
        return []
    window = _episode_window(episode, scope, source=source, matched_lead_key=matched_lead_key)
    if window is None:
        return []
    match_id, episode_index = _episode_key(episode)
    phase = _phase_name(getattr(episode, "phase", None)) or "unknown"
    difference = _int(getattr(episode, "goal_difference", None), 0) or 0
    band = lead_band(difference) or "drawing"
    state_entry = _int(getattr(episode, "state_entry_second", None), window[0]) or window[0]
    entry_event_index = _int(getattr(episode, "entry_event_index", None))
    first_bucket, last_bucket = _clock_bucket(window[0]), _clock_bucket(window[1] - 1)
    return [
        LeadWindow(
            match_id=match_id,
            episode_index=episode_index,
            phase=phase,
            goal_difference=difference,
            lead_band=band,
            start_second=max(window[0], bucket * CLOCK_BUCKET_SECONDS),
            end_second=min(window[1], (bucket + 1) * CLOCK_BUCKET_SECONDS),
            state_entry_second=state_entry,
            clock_bucket=bucket,
            entry_event_index=entry_event_index,
            source=source,
            matched_lead_key=matched_lead_key,
        )
        for bucket in range(first_bucket, last_bucket + 1)
        if min(window[1], (bucket + 1) * CLOCK_BUCKET_SECONDS) > max(window[0], bucket * CLOCK_BUCKET_SECONDS)
    ]


def build_lead_windows(episodes: Iterable[Any], scope: StateLensScope | None = None) -> list[LeadWindow]:
    """Build winning episode slices after applying the selected State Lens."""

    windows: list[LeadWindow] = []
    for episode in episodes:
        if _state_name(getattr(episode, "state", None)) != "winning":
            continue
        windows.extend(_episode_to_windows(episode, scope))
    return windows


def _clock_distance(first: LeadWindow, second: Any) -> int:
    start = _int(getattr(second, "start_second", None), 0) or 0
    end = _int(getattr(second, "end_second", None), start) or start
    midpoint = (start + end) / 2
    target_midpoint = (first.start_second + first.end_second) / 2
    return abs(int(midpoint - target_midpoint))


def build_matched_baseline_windows(
    lead_windows: Sequence[LeadWindow],
    episodes: Iterable[Any],
    baseline_scope: StateLensScope | None = None,
) -> list[LeadWindow]:
    """Match drawing windows by phase and clock, never by season-wide totals.

    Drawing episodes are clipped to their own 15-minute clock bucket.  A
    candidate can be at most one bucket (15 minutes) from the lead slice's
    midpoint.  If no candidate exists, no baseline denominator is emitted for
    that lead slice.  Goal difference zero is forced even when a caller passes
    a broad State Lens baseline, because it is the explicit control state.
    """

    candidates = []
    for episode in episodes:
        if _state_name(getattr(episode, "state", None)) != "drawing":
            continue
        if (_int(getattr(episode, "goal_difference", None), 0) or 0) != 0:
            continue
        if baseline_scope and not _scope_matches_episode(episode, baseline_scope):
            continue
        candidate_windows = _episode_to_windows(
            episode,
            baseline_scope,
            source="baseline",
        )
        candidates.extend(candidate_windows)

    matched: list[LeadWindow] = []
    seen: set[tuple[int, int, int, int, int, tuple[int, int]]] = set()
    for lead in lead_windows:
        for candidate in candidates:
            if candidate.phase != lead.phase:
                continue
            if abs(candidate.clock_bucket - lead.clock_bucket) > 1:
                continue
            if _clock_distance(lead, candidate) > CLOCK_MATCH_TOLERANCE_SECONDS:
                continue
            # Keep the candidate's actual timeline.  Only its bucket and phase
            # are matched; moving event seconds to the lead clock would invent
            # observations that were not recorded.
            key = (
                candidate.match_id,
                candidate.episode_index,
                candidate.start_second,
                candidate.end_second,
                candidate.clock_bucket,
                lead.episode_key,
            )
            if key in seen:
                continue
            seen.add(key)
            matched.append(
                LeadWindow(
                    match_id=candidate.match_id,
                    episode_index=candidate.episode_index,
                    phase=candidate.phase,
                    goal_difference=0,
                    lead_band="drawing",
                    start_second=candidate.start_second,
                    end_second=candidate.end_second,
                    state_entry_second=candidate.state_entry_second,
                    clock_bucket=candidate.clock_bucket,
                    entry_event_index=candidate.entry_event_index,
                    source="baseline",
                    matched_lead_key=lead.episode_key,
                )
            )
    return matched


def _event_second(event: Any) -> int | None:
    return _int(getattr(event, "timeline_seconds", None), _int(getattr(event, "match_seconds", None)))


def _event_match_id(event: Any) -> int:
    provider_match = getattr(event, "provider_match", None)
    return _int(getattr(event, "provider_match_id", None), _object_id(provider_match)) or 0


def _event_id(event: Any) -> tuple[int, int]:
    return _event_match_id(event), _int(getattr(event, "event_index", None), _object_id(event)) or 0


def _possession_match_id(possession: Any) -> int:
    return _int(getattr(possession, "provider_match_id", None), _object_id(getattr(possession, "provider_match", None))) or 0


def _event_in_windows(event: Any, windows: Sequence[LeadWindow]) -> LeadWindow | None:
    second = _event_second(event)
    if second is None:
        return None
    match_id = _event_match_id(event)
    for window in windows:
        if window.match_id == match_id and window.start_second <= second < window.end_second:
            return window
    return None


def _possession_in_windows(possession: Any, windows: Sequence[LeadWindow]) -> LeadWindow | None:
    second = _int(getattr(possession, "start_second", None))
    if second is None:
        return None
    match_id = _possession_match_id(possession)
    for window in windows:
        if window.match_id == match_id and window.start_second <= second < window.end_second:
            return window
    return None


def _is_deleted(event: Any) -> bool:
    return bool(getattr(event, "is_deleted_event", False))


def _is_focal_event(event: Any, focal_team_id: int, focal_provider_by_match: Mapping[int, str]) -> bool:
    team_id = _int(getattr(event, "team_id", None))
    if team_id is not None:
        return team_id == int(focal_team_id)
    provider = focal_provider_by_match.get(_event_match_id(event))
    return provider is not None and str(getattr(event, "provider_team_id", "")) == str(provider)


def _located_x(event: Any) -> int | None:
    return _int(getattr(event, "x", None))


def _located_passes(events: Sequence[Any]) -> list[Any]:
    return [
        event
        for event in events
        if _int(getattr(event, "event_type", None)) == MatchEventType.PASS
        and None not in (
            _int(getattr(event, "x", None)),
            _int(getattr(event, "y", None)),
            _int(getattr(event, "end_x", None)),
            _int(getattr(event, "end_y", None)),
        )
    ]


def _height_metric(
    values: Sequence[int],
    exposure_seconds: int,
    *,
    key: str,
    label: str,
) -> dict[str, Any]:
    values = [int(value) for value in values if value is not None]
    value = round(mean(values) / 100, 3) if values else None
    return {
        "key": key,
        "label": label,
        "kind": "height",
        "value": value,
        "count": len(values),
        "sample_size": len(values),
        "unit": "pitch percentage",
        "exposure_seconds": int(exposure_seconds),
        "per_state_minute": None,
        "per_90": None,
        "raw": {"sum_x": sum(values), "located_count": len(values)},
    }


def _rate_metric(
    count: int,
    exposure_seconds: int,
    *,
    key: str,
    label: str,
    unit: str = "events per 90 lead minutes",
    denominator: int | None = None,
    raw: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    per_minute = round(count * 60 / exposure_seconds, 4) if exposure_seconds else None
    per_90 = round(count * 5400 / exposure_seconds, 4) if exposure_seconds else None
    return {
        "key": key,
        "label": label,
        "kind": "rate",
        "value": per_90,
        "count": int(count),
        "sample_size": int(denominator if denominator is not None else count),
        "unit": unit,
        "exposure_seconds": int(exposure_seconds),
        "per_state_minute": per_minute,
        "per_90": per_90,
        "raw": {"count": int(count), **dict(raw or {})},
    }


def _share_metric(
    count: int,
    denominator: int,
    exposure_seconds: int,
    *,
    key: str,
    label: str,
    unit: str = "share of located attempts",
    raw: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    share = round(count / denominator, 4) if denominator else None
    return {
        "key": key,
        "label": label,
        "kind": "share",
        "value": share,
        "count": int(count),
        "sample_size": int(denominator),
        "denominator": int(denominator),
        "unit": unit,
        "exposure_seconds": int(exposure_seconds),
        "per_state_minute": round(count * 60 / exposure_seconds, 4) if exposure_seconds else None,
        "per_90": round(count * 5400 / exposure_seconds, 4) if exposure_seconds else None,
        "raw": {"count": int(count), "denominator": int(denominator), **dict(raw or {})},
    }


def _time_metric(
    seconds: Sequence[int],
    total_episode_count: int,
    exposure_seconds: int,
    *,
    key: str,
    label: str,
) -> dict[str, Any]:
    values = sorted(int(value) for value in seconds if value is not None)
    return {
        "key": key,
        "label": label,
        "kind": "time",
        "value": round(median(values), 1) if values else None,
        "mean": round(mean(values), 1) if values else None,
        "count": len(values),
        "sample_size": len(values),
        "episodes_with_attack": len(values),
        "episodes_without_attack": max(0, total_episode_count - len(values)),
        "unit": "seconds from lead entry",
        "exposure_seconds": int(exposure_seconds),
        "per_state_minute": None,
        "per_90": None,
        "raw": {
            "values_seconds": values,
            "minimum_seconds": min(values) if values else None,
            "maximum_seconds": max(values) if values else None,
        },
    }


def _unique_windows(windows: Sequence[LeadWindow]) -> list[LeadWindow]:
    seen: set[tuple[Any, ...]] = set()
    result = []
    for window in windows:
        key = (
            window.source,
            window.match_id,
            window.episode_index,
            window.start_second,
            window.end_second,
            window.matched_lead_key,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(window)
    return result


def _first_meaningful_attacks(
    events: Sequence[Any],
    windows: Sequence[LeadWindow],
    *,
    focal_team_id: int,
    focal_provider_by_match: Mapping[int, str],
) -> dict[tuple[int, int], int]:
    first: dict[tuple[int, int], int] = {}
    for event in events:
        if _is_deleted(event) or _is_focal_event(event, focal_team_id, focal_provider_by_match):
            continue
        if not (
            bool(getattr(event, "is_box_entry", False))
            or _int(getattr(event, "event_type", None)) == MatchEventType.SHOT
            or bool(getattr(event, "is_big_chance", False))
        ):
            continue
        window = _event_in_windows(event, windows)
        if window is None:
            continue
        second = _event_second(event)
        if second is None:
            continue
        elapsed = max(0, second - window.state_entry_second)
        key = window.episode_key
        first[key] = min(first.get(key, elapsed), elapsed)
    return first


def _raw_cohort(
    events: Iterable[Any],
    possessions: Iterable[Any],
    windows: Sequence[LeadWindow],
    *,
    focal_team_id: int,
    focal_provider_by_match: Mapping[int, str] | None = None,
) -> dict[str, Any]:
    windows = _unique_windows(windows)
    focal_provider_by_match = focal_provider_by_match or {}
    selected_event_rows: list[Any] = []
    seen_events: set[tuple[int, int]] = set()
    for event in events:
        if _is_deleted(event):
            continue
        window = _event_in_windows(event, windows)
        if window is None:
            continue
        event_id = _event_id(event)
        if event_id in seen_events:
            continue
        # The score-changing event belongs to the boundary, not the observed
        # behaviour after the lead.  State episodes are half-open, but keeping
        # this guard also makes the rule explicit for hand-built fixtures.
        if window.source == "lead" and window.entry_event_index is not None and _int(getattr(event, "event_index", None)) == window.entry_event_index:
            continue
        seen_events.add(event_id)
        selected_event_rows.append(event)

    selected_possessions: list[Any] = []
    seen_possessions: set[tuple[int, int, int]] = set()
    for possession in possessions:
        window = _possession_in_windows(possession, windows)
        if window is None or bool(getattr(possession, "is_ambiguous", False)):
            continue
        key = (
            _possession_match_id(possession),
            _int(getattr(possession, "possession_index", None), _object_id(possession)) or 0,
            window.source == "baseline",
        )
        if key in seen_possessions:
            continue
        seen_possessions.add(key)
        selected_possessions.append(possession)

    exposure_seconds = sum(max(0, window.end_second - window.start_second) for window in windows)
    episode_keys = {window.episode_key for window in windows if window.source == "lead"}
    own_events = [
        event
        for event in selected_event_rows
        if _is_focal_event(event, focal_team_id, focal_provider_by_match)
    ]
    opponent_events = [event for event in selected_event_rows if event not in own_events]
    located_passes = _located_passes(own_events)
    pass_directions = Counter()
    for event in located_passes:
        try:
            pass_directions[pass_direction(physical_vector(event)[0])] += 1
        except (TypeError, ValueError):
            continue

    touches = [
        event
        for event in own_events
        if (bool(getattr(event, "is_touch", False)) or _int(getattr(event, "event_type", None)) == MatchEventType.BALL_TOUCH)
        and _located_x(event) is not None
    ]
    defensive = [
        event
        for event in own_events
        if defensive_family(event) is not None and _located_x(event) is not None
    ]
    shots = [event for event in own_events if _int(getattr(event, "event_type", None)) == MatchEventType.SHOT]
    opponent_shots = [event for event in opponent_events if _int(getattr(event, "event_type", None)) == MatchEventType.SHOT]
    opponent_located = [
        event
        for event in opponent_events
        if _located_x(event) is not None and _int(getattr(event, "event_type", None)) in CONTROL_TYPES
    ]

    territorial_exits = 0
    counters = 0
    for possession in selected_possessions:
        if not _is_focal_event(possession, focal_team_id, focal_provider_by_match):
            # Possessions expose provider_team_id rather than team_id in most
            # materialized rows, so use the provider side below as a fallback.
            team_id = _int(getattr(possession, "team_id", None))
            if team_id != int(focal_team_id):
                provider = focal_provider_by_match.get(_possession_match_id(possession))
                if provider is None or str(getattr(possession, "provider_team_id", "")) != str(provider):
                    continue
        start_x = _int(getattr(possession, "start_x", None))
        end_x = _int(getattr(possession, "end_x", None))
        if start_x is not None and end_x is not None and start_x < 3333 <= end_x:
            territorial_exits += 1
        counters += int(bool(getattr(possession, "is_counter_launch", False)))

    first_attacks = _first_meaningful_attacks(
        selected_event_rows,
        windows,
        focal_team_id=focal_team_id,
        focal_provider_by_match=focal_provider_by_match,
    )
    # Baseline windows have no lead episodes of their own.  Use a synthetic
    # key per baseline window so time-to-first-attack remains comparable and
    # inspectable, while the lead cohort keeps one value per real episode.
    if not episode_keys:
        episode_keys = {window.episode_key for window in windows}

    metrics = {
        "touch_origin_height": _height_metric(
            [_located_x(event) for event in touches if _located_x(event) is not None],
            exposure_seconds,
            key="touch_origin_height",
            label="Touch origin height",
        ),
        "pass_origin_height": _height_metric(
            [_int(getattr(event, "x", None)) for event in located_passes],
            exposure_seconds,
            key="pass_origin_height",
            label="Pass origin height",
        ),
        "defensive_action_height": _height_metric(
            [_located_x(event) for event in defensive if _located_x(event) is not None],
            exposure_seconds,
            key="defensive_action_height",
            label="Defensive-action height",
        ),
        "pass_direction": {
            direction_name: _share_metric(
                pass_directions[direction_name],
                len(located_passes),
                exposure_seconds,
                key=f"pass_direction_{direction_name}",
                label=f"{direction_name.title()} pass share",
                raw={"located_passes": len(located_passes)},
            )
            for direction_name in ("forward", "lateral", "backward")
        },
        "box_entries": _rate_metric(
            sum(bool(getattr(event, "is_box_entry", False)) for event in own_events),
            exposure_seconds,
            key="box_entries",
            label="Own box entries",
        ),
        "shots": _rate_metric(
            len(shots),
            exposure_seconds,
            key="shots",
            label="Own shots",
        ),
        "clearances": _rate_metric(
            sum(defensive_family(event) == "clearance" for event in own_events),
            exposure_seconds,
            key="clearances",
            label="Clearances",
        ),
        "opponent_territory_height": _height_metric(
            [_located_x(event) for event in opponent_located if _located_x(event) is not None],
            exposure_seconds,
            key="opponent_territory_height",
            label="Opponent territorial height",
        ),
        "opponent_final_third_share": _share_metric(
            sum((_located_x(event) or 0) >= FINAL_THIRD_X for event in opponent_located),
            len(opponent_located),
            exposure_seconds,
            key="opponent_final_third_share",
            label="Opponent final-third share",
            raw={"located_opponent_control_events": len(opponent_located)},
        ),
        "opponent_box_entries": _rate_metric(
            sum(bool(getattr(event, "is_box_entry", False)) for event in opponent_events),
            exposure_seconds,
            key="opponent_box_entries",
            label="Opponent box entries",
        ),
        "opponent_shots": _rate_metric(
            len(opponent_shots),
            exposure_seconds,
            key="opponent_shots",
            label="Opponent shots",
        ),
        "opponent_big_chances": _rate_metric(
            sum(bool(getattr(event, "is_big_chance", False)) for event in opponent_shots),
            exposure_seconds,
            key="opponent_big_chances",
            label="Opponent big chances",
        ),
        "own_territorial_exits": _rate_metric(
            territorial_exits,
            exposure_seconds,
            key="own_territorial_exits",
            label="Own territorial exits",
        ),
        "own_counters": _rate_metric(
            counters,
            exposure_seconds,
            key="own_counters",
            label="Own counters",
        ),
        "own_shots": _rate_metric(
            len(shots),
            exposure_seconds,
            key="own_shots",
            label="Own shots",
        ),
        "time_to_first_meaningful_opponent_attack": _time_metric(
            list(first_attacks.values()),
            len(episode_keys),
            exposure_seconds,
            key="time_to_first_meaningful_opponent_attack",
            label="Time to first meaningful opponent attack",
        ),
    }
    return {
        "exposure_seconds": exposure_seconds,
        "episode_count": len(episode_keys),
        "match_count": len({window.match_id for window in windows}),
        "window_count": len(windows),
        "event_count": len(selected_event_rows),
        "own_event_count": len(own_events),
        "opponent_event_count": len(opponent_events),
        "metrics": metrics,
        "first_attacks": first_attacks,
        "windows": windows,
        "raw_counts": {
            "touches_with_location": len(touches),
            "located_passes": len(located_passes),
            "defensive_actions_with_location": len(defensive),
            "opponent_control_events_with_location": len(opponent_located),
        },
    }


def _metric_reliability(metric: Mapping[str, Any], exposure_seconds: int, *, baseline: Mapping[str, Any] | None = None) -> str:
    if metric.get("value") is None or exposure_seconds <= 0 or metric.get("sample_size", 0) <= 0:
        return "unavailable"
    if metric.get("sample_size", 0) < MIN_COMPONENT_EVENTS or exposure_seconds < MIN_LEAD_EXPOSURE_SECONDS:
        return "sparse"
    if baseline is not None and baseline.get("value") is None:
        return "partial"
    return "verified"


def _decorate_metric(selected: Mapping[str, Any], baseline: Mapping[str, Any] | None) -> dict[str, Any]:
    selected = dict(selected)
    baseline_value = baseline.get("value") if baseline else None
    selected_value = selected.get("value")
    selected["baseline_value"] = baseline_value
    selected["baseline_count"] = baseline.get("count") if baseline else None
    selected["baseline_sample_size"] = baseline.get("sample_size") if baseline else None
    selected["baseline_per_state_minute"] = baseline.get("per_state_minute") if baseline else None
    selected["baseline_per_90"] = baseline.get("per_90") if baseline else None
    selected["baseline_raw"] = baseline.get("raw") if baseline else None
    selected["delta"] = (
        round(selected_value - baseline_value, 4)
        if selected_value is not None and baseline_value is not None
        else None
    )
    selected["delta_per_state_minute"] = (
        round(selected.get("per_state_minute") - baseline.get("per_state_minute"), 4)
        if selected.get("per_state_minute") is not None and baseline and baseline.get("per_state_minute") is not None
        else None
    )
    selected["delta_per_90"] = (
        round(selected.get("per_90") - baseline.get("per_90"), 4)
        if selected.get("per_90") is not None and baseline and baseline.get("per_90") is not None
        else None
    )
    selected["reliability"] = _metric_reliability(selected, selected.get("exposure_seconds", 0), baseline=baseline)
    selected["baseline_reliability"] = (
        _metric_reliability(baseline, baseline.get("exposure_seconds", 0)) if baseline else "unavailable"
    )
    return selected


def _surface_metrics(raw: Mapping[str, Any], baseline: Mapping[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    selected_metrics = raw["metrics"]
    baseline_metrics = baseline["metrics"] if baseline else {}
    gravity_keys = (
        "touch_origin_height",
        "pass_origin_height",
        "defensive_action_height",
        "box_entries",
        "shots",
        "clearances",
        "opponent_territory_height",
        "opponent_final_third_share",
    )
    ownership_keys = (
        "opponent_box_entries",
        "opponent_shots",
        "opponent_big_chances",
        "own_territorial_exits",
        "own_counters",
        "own_shots",
        "time_to_first_meaningful_opponent_attack",
    )

    def decorate(key: str) -> Any:
        value = selected_metrics[key]
        other = baseline_metrics.get(key) if baseline_metrics else None
        if isinstance(value, dict) and "value" not in value:
            return {
                direction_name: _decorate_metric(
                    value[direction_name],
                    other.get(direction_name) if isinstance(other, dict) else None,
                )
                for direction_name in value
            }
        return _decorate_metric(value, other)

    gravity = {key: decorate(key) for key in gravity_keys}
    gravity["pass_direction"] = {
        direction_name: _decorate_metric(
            selected_metrics["pass_direction"][direction_name],
            baseline_metrics.get("pass_direction", {}).get(direction_name) if baseline_metrics else None,
        )
        for direction_name in ("forward", "lateral", "backward")
    }
    ownership = {key: decorate(key) for key in ownership_keys}
    return gravity, ownership


def _clamp(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _axis_value(pairs: Sequence[tuple[float | None, float]]) -> tuple[float | None, int]:
    values = [_clamp(value / scale) for value, scale in pairs if value is not None]
    if not values:
        return None, 0
    return round(50 + 50 * (sum(values) / len(values)), 1), len(values)


def _metric_delta(metrics: Mapping[str, Any], key: str, nested: str | None = None) -> float | None:
    value = metrics.get(key)
    if nested:
        value = value.get(nested) if isinstance(value, Mapping) else None
    if not isinstance(value, Mapping):
        return None
    if value.get("reliability") not in {"verified", "partial"}:
        return None
    if value.get("baseline_reliability") not in {"verified", "partial"}:
        return None
    return value.get("delta")


def _axes(gravity: Mapping[str, Any], ownership: Mapping[str, Any]) -> dict[str, Any]:
    # Positive gravity components indicate more retreat relative to the
    # matched drawing baseline.  The fixed scales are intentionally visible in
    # the API thresholds; they are display axes, not team-strength scores.
    gravity_pairs = [
        (-_metric_delta(gravity, "touch_origin_height") if _metric_delta(gravity, "touch_origin_height") is not None else None, 15.0),
        (-_metric_delta(gravity, "pass_origin_height") if _metric_delta(gravity, "pass_origin_height") is not None else None, 15.0),
        (-_metric_delta(gravity, "defensive_action_height") if _metric_delta(gravity, "defensive_action_height") is not None else None, 15.0),
        (-_metric_delta(gravity, "pass_direction", "forward") if _metric_delta(gravity, "pass_direction", "forward") is not None else None, 0.25),
        (-_metric_delta(gravity, "box_entries") if _metric_delta(gravity, "box_entries") is not None else None, 2.0),
        (-_metric_delta(gravity, "shots") if _metric_delta(gravity, "shots") is not None else None, 2.0),
        (_metric_delta(gravity, "clearances"), 2.0),
        (_metric_delta(gravity, "opponent_territory_height"), 15.0),
    ]
    ownership_pairs = [
        (-_metric_delta(ownership, "opponent_box_entries") if _metric_delta(ownership, "opponent_box_entries") is not None else None, 2.0),
        (-_metric_delta(ownership, "opponent_shots") if _metric_delta(ownership, "opponent_shots") is not None else None, 2.0),
        (-_metric_delta(ownership, "opponent_big_chances") if _metric_delta(ownership, "opponent_big_chances") is not None else None, 1.0),
        (_metric_delta(ownership, "own_territorial_exits"), 2.0),
        (_metric_delta(ownership, "own_counters"), 2.0),
        (_metric_delta(ownership, "own_shots"), 2.0),
        (_metric_delta(ownership, "time_to_first_meaningful_opponent_attack"), 300.0),
    ]
    gravity_value, gravity_available = _axis_value(gravity_pairs)
    ownership_value, ownership_available = _axis_value(ownership_pairs)
    return {
        "behavioral_retreat": {
            "value": gravity_value,
            "available_components": gravity_available,
            "higher_means": "more observed retreat relative to the matched baseline",
            "unit": "descriptive 0–100 axis",
        },
        "process_control": {
            "value": ownership_value,
            "available_components": ownership_available,
            "higher_means": "more opposition restriction and viable outlets relative to the matched baseline",
            "unit": "descriptive 0–100 axis",
        },
    }


def quadrant_for(axes: Mapping[str, Any], *, eligible: bool) -> dict[str, Any]:
    """Map the two descriptive axes into a cautious, non-causal quadrant."""

    retreat = axes.get("behavioral_retreat", {}).get("value")
    control = axes.get("process_control", {}).get("value")
    if not eligible or retreat is None or control is None:
        return {
            "label": None,
            "short_label": "Insufficient evidence",
            "available": False,
            "note": "A quadrant label is withheld until lead episodes and matched baseline evidence are sufficient.",
        }
    if retreat < 50 and control >= 50:
        label = "assertive controllers"
    elif retreat >= 50 and control >= 50:
        label = "controlled deep defenders"
    elif retreat < 50:
        label = "vulnerable high teams"
    else:
        label = "retreat and suffer"
    return {
        "label": label,
        "short_label": label.title(),
        "available": True,
        "note": "Descriptive placement from component deltas; it is not a causal or team-strength judgement.",
    }


def _reliability(lead_raw: Mapping[str, Any], baseline_raw: Mapping[str, Any] | None) -> dict[str, Any]:
    episode_count = int(lead_raw.get("episode_count", 0))
    exposure = int(lead_raw.get("exposure_seconds", 0))
    baseline_available = bool(baseline_raw and baseline_raw.get("exposure_seconds", 0) > 0)
    if episode_count == 0 or exposure == 0:
        status = "unavailable"
    elif episode_count < MIN_LEAD_EPISODES or exposure < MIN_LEAD_EXPOSURE_SECONDS:
        status = "sparse"
    elif not baseline_available:
        status = "partial"
    else:
        status = "verified"
    return {
        "status": status,
        "label_eligible": status == "verified",
        "lead_episode_count": episode_count,
        "minimum_lead_episodes": MIN_LEAD_EPISODES,
        "exposure_seconds": exposure,
        "minimum_exposure_seconds": MIN_LEAD_EXPOSURE_SECONDS,
        "matched_baseline_available": baseline_available,
        "note": (
            "Raw components remain visible, but descriptive labels are withheld for sparse or unmatched evidence."
            if status != "verified"
            else "Lead and matched drawing evidence meet the minimum reliability thresholds."
        ),
    }


def _surface_payload(raw: Mapping[str, Any], baseline_raw: Mapping[str, Any] | None) -> dict[str, Any]:
    gravity, ownership = _surface_metrics(raw, baseline_raw)
    axes = _axes(gravity, ownership)
    reliability = _reliability(raw, baseline_raw)
    return {
        "exposure_seconds": raw["exposure_seconds"],
        "exposure_minutes": round(raw["exposure_seconds"] / 60, 2),
        "episode_count": raw["episode_count"],
        "match_count": raw["match_count"],
        "window_count": raw["window_count"],
        "event_count": raw["event_count"],
        "gravity": {
            "components": gravity,
            "raw_components": gravity,
            "axis": axes["behavioral_retreat"],
        },
        "ownership": {
            "components": ownership,
            "raw_components": ownership,
            "axis": axes["process_control"],
        },
        "axes": axes,
        "reliability": reliability,
        "raw_counts": raw["raw_counts"],
    }


def _match_result(match: Any, focal_team_id: int) -> str | None:
    home_score = _int(getattr(match, "home_score", None))
    away_score = _int(getattr(match, "away_score", None))
    if home_score is None or away_score is None:
        return None
    if _int(getattr(match, "home_team_id", None)) == int(focal_team_id):
        difference = home_score - away_score
    else:
        difference = away_score - home_score
    return "win" if difference > 0 else "loss" if difference < 0 else "draw"


def _episode_payload(
    episode: Any,
    lead_windows: Sequence[LeadWindow],
    baseline_windows: Sequence[LeadWindow],
    events: Sequence[Any],
    possessions: Sequence[Any],
    *,
    focal_team_id: int,
    focal_provider_by_match: Mapping[int, str],
    match_references: Mapping[int, int],
    matches_by_id: Mapping[int, Any],
    match_end_seconds: Mapping[int, int] | None = None,
) -> dict[str, Any]:
    lead_raw = _raw_cohort(
        events,
        possessions,
        lead_windows,
        focal_team_id=focal_team_id,
        focal_provider_by_match=focal_provider_by_match,
    )
    baseline_raw = _raw_cohort(
        events,
        possessions,
        baseline_windows,
        focal_team_id=focal_team_id,
        focal_provider_by_match=focal_provider_by_match,
    ) if baseline_windows else None
    surface = _surface_payload(lead_raw, baseline_raw)
    match_id, episode_index = _episode_key(episode)
    start = _int(getattr(episode, "start_second", None), 0) or 0
    end = _int(getattr(episode, "end_second", None), start) or start
    state_entry = _int(getattr(episode, "state_entry_second", None), start) or start
    first_attack = _first_meaningful_attacks(
        events,
        lead_windows,
        focal_team_id=focal_team_id,
        focal_provider_by_match=focal_provider_by_match,
    ).get((match_id, episode_index))
    match = matches_by_id.get(match_id)
    match_end = (match_end_seconds or {}).get(match_id)
    survived = (
        end >= match_end
        if match_end is not None
        else _match_result(match, focal_team_id) == "win"
        if match
        else None
    )
    return {
        "episode_id": f"{match_references.get(match_id, match_id)}:{episode_index}",
        "match_ref": match_references.get(match_id),
        "phase": _phase_name(getattr(episode, "phase", None)),
        "lead_band": lead_band(getattr(episode, "goal_difference", None)),
        "goal_difference": _int(getattr(episode, "goal_difference", None)),
        "start_second": start,
        "end_second": end,
        "state_entry_second": state_entry,
        "duration_seconds": max(0, end - start),
        "clock_buckets": sorted({window.clock_bucket for window in lead_windows}),
        "matched_baseline_windows": len(baseline_windows),
        "matched_baseline_exposure_seconds": baseline_raw["exposure_seconds"] if baseline_raw else 0,
        "time_to_first_meaningful_opponent_attack_seconds": first_attack,
        "behavior": surface["gravity"],
        "ownership": surface["ownership"],
        "coverage": {
            "exposure_seconds": surface["exposure_seconds"],
            "matched_baseline": bool(baseline_raw and baseline_raw["exposure_seconds"] > 0),
            "reliability": surface["reliability"],
        },
        "secondary_outcomes": {
            "lead_survived_to_match_end": survived,
            "final_result": _match_result(match, focal_team_id) if match else None,
            "note": "Survival and final result are secondary outcomes, not the ownership definition.",
        },
    }


def _group_surface(
    lead_windows: Sequence[LeadWindow],
    baseline_windows: Sequence[LeadWindow],
    events: Sequence[Any],
    possessions: Sequence[Any],
    *,
    focal_team_id: int,
    focal_provider_by_match: Mapping[int, str],
) -> dict[str, Any]:
    lead_keys = {window.episode_key for window in lead_windows}
    baseline = [window for window in baseline_windows if window.matched_lead_key in lead_keys]
    return _surface_payload(
        _raw_cohort(
            events,
            possessions,
            lead_windows,
            focal_team_id=focal_team_id,
            focal_provider_by_match=focal_provider_by_match,
        ),
        _raw_cohort(
            events,
            possessions,
            baseline,
            focal_team_id=focal_team_id,
            focal_provider_by_match=focal_provider_by_match,
        ) if baseline else None,
    )


def build_lead_control_payload(
    events: Iterable[Any],
    episodes: Iterable[Any],
    possessions: Iterable[Any] = (),
    *,
    focal_team_id: int,
    team_name: str | None = None,
    matches: Iterable[Any] = (),
    match_references: Mapping[int, int] | None = None,
    focal_provider_by_match: Mapping[int, str] | None = None,
    lens: StateLens | None = None,
    eligible_match_ids: set[int] | None = None,
    selected_match_ref: int | None = None,
    match_end_seconds: Mapping[int, int] | None = None,
) -> dict[str, Any]:
    """Build the complete, public Lead Control contract from materialized rows."""

    events = list(events)
    episodes = list(episodes)
    possessions = list(possessions)
    matches = list(matches)
    match_references = dict(match_references or {})
    focal_provider_by_match = dict(focal_provider_by_match or {})
    if eligible_match_ids is not None:
        allowed = {int(value) for value in eligible_match_ids}
        events = [event for event in events if _event_match_id(event) in allowed]
        episodes = [episode for episode in episodes if _episode_key(episode)[0] in allowed]
        possessions = [possession for possession in possessions if _possession_match_id(possession) in allowed]
        matches = [match for match in matches if _object_id(match) in allowed]

    lens = lens or StateLens(selected=StateLensScope(), baseline=None)
    selected_scope = lens.selected
    # Lead Gravity always requires winning episodes.  ``state=all`` means
    # “all winning lead episodes”, not a blend with drawing or losing states.
    lead_episodes = [
        episode
        for episode in episodes
        if _state_name(getattr(episode, "state", None)) == "winning"
        and _scope_matches_episode(episode, selected_scope)
    ]
    lead_windows = build_lead_windows(lead_episodes, selected_scope)
    baseline_scope = lens.baseline
    if baseline_scope is None:
        baseline_scope = StateLensScope(state="drawing", goal_difference=0)
    elif baseline_scope.state not in {"all", "drawing"}:
        # A winning/losing UI baseline cannot be mistaken for the explicit
        # drawing control.  Keep its phase/age refinements, but force draw.
        baseline_scope = StateLensScope(
            state="drawing",
            goal_difference=0,
            phase=baseline_scope.phase,
            draw_provenance=baseline_scope.draw_provenance,
            minimum_state_age_seconds=baseline_scope.minimum_state_age_seconds,
            maximum_state_age_seconds=baseline_scope.maximum_state_age_seconds,
        )
    baseline_windows = build_matched_baseline_windows(lead_windows, episodes, baseline_scope)

    selected_raw = _raw_cohort(
        events,
        possessions,
        lead_windows,
        focal_team_id=focal_team_id,
        focal_provider_by_match=focal_provider_by_match,
    )
    baseline_raw = _raw_cohort(
        events,
        possessions,
        baseline_windows,
        focal_team_id=focal_team_id,
        focal_provider_by_match=focal_provider_by_match,
    ) if baseline_windows else None
    selected = _surface_payload(selected_raw, baseline_raw)
    baseline = _surface_payload(baseline_raw, None) if baseline_raw else None
    reliability = selected["reliability"]
    axes = selected["axes"]

    episodes_by_key = {_episode_key(episode): episode for episode in lead_episodes}
    episode_rows = []
    for key, episode in sorted(episodes_by_key.items(), key=lambda item: (item[1].start_second, item[0])):
        windows = [window for window in lead_windows if window.episode_key == key]
        matching = [window for window in baseline_windows if window.matched_lead_key == key]
        if len(episode_rows) >= EPISODE_EVIDENCE_LIMIT:
            break
        episode_rows.append(
            _episode_payload(
                episode,
                windows,
                matching,
                events,
                possessions,
                focal_team_id=focal_team_id,
                focal_provider_by_match=focal_provider_by_match,
                match_references=match_references,
                matches_by_id={_object_id(match): match for match in matches},
                match_end_seconds=match_end_seconds,
            )
        )

    lead_band_breakdown = {
        band: _group_surface(
            [window for window in lead_windows if window.lead_band == band],
            baseline_windows,
            events,
            possessions,
            focal_team_id=focal_team_id,
            focal_provider_by_match=focal_provider_by_match,
        )
        for band in LEAD_BANDS
    }
    phase_names = sorted({window.phase for window in lead_windows})
    phase_breakdown = {
        phase: _group_surface(
            [window for window in lead_windows if window.phase == phase],
            baseline_windows,
            events,
            possessions,
            focal_team_id=focal_team_id,
            focal_provider_by_match=focal_provider_by_match,
        )
        for phase in phase_names
    }

    matched_episode_keys = {window.matched_lead_key for window in baseline_windows if window.matched_lead_key}
    coverage = {
        "lead_episode_count": len(episodes_by_key),
        "one_goal_episode_count": sum(
            lead_band(getattr(episode, "goal_difference", None)) == LEAD_BAND_ONE_GOAL
            for episode in lead_episodes
        ),
        "multi_goal_episode_count": sum(
            lead_band(getattr(episode, "goal_difference", None)) == LEAD_BAND_MULTI_GOAL
            for episode in lead_episodes
        ),
        "match_count": len({key[0] for key in episodes_by_key}),
        "exposure_seconds": selected_raw["exposure_seconds"],
        "matched_baseline_window_count": len(baseline_windows),
        "matched_baseline_episode_count": len(matched_episode_keys),
        "matched_baseline_exposure_seconds": baseline_raw["exposure_seconds"] if baseline_raw else 0,
        "episode_evidence_limit": EPISODE_EVIDENCE_LIMIT,
        "episode_evidence_truncated": len(episodes_by_key) > EPISODE_EVIDENCE_LIMIT,
        "reliability": reliability,
    }

    return {
        "contract_version": LEAD_CONTROL_API_VERSION,
        "formula_version": LEAD_CONTROL_FORMULA_VERSION,
        "team": {"id": int(focal_team_id), "name": team_name},
        "selected_match_ref": selected_match_ref,
        "selected": {
            **selected,
            "lead_band_breakdown": lead_band_breakdown,
            "phase_breakdown": phase_breakdown,
            "episodes": episode_rows,
        },
        "baseline": baseline,
        "comparison": {
            "enabled": baseline_raw is not None and baseline_raw["exposure_seconds"] > 0,
            "baseline_type": "clock_goal_difference_matched_drawing",
            "lead_state": "winning",
            "baseline_state": "drawing",
            "baseline_goal_difference": 0,
            "phase_matching": "same_phase",
            "clock_matching": {
                "bucket_seconds": CLOCK_BUCKET_SECONDS,
                "tolerance_seconds": CLOCK_MATCH_TOLERANCE_SECONDS,
                "rule": "same or adjacent 15-minute clock bucket; candidate midpoint within 15 minutes",
            },
            "baseline": baseline,
            "matched_windows": len(baseline_windows),
            "delta_note": "Component deltas are lead minus the matched drawing baseline; no composite is used to replace them.",
        },
        "quadrant": {
            **axes,
            "placement": quadrant_for(axes, eligible=reliability["label_eligible"]),
        },
        "episodes": episode_rows,
        "coverage": coverage,
        "thresholds": {
            "clock_bucket_seconds": CLOCK_BUCKET_SECONDS,
            "clock_match_tolerance_seconds": CLOCK_MATCH_TOLERANCE_SECONDS,
            "minimum_lead_episodes": MIN_LEAD_EPISODES,
            "minimum_lead_exposure_seconds": MIN_LEAD_EXPOSURE_SECONDS,
            "minimum_component_events": MIN_COMPONENT_EVENTS,
            "episode_evidence_limit": EPISODE_EVIDENCE_LIMIT,
            "axis_scales": AXIS_SCALES,
            "possession_calculation_version": POSSESSION_CALCULATION_VERSION,
            "territory": {
                "final_third_x": FINAL_THIRD_X / 100,
                "box_x": BOX_X / 100,
            },
        },
        "limitations": [
            "Lead Gravity describes within-team behavioural change after a lead; it is not a causal explanation.",
            "Lead Ownership uses opponent access, own outlets, and first-attack timing as process evidence; lead survival and final result are secondary outcomes.",
            "Opponent strength, venue, line-ups, substitutions, and tactical context are not controlled in this v1 contract.",
            "Raw counts, state-minute rates, matched baseline values, and episode evidence remain inspectable beside every descriptive axis.",
            "Sparse or unmatched lead samples do not receive a quadrant label.",
        ],
        "opponent_strength": {
            "controlled": False,
            "available": False,
            "note": "No opponent-strength adjustment is present; comparisons should not be read as causal or as a team-strength ranking.",
        },
    }
