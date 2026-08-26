"""Inspectable, provider-neutral transition leverage evidence.

This module deliberately keeps the calculation close to the materialized
possession, game-state, and player-participation contracts.  It does not try
to infer causality from a goal window: a row is only emitted when all of its
actions are linked to the same #112 possession.

The public shape is made from small, auditable components:

* an outcome ladder (territorial entry -> box entry -> shot -> big chance ->
  goal),
* a focal-team state transition attached to the terminal event, and
* one role/stage for every action in the possession trace.

``build_transition_leverage_payload`` is intentionally usable by a view or a
backfill script.  It reads existing materializations and never writes to the
database.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Prefetch, Q

from ingestion.event_profile_api import compact_match_lookup
from ingestion.models import (
    CanonicalTeam,
    MatchEventGameState,
    MatchEventShotOutcome,
    MatchEventShotSituation,
    MatchEventType,
    Provider,
    ProviderMatch,
    ProviderMatchGameState,
    ProviderMatchPlayerInterval,
    ProviderMatchPlayerParticipation,
    ProviderMatchPossession,
    ProviderMatchPossessionEvent,
    ProviderMatchTeamGameStateEpisode,
)
from ingestion.services.possession_context import (
    BOX_X,
    BOX_Y_MAX,
    BOX_Y_MIN,
    FINAL_THIRD_X,
    POSSESSION_CALCULATION_VERSION,
)
from ingestion.state_lens import StateLens, StateLensScope, state_lens_metadata


TRANSITION_LEVERAGE_FORMULA_VERSION = "transition_leverage_v1"
# Bumped when the public observation shape gained rapid-transition evidence;
# this also invalidates already materialized API payloads safely.
TRANSITION_LEVERAGE_API_VERSION = "transition_leverage_api_v2"
PLAYER_EVIDENCE_LIMIT = 25
OBSERVATION_LIMIT = 100
SPARSE_POSSESSION_THRESHOLD = 10

OUTCOME_LADDER: tuple[str, ...] = (
    "territorial_entry",
    "box_entry",
    "shot",
    "big_chance",
    "goal",
)
OUTCOME_LABELS = {
    "territorial_entry": "Final-third entry",
    "box_entry": "Box entry",
    "shot": "Shot",
    "big_chance": "Big chance",
    "goal": "Goal",
}

SEQUENCE_ROLES: tuple[str, ...] = (
    "origin_recovery",
    "escape",
    "advancement",
    "destabilisation",
    "creation",
    "contest",
    "terminal",
    "support",
)
ROLE_LABELS = {
    "origin_recovery": "Origin / recovery",
    "escape": "Escape",
    "advancement": "Advancement",
    "destabilisation": "Destabilisation",
    "creation": "Creation",
    "contest": "Contest",
    "terminal": "Terminal action",
    "support": "Supporting action",
}
STAGE_LABELS = {
    "origin": "Origin",
    "escape": "Escape",
    "advance": "Advancement",
    "destabilise": "Destabilisation",
    "create": "Creation",
    "contest": "Contest",
    "terminal": "Terminal",
    "support": "Support",
}

CONTROL_EVENT_TYPES = frozenset(
    {
        MatchEventType.PASS,
        MatchEventType.BALL_TOUCH,
        MatchEventType.TAKE_ON,
        MatchEventType.SHOT,
        MatchEventType.BALL_RECOVERY,
        MatchEventType.TACKLE,
        MatchEventType.INTERCEPTION,
        MatchEventType.SAVE,
    }
)
CONTEST_EVENT_TYPES = frozenset(
    {
        MatchEventType.TACKLE,
        MatchEventType.INTERCEPTION,
        MatchEventType.AERIAL,
        MatchEventType.CHALLENGE,
        MatchEventType.BLOCKED_PASS,
    }
)
ACQUISITION_EVENT_TYPES = frozenset(
    {
        MatchEventType.BALL_RECOVERY,
        MatchEventType.TACKLE,
        MatchEventType.INTERCEPTION,
        MatchEventType.SAVE,
    }
)


@dataclass(frozen=True, slots=True)
class EventContext:
    """Focal-team context for an event, using half-open episode semantics."""

    state: str | None = None
    state_value: int | None = None
    goal_difference: int | None = None
    phase: str | None = None
    draw_provenance: str | None = None
    state_age_seconds: int | None = None
    episode_index: int | None = None


def _int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _event_second(event: Any) -> int | None:
    value = getattr(event, "timeline_seconds", None)
    if value is None:
        value = getattr(event, "match_seconds", None)
    return _int(value)


def _state_name(value: Any) -> str | None:
    if value in (None, "", MatchEventGameState.UNKNOWN):
        return None
    try:
        return {
            MatchEventGameState.DRAWING: "drawing",
            MatchEventGameState.WINNING: "winning",
            MatchEventGameState.LOSING: "losing",
        }.get(int(value))
    except (TypeError, ValueError):
        value = str(value).lower()
        return value if value in {"drawing", "winning", "losing"} else None


def _state_value(value: Any) -> int | None:
    name = _state_name(value)
    return {
        "drawing": MatchEventGameState.DRAWING,
        "winning": MatchEventGameState.WINNING,
        "losing": MatchEventGameState.LOSING,
    }.get(name)


def _invert_state(value: Any) -> int | None:
    state = _state_value(value)
    return {
        MatchEventGameState.DRAWING: MatchEventGameState.DRAWING,
        MatchEventGameState.WINNING: MatchEventGameState.LOSING,
        MatchEventGameState.LOSING: MatchEventGameState.WINNING,
    }.get(state)


def _event_type_name(event: Any) -> str:
    raw = _int(getattr(event, "event_type", None))
    labels = {
        MatchEventType.UNKNOWN: "unknown",
        MatchEventType.PASS: "pass",
        MatchEventType.BALL_TOUCH: "ball_touch",
        MatchEventType.TAKE_ON: "take_on",
        MatchEventType.SHOT: "shot",
        MatchEventType.BALL_RECOVERY: "ball_recovery",
        MatchEventType.TACKLE: "tackle",
        MatchEventType.INTERCEPTION: "interception",
        MatchEventType.CLEARANCE: "clearance",
        MatchEventType.BLOCKED_PASS: "blocked_pass",
        MatchEventType.AERIAL: "aerial",
        MatchEventType.CHALLENGE: "challenge",
        MatchEventType.DISPOSSESSED: "dispossessed",
        MatchEventType.FOUL: "foul",
        MatchEventType.SAVE: "save",
        MatchEventType.OFFSIDE: "offside",
        MatchEventType.CARD: "card",
        MatchEventType.SUBSTITUTION: "substitution",
        MatchEventType.ADMINISTRATIVE: "administrative",
        MatchEventType.OWN_GOAL: "own_goal",
    }
    return labels.get(raw, "unknown")


def is_valid_goal_event(event: Any) -> bool:
    """Return whether this event changes the replayed score."""

    if getattr(event, "is_deleted_event", False) or getattr(
        event, "is_goal_disallowed", False
    ):
        return False
    event_type = _int(getattr(event, "event_type", None))
    return event_type == MatchEventType.OWN_GOAL or (
        event_type == MatchEventType.SHOT
        and _int(getattr(event, "shot_outcome", None)) == MatchEventShotOutcome.GOAL
    )


def scoring_provider_team_id(event: Any, match: Any) -> str | None:
    if not is_valid_goal_event(event):
        return None
    explicit = getattr(event, "scoring_provider_team_id", None)
    if explicit:
        return str(explicit)
    acting = str(getattr(event, "provider_team_id", ""))
    if _int(getattr(event, "event_type", None)) == MatchEventType.OWN_GOAL:
        home = str(getattr(match, "home_provider_team_id", ""))
        away = str(getattr(match, "away_provider_team_id", ""))
        if acting == home:
            return away
        if acting == away:
            return home
        return None
    return acting or None


def focal_provider_team_id(match: Any, focal_team_id: int) -> str | None:
    if _int(getattr(match, "home_team_id", None)) == int(focal_team_id):
        return str(getattr(match, "home_provider_team_id", ""))
    if _int(getattr(match, "away_team_id", None)) == int(focal_team_id):
        return str(getattr(match, "away_provider_team_id", ""))
    return None


def canonical_team_id_for_provider(match: Any, provider_team_id: str | None) -> int | None:
    """Map a provider side back to the already-resolved canonical side."""

    if not provider_team_id:
        return None
    provider_team_id = str(provider_team_id)
    if provider_team_id == str(getattr(match, "home_provider_team_id", "")):
        return _int(getattr(match, "home_team_id", None))
    if provider_team_id == str(getattr(match, "away_provider_team_id", "")):
        return _int(getattr(match, "away_team_id", None))
    return None


def classify_state_transition(
    before_state: Any,
    after_state: Any,
    *,
    before_goal_difference: int | None = None,
    after_goal_difference: int | None = None,
    scoring_for_focal: bool | None = None,
) -> dict[str, Any]:
    """Classify a focal-team score/state change without a composite score.

    The exact goal difference is retained so a winning-to-winning goal can be
    reported as the meaningful ``one_goal_to_multi_goal_lead`` transition.
    """

    before = _state_name(before_state)
    after = _state_name(after_state)
    classification = "no_state_transition"
    if (
        before_goal_difference is not None
        and after_goal_difference is not None
        and before_goal_difference != after_goal_difference
    ):
        if before_goal_difference == 1 and after_goal_difference >= 2:
            classification = "one_goal_to_multi_goal_lead"
        elif before_goal_difference >= 2 and after_goal_difference == 1:
            classification = "multi_goal_to_one_goal_lead"
        elif before_goal_difference == -1 and after_goal_difference == 0:
            classification = "losing_to_drawing"
        elif before_goal_difference == 0 and after_goal_difference == 1:
            classification = "drawing_to_winning"
        elif before_goal_difference == 1 and after_goal_difference == 0:
            classification = "winning_to_drawing"
        elif before_goal_difference == 0 and after_goal_difference == -1:
            classification = "drawing_to_losing"
        elif before_goal_difference < -1 and after_goal_difference == -1:
            classification = "multi_goal_deficit_to_one_goal_deficit"
        elif before_goal_difference == -1 and after_goal_difference < -1:
            classification = "one_goal_deficit_to_multi_goal_deficit"
        elif before is not None and after is not None and before != after:
            classification = f"{before}_to_{after}"
        else:
            classification = "goal_difference_change"
    elif before is not None and after is not None and before != after:
        classification = f"{before}_to_{after}"
    actual = classification != "no_state_transition"
    perspective = (
        "for"
        if scoring_for_focal is True
        else "against"
        if scoring_for_focal is False
        else None
    )
    return {
        "actual": actual,
        "classification": classification,
        "directional_classification": (
            f"{classification}_{perspective}" if actual and perspective else classification
        ),
        "before": before,
        "after": after,
        "before_goal_difference": before_goal_difference,
        "after_goal_difference": after_goal_difference,
        "perspective": perspective,
    }


def _episode_for_second(
    second: int | None,
    episodes: Sequence[Any],
    *,
    before_boundary: bool = False,
) -> Any | None:
    if second is None:
        return None
    if before_boundary:
        prior = [row for row in episodes if int(row.end_second) <= second]
        if prior:
            return max(prior, key=lambda row: (int(row.end_second), int(row.episode_index)))
    for row in episodes:
        if int(row.start_second) <= second < int(row.end_second):
            return row
    return None


def _context_from_episode(row: Any, second: int | None) -> EventContext:
    if row is None:
        return EventContext()
    age = None
    if second is not None:
        age = int(row.state_age_seconds_at_start) + second - int(row.start_second)
    return EventContext(
        state=_state_name(row.state),
        state_value=_state_value(row.state),
        goal_difference=_int(row.goal_difference),
        phase=str(row.phase) if row.phase is not None else None,
        draw_provenance=str(row.draw_provenance) if row.draw_provenance is not None else None,
        state_age_seconds=max(0, age) if age is not None else None,
        episode_index=_int(row.episode_index),
    )


def event_context(
    event: Any,
    *,
    match: Any,
    focal_team_id: int,
    episodes: Sequence[Any] = (),
    before_boundary: bool = False,
) -> EventContext:
    """Return focal state; acting-team state is inverted for opponent events."""

    second = _event_second(event)
    episode = _episode_for_second(second, episodes, before_boundary=before_boundary)
    episode_context = _context_from_episode(episode, second)
    focal_provider = focal_provider_team_id(match, focal_team_id)
    acting_provider = str(getattr(event, "provider_team_id", ""))
    direct = focal_provider is not None and acting_provider == focal_provider

    state_field = getattr(event, "game_state_before", None)
    state = _state_value(state_field)
    if state is not None:
        if not direct:
            state = _invert_state(state)
        return EventContext(
            state=_state_name(state),
            state_value=state,
            goal_difference=episode_context.goal_difference,
            phase=episode_context.phase,
            draw_provenance=episode_context.draw_provenance,
            state_age_seconds=episode_context.state_age_seconds,
            episode_index=episode_context.episode_index,
        )
    return episode_context


def _score_difference(
    event: Any,
    *,
    match: Any,
    focal_team_id: int,
    before: bool,
) -> int | None:
    home_score = _int(getattr(event, "home_score_before" if before else "home_score_after", None))
    away_score = _int(getattr(event, "away_score_before" if before else "away_score_after", None))
    if home_score is None or away_score is None:
        return None
    if _int(getattr(match, "home_team_id", None)) == int(focal_team_id):
        return home_score - away_score
    if _int(getattr(match, "away_team_id", None)) == int(focal_team_id):
        return away_score - home_score
    return None


def _team_name(team: Any) -> str | None:
    value = getattr(team, "name", None)
    return str(value) if value else None


def _player_name(player: Any) -> str | None:
    value = getattr(player, "display_name", None) or getattr(player, "name", None)
    return str(value) if value else None


def _coordinate(value: Any) -> float | None:
    raw = _int(value)
    return None if raw is None else raw / 100


def _location(event: Any, *, end: bool = False) -> dict[str, float | None]:
    if end and _int(getattr(event, "event_type", None)) == MatchEventType.PASS:
        x = getattr(event, "end_x", None)
        y = getattr(event, "end_y", None)
    else:
        x = getattr(event, "x", None)
        y = getattr(event, "y", None)
    return {"x": _coordinate(x), "y": _coordinate(y)}


def _event_endpoint(event: Any) -> tuple[int | None, int | None]:
    if _int(getattr(event, "event_type", None)) == MatchEventType.PASS:
        x = _int(getattr(event, "end_x", None))
        y = _int(getattr(event, "end_y", None))
        if x is not None or y is not None:
            return x, y
    return _int(getattr(event, "x", None)), _int(getattr(event, "y", None))


def _event_outcome_flags(
    events: Sequence[Any],
    *,
    owner_provider_team_id: str | None = None,
) -> tuple[dict[str, bool], dict[str, int | None]]:
    flags = {key: False for key in OUTCOME_LADDER}
    first_event: dict[str, int | None] = {key: None for key in OUTCOME_LADDER}
    for event in events:
        # Opponent contests can be linked to the same chain, but they must not
        # make the owning team's territorial/shot ladder look more advanced.
        if (
            owner_provider_team_id is not None
            and str(getattr(event, "provider_team_id", "")) != str(owner_provider_team_id)
        ):
            continue
        endpoint_x, endpoint_y = _event_endpoint(event)
        territorial = bool(getattr(event, "is_final_third_entry", False)) or (
            endpoint_x is not None and endpoint_x >= FINAL_THIRD_X
        )
        box = bool(getattr(event, "is_box_entry", False)) or (
            endpoint_x is not None
            and endpoint_x >= BOX_X
            and endpoint_y is not None
            and BOX_Y_MIN <= endpoint_y <= BOX_Y_MAX
        )
        shot = _int(getattr(event, "event_type", None)) == MatchEventType.SHOT
        big_chance = shot and bool(getattr(event, "is_big_chance", False))
        goal = is_valid_goal_event(event)
        current = {
            "territorial_entry": territorial,
            "box_entry": box,
            "shot": shot,
            "big_chance": big_chance,
            "goal": goal,
        }
        if box:
            current["territorial_entry"] = True
        for key, reached in current.items():
            if reached:
                flags[key] = True
                if first_event[key] is None:
                    first_event[key] = _int(getattr(event, "event_index", None))
    return flags, first_event


def _role_for_event(
    event: Any,
    *,
    is_first_control: bool,
    is_terminal: bool,
) -> tuple[str, str, list[str]]:
    event_type = _int(getattr(event, "event_type", None))
    evidence: list[str] = []
    if is_terminal and (
        event_type in {MatchEventType.SHOT, MatchEventType.OWN_GOAL}
        or is_valid_goal_event(event)
    ):
        evidence.append("terminal_event")
        if _int(getattr(event, "shot_situation", None)) == MatchEventShotSituation.PENALTY:
            evidence.append("penalty_situation")
        return "terminal", "terminal", evidence
    if bool(getattr(event, "is_intentional_assist", False)) or bool(
        getattr(event, "is_shot_assist", False)
    ):
        evidence.append("assist_flag")
        return "creation", "create", evidence
    if is_first_control:
        evidence.append("first_control_action")
        if event_type in ACQUISITION_EVENT_TYPES:
            evidence.append("recovery_or_acquisition_type")
        return "origin_recovery", "origin", evidence
    if event_type in CONTEST_EVENT_TYPES:
        evidence.append("contested_event_type")
        if getattr(event, "outcome_successful", None) is False:
            evidence.append("unsuccessful_contest")
        return "contest", "contest", evidence
    if event_type == MatchEventType.TAKE_ON:
        evidence.append("take_on_type")
        if getattr(event, "outcome_successful", None) is True:
            evidence.append("successful_outcome")
            return "escape", "escape", evidence
        return "destabilisation", "destabilise", evidence
    if event_type == MatchEventType.PASS:
        if bool(getattr(event, "is_progressive_pass", False)) or bool(
            getattr(event, "is_final_third_entry", False)
        ) or bool(getattr(event, "is_box_entry", False)):
            evidence.append("progression_or_entry_flag")
            return "advancement", "advance", evidence
        if bool(getattr(event, "is_key_pass", False)) or bool(
            getattr(event, "is_through_ball", False)
        ):
            evidence.append("unlocking_pass_flag")
            return "destabilisation", "destabilise", evidence
    if bool(getattr(event, "is_key_pass", False)):
        evidence.append("key_pass_flag")
        return "destabilisation", "destabilise", evidence
    if event_type in CONTROL_EVENT_TYPES:
        evidence.append("control_action_type")
    else:
        evidence.append("linked_event_in_possession")
    return "support", "support", evidence


def _state_public(context: EventContext) -> dict[str, Any]:
    return {
        "state": context.state,
        "goal_difference": context.goal_difference,
        "phase": context.phase,
        "draw_provenance": context.draw_provenance,
        "state_age_seconds": context.state_age_seconds,
        "episode_index": context.episode_index,
    }


def _focal_state_for_event(
    event: Any,
    *,
    match: Any,
    focal_team_id: int,
    episodes: Sequence[Any],
    before_boundary: bool = False,
) -> EventContext:
    context = event_context(
        event,
        match=match,
        focal_team_id=focal_team_id,
        episodes=episodes,
        before_boundary=before_boundary,
    )
    difference = _score_difference(
        event,
        match=match,
        focal_team_id=focal_team_id,
        before=True,
    )
    if difference is not None:
        context = EventContext(
            state=_state_name(
                MatchEventGameState.WINNING
                if difference > 0
                else MatchEventGameState.LOSING
                if difference < 0
                else MatchEventGameState.DRAWING
            ),
            state_value=(
                MatchEventGameState.WINNING
                if difference > 0
                else MatchEventGameState.LOSING
                if difference < 0
                else MatchEventGameState.DRAWING
            ),
            goal_difference=difference,
            phase=context.phase,
            draw_provenance=context.draw_provenance,
            state_age_seconds=context.state_age_seconds,
            episode_index=context.episode_index,
        )
    return context


def _possession_events(possession: Any) -> list[tuple[Any, Any]]:
    links = list(possession.event_links.all())
    links.sort(key=lambda link: (int(link.sequence), int(link.event.event_index)))
    return [(link, link.event) for link in links]


def possession_observation(
    possession: Any,
    *,
    match: Any,
    focal_team: CanonicalTeam,
    match_ref: int,
    episodes: Sequence[Any] = (),
) -> dict[str, Any]:
    """Build one complete public possession trace.

    This function accepts a materialized possession and can therefore be used
    in focused tests with a lightweight object exposing the same fields.
    """

    linked = _possession_events(possession)
    events = [event for _link, event in linked]
    terminal = events[-1] if events else None
    flags, first_outcome_events = _event_outcome_flags(
        events,
        owner_provider_team_id=str(getattr(possession, "provider_team_id", "")),
    )
    first_control_sequence = next(
        (index for index, (link, _event) in enumerate(linked) if link.is_control_action),
        None,
    )
    if first_control_sequence is None:
        first_control_sequence = next(
            (
                index
                for index, (_link, event) in enumerate(linked)
                if _int(getattr(event, "event_type", None)) in CONTROL_EVENT_TYPES
            ),
            None,
        )
    terminal_index = len(events) - 1
    focal_provider = focal_provider_team_id(match, focal_team.id)
    possession_provider = str(getattr(possession, "provider_team_id", ""))
    direction = "for" if possession_provider == focal_provider else "against"
    owner_team = getattr(possession, "team", None)
    owner_team_id = _int(getattr(possession, "team_id", None))
    owner_name = _team_name(owner_team)
    if owner_team_id is None:
        owner_team_id = (
            focal_team.id
            if direction == "for"
            else _int(getattr(match, "away_team_id", None))
            if _int(getattr(match, "home_team_id", None)) == focal_team.id
            else _int(getattr(match, "home_team_id", None))
        )
    if owner_team is None:
        if owner_team_id == _int(getattr(match, "home_team_id", None)):
            owner_team = getattr(match, "home_team", None)
        elif owner_team_id == _int(getattr(match, "away_team_id", None)):
            owner_team = getattr(match, "away_team", None)
    if owner_name is None and owner_team_id == focal_team.id:
        owner_name = focal_team.name
    if owner_name is None:
        owner_name = _team_name(owner_team)

    terminal_is_goal = bool(terminal and is_valid_goal_event(terminal))
    terminal_context = (
        _focal_state_for_event(
            terminal,
            match=match,
            focal_team_id=focal_team.id,
            episodes=episodes,
            before_boundary=terminal_is_goal,
        )
        if terminal is not None
        else EventContext()
    )
    scoring_provider = scoring_provider_team_id(terminal, match) if terminal else None
    scoring_for_focal = (
        scoring_provider == focal_provider
        if scoring_provider is not None and focal_provider is not None
        else None
    )
    before_difference = _score_difference(
        terminal,
        match=match,
        focal_team_id=focal_team.id,
        before=True,
    ) if terminal else None
    after_difference = _score_difference(
        terminal,
        match=match,
        focal_team_id=focal_team.id,
        before=False,
    ) if terminal else None
    if before_difference is None:
        before_difference = terminal_context.goal_difference
    if after_difference is None:
        after_difference = (
            before_difference + (1 if scoring_for_focal else -1)
            if terminal_is_goal and before_difference is not None and scoring_for_focal is not None
            else before_difference
        )
    before_state = terminal_context.state
    after_state = terminal_context.state
    if terminal is not None:
        before_state_value = getattr(terminal, "game_state_before", None)
        after_state_value = getattr(terminal, "game_state_after", None)
        acting_is_focal = str(getattr(terminal, "provider_team_id", "")) == focal_provider
        before_state = _state_name(
            before_state_value if acting_is_focal else _invert_state(before_state_value)
        ) or before_state
        after_state = _state_name(
            after_state_value if acting_is_focal else _invert_state(after_state_value)
        ) or after_state
    transition = classify_state_transition(
        before_state,
        after_state,
        before_goal_difference=before_difference,
        after_goal_difference=after_difference,
        scoring_for_focal=scoring_for_focal,
    )
    if not terminal_is_goal:
        transition["actual"] = False
        transition["classification"] = "no_state_transition"
        transition["perspective"] = None
    transition["directional_classification"] = (
        f"{transition['classification']}_{transition['perspective']}"
        if transition["actual"] and transition["perspective"]
        else transition["classification"]
    )

    trace: list[dict[str, Any]] = []
    for sequence, (link, event) in enumerate(linked):
        event_second = _event_second(event)
        event_is_terminal = sequence == terminal_index
        context = _focal_state_for_event(
            event,
            match=match,
            focal_team_id=focal_team.id,
            episodes=episodes,
            before_boundary=event_is_terminal and is_valid_goal_event(event),
        )
        role, stage, role_evidence = _role_for_event(
            event,
            is_first_control=sequence == first_control_sequence,
            is_terminal=event_is_terminal,
        )
        event_provider = str(getattr(event, "provider_team_id", ""))
        event_team = getattr(event, "team", None)
        event_team_id = _int(getattr(event, "team_id", None))
        event_team_name = _team_name(event_team)
        if event_team_id is None and event_provider == focal_provider:
            event_team_id, event_team_name = focal_team.id, focal_team.name
        if event_team_id is None:
            event_team_id = canonical_team_id_for_provider(match, event_provider)
        if event_team_name is None:
            if event_team_id == _int(getattr(match, "home_team_id", None)):
                event_team_name = _team_name(getattr(match, "home_team", None))
            elif event_team_id == _int(getattr(match, "away_team_id", None)):
                event_team_name = _team_name(getattr(match, "away_team", None))
        if event_team_name is None and event_team_id == focal_team.id:
            event_team_name = focal_team.name
        player = getattr(event, "player", None)
        event_type = _int(getattr(event, "event_type", None))
        trace.append(
            {
                "sequence": sequence,
                "event_index": _int(getattr(event, "event_index", None)),
                "match_seconds": event_second,
                "minute": event_second // 60 if event_second is not None else None,
                "second": event_second % 60 if event_second is not None else None,
                "period": _int(getattr(event, "period", None)),
                "event_type": _event_type_name(event),
                "team_id": event_team_id,
                "team_name": event_team_name,
                "team_perspective": "for" if event_provider == focal_provider else "against",
                "player_id": _int(getattr(event, "player_id", None)),
                "player_name": _player_name(player) if player is not None else None,
                "location": _location(event),
                "destination": _location(event, end=True),
                "completed": getattr(event, "outcome_successful", None),
                "is_control_action": bool(link.is_control_action),
                "is_settled_defensive_action": bool(link.is_settled_defensive_action),
                "stage": stage,
                "stage_label": STAGE_LABELS[stage],
                "role": role,
                "role_label": ROLE_LABELS[role],
                "role_evidence": role_evidence,
                "is_terminal": event_is_terminal,
                "flags": {
                    "progressive": bool(getattr(event, "is_progressive_pass", False)),
                    "final_third_entry": bool(getattr(event, "is_final_third_entry", False)),
                    "box_entry": bool(getattr(event, "is_box_entry", False)),
                    "key_pass": bool(getattr(event, "is_key_pass", False)),
                    "shot_assist": bool(getattr(event, "is_shot_assist", False)),
                    "intentional_assist": bool(getattr(event, "is_intentional_assist", False)),
                    "big_chance": bool(getattr(event, "is_big_chance", False)),
                    "penalty": _int(getattr(event, "shot_situation", None)) == MatchEventShotSituation.PENALTY,
                    "restart": bool(
                        getattr(event, "is_set_piece", False)
                        or getattr(event, "is_throw_in", False)
                        or getattr(event, "is_corner", False)
                        or getattr(event, "is_free_kick", False)
                    ),
                    "contested": event_type in CONTEST_EVENT_TYPES,
                },
                "game_state": _state_public(context),
            }
        )

    scoring_team_id = canonical_team_id_for_provider(match, scoring_provider)
    score = {
        "is_goal": terminal_is_goal,
        "goal_type": (
            "own_goal"
            if terminal_is_goal
            and _int(getattr(terminal, "event_type", None)) == MatchEventType.OWN_GOAL
            else "goal"
            if terminal_is_goal
            else None
        ),
        "scoring_team_id": scoring_team_id,
        "perspective": (
            "for" if scoring_for_focal is True else "against" if scoring_for_focal is False else None
        ),
        "before_goal_difference": before_difference,
        "after_goal_difference": after_difference,
        "situation": (
            "penalty"
            if terminal is not None
            and _int(getattr(terminal, "shot_situation", None)) == MatchEventShotSituation.PENALTY
            else None
        ),
    }
    raw_ladder = {
        key: {
            "reached": flags[key],
            "first_event_index": first_outcome_events[key],
        }
        for key in OUTCOME_LADDER
    }
    direction_ladder = {
        key: value["reached"]
        for key, value in raw_ladder.items()
    }
    if direction == "for" and score["perspective"] == "against":
        direction_ladder["goal"] = False
    if direction == "against" and score["perspective"] != "against":
        direction_ladder["goal"] = False
    highest = next((key for key in reversed(OUTCOME_LADDER) if direction_ladder[key]), "possession")
    diagnostics = getattr(possession, "diagnostics", {}) or {}
    if not isinstance(diagnostics, Mapping):
        diagnostics = {}
    return {
        "possession_id": str(getattr(possession, "identity", "")),
        "match_ref": match_ref,
        "team_id": owner_team_id,
        "team_name": owner_name,
        "direction": direction,
        "period": _int(getattr(possession, "period", None)),
        "start_second": _int(getattr(possession, "start_second", None)),
        "end_second": _int(getattr(possession, "end_second", None)),
        "duration_seconds": _int(getattr(possession, "duration_seconds", None)),
        "start": {"x": _coordinate(getattr(possession, "start_x", None)), "y": _coordinate(getattr(possession, "start_y", None))},
        "end": {"x": _coordinate(getattr(possession, "end_x", None)), "y": _coordinate(getattr(possession, "end_y", None))},
        "launch_type": str(getattr(possession, "launch_type", "continued_control")),
        "termination_reason": str(getattr(possession, "termination_reason", "period_end")),
        "is_ambiguous": bool(getattr(possession, "is_ambiguous", False)),
        "rapid_transition": {
            "is_counter_launch": bool(getattr(possession, "is_counter_launch", False)),
            "qualifies_forward_progress": bool(
                diagnostics.get("qualifies_counter_progress", False)
            ),
            "elapsed_seconds": _int(getattr(possession, "counter_elapsed_seconds", None)),
            "forward_metres": (
                float(possession.counter_forward_metres)
                if getattr(possession, "counter_forward_metres", None) is not None
                else None
            ),
            "speed_mps": (
                float(possession.counter_speed_mps)
                if getattr(possession, "counter_speed_mps", None) is not None
                else None
            ),
            "outcome": str(possession.counter_outcome)
            if getattr(possession, "counter_outcome", None)
            else None,
        },
        "outcome_tier": highest,
        "outcome_ladder": raw_ladder,
        "direction_ladder": direction_ladder,
        "score": score,
        "state": _state_public(
            EventContext(
                state=before_state,
                goal_difference=before_difference,
                phase=terminal_context.phase,
                draw_provenance=terminal_context.draw_provenance,
                state_age_seconds=terminal_context.state_age_seconds,
                episode_index=terminal_context.episode_index,
            )
        ),
        "state_transition": transition,
        "actual_state_transition": transition["actual"],
        "transition_classification": transition["classification"],
        "possession_trace": trace,
        "action_evidence": trace,
    }


def _scope_context(context: Mapping[str, Any], scope: StateLensScope) -> bool:
    if scope.state != "all" and context.get("state") != scope.state:
        return False
    if scope.goal_difference is not None and context.get("goal_difference") != scope.goal_difference:
        return False
    if scope.phase is not None and context.get("phase") != scope.phase:
        return False
    if scope.draw_provenance is not None and context.get("draw_provenance") != scope.draw_provenance:
        return False
    age = context.get("state_age_seconds")
    if scope.minimum_state_age_seconds is not None and (age is None or age < scope.minimum_state_age_seconds):
        return False
    if scope.maximum_state_age_seconds is not None and (age is None or age >= scope.maximum_state_age_seconds):
        return False
    return True


def _rate(count: int, denominator: int) -> float | None:
    return round(count / denominator, 4) if denominator else None


def _ladder_for_observations(
    observations: Sequence[dict[str, Any]],
    *,
    direction: str,
) -> dict[str, Any]:
    if direction == "attacking":
        selected = [row for row in observations if row["direction"] == "for"]
    else:
        selected = [
            row
            for row in observations
            if row["direction"] == "against"
            or row["score"]["perspective"] == "against"
        ]
    opportunities = len(selected)
    ladder = []
    for key in OUTCOME_LADDER:
        def reached(row: Mapping[str, Any]) -> bool:
            if key == "goal":
                return row["score"]["perspective"] == (
                    "for" if direction == "attacking" else "against"
                )
            if direction == "concession" and row["direction"] == "for":
                # A focal own-goal chain is an explicit concession opportunity,
                # but its preceding territory is not an opponent advancement.
                return False
            return bool(row["outcome_ladder"].get(key, {}).get("reached"))

        count = sum(reached(row) for row in selected)
        ladder.append(
            {
                "key": key,
                "label": OUTCOME_LABELS[key],
                "count": count,
                "rate_per_opportunity": _rate(count, opportunities),
            }
        )
    transitions = [row["state_transition"] for row in selected if row["state_transition"]["actual"]]
    transition_counts = Counter(row["classification"] for row in transitions)
    score_counts = Counter(
        row["score"]["goal_type"]
        for row in selected
        if row["score"]["is_goal"]
    )
    return {
        "opportunities": opportunities,
        "opportunity_basis": (
            "focal_team_possessions"
            if direction == "attacking"
            else "opponent_possessions_plus_focal_own_goal_chains"
        ),
        "outcome_ladder": ladder,
        "state_transitions": {
            "count": len(transitions),
            "by_classification": dict(sorted(transition_counts.items())),
            "rate_per_opportunity": _rate(len(transitions), opportunities),
        },
        "scores": {
            "goals": sum(
                row["score"]["perspective"] == ("for" if direction == "attacking" else "against")
                for row in selected
                if row["score"]["is_goal"]
            ),
            "normal_goals": score_counts["goal"] if direction == "attacking" else sum(
                1 for row in selected if row["score"]["goal_type"] == "goal" and row["score"]["perspective"] == "against"
            ),
            "own_goals": score_counts["own_goal"] if direction == "attacking" else sum(
                1 for row in selected if row["score"]["goal_type"] == "own_goal" and row["score"]["perspective"] == "against"
            ),
        },
    }


def _interval_contains(intervals: Sequence[Any], second: int | None) -> bool:
    return second is not None and any(
        int(interval.start_second) <= second < int(interval.end_second)
        for interval in intervals
    )


def _selected_interval_seconds(
    intervals: Sequence[Any],
    *,
    episodes: Sequence[Any],
    scope: StateLensScope,
) -> int:
    total = 0
    for interval in intervals:
        for episode in episodes:
            start = max(int(interval.start_second), int(episode.start_second))
            end = min(int(interval.end_second), int(episode.end_second))
            if end <= start:
                continue
            age_start = int(episode.state_age_seconds_at_start) + start - int(episode.start_second)
            age_end = int(episode.state_age_seconds_at_start) + end - int(episode.start_second)
            if scope.state != "all" and _state_name(episode.state) != scope.state:
                continue
            if scope.goal_difference is not None and int(episode.goal_difference) != scope.goal_difference:
                continue
            if scope.phase is not None and str(episode.phase) != scope.phase:
                continue
            if scope.draw_provenance is not None and str(episode.draw_provenance) != scope.draw_provenance:
                continue
            if scope.minimum_state_age_seconds is not None:
                start = max(start, int(episode.start_second) + scope.minimum_state_age_seconds - int(episode.state_age_seconds_at_start))
            if scope.maximum_state_age_seconds is not None:
                end = min(end, int(episode.start_second) + scope.maximum_state_age_seconds - int(episode.state_age_seconds_at_start))
            if end > start and age_end > age_start:
                total += end - start
    return total


def _empty_player_row(participant: Any, *, team: CanonicalTeam, match_seconds: int) -> dict[str, Any]:
    player = getattr(participant, "player", None)
    return {
        "canonical_player_id": _int(getattr(participant, "player_id", None)),
        "canonical_player_name": _player_name(player) if player is not None else None,
        "canonical_team_id": team.id,
        "canonical_team_name": team.name,
        "roster_role": str(getattr(participant, "roster_role", "unknown")),
        "verified_on_pitch_seconds": match_seconds,
        "verified_on_pitch_minutes": round(match_seconds / 60, 4),
        "opportunities": 0,
        "involved_possessions": 0,
        "involvement_rate": None,
        "outcome_ladder": {
            key: {
                "opportunities": 0,
                "involved_possessions": 0,
                "involvement_rate": None,
            }
            for key in OUTCOME_LADDER
        },
        "sequence_stages": {
            role: {"actions": 0, "possessions": 0, "rate_per_opportunity": None}
            for role in SEQUENCE_ROLES
        },
        "concession": {
            "opportunities": 0,
            "defensive_action_possessions": 0,
            "defensive_action_rate": None,
        },
        "coverage": {
            "included_match_count": 0,
            "excluded_match_count": 0,
            "excluded_reasons": {},
            "selected_verified_seconds": 0,
            "selected_verified_minutes": 0,
            "confidence": "unavailable",
        },
        "evidence": [],
        "evidence_truncated": False,
    }


def _build_player_involvement(
    observations: Sequence[dict[str, Any]],
    *,
    matches: Sequence[Any],
    focal_team: CanonicalTeam,
    scope: StateLensScope,
    episodes_by_match: Mapping[int, Sequence[Any]],
    participation_by_match: Mapping[int, Sequence[Any]],
    excluded_match_reasons: Mapping[int, str],
) -> list[dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    participant_intervals: dict[tuple[int, int], Sequence[Any]] = {}
    eligible_players_by_match: dict[int, set[int]] = defaultdict(set)
    participant_match_ids: dict[int, set[int]] = defaultdict(set)
    for match in matches:
        match_id = int(match.id)
        for participant in participation_by_match.get(match_id, ()):
            player_id = _int(getattr(participant, "player_id", None))
            if (
                player_id is None
                or getattr(participant, "player", None) is None
                or _int(getattr(participant, "team_id", None)) != focal_team.id
            ):
                continue
            intervals = list(participant.intervals.all())
            if (
                getattr(participant, "status", None) != "verified"
                or getattr(participant, "confidence", None) != "verified"
                or not intervals
                or any(
                    str(getattr(interval, "confidence", "verified")) != "verified"
                    or int(interval.end_second) <= int(interval.start_second)
                    for interval in intervals
                )
                or sum(int(interval.duration_seconds) for interval in intervals) <= 0
            ):
                continue
            row = rows.setdefault(
                player_id,
                _empty_player_row(participant, team=focal_team, match_seconds=0),
            )
            participant_intervals[(player_id, match_id)] = tuple(intervals)
            eligible_players_by_match[match_id].add(player_id)
            participant_match_ids[player_id].add(match_id)
            episodes = episodes_by_match.get(match_id, ())
            selected_seconds = _selected_interval_seconds(intervals, episodes=episodes, scope=scope)
            row["coverage"]["selected_verified_seconds"] += selected_seconds
            row["coverage"]["selected_verified_minutes"] = round(
                row["coverage"]["selected_verified_seconds"] / 60, 4
            )
            row["verified_on_pitch_seconds"] += sum(
                int(interval.duration_seconds) for interval in intervals
            )
            row["verified_on_pitch_minutes"] = round(row["verified_on_pitch_seconds"] / 60, 4)
            row["coverage"]["included_match_count"] = len(participant_match_ids[player_id])

    for row in rows.values():
        player_id = row["canonical_player_id"]
        included_ids = participant_match_ids[player_id]
        excluded = {
            reason: sum(1 for match_id, value in excluded_match_reasons.items() if match_id not in included_ids and value == reason)
            for reason in set(excluded_match_reasons.values())
        }
        row["coverage"]["excluded_match_count"] = sum(excluded.values())
        row["coverage"]["excluded_reasons"] = {key: value for key, value in sorted(excluded.items()) if value}
        row["coverage"]["confidence"] = "partial" if row["coverage"]["excluded_match_count"] else "verified"

    match_lookup = {int(match.id): match for match in matches}
    for observation in observations:
        if observation["direction"] != "for":
            continue
        if not 0 <= observation["match_ref"] < len(matches):
            continue
        match_id = int(matches[observation["match_ref"]].id)
        match = match_lookup[match_id]
        trace = observation["possession_trace"]
        selected_events = [
            event
            for event in trace
            if event["team_perspective"] == "for" and _scope_context(event["game_state"], scope)
        ]
        if not selected_events:
            continue
        for player_id in eligible_players_by_match.get(match_id, ()):
            row = rows[player_id]
            intervals = participant_intervals.get((player_id, match_id), ())
            opportunity = any(_interval_contains(intervals, event["match_seconds"]) for event in selected_events)
            if not opportunity:
                continue
            row["opportunities"] += 1
            involved_events = [
                event
                for event in selected_events
                if event["player_id"] == player_id
                and _interval_contains(intervals, event["match_seconds"])
            ]
            if not involved_events:
                continue
            row["involved_possessions"] += 1
            row["involvement_rate"] = _rate(row["involved_possessions"], row["opportunities"])
            for key in OUTCOME_LADDER:
                row["outcome_ladder"][key]["opportunities"] += 1
                if observation["direction_ladder"].get(key):
                    row["outcome_ladder"][key]["involved_possessions"] += 1
                row["outcome_ladder"][key]["involvement_rate"] = _rate(
                    row["outcome_ladder"][key]["involved_possessions"],
                    row["outcome_ladder"][key]["opportunities"],
                )
            roles_in_observation: set[str] = set()
            for event in involved_events:
                role = event["role"]
                roles_in_observation.add(role)
                row["sequence_stages"][role]["actions"] += 1
            for role in roles_in_observation:
                row["sequence_stages"][role]["possessions"] += 1
                row["sequence_stages"][role]["rate_per_opportunity"] = _rate(
                    row["sequence_stages"][role]["possessions"], row["opportunities"]
                )
            evidence = {
                "match_ref": observation["match_ref"],
                "possession_id": observation["possession_id"],
                "state": observation["state"],
                "state_transition": observation["state_transition"],
                "outcome_tier": observation["outcome_tier"],
                "action_stages": sorted({event["stage"] for event in involved_events}),
                "action_event_indexes": [event["event_index"] for event in involved_events],
                "possession_trace": observation["possession_trace"],
            }
            if len(row["evidence"]) < PLAYER_EVIDENCE_LIMIT:
                row["evidence"].append(evidence)
            else:
                row["evidence_truncated"] = True

    # Concession vulnerability stays separate from attacking involvement.  A
    # player opportunity is an opponent possession with an event inside the
    # same verified interval; the numerator is a focal defensive/contested
    # action in that chain.  This does not imply that a defensive action caused
    # or prevented the terminal outcome.
    for observation in observations:
        if observation["direction"] != "against" and observation["score"]["perspective"] != "against":
            continue
        if not 0 <= observation["match_ref"] < len(matches):
            continue
        match_id = int(matches[observation["match_ref"]].id)
        trace = observation["possession_trace"]
        selected_events = [
            event
            for event in trace
            if _scope_context(event["game_state"], scope)
        ]
        if not selected_events:
            continue
        for player_id in eligible_players_by_match.get(match_id, ()):
            row = rows[player_id]
            intervals = participant_intervals.get((player_id, match_id), ())
            if not any(_interval_contains(intervals, event["match_seconds"]) for event in selected_events):
                continue
            row["concession"]["opportunities"] += 1
            defensive_events = [
                event
                for event in selected_events
                if event["team_perspective"] == "for"
                and event["player_id"] == player_id
                and _interval_contains(intervals, event["match_seconds"])
                and (
                    event["flags"]["contested"]
                    or event["is_settled_defensive_action"]
                    or event["event_type"] in {"clearance", "foul"}
                )
            ]
            if defensive_events:
                row["concession"]["defensive_action_possessions"] += 1
            row["concession"]["defensive_action_rate"] = _rate(
                row["concession"]["defensive_action_possessions"],
                row["concession"]["opportunities"],
            )

    return sorted(
        rows.values(),
        key=lambda row: (
            row["involved_possessions"] == 0,
            -(row["involved_possessions"] or 0),
            row["canonical_player_name"] or "",
        ),
    )


def _coverage(
    *,
    matches: Sequence[Any],
    eligible_match_ids: set[int],
    observations: Sequence[dict[str, Any]],
    excluded_reasons: Mapping[str, int],
    ambiguous_count: int,
    participation_by_match: Mapping[int, Sequence[Any]],
) -> dict[str, Any]:
    participation_rows = [
        row
        for match_rows in participation_by_match.values()
        for row in match_rows
    ]
    def interval_evidence_verified(row: Any) -> bool:
        intervals = list(row.intervals.all())
        return bool(intervals) and all(
            str(getattr(interval, "confidence", "verified")) == "verified"
            and int(interval.end_second) > int(interval.start_second)
            for interval in intervals
        )

    def strict_verified(row: Any) -> bool:
        return (
            str(getattr(row, "status", "")) == "verified"
            and str(getattr(row, "confidence", "")) == "verified"
            and _int(getattr(row, "player_id", None)) is not None
            and _int(getattr(row, "team_id", None)) is not None
            and int(getattr(row, "on_pitch_seconds", 0) or 0) > 0
            and interval_evidence_verified(row)
        )

    def exclusion_reason(row: Any) -> str:
        explicit = getattr(row, "exclusion_reason", None)
        if explicit:
            return str(explicit)
        if str(getattr(row, "status", "")) == "unused":
            return "unused_participation"
        if str(getattr(row, "status", "")) == "verified" and str(getattr(row, "confidence", "")) != "verified":
            return "participation_confidence_unverified"
        if _int(getattr(row, "player_id", None)) is None or _int(getattr(row, "team_id", None)) is None:
            return "canonical_identity_unresolved"
        if not interval_evidence_verified(row):
            return "interval_confidence_unverified"
        if int(getattr(row, "on_pitch_seconds", 0) or 0) <= 0:
            return "verified_interval_missing"
        return "participation_unverified"

    participation_exclusions = Counter(
        exclusion_reason(row)
        for row in participation_rows
        if not strict_verified(row) and str(getattr(row, "status", "")) != "unused"
    )
    return {
        "matches_available": len(matches),
        "matches_eligible": len(eligible_match_ids),
        "matches_included": len({row["match_ref"] for row in observations}),
        "matches_excluded": len(matches) - len({row["match_ref"] for row in observations}),
        "exclusion_reasons": dict(sorted(excluded_reasons.items())),
        "possession_count": len(observations),
        "ambiguous_possession_count": ambiguous_count,
        "evidence_limit": OBSERVATION_LIMIT,
        "evidence_truncated": len(observations) > OBSERVATION_LIMIT,
        "sparse": len(observations) < SPARSE_POSSESSION_THRESHOLD,
        "sparse_threshold": SPARSE_POSSESSION_THRESHOLD,
        "player_participation": {
            "candidate_count": len(participation_rows),
            "verified_count": sum(strict_verified(row) for row in participation_rows),
            "excluded_count": sum(
                not strict_verified(row) and str(getattr(row, "status", "")) != "unused"
                for row in participation_rows
            ),
            "unused_count": sum(
                str(getattr(row, "status", "")) == "unused"
                for row in participation_rows
            ),
            "verified_seconds": sum(
                int(getattr(row, "on_pitch_seconds", 0) or 0)
                for row in participation_rows
                if str(getattr(row, "status", "")) == "verified"
                and str(getattr(row, "confidence", "")) == "verified"
            ),
            "exclusion_reasons": dict(sorted(participation_exclusions.items())),
        },
        "reliability": {
            "eligible_game_state_only": True,
            "verified_possession_only": True,
            "timeline": "half_open_played_seconds",
            "causal_claims": False,
        },
    }


def _comparison_delta(selected: dict[str, Any], baseline: dict[str, Any] | None) -> dict[str, Any] | None:
    if baseline is None:
        return None
    result: dict[str, Any] = {}
    for direction in ("attacking", "concession"):
        selected_ladder = {row["key"]: row["rate_per_opportunity"] for row in selected[direction]["outcome_ladder"]}
        baseline_ladder = {row["key"]: row["rate_per_opportunity"] for row in baseline[direction]["outcome_ladder"]}
        result[direction] = {
            key: (
                round(selected_ladder[key] - baseline_ladder[key], 4)
                if selected_ladder[key] is not None and baseline_ladder[key] is not None
                else None
            )
            for key in OUTCOME_LADDER
        }
    return result


def _build_scope(
    observations: Sequence[dict[str, Any]],
    *,
    matches: Sequence[Any],
    all_matches: Sequence[Any],
    focal_team: CanonicalTeam,
    scope: StateLensScope,
    episodes_by_match: Mapping[int, Sequence[Any]],
    participation_by_match: Mapping[int, Sequence[Any]],
    excluded_match_reasons: Mapping[int, str],
    eligible_match_ids: set[int],
    excluded_reasons: Mapping[str, int],
    ambiguous_count: int,
) -> dict[str, Any]:
    attacking = _ladder_for_observations(observations, direction="attacking")
    concession = _ladder_for_observations(observations, direction="concession")
    players = _build_player_involvement(
        observations,
        matches=all_matches,
        focal_team=focal_team,
        scope=scope,
        episodes_by_match=episodes_by_match,
        participation_by_match=participation_by_match,
        excluded_match_reasons=excluded_match_reasons,
    )
    return {
        "scope": scope.public(),
        "attacking": attacking,
        "concession": concession,
        "concession_vulnerability": concession,
        "players": players,
        "player_involvement": players,
        "observations": list(observations[:OBSERVATION_LIMIT]),
        "coverage": _coverage(
            matches=matches,
            eligible_match_ids=eligible_match_ids,
            observations=observations,
            excluded_reasons=excluded_reasons,
            ambiguous_count=ambiguous_count,
            participation_by_match=participation_by_match,
        ),
    }


def build_transition_leverage_payload(
    *,
    competition_season: Any,
    team: CanonicalTeam,
    match_ref: int | None,
    lens: StateLens,
) -> dict[str, Any]:
    """Build a public-safe season/team payload from #112/#104/#105 rows."""

    matches = list(
        ProviderMatch.objects.filter(
            competition_season=competition_season,
            provider=Provider.WHOSCORED,
        )
        .filter(Q(home_team=team) | Q(away_team=team))
        .select_related("home_team", "away_team")
        .order_by("kickoff_at", "id")
    )
    subject_team_ids = {match.id: team.id for match in matches}
    match_lookup, references = compact_match_lookup(matches, subject_team_ids)
    if match_ref is not None and match_ref not in references.values():
        raise DjangoValidationError("match is not available in this transition-leverage profile.")
    selected_match_ids = {
        match_id for match_id, reference in references.items() if match_ref is None or reference == match_ref
    }
    scoped_matches = [match for match in matches if match.id in selected_match_ids]
    state_lens = state_lens_metadata(team.id, scoped_matches, lens)
    audits = {
        int(row.provider_match_id): row
        for row in ProviderMatchGameState.objects.filter(provider_match_id__in=[match.id for match in matches])
    }
    eligible_match_ids = {
        match_id for match_id, audit in audits.items() if audit.eligible and match_id in selected_match_ids
    }
    episodes_by_match: dict[int, list[Any]] = defaultdict(list)
    episode_rows = ProviderMatchTeamGameStateEpisode.objects.filter(
        provider_match_id__in=eligible_match_ids,
        focal_team=team,
    ).order_by("provider_match_id", "episode_index")
    for episode in episode_rows:
        episodes_by_match[int(episode.provider_match_id)].append(episode)
    participation_rows = list(
        ProviderMatchPlayerParticipation.objects.filter(
            provider_match_id__in=eligible_match_ids,
            team=team,
        )
        .select_related("player", "team", "build")
        .prefetch_related(
            Prefetch(
                "intervals",
                queryset=ProviderMatchPlayerInterval.objects.order_by("sequence"),
            )
        )
    )
    participation_by_match: dict[int, list[Any]] = defaultdict(list)
    for row in participation_rows:
        participation_by_match[int(row.provider_match_id)].append(row)

    link_queryset = ProviderMatchPossessionEvent.objects.select_related(
        "event", "event__player", "event__team"
    ).order_by("sequence")
    possessions = list(
        ProviderMatchPossession.objects.filter(
            provider_match_id__in=eligible_match_ids,
            build__calculation_version=POSSESSION_CALCULATION_VERSION,
            is_ambiguous=False,
        )
        .select_related("provider_match", "team", "build")
        .prefetch_related(Prefetch("event_links", queryset=link_queryset))
        .order_by("provider_match_id", "possession_index")
    )
    match_by_id = {match.id: match for match in matches}
    all_observations: list[dict[str, Any]] = []
    selected_observations: list[dict[str, Any]] = []
    excluded_reasons: Counter[str] = Counter()
    excluded_match_reasons: dict[int, str] = {}
    ambiguous_count = 0
    for match in matches:
        if match.id not in selected_match_ids:
            continue
        audit = audits.get(match.id)
        if audit is None:
            excluded_match_reasons[match.id] = "game_state_unverified"
            excluded_reasons["game_state_unverified"] += 1
            continue
        if not audit.eligible:
            excluded_match_reasons[match.id] = str(audit.exclusion_reason or "game_state_unverified")
            excluded_reasons[excluded_match_reasons[match.id]] += 1
    for possession in possessions:
        match = match_by_id.get(int(possession.provider_match_id))
        if match is None:
            continue
        observation = possession_observation(
            possession,
            match=match,
            focal_team=team,
            match_ref=references[match.id],
            episodes=episodes_by_match.get(match.id, ()),
        )
        all_observations.append(observation)
        if _scope_context(observation["state"], lens.selected):
            selected_observations.append(observation)
    observed_match_ids = {
        match_id
        for match_id, reference in references.items()
        if any(row["match_ref"] == reference for row in selected_observations)
    }
    for match in matches:
        if match.id not in selected_match_ids or match.id in observed_match_ids:
            continue
        if match.id not in excluded_match_reasons:
            excluded_match_reasons[match.id] = "possession_context_unavailable"
            excluded_reasons["possession_context_unavailable"] += 1
    # A separate pass over ambiguous materializations is intentionally only
    # diagnostic.  Ambiguous rows never enter observations or denominators.
    ambiguous_count = ProviderMatchPossession.objects.filter(
        provider_match_id__in=eligible_match_ids,
        build__calculation_version=POSSESSION_CALCULATION_VERSION,
        is_ambiguous=True,
    ).count()
    selected_scope = _build_scope(
        selected_observations,
        matches=scoped_matches,
        all_matches=matches,
        focal_team=team,
        scope=lens.selected,
        episodes_by_match=episodes_by_match,
        participation_by_match=participation_by_match,
        excluded_match_reasons=excluded_match_reasons,
        eligible_match_ids=eligible_match_ids,
        excluded_reasons=excluded_reasons,
        ambiguous_count=ambiguous_count,
    )
    baseline_scope = None
    if lens.baseline is not None:
        baseline_observations = [
            row
            for row in all_observations
            if _scope_context(row["state"], lens.baseline)
        ]
        baseline_scope = _build_scope(
            baseline_observations,
            matches=scoped_matches,
            all_matches=matches,
            focal_team=team,
            scope=lens.baseline,
            episodes_by_match=episodes_by_match,
            participation_by_match=participation_by_match,
            excluded_match_reasons=excluded_match_reasons,
            eligible_match_ids=eligible_match_ids,
            excluded_reasons=excluded_reasons,
            ambiguous_count=ambiguous_count,
        )
    return {
        "contract_version": TRANSITION_LEVERAGE_API_VERSION,
        "formula_version": TRANSITION_LEVERAGE_FORMULA_VERSION,
        "team": {"id": team.id, "name": team.name},
        "competition_season": {
            "id": competition_season.id,
            "competition": competition_season.competition.short_code,
            "season": competition_season.season.label,
        },
        "selected_match_ref": match_ref,
        "matches": match_lookup,
        "state_lens": state_lens,
        "thresholds": {
            "outcome_ladder": [
                {"key": key, "label": OUTCOME_LABELS[key]} for key in OUTCOME_LADDER
            ],
            "sequence_roles": [
                {"key": key, "label": ROLE_LABELS[key]} for key in SEQUENCE_ROLES
            ],
            "possession_calculation_version": POSSESSION_CALCULATION_VERSION,
            "transition_calculation_version": TRANSITION_LEVERAGE_FORMULA_VERSION,
            "state_boundary": "goal-ending possessions use the pre-goal half-open episode",
            "player_opportunity_denominator": "team possessions with an event during the player's verified on-pitch interval",
        },
        "selected": selected_scope,
        "comparison": {
            "enabled": baseline_scope is not None,
            "baseline": baseline_scope,
            "delta": _comparison_delta(selected_scope, baseline_scope),
        },
    }
