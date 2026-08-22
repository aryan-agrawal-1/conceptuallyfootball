from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping, Sequence

from django.db import transaction

from ingestion.models import (
    IngestionRun,
    MatchEventBodyPart,
    MatchEventPeriod,
    MatchEventShotOutcome,
    MatchEventShotSituation,
    MatchEventType,
    ProviderMatch,
    ProviderMatchEvent,
)


RAW_PAYLOAD_SCHEMA_VERSION = 1
NORMALIZATION_SCHEMA_VERSION = 2
ACTION_GRID_COLUMNS = 24
ACTION_GRID_ROWS = 16
TEAM_ZONE_COLUMNS = 5
TEAM_ZONE_ROWS = 3

SHOT_EVENT_NAMES = frozenset({"Goal", "MissedShots", "SavedShot", "ShotOnPost"})
ADMINISTRATIVE_EVENT_NAMES = frozenset(
    {
        "Start",
        "End",
        "Out",
        "CornerAwarded",
        "Turnover",
        "PlayerRetired",
        "PlayerReturns",
        "KeeperBecomesPlayer",
        "PlayerBecomesGoalkeeper",
        "ConditionChange",
        "OfficialChange",
        "StartDelay",
        "EndDelay",
        "TeamSetUp",
        "FormationSet",
        "FormationChange",
        "PlayerOff",
        "PlayerOn",
        "PlayerChangedPosition",
        "PlayerChangedJerseyNumber",
        "DeletedEvent",
        "FormationPosition",
        "Error",
        "ChanceMissed",
        "Resume",
        "ContentiousRefereeDecision",
        "RefereeDropBall",
        "InjuryTimeAnnouncement",
        "CoachSetup",
        "DelayedStart",
        "EarlyEnd",
        "CoverageInterruption",
    }
)
SAVE_EVENT_NAMES = frozenset(
    {
        "KeeperPickup",
        "Save",
        "Claim",
        "Smother",
        "Punch",
        "KeeperSweeper",
        "CrossNotClaimed",
        "PenaltyFaced",
    }
)
OFFSIDE_EVENT_NAMES = frozenset({"OffsideGiven", "OffsideProvoked"})
SUBSTITUTION_EVENT_NAMES = frozenset({"SubstitutionOff", "SubstitutionOn"})

EVENT_TYPE_BY_NAME = {
    "Pass": MatchEventType.PASS,
    "BallTouch": MatchEventType.BALL_TOUCH,
    "TakeOn": MatchEventType.TAKE_ON,
    "BallRecovery": MatchEventType.BALL_RECOVERY,
    "Tackle": MatchEventType.TACKLE,
    "Interception": MatchEventType.INTERCEPTION,
    "Clearance": MatchEventType.CLEARANCE,
    "BlockedPass": MatchEventType.BLOCKED_PASS,
    "Aerial": MatchEventType.AERIAL,
    "Challenge": MatchEventType.CHALLENGE,
    "Dispossessed": MatchEventType.DISPOSSESSED,
    "Foul": MatchEventType.FOUL,
    "FoulThrowIn": MatchEventType.FOUL,
    "Card": MatchEventType.CARD,
    "RescindedCard": MatchEventType.CARD,
    "OtherBallContact": MatchEventType.BALL_TOUCH,
    "FiftyFifty": MatchEventType.CHALLENGE,
    "FailedToBlock": MatchEventType.CHALLENGE,
    "AttemptedTackle": MatchEventType.TACKLE,
    "MissedChallenge": MatchEventType.CHALLENGE,
    "GoodSkill": MatchEventType.TAKE_ON,
    "ShieldBallOpp": MatchEventType.DISPOSSESSED,
    "ShieldBallOutOfPlay": MatchEventType.DISPOSSESSED,
}

