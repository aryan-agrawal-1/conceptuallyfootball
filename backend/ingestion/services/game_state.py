"""Deterministic focal-team score replay, episodes, exposure, and helpers."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, fields as dataclass_fields, replace
from typing import Any, Iterable, Mapping, Sequence

from django.db import transaction
from django.db.models import Count, Exists, OuterRef, QuerySet, Sum
from django.utils import timezone

from ingestion.models import (
    MatchEventGameState,
    MatchEventPeriod,
    MatchEventShotOutcome,
    MatchEventType,
    MatchGameStateExclusionReason,
    MatchGameStateStatus,
    MatchStateDrawProvenance,
    MatchStatePhase,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchPayload,
    ProviderMatchPlayedPeriod,
    ProviderMatchStatus,
    ProviderMatchTeamGameStateEpisode,
    ProviderMatchTeamGameStateExposure,
    ProviderPayloadLifecycle,
)
from ingestion.services.game_clock import (
    CLOCK_CALCULATION_VERSION,
    MatchClock,
    MatchClockError,
    coerce_match_clock,
    match_clock_from_period_rows,
    validate_event_timestamp,
)

GAME_STATE_CALCULATION_VERSION = "team_game_state_v1"
SUPPORTED_PERIODS = frozenset({1, 2, 3, 4})
PHASE_BY_PERIOD = {
    1: MatchStatePhase.FIRST_HALF,
    2: MatchStatePhase.SECOND_HALF,
    3: MatchStatePhase.FIRST_EXTRA_TIME,
    4: MatchStatePhase.SECOND_EXTRA_TIME,
}


@dataclass(frozen=True, slots=True)
class MatchEventGameStateContext:
    home_score_before: int
    away_score_before: int
    home_score_after: int
    away_score_after: int
    game_state_before: int | None
    game_state_after: int | None
    scoring_provider_team_id: str | None


@dataclass(frozen=True, slots=True)
class ScoreTransition:
    second: int
    sequence: tuple[int, str, int]
    event: Any
    scoring_provider_team_id: str
    home_score_before: int
    away_score_before: int
    home_score_after: int
    away_score_after: int


@dataclass(frozen=True, slots=True)
class EpisodeSpec:
    focal_team_id: int
    focal_is_home: bool
    episode_index: int
    period: int
    phase: str
    start_second: int
    end_second: int
    duration_seconds: int
    is_added_time: bool
    focal_score: int
    opponent_score: int
    goal_difference: int
    state: int
    previous_state: int | None
    draw_provenance: str
    state_entry_second: int
    state_age_seconds_at_start: int
    entry_event: Any | None
    entry_event_index: int | None


@dataclass(frozen=True, slots=True)
class ExposureSpec:
    focal_team_id: int
    state: int
    goal_difference: int
    phase: str
    draw_provenance: str
    exposure_seconds: int
    episode_count: int


@dataclass(frozen=True, slots=True)
class MatchGameStateReplay:
    contexts: dict[int, MatchEventGameStateContext]
    transitions: tuple[ScoreTransition, ...]
    episodes: tuple[EpisodeSpec, ...]
    exposures: tuple[ExposureSpec, ...]
    status: str
    eligible: bool
    exclusion_reason: str | None
    event_count: int
    goal_event_count: int
    ignored_goal_event_count: int
    shootout_goal_event_count: int
    replayed_home_score: int
    replayed_away_score: int
    replayed_shootout_home_score: int
    replayed_shootout_away_score: int
    diagnostics: dict[str, Any]


def is_goal_event(event: Any) -> bool:
    return int(event.event_type) == MatchEventType.OWN_GOAL or (
        int(event.event_type) == MatchEventType.SHOT
        and int(event.shot_outcome) == MatchEventShotOutcome.GOAL
    )


def state_from_difference(difference: int) -> int:
    if difference > 0:
        return MatchEventGameState.WINNING
    if difference < 0:
        return MatchEventGameState.LOSING
    return MatchEventGameState.DRAWING


def state_for_team(team: str, home: str, away: str, hs: int, aws: int) -> int | None:
    if team == home:
        return state_from_difference(hs - aws)
    if team == away:
        return state_from_difference(aws - hs)
    return None


def scoring_team_for_goal(event: Any, home: str, away: str) -> str | None:
    team = str(event.provider_team_id)
    if team not in {home, away}:
        return None
    if int(event.event_type) == MatchEventType.OWN_GOAL:
        return away if team == home else home
    return team


def event_sequence(event: Any) -> tuple[int, str, int]:
    value = getattr(event, "provider_event_sequence_id", None)
    value = getattr(event, "event_index", 0) if value is None else value
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 2**31 - 1
    return number, str(value), int(getattr(event, "event_index", 0))


def identity_keys(event: Any, *, related: bool = False) -> set[str]:
    names = (
        ("related_provider_event_sequence_id",)
        if related
        else ("provider_event_sequence_id",)
    )
    return {
        str(value)
        for name in names
        if (value := getattr(event, name, None)) not in (None, "")
    }


def score_replay(match: Any, events: Sequence[Any], clock: MatchClock | None):
    home, away = str(match.home_provider_team_id), str(match.away_provider_team_id)
    cancelled = {
        (str(event.provider_team_id), key)
        for event in events
        if getattr(event, "is_deleted_event", False)
        for key in identity_keys(event, related=True)
    }
    known = {
        (str(event.provider_team_id), key)
        for event in events
        for key in identity_keys(event)
    }
    warnings, errors = [], []
    if unresolved := sorted(cancelled - known):
        warnings.append(
            {"code": "unresolved_deleted_event_references", "event_ids": unresolved}
        )
    hs = aws = sho = sha = goals = ignored = shootout_goals = 0
    contexts, transitions = {}, []
    ordered = sorted(
        events,
        key=lambda e: (
            getattr(e, "timeline_seconds", None) is None,
            getattr(e, "timeline_seconds", 0) or 0,
            event_sequence(e),
        ),
    )
    for event in ordered:
        before_hs, before_aws, scoring = hs, aws, None
        period = int(event.period)
        if is_goal_event(event):
            goals += 1
            event_identity = {
                (str(event.provider_team_id), key) for key in identity_keys(event)
            }
            if (
                getattr(event, "is_goal_disallowed", False)
                or event_identity & cancelled
            ):
                ignored += 1
            else:
                scoring = scoring_team_for_goal(event, home, away)
                if scoring is None:
                    errors.append(
                        {
                            "code": "goal_team_not_in_match",
                            "event_index": event.event_index,
                        }
                    )
                elif period in SUPPORTED_PERIODS:
                    try:
                        second = (
                            validate_event_timestamp(event, clock) if clock else None
                        )
                        if second is None:
                            raise MatchClockError("clock_metadata_missing", "No clock.")
                    except MatchClockError as error:
                        errors.append(
                            {"code": error.code, "event_index": event.event_index}
                        )
                    else:
                        hs += scoring == home
                        aws += scoring == away
                        transitions.append(
                            ScoreTransition(
                                second,
                                event_sequence(event),
                                event,
                                scoring,
                                before_hs,
                                before_aws,
                                hs,
                                aws,
                            )
                        )
                elif period == MatchEventPeriod.PENALTY_SHOOTOUT:
                    shootout_goals += 1
                    sho += scoring == home
                    sha += scoring == away
                else:
                    ignored += 1
                    errors.append(
                        {
                            "code": "goal_outside_supported_play",
                            "event_index": event.event_index,
                            "period": period,
                        }
                    )
        acting = str(event.provider_team_id)
        contexts[int(event.event_index)] = MatchEventGameStateContext(
            before_hs,
            before_aws,
            hs,
            aws,
            (
                state_for_team(acting, home, away, before_hs, before_aws)
                if period in SUPPORTED_PERIODS
                else None
            ),
            (
                state_for_team(acting, home, away, hs, aws)
                if period in SUPPORTED_PERIODS
                else None
            ),
            scoring,
        )
    return (
        contexts,
        tuple(transitions),
        dict(
            warnings=warnings,
            errors=errors,
            goal_event_count=goals,
            ignored_goal_event_count=ignored,
            shootout_goal_event_count=shootout_goals,
            home_score=hs,
            away_score=aws,
            shootout_home_score=sho,
            shootout_away_score=sha,
            cancelled_event_ids=[
                {"provider_team_id": team_id, "event_sequence_id": sequence_id}
                for team_id, sequence_id in sorted(cancelled)
            ],
        ),
    )


def replay_status(match: Any, data: dict[str, Any]) -> str:
    if data["errors"]:
        return MatchGameStateStatus.INVALID
    stored = match.home_score, match.away_score
    replayed = data["home_score"], data["away_score"]
    shootout = (
        replayed[0] + data["shootout_home_score"],
        replayed[1] + data["shootout_away_score"],
    )
    if None in stored:
        return MatchGameStateStatus.UNVERIFIED
    if stored == replayed:
        return (
            MatchGameStateStatus.VERIFIED_WITH_SHOOTOUT
            if data["shootout_goal_event_count"]
            else MatchGameStateStatus.VERIFIED
        )
    if data["shootout_goal_event_count"] and stored == shootout:
        data["warnings"].append({"code": "stored_score_includes_shootout"})
        return MatchGameStateStatus.VERIFIED_WITH_SHOOTOUT
    data["errors"].append(
        {
            "code": "event_score_does_not_match_match_score",
            "replayed_score": replayed,
            "stored_score": stored,
        }
    )
    return MatchGameStateStatus.SCORE_MISMATCH


def exclusion_reason(match: Any, status: str, clock_error: MatchClockError | None):
    if str(match.status) != ProviderMatchStatus.COMPLETED:
        return MatchGameStateExclusionReason.NOT_COMPLETED
    if getattr(match, "pk", None) is not None:
        try:
            payload = match.payload
        except (AttributeError, ProviderMatchPayload.DoesNotExist):
            return MatchGameStateExclusionReason.NON_FINAL_PAYLOAD
        if payload.lifecycle_state != ProviderPayloadLifecycle.FINAL:
            return MatchGameStateExclusionReason.NON_FINAL_PAYLOAD
    if (
        match.home_team_id is None
        or match.away_team_id is None
        or match.home_team_id == match.away_team_id
    ):
        return MatchGameStateExclusionReason.TEAM_IDENTITY_UNRESOLVED
    if clock_error:
        return (
            MatchGameStateExclusionReason.CLOCK_METADATA_MISSING
            if clock_error.code == "clock_metadata_missing"
            else MatchGameStateExclusionReason.CLOCK_METADATA_INVALID
        )
    if match.home_score is None:
        return MatchGameStateExclusionReason.SCORE_UNAVAILABLE
    if status == MatchGameStateStatus.SCORE_MISMATCH:
        return MatchGameStateExclusionReason.SCORE_MISMATCH
    if status not in {
        MatchGameStateStatus.VERIFIED,
        MatchGameStateStatus.VERIFIED_WITH_SHOOTOUT,
    }:
        return MatchGameStateExclusionReason.INVALID_SCORE_REPLAY
    return None


def focal_scores(t: ScoreTransition, home: bool):
    return (
        (
            t.home_score_before,
            t.away_score_before,
            t.home_score_after,
            t.away_score_after,
        )
        if home
        else (
            t.away_score_before,
            t.home_score_before,
            t.away_score_after,
            t.home_score_after,
        )
    )


def build_focal_episodes(
    match: Any, clock: MatchClock, transitions: Sequence[ScoreTransition]
):
    result = []
    ordered = sorted(transitions, key=lambda t: (t.second, t.sequence))
    sides = (
        (int(match.home_team_id), True, str(match.home_provider_team_id)),
        (int(match.away_team_id), False, str(match.away_provider_team_id)),
    )
    for team_id, is_home, provider_team_id in sides:
        current, previous, entered_at, entered_by, entered_index = (
            MatchEventGameState.DRAWING,
            None,
            0,
            None,
            None,
        )
        provenance = MatchStateDrawProvenance.NEUTRAL
        lineage = [
            (0, current, previous, entered_at, entered_by, entered_index, provenance)
        ]
        for transition in ordered:
            _, _, fs, os = focal_scores(transition, is_home)
            new = state_from_difference(fs - os)
            if new != current:
                previous, current, entered_at = current, new, transition.second
                entered_by, entered_index = transition.event, int(
                    transition.event.event_index
                )
                provenance = (
                    (
                        MatchStateDrawProvenance.RESTORED
                        if transition.scoring_provider_team_id == provider_team_id
                        else MatchStateDrawProvenance.SURRENDERED
                    )
                    if new == MatchEventGameState.DRAWING
                    else MatchStateDrawProvenance.NONE
                )
            lineage.append(
                (
                    transition.second,
                    current,
                    previous,
                    entered_at,
                    entered_by,
                    entered_index,
                    provenance,
                )
            )
        index = 0
        for period in clock.periods:
            boundaries = {
                period.start_second,
                period.end_second,
                *(t.second for t in ordered if period.contains(t.second)),
            }
            if period.nominal_end_second < period.end_second:
                boundaries.add(period.nominal_end_second)
            values = sorted(boundaries)
            for start, end in zip(values, values[1:]):
                if end <= start:
                    continue
                prior = [t for t in ordered if t.second <= start]
                if prior:
                    latest = prior[-1]
                    fs, os = (
                        (latest.home_score_after, latest.away_score_after)
                        if is_home
                        else (latest.away_score_after, latest.home_score_after)
                    )
                else:
                    fs = os = 0
                _, state, previous_state, state_entry, entry, entry_index, draw = [
                    row for row in lineage if row[0] <= start
                ][-1]
                result.append(
                    EpisodeSpec(
                        team_id,
                        is_home,
                        index,
                        int(period.period),
                        PHASE_BY_PERIOD[int(period.period)],
                        start,
                        end,
                        end - start,
                        period.is_added_time(start),
                        fs,
                        os,
                        fs - os,
                        state,
                        previous_state,
                        draw,
                        state_entry,
                        start - state_entry,
                        entry,
                        entry_index,
                    )
                )
                index += 1
    return tuple(result)


def build_exposures(episodes: Sequence[EpisodeSpec]):
    grouped = defaultdict(lambda: [0, 0])
    for e in episodes:
        key = e.focal_team_id, e.state, e.goal_difference, e.phase, e.draw_provenance
        grouped[key][0] += e.duration_seconds
        grouped[key][1] += 1
    return tuple(
        ExposureSpec(*key, exposure_seconds=value[0], episode_count=value[1])
        for key, value in sorted(
            grouped.items(), key=lambda item: tuple(str(v) for v in item[0])
        )
    )


def replay_match_game_state(
    match: Any, events: Iterable[Any], *, clock=None
) -> MatchGameStateReplay:
    rows, resolved, clock_error = list(events), None, None
    try:
        if clock is not None:
            resolved = coerce_match_clock(clock)
        elif getattr(match, "pk", None):
            resolved = match_clock_from_period_rows(match.played_periods.all())
        else:
            raise MatchClockError("clock_metadata_missing", "No match clock supplied.")
    except MatchClockError as error:
        clock_error = error
    contexts, transitions, data = score_replay(match, rows, resolved)
    status = MatchGameStateStatus.NO_EVENTS if not rows else replay_status(match, data)
    reason = exclusion_reason(match, status, clock_error)
    episodes = (
        build_focal_episodes(match, resolved, transitions)
        if reason is None and resolved
        else ()
    )
    exposures = build_exposures(episodes)
    if reason:
        contexts = {
            key: replace(value, game_state_before=None, game_state_after=None)
            for key, value in contexts.items()
        }
    diagnostics = {
        "calculation_version": GAME_STATE_CALCULATION_VERSION,
        "clock_calculation_version": (
            resolved.calculation_version if resolved else CLOCK_CALCULATION_VERSION
        ),
        "status": status,
        "eligible": reason is None,
        "exclusion_reason": reason,
        "warnings": data["warnings"],
        "errors": data["errors"],
        "cancelled_event_ids": data["cancelled_event_ids"],
        "replayed_score": {"home": data["home_score"], "away": data["away_score"]},
        "replayed_shootout_score": {
            "home": data["shootout_home_score"],
            "away": data["shootout_away_score"],
        },
        "stored_score": {"home": match.home_score, "away": match.away_score},
        "clock": resolved.as_dict() if resolved else None,
    }
    return MatchGameStateReplay(
        contexts,
        transitions,
        episodes,
        exposures,
        status,
        reason is None,
        reason,
        len(rows),
        data["goal_event_count"],
        data["ignored_goal_event_count"],
        data["shootout_goal_event_count"],
        data["home_score"],
        data["away_score"],
        data["shootout_home_score"],
        data["shootout_away_score"],
        diagnostics,
    )


@transaction.atomic
def materialize_match_game_state(
    provider_match: ProviderMatch, *, events=None, clock=None, calculated_at=None
):
    match = ProviderMatch.objects.select_for_update().get(pk=provider_match.pk)
    rows = list(
        events
        if events is not None
        else ProviderMatchEvent.objects.filter(provider_match=match).order_by(
            "timeline_seconds", "provider_event_sequence_id", "event_index"
        )
    )
    resolved = None
    try:
        resolved = (
            coerce_match_clock(clock)
            if clock is not None
            else match_clock_from_period_rows(match.played_periods.all())
        )
    except MatchClockError:
        pass
    replay = replay_match_game_state(
        match, rows, clock=clock if clock is not None else resolved
    )
    ProviderMatchTeamGameStateExposure.objects.filter(provider_match=match).delete()
    ProviderMatchTeamGameStateEpisode.objects.filter(provider_match=match).delete()
    if clock is not None:
        ProviderMatchPlayedPeriod.objects.filter(provider_match=match).delete()
    if clock is not None and resolved:
        ProviderMatchPlayedPeriod.objects.bulk_create(
            [
                ProviderMatchPlayedPeriod(
                    provider_match=match,
                    period=p.period,
                    period_index=p.period_index,
                    start_second=p.start_second,
                    end_second=p.end_second,
                    duration_seconds=p.duration_seconds,
                    calculation_version=resolved.calculation_version,
                )
                for p in resolved.periods
            ]
        )
    fields = (
        "home_score_before",
        "away_score_before",
        "home_score_after",
        "away_score_after",
        "game_state_before",
        "game_state_after",
        "scoring_provider_team_id",
    )
    for event in rows:
        context = replay.contexts[int(event.event_index)]
        for field in fields:
            setattr(event, field, getattr(context, field))
    if rows:
        # Keep CASE expressions bounded. Large WhoScored matches can contain
        # thousands of events and Django's expression compiler becomes the
        # dominant cost with a 1,000-row, seven-field update.
        ProviderMatchEvent.objects.bulk_update(rows, fields, batch_size=200)
    ProviderMatchTeamGameStateEpisode.objects.bulk_create(
        [
            ProviderMatchTeamGameStateEpisode(
                provider_match=match,
                calculation_version=GAME_STATE_CALCULATION_VERSION,
                **{field.name: getattr(e, field.name) for field in dataclass_fields(e)},
            )
            for e in replay.episodes
        ],
        batch_size=1000,
    )
    ProviderMatchTeamGameStateExposure.objects.bulk_create(
        [
            ProviderMatchTeamGameStateExposure(
                provider_match=match,
                calculation_version=GAME_STATE_CALCULATION_VERSION,
                **{field.name: getattr(e, field.name) for field in dataclass_fields(e)},
            )
            for e in replay.exposures
        ],
        batch_size=1000,
    )
    try:
        checksum = match.payload.payload_sha256
    except (AttributeError, ProviderMatchPayload.DoesNotExist):
        checksum = ""
    defaults = dict(
        status=replay.status,
        eligible=replay.eligible,
        exclusion_reason=replay.exclusion_reason,
        calculation_version=GAME_STATE_CALCULATION_VERSION,
        source_checksum=checksum,
        event_count=replay.event_count,
        goal_event_count=replay.goal_event_count,
        ignored_goal_event_count=replay.ignored_goal_event_count,
        shootout_goal_event_count=replay.shootout_goal_event_count,
        replayed_home_score=replay.replayed_home_score,
        replayed_away_score=replay.replayed_away_score,
        replayed_shootout_home_score=replay.replayed_shootout_home_score,
        replayed_shootout_away_score=replay.replayed_shootout_away_score,
        supported_start_second=resolved.supported_start_second if resolved else None,
        supported_end_second=resolved.supported_end_second if resolved else None,
        exposure_seconds=(
            resolved.exposure_seconds if resolved and replay.eligible else 0
        ),
        period_count=len(resolved.periods) if resolved else 0,
        episode_count=len(replay.episodes),
        focal_team_count=2 if replay.eligible else 0,
        diagnostics=replay.diagnostics,
        calculated_at=calculated_at or timezone.now(),
    )
    return ProviderMatchGameState.objects.update_or_create(
        provider_match=match, defaults=defaults
    )[0]


def get_match_state_eligibility(match: ProviderMatch):
    try:
        audit = match.game_state
    except ProviderMatchGameState.DoesNotExist:
        return {
            "eligible": False,
            "status": MatchGameStateStatus.UNVERIFIED,
            "exclusion_reason": MatchGameStateExclusionReason.INVALID_SCORE_REPLAY,
            "formula_version": GAME_STATE_CALCULATION_VERSION,
        }
    return {
        "eligible": audit.eligible,
        "status": audit.status,
        "exclusion_reason": audit.exclusion_reason,
        "formula_version": audit.calculation_version,
    }


def state_context_for_event(event: ProviderMatchEvent, focal_team: Any):
    if event.timeline_seconds is None:
        return None
    team_id = int(getattr(focal_team, "pk", focal_team))
    episode = ProviderMatchTeamGameStateEpisode.objects.filter(
        provider_match_id=event.provider_match_id,
        focal_team_id=team_id,
        start_second__lte=event.timeline_seconds,
        end_second__gt=event.timeline_seconds,
    ).first()
    if not episode:
        return None
    return {
        "state": episode.state,
        "goal_difference": episode.goal_difference,
        "phase": episode.phase,
        "draw_provenance": episode.draw_provenance,
        "state_age_seconds": event.timeline_seconds - episode.state_entry_second,
        "episode_index": episode.episode_index,
    }


def scope_events_to_focal_state(
    queryset: QuerySet,
    focal_team: Any,
    *,
    state=None,
    goal_difference=None,
    phase=None,
    draw_provenance=None,
    minimum_state_age_seconds=None,
    maximum_state_age_seconds=None,
):
    episodes = ProviderMatchTeamGameStateEpisode.objects.filter(
        provider_match_id=OuterRef("provider_match_id"),
        focal_team_id=int(getattr(focal_team, "pk", focal_team)),
        start_second__lte=OuterRef("timeline_seconds"),
        end_second__gt=OuterRef("timeline_seconds"),
    )
    for field, value in (
        ("state", state),
        ("goal_difference", goal_difference),
        ("phase", phase),
        ("draw_provenance", draw_provenance),
    ):
        if value is not None:
            episodes = episodes.filter(**{field: value})
    if minimum_state_age_seconds is not None:
        episodes = episodes.filter(
            state_entry_second__lte=OuterRef("timeline_seconds")
            - minimum_state_age_seconds
        )
    if maximum_state_age_seconds is not None:
        episodes = episodes.filter(
            state_entry_second__gt=OuterRef("timeline_seconds")
            - maximum_state_age_seconds
        )
    return (
        queryset.filter(timeline_seconds__isnull=False)
        .annotate(in_focal_game_state=Exists(episodes))
        .filter(in_focal_game_state=True)
    )


def game_state_exposure(focal_team: Any, matches, **filters):
    ids = (
        list(matches.values_list("pk", flat=True))
        if isinstance(matches, QuerySet)
        else [int(getattr(m, "pk", m)) for m in matches]
    )
    rows = ProviderMatchTeamGameStateExposure.objects.filter(
        provider_match_id__in=ids,
        focal_team_id=int(getattr(focal_team, "pk", focal_team)),
    )
    rows = rows.filter(
        **{key: value for key, value in filters.items() if value is not None}
    )
    values = rows.aggregate(
        exposure_seconds=Sum("exposure_seconds"),
        episode_count=Sum("episode_count"),
        match_count=Count("provider_match_id", distinct=True),
    )
    return {key: int(value or 0) for key, value in values.items()}


def public_game_state_metadata(focal_team: Any, matches, **filters):
    ids = (
        list(matches.values_list("pk", flat=True))
        if isinstance(matches, QuerySet)
        else [int(getattr(m, "pk", m)) for m in matches]
    )
    audits = ProviderMatchGameState.objects.filter(provider_match_id__in=ids)
    included = audits.filter(eligible=True).count()
    reasons = {
        str(
            row["exclusion_reason"]
            or MatchGameStateExclusionReason.INVALID_SCORE_REPLAY
        ): row["count"]
        for row in audits.filter(eligible=False)
        .values("exclusion_reason")
        .annotate(count=Count("id"))
    }
    missing = len(ids) - audits.count()
    if missing:
        key = str(MatchGameStateExclusionReason.INVALID_SCORE_REPLAY)
        reasons[key] = reasons.get(key, 0) + missing
    return {
        "formula_version": GAME_STATE_CALCULATION_VERSION,
        **game_state_exposure(focal_team, ids, **filters),
        "matches_included": included,
        "matches_excluded": len(ids) - included,
        "exclusion_reasons": dict(sorted(reasons.items())),
        "reliability": {
            "eligible_only": True,
            "timeline": "half_open_played_seconds",
            "shootouts_included": False,
        },
    }
