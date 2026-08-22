"""Derive SPADL-style carries from the normalized Opta/WhoScored event stream.

Carries bridge a reliable possession origin to the carrier's next located
action during an uninterrupted phase of play. Completed passes may hand the
ball to another player; every other origin must belong to the eventual carrier.
Derived rows are rebuilt whenever a match's source events are replaced and
remain separate from ``ProviderMatchEvent`` so they cannot alter event counts.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from django.db import transaction

from ingestion.models import (
    MatchEventBodyPart,
    MatchEventType,
    ProviderMatch,
    ProviderMatchCarry,
    ProviderMatchEvent,
)
from ingestion.services.whoscored_normalization import (
    box_entry,
    final_third_entry,
    progressive_action,
)

# Scaled coordinates span 0..10000 for a 105m x 68m pitch, so one int unit is
# 1.05cm along x and 0.68cm across y.
X_METRES_PER_UNIT = 105.0 / 10_000
Y_METRES_PER_UNIT = 68.0 / 10_000

MIN_CARRY_METRES = 3.0
MAX_CARRY_METRES = 60.0
MAX_CARRY_SECONDS = 10
MAX_ONE_SECOND_ACQUISITION_METRES = 6.0

CARRY_ACQUISITION_EVENT_TYPES = frozenset(
    {
        MatchEventType.BALL_RECOVERY,
        MatchEventType.SAVE,
        MatchEventType.TACKLE,
        MatchEventType.INTERCEPTION,
    }
)
CARRY_CONTROL_EVENT_TYPES = frozenset(
    {
        MatchEventType.BALL_TOUCH,
        MatchEventType.TAKE_ON,
    }
)
CARRY_END_EVENT_TYPES = frozenset(
    {
        MatchEventType.PASS,
        MatchEventType.BALL_TOUCH,
        MatchEventType.TAKE_ON,
        MatchEventType.SHOT,
    }
)
CARRY_ANCHOR_EVENT_TYPES = frozenset(
    {MatchEventType.PASS}
    | CARRY_ACQUISITION_EVENT_TYPES
    | CARRY_CONTROL_EVENT_TYPES
    | CARRY_END_EVENT_TYPES
)
CARRY_BREAK_EVENT_TYPES = frozenset(
    {
        MatchEventType.AERIAL,
        MatchEventType.CHALLENGE,
        MatchEventType.CLEARANCE,
        MatchEventType.BLOCKED_PASS,
        MatchEventType.DISPOSSESSED,
        MatchEventType.FOUL,
        MatchEventType.OFFSIDE,
        MatchEventType.SUBSTITUTION,
        MatchEventType.ADMINISTRATIVE,
        MatchEventType.OWN_GOAL,
    }
)


@dataclass(frozen=True)
class CarrySegment:
    start_event_index: int
    end_event_index: int
    provider_team_id: str
    team_id: int | None
    provider_player_id: str | None
    player_id: int | None
    period: int
    minute: int
    second: int
    match_seconds: int | None
    x: int
    y: int
    end_x: int
    end_y: int
    is_progressive_carry: bool
    is_final_third_entry: bool
    is_box_entry: bool
    is_low_confidence: bool


def located_carry_anchor(event: ProviderMatchEvent) -> bool:
    return (
        event.event_type in CARRY_ANCHOR_EVENT_TYPES
        and event.x is not None
        and event.y is not None
    )


def carry_start_position(
    previous: ProviderMatchEvent,
    event: ProviderMatchEvent,
) -> tuple[int, int] | None:
    """Return a reliable possession origin for the player making ``event``."""
    if (
        previous.event_type == MatchEventType.PASS
        and previous.outcome_successful is True
        and previous.end_x is not None
        and previous.end_y is not None
    ):
        return previous.end_x, previous.end_y
    same_player = (
        previous.provider_player_id is not None
        and previous.provider_player_id == event.provider_player_id
    )
    if (
        same_player
        and previous.outcome_successful is True
        and previous.event_type in CARRY_ACQUISITION_EVENT_TYPES | CARRY_CONTROL_EVENT_TYPES
    ):
        return previous.x, previous.y
    return None


def valid_carry_end(event: ProviderMatchEvent) -> bool:
    if event.event_type not in CARRY_END_EVENT_TYPES:
        return False
    if event.is_set_piece or event.is_throw_in or event.is_corner or event.is_free_kick:
        return False
    return not (
        event.event_type == MatchEventType.SHOT
        and event.body_part == MatchEventBodyPart.HEAD
    )


def phase_interrupted(events: Sequence[ProviderMatchEvent]) -> bool:
    """Whether filtered-out events make the inferred movement unreliable."""
    return any(
        event.event_type in CARRY_BREAK_EVENT_TYPES
        or event.event_type in CARRY_ANCHOR_EVENT_TYPES
        or event.is_set_piece
        or event.is_throw_in
        or event.is_corner
        or event.is_free_kick
        or event.is_touch
        for event in events
    )


def carry_distance_metres(start: tuple[int, int], end: tuple[int, int]) -> float:
    delta_x = (end[0] - start[0]) * X_METRES_PER_UNIT
    delta_y = (end[1] - start[1]) * Y_METRES_PER_UNIT
    return (delta_x * delta_x + delta_y * delta_y) ** 0.5


def derive_carries(events: Sequence[ProviderMatchEvent]) -> list[CarrySegment]:
    event_stream = sorted(events, key=lambda event: event.event_index)
    located = [
        (stream_index, event)
        for stream_index, event in enumerate(event_stream)
        if located_carry_anchor(event)
    ]
    carries: list[CarrySegment] = []
    for (previous_index, previous), (event_index, event) in zip(located, located[1:]):
        if (
            event.provider_player_id is None
            or not event.provider_team_id
            or event.provider_team_id != previous.provider_team_id
            or event.period != previous.period
            or event.match_seconds is None
            or previous.match_seconds is None
        ):
            continue
        elapsed_seconds = event.match_seconds - previous.match_seconds
        if not 0 <= elapsed_seconds <= MAX_CARRY_SECONDS:
            continue
        if phase_interrupted(event_stream[previous_index + 1 : event_index]):
            continue
        if not valid_carry_end(event):
            continue
        start = carry_start_position(previous, event)
        if start is None:
            continue
        end = (event.x, event.y)
        distance = carry_distance_metres(start, end)
        if not MIN_CARRY_METRES <= distance <= MAX_CARRY_METRES:
            continue
        acquisition_origin = previous.event_type in CARRY_ACQUISITION_EVENT_TYPES
        if acquisition_origin and (
            elapsed_seconds == 0
            or (elapsed_seconds == 1 and distance > MAX_ONE_SECOND_ACQUISITION_METRES)
        ):
            continue
        carries.append(
            CarrySegment(
                start_event_index=previous.event_index,
                end_event_index=event.event_index,
                provider_team_id=event.provider_team_id,
                team_id=event.team_id,
                provider_player_id=event.provider_player_id,
                player_id=event.player_id,
                period=event.period,
                minute=event.minute,
                second=event.second,
                match_seconds=event.match_seconds,
                x=start[0],
                y=start[1],
                end_x=end[0],
                end_y=end[1],
                is_progressive_carry=progressive_action(start[0], start[1], end[0], end[1]),
                is_final_third_entry=final_third_entry(True, start[0], end[0]),
                is_box_entry=box_entry(True, start[0], start[1], end[0], end[1]),
                is_low_confidence=acquisition_origin and elapsed_seconds == 1,
            )
        )
    return carries


def replace_match_carries(provider_match: ProviderMatch) -> int:
    """Rebuild derived carries for one match from its persisted events."""
    carries = derive_carries(list(provider_match.events.all()))
    with transaction.atomic():
        provider_match.derived_carries.all().delete()
        ProviderMatchCarry.objects.bulk_create(
            [
                ProviderMatchCarry(
                    provider_match=provider_match,
                    start_event_index=carry.start_event_index,
                    end_event_index=carry.end_event_index,
                    provider_team_id=carry.provider_team_id,
                    team_id=carry.team_id,
                    provider_player_id=carry.provider_player_id,
                    player_id=carry.player_id,
                    period=carry.period,
                    minute=carry.minute,
                    second=carry.second,
                    match_seconds=carry.match_seconds,
                    x=carry.x,
                    y=carry.y,
                    end_x=carry.end_x,
                    end_y=carry.end_y,
                    is_progressive_carry=carry.is_progressive_carry,
                    is_final_third_entry=carry.is_final_third_entry,
                    is_box_entry=carry.is_box_entry,
                    is_low_confidence=carry.is_low_confidence,
                )
                for carry in carries
            ],
            batch_size=1000,
        )
    return len(carries)


def backfill_match_carries(provider_matches: Iterable[ProviderMatch]) -> int:
    """Rebuild carries for already-ingested matches using the current formula."""
    total = 0
    for provider_match in provider_matches:
        total += replace_match_carries(provider_match)
    return total