TYPED_QUALIFIER_NAMES = frozenset(
    {
        "Cross",
        "Longball",
        "Chipped",
        "HeadPass",
        "Throughball",
        "ThrowIn",
        "CornerTaken",
        "FreekickTaken",
        "SetPiece",
        "RegularPlay",
        "BigChance",
        "KeyPass",
        "ShotAssist",
        "IntentionalGoalAssist",
        "IntentionalAssist",
        "RightFoot",
        "LeftFoot",
        "Head",
        "OtherBodyPart",
        "Blocked",
        "OpenPlay",
        "Penalty",
        "FromCorner",
        "DirectFreekick",
        "FastBreak",
        "Defensive",
    }
)
KNOWN_UNTYPED_QUALIFIER_NAMES = frozenset(
    {
        "Length",
        "Angle",
        "RelatedEventId",
        "PassEndX",
        "PassEndY",
        "GoalMouthY",
        "GoalMouthZ",
        "BlockedX",
        "BlockedY",
        "Assisted",
        "LeadingToAttempt",
        "LeadingToGoal",
        "OppositeRelatedEvent",
        "PlayerPosition",
        "Zone",
        "OutOfBox",
        "PenaltyArea",
        "SixYardBox",
        "BoxLeft",
        "BoxRight",
        "BoxCentre",
        "High",
        "Low",
        "Normal",
        "Standing",
        "Diving",
        "NoTouch",
        "PullBack",
        # Current Opta/WhoScored match-centre qualifier vocabulary that v1
        # deliberately preserves only in the private raw payload.
        "AerialFoul",
        "BigChanceCreated",
        "BlockedCross",
        "CaptainPlayerId",
        "Collected",
        "DeepBoxLeft",
        "DeepBoxRight",
        "DivingSave",
        "Feet",
        "FirstTouch",
        "Foul",
        "FromShotOffTarget",
        "GoalDisallowed",
        "GoalKick",
        "Hands",
        "HighCentre",
        "HighClaim",
        "HighLeft",
        "HighRight",
        "IndirectFreekickTaken",
        "IndividualPlay",
        "InvolvedPlayers",
        "JerseyNumber",
        "KeeperMissed",
        "KeeperSaved",
        "KeeperSaveInSixYard",
        "KeeperSaveInTheBox",
        "KeeperSaveObox",
        "KeeperThrow",
        "LastMan",
        "LayOff",
        "LowCentre",
        "LowLeft",
        "LowRight",
        "MissHigh",
        "MissLeft",
        "MissRight",
        "Offensive",
        "OneOnOne",
        "OutOfBoxCentre",
        "OutOfBoxDeepLeft",
        "OutOfBoxDeepRight",
        "OutOfBoxLeft",
        "OutOfBoxRight",
        "OutfielderBlock",
        "OverRun",
        "OwnGoal",
        "ParriedDanger",
        "ParriedSafe",
        "PlayerCaughtOffside",
        "Red",
        "SavedOffline",
        "SecondYellow",
        "SixYardBlock",
        "SmallBoxCentre",
        "SmallBoxLeft",
        "SmallBoxRight",
        "StandingSave",
        "TeamFormation",
        "TeamPlayerFormation",
        "ThirtyFivePlusCentre",
        "ThrowinSetPiece",
        "VoidYellowCard",
        "Volley",
        "Yellow",
        "FormationSlot",
    }
)

ACTION_EVENT_TYPES = frozenset(
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
        MatchEventType.DISPOSSESSED,
    }
)
DEFENSIVE_EVENT_TYPES = frozenset(
    {
        MatchEventType.BALL_RECOVERY,
        MatchEventType.TACKLE,
        MatchEventType.INTERCEPTION,
        MatchEventType.CLEARANCE,
        MatchEventType.BLOCKED_PASS,
    }
)


class WhoScoredNormalizationError(ValueError):
    def __init__(self, diagnostics: "NormalizationDiagnostics") -> None:
        self.diagnostics = diagnostics
        super().__init__("WhoScored payload failed normalization validation.")


@dataclass(frozen=True)
class NormalizationPolicy:
    minimum_event_count: int = 100
    unknown_event_tolerance: int = 5
    unknown_qualifier_tolerance: int = 10
    minimum_orientation_shots: int = 3
    minimum_shot_median_x: float = 50.0


