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
from collections.abc import Mapping
from statistics import mean, median
from typing import Any, Iterable, Sequence

from ingestion.models import MatchEventShotOutcome, MatchEventType
from ingestion.services.defensive_territory import defensive_family
from ingestion.services.lead_control_presentation import (
    AXIS_SCALES,
    MIN_COMPONENT_EVENTS,
    MIN_LEAD_EPISODES,
    MIN_LEAD_EXPOSURE_SECONDS,
    _surface_payload,
    quadrant_for,
)
from ingestion.services.lead_control_windows import (
    CLOCK_BUCKET_SECONDS,
    CLOCK_MATCH_TOLERANCE_SECONDS,
    LEAD_BAND_MULTI_GOAL,
    LEAD_BAND_ONE_GOAL,
    LEAD_BANDS,
    LeadWindow,
    _episode_key,
    _event_id,
    _event_in_windows,
    _event_match_id,
    _event_second,
    _int,
    _object_id,
    _phase_name,
    _possession_in_windows,
    _possession_match_id,
    _rows_by_match,
    _scope_matches_episode,
    _state_name,
    _window_index,
    build_lead_windows,
    build_matched_baseline_windows,
    lead_band,
)
from ingestion.services.possession_context import (
    BOX_X,
    FINAL_THIRD_X,
    POSSESSION_CALCULATION_VERSION,
)
from ingestion.services.pass_state import direction as pass_direction
from ingestion.services.pass_state import physical_vector
from ingestion.state_lens import StateLens, StateLensScope


LEAD_CONTROL_FORMULA_VERSION = "lead_control_v1"
LEAD_CONTROL_API_VERSION = "lead_control_api_v2"
EPISODE_EVIDENCE_LIMIT = 100

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
    events_by_match: Mapping[int, Sequence[Any]] | None = None,
) -> dict[tuple[int, int], int]:
    first: dict[tuple[int, int], int] = {}
    window_index = _window_index(windows)
    if events_by_match is None:
        event_rows: Iterable[Any] = events
    else:
        event_rows = (
            event
            for match_id in sorted(window_index)
            for event in events_by_match.get(match_id, ())
        )
    for event in event_rows:
        if _is_deleted(event) or _is_focal_event(event, focal_team_id, focal_provider_by_match):
            continue
        if not (
            bool(getattr(event, "is_box_entry", False))
            or _int(getattr(event, "event_type", None)) == MatchEventType.SHOT
            or bool(getattr(event, "is_big_chance", False))
        ):
            continue
        window = _event_in_windows(event, window_index)
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
    events_by_match: Mapping[int, Sequence[Any]] | None = None,
    possessions_by_match: Mapping[int, Sequence[Any]] | None = None,
) -> dict[str, Any]:
    windows = _unique_windows(windows)
    window_index = _window_index(windows)
    focal_provider_by_match = focal_provider_by_match or {}
    selected_event_rows: list[Any] = []
    seen_events: set[tuple[int, int]] = set()
    if events_by_match is None:
        event_rows: Iterable[Any] = events
    else:
        event_rows = (
            event
            for match_id in sorted(window_index)
            for event in events_by_match.get(match_id, ())
        )
    for event in event_rows:
        if _is_deleted(event):
            continue
        window = _event_in_windows(event, window_index)
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
    if possessions_by_match is None:
        possession_rows: Iterable[Any] = possessions
    else:
        possession_rows = (
            possession
            for match_id in sorted(window_index)
            for possession in possessions_by_match.get(match_id, ())
        )
    for possession in possession_rows:
        window = _possession_in_windows(possession, window_index)
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
    own_event_ids = {_event_id(event) for event in own_events}
    opponent_events = [event for event in selected_event_rows if _event_id(event) not in own_event_ids]
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
    events_by_match: Mapping[int, Sequence[Any]] | None = None,
    possessions_by_match: Mapping[int, Sequence[Any]] | None = None,
    first_attacks: Mapping[tuple[int, int], int] | None = None,
) -> dict[str, Any]:
    lead_raw = _raw_cohort(
        events,
        possessions,
        lead_windows,
        focal_team_id=focal_team_id,
        focal_provider_by_match=focal_provider_by_match,
        events_by_match=events_by_match,
        possessions_by_match=possessions_by_match,
    )
    baseline_raw = _raw_cohort(
        events,
        possessions,
        baseline_windows,
        focal_team_id=focal_team_id,
        focal_provider_by_match=focal_provider_by_match,
        events_by_match=events_by_match,
        possessions_by_match=possessions_by_match,
    ) if baseline_windows else None
    surface = _surface_payload(lead_raw, baseline_raw)
    match_id, episode_index = _episode_key(episode)
    start = _int(getattr(episode, "start_second", None), 0) or 0
    end = _int(getattr(episode, "end_second", None), start) or start
    state_entry = _int(getattr(episode, "state_entry_second", None), start) or start
    if first_attacks is None:
        first_attacks = _first_meaningful_attacks(
            events,
            lead_windows,
            focal_team_id=focal_team_id,
            focal_provider_by_match=focal_provider_by_match,
            events_by_match=events_by_match,
        )
    first_attack = first_attacks.get((match_id, episode_index))
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
        # Episode drilldown keeps the component metrics (including each
        # metric's raw values) but omits the aggregate raw_components alias.
        # The alias is identical to components and would double the bounded
        # evidence payload without adding information.
        "behavior": {
            "components": surface["gravity"]["components"],
            "axis": surface["gravity"]["axis"],
        },
        "ownership": {
            "components": surface["ownership"]["components"],
            "axis": surface["ownership"]["axis"],
        },
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
    events_by_match: Mapping[int, Sequence[Any]] | None = None,
    possessions_by_match: Mapping[int, Sequence[Any]] | None = None,
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
            events_by_match=events_by_match,
            possessions_by_match=possessions_by_match,
        ),
        _raw_cohort(
            events,
            possessions,
            baseline,
            focal_team_id=focal_team_id,
            focal_provider_by_match=focal_provider_by_match,
            events_by_match=events_by_match,
            possessions_by_match=possessions_by_match,
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

    events_by_match = _rows_by_match(events, _event_match_id)
    possessions_by_match = _rows_by_match(possessions, _possession_match_id)

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
        events_by_match=events_by_match,
        possessions_by_match=possessions_by_match,
    )
    baseline_raw = _raw_cohort(
        events,
        possessions,
        baseline_windows,
        focal_team_id=focal_team_id,
        focal_provider_by_match=focal_provider_by_match,
        events_by_match=events_by_match,
        possessions_by_match=possessions_by_match,
    ) if baseline_windows else None
    selected = _surface_payload(selected_raw, baseline_raw)
    baseline = _surface_payload(baseline_raw, None) if baseline_raw else None
    reliability = selected["reliability"]
    axes = selected["axes"]
    lead_first_attacks = _first_meaningful_attacks(
        events,
        lead_windows,
        focal_team_id=focal_team_id,
        focal_provider_by_match=focal_provider_by_match,
        events_by_match=events_by_match,
    )

    episodes_by_key = {_episode_key(episode): episode for episode in lead_episodes}
    matches_by_id = {_object_id(match): match for match in matches}
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
                matches_by_id=matches_by_id,
                match_end_seconds=match_end_seconds,
                events_by_match=events_by_match,
                possessions_by_match=possessions_by_match,
                first_attacks=lead_first_attacks,
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
            events_by_match=events_by_match,
            possessions_by_match=possessions_by_match,
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
            events_by_match=events_by_match,
            possessions_by_match=possessions_by_match,
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
