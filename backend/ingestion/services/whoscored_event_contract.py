"""WhoScored source vocabulary mapped by the normalization boundary."""

from typing import Any, Mapping

from ingestion.models import (
    MatchDismissalType,
    MatchEventType,
    MatchParticipationAction,
)
from ingestion.services.whoscored_match_metadata import display_name, optional_string


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
DELETED_EVENT_NAMES = frozenset({"DeletedEvent"})
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

PARTICIPATION_ACTION_BY_EVENT_NAME = {
    "SubstitutionOn": MatchParticipationAction.SUBSTITUTION_ON,
    "SubstitutionOff": MatchParticipationAction.SUBSTITUTION_OFF,
    "PlayerOn": MatchParticipationAction.PLAYER_ON,
    "PlayerOff": MatchParticipationAction.PLAYER_OFF,
    "PlayerRetired": MatchParticipationAction.PLAYER_RETIRED,
    "PlayerReturns": MatchParticipationAction.PLAYER_RETURNS,
}

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


def related_event_sequence_id(qualifiers: Any) -> str | None:
    if not isinstance(qualifiers, list):
        return None
    for qualifier in qualifiers:
        if not isinstance(qualifier, Mapping):
            continue
        if display_name(qualifier.get("type")) != "RelatedEventId":
            continue
        value = qualifier.get("value")
        if isinstance(value, Mapping):
            value = value.get("value") or value.get("displayName")
        return optional_string(value)
    return None


def normalized_dismissal_type(event_name: str, card_type: Any) -> str:
    if event_name != "Card":
        return MatchDismissalType.NONE
    return {
        "Red": MatchDismissalType.RED,
        "SecondYellow": MatchDismissalType.SECOND_YELLOW,
    }.get(display_name(card_type), MatchDismissalType.NONE)
