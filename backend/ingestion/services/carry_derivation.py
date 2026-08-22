"""Derivation of ball carries from the normalized Opta/WhoScored event stream.

Opta does not publish carry events. Following the StatsBomb definition — a
player moving the ball with consecutive touches while in controlled
possession — a carry is derived here as the displacement between two
consecutive located touches by the same player where no other player's touch
intervenes. Derived rows are rebuilt from scratch whenever a match's events
are replaced; they never live inside ``ProviderMatchEvent`` itself.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from django.db import transaction

from ingestion.models import (
    MatchEventType,
    ProviderMatch,
    ProviderMatchCarry,
    ProviderMatchEvent,
)

# Scaled coordinates span 0..10000 for a 105m x 68m pitch, so one int unit is
# 1.05cm along x and 0.68cm across y.
X_METRES_PER_UNIT = 105.0 / 10_000
Y_METRES_PER_UNIT = 68.0 / 10_000

MIN_CARRY_METRES = 3.0
MAX_CARRY_METRES = 60.0


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


def _located_touch(event: ProviderMatchEvent) -> bool:
    return event.is_touch and event.x is not None and event.y is not None


def _touch_position(event: ProviderMatchEvent) -> tuple[int, int]:
    """Where the ball sits after this touch.

    A completed pass with an end location leaves the ball at its destination;
    every other touch (and any incomplete pass) keeps the event's own origin,
    so the displacement a pass already covers is never re-emitted as a carry.
    """
    if (
        event.event_type == MatchEventType.PASS
        and event.outcome_successful is True
        and event.end_x is not None
        and event.end_y is not None
    ):
        return event.end_x, event.end_y
    return event.x, event.y


def carry_distance_metres(start: tuple[int, int], end: tuple[int, int]) -> float:
    delta_x = (end[0] - start[0]) * X_METRES_PER_UNIT
    delta_y = (end[1] - start[1]) * Y_METRES_PER_UNIT
    return (delta_x * delta_x + delta_y * delta_y) ** 0.5


def derive_carries(events: Sequence[ProviderMatchEvent]) -> list[CarrySegment]:
    ordered = sorted(
        (event for event in events if _located_touch(event)),
        key=lambda event: event.event_index,
    )
    carries: list[CarrySegment] = []
    for previous, event in zip(ordered, ordered[1:]):
        same_player = (
            event.provider_player_id is not None
            and event.provider_player_id == previous.provider_player_id
            and event.team_id == previous.team_id
        )
        if not same_player:
            continue
        start = _touch_position(previous)
        end = (event.x, event.y)
        distance = carry_distance_metres(start, end)
        if not MIN_CARRY_METRES <= distance <= MAX_CARRY_METRES:
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
                )
                for carry in carries
            ],
            batch_size=1000,
        )
    return len(carries)


def backfill_match_carries(provider_matches: Iterable[ProviderMatch]) -> int:
    """Rebuild carries for matches whose events predate carry derivation."""
    total = 0
    for provider_match in provider_matches:
        total += replace_match_carries(provider_match)
    return total
