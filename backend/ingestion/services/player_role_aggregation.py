"""Frozen compact aggregation contract for player role feature materialization.

This module owns data shapes and merge semantics only. Match-batch readers and
row classification belong to the Batch 3 implementations.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
import json
from typing import Any, Iterable, Mapping

from ingestion.services.player_state_comparison import metric_rate, percentage, team_relative_shares
from ingestion.services.whoscored_normalization import ACTION_GRID_COLUMNS, ACTION_GRID_ROWS


STATE_NAMES = ("losing", "drawing", "winning")
DEFAULT_MATCH_BATCH_SIZE = 5
TRANSITION_STAGE_NAMES = (
    "origin_recovery", "escape", "advancement", "destabilisation",
    "creation", "contest", "terminal", "support",
)
TRANSITION_EVIDENCE_LIMIT = 25

# These are the complete scalar projections permitted at the match-batch boundary.
# Batch readers use values()/values_list(); no foreign-key model object is required.
MATCH_COLUMNS = (
    "id", "kickoff_at", "home_team_id", "away_team_id", "home_provider_team_id",
    "away_provider_team_id",
)
PROFILE_COLUMNS = ("id", "competition_season_id", "player_id", "team_id")
SUPPORTING_METRIC_COLUMNS = (
    "canonical_player_id", "native_position", "position_group", "minutes",
    "xg_per_90", "xa_per_90", "key_passes_per_90", "successful_dribbles_per_90",
)
EVENT_COLUMNS = (
    "id", "provider_match_id", "event_index", "provider_team_id", "team_id",
    "player_id", "period", "match_seconds", "timeline_seconds", "event_type",
    "outcome_successful", "x", "y", "end_x", "end_y", "is_touch",
    "is_key_pass", "is_shot_assist", "is_intentional_assist", "is_cross",
    "is_long_ball", "is_through_ball", "is_throw_in", "is_corner",
    "is_free_kick", "is_set_piece", "is_big_chance", "is_defensive",
    "shot_situation", "shot_outcome", "scoring_provider_team_id",
    "home_score_before", "away_score_before", "home_score_after",
    "away_score_after", "game_state_before", "game_state_after",
    "is_progressive_pass", "is_final_third_entry", "is_box_entry",
    "is_goal_disallowed", "is_deleted_event",
)
CARRY_COLUMNS = (
    "id", "provider_match_id", "start_event_index", "end_event_index", "team_id",
    "player_id", "match_seconds", "x", "y", "end_x", "end_y",
    "is_progressive_carry", "is_final_third_entry", "is_box_entry",
)
EXPOSURE_COLUMNS = (
    "id", "player_interval__participation__provider_match_id",
    "player_interval__participation__team_id", "player_interval__participation__player_id",
    "team_episode_id", "team_episode__episode_index", "start_second", "end_second",
    "coarse_state", "goal_difference", "phase", "provenance",
)
TEAM_EPISODE_COLUMNS = (
    "id", "provider_match_id", "focal_team_id", "episode_index", "start_second",
    "end_second", "state", "previous_state", "goal_difference", "phase",
    "draw_provenance", "state_entry_second", "entry_event_id",
)
POSSESSION_COLUMNS = (
    "id", "provider_match_id", "possession_index", "identity", "provider_team_id",
    "team_id", "start_second", "end_second", "is_ambiguous", "is_counter_launch",
    "counter_final_third_arrival", "counter_box_arrival", "counter_shot",
    "counter_outcome", "state_segments",
)
POSSESSION_EVENT_COLUMNS = (
    "id", "possession_id", "event_id", "sequence", "is_control_action",
    "is_settled_defensive_action",
)
POSSESSION_PARTICIPANT_COLUMNS = (
    "id", "possession_id", "player_id", "first_event_index", "action_count",
)

DETERMINISTIC_ORDERING = {
    "matches": ("kickoff_at", "id"),
    "events": ("provider_match_id", "event_index", "id"),
    "carries": ("provider_match_id", "start_event_index", "id"),
    "exposures": (
        "player_interval__participation__provider_match_id",
        "player_interval__participation__team_id",
        "player_interval__participation__player_id",
        "start_second", "end_second", "id",
    ),
    "team_episodes": ("provider_match_id", "focal_team_id", "episode_index", "id"),
    "possessions": ("provider_match_id", "possession_index", "id"),
    "possession_events": ("possession_id", "sequence", "event_id", "id"),
    "possession_participants": ("possession_id", "first_event_index", "player_id", "id"),
}


@dataclass(frozen=True, slots=True)
class CompactMatchBatch:
    """Ephemeral scalar rows for at most ``DEFAULT_MATCH_BATCH_SIZE`` matches."""

    matches: tuple[Mapping[str, Any], ...]
    events: tuple[Mapping[str, Any], ...] = ()
    carries: tuple[Mapping[str, Any], ...] = ()
    exposures: tuple[Mapping[str, Any], ...] = ()
    team_episodes: tuple[Mapping[str, Any], ...] = ()
    possessions: tuple[Mapping[str, Any], ...] = ()
    possession_events: tuple[Mapping[str, Any], ...] = ()
    possession_participants: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        match_ids = tuple(int(row["id"]) for row in self.matches)
        if not match_ids:
            raise ValueError("A compact match batch cannot be empty.")
        if len(match_ids) > DEFAULT_MATCH_BATCH_SIZE:
            raise ValueError(
                f"A compact match batch is limited to {DEFAULT_MATCH_BATCH_SIZE} matches."
            )
        if len(match_ids) != len(set(match_ids)):
            raise ValueError("A compact match batch contains duplicate matches.")
        allowed = set(match_ids)
        scoped_rows = (
            ("events", self.events, "provider_match_id"),
            ("carries", self.carries, "provider_match_id"),
            (
                "exposures",
                self.exposures,
                "player_interval__participation__provider_match_id",
            ),
            ("team episodes", self.team_episodes, "provider_match_id"),
            ("possessions", self.possessions, "provider_match_id"),
        )
        for label, rows, match_key in scoped_rows:
            if any(int(row[match_key]) not in allowed for row in rows):
                raise ValueError(f"Compact {label} rows include a match outside the batch.")

    @property
    def match_ids(self) -> tuple[int, ...]:
        return tuple(int(row["id"]) for row in self.matches)


SUMMARY_FIELDS = (
    "touches", "actions", "pass_attempts", "pass_completions", "progressive_passes",
    "progressive_carries", "progressive_actions", "carries", "shots", "goals",
    "big_chance_shots", "take_ons", "final_third_entries", "box_entries",
    "key_passes", "crosses", "long_balls", "defensive_actions", "recoveries",
    "tackles", "interceptions", "clearances",
)
GEOMETRY_FIELDS = (
    "open_play_events", "touches", "passes", "completed_passes", "central_touches",
    "advanced_actions", "advanced_touches", "box_touches", "shots", "key_passes",
    "line_breaking_passes", "build_up_passes", "build_up_progressive_passes",
    "central_progressive_passes", "dangerous_entries", "long_progressive_passes",
    "defensive_actions", "deep_defensive_actions", "protective_interventions",
    "ball_wins", "tackles_interceptions", "aerials", "turnovers",
    "set_piece_actions", "set_piece_creation", "sweeper_actions", "saves",
    "close_range_saves",
)
GEOMETRY_RATE_FIELDS = (
    "touches", "passes", "line_breaking_passes", "box_touches", "shots", "key_passes",
    "defensive_actions", "ball_wins", "deep_defensive_actions", "aerials", "turnovers",
    "sweeper_actions", "saves",
)
SCORE_EVENT_FIELDS = (
    "goals", "state_changing_goals", "winning_state_goals", "equalising_goals",
    "restored_draw_winning_goals", "surrendered_draw_winning_goals",
    "neutral_draw_winning_goals_excluded", "intentional_assists",
    "state_changing_assists", "winning_state_assists", "equalising_assists",
    "restored_draw_winning_assists", "surrendered_draw_winning_assists",
    "neutral_draw_winning_assists_excluded",
)
TRANSITION_COUNTER_FIELDS = (
    "candidate_possessions", "opportunities", "involved_possessions",
    "counter_possessions", "shot_producing_possessions", "box_entry_possessions",
    "final_third_possessions", "big_chance_possessions", "goal_possessions",
    "state_changing_possessions", "ambiguous_excluded",
    "outside_verified_player_interval", "state_or_team_mismatch",
)


def decimal_value(value: int | float | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(slots=True)
class DecimalMeasure:
    total: Decimal = Decimal(0)
    count: int = 0
    positive_count: int = 0

    def add(self, value: int | float | Decimal) -> None:
        converted = decimal_value(value)
        self.total += converted
        self.count += 1
        self.positive_count += converted > 0

    def merge(self, other: "DecimalMeasure") -> "DecimalMeasure":
        self.total += other.total
        self.count += other.count
        self.positive_count += other.positive_count
        return self

    def mean(self, digits: int) -> float | None:
        return round(float(self.total / self.count), digits) if self.count else None


@dataclass(slots=True)
class LocationAccumulator:
    x: Decimal = Decimal(0)
    y: Decimal = Decimal(0)
    count: int = 0

    def add(self, x: int | float | Decimal, y: int | float | Decimal) -> None:
        self.x += decimal_value(x)
        self.y += decimal_value(y)
        self.count += 1

    def merge(self, other: "LocationAccumulator") -> "LocationAccumulator":
        self.x += other.x
        self.y += other.y
        self.count += other.count
        return self

    def to_json(self) -> dict:
        return {
            "x": round(float(self.x / self.count), 4) if self.count else None,
            "y": round(float(self.y / self.count), 4) if self.count else None,
            "sample_size": self.count,
        }


@dataclass(slots=True)
class GridAccumulator:
    counts: list[int] = field(
        default_factory=lambda: [0] * (ACTION_GRID_COLUMNS * ACTION_GRID_ROWS)
    )

    def add(self, index: int, count: int = 1) -> None:
        if not 0 <= index < len(self.counts):
            raise ValueError(f"Grid index {index} is outside the fixed grid.")
        self.counts[index] += count

    def merge(self, other: "GridAccumulator") -> "GridAccumulator":
        if len(self.counts) != len(other.counts):
            raise ValueError("Grid shapes do not match.")
        self.counts = [left + right for left, right in zip(self.counts, other.counts)]
        return self

    def to_json(self, exposure_seconds: int) -> list[dict]:
        total = sum(self.counts)
        return [
            {
                "column": column,
                "row": row,
                "raw_count": self.counts[column * ACTION_GRID_ROWS + row],
                "per_state_minute": (
                    round(self.counts[column * ACTION_GRID_ROWS + row] / (exposure_seconds / 60), 4)
                    if exposure_seconds else None
                ),
                "per_90": (
                    round(self.counts[column * ACTION_GRID_ROWS + row] * 5400 / exposure_seconds, 4)
                    if exposure_seconds else None
                ),
                "share": (
                    round(self.counts[column * ACTION_GRID_ROWS + row] / total, 6)
                    if total else 0.0
                ),
            }
            for column in range(ACTION_GRID_COLUMNS)
            for row in range(ACTION_GRID_ROWS)
        ]


@dataclass(slots=True)
class ExposureAccumulator:
    seconds: int = 0
    match_ids: set[int] = field(default_factory=set)
    episode_keys: set[tuple[int, int]] = field(default_factory=set)

    def add(self, match_id: int, episode_index: int, start_second: int, end_second: int) -> None:
        if end_second <= start_second:
            raise ValueError("Exposure intervals must be positive and half-open.")
        self.seconds += end_second - start_second
        self.match_ids.add(match_id)
        self.episode_keys.add((match_id, episode_index))

    def merge(self, other: "ExposureAccumulator") -> "ExposureAccumulator":
        self.seconds += other.seconds
        self.match_ids.update(other.match_ids)
        self.episode_keys.update(other.episode_keys)
        return self

    def to_json(self) -> dict:
        return {
            "verified_seconds": self.seconds,
            "matches": len(self.match_ids),
            "episodes": len(self.episode_keys),
        }


@dataclass(frozen=True, order=True, slots=True)
class ExposureInterval:
    match_id: int
    team_id: int
    player_id: int
    start_second: int
    end_second: int
    state: str
    episode_index: int

    def __post_init__(self) -> None:
        if self.end_second <= self.start_second:
            raise ValueError("Exposure intervals must satisfy start_second < end_second.")

    def contains(self, second: int | None) -> bool:
        return second is not None and self.start_second <= second < self.end_second


class ExposureIntervalIndex:
    """Keyed player exposure lookup with explicit half-open boundaries."""

    def __init__(self, intervals: Iterable[ExposureInterval] = ()) -> None:
        grouped: dict[tuple[int, int, int], list[ExposureInterval]] = {}
        for interval in intervals:
            key = (interval.match_id, interval.team_id, interval.player_id)
            grouped.setdefault(key, []).append(interval)
        self.intervals = {
            key: tuple(sorted(rows, key=lambda row: (row.start_second, row.end_second, row.episode_index)))
            for key, rows in grouped.items()
        }
        self.starts = {
            key: tuple(row.start_second for row in rows)
            for key, rows in self.intervals.items()
        }

    def find(self, match_id: int, team_id: int, player_id: int, second: int | None) -> ExposureInterval | None:
        if second is None:
            return None
        key = (match_id, team_id, player_id)
        rows = self.intervals.get(key, ())
        index = bisect_right(self.starts.get(key, ()), second) - 1
        return rows[index] if index >= 0 and rows[index].contains(second) else None


@dataclass(slots=True)
class ActionAccumulator:
    counters: Counter = field(default_factory=Counter)
    pass_lengths: DecimalMeasure = field(default_factory=DecimalMeasure)
    pass_forward: DecimalMeasure = field(default_factory=DecimalMeasure)
    carry_lengths: DecimalMeasure = field(default_factory=DecimalMeasure)
    carry_forward: DecimalMeasure = field(default_factory=DecimalMeasure)
    touch_location: LocationAccumulator = field(default_factory=LocationAccumulator)
    touch_grid: GridAccumulator = field(default_factory=GridAccumulator)

    def merge(self, other: "ActionAccumulator") -> "ActionAccumulator":
        self.counters.update(other.counters)
        self.pass_lengths.merge(other.pass_lengths)
        self.pass_forward.merge(other.pass_forward)
        self.carry_lengths.merge(other.carry_lengths)
        self.carry_forward.merge(other.carry_forward)
        self.touch_location.merge(other.touch_location)
        self.touch_grid.merge(other.touch_grid)
        return self

    def summary(self) -> dict:
        return {name: self.counters[name] for name in SUMMARY_FIELDS}

    def to_context(self, exposure_seconds: int) -> dict:
        summary = self.summary()
        return {
            "summary": summary,
            "rates": {name: metric_rate(value, exposure_seconds) for name, value in summary.items()},
            "passing": {
                "attempts": self.counters["pass_attempts"],
                "completed": self.counters["pass_completions"],
                "completion_rate": percentage(self.counters["pass_completions"], self.counters["pass_attempts"]),
                "progressive": self.counters["progressive_passes"],
                "key_passes": self.counters["key_passes"],
                "final_third_entries": self.counters["final_third_entries"],
                "box_entries": self.counters["box_entries"],
                "crosses": self.counters["crosses"],
                "long_balls": self.counters["long_balls"],
                "mean_length_metres": self.pass_lengths.mean(2),
                "mean_forward_metres": self.pass_forward.mean(2),
                "forward_share": percentage(self.pass_forward.positive_count, self.pass_forward.count),
            },
            "carrying": {
                "attempts": self.counters["carries"],
                "progressive": self.counters["progressive_carries"],
                "final_third_entries": self.counters["carry_final_third_entries"],
                "box_entries": self.counters["carry_box_entries"],
                "mean_length_metres": self.carry_lengths.mean(2),
                "mean_forward_metres": self.carry_forward.mean(2),
                "forward_share": percentage(self.carry_forward.positive_count, self.carry_forward.count),
            },
            "touch_location": self.touch_location.to_json(),
            "touch_grid": self.touch_grid.to_json(exposure_seconds),
        }


@dataclass(slots=True)
class GeometryAccumulator:
    counters: Counter = field(default_factory=Counter)
    defensive_x: DecimalMeasure = field(default_factory=DecimalMeasure)
    sweeper_x: DecimalMeasure = field(default_factory=DecimalMeasure)

    def merge(self, other: "GeometryAccumulator") -> "GeometryAccumulator":
        self.counters.update(other.counters)
        self.defensive_x.merge(other.defensive_x)
        self.sweeper_x.merge(other.sweeper_x)
        return self

    def to_json(self, exposure_seconds: int) -> dict:
        values = {name: self.counters[name] for name in GEOMETRY_FIELDS}
        values.update({
            "pass_completion": ratio(self.counters["completed_passes"], self.counters["passes"]),
            "central_touch_share": ratio(self.counters["central_touches"], self.counters["touches"]),
            "advanced_touch_share": ratio(self.counters["advanced_touches"], self.counters["touches"]),
            "box_touch_share": ratio(self.counters["box_touches"], self.counters["touches"]),
            "line_break_frequency": ratio(self.counters["line_breaking_passes"], self.counters["passes"]),
            "defensive_height": self.defensive_x.mean(4),
            "sweeper_height": self.sweeper_x.mean(4),
            "rates_per90": {
                name: round(self.counters[name] * 5400 / exposure_seconds, 4) if exposure_seconds else None
                for name in GEOMETRY_RATE_FIELDS
            },
        })
        return values


def ratio(numerator: int | float, denominator: int | float) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


@dataclass(slots=True)
class StateAccumulator:
    exposure: ExposureAccumulator = field(default_factory=ExposureAccumulator)
    player: ActionAccumulator = field(default_factory=ActionAccumulator)
    team: ActionAccumulator = field(default_factory=ActionAccumulator)

    def merge(self, other: "StateAccumulator") -> "StateAccumulator":
        self.exposure.merge(other.exposure)
        self.player.merge(other.player)
        self.team.merge(other.team)
        return self

    def to_json(self) -> dict:
        player = self.player.to_context(self.exposure.seconds)
        team = self.team.to_context(self.exposure.seconds)
        return {
            "exposure_seconds": self.exposure.seconds,
            "match_count": len(self.exposure.match_ids),
            "episode_count": len(self.exposure.episode_keys),
            "summary": player["summary"],
            "rates": player["rates"],
            "passing": player["passing"],
            "carrying": player["carrying"],
            "touch_location": player["touch_location"],
            "touch_grid": player["touch_grid"],
            "team_touch_location": team["touch_location"],
            "team_action_shares": team_relative_shares(player["summary"], team["summary"]),
        }


@dataclass(slots=True)
class BoundedEvidenceAccumulator:
    limit: int = TRANSITION_EVIDENCE_LIMIT
    rows: dict[tuple[int, int, int, str], str] = field(default_factory=dict)

    def add(self, sort_key: tuple[int, int, int, str], payload: dict) -> None:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        existing = self.rows.get(sort_key)
        self.rows[sort_key] = encoded if existing is None else min(existing, encoded)
        self.trim()

    def trim(self) -> None:
        for key in sorted(self.rows)[self.limit:]:
            del self.rows[key]

    def merge(self, other: "BoundedEvidenceAccumulator") -> "BoundedEvidenceAccumulator":
        if self.limit != other.limit:
            raise ValueError("Evidence limits do not match.")
        for key, encoded in other.rows.items():
            existing = self.rows.get(key)
            self.rows[key] = encoded if existing is None else min(existing, encoded)
        self.trim()
        return self

    def to_json(self) -> list[dict]:
        return [json.loads(self.rows[key]) for key in sorted(self.rows)]


@dataclass(slots=True)
class TransitionAccumulator:
    counters: Counter = field(default_factory=Counter)
    stage_actions: Counter = field(default_factory=Counter)
    stage_possessions: Counter = field(default_factory=Counter)
    evidence: BoundedEvidenceAccumulator = field(default_factory=BoundedEvidenceAccumulator)

    def merge(self, other: "TransitionAccumulator") -> "TransitionAccumulator":
        self.counters.update(other.counters)
        self.stage_actions.update(other.stage_actions)
        self.stage_possessions.update(other.stage_possessions)
        self.evidence.merge(other.evidence)
        return self

    def to_evidence_json(self) -> dict:
        opportunities = self.counters["opportunities"]
        excluded_from_top_level = {
            "candidate_possessions", "outside_verified_player_interval", "state_or_team_mismatch",
        }
        return {
            "available": bool(self.counters["candidate_possessions"]),
            **{
                name: self.counters[name]
                for name in TRANSITION_COUNTER_FIELDS
                if name not in excluded_from_top_level
            },
            "sequence_stages": {
                name: {
                    "actions": self.stage_actions[name],
                    "possessions": self.stage_possessions[name],
                    "rate_per_opportunity": (
                        round(self.stage_possessions[name] / opportunities, 4)
                        if opportunities else None
                    ),
                }
                for name in TRANSITION_STAGE_NAMES
            },
            "sequence_evidence": self.evidence.to_json(),
            "evidence_truncated": self.counters["involved_possessions"] > len(self.evidence.rows),
            "exclusions": {
                "ambiguous_possessions": self.counters["ambiguous_excluded"],
                "outside_verified_player_interval": self.counters["outside_verified_player_interval"],
                "state_or_team_mismatch": self.counters["state_or_team_mismatch"],
            },
        }

    def to_compact_json(self) -> dict:
        return {
            "available": bool(self.counters["candidate_possessions"]),
            "opportunities": self.counters["opportunities"],
            "involved_possessions": self.counters["involved_possessions"],
            "counter_possessions": self.counters["counter_possessions"],
            "shot_producing_possessions": self.counters["shot_producing_possessions"],
            "final_third_possessions": self.counters["final_third_possessions"],
            "advancement_actions": self.stage_actions["advancement"],
            "escape_actions": self.stage_actions["escape"],
        }


@dataclass(frozen=True, slots=True)
class TeamStateKey:
    match_id: int
    team_id: int
    state: str


@dataclass(slots=True)
class TeamStateAccumulator:
    actions: ActionAccumulator = field(default_factory=ActionAccumulator)
    geometry: GeometryAccumulator = field(default_factory=GeometryAccumulator)
    transition_opportunities: int = 0

    def merge(self, other: "TeamStateAccumulator") -> "TeamStateAccumulator":
        self.actions.merge(other.actions)
        self.geometry.merge(other.geometry)
        self.transition_opportunities += other.transition_opportunities
        return self


@dataclass(slots=True)
class PlayerRoleFeatureAccumulator:
    player_id: int
    team_id: int
    competition_season_id: int
    position_group: str = "UNK"
    recorded_position: str = ""
    supporting_metrics: dict = field(default_factory=dict)
    exposure: ExposureAccumulator = field(default_factory=ExposureAccumulator)
    overall_player: ActionAccumulator = field(default_factory=ActionAccumulator)
    overall_team: ActionAccumulator = field(default_factory=ActionAccumulator)
    player_geometry: GeometryAccumulator = field(default_factory=GeometryAccumulator)
    team_geometry: GeometryAccumulator = field(default_factory=GeometryAccumulator)
    states: dict[str, StateAccumulator] = field(
        default_factory=lambda: {name: StateAccumulator() for name in STATE_NAMES}
    )
    transition: TransitionAccumulator = field(default_factory=TransitionAccumulator)
    score_events: Counter = field(default_factory=Counter)

    @property
    def identity(self) -> tuple[int, int, int]:
        return self.competition_season_id, self.player_id, self.team_id

    def merge(self, other: "PlayerRoleFeatureAccumulator") -> "PlayerRoleFeatureAccumulator":
        if self.identity != other.identity:
            raise ValueError("Player-team-season accumulator identities do not match.")
        if (self.position_group, self.recorded_position, self.supporting_metrics) != (
            other.position_group, other.recorded_position, other.supporting_metrics
        ):
            raise ValueError("Accumulator metadata does not match.")
        self.exposure.merge(other.exposure)
        self.overall_player.merge(other.overall_player)
        self.overall_team.merge(other.overall_team)
        self.player_geometry.merge(other.player_geometry)
        self.team_geometry.merge(other.team_geometry)
        for state in STATE_NAMES:
            self.states[state].merge(other.states[state])
        self.transition.merge(other.transition)
        self.score_events.update(other.score_events)
        return self

    def to_feature_json(self) -> dict:
        from ingestion.services.player_role_features import spatial_state_features

        overall_player = self.overall_player.to_context(self.exposure.seconds)
        overall_team = self.overall_team.to_context(self.exposure.seconds)
        states = {name: self.states[name].to_json() for name in STATE_NAMES}
        return {
            "identity": {
                "player_id": self.player_id,
                "team_id": self.team_id,
                "competition_season_id": self.competition_season_id,
            },
            "position": {
                "group": self.position_group,
                "recorded": self.recorded_position,
                "average_touch": overall_player["touch_location"],
            },
            "exposure": self.exposure.to_json(),
            "overall": {
                "summary": overall_player["summary"],
                "passing": overall_player["passing"],
                "carrying": overall_player["carrying"],
                "touch_location": overall_player["touch_location"],
                "team_action_shares": team_relative_shares(
                    overall_player["summary"], overall_team["summary"]
                ),
                "geometry": self.player_geometry.to_json(self.exposure.seconds),
                "team_geometry": self.team_geometry.to_json(self.exposure.seconds),
            },
            "states": states,
            "state_spatial": spatial_state_features(states),
            "transitions": self.transition.to_compact_json(),
            "score_events": {name: self.score_events[name] for name in SCORE_EVENT_FIELDS},
            "supporting_metrics": self.supporting_metrics.copy(),
        }
