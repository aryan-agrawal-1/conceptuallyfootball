"""Lead-control episode slicing, clock matching, and interval lookup."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from ingestion.models import MatchEventGameState, MatchStatePhase
from ingestion.state_lens import StateLensScope


CLOCK_BUCKET_SECONDS = 15 * 60
CLOCK_MATCH_TOLERANCE_SECONDS = CLOCK_BUCKET_SECONDS

LEAD_BAND_ONE_GOAL = "one_goal"
LEAD_BAND_MULTI_GOAL = "multi_goal"
LEAD_BANDS = (LEAD_BAND_ONE_GOAL, LEAD_BAND_MULTI_GOAL)

PHASE_LABELS = {
    MatchStatePhase.FIRST_HALF: "first_half",
    MatchStatePhase.SECOND_HALF: "second_half",
    MatchStatePhase.FIRST_EXTRA_TIME: "first_extra_time",
    MatchStatePhase.SECOND_EXTRA_TIME: "second_extra_time",
}


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
        if normalized in PHASE_LABELS.values():
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
    match_id = _int(getattr(row, "provider_match_id", None))
    if match_id is None:
        match_id = _object_id(getattr(row, "provider_match", None), fallback)
    return match_id, _episode_index(row, fallback)


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


def _episode_window(
    episode: Any,
    scope: StateLensScope | None,
) -> tuple[int, int] | None:
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


def _episode_to_windows(
    episode: Any,
    scope: StateLensScope | None,
    *,
    source: str = "lead",
    matched_lead_key: tuple[int, int] | None = None,
) -> list[LeadWindow]:
    if not _scope_matches_episode(episode, scope):
        return []
    window = _episode_window(episode, scope)
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
        if min(window[1], (bucket + 1) * CLOCK_BUCKET_SECONDS)
        > max(window[0], bucket * CLOCK_BUCKET_SECONDS)
    ]


def build_lead_windows(
    episodes: Iterable[Any],
    scope: StateLensScope | None = None,
) -> list[LeadWindow]:
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
    """Match drawing windows by phase and clock, never season-wide totals."""

    candidates = []
    for episode in episodes:
        if _state_name(getattr(episode, "state", None)) != "drawing":
            continue
        if (_int(getattr(episode, "goal_difference", None), 0) or 0) != 0:
            continue
        if baseline_scope and not _scope_matches_episode(episode, baseline_scope):
            continue
        candidates.extend(
            _episode_to_windows(episode, baseline_scope, source="baseline")
        )

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
    return _int(
        getattr(event, "timeline_seconds", None),
        _int(getattr(event, "match_seconds", None)),
    )


def _event_match_id(event: Any) -> int:
    match_id = _int(getattr(event, "provider_match_id", None))
    if match_id is not None:
        return match_id
    return _object_id(getattr(event, "provider_match", None))


def _event_id(event: Any) -> tuple[int, int]:
    event_index = _int(getattr(event, "event_index", None))
    if event_index is None:
        event_index = _object_id(event)
    return _event_match_id(event), event_index


def _possession_match_id(possession: Any) -> int:
    match_id = _int(getattr(possession, "provider_match_id", None))
    if match_id is not None:
        return match_id
    return _object_id(getattr(possession, "provider_match", None))


def _window_index(
    windows: Sequence[LeadWindow],
) -> dict[int, tuple[tuple[int, ...], tuple[LeadWindow, ...]]]:
    indexed: dict[int, list[LeadWindow]] = {}
    for window in windows:
        indexed.setdefault(window.match_id, []).append(window)
    result: dict[int, tuple[tuple[int, ...], tuple[LeadWindow, ...]]] = {}
    for match_id, windows_for_match in indexed.items():
        sorted_windows = sorted(
            windows_for_match,
            key=lambda window: (window.start_second, window.end_second),
        )
        result[match_id] = (
            tuple(window.start_second for window in sorted_windows),
            tuple(sorted_windows),
        )
    return result


def _rows_by_match(rows: Iterable[Any], match_id_getter: Any) -> dict[int, list[Any]]:
    indexed: dict[int, list[Any]] = {}
    for row in rows:
        indexed.setdefault(int(match_id_getter(row)), []).append(row)
    return indexed


def _window_at_second(
    second: int | None,
    match_id: int,
    windows: Sequence[LeadWindow]
    | Mapping[int, tuple[tuple[int, ...], tuple[LeadWindow, ...]]],
) -> LeadWindow | None:
    if second is None:
        return None
    if isinstance(windows, Mapping):
        indexed = windows.get(match_id)
        if indexed is None:
            return None
        starts, candidates = indexed
        candidate_index = bisect_right(starts, second) - 1
        while candidate_index >= 0 and candidates[candidate_index].start_second <= second:
            window = candidates[candidate_index]
            if window.end_second > second:
                return window
            candidate_index -= 1
        return None
    for window in windows:
        if window.match_id == match_id and window.start_second <= second < window.end_second:
            return window
    return None


def _event_in_windows(
    event: Any,
    windows: Sequence[LeadWindow]
    | Mapping[int, tuple[tuple[int, ...], tuple[LeadWindow, ...]]],
) -> LeadWindow | None:
    return _window_at_second(_event_second(event), _event_match_id(event), windows)


def _possession_in_windows(
    possession: Any,
    windows: Sequence[LeadWindow]
    | Mapping[int, tuple[tuple[int, ...], tuple[LeadWindow, ...]]],
) -> LeadWindow | None:
    return _window_at_second(
        _int(getattr(possession, "start_second", None)),
        _possession_match_id(possession),
        windows,
    )