@dataclass
class NormalizationDiagnostics:
    schema_version: int = NORMALIZATION_SCHEMA_VERSION
    source_event_count: int = 0
    normalized_event_count: int = 0
    unknown_event_types: dict[str, int] = field(default_factory=dict)
    unknown_qualifiers: dict[str, int] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"valid": self.valid}


@dataclass(frozen=True)
class NormalizedMatchEvent:
    event_index: int
    provider_event_id: str | None
    provider_team_id: str
    provider_player_id: str | None
    period: int
    minute: int
    second: int
    expanded_minute: int | None
    match_seconds: int
    event_type: int
    source_event_type_id: int | None
    outcome_successful: bool | None
    x: int | None
    y: int | None
    end_x: int | None
    end_y: int | None
    goal_mouth_y: int | None
    goal_mouth_z: int | None
    blocked_x: int | None
    blocked_y: int | None
    is_touch: bool
    is_key_pass: bool
    is_shot_assist: bool
    is_intentional_assist: bool
    is_cross: bool
    is_long_ball: bool
    is_chipped: bool
    is_head_pass: bool
    is_through_ball: bool
    is_throw_in: bool
    is_corner: bool
    is_free_kick: bool
    is_set_piece: bool
    is_regular_play: bool
    is_big_chance: bool
    is_defensive: bool
    body_part: int
    shot_situation: int
    shot_outcome: int
    is_progressive_pass: bool
    is_final_third_entry: bool
    is_box_entry: bool

    def model_values(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedMatch:
    schema_version: int
    source_checksum: str
    events: tuple[NormalizedMatchEvent, ...]
    diagnostics: NormalizationDiagnostics
    team_names: tuple[tuple[str, str], ...] = ()
    player_names: tuple[tuple[str, str], ...] = ()

    def canonical_bytes(self) -> bytes:
        value = {
            "schema_version": self.schema_version,
            "source_checksum": self.source_checksum,
            "events": [event.model_values() for event in self.events],
        }
        return canonical_json_bytes(value)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def wrap_raw_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": RAW_PAYLOAD_SCHEMA_VERSION,
        "provider": "whoscored",
        "payload": payload,
    }


