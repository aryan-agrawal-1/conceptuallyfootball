"""Versioned, provider-neutral possession and transition-context derivation.

The algorithm consumes only the ordered normalized event contract. Provider
qualifiers are used solely for the separately labelled observed fast-break
shot count; they never determine derived counter status.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from hashlib import sha256
from typing import Any, Sequence

from django.db import transaction
from django.utils import timezone

from ingestion.models import (
    MatchEventShotOutcome,
    MatchEventShotSituation,
    MatchEventType,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchPossession,
    ProviderMatchPossessionBuild,
    ProviderMatchPossessionEvent,
    ProviderMatchPossessionParticipant,
)

POSSESSION_CALCULATION_VERSION = "possession_context_v1"
SETTLED_SECONDS = 10
SETTLED_CONTROL_ACTIONS = 3
COUNTER_WINDOW_SECONDS = 12
COUNTER_MAX_START_X = 6000
COUNTER_MIN_FORWARD_UNITS = 2000
FINAL_THIRD_X = 6667
BOX_X = 8350
BOX_Y_MIN = 2118
BOX_Y_MAX = 7882
X_METRES_PER_UNIT = 105.0 / 10_000

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
        MatchEventType.SAVE,
    }
)
ACQUISITION_TYPES = frozenset(
    {
        MatchEventType.BALL_RECOVERY,
        MatchEventType.TACKLE,
        MatchEventType.INTERCEPTION,
        MatchEventType.SAVE,
    }
)
DEFENSIVE_TYPES = frozenset(
    {
        MatchEventType.TACKLE,
        MatchEventType.INTERCEPTION,
        MatchEventType.CLEARANCE,
        MatchEventType.BLOCKED_PASS,
        MatchEventType.CHALLENGE,
        MatchEventType.AERIAL,
    }
)
EXCLUDED_TYPES = frozenset(
    {
        MatchEventType.CARD,
        MatchEventType.SUBSTITUTION,
        MatchEventType.ADMINISTRATIVE,
    }
)


@dataclass
class PossessionSpec:
    provider_team_id: str
    team_id: int | None
    period: int
    events: list[ProviderMatchEvent] = field(default_factory=list)
    control_event_indexes: set[int] = field(default_factory=set)
    launch_type: str = "continued_control"
    termination_reason: str = "period_end"
    ambiguous: bool = False


@dataclass(frozen=True)
class DerivationResult:
    possessions: tuple[PossessionSpec, ...]
    excluded: tuple[dict[str, Any], ...]


def event_second(event: ProviderMatchEvent) -> int:
    return int(event.timeline_seconds if event.timeline_seconds is not None else event.match_seconds or 0)


def event_location(event: ProviderMatchEvent, *, end: bool = False) -> tuple[int | None, int | None]:
    if (
        end
        and event.event_type == MatchEventType.PASS
        and event.end_x is not None
        and event.end_y is not None
    ):
        return event.end_x, event.end_y
    return event.x, event.y


def forward_location(event: ProviderMatchEvent) -> tuple[int | None, int | None]:
    return event_location(event, end=True)


def is_restart(event: ProviderMatchEvent) -> bool:
    return bool(event.is_set_piece or event.is_throw_in or event.is_corner or event.is_free_kick)


def grants_control(event: ProviderMatchEvent) -> bool:
    if event.event_type not in CONTROL_TYPES or event.is_deleted_event:
        return False
    if event.event_type in {MatchEventType.TACKLE, MatchEventType.INTERCEPTION, MatchEventType.SAVE}:
        return event.outcome_successful is not False
    if event.event_type == MatchEventType.CLEARANCE:
        return False
    return True


def closes_possession(event: ProviderMatchEvent) -> str | None:
    if event.event_type in {MatchEventType.SHOT, MatchEventType.OWN_GOAL}:
        return "goal" if (
            event.event_type == MatchEventType.OWN_GOAL
            or event.shot_outcome == MatchEventShotOutcome.GOAL
        ) else "shot"
    if event.event_type == MatchEventType.OFFSIDE:
        return "offside"
    if event.event_type == MatchEventType.FOUL:
        return "foul"
    if event.event_type == MatchEventType.DISPOSSESSED:
        return "turnover"
    if event.event_type == MatchEventType.PASS and event.outcome_successful is False:
        return "out_of_play_or_turnover"
    return None


def derive_possessions(events: Sequence[ProviderMatchEvent]) -> DerivationResult:
    ordered = sorted(events, key=lambda event: (event.period, event_second(event), event.event_index))
    possessions: list[PossessionSpec] = []
    excluded: list[dict[str, Any]] = []
    current: PossessionSpec | None = None
    previous_period: int | None = None
    last_control_team: str | None = None
    last_termination: str | None = None

    def finish(reason: str) -> None:
        nonlocal current, last_control_team, last_termination
        if current is not None:
            current.termination_reason = reason
            possessions.append(current)
            last_control_team = current.provider_team_id
            last_termination = reason
            current = None

    for event in ordered:
        if previous_period is not None and event.period != previous_period:
            finish("period_end")
        previous_period = event.period
        if event.is_deleted_event or event.event_type in EXCLUDED_TYPES:
            excluded.append({"event_index": event.event_index, "reason": "non_play_event"})
            continue
        if event.event_type == MatchEventType.UNKNOWN or not event.provider_team_id:
            excluded.append({"event_index": event.event_index, "reason": "ambiguous_control"})
            if current is not None:
                current.ambiguous = True
            continue

        control = grants_control(event)
        restart = is_restart(event)
        if restart:
            finish("restart")
        if control and (current is None or event.provider_team_id != current.provider_team_id):
            prior = current
            finish("control_change")
            launch = "restart" if restart else (
                "turnover_recovery" if event.event_type in ACQUISITION_TYPES else
                "opponent_control_change" if (
                    prior is not None
                    or last_termination == "turnover"
                    and last_control_team != event.provider_team_id
                ) else "period_start"
            )
            current = PossessionSpec(
                provider_team_id=event.provider_team_id,
                team_id=event.team_id,
                period=event.period,
                launch_type=launch,
            )
        if current is None:
            excluded.append({"event_index": event.event_index, "reason": "no_control_anchor"})
            continue
        current.events.append(event)
        if control and event.provider_team_id == current.provider_team_id:
            current.control_event_indexes.add(event.event_index)
        if reason := closes_possession(event):
            finish(reason)
    finish("period_end")
    return DerivationResult(tuple(possessions), tuple(excluded))


def block_height(average_x: int | None) -> str | None:
    if average_x is None:
        return None
    if average_x >= FINAL_THIRD_X:
        return "high"
    if average_x >= 3333:
        return "mid"
    return "low"


def shot_outcome_label(event: ProviderMatchEvent) -> str:
    return {
        MatchEventShotOutcome.GOAL: "goal",
        MatchEventShotOutcome.SAVED: "saved",
        MatchEventShotOutcome.BLOCKED: "blocked",
        MatchEventShotOutcome.OFF_TARGET: "off_target",
        MatchEventShotOutcome.WOODWORK: "woodwork",
    }.get(event.shot_outcome, "unknown")


def state_segments(provider_match: ProviderMatch, spec: PossessionSpec) -> list[dict[str, Any]]:
    start = event_second(spec.events[0])
    end = event_second(spec.events[-1])
    # Episodes are [start,end). A goal at the terminal timestamp belongs to the
    # score state before that event and must not inherit the post-goal episode.
    terminal = spec.events[-1]
    goal_end = spec.termination_reason == "goal"
    rows = list(
        provider_match.team_game_state_episodes.filter(
            focal_team_id=spec.team_id,
            end_second__gt=start,
            start_second__lt=end if end > start else start + 1,
        ).order_by("start_second")
    ) if spec.team_id else []
    segments = []
    for row in rows:
        segment_start, segment_end = max(start, row.start_second), min(end, row.end_second)
        if segment_end > segment_start:
            segments.append(
                {
                    "start_second": segment_start,
                    "end_second": segment_end,
                    "duration_seconds": segment_end - segment_start,
                    "state": row.get_state_display().lower(),
                    "goal_difference": row.goal_difference,
                }
            )
    if not segments or goal_end:
        state = terminal.game_state_before
        if state is not None and (not segments or end == start):
            segments.append(
                {
                    "start_second": start,
                    "end_second": end,
                    "duration_seconds": max(0, end - start),
                    "state": terminal.get_game_state_before_display().lower(),
                    "goal_difference": None,
                }
            )
    return segments


def possession_values(provider_match: ProviderMatch, spec: PossessionSpec, index: int) -> dict[str, Any]:
    start_event, end_event = spec.events[0], spec.events[-1]
    start_second, end_second = event_second(start_event), event_second(end_event)
    controls = [event for event in spec.events if event.event_index in spec.control_event_indexes]
    establishment_event = next(
        (
            event for action_number, event in enumerate(controls, start=1)
            if action_number >= SETTLED_CONTROL_ACTIONS or event_second(event) - start_second >= SETTLED_SECONDS
        ),
        None,
    )
    establishment_second = event_second(establishment_event) if establishment_event else None
    settled_defensive = [
        event for event in spec.events
        if establishment_second is not None
        and event.event_index > establishment_event.event_index
        and event.provider_team_id != spec.provider_team_id
        and event.event_type in DEFENSIVE_TYPES
        and event.x is not None
    ]
    average_defensive_x = (
        round(sum(event.x for event in settled_defensive) / len(settled_defensive))
        if settled_defensive else None
    )
    sx, sy = event_location(start_event)
    ex, ey = event_location(end_event, end=True)
    is_counter_launch = (
        spec.launch_type in {"turnover_recovery", "opponent_control_change"}
        and not is_restart(start_event)
        and sx is not None
        and sx <= COUNTER_MAX_START_X
    )
    counter_events = (
        [
            event
            for event in controls
            if event_second(event) - start_second <= COUNTER_WINDOW_SECONDS
        ]
        if is_counter_launch
        else []
    )
    counter_locations = [
        (event, *forward_location(event)) for event in counter_events
    ]
    final_arrivals = [
        event for event, x, _ in counter_locations if (x or 0) >= FINAL_THIRD_X
    ]
    box_arrivals = [
        event
        for event, x, y in counter_locations
        if (x or 0) >= BOX_X
        and BOX_Y_MIN <= (y if y is not None else -1) <= BOX_Y_MAX
    ]
    shots = [event for event in counter_events if event.event_type == MatchEventType.SHOT]
    furthest_x = max([sx or 0] + [(x or 0) for _, x, _ in counter_locations])
    forward_units = max(0, furthest_x - (sx or furthest_x))
    qualifies = is_counter_launch and forward_units >= COUNTER_MIN_FORWARD_UNITS
    elapsed = max((event_second(event) - start_second for event in counter_events), default=0)
    outcome = (
        shot_outcome_label(shots[-1]) if shots else
        "box_arrival" if box_arrivals else "final_third_arrival" if final_arrivals else "no_progress"
    ) if is_counter_launch else None
    identity_seed = f"{POSSESSION_CALCULATION_VERSION}:{provider_match.provider_match_id}:{spec.period}:{start_event.event_index}:{spec.provider_team_id}"
    return {
        "possession_index": index,
        "identity": sha256(identity_seed.encode()).hexdigest()[:40],
        "provider_team_id": spec.provider_team_id,
        "team_id": spec.team_id,
        "period": spec.period,
        "start_second": start_second,
        "end_second": end_second,
        "duration_seconds": max(0, end_second - start_second),
        "start_x": sx,
        "start_y": sy,
        "end_x": ex,
        "end_y": ey,
        "action_count": len(controls),
        "termination_reason": spec.termination_reason,
        "launch_type": spec.launch_type,
        "is_ambiguous": spec.ambiguous,
        "exclusion_reason": "ambiguous_interstitial_event" if spec.ambiguous else None,
        "establishment_second": establishment_second,
        "establishment_event_index": (
            establishment_event.event_index if establishment_event else None
        ),
        "is_settled": establishment_second is not None,
        "is_counter_launch": is_counter_launch,
        "counter_final_third_arrival": qualifies and bool(final_arrivals),
        "counter_box_arrival": qualifies and bool(box_arrivals),
        "counter_shot": qualifies and bool(shots),
        "counter_outcome": outcome,
        "counter_elapsed_seconds": elapsed if is_counter_launch else None,
        "counter_forward_metres": Decimal(str(round(forward_units * X_METRES_PER_UNIT, 2))) if is_counter_launch else None,
        "counter_speed_mps": Decimal(str(round(forward_units * X_METRES_PER_UNIT / elapsed, 2))) if is_counter_launch and elapsed else None,
        "provider_fast_break_shot_count": sum(
            event.event_type == MatchEventType.SHOT and event.shot_situation == MatchEventShotSituation.FAST_BREAK
            for event in spec.events
        ),
        "settled_defensive_action_count": len(settled_defensive),
        "settled_defensive_average_x": average_defensive_x,
        "settled_block_height": block_height(average_defensive_x),
        "state_segments": state_segments(provider_match, spec),
        "diagnostics": {"qualifies_counter_progress": qualifies},
    }


def replace_match_possessions(provider_match: ProviderMatch) -> int:
    """Atomically replace only this match's possession-context outputs."""
    events = list(provider_match.events.select_related("team", "player").all())
    result = derive_possessions(events)
    ambiguous = sum(item["reason"] == "ambiguous_control" for item in result.excluded)
    reason_counts = dict(Counter(item["reason"] for item in result.excluded))
    source_checksum = getattr(getattr(provider_match, "payload", None), "payload_sha256", "")
    with transaction.atomic():
        ProviderMatchPossessionBuild.objects.filter(provider_match=provider_match).delete()
        build = ProviderMatchPossessionBuild.objects.create(
            provider_match=provider_match,
            calculation_version=POSSESSION_CALCULATION_VERSION,
            source_checksum=source_checksum,
            possession_count=len(result.possessions),
            included_event_count=sum(len(spec.events) for spec in result.possessions),
            excluded_event_count=len(result.excluded),
            ambiguous_event_count=ambiguous,
            diagnostics={"excluded_by_reason": reason_counts, "excluded_events": list(result.excluded)},
            calculated_at=timezone.now(),
        )
        for index, spec in enumerate(result.possessions):
            possession = ProviderMatchPossession.objects.create(
                build=build,
                provider_match=provider_match,
                **possession_values(provider_match, spec, index),
            )
            ProviderMatchPossessionEvent.objects.bulk_create(
                [
                    ProviderMatchPossessionEvent(
                        possession=possession,
                        event=event,
                        sequence=sequence,
                        is_control_action=event.event_index in spec.control_event_indexes,
                        is_settled_defensive_action=(
                            possession.establishment_second is not None
                            and event.event_index > possession.establishment_event_index
                            and event.provider_team_id != spec.provider_team_id
                            and event.event_type in DEFENSIVE_TYPES
                        ),
                    )
                    for sequence, event in enumerate(spec.events)
                ]
            )
            participants = {}
            for event in spec.events:
                if (
                    event.event_index not in spec.control_event_indexes
                    or not event.provider_player_id
                ):
                    continue
                participant = participants.setdefault(
                    event.provider_player_id,
                    {
                        "player_id": event.player_id,
                        "first_event_index": event.event_index,
                        "action_count": 0,
                    },
                )
                participant["player_id"] = event.player_id
                participant["first_event_index"] = min(
                    participant["first_event_index"], event.event_index
                )
                participant["action_count"] += 1
            ProviderMatchPossessionParticipant.objects.bulk_create(
                [
                    ProviderMatchPossessionParticipant(
                        possession=possession,
                        provider_player_id=provider_player_id,
                        **values,
                    )
                    for provider_player_id, values in participants.items()
                ]
            )
    return len(result.possessions)


def public_possession_thresholds() -> dict[str, Any]:
    return {
        "calculation_version": POSSESSION_CALCULATION_VERSION,
        "settled_seconds": SETTLED_SECONDS,
        "settled_control_actions": SETTLED_CONTROL_ACTIONS,
        "counter_window_seconds": COUNTER_WINDOW_SECONDS,
        "counter_max_start_x": COUNTER_MAX_START_X / 100,
        "counter_min_forward_metres": COUNTER_MIN_FORWARD_UNITS * X_METRES_PER_UNIT,
        "final_third_x": FINAL_THIRD_X / 100,
        "box": {"x_min": BOX_X / 100, "y_min": BOX_Y_MIN / 100, "y_max": BOX_Y_MAX / 100},
        "block_height_x": {"low_below": 33.33, "high_from": 66.67},
    }
