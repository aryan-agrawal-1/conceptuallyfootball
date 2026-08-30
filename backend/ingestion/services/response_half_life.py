"""Deterministic post-concession Response Half-Life evidence.

Response Half-Life describes how a team's observed behaviour moves from the
first five minutes after a concession towards the team's established behaviour
for the new score state.  It is a descriptive temporal measure; it is not a
claim that an event caused a goal or that the destination is a tactical
quality grade.

The service intentionally consumes the already materialized WhoScored
contracts from batches 9 and 10:

* score transitions and focal-team episodes from ``#105``;
* shot/box-entry evidence from ``#108``;
* defensive location families from ``#107``; and
* pass direction, length, and completion semantics from ``#110``.

Windows are half-open five-minute intervals beginning at the valid concession
timestamp.  A new window starts every minute, so consecutive windows overlap
by four minutes.  A window must fit wholly inside one played period.  Added
time and extra-time periods use their persisted played boundaries and are
therefore included only when a complete window remains.  A window crossing a
period boundary, a subsequent goal, a dismissal, or a participation change is
not used for the aggregate and remains visible as a censored trace.

The expected destination is built from stable episodes in the competition
season.  Exact resulting state + phase + goal difference is preferred.  When
that exact cell has too little stable exposure, a state + phase destination may
be used and the relaxed match basis is exposed.  No destination is invented
when neither cell meets the evidence floor.

Attacking and structural signals are deliberately different:

* attacking = equal-weight mean of normalized absolute deviations in shot
  frequency, box-entry frequency, progressive-action frequency, and attacking
  action height;
* structural = equal-weight mean of normalized absolute deviations in forward
  pass share, pass length, completion rate, team action territory, and
  defensive-action height.

For an episode, the initial deviation is the signal in offset-zero's window.
The half-life is the first later supported rolling window whose signal is at
most half of that initial value.  A zero initial deviation has a zero
half-life.  If no later supported window reaches the threshold the episode is
reported as ``no_recovery`` rather than being assigned a value.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from statistics import median
from typing import Any, Mapping, Sequence
from types import SimpleNamespace

from django.core.exceptions import ObjectDoesNotExist

from ingestion.models import (
    MatchEventGameState,
    MatchEventPeriod,
    MatchEventShotOutcome,
    MatchEventShotSituation,
    MatchEventType,
    MatchStatePhase,
)
from ingestion.services.defensive_territory import defensive_family
from ingestion.services.pass_state import direction as pass_direction
from ingestion.services.pass_state import physical_vector
from ingestion.services.transition_leverage import (
    focal_provider_team_id,
    is_valid_goal_event,
    scoring_provider_team_id,
)
from ingestion.state_lens import StateLensScope


RESPONSE_HALF_LIFE_FORMULA_VERSION = "response_half_life_v1"
RESPONSE_HALF_LIFE_API_VERSION = "response_half_life_api_v1"
RESPONSE_HALF_LIFE_WINDOW_SECONDS = 300
RESPONSE_HALF_LIFE_STEP_SECONDS = 60
RESPONSE_HALF_LIFE_HORIZON_SECONDS = 900
RESPONSE_HALF_LIFE_RAPID_GOAL_SECONDS = 120
RESPONSE_HALF_LIFE_DESTINATION_STABLE_AGE_SECONDS = 600
RESPONSE_HALF_LIFE_DESTINATION_MIN_EXPOSURE_SECONDS = 900
RESPONSE_HALF_LIFE_DESTINATION_MIN_EVENTS = 10
RESPONSE_HALF_LIFE_DESTINATION_MIN_PASSES = 5
RESPONSE_HALF_LIFE_TRACE_LIMIT = 100
RESPONSE_HALF_LIFE_WINDOW_LIMIT = 25

ATTACKING_ACTION_TYPES = frozenset(
    {
        MatchEventType.PASS,
        MatchEventType.BALL_TOUCH,
        MatchEventType.TAKE_ON,
        MatchEventType.SHOT,
    }
)
ACTION_TYPES = ATTACKING_ACTION_TYPES | frozenset(
    {
        MatchEventType.BALL_RECOVERY,
        MatchEventType.TACKLE,
        MatchEventType.INTERCEPTION,
        MatchEventType.CLEARANCE,
        MatchEventType.BLOCKED_PASS,
        MatchEventType.AERIAL,
        MatchEventType.CHALLENGE,
        MatchEventType.DISPOSSESSED,
    }
)

ATTACKING_COMPONENTS = (
    "shots_per_minute",
    "box_entries_per_minute",
    "progressive_actions_per_minute",
    "action_height",
)
STRUCTURAL_COMPONENTS = (
    "forward_pass_share",
    "pass_length_metres",
    "completion_rate",
    "territory_height",
    "defensive_height",
)

# The rate floors avoid an unstable relative difference when a destination has
# a zero count.  Height uses the 0..100 normalized acting-team frame.  These
# are scales, not weights and are returned as part of the public contract.
ATTACKING_DEVIATION_SCALES = {
    "shots_per_minute": 1.0,
    "box_entries_per_minute": 1.0,
    "progressive_actions_per_minute": 1.0,
    "action_height": 50.0,
}
STRUCTURAL_DEVIATION_SCALES = {
    "forward_pass_share": 0.5,
    "pass_length_metres": 15.0,
    "completion_rate": 0.25,
    "territory_height": 50.0,
    "defensive_height": 50.0,
}


@dataclass(frozen=True, slots=True)
class ResponseConcession:
    """One score-changing goal conceded by the focal team."""

    provider_match_id: int
    match_ref: int | None
    event_index: int
    second: int
    period: int
    phase: str | None
    before_state: str | None
    after_state: str | None
    before_goal_difference: int | None
    after_goal_difference: int | None
    before_score: tuple[int | None, int | None]
    after_score: tuple[int | None, int | None]
    draw_provenance: str | None
    scoring_provider_team_id: str | None


@dataclass(frozen=True, slots=True)
class ResponseMatchData:
    """Loaded event materializations for one match.

    The dataclass makes the calculation usable in deterministic unit tests
    without requiring a Django queryset for every helper.
    """

    match: Any
    events: tuple[Any, ...]
    episodes: tuple[Any, ...]
    carries: tuple[Any, ...]
    eligible: bool = True


def _int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _second(event: Any) -> int | None:
    """Return only the canonical played-time timestamp.

    ``match_seconds`` is the provider display clock and may reset at a period
    boundary; using it for episode attribution would turn an uncertain event
    into a seemingly valid response observation.
    """

    return _int(getattr(event, "timeline_seconds", None))


def _sequence(event: Any) -> tuple[int, str, int]:
    value = getattr(event, "provider_event_sequence_id", None)
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = 2**31 - 1
    return numeric, str(value or ""), _int(getattr(event, "event_index", None)) or 0


def _event_state_name(value: Any) -> str | None:
    values = {
        MatchEventGameState.DRAWING: "drawing",
        MatchEventGameState.WINNING: "winning",
        MatchEventGameState.LOSING: "losing",
    }
    value = _int(value)
    return values.get(value)


def _state_from_difference(difference: int | None) -> str | None:
    if difference is None:
        return None
    if difference > 0:
        return "winning"
    if difference < 0:
        return "losing"
    return "drawing"


def _focal_id(match: Any, focal_team_id: int) -> str | None:
    return focal_provider_team_id(match, focal_team_id)


def _event_provider_team(event: Any) -> str:
    return str(getattr(event, "provider_team_id", ""))


def _score_before_after(
    event: Any,
    *,
    match: Any,
    focal_team_id: int,
    fallback_before: tuple[int, int] | None = None,
) -> tuple[int | None, int | None, tuple[int | None, int | None], tuple[int | None, int | None]]:
    home_before = _int(getattr(event, "home_score_before", None))
    away_before = _int(getattr(event, "away_score_before", None))
    home_after = _int(getattr(event, "home_score_after", None))
    away_after = _int(getattr(event, "away_score_after", None))
    if home_before is None or away_before is None:
        if fallback_before is not None:
            home_before, away_before = fallback_before
    scoring = scoring_provider_team_id(event, match)
    if home_after is None or away_after is None:
        home_after, away_after = home_before, away_before
        if scoring == str(getattr(match, "home_provider_team", "")):
            home_after = (home_after or 0) + 1
        elif scoring == str(getattr(match, "away_provider_team", "")):
            away_after = (away_after or 0) + 1
        else:
            home_provider = str(getattr(match, "home_provider_team_id", ""))
            away_provider = str(getattr(match, "away_provider_team_id", ""))
            if scoring == home_provider:
                home_after = (home_after or 0) + 1
            elif scoring == away_provider:
                away_after = (away_after or 0) + 1

    if _int(getattr(match, "home_team_id", None)) == int(focal_team_id):
        before_difference = (
            home_before - away_before
            if home_before is not None and away_before is not None
            else None
        )
        after_difference = (
            home_after - away_after
            if home_after is not None and away_after is not None
            else None
        )
        return before_difference, after_difference, (home_before, away_before), (home_after, away_after)
    before_difference = (
        away_before - home_before
        if home_before is not None and away_before is not None
        else None
    )
    after_difference = (
        away_after - home_after
        if home_after is not None and away_after is not None
        else None
    )
    return before_difference, after_difference, (home_before, away_before), (home_after, away_after)


def _episode_at(second: int | None, episodes: Sequence[Any], *, before: bool = False) -> Any | None:
    if second is None:
        return None
    if before:
        rows = [row for row in episodes if int(row.end_second) <= second]
        return max(rows, key=lambda row: (int(row.end_second), int(row.episode_index)), default=None)
    return next(
        (
            row
            for row in episodes
            if int(row.start_second) <= second < int(row.end_second)
        ),
        None,
    )


def valid_goal_events(data: ResponseMatchData) -> list[Any]:
    """Return sorted goals that changed the supported played score."""

    return sorted(
        (
            event
            for event in data.events
            if is_valid_goal_event(event)
            and _second(event) is not None
            and _int(getattr(event, "period", None)) in {
                int(MatchEventPeriod.FIRST_HALF),
                int(MatchEventPeriod.SECOND_HALF),
                int(MatchEventPeriod.FIRST_EXTRA_TIME),
                int(MatchEventPeriod.SECOND_EXTRA_TIME),
            }
        ),
        key=lambda event: (_second(event) or 0, _sequence(event)),
    )


def uncertain_concession_event_count(
    data: ResponseMatchData,
    *,
    focal_team_id: int,
) -> int:
    """Count opponent goals that lack canonical played-time timestamps."""

    focal_provider = _focal_id(data.match, focal_team_id)
    if not focal_provider or not data.eligible:
        return 0
    return sum(
        _second(event) is None
        and is_valid_goal_event(event)
        and scoring_provider_team_id(event, data.match) not in {None, focal_provider}
        for event in data.events
    )


def find_concessions(
    data: ResponseMatchData,
    *,
    focal_team_id: int,
    match_ref: int | None = None,
) -> list[ResponseConcession]:
    """Replay valid goals and return only opponent-scored transitions."""

    if not data.eligible:
        return []
    match = data.match
    focal_provider = _focal_id(match, focal_team_id)
    if not focal_provider:
        return []
    score = (0, 0)
    result = []
    episodes = data.episodes
    for event in valid_goal_events(data):
        before_difference, after_difference, before_score, after_score = _score_before_after(
            event,
            match=match,
            focal_team_id=focal_team_id,
            fallback_before=score,
        )
        # Prefer persisted score context when available, but keep the replay
        # running for compact test fixtures without score-before fields.
        home_after = after_score[0]
        away_after = after_score[1]
        if home_after is not None and away_after is not None:
            score = (home_after, away_after)
        scorer = scoring_provider_team_id(event, match)
        if scorer is None:
            continue
        if scorer != focal_provider:
            second = _second(event)
            after_episode = _episode_at(second, episodes)
            before_episode = _episode_at(second, episodes, before=True)
            phase = getattr(after_episode, "phase", None) or getattr(event, "period", None)
            if isinstance(phase, int):
                phase = {
                    int(MatchEventPeriod.FIRST_HALF): MatchStatePhase.FIRST_HALF,
                    int(MatchEventPeriod.SECOND_HALF): MatchStatePhase.SECOND_HALF,
                    int(MatchEventPeriod.FIRST_EXTRA_TIME): MatchStatePhase.FIRST_EXTRA_TIME,
                    int(MatchEventPeriod.SECOND_EXTRA_TIME): MatchStatePhase.SECOND_EXTRA_TIME,
                }.get(phase)
            result.append(
                ResponseConcession(
                    provider_match_id=int(getattr(match, "id", getattr(match, "pk", 0))),
                    match_ref=match_ref,
                    event_index=int(getattr(event, "event_index", 0)),
                    second=int(second),
                    period=int(getattr(event, "period", 0)),
                    phase=str(phase) if phase is not None else None,
                    before_state=(
                        _state_from_difference(before_difference)
                        or _event_state_name(getattr(before_episode, "state", None))
                    ),
                    after_state=(
                        _state_from_difference(after_difference)
                        or _event_state_name(getattr(after_episode, "state", None))
                    ),
                    before_goal_difference=before_difference,
                    after_goal_difference=after_difference,
                    before_score=(
                        before_score
                        if _int(getattr(match, "home_team_id", None)) == int(focal_team_id)
                        else (before_score[1], before_score[0])
                    ),
                    after_score=(
                        after_score
                        if _int(getattr(match, "home_team_id", None)) == int(focal_team_id)
                        else (after_score[1], after_score[0])
                    ),
                    draw_provenance=(
                        str(getattr(after_episode, "draw_provenance", "none"))
                        if after_episode is not None
                        else None
                    ),
                    scoring_provider_team_id=scorer,
                )
            )
    return result


def _scope_matches(concession: ResponseConcession, scope: StateLensScope | Mapping[str, Any] | None) -> bool:
    if scope is None:
        return True
    if isinstance(scope, StateLensScope):
        values = {
            "state": scope.state,
            "goal_difference": scope.goal_difference,
            "phase": scope.phase,
            "draw_provenance": scope.draw_provenance,
        }
    else:
        values = {
            "state": scope.get("state", "all"),
            "goal_difference": scope.get("goal_difference", scope.get("goalDifference")),
            "phase": scope.get("phase"),
            "draw_provenance": scope.get("draw_provenance", scope.get("drawProvenance")),
        }
    return (
        values["state"] in (None, "all", concession.after_state)
        and (values["goal_difference"] is None or values["goal_difference"] == concession.after_goal_difference)
        and (values["phase"] is None or values["phase"] == concession.phase)
        and (
            values["draw_provenance"] is None
            or values["draw_provenance"] == concession.draw_provenance
        )
    )


def _stable_segments(
    data: ResponseMatchData,
    *,
    focal_team_id: int,
    state: str | None,
    phase: str | None,
    goal_difference: int | None,
) -> tuple[list[tuple[int, int]], int]:
    segments = []
    exposure = 0
    for episode in data.episodes:
        if state not in (None, "all", _event_state_name(getattr(episode, "state", None))):
            continue
        if phase is not None and str(getattr(episode, "phase", "")) != str(phase):
            continue
        if goal_difference is not None and int(getattr(episode, "goal_difference", 0)) != int(goal_difference):
            continue
        start = max(
            int(episode.start_second),
            int(episode.state_entry_second) + RESPONSE_HALF_LIFE_DESTINATION_STABLE_AGE_SECONDS,
        )
        end = int(episode.end_second)
        if end <= start:
            continue
        segments.append((start, end))
        exposure += end - start
    return segments, exposure


def _event_in_segments(event: Any, segments: Sequence[tuple[int, int]]) -> bool:
    second = _second(event)
    return second is not None and any(start <= second < end for start, end in segments)


def _carry_second(carry: Any, event_by_index: Mapping[int, Any]) -> int | None:
    for key in ("end_event_index", "start_event_index"):
        event = event_by_index.get(_int(getattr(carry, key, None)))
        if event is not None and _second(event) is not None:
            return _second(event)
    return _int(getattr(carry, "timeline_seconds", None))


def _is_penalty(event: Any) -> bool:
    return _int(getattr(event, "shot_situation", None)) == int(MatchEventShotSituation.PENALTY)


def _located_action_height(events: Sequence[Any], *, focal_team_id: str) -> list[float]:
    return [
        float(event.x) / 100
        for event in events
        if _event_provider_team(event) == focal_team_id
        and _int(getattr(event, "event_type", None)) in ATTACKING_ACTION_TYPES
        and getattr(event, "x", None) is not None
    ]


def _metric_snapshot(
    events: Sequence[Any],
    carries: Sequence[Any],
    *,
    match: Any,
    focal_team_id: int,
    segments: Sequence[tuple[int, int]],
    exposure_seconds: int,
) -> dict[str, Any]:
    focal_provider = _focal_id(match, focal_team_id)
    if not focal_provider or exposure_seconds <= 0:
        return {
            "exposure_seconds": max(0, exposure_seconds),
            "exposure_minutes": round(max(0, exposure_seconds) / 60, 4),
            "attacking": {key: None for key in ATTACKING_COMPONENTS},
            "structural": {key: None for key in STRUCTURAL_COMPONENTS},
            "counts": {},
        }
    selected_events = [
        event
        for event in events
        if not getattr(event, "is_deleted_event", False)
        and _event_provider_team(event) == focal_provider
        and _event_in_segments(event, segments)
    ]
    event_by_index = {
        int(getattr(event, "event_index", 0)): event for event in events
    }
    selected_carries = [
        carry
        for carry in carries
        if str(getattr(carry, "provider_team_id", "")) == focal_provider
        and any(
            start <= (_carry_second(carry, event_by_index) or -1) < end
            for start, end in segments
        )
        and not getattr(carry, "is_low_confidence", False)
    ]
    shots = [
        event
        for event in selected_events
        if _int(getattr(event, "event_type", None)) == MatchEventType.SHOT
        and not _is_penalty(event)
    ]
    passes = [
        event
        for event in selected_events
        if _int(getattr(event, "event_type", None)) == MatchEventType.PASS
    ]
    located_passes = [
        event
        for event in passes
        if None not in (
            getattr(event, "x", None),
            getattr(event, "y", None),
            getattr(event, "end_x", None),
            getattr(event, "end_y", None),
        )
    ]
    located_actions = [
        event
        for event in selected_events
        if _int(getattr(event, "event_type", None)) in ACTION_TYPES
        and getattr(event, "x", None) is not None
    ]
    heights = _located_action_height(selected_events, focal_team_id=focal_provider)
    defensive_heights = [
        float(event.x) / 100
        for event in selected_events
        if getattr(event, "x", None) is not None and defensive_family(event) is not None
    ]
    forward_count = lateral_count = backward_count = 0
    length_total = 0.0
    for event in located_passes:
        forward, _lateral, length = physical_vector(event)
        value = pass_direction(forward)
        forward_count += value == "forward"
        lateral_count += value == "lateral"
        backward_count += value == "backward"
        length_total += length
    located_count = len(located_passes)
    exposure_minutes = exposure_seconds / 60
    box_entries = sum(bool(getattr(event, "is_box_entry", False)) for event in passes)
    box_entries += sum(bool(getattr(carry, "is_box_entry", False)) for carry in selected_carries)
    progressive_actions = sum(bool(getattr(event, "is_progressive_pass", False)) for event in passes)
    progressive_actions += sum(bool(getattr(carry, "is_progressive_carry", False)) for carry in selected_carries)
    return {
        "exposure_seconds": exposure_seconds,
        "exposure_minutes": round(exposure_minutes, 4),
        "attacking": {
            "shots_per_minute": round(len(shots) / exposure_minutes, 6) if exposure_minutes else None,
            "box_entries_per_minute": round(box_entries / exposure_minutes, 6) if exposure_minutes else None,
            "progressive_actions_per_minute": round(progressive_actions / exposure_minutes, 6) if exposure_minutes else None,
            "action_height": round(sum(heights) / len(heights), 4) if heights else None,
        },
        "structural": {
            "forward_pass_share": round(forward_count / located_count, 6) if located_count else None,
            "pass_length_metres": round(length_total / located_count, 4) if located_count else None,
            "completion_rate": round(
                sum(getattr(event, "outcome_successful", None) is True for event in passes) / len(passes),
                6,
            ) if passes else None,
            "territory_height": round(sum(heights) / len(heights), 4) if heights else None,
            "defensive_height": round(sum(defensive_heights) / len(defensive_heights), 4) if defensive_heights else None,
        },
        "counts": {
            "events": len(selected_events),
            "shots": len(shots),
            "penalty_shots_excluded": sum(
                _int(getattr(event, "event_type", None)) == MatchEventType.SHOT and _is_penalty(event)
                for event in selected_events
            ),
            "passes": len(passes),
            "located_passes": located_count,
            "progressive_passes": sum(bool(getattr(event, "is_progressive_pass", False)) for event in passes),
            "box_entry_passes": sum(bool(getattr(event, "is_box_entry", False)) for event in passes),
            "progressive_carries": sum(bool(getattr(carry, "is_progressive_carry", False)) for carry in selected_carries),
            "box_entry_carries": sum(bool(getattr(carry, "is_box_entry", False)) for carry in selected_carries),
            "carries": len(selected_carries),
            "located_actions": len(located_actions),
            "defensive_actions": len(defensive_heights),
            "direction_counts": {
                "forward": forward_count,
                "lateral": lateral_count,
                "backward": backward_count,
            },
        },
    }


def _destination_segments(
    data: Sequence[ResponseMatchData],
    *,
    focal_team_id: int,
    state: str | None,
    phase: str | None,
    goal_difference: int | None,
) -> tuple[list[tuple[ResponseMatchData, list[tuple[int, int]]]], int]:
    result = []
    exposure = 0
    for item in data:
        segments, seconds = _stable_segments(
            item,
            focal_team_id=focal_team_id,
            state=state,
            phase=phase,
            goal_difference=goal_difference,
        )
        if segments:
            result.append((item, segments))
            exposure += seconds
    return result, exposure


def _destination(
    data: Sequence[ResponseMatchData],
    *,
    focal_team_id: int,
    concession: ResponseConcession,
) -> dict[str, Any]:
    exact, exact_exposure = _destination_segments(
        data,
        focal_team_id=focal_team_id,
        state=concession.after_state,
        phase=concession.phase,
        goal_difference=concession.after_goal_difference,
    )
    basis = "state_phase_goal_difference"
    chosen = exact
    exposure = exact_exposure

    def candidate_snapshots(candidate: Sequence[tuple[ResponseMatchData, list[tuple[int, int]]]]):
        values = [
            _metric_snapshot(
                item.events,
                item.carries,
                match=item.match,
                focal_team_id=focal_team_id,
                segments=segments,
                exposure_seconds=sum(end - start for start, end in segments),
            )
            for item, segments in candidate
        ]
        event_total = sum(value["counts"].get("events", 0) for value in values)
        pass_total = sum(value["counts"].get("passes", 0) for value in values)
        return values, event_total, pass_total

    snapshots, event_count, pass_count = candidate_snapshots(chosen)
    candidate_available = (
        exposure >= RESPONSE_HALF_LIFE_DESTINATION_MIN_EXPOSURE_SECONDS
        and event_count >= RESPONSE_HALF_LIFE_DESTINATION_MIN_EVENTS
        and pass_count >= RESPONSE_HALF_LIFE_DESTINATION_MIN_PASSES
    )
    if not candidate_available:
        relaxed, relaxed_exposure = _destination_segments(
            data,
            focal_team_id=focal_team_id,
            state=concession.after_state,
            phase=concession.phase,
            goal_difference=None,
        )
        relaxed_snapshots, relaxed_event_count, relaxed_pass_count = candidate_snapshots(relaxed)
        if (
            relaxed_exposure >= RESPONSE_HALF_LIFE_DESTINATION_MIN_EXPOSURE_SECONDS
            and relaxed_event_count >= RESPONSE_HALF_LIFE_DESTINATION_MIN_EVENTS
            and relaxed_pass_count >= RESPONSE_HALF_LIFE_DESTINATION_MIN_PASSES
        ):
            chosen, exposure, basis = relaxed, relaxed_exposure, "state_phase"
            snapshots, event_count, pass_count = relaxed_snapshots, relaxed_event_count, relaxed_pass_count
    available = (
        exposure >= RESPONSE_HALF_LIFE_DESTINATION_MIN_EXPOSURE_SECONDS
        and event_count >= RESPONSE_HALF_LIFE_DESTINATION_MIN_EVENTS
        and pass_count >= RESPONSE_HALF_LIFE_DESTINATION_MIN_PASSES
    )
    if snapshots and available:
        def weighted(metric_group: str, key: str) -> float | None:
            values = [
                (snapshot[metric_group].get(key), snapshot["exposure_seconds"])
                for snapshot in snapshots
                if snapshot[metric_group].get(key) is not None
            ]
            denominator = sum(weight for value, weight in values if value is not None)
            if not values or not denominator:
                return None
            return round(sum(value * weight for value, weight in values) / denominator, 6)

        attacking = {key: weighted("attacking", key) for key in ATTACKING_COMPONENTS}
        structural = {key: weighted("structural", key) for key in STRUCTURAL_COMPONENTS}
        counts = {
            key: sum(snapshot["counts"].get(key, 0) for snapshot in snapshots)
            for key in {
                "events",
                "shots",
                "passes",
                "located_passes",
                "progressive_passes",
                "box_entry_passes",
                "progressive_carries",
                "box_entry_carries",
                "carries",
                "located_actions",
                "defensive_actions",
            }
        }
    else:
        attacking = {key: None for key in ATTACKING_COMPONENTS}
        structural = {key: None for key in STRUCTURAL_COMPONENTS}
        counts = {"events": event_count, "passes": pass_count}
    return {
        "available": available,
        "reliability": "verified" if basis == "state_phase_goal_difference" else "partial" if available else "unavailable",
        "match_basis": basis if available else None,
        "state": concession.after_state,
        "phase": concession.phase,
        "goal_difference": concession.after_goal_difference if basis == "state_phase_goal_difference" and available else None,
        "exposure_seconds": exposure,
        "exposure_minutes": round(exposure / 60, 2),
        "match_count": len(chosen),
        "event_count": event_count,
        "pass_count": pass_count,
        "attacking": attacking,
        "structural": structural,
        "counts": counts,
        "unavailable_reason": (
            None
            if available
            else "stable destination requires 900 seconds, 10 events, and 5 passes"
        ),
    }


def _signal(
    snapshot: Mapping[str, Any],
    destination: Mapping[str, Any],
    *,
    group: str,
) -> dict[str, Any]:
    keys = ATTACKING_COMPONENTS if group == "attacking" else STRUCTURAL_COMPONENTS
    scales = ATTACKING_DEVIATION_SCALES if group == "attacking" else STRUCTURAL_DEVIATION_SCALES
    components = {}
    values = []
    for key in keys:
        observed = snapshot.get(group, {}).get(key)
        expected = destination.get(group, {}).get(key)
        scale = scales[key]
        deviation = None if observed is None or expected is None else round(abs(observed - expected), 6)
        normalized = None if deviation is None else round(deviation / scale, 6)
        components[key] = {
            "observed": observed,
            "expected": expected,
            "absolute_deviation": deviation,
            "normalised_deviation": normalized,
            "scale": scale,
        }
        if normalized is not None:
            values.append(normalized)
    return {
        "signal": round(sum(values) / len(values), 6) if values else None,
        "supported_components": len(values),
        "components": components,
        "formula": (
            "mean(abs(observed - destination) / fixed_component_scale) over supported components"
        ),
    }


def _period_for(second: int, match: Any, periods: Sequence[Any]) -> Any | None:
    return next(
        (
            period
            for period in periods
            if int(period.start_second) <= second < int(period.end_second)
        ),
        None,
    )


def _period_boundary_reason(
    concession: ResponseConcession,
    *,
    periods: Sequence[Any],
) -> str | None:
    period = _period_for(concession.second, concession, periods)
    if period is None:
        return "period_boundary"
    if int(period.end_second) - concession.second < RESPONSE_HALF_LIFE_WINDOW_SECONDS:
        return "period_boundary"
    return None


def _subsequent_goal(
    concession: ResponseConcession,
    goals: Sequence[Any],
) -> tuple[int | None, str | None]:
    later = [(_second(goal) or 0) for goal in goals if (_second(goal) or 0) > concession.second]
    if not later:
        return None, None
    second = min(later)
    gap = second - concession.second
    if gap <= RESPONSE_HALF_LIFE_RAPID_GOAL_SECONDS:
        return second, "rapid_subsequent_goal"
    if gap < RESPONSE_HALF_LIFE_WINDOW_SECONDS:
        return second, "subsequent_goal"
    return second, None


def _uncertainty_reason(
    data: ResponseMatchData,
    *,
    concession: ResponseConcession,
    end_second: int,
) -> str | None:
    for event in data.events:
        second = _second(event)
        if second is None or not concession.second <= second < end_second:
            continue
        dismissal = str(getattr(event, "dismissal_type", "none") or "none")
        if dismissal in {"red", "second_yellow"}:
            return "red_card"
        participation = str(getattr(event, "participation_action", "none") or "none")
        if participation != "none":
            return "participation_uncertainty"
    try:
        build = data.match.player_participation_build
    except (AttributeError, ObjectDoesNotExist):
        build = None
    if build is not None and str(getattr(build, "status", "")) in {"excluded", "no_lineup"}:
        return "participation_uncertainty"
    return None


def _window_segments(start: int, end: int) -> list[tuple[int, int]]:
    return [(start, end)] if end > start else []


def _windows_for_episode(
    data: ResponseMatchData,
    *,
    focal_team_id: int,
    concession: ResponseConcession,
    destination: Mapping[str, Any],
    periods: Sequence[Any],
    goals: Sequence[Any],
) -> tuple[list[dict[str, Any]], str | None]:
    period = _period_for(concession.second, data.match, periods)
    if period is None and not periods:
        episode_end = max(
            (int(getattr(row, "end_second", concession.second)) for row in data.episodes),
            default=concession.second,
        )
        period = SimpleNamespace(
            period=concession.period,
            start_second=0,
            end_second=episode_end,
        )
    if period is None:
        return [], "period_boundary"
    boundary_reason = (
        _period_boundary_reason(concession, periods=periods)
        if periods
        else (
            "period_boundary"
            if int(period.end_second) - concession.second < RESPONSE_HALF_LIFE_WINDOW_SECONDS
            else None
        )
    )
    if boundary_reason:
        return [], boundary_reason
    next_goal_second, next_goal_reason = _subsequent_goal(concession, goals)
    first_end = concession.second + RESPONSE_HALF_LIFE_WINDOW_SECONDS
    if next_goal_second is not None and next_goal_second < first_end:
        return [], next_goal_reason or "subsequent_goal"
    windows = []
    max_start = min(
        concession.second + RESPONSE_HALF_LIFE_HORIZON_SECONDS - RESPONSE_HALF_LIFE_WINDOW_SECONDS,
        int(period.end_second) - RESPONSE_HALF_LIFE_WINDOW_SECONDS,
    )
    if max_start < concession.second:
        return [], "period_boundary"
    start = concession.second
    while start <= max_start and len(windows) < RESPONSE_HALF_LIFE_WINDOW_LIMIT:
        end = start + RESPONSE_HALF_LIFE_WINDOW_SECONDS
        censor_reason = None
        if next_goal_second is not None and start < next_goal_second < end:
            censor_reason = "rapid_subsequent_goal" if next_goal_reason == "rapid_subsequent_goal" else "subsequent_goal"
        uncertainty = _uncertainty_reason(data, concession=concession, end_second=end)
        if uncertainty:
            censor_reason = uncertainty
        snapshot = _metric_snapshot(
            data.events,
            data.carries,
            match=data.match,
            focal_team_id=focal_team_id,
            segments=_window_segments(start, end),
            exposure_seconds=end - start,
        )
        attacking = _signal(snapshot, destination, group="attacking") if not censor_reason and destination["available"] else None
        structural = _signal(snapshot, destination, group="structural") if not censor_reason and destination["available"] else None
        windows.append(
            {
                "index": len(windows),
                "offset_seconds": start - concession.second,
                "start_second": start,
                "end_second": end,
                "duration_seconds": end - start,
                "phase": {
                    int(MatchEventPeriod.FIRST_HALF): MatchStatePhase.FIRST_HALF,
                    int(MatchEventPeriod.SECOND_HALF): MatchStatePhase.SECOND_HALF,
                    int(MatchEventPeriod.FIRST_EXTRA_TIME): MatchStatePhase.FIRST_EXTRA_TIME,
                    int(MatchEventPeriod.SECOND_EXTRA_TIME): MatchStatePhase.SECOND_EXTRA_TIME,
                }.get(int(getattr(period, "period", 0)), concession.phase),
                "is_added_time": bool(
                    end > int(getattr(period, "start_second", 0))
                    + (
                        45 * 60
                        if int(getattr(period, "period", 0)) in {1, 2}
                        else 15 * 60
                    )
                ),
                "complete": censor_reason is None and destination["available"],
                "censored": censor_reason is not None or not destination["available"],
                "censor_reason": censor_reason or (None if destination["available"] else "no_destination"),
                "snapshot": snapshot,
                "attacking": attacking,
                "structural": structural,
            }
        )
        start += RESPONSE_HALF_LIFE_STEP_SECONDS
    # A dismissal/substitution in the initial five-minute response means the
    # concession cannot identify a clean response episode.  Later changes are
    # retained as window-level censoring so the earlier trace remains useful.
    initial_reason = windows[0]["censor_reason"] if windows else None
    return windows, initial_reason


def _half_life(windows: Sequence[Mapping[str, Any]], group: str) -> dict[str, Any]:
    supported = [
        window
        for window in windows
        if not window.get("censored") and window.get(group) and window[group].get("signal") is not None
    ]
    if not supported:
        return {
            "initial_deviation": None,
            "half_threshold": None,
            "half_life_seconds": None,
            "recovered": False,
            "supported_window_count": 0,
            "status": "unavailable",
        }
    initial = float(supported[0][group]["signal"])
    threshold = initial / 2
    recovered = next(
        (
            window
            for window in supported[1:]
            if float(window[group]["signal"]) <= threshold
        ),
        None,
    )
    return {
        "initial_deviation": round(initial, 6),
        "half_threshold": round(threshold, 6),
        "half_life_seconds": (
            int(recovered["offset_seconds"]) if recovered is not None else 0 if initial == 0 else None
        ),
        "recovered": recovered is not None or initial == 0,
        "supported_window_count": len(supported),
        "status": "recovered" if recovered is not None or initial == 0 else "no_recovery",
    }


def _aggregate(values: Sequence[float | None]) -> dict[str, Any]:
    available = [value for value in values if value is not None]
    return {
        "sample_size": len(available),
        "mean_seconds": round(sum(available) / len(available), 2) if available else None,
        "median_seconds": round(float(median(available)), 2) if available else None,
        "values_seconds": [round(value, 2) for value in available],
    }


def _reliability(
    *,
    qualifying_concessions: int,
    qualifying_windows: int,
    matches: int,
    destinations_available: int,
    censored: int,
    recoveries: int,
) -> tuple[str, str | None]:
    if not qualifying_concessions or not qualifying_windows or not destinations_available:
        return "unavailable", "insufficient qualifying concessions, windows, or stable destinations"
    if qualifying_concessions < 3 or qualifying_windows < 3:
        return "sparse", "fewer than three qualifying concessions or windows"
    if censored or recoveries < qualifying_concessions:
        return "partial", "one or more concessions are censored or have no observed recovery"
    if matches < 2:
        return "partial", "only one qualifying match"
    return "verified", None


def _episode_public(
    concession: ResponseConcession,
    *,
    destination: Mapping[str, Any],
    windows: Sequence[Mapping[str, Any]],
    censor_reason: str | None,
) -> dict[str, Any]:
    focal_score_before, opponent_score_before = concession.before_score
    focal_score_after, opponent_score_after = concession.after_score
    first_window = windows[0] if windows else None
    return {
        "match_ref": concession.match_ref,
        "provider_match_id": concession.provider_match_id,
        "event_index": concession.event_index,
        "concession_second": concession.second,
        "period": concession.period,
        "phase": concession.phase,
        "score": {
            "before": {
                "focal_goal_difference": concession.before_goal_difference,
                "focal_score": focal_score_before,
                "opponent_score": opponent_score_before,
            },
            "after": {
                "focal_goal_difference": concession.after_goal_difference,
                "focal_score": focal_score_after,
                "opponent_score": opponent_score_after,
            },
        },
        "state": {
            "before": concession.before_state,
            "after": concession.after_state,
            "draw_provenance": concession.draw_provenance,
        },
        "destination": destination,
        "first_five_minute_response": {
            "available": bool(first_window and first_window["complete"]),
            "censor_reason": first_window["censor_reason"] if first_window else censor_reason,
            "snapshot": first_window["snapshot"] if first_window else None,
            "attacking": first_window["attacking"] if first_window else None,
            "structural": first_window["structural"] if first_window else None,
        },
        "qualifies": censor_reason is None and destination["available"] and bool(windows),
        "censored": censor_reason is not None or not destination["available"],
        "censor_reason": censor_reason or (None if destination["available"] else "no_destination"),
        "attacking": _half_life(windows, "attacking"),
        "structural": _half_life(windows, "structural"),
        "windows": list(windows),
    }


def build_response_half_life_cohort(
    *,
    focal_team_id: int,
    matches: Sequence[ResponseMatchData],
    destination_matches: Sequence[ResponseMatchData] | None = None,
    scope: StateLensScope | Mapping[str, Any] | None = None,
    periods_by_match: Mapping[int, Sequence[Any]] | None = None,
    match_refs: Mapping[int, int] | None = None,
) -> dict[str, Any]:
    """Build one selected or baseline response cohort.

    ``matches`` are the concessions included in this view.  Destinations are
    normally calculated from all season matches, supplied separately, so a
    single-match trace can still be compared with an established destination.
    """

    destination_matches = destination_matches or matches
    match_refs = match_refs or {}
    periods_by_match = periods_by_match or {}
    concessions: list[ResponseConcession] = []
    all_goals_by_match: dict[int, list[Any]] = {}
    uncertain_event_count = 0
    for item in matches:
        ref = match_refs.get(int(getattr(item.match, "id", getattr(item.match, "pk", 0))))
        uncertain_event_count += uncertain_concession_event_count(
            item,
            focal_team_id=focal_team_id,
        )
        concessions.extend(
            find_concessions(item, focal_team_id=focal_team_id, match_ref=ref)
        )
        all_goals_by_match[int(getattr(item.match, "id", getattr(item.match, "pk", 0)))] = valid_goal_events(item)
    concessions = [concession for concession in concessions if _scope_matches(concession, scope)]
    data_by_match = {
        int(getattr(item.match, "id", getattr(item.match, "pk", 0))): item
        for item in destination_matches
    }
    trace_rows = []
    censor_reasons = Counter()
    if uncertain_event_count:
        censor_reasons["uncertain_timestamp"] += uncertain_event_count
    destination_count = 0
    qualifying_concession_count = 0
    qualifying_window_count = 0
    qualifying_match_ids: set[int] = set()
    attacking_values = []
    structural_values = []
    attacking_recovered = 0
    structural_recovered = 0
    for concession in sorted(
        concessions,
        key=lambda row: (row.provider_match_id, row.second, row.event_index),
    ):
        destination = _destination(
            list(data_by_match.values()),
            focal_team_id=focal_team_id,
            concession=concession,
        )
        if destination["available"]:
            destination_count += 1
        item = next(
            (value for value in matches if int(getattr(value.match, "id", getattr(value.match, "pk", 0))) == concession.provider_match_id),
            None,
        )
        if item is None:
            reason = "state_evidence_missing"
            windows = []
        else:
            goals = all_goals_by_match.get(concession.provider_match_id, [])
            periods = periods_by_match.get(concession.provider_match_id, ())
            windows, reason = _windows_for_episode(
                item,
                focal_team_id=focal_team_id,
                concession=concession,
                destination=destination,
                periods=periods,
                goals=goals,
            )
        if not destination["available"] and reason is None:
            reason = "no_destination"
        episode = _episode_public(
            concession,
            destination=destination,
            windows=windows,
            censor_reason=reason,
        )
        episode["attacking"] = _half_life(windows, "attacking")
        episode["structural"] = _half_life(windows, "structural")
        if episode["qualifies"]:
            qualifying_concession_count += 1
            qualifying_window_count += sum(not window["censored"] for window in windows)
            qualifying_match_ids.add(concession.provider_match_id)
            attacking_values.append(episode["attacking"]["half_life_seconds"])
            structural_values.append(episode["structural"]["half_life_seconds"])
            attacking_recovered += bool(episode["attacking"]["recovered"])
            structural_recovered += bool(episode["structural"]["recovered"])
        if episode["censored"]:
            censor_reasons[episode["censor_reason"] or "unknown"] += 1
        trace_rows.append(episode)
    reliability, reliability_note = _reliability(
        qualifying_concessions=qualifying_concession_count,
        qualifying_windows=qualifying_window_count,
        matches=len(qualifying_match_ids),
        destinations_available=destination_count,
        censored=sum(censor_reasons.values()),
        recoveries=min(attacking_recovered, structural_recovered),
    )
    return {
        "available": reliability != "unavailable",
        "reliability": reliability,
        "reliability_note": reliability_note,
        "qualifying_concessions": qualifying_concession_count,
        "qualifying_windows": qualifying_window_count,
        "qualifying_matches": len(qualifying_match_ids),
        "destination_available_concessions": destination_count,
        "censored_episodes": sum(censor_reasons.values()),
        "uncertain_concession_events": uncertain_event_count,
        "censor_reasons": dict(sorted(censor_reasons.items())),
        "episode_count": len(trace_rows),
        "trace_limit": RESPONSE_HALF_LIFE_TRACE_LIMIT,
        "trace_truncated": len(trace_rows) > RESPONSE_HALF_LIFE_TRACE_LIMIT,
        "attacking": {
            "half_life_seconds": _aggregate(attacking_values),
            "recovered_concessions": attacking_recovered,
            "formula": "mean(abs(observed - destination) / fixed component scale) across shot, box-entry, progressive-action, and action-height components",
        },
        "structural": {
            "half_life_seconds": _aggregate(structural_values),
            "recovered_concessions": structural_recovered,
            "formula": "mean(abs(observed - destination) / fixed component scale) across direction, length, completion, territory, and defensive-height components",
        },
        "episodes": trace_rows[:RESPONSE_HALF_LIFE_TRACE_LIMIT],
    }


def response_half_life_definitions() -> dict[str, Any]:
    """Return the public, versioned window/formula contract."""

    return {
        "formula_version": RESPONSE_HALF_LIFE_FORMULA_VERSION,
        "window_seconds": RESPONSE_HALF_LIFE_WINDOW_SECONDS,
        "step_seconds": RESPONSE_HALF_LIFE_STEP_SECONDS,
        "overlap_seconds": RESPONSE_HALF_LIFE_WINDOW_SECONDS - RESPONSE_HALF_LIFE_STEP_SECONDS,
        "horizon_seconds": RESPONSE_HALF_LIFE_HORIZON_SECONDS,
        "interval_boundary": "half_open_[start,end)",
        "period_boundary": "windows must fit wholly inside one played period; a concession with less than five minutes remaining is censored",
        "added_time": "included only when a complete window remains inside the persisted played period; is_added_time is exposed per window",
        "extra_time": "periods 3 and 4 use the same rules and remain phase-matched destinations",
        "subsequent_goal": "a subsequent goal in the first five minutes censors the concession; later rolling windows crossing a subsequent goal are censored",
        "rapid_subsequent_goal_seconds": RESPONSE_HALF_LIFE_RAPID_GOAL_SECONDS,
        "red_card": "windows containing a red or second-yellow dismissal are censored",
        "participation_uncertainty": "windows containing normalized substitution/retirement evidence or an explicitly excluded participation build are censored",
        "destination": {
            "stable_age_seconds": RESPONSE_HALF_LIFE_DESTINATION_STABLE_AGE_SECONDS,
            "minimum_exposure_seconds": RESPONSE_HALF_LIFE_DESTINATION_MIN_EXPOSURE_SECONDS,
            "minimum_events": RESPONSE_HALF_LIFE_DESTINATION_MIN_EVENTS,
            "minimum_passes": RESPONSE_HALF_LIFE_DESTINATION_MIN_PASSES,
            "priority": "resulting_state + phase + goal_difference, then resulting_state + phase when the exact cell lacks stable evidence",
        },
        "attacking_components": list(ATTACKING_COMPONENTS),
        "structural_components": list(STRUCTURAL_COMPONENTS),
        "attacking_scales": dict(ATTACKING_DEVIATION_SCALES),
        "structural_scales": dict(STRUCTURAL_DEVIATION_SCALES),
        "half_life": "first later supported rolling window with signal <= initial_deviation / 2; zero initial deviation has zero half-life; no crossing is no_recovery",
        "censor_reasons": [
            "period_boundary",
            "subsequent_goal",
            "rapid_subsequent_goal",
            "red_card",
            "participation_uncertainty",
            "no_destination",
            "state_evidence_missing",
        ],
    }


def build_response_half_life_payload(
    *,
    canonical_team_id: int,
    canonical_team_name: str,
    competition_season: int,
    competition_code: str,
    season_label: str,
    selected: dict[str, Any],
    baseline: dict[str, Any] | None,
    state_lens: Mapping[str, Any],
    matches: Sequence[Mapping[str, Any]],
    selected_match_ref: int | None,
) -> dict[str, Any]:
    return {
        "contract_version": "response_half_life_api_v1",
        "formula_version": RESPONSE_HALF_LIFE_FORMULA_VERSION,
        "canonical_team_id": canonical_team_id,
        "canonical_team_name": canonical_team_name,
        "competition_season": competition_season,
        "competition_code": competition_code,
        "season_label": season_label,
        "selected_match_ref": selected_match_ref,
        "matches": list(matches),
        "definitions": response_half_life_definitions(),
        "state_lens": dict(state_lens),
        "selected": selected,
        "baseline": baseline,
        "comparison": {
            "enabled": baseline is not None,
            "baseline": baseline,
            "note": "Attacking and structural half-lives are reported as separate descriptive aggregates; no composite score or causal interpretation is formed.",
        },
        "notes": [
            "A concession is a valid opponent-scored goal in the focal team's supported played timeline.",
            "Destination behavior is matched to the resulting state, phase, and goal difference when stable evidence permits; relaxed state+phase matching is labelled partial.",
            "Rates use the fixed five-minute window duration, while destination rates use stable verified exposure seconds.",
            "Observed action height is a normalized acting-team frame; it is not a pressing or block label.",
            "No half-life is displayed when the destination or qualifying window evidence is unavailable.",
        ],
    }
