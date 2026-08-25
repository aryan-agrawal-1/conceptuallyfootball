"""Normalize match-level WhoScored clock and lineup metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ingestion.models import (
    MatchEventPeriod,
    MatchPlayerPositionRole,
    MatchPlayerRosterRole,
)


NOMINAL_PERIOD_MINUTES = {
    MatchEventPeriod.FIRST_HALF: 45,
    MatchEventPeriod.SECOND_HALF: 45,
    MatchEventPeriod.FIRST_EXTRA_TIME: 15,
    MatchEventPeriod.SECOND_EXTRA_TIME: 15,
}


@dataclass(frozen=True)
class NormalizedMatchPlayer:
    provider_team_id: str
    provider_player_id: str
    roster_index: int
    roster_role: str
    position_role: str


def normalize_match_clock(payload: Mapping[str, Any], diagnostics) -> dict[str, Any]:
    """Build the private provider-neutral continuous clock used by state features."""
    period_ends = payload.get("periodEndMinutes")
    expanded_minutes = payload.get("expandedMinutes")
    expanded_max_minute = optional_int(payload.get("expandedMaxMinute"))
    source_events = payload.get("events")
    if (
        not isinstance(period_ends, Mapping)
        or not isinstance(expanded_minutes, Mapping)
        or expanded_max_minute is None
        or not isinstance(source_events, list)
    ):
        diagnostics.warnings.append({"code": "clock_metadata_missing"})
        return invalid_clock("clock_metadata_missing")

    supported_periods = [
        int(period)
        for period in NOMINAL_PERIOD_MINUTES
        if str(int(period)) in period_ends or int(period) in period_ends
    ]
    if not supported_periods:
        diagnostics.warnings.append({"code": "no_supported_play"})
        return invalid_clock("no_supported_play")

    periods: list[dict[str, int]] = []
    previous_end_second = 0
    try:
        for period_index, period in enumerate(supported_periods):
            raw_end_minute = strict_nonnegative_int(mapping_lookup(period_ends, period))
            if raw_end_minute is None:
                raise ValueError("period end is missing")
            period_expansion = mapping_lookup(expanded_minutes, period)
            if not isinstance(period_expansion, Mapping):
                raise ValueError("expanded-minute period mapping is missing")
            expanded_end_minute = optional_int(
                mapping_lookup(period_expansion, raw_end_minute)
            )
            if expanded_end_minute is None:
                raise ValueError("expanded period end is missing")
            if period == supported_periods[-1] and expanded_end_minute != expanded_max_minute:
                raise ValueError("expanded match end does not reconcile")

            source_starts = source_boundary_seconds(
                source_events, period=period, event_name="Start"
            )
            source_ends = source_boundary_seconds(
                source_events, period=period, event_name="End"
            )
            if len(source_starts) != 1 or len(source_ends) != 1:
                raise ValueError("exact period boundary evidence is missing or conflicting")
            source_start_second = next(iter(source_starts))
            source_end_second = next(iter(source_ends))
            if source_end_second <= source_start_second:
                raise ValueError("period duration is not positive")
            if source_end_second // 60 != expanded_end_minute:
                raise ValueError("exact period end does not reconcile")
            duration_seconds = source_end_second - source_start_second
            end_second = previous_end_second + duration_seconds
            periods.append(
                {
                    "period": period,
                    "period_index": period_index,
                    "start_second": previous_end_second,
                    "end_second": end_second,
                    "duration_seconds": duration_seconds,
                    "nominal_duration_seconds": NOMINAL_PERIOD_MINUTES[period] * 60,
                    "source_start_second": source_start_second,
                    "source_end_second": source_end_second,
                }
            )
            previous_end_second = end_second
    except (TypeError, ValueError) as error:
        diagnostics.warnings.append(
            {"code": "clock_metadata_invalid", "message": str(error)}
        )
        return invalid_clock("clock_metadata_invalid")

    return {
        "calculation_version": "match_clock_v1",
        "valid": True,
        "exclusion_reason": None,
        "periods": periods,
        "supported_end_second": previous_end_second,
    }


def invalid_clock(reason: str) -> dict[str, Any]:
    return {
        "calculation_version": "match_clock_v1",
        "valid": False,
        "exclusion_reason": reason,
        "periods": [],
        "supported_end_second": None,
    }


def source_boundary_seconds(
    source_events: Sequence[Any], *, period: int, event_name: str
) -> set[int]:
    boundaries: set[int] = set()
    for source_event in source_events:
        if not isinstance(source_event, Mapping):
            continue
        if display_name(source_event.get("type")) != event_name:
            continue
        if normalized_period(source_event.get("period")) != period:
            continue
        minute = optional_int(source_event.get("expandedMinute"))
        second = strict_nonnegative_int(source_event.get("second"))
        if minute is not None and second is not None and second <= 59:
            boundaries.add(minute * 60 + second)
    return boundaries


def normalize_match_players(
    payload: Mapping[str, Any], diagnostics
) -> tuple[NormalizedMatchPlayer, ...]:
    players: list[NormalizedMatchPlayer] = []
    for side in ("home", "away"):
        team = payload.get(side)
        if not isinstance(team, Mapping):
            continue
        provider_team_id = optional_string(team.get("teamId"))
        source_players = team.get("players")
        if provider_team_id is None or not isinstance(source_players, list):
            diagnostics.warnings.append({"code": "lineup_metadata_missing", "side": side})
            continue
        for roster_index, source_player in enumerate(source_players):
            if not isinstance(source_player, Mapping):
                diagnostics.warnings.append(
                    {"code": "invalid_lineup_player", "side": side, "index": roster_index}
                )
                continue
            provider_player_id = optional_string(source_player.get("playerId"))
            if provider_player_id is None or len(provider_player_id) > 64:
                diagnostics.warnings.append(
                    {"code": "invalid_lineup_player_id", "side": side, "index": roster_index}
                )
                continue
            source_position = str(source_player.get("position") or "").strip().upper()
            players.append(
                NormalizedMatchPlayer(
                    provider_team_id=provider_team_id,
                    provider_player_id=provider_player_id,
                    roster_index=roster_index,
                    roster_role=(
                        MatchPlayerRosterRole.STARTER
                        if source_player.get("isFirstEleven") is True
                        else MatchPlayerRosterRole.SUBSTITUTE
                    ),
                    position_role=(
                        MatchPlayerPositionRole.GOALKEEPER
                        if source_position in {"GK", "GOALKEEPER"}
                        else MatchPlayerPositionRole.OUTFIELD
                        if source_position
                        else MatchPlayerPositionRole.UNKNOWN
                    ),
                )
            )
    return tuple(players)


def normalized_timeline_seconds(
    event: Mapping[str, Any], clock: Mapping[str, Any]
) -> int | None:
    if not clock.get("valid"):
        return None
    expanded_minute = optional_int(event.get("expandedMinute"))
    second = strict_nonnegative_int(event.get("second"))
    if expanded_minute is None or second is None or second > 59:
        return None
    source_second = expanded_minute * 60 + second
    period = normalized_period(event.get("period"))
    for boundary in clock.get("periods", []):
        if boundary["period"] != period:
            continue
        timeline_seconds = (
            boundary["start_second"] + source_second - boundary["source_start_second"]
        )
        return (
            timeline_seconds
            if boundary["start_second"] <= timeline_seconds < boundary["end_second"]
            else None
        )
    return None


def normalized_period(value: Any) -> int:
    raw = optional_int(mapping_value(value, "value"))
    if raw in MatchEventPeriod.values:
        return raw
    names = {
        "FirstHalf": MatchEventPeriod.FIRST_HALF,
        "SecondHalf": MatchEventPeriod.SECOND_HALF,
        "FirstPeriodOfExtraTime": MatchEventPeriod.FIRST_EXTRA_TIME,
        "SecondPeriodOfExtraTime": MatchEventPeriod.SECOND_EXTRA_TIME,
        "PenaltyShootout": MatchEventPeriod.PENALTY_SHOOTOUT,
        "PostGame": MatchEventPeriod.POST_GAME,
    }
    return names.get(display_name(value), MatchEventPeriod.UNKNOWN)


def mapping_lookup(value: Mapping[Any, Any], key: int) -> Any:
    return value[key] if key in value else value.get(str(key))


def display_name(value: Any) -> str:
    return str(value.get("displayName") or "") if isinstance(value, Mapping) else str(value or "")


def mapping_value(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, Mapping) else None


def optional_int(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def strict_nonnegative_int(value: Any) -> int | None:
    converted = optional_int(value)
    return converted if converted is not None and converted >= 0 else None


def optional_string(value: Any) -> str | None:
    return None if value in (None, "") else str(value)