def canonical_raw_payload_bytes(payload: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(wrap_raw_payload(payload))


def unwrap_raw_payload(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if "schema_version" not in value and "payload" not in value:
        return value
    if value.get("schema_version") != RAW_PAYLOAD_SCHEMA_VERSION:
        raise ValueError(f"Unsupported WhoScored raw schema version: {value.get('schema_version')!r}.")
    if value.get("provider") != "whoscored":
        raise ValueError("Raw payload wrapper is not for the WhoScored provider.")
    payload = value.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("Raw payload wrapper has no object payload.")
    return payload


def encode_coordinate(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Coordinate must be numeric.")
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("Coordinate must be numeric.") from error
    if not decimal_value.is_finite() or not Decimal("0") <= decimal_value <= Decimal("100"):
        raise ValueError("Coordinate must be within 0..100.")
    return int((decimal_value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def decode_coordinate(value: int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10000:
        raise ValueError("Scaled coordinate must be an integer within 0..10000.")
    return value / 100


def progressive_action(start_x: int, start_y: int, end_x: int, end_y: int) -> bool:
    values = (start_x, start_y, end_x, end_y)
    if any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10000 for value in values):
        raise ValueError("Progressive-action coordinates must be scaled integers within 0..10000.")
    start_m = (start_x / 10000 * 105, start_y / 10000 * 68)
    end_m = (end_x / 10000 * 105, end_y / 10000 * 68)
    start_distance = math.dist(start_m, (105, 34))
    end_distance = math.dist(end_m, (105, 34))
    progress = start_distance - end_distance
    if start_x < 5000 and end_x < 5000:
        return progress >= 30
    if start_x < 5000 <= end_x:
        return progress >= 15
    return progress >= 10


def progressive_pass(start_x: int, start_y: int, end_x: int, end_y: int) -> bool:
    return progressive_action(start_x, start_y, end_x, end_y)


def final_third_entry(
    successful: bool | None,
    start_x: int | None,
    end_x: int | None,
) -> bool:
    return successful is True and start_x is not None and end_x is not None and start_x < 6670 <= end_x


def inside_opposition_box(x: int, y: int) -> bool:
    return x >= 8350 and 2110 <= y <= 7890


def box_entry(
    successful: bool | None,
    start_x: int | None,
    start_y: int | None,
    end_x: int | None,
    end_y: int | None,
) -> bool:
    if successful is not True or None in (start_x, start_y, end_x, end_y):
        return False
    return not inside_opposition_box(start_x, start_y) and inside_opposition_box(end_x, end_y)


def grid_assignment(x: int, y: int, columns: int, rows: int) -> tuple[int, int, int]:
    if columns <= 0 or rows <= 0:
        raise ValueError("Grid dimensions must be positive.")
    if any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10000 for value in (x, y)):
        raise ValueError("Grid coordinates must be scaled integers within 0..10000.")
    column = min(x * columns // 10000, columns - 1)
    row = min(y * rows // 10000, rows - 1)
    return column, row, column * rows + row


def action_grid_assignment(x: int, y: int) -> tuple[int, int, int]:
    return grid_assignment(x, y, ACTION_GRID_COLUMNS, ACTION_GRID_ROWS)


def team_zone_assignment(x: int, y: int) -> tuple[int, int, int]:
    return grid_assignment(x, y, TEAM_ZONE_COLUMNS, TEAM_ZONE_ROWS)


def is_action_event(event_type: int, *, defensive_qualifier: bool = False) -> bool:
    if event_type in {MatchEventType.AERIAL, MatchEventType.CHALLENGE}:
        return defensive_qualifier
    return event_type in ACTION_EVENT_TYPES


def is_defensive_event(event_type: int, *, defensive_qualifier: bool = False) -> bool:
    return event_type in DEFENSIVE_EVENT_TYPES or (
        event_type in {MatchEventType.AERIAL, MatchEventType.CHALLENGE}
        and defensive_qualifier
    )


def parse_match_payload(
    wrapped_or_payload: Mapping[str, Any],
    *,
    policy: NormalizationPolicy | None = None,
    changed_payload: bool = False,
) -> NormalizedMatch:
    active_policy = policy or NormalizationPolicy()
    diagnostics = NormalizationDiagnostics()
    try:
        payload = unwrap_raw_payload(wrapped_or_payload)
    except ValueError as error:
        diagnostics.errors.append({"code": "invalid_wrapper", "message": str(error)})
        raise WhoScoredNormalizationError(diagnostics) from error

    validate_match_structure(payload, diagnostics)
    source_events = payload.get("events")
    if not isinstance(source_events, list):
        raise WhoScoredNormalizationError(diagnostics)
    diagnostics.source_event_count = len(source_events)

    ordered_events = []
    for source_index, event in enumerate(source_events):
        if not isinstance(event, Mapping):
            diagnostics.errors.append(
                {
                    "code": "invalid_event",
                    "event_index": source_index,
                    "message": "Event must be an object.",
                }
            )
            continue
        ordered_events.append((event_sort_key(event, source_index), source_index, event))
    ordered_events.sort(key=lambda row: row[0])

    normalized_events: list[NormalizedMatchEvent] = []
    for event_index, (_, source_index, event) in enumerate(ordered_events):
        normalized = normalize_event(event_index, source_index, event, diagnostics)
        if normalized is not None:
            normalized_events.append(normalized)
    diagnostics.normalized_event_count = len(normalized_events)

    validate_match_level(
        payload,
        diagnostics,
        active_policy,
        changed_payload=changed_payload,
        normalized_events=normalized_events,
    )
    if not diagnostics.valid:
        raise WhoScoredNormalizationError(diagnostics)

    source_checksum = hashlib.sha256(canonical_raw_payload_bytes(payload)).hexdigest()
    team_names = tuple(
        (str(team["teamId"]), str(team.get("name") or ""))
        for side in ("home", "away")
        if isinstance((team := payload.get(side)), Mapping)
        and team.get("teamId") not in (None, "")
    )
    player_dictionary = payload.get("playerIdNameDictionary")
    player_names = (
        tuple(
            sorted(
                (str(provider_player_id), str(player_name or ""))
                for provider_player_id, player_name in player_dictionary.items()
            )
        )
        if isinstance(player_dictionary, Mapping)
        else ()
    )
    return NormalizedMatch(
        schema_version=NORMALIZATION_SCHEMA_VERSION,
        source_checksum=source_checksum,
        events=tuple(normalized_events),
        diagnostics=diagnostics,
        team_names=team_names,
        player_names=player_names,
    )


def validate_match_structure(
    payload: Mapping[str, Any],
    diagnostics: NormalizationDiagnostics,
) -> None:
    for field_name in ("home", "away", "events"):
        if field_name not in payload:
            diagnostics.errors.append(
                {"code": "missing_match_field", "field": field_name}
            )
    for side in ("home", "away"):
        team = payload.get(side)
        if not isinstance(team, Mapping) or team.get("teamId") in (None, ""):
            diagnostics.errors.append(
                {"code": "missing_team_id", "field": f"{side}.teamId"}
            )
    if "events" in payload and not isinstance(payload.get("events"), list):
        diagnostics.errors.append(
            {"code": "invalid_events", "message": "events must be a list."}
        )


def event_sort_key(event: Mapping[str, Any], source_index: int) -> tuple[int, int, int, int, int]:
    period = optional_int(mapping_value(event.get("period"), "value")) or 0
    minute = optional_int(event.get("expandedMinute"))
    if minute is None:
        minute = optional_int(event.get("minute")) or 0
    second = optional_int(event.get("second")) or 0
    event_id = optional_int(event.get("eventId"))
    return period, minute, second, event_id if event_id is not None else source_index, source_index


def normalize_event(
    event_index: int,
    source_index: int,
    event: Mapping[str, Any],
    diagnostics: NormalizationDiagnostics,
) -> NormalizedMatchEvent | None:
    event_name = display_name(event.get("type"))
    source_event_type_id = optional_int(mapping_value(event.get("type"), "value"))
    event_type = normalized_event_type(event_name)
    if event_type == MatchEventType.UNKNOWN:
        diagnostic_key = f"{source_event_type_id if source_event_type_id is not None else '?'}:{event_name or '?'}"
        increment(diagnostics.unknown_event_types, diagnostic_key)

    required_values = {
        "teamId": event.get("teamId"),
        "type": event.get("type"),
        "period": event.get("period"),
        "minute": event.get("minute"),
    }
    missing = [name for name, value in required_values.items() if value in (None, "")]
    if missing:
        diagnostics.errors.append(
            {
                "code": "missing_event_fields",
                "event_index": source_index,
                "fields": missing,
            }
        )
        return None

    minute = strict_nonnegative_int(event.get("minute"))
    # Current OffsideGiven companion events consistently omit seconds. They
    # are minute-granularity annotations rather than the primary offside event.
    second_value = (
        0
        if event_name == "OffsideGiven" and event.get("second") in (None, "")
        else event.get("second")
    )
    second = strict_nonnegative_int(second_value)
    period = normalized_period(event.get("period"))
    expanded_minute = optional_int(event.get("expandedMinute"))
    if (
        minute is None
        or minute > 65535
        or second is None
        or second > 59
        or expanded_minute is not None
        and not 0 <= expanded_minute <= 65535
    ):
        diagnostics.errors.append(
            {
                "code": "invalid_event_clock",
                "event_index": source_index,
                "minute": event.get("minute"),
                "second": event.get("second"),
            }
        )
        return None
    provider_event_id = optional_string(event.get("id"))
    provider_team_id = str(event.get("teamId"))
    provider_player_id = optional_string(event.get("playerId"))
    identifiers = {
        "id": provider_event_id,
        "teamId": provider_team_id,
        "playerId": provider_player_id,
    }
    oversized = [name for name, value in identifiers.items() if value is not None and len(value) > 64]
    if oversized:
        diagnostics.errors.append(
            {
                "code": "identifier_too_long",
                "event_index": source_index,
                "fields": oversized,
            }
        )
        return None
    if source_event_type_id is not None and not 0 <= source_event_type_id <= 65535:
        diagnostics.errors.append(
            {
                "code": "invalid_source_event_type_id",
                "event_index": source_index,
                "value": source_event_type_id,
            }
        )
        return None

    coordinates: dict[str, int | None] = {}
    for source_name, target_name in (
        ("x", "x"),
        ("y", "y"),
        ("endX", "end_x"),
        ("endY", "end_y"),
        ("goalMouthY", "goal_mouth_y"),
        ("goalMouthZ", "goal_mouth_z"),
        ("blockedX", "blocked_x"),
        ("blockedY", "blocked_y"),
    ):
        try:
            coordinates[target_name] = encode_coordinate(event.get(source_name))
        except ValueError as error:
            diagnostics.errors.append(
                {
                    "code": "invalid_coordinate",
                    "event_index": source_index,
                    "field": source_name,
                    "value": event.get(source_name),
                    "message": str(error),
                }
            )
            return None

    qualifier_names = qualifier_name_set(event.get("qualifiers"), source_index, diagnostics)
    if event_type == MatchEventType.SHOT and "OwnGoal" in qualifier_names:
        event_type = MatchEventType.OWN_GOAL
    successful = normalized_outcome(event.get("outcomeType"))
    start_x, start_y = coordinates["x"], coordinates["y"]
    end_x, end_y = coordinates["end_x"], coordinates["end_y"]
    pass_with_coordinates = (
        event_type == MatchEventType.PASS
        and None not in (start_x, start_y, end_x, end_y)
    )
    return NormalizedMatchEvent(
        event_index=event_index,
        provider_event_id=provider_event_id,
        provider_team_id=provider_team_id,
        provider_player_id=provider_player_id,
        period=period,
        minute=minute,
        second=second,
        expanded_minute=expanded_minute,
        match_seconds=minute * 60 + second,
        event_type=event_type,
        source_event_type_id=source_event_type_id,
        outcome_successful=successful,
        **coordinates,
        is_touch=event.get("isTouch") is True,
        is_key_pass=event.get("isKeyPass") is True or "KeyPass" in qualifier_names,
        is_shot_assist=event.get("isShotAssist") is True or "ShotAssist" in qualifier_names,
        is_intentional_assist=bool(
            event.get("isGoalAssist") is True
            or qualifier_names & {"IntentionalGoalAssist", "IntentionalAssist"}
        ),
        is_cross="Cross" in qualifier_names,
        is_long_ball="Longball" in qualifier_names,
        is_chipped="Chipped" in qualifier_names,
        is_head_pass="HeadPass" in qualifier_names,
        is_through_ball="Throughball" in qualifier_names,
        is_throw_in="ThrowIn" in qualifier_names,
        is_corner="CornerTaken" in qualifier_names,
        is_free_kick="FreekickTaken" in qualifier_names,
        is_set_piece=bool(
            qualifier_names
            & {
                "SetPiece",
                "Penalty",
                "FromCorner",
                "CornerTaken",
                "DirectFreekick",
                "FreekickTaken",
            }
        ),
        is_regular_play=bool(qualifier_names & {"RegularPlay", "OpenPlay"}),
        is_big_chance="BigChance" in qualifier_names,
        is_defensive="Defensive" in qualifier_names,
        body_part=normalized_body_part(qualifier_names),
        shot_situation=normalized_shot_situation(qualifier_names),
        shot_outcome=normalized_shot_outcome(event_name, qualifier_names),
        is_progressive_pass=bool(
            pass_with_coordinates
            and progressive_pass(start_x, start_y, end_x, end_y)
        ),
        is_final_third_entry=bool(
            event_type == MatchEventType.PASS
            and final_third_entry(successful, start_x, end_x)
        ),
        is_box_entry=bool(
            event_type == MatchEventType.PASS
            and box_entry(successful, start_x, start_y, end_x, end_y)
        ),
    )


def validate_match_level(
    payload: Mapping[str, Any],
    diagnostics: NormalizationDiagnostics,
    policy: NormalizationPolicy,
    *,
    changed_payload: bool,
    normalized_events: Sequence[NormalizedMatchEvent],
) -> None:
    if diagnostics.source_event_count < policy.minimum_event_count:
        diagnostics.errors.append(
            {
                "code": "implausibly_low_event_count",
                "count": diagnostics.source_event_count,
                "minimum": policy.minimum_event_count,
            }
        )
    if changed_payload and not normalized_events:
        diagnostics.errors.append({"code": "changed_payload_empty"})
    unknown_event_count = sum(diagnostics.unknown_event_types.values())
    if unknown_event_count > policy.unknown_event_tolerance:
        diagnostics.errors.append(
            {
                "code": "unknown_event_tolerance_exceeded",
                "count": unknown_event_count,
                "tolerance": policy.unknown_event_tolerance,
            }
        )
    elif unknown_event_count:
        diagnostics.warnings.append(
            {"code": "unknown_event_types", "count": unknown_event_count}
        )
    unknown_qualifier_count = sum(diagnostics.unknown_qualifiers.values())
    if unknown_qualifier_count > policy.unknown_qualifier_tolerance:
        diagnostics.errors.append(
            {
                "code": "unknown_qualifier_tolerance_exceeded",
                "count": unknown_qualifier_count,
                "tolerance": policy.unknown_qualifier_tolerance,
            }
        )
    elif unknown_qualifier_count:
        diagnostics.warnings.append(
            {"code": "unknown_qualifiers", "count": unknown_qualifier_count}
        )

    shot_x_by_team: dict[str, list[float]] = {}
    for event in normalized_events:
        if event.event_type == MatchEventType.SHOT and event.x is not None:
            shot_x_by_team.setdefault(event.provider_team_id, []).append(decode_coordinate(event.x))
    for team_id, values in sorted(shot_x_by_team.items()):
        if len(values) < policy.minimum_orientation_shots:
            continue
        ordered = sorted(values)
        middle = len(ordered) // 2
        median_x = (
            ordered[middle]
            if len(ordered) % 2
            else (ordered[middle - 1] + ordered[middle]) / 2
        )
        if median_x < policy.minimum_shot_median_x:
            diagnostics.errors.append(
                {
                    "code": "shot_orientation_failed",
                    "team_id": team_id,
                    "shot_count": len(values),
                    "median_x": median_x,
                }
            )


def replace_match_events(
    provider_match: ProviderMatch,
    normalized_match: NormalizedMatch,
    *,
    batch_size: int = 1000,
    run: IngestionRun | None = None,
) -> int:
    if not normalized_match.diagnostics.valid:
        raise WhoScoredNormalizationError(normalized_match.diagnostics)
    with transaction.atomic():
        locked_match = ProviderMatch.objects.select_for_update().get(pk=provider_match.pk)
        locked_match.events.all().delete()
        rows = [
            ProviderMatchEvent(provider_match=locked_match, **event.model_values())
            for event in normalized_match.events
        ]
        ProviderMatchEvent.objects.bulk_create(rows, batch_size=batch_size)
        from ingestion.services.identity import attach_provider_match_identities

        attach_provider_match_identities(
            locked_match,
            run=run,
            team_names=dict(normalized_match.team_names),
            player_names=dict(normalized_match.player_names),
            include_report=False,
        )
        from ingestion.services.carry_derivation import replace_match_carries

        replace_match_carries(locked_match)
    return len(normalized_match.events)


def normalized_event_type(event_name: str) -> int:
    if event_name in SHOT_EVENT_NAMES:
        return MatchEventType.SHOT
    if event_name in SAVE_EVENT_NAMES:
        return MatchEventType.SAVE
    if event_name in OFFSIDE_EVENT_NAMES or event_name in {"CaughtOffside", "OffsidePass"}:
        return MatchEventType.OFFSIDE
    if event_name in SUBSTITUTION_EVENT_NAMES:
        return MatchEventType.SUBSTITUTION
    if event_name in ADMINISTRATIVE_EVENT_NAMES:
        return MatchEventType.ADMINISTRATIVE
    return EVENT_TYPE_BY_NAME.get(event_name, MatchEventType.UNKNOWN)


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


def normalized_outcome(value: Any) -> bool | None:
    raw = optional_int(mapping_value(value, "value"))
    name = display_name(value).lower()
    if raw == 1 or name == "successful":
        return True
    if raw == 0 or name == "unsuccessful":
        return False
    return None


def normalized_body_part(qualifier_names: set[str]) -> int:
    if "RightFoot" in qualifier_names:
        return MatchEventBodyPart.RIGHT_FOOT
    if "LeftFoot" in qualifier_names:
        return MatchEventBodyPart.LEFT_FOOT
    if "Head" in qualifier_names:
        return MatchEventBodyPart.HEAD
    if "OtherBodyPart" in qualifier_names:
        return MatchEventBodyPart.OTHER
    return MatchEventBodyPart.UNKNOWN


def normalized_shot_situation(qualifier_names: set[str]) -> int:
    if "Penalty" in qualifier_names:
        return MatchEventShotSituation.PENALTY
    if "DirectFreekick" in qualifier_names:
        return MatchEventShotSituation.DIRECT_FREE_KICK
    if "FromCorner" in qualifier_names or "CornerTaken" in qualifier_names:
        return MatchEventShotSituation.CORNER
    if "FastBreak" in qualifier_names:
        return MatchEventShotSituation.FAST_BREAK
    if qualifier_names & {"SetPiece", "FreekickTaken"}:
        return MatchEventShotSituation.SET_PIECE
    if qualifier_names & {"RegularPlay", "OpenPlay"}:
        return MatchEventShotSituation.OPEN_PLAY
    return MatchEventShotSituation.UNKNOWN


def normalized_shot_outcome(event_name: str, qualifier_names: set[str]) -> int:
    if event_name == "SavedShot" and "Blocked" in qualifier_names:
        return MatchEventShotOutcome.BLOCKED
    return {
        "Goal": MatchEventShotOutcome.GOAL,
        "SavedShot": MatchEventShotOutcome.SAVED,
        "MissedShots": MatchEventShotOutcome.OFF_TARGET,
        "ShotOnPost": MatchEventShotOutcome.WOODWORK,
    }.get(event_name, MatchEventShotOutcome.UNKNOWN)


def qualifier_name_set(
    qualifiers: Any,
    source_index: int,
    diagnostics: NormalizationDiagnostics,
) -> set[str]:
    if qualifiers is None:
        return set()
    if not isinstance(qualifiers, list):
        diagnostics.errors.append(
            {
                "code": "invalid_qualifiers",
                "event_index": source_index,
                "message": "qualifiers must be a list.",
            }
        )
        return set()
    names: set[str] = set()
    for qualifier_index, qualifier in enumerate(qualifiers):
        if not isinstance(qualifier, Mapping):
            diagnostics.errors.append(
                {
                    "code": "invalid_qualifier",
                    "event_index": source_index,
                    "qualifier_index": qualifier_index,
                }
            )
            continue
        name = display_name(qualifier.get("type"))
        qualifier_id = optional_int(mapping_value(qualifier.get("type"), "value"))
        if name:
            names.add(name)
        if name not in TYPED_QUALIFIER_NAMES and name not in KNOWN_UNTYPED_QUALIFIER_NAMES:
            key = f"{qualifier_id if qualifier_id is not None else '?'}:{name or '?'}"
            increment(diagnostics.unknown_qualifiers, key)
    return names


def display_name(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("displayName") or "")
    return str(value or "")


def mapping_value(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, Mapping) else None


def optional_int(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        converted = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return converted


def strict_nonnegative_int(value: Any) -> int | None:
    converted = optional_int(value)
    if converted is None or converted < 0:
        return None
    return converted


def optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def increment(values: dict[str, int], key: str) -> None:
    values[key] = values.get(key, 0) + 1
