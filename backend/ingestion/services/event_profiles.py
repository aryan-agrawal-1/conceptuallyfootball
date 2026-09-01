"""Rebuildable WhoScored season event profiles.

The event table is deliberately the only input here: this service never fetches
the provider and never applies match deltas to an existing aggregate.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from time import monotonic
from typing import Iterable, NamedTuple

from django.db import transaction
from django.utils import timezone

from ingestion.api_cache import invalidate_event_profile_api_payloads
from ingestion.models import (
    CompetitionSeason, EventProfileSplitType,
    IngestionKind, IngestionRun, IngestionRunStatus, MatchEventShotOutcome, MatchEventType,
    PlayerSeasonDerivedStats, PlayerSeasonEventProfile, Provider,
    ProviderMatchEvent, TeamSeasonEventProfile,
)
from ingestion.services.identity import (
    build_event_identity_report,
    validate_event_identity_publication,
)
from ingestion.services.player_role_diagnostics import record_stage, sample_memory
from ingestion.services.whoscored_normalization import (
    ACTION_GRID_COLUMNS, ACTION_GRID_ROWS,
    action_grid_assignment, grid_assignment, is_action_event, is_defensive_event,
)

FORMULA_VERSION = "event_profiles_v3"
PASS_FLOW_COLUMNS = 6
PASS_FLOW_ROWS = 4


@dataclass
class BuildResult:
    player_rows: int
    team_rows: int
    affected_player_ids: set[int]
    affected_team_ids: set[int]


class ProfileEvent(NamedTuple):
    provider_match_id: int
    player_id: int | None
    team_id: int | None
    expanded_minute: int | None
    minute: int
    x: float | None
    y: float | None
    end_x: float | None
    end_y: float | None
    event_type: str
    outcome_successful: bool | None
    is_touch: bool
    is_key_pass: bool
    is_cross: bool
    is_long_ball: bool
    is_big_chance: bool
    is_defensive: bool
    shot_outcome: str
    is_progressive_pass: bool
    is_final_third_entry: bool
    is_box_entry: bool


PROFILE_EVENT_COLUMNS = ProfileEvent._fields


def _start(run: IngestionRun) -> None:
    run.status = IngestionRunStatus.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])


def _fail(run: IngestionRun, exc: Exception) -> None:
    run.status = IngestionRunStatus.FAILED
    run.finished_at = timezone.now()
    run.error_detail = str(exc)[:8000]
    run.save(update_fields=["status", "finished_at", "error_detail", "stats"])


def _event_minutes(events: Iterable[ProfileEvent], match_minutes: dict[int, int]) -> int:
    return sum(match_minutes[event_id] for event_id in {event.provider_match_id for event in events})


def event_profile_availability(passes: int, shots: int, actions: int) -> dict:
    return {
        "pass_map": {"available": passes > 0, "sparse": passes < 100},
        "shot_map": {"available": shots > 0, "sparse": shots < 5},
        "action_grid": {"available": actions >= 20, "sparse": actions < 100},
    }


def _grid(
    events: Iterable[ProfileEvent],
    minutes: int,
    *,
    touches_only: bool = False,
) -> tuple[list[dict], int]:
    counts = [0] * (ACTION_GRID_COLUMNS * ACTION_GRID_ROWS)
    total = 0
    for event in events:
        if event.x is None or event.y is None:
            continue
        if touches_only and not event.is_touch:
            continue
        if not touches_only and not is_action_event(
            event.event_type, defensive_qualifier=event.is_defensive
        ):
            continue
        _, _, cell = action_grid_assignment(event.x, event.y)
        counts[cell] += 1
        total += 1
    availability = event_profile_availability(0, 0, total)["action_grid"]
    cells = []
    for column in range(ACTION_GRID_COLUMNS):
        for row in range(ACTION_GRID_ROWS):
            index = column * ACTION_GRID_ROWS + row
            raw = counts[index]
            cells.append({
                "column": column, "row": row, "raw_count": raw,
                "per90_count": (raw * 90.0 / minutes) if minutes else None,
                "share": (raw / total) if total else 0.0,
                "available": availability["available"], "sparse": availability["sparse"],
            })
    return cells, total


def _summary(events: list[ProfileEvent]) -> dict:
    passes = [event for event in events if event.event_type == MatchEventType.PASS]
    shots = [event for event in events if event.event_type == MatchEventType.SHOT]
    take_ons = [event for event in events if event.event_type == MatchEventType.TAKE_ON]
    defensive = [event for event in events if is_defensive_event(event.event_type, defensive_qualifier=event.is_defensive)]
    touches = [event for event in events if event.is_touch]
    located_touches = [event for event in touches if event.x is not None and event.y is not None]
    valid_location = [event for event in events if event.x is not None and event.y is not None and is_action_event(event.event_type, defensive_qualifier=event.is_defensive)]
    return {
        "valid_location_actions": len(valid_location), "touches": len(touches),
        "pass_attempts": len(passes), "pass_completions": sum(e.outcome_successful is True for e in passes),
        "progressive_pass_attempts": sum(e.is_progressive_pass for e in passes),
        "progressive_pass_completions": sum(e.is_progressive_pass and e.outcome_successful is True for e in passes),
        "final_third_entries": sum(e.is_final_third_entry for e in passes),
        "box_entries": sum(e.is_box_entry for e in passes),
        "key_passes": sum(e.is_key_pass for e in passes), "crosses": sum(e.is_cross for e in passes),
        "long_balls": sum(e.is_long_ball for e in passes), "shots": len(shots),
        "goals": sum(e.shot_outcome == MatchEventShotOutcome.GOAL for e in shots),
        "big_chance_shots": sum(e.is_big_chance for e in shots),
        "take_ons_attempted": len(take_ons), "take_ons_successful": sum(e.outcome_successful is True for e in take_ons),
        "defensive_actions": len(defensive),
        "average_touch_x": round(sum(e.x for e in located_touches) / len(located_touches)) if located_touches else None,
        "average_touch_y": round(sum(e.y for e in located_touches) / len(located_touches)) if located_touches else None,
    }


def _pass_flow(events: Iterable[ProfileEvent]) -> list[dict]:
    values = defaultdict(lambda: [0, 0, 0, 0, 0, 0.0])
    for event in events:
        if (
            event.event_type != MatchEventType.PASS
            or event.outcome_successful is not True
            or None in (event.x, event.y, event.end_x, event.end_y)
        ):
            continue
        column, row, _ = grid_assignment(
            event.x,
            event.y,
            PASS_FLOW_COLUMNS,
            PASS_FLOW_ROWS,
        )
        value = values[(column, row)]
        value[0] += 1
        value[1] += event.x
        value[2] += event.y
        value[3] += event.end_x
        value[4] += event.end_y
        delta_x_metres = (event.end_x - event.x) * 0.0105
        delta_y_metres = (event.end_y - event.y) * 0.0068
        value[5] += (delta_x_metres ** 2 + delta_y_metres ** 2) ** 0.5
    total = sum(value[0] for value in values.values())
    rows = []
    for column in range(PASS_FLOW_COLUMNS):
        for row in range(PASS_FLOW_ROWS):
            count, origin_x, origin_y, end_x, end_y, length = values[(column, row)]
            if not count:
                continue
            rows.append({
                "column": column,
                "row": row,
                "completed_count": count,
                "share": count / total if total else 0.0,
                "mean_origin_x": round(origin_x / count / 100, 4),
                "mean_origin_y": round(origin_y / count / 100, 4),
                "mean_destination_x": round(end_x / count / 100, 4),
                "mean_destination_y": round(end_y / count / 100, 4),
                "mean_length_metres": round(length / count, 3),
            })
    return rows


def _profile_events(competition_season: CompetitionSeason) -> list[ProfileEvent]:
    rows = ProviderMatchEvent.objects.filter(
        provider_match__competition_season=competition_season,
        provider_match__provider=Provider.WHOSCORED,
    ).values_list(*PROFILE_EVENT_COLUMNS)
    return [ProfileEvent(*row) for row in rows.iterator(chunk_size=5000)]


def materialize_event_profiles(
    competition_season: CompetitionSeason, *, run: IngestionRun,
    affected_player_ids: Iterable[int] | None = None, affected_team_ids: Iterable[int] | None = None,
    internal_pilot: bool = False,
) -> BuildResult | None:
    """Publish a full or affected-entity rebuild; failures leave current rows intact."""
    if run.kind != IngestionKind.EVENT_PROFILES:
        raise ValueError("Event profiles require an event-profile ingestion run.")
    if run.competition_season_id != competition_season.pk:
        raise ValueError("Event-profile run belongs to another competition season.")
    if not competition_season.supports_whoscored:
        raise ValueError("WhoScored is not configured for this competition season.")
    _start(run)
    diagnostics = {"stage_timings_seconds": {}, "rss_samples_mb": {}}
    total_started = monotonic()
    sample_memory(diagnostics, "start")
    try:
        with transaction.atomic():
            stage_started = monotonic()
            report = build_event_identity_report(competition_season)
            record_stage(diagnostics, "identity_report", stage_started)
            stage_started = monotonic()
            all_events = _profile_events(competition_season)
            record_stage(diagnostics, "load_events", stage_started)
            stage_started = monotonic()
            coverage = _coverage_report(competition_season, all_events)
            record_stage(diagnostics, "coverage", stage_started)
            public_complete = (
                coverage["complete"]
                and report.volume.unmapped_team_events == 0
                and not report.publication_failure
            )
            run.stats = {
                "formula_version": FORMULA_VERSION,
                "event_identity": report.as_dict(),
                "coverage": coverage,
                "public_complete": public_complete,
                "internal_pilot": internal_pilot,
                "pipeline": diagnostics,
            }
            validate_event_identity_publication(report)
            if not all_events:
                raise ValueError("No normalized WhoScored events are available to materialize.")
            stage_started = monotonic()
            if affected_player_ids is None:
                player_ids = {e.player_id for e in all_events if e.player_id}
                player_ids.update(PlayerSeasonEventProfile.objects.filter(competition_season=competition_season, is_current=True).values_list("player_id", flat=True))
            else:
                player_ids = set(affected_player_ids)
            if affected_team_ids is None:
                team_ids = {e.team_id for e in all_events if e.team_id}
                team_ids.update(TeamSeasonEventProfile.objects.filter(competition_season=competition_season, is_current=True).values_list("team_id", flat=True))
            else:
                team_ids = set(affected_team_ids)
            record_stage(diagnostics, "resolve_profile_scopes", stage_started)
            if competition_season.is_published and not public_complete and not internal_pilot:
                raise ValueError("Published event profiles require mapped teams and complete WhoScored coverage.")
            stage_started = monotonic()
            result = _publish(competition_season, run, all_events, player_ids, team_ids)
            record_stage(diagnostics, "publish_profiles", stage_started)
            record_stage(diagnostics, "total", total_started)
            stats = run.stats | {
                "player_profiles": result.player_rows,
                "team_profiles": result.team_rows,
                "affected_player_ids": sorted(player_ids),
                "affected_team_ids": sorted(team_ids),
            }
            run.stats = stats
            run.status = IngestionRunStatus.SUCCESS
            run.finished_at = timezone.now()
            run.error_detail = ""
            run.save(update_fields=["stats", "status", "finished_at", "error_detail"])
            invalidate_event_profile_api_payloads(competition_season.pk)
            return result
    except Exception as exc:  # publication transaction must have exited before recording failure
        _fail(run, exc)
        return None


def _coverage_report(competition_season: CompetitionSeason, events: list[ProfileEvent]) -> dict:
    expected = competition_season.whoscored_expected_match_count
    completed = set(competition_season.provider_matches.filter(provider=Provider.WHOSCORED, status="completed").values_list("id", flat=True))
    observed = {event.provider_match_id for event in events}
    discovered_complete = completed <= observed
    expected_complete = competition_season.refresh_enabled or (
        expected is not None and len(observed) >= expected
    )
    return {"completed_matches": len(completed), "observed_matches": len(observed), "expected_matches": expected,
            "discovered_complete": discovered_complete, "complete": discovered_complete and expected_complete}


def _publish(cs: CompetitionSeason, run: IngestionRun, events: list[ProfileEvent], player_ids: set[int], team_ids: set[int]) -> BuildResult:
    by_player = defaultdict(list)
    by_player_team = defaultdict(list)
    by_team = defaultdict(list)
    by_match = defaultdict(list)
    for event in events:
        by_match[event.provider_match_id].append(event)
        if event.player_id:
            by_player[event.player_id].append(event)
            if event.team_id:
                by_player_team[(event.player_id, event.team_id)].append(event)
        if event.team_id:
            by_team[event.team_id].append(event)
    match_minutes = {}
    for event in events:
        minute = event.expanded_minute if event.expanded_minute is not None else event.minute
        match_minutes[event.provider_match_id] = max(match_minutes.get(event.provider_match_id, 0), minute)
    derived_minutes = {row.canonical_player_id: row.minutes or 0 for row in PlayerSeasonDerivedStats.objects.filter(
        competition_season=cs, is_current=True, canonical_player_id__in=player_ids)}
    player_rows = []
    for player_id in sorted(player_ids):
        events_for_player = by_player.get(player_id, [])
        if not events_for_player:
            continue
        player_rows.append(_player_row(cs, run, player_id, None, EventProfileSplitType.SEASON_TOTAL, events_for_player, derived_minutes.get(player_id, 0), match_minutes))
        for team_id in sorted({team_id for (pid, team_id) in by_player_team if pid == player_id}):
            scoped = by_player_team[(player_id, team_id)]
            player_rows.append(_player_row(cs, run, player_id, team_id, EventProfileSplitType.TEAM, scoped, derived_minutes.get(player_id, 0), match_minutes))
    team_rows = [
        _team_row(cs, run, team_id, by_team[team_id], by_match)
        for team_id in sorted(team_ids)
        if team_id in by_team
    ]
    if len({(row.player_id, row.team_id, row.split_type) for row in player_rows}) != len(player_rows):
        raise ValueError("Duplicate player event-profile scope.")
    if (
        len({row.team_id for row in team_rows}) != len(team_rows)
        or any(len(row.action_grid) != ACTION_GRID_COLUMNS * ACTION_GRID_ROWS for row in player_rows + team_rows)
        or any(len(row.opponent_action_grid) != ACTION_GRID_COLUMNS * ACTION_GRID_ROWS for row in team_rows)
        or any(len(row.pass_flow) > PASS_FLOW_COLUMNS * PASS_FLOW_ROWS for row in team_rows)
        or any(
            len({(flow.get("column"), flow.get("row")) for flow in row.pass_flow})
            != len(row.pass_flow)
            for row in team_rows
        )
    ):
        raise ValueError("Invalid event-profile candidate shape.")
    # Insert non-current rows first, then switch the entire selected set together.
    PlayerSeasonEventProfile.objects.bulk_create(player_rows)
    TeamSeasonEventProfile.objects.bulk_create(team_rows)
    PlayerSeasonEventProfile.objects.filter(competition_season=cs, is_current=True, player_id__in=player_ids).update(is_current=False, superseded_at=timezone.now())
    TeamSeasonEventProfile.objects.filter(competition_season=cs, is_current=True, team_id__in=team_ids).update(is_current=False, superseded_at=timezone.now())
    PlayerSeasonEventProfile.objects.filter(materialized_ingestion_run=run).update(is_current=True)
    TeamSeasonEventProfile.objects.filter(materialized_ingestion_run=run).update(is_current=True)
    return BuildResult(len(player_rows), len(team_rows), player_ids, team_ids)


def _player_row(cs, run, player_id, team_id, split_type, events, minutes, match_minutes):
    summary = _summary(events); grid, _ = _grid(events, minutes, touches_only=True)
    return PlayerSeasonEventProfile(competition_season=cs, player_id=player_id, team_id=team_id, split_type=split_type,
        formula_version=FORMULA_VERSION, materialized_ingestion_run=run, observed_match_count=len({e.provider_match_id for e in events}),
        observed_event_minutes=_event_minutes(events, match_minutes), minutes=minutes, action_grid=grid, is_current=False, **summary)


def _team_row(cs, run, team_id, events, by_match):
    summary = _summary(events); grid, _ = _grid(events, 0, touches_only=True)
    match_ids = {event.provider_match_id for event in events}
    opponents = [
        event
        for match_id in match_ids
        for event in by_match[match_id]
        if event.team_id != team_id
    ]
    opponent_grid, _ = _grid(opponents, 0, touches_only=True); against = _summary(opponents)
    observed = len({e.provider_match_id for e in events})
    expected = (
        cs.whoscored_expected_match_count * 2 / cs.expected_team_count
        if cs.whoscored_expected_match_count and cs.expected_team_count
        else None
    )
    expected_int = round(expected) if expected is not None else None
    return TeamSeasonEventProfile(competition_season=cs, team_id=team_id, formula_version=FORMULA_VERSION,
        materialized_ingestion_run=run, observed_match_count=observed, expected_match_count=expected_int,
        coverage=min(1.0, observed / expected_int) if expected_int else None, action_grid=grid, opponent_action_grid=opponent_grid,
        pass_flow=_pass_flow(events), is_current=False, **{k: v for k, v in summary.items() if k not in {"average_touch_x", "average_touch_y", "shots", "goals", "big_chance_shots"}},
        shots_for=summary["shots"], goals_for=summary["goals"], big_chance_shots_for=summary["big_chance_shots"],
        shots_against=against["shots"], goals_against=against["goals"], big_chance_shots_against=against["big_chance_shots"])
