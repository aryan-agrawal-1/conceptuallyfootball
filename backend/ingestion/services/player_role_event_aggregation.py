"""Bounded match-batch exposure, event, carry, and team aggregation."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from itertools import islice
from typing import Iterable, Mapping

from ingestion.models import (
    MatchEventGameState,
    MatchEventShotOutcome,
    MatchEventShotSituation,
    MatchEventType,
    Provider,
    ProviderMatch,
    ProviderMatchCarry,
    ProviderMatchEvent,
    ProviderMatchPlayerStateExposure,
)
from ingestion.services.player_role_aggregation import (
    CARRY_COLUMNS,
    DEFAULT_MATCH_BATCH_SIZE,
    EVENT_COLUMNS,
    EXPOSURE_COLUMNS,
    MATCH_COLUMNS,
    ActionAccumulator,
    CompactMatchBatch,
    GeometryAccumulator,
    PlayerRoleFeatureAccumulator,
)
from ingestion.services.whoscored_normalization import (
    action_grid_assignment,
    is_action_event,
    is_defensive_event,
)


STATE_BY_VALUE = {
    MatchEventGameState.LOSING: "losing",
    MatchEventGameState.DRAWING: "drawing",
    MatchEventGameState.WINNING: "winning",
}
SET_PIECE_SHOT_SITUATIONS = {
    MatchEventShotSituation.SET_PIECE,
    MatchEventShotSituation.CORNER,
    MatchEventShotSituation.DIRECT_FREE_KICK,
    MatchEventShotSituation.PENALTY,
}


def state_name(value) -> str:
    if isinstance(value, str) and value in {"losing", "drawing", "winning"}:
        return value
    return STATE_BY_VALUE[int(value)]


def row_open_play(event: Mapping) -> bool:
    if event.get("is_set_piece") or event.get("is_corner") or event.get("is_free_kick") or event.get("is_throw_in"):
        return False
    return not (
        event.get("event_type") == MatchEventType.SHOT
        and event.get("shot_situation") in SET_PIECE_SHOT_SITUATIONS
    )


def distance_metres(row: Mapping) -> float | None:
    if None in (row.get("x"), row.get("y"), row.get("end_x"), row.get("end_y")):
        return None
    delta_x = (row["end_x"] - row["x"]) * 0.0105
    delta_y = (row["end_y"] - row["y"]) * 0.0068
    return (delta_x ** 2 + delta_y ** 2) ** 0.5


def add_event_action(accumulator: ActionAccumulator, event: Mapping) -> None:
    event_type = event.get("event_type")
    defensive = is_defensive_event(event_type, defensive_qualifier=event.get("is_defensive", False))
    if event.get("is_touch"):
        accumulator.counters["touches"] += 1
        if event.get("x") is not None and event.get("y") is not None:
            accumulator.touch_location.add(event["x"] / 100, event["y"] / 100)
            accumulator.touch_grid.add(action_grid_assignment(event["x"], event["y"])[2])
    accumulator.counters["actions"] += is_action_event(
        event_type, defensive_qualifier=event.get("is_defensive", False)
    )
    if event_type == MatchEventType.PASS:
        accumulator.counters["pass_attempts"] += 1
        accumulator.counters["pass_completions"] += event.get("outcome_successful") is True
        accumulator.counters["progressive_passes"] += bool(event.get("is_progressive_pass"))
        accumulator.counters["progressive_actions"] += bool(event.get("is_progressive_pass"))
        accumulator.counters["final_third_entries"] += bool(event.get("is_final_third_entry"))
        accumulator.counters["box_entries"] += bool(event.get("is_box_entry"))
        accumulator.counters["key_passes"] += bool(event.get("is_key_pass"))
        accumulator.counters["crosses"] += bool(event.get("is_cross"))
        accumulator.counters["long_balls"] += bool(event.get("is_long_ball"))
        length = distance_metres(event)
        if length is not None:
            accumulator.pass_lengths.add(length)
        if event.get("x") is not None and event.get("end_x") is not None:
            delta = event["end_x"] - event["x"]
            accumulator.pass_forward.add(
                delta * 0.0105,
                exact_value=Decimal(delta) * Decimal("0.0105"),
            )
    accumulator.counters["shots"] += event_type == MatchEventType.SHOT
    accumulator.counters["goals"] += (
        event_type == MatchEventType.SHOT
        and event.get("shot_outcome") == MatchEventShotOutcome.GOAL
    )
    accumulator.counters["big_chance_shots"] += (
        event_type == MatchEventType.SHOT and bool(event.get("is_big_chance"))
    )
    accumulator.counters["take_ons"] += event_type == MatchEventType.TAKE_ON
    if defensive:
        accumulator.counters["defensive_actions"] += 1
        accumulator.counters["recoveries"] += event_type == MatchEventType.BALL_RECOVERY
        accumulator.counters["tackles"] += event_type == MatchEventType.TACKLE
        accumulator.counters["interceptions"] += event_type == MatchEventType.INTERCEPTION
        accumulator.counters["clearances"] += event_type == MatchEventType.CLEARANCE


def add_carry_action(accumulator: ActionAccumulator, carry: Mapping) -> None:
    accumulator.counters["carries"] += 1
    accumulator.counters["progressive_carries"] += bool(carry.get("is_progressive_carry"))
    accumulator.counters["progressive_actions"] += bool(carry.get("is_progressive_carry"))
    accumulator.counters["carry_final_third_entries"] += bool(carry.get("is_final_third_entry"))
    accumulator.counters["carry_box_entries"] += bool(carry.get("is_box_entry"))
    length = distance_metres(carry)
    if length is not None:
        accumulator.carry_lengths.add(length)
    if carry.get("x") is not None and carry.get("end_x") is not None:
        delta = carry["end_x"] - carry["x"]
        accumulator.carry_forward.add(
            delta * 0.0105,
            exact_value=Decimal(delta) * Decimal("0.0105"),
        )


def line_breaking_pass(event: Mapping) -> bool:
    if (
        event.get("event_type") != MatchEventType.PASS
        or event.get("outcome_successful") is not True
        or event.get("is_cross")
        or event.get("x") is None
        or event.get("end_x") is None
    ):
        return False
    forward_distance = event["end_x"] - event["x"]
    crosses_line = event["x"] < 3300 <= event["end_x"] or event["x"] < 6600 <= event["end_x"]
    return bool(event.get("is_through_ball")) or forward_distance >= 1200 and crosses_line


def add_event_geometry(accumulator: GeometryAccumulator, event: Mapping, *, goalkeeper: bool) -> None:
    event_type = event.get("event_type")
    set_piece = bool(event.get("is_set_piece") or event.get("is_corner") or event.get("is_free_kick"))
    if set_piece:
        accumulator.counters["set_piece_actions"] += 1
        accumulator.counters["set_piece_creation"] += bool(
            event.get("is_key_pass") or event.get("is_shot_assist")
        )
    if not row_open_play(event):
        return
    accumulator.counters["open_play_events"] += 1
    is_pass = event_type == MatchEventType.PASS
    is_touch = bool(event.get("is_touch"))
    defensive = event_type in {
        MatchEventType.BALL_RECOVERY, MatchEventType.TACKLE, MatchEventType.INTERCEPTION,
        MatchEventType.CLEARANCE, MatchEventType.BLOCKED_PASS, MatchEventType.AERIAL,
        MatchEventType.CHALLENGE,
    } and (event_type not in {MatchEventType.AERIAL, MatchEventType.CHALLENGE} or event.get("is_defensive"))
    accumulator.counters["passes"] += is_pass
    accumulator.counters["completed_passes"] += is_pass and event.get("outcome_successful") is True
    accumulator.counters["touches"] += is_touch
    accumulator.counters["central_touches"] += is_touch and event.get("y") is not None and 2500 <= event["y"] <= 7500
    accumulator.counters["advanced_actions"] += event.get("x") is not None and event["x"] >= 6000
    accumulator.counters["advanced_touches"] += is_touch and event.get("x") is not None and event["x"] >= 6000
    accumulator.counters["box_touches"] += is_touch and event.get("x") is not None and event.get("y") is not None and event["x"] >= 8300 and 2100 <= event["y"] <= 7900
    accumulator.counters["shots"] += event_type == MatchEventType.SHOT
    accumulator.counters["key_passes"] += is_pass and bool(event.get("is_key_pass") or event.get("is_shot_assist"))
    accumulator.counters["line_breaking_passes"] += line_breaking_pass(event)
    accumulator.counters["build_up_passes"] += is_pass and event.get("x") is not None and event["x"] <= 4500
    accumulator.counters["build_up_progressive_passes"] += is_pass and event.get("x") is not None and event["x"] <= 4500 and bool(event.get("is_progressive_pass"))
    accumulator.counters["central_progressive_passes"] += is_pass and bool(event.get("is_progressive_pass")) and event.get("y") is not None and 2500 <= event["y"] <= 7500
    accumulator.counters["dangerous_entries"] += is_pass and bool(event.get("is_final_third_entry") or event.get("is_box_entry"))
    accumulator.counters["long_progressive_passes"] += is_pass and bool(event.get("is_long_ball") or event.get("is_progressive_pass"))
    accumulator.counters["defensive_actions"] += defensive
    deep = defensive and event.get("x") is not None and event["x"] <= 4000
    accumulator.counters["deep_defensive_actions"] += deep
    accumulator.counters["protective_interventions"] += deep and event_type in {MatchEventType.CLEARANCE, MatchEventType.BLOCKED_PASS, MatchEventType.AERIAL}
    accumulator.counters["ball_wins"] += defensive and event_type in {MatchEventType.BALL_RECOVERY, MatchEventType.TACKLE, MatchEventType.INTERCEPTION, MatchEventType.CHALLENGE}
    accumulator.counters["tackles_interceptions"] += defensive and event_type in {MatchEventType.TACKLE, MatchEventType.INTERCEPTION}
    accumulator.counters["aerials"] += event_type == MatchEventType.AERIAL
    accumulator.counters["turnovers"] += event_type == MatchEventType.DISPOSSESSED or (event_type == MatchEventType.TAKE_ON and event.get("outcome_successful") is False)
    if defensive and event.get("x") is not None:
        accumulator.defensive_x.add(event["x"] / 100)
    sweeper = goalkeeper and event.get("x") is not None and event["x"] >= 1800 and event_type in {MatchEventType.PASS, MatchEventType.BALL_RECOVERY, MatchEventType.CLEARANCE}
    accumulator.counters["sweeper_actions"] += sweeper
    if sweeper:
        accumulator.sweeper_x.add(event["x"] / 100)
    accumulator.counters["saves"] += event_type == MatchEventType.SAVE
    accumulator.counters["close_range_saves"] += event_type == MatchEventType.SAVE and event.get("x") is not None and event["x"] <= 1800


def active_profiles(exposures, match_id: int, team_id: int, second: int | None):
    if second is None:
        return ()
    return (
        (player_id, state)
        for player_id, intervals in exposures.get((match_id, team_id), {}).items()
        for start, end, state in intervals
        if start <= second < end
    )


def aggregate_non_possession_batch(
    batch: CompactMatchBatch,
    accumulators: dict[tuple[int, int], PlayerRoleFeatureAccumulator],
) -> None:
    """Update compact accumulators while retaining no row beyond this batch."""

    exposures = defaultdict(lambda: defaultdict(list))
    for row in batch.exposures:
        match_id = int(row["player_interval__participation__provider_match_id"])
        team_id = int(row["player_interval__participation__team_id"])
        player_id = int(row["player_interval__participation__player_id"])
        pair = (player_id, team_id)
        if pair not in accumulators:
            continue
        state = state_name(row["coarse_state"])
        start, end = int(row["start_second"]), int(row["end_second"])
        episode = int(row["team_episode__episode_index"])
        exposures[(match_id, team_id)][player_id].append((start, end, state))
        target = accumulators[pair]
        target.exposure.add(match_id, episode, start, end)
        target.states[state].exposure.add(match_id, episode, start, end)

    for event in batch.events:
        match_id, team_id = int(event["provider_match_id"]), event.get("team_id")
        if team_id is None:
            continue
        team_id = int(team_id)
        second = event.get("timeline_seconds")
        for player_id, state in active_profiles(exposures, match_id, team_id, second):
            target = accumulators[(player_id, team_id)]
            add_event_geometry(target.team_geometry, event, goalkeeper=False)
            if row_open_play(event):
                add_event_action(target.overall_team, event)
                add_event_action(target.states[state].team, event)
            if event.get("player_id") == player_id:
                add_event_geometry(target.player_geometry, event, goalkeeper=target.position_group == "GK")
                if row_open_play(event):
                    add_event_action(target.overall_player, event)
                    add_event_action(target.states[state].player, event)

    for carry in batch.carries:
        match_id, team_id = int(carry["provider_match_id"]), carry.get("team_id")
        if team_id is None:
            continue
        team_id = int(team_id)
        for player_id, state in active_profiles(exposures, match_id, team_id, carry.get("match_seconds")):
            target = accumulators[(player_id, team_id)]
            add_carry_action(target.overall_team, carry)
            add_carry_action(target.states[state].team, carry)
            if carry.get("player_id") == player_id:
                add_carry_action(target.overall_player, carry)
                add_carry_action(target.states[state].player, carry)


def iter_non_possession_batches(
    competition_season,
    batch_size: int = DEFAULT_MATCH_BATCH_SIZE,
    *,
    match_ids: Iterable[int] | None = None,
):
    """Yield fixed-size scalar batches and release each before reading the next."""

    if not 1 <= batch_size <= DEFAULT_MATCH_BATCH_SIZE:
        raise ValueError(f"match batch size must be between 1 and {DEFAULT_MATCH_BATCH_SIZE}")
    matches_query = ProviderMatch.objects.filter(
        competition_season=competition_season, provider=Provider.WHOSCORED,
    )
    if match_ids is not None:
        matches_query = matches_query.filter(id__in=tuple(int(match_id) for match_id in match_ids))
    matches = matches_query.values(*MATCH_COLUMNS).order_by("kickoff_at", "id").iterator(chunk_size=batch_size)
    while rows := tuple(islice(matches, batch_size)):
        match_ids = tuple(int(row["id"]) for row in rows)
        events = tuple(ProviderMatchEvent.objects.filter(
            provider_match_id__in=match_ids,
        ).values(*EVENT_COLUMNS).order_by("provider_match_id", "event_index", "id"))
        carries = tuple(ProviderMatchCarry.objects.filter(
            provider_match_id__in=match_ids,
        ).values(*CARRY_COLUMNS).order_by("provider_match_id", "start_event_index", "id"))
        exposures = tuple(ProviderMatchPlayerStateExposure.objects.filter(
            player_interval__participation__provider_match_id__in=match_ids,
            player_interval__participation__status="verified",
            player_interval__participation__confidence="verified",
            player_interval__confidence="verified",
        ).values(*EXPOSURE_COLUMNS).order_by(
            "player_interval__participation__provider_match_id",
            "player_interval__participation__team_id",
            "player_interval__participation__player_id", "start_second", "end_second", "id",
        ))
        yield CompactMatchBatch(matches=rows, events=events, carries=carries, exposures=exposures)
