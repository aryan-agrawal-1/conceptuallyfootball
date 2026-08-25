"""Verified player participation and game-state exposure materialization.

Raw provider lineup objects are normalized before entering this module.  This
service deliberately works with provider-neutral evidence and a shared,
continuous match clock supplied by the game-state episode foundation.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from django.db import transaction
from django.utils import timezone

from ingestion.models import (
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchPayload,
    ProviderMatchPlayedPeriod,
    ProviderMatchPlayerInterval,
    ProviderMatchPlayerParticipation,
    ProviderMatchPlayerParticipationBuild,
    ProviderMatchPlayerStateExposure,
    ProviderMatchTeamGameStateEpisode,
    ProviderPlayerMapping,
    ProviderTeamMapping,
)


PARTICIPATION_FORMULA_VERSION = "player_participation_v1"
PLAYER_STATE_EXPOSURE_FORMULA_VERSION = "player_state_exposure_v1"

ENTRY_ACTIONS = frozenset({"substitution_on", "player_on", "player_returns"})
EXIT_ACTIONS = frozenset({"substitution_off", "player_off", "player_retired"})
SUBSTITUTION_ACTIONS = frozenset({"substitution_on", "substitution_off"})
DISMISSALS = frozenset({"red", "second_yellow"})

# State age is kept exact on each exposure row.  These stable public buckets
# are an additional grouping, not a replacement for the exact second values.
STATE_AGE_BUCKETS = (
    (0, 300, "0_5_minutes"),
    (300, 900, "5_15_minutes"),
    (900, None, "15_plus_minutes"),
)


@dataclass(frozen=True)
class LineupPlayerEvidence:
    provider_team_id: str
    provider_player_id: str
    roster_index: int
    starting_status: str
    position_role: str = "unknown"


@dataclass(frozen=True)
class ParticipationEventEvidence:
    event_index: int
    provider_team_id: str
    provider_player_id: str | None
    timeline_seconds: int | None
    participation_action: str = "none"
    dismissal_type: str = "none"
    provider_event_sequence_id: str | None = None
    related_provider_event_sequence_id: str | None = None
    related_provider_player_id: str | None = None
    is_deleted_event: bool = False
    is_rescinded_event: bool = False


@dataclass(frozen=True)
class IntervalDraft:
    start_second: int
    end_second: int
    start_evidence: str
    end_evidence: str
    start_event_index: int | None = None
    end_event_index: int | None = None
    start_event_sequence_id: str | None = None
    end_event_sequence_id: str | None = None
    confidence: str = "verified"
    exclusion_reason: str | None = None

    @property
    def duration_seconds(self) -> int:
        return self.end_second - self.start_second


@dataclass
class ParticipantDraft:
    provider_team_id: str
    provider_player_id: str
    roster_role: str
    position_role: str
    status: str = "verified"
    confidence: str = "verified"
    exclusion_reason: str | None = None
    intervals: list[IntervalDraft] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    @property
    def on_pitch_seconds(self) -> int:
        return sum(interval.duration_seconds for interval in self.intervals)


@dataclass(frozen=True)
class ParticipationReconstruction:
    status: str
    participants: tuple[ParticipantDraft, ...]
    diagnostics: dict[str, Any]


def evidence_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def optional_identifier(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def normalize_lineup_player(value: Any, index: int) -> LineupPlayerEvidence:
    starting_status = evidence_value(
        value,
        "starting_status",
        evidence_value(value, "roster_role"),
    )
    if starting_status is None:
        starting_status = (
            "starter" if evidence_value(value, "is_starter", False) else "substitute"
        )
    position_role = str(evidence_value(value, "position_role", "unknown") or "unknown")
    return LineupPlayerEvidence(
        provider_team_id=str(evidence_value(value, "provider_team_id")),
        provider_player_id=str(evidence_value(value, "provider_player_id")),
        roster_index=int(evidence_value(value, "roster_index", index)),
        starting_status=str(starting_status),
        position_role=position_role,
    )


def normalize_participation_event(value: Any) -> ParticipationEventEvidence:
    return ParticipationEventEvidence(
        event_index=int(evidence_value(value, "event_index")),
        provider_team_id=str(evidence_value(value, "provider_team_id")),
        provider_player_id=optional_identifier(
            evidence_value(value, "provider_player_id")
        ),
        timeline_seconds=evidence_value(value, "timeline_seconds"),
        participation_action=str(
            evidence_value(value, "participation_action", "none") or "none"
        ),
        dismissal_type=str(evidence_value(value, "dismissal_type", "none") or "none"),
        provider_event_sequence_id=optional_identifier(
            evidence_value(value, "provider_event_sequence_id")
        ),
        related_provider_event_sequence_id=optional_identifier(
            evidence_value(value, "related_provider_event_sequence_id")
        ),
        related_provider_player_id=optional_identifier(
            evidence_value(value, "related_provider_player_id")
        ),
        is_deleted_event=bool(evidence_value(value, "is_deleted_event", False)),
        is_rescinded_event=bool(evidence_value(value, "is_rescinded_event", False)),
    )


def mark_excluded(participant: ParticipantDraft, reason: str, **detail: Any) -> None:
    participant.status = "excluded"
    participant.confidence = "unverified"
    if participant.exclusion_reason is None:
        participant.exclusion_reason = reason
    participant.diagnostics.append({"code": reason, **detail})


def substitution_pair_errors(
    events: Sequence[ParticipationEventEvidence],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Return player-scoped errors for substitution evidence that cannot pair."""
    errors: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    substitutions = [
        event for event in events if event.participation_action in SUBSTITUTION_ACTIONS
    ]
    by_sequence = {
        (event.provider_team_id, event.provider_event_sequence_id): event
        for event in substitutions
        if event.provider_event_sequence_id
    }

    for event in substitutions:
        opposite = (
            "substitution_off"
            if event.participation_action == "substitution_on"
            else "substitution_on"
        )
        candidates: list[ParticipationEventEvidence] = []
        if event.related_provider_event_sequence_id:
            related = by_sequence.get(
                (event.provider_team_id, event.related_provider_event_sequence_id)
            )
            if related is not None:
                candidates = [related]
        if not candidates and event.related_provider_player_id:
            candidates = [
                candidate
                for candidate in substitutions
                if candidate.provider_team_id == event.provider_team_id
                and candidate.provider_player_id == event.related_provider_player_id
                and candidate.participation_action == opposite
                and candidate.timeline_seconds == event.timeline_seconds
            ]
        if not candidates:
            candidates = [
                candidate
                for candidate in substitutions
                if candidate is not event
                and candidate.provider_team_id == event.provider_team_id
                and candidate.participation_action == opposite
                and candidate.timeline_seconds == event.timeline_seconds
            ]
        valid = [
            candidate
            for candidate in candidates
            if candidate.participation_action == opposite
            and candidate.provider_team_id == event.provider_team_id
        ]
        if len(valid) == 1:
            continue
        if event.provider_player_id is not None:
            errors[(event.provider_team_id, event.provider_player_id)].append(
                {
                    "code": "unmatched_substitution_event",
                    "event_index": event.event_index,
                    "candidate_count": len(valid),
                }
            )
    return errors


def reconstruct_player_intervals(
    *,
    lineup_players: Iterable[Any],
    events: Iterable[Any],
    match_start_second: int,
    match_end_second: int,
    valid_team_ids: Iterable[str],
) -> ParticipationReconstruction:
    """Build player intervals without guessing missing lineup or clock evidence."""
    if match_start_second < 0 or match_end_second <= match_start_second:
        raise ValueError("A verified positive match interval is required.")

    team_ids = {str(team_id) for team_id in valid_team_ids}
    lineup = [
        normalize_lineup_player(value, index)
        for index, value in enumerate(lineup_players)
    ]
    normalized_events = [normalize_participation_event(value) for value in events]
    diagnostics: dict[str, Any] = {"warnings": [], "errors": []}

    participants: dict[tuple[str, str], ParticipantDraft] = {}
    duplicate_lineup_keys: set[tuple[str, str]] = set()
    for player in sorted(
        lineup,
        key=lambda item: (
            item.provider_team_id,
            item.roster_index,
            item.provider_player_id,
        ),
    ):
        key = (player.provider_team_id, player.provider_player_id)
        if key in participants:
            duplicate_lineup_keys.add(key)
            continue
        participants[key] = ParticipantDraft(
            provider_team_id=player.provider_team_id,
            provider_player_id=player.provider_player_id,
            roster_role=player.starting_status,
            position_role=player.position_role,
        )

    lineup_by_team: dict[str, list[LineupPlayerEvidence]] = defaultdict(list)
    for player in lineup:
        lineup_by_team[player.provider_team_id].append(player)
    invalid_teams: dict[str, str] = {}
    for team_id in sorted(team_ids):
        team_lineup = lineup_by_team.get(team_id, [])
        if not team_lineup:
            invalid_teams[team_id] = "missing_team_lineup"
            continue
        starter_count = sum(
            player.starting_status == "starter" for player in team_lineup
        )
        if starter_count != 11:
            invalid_teams[team_id] = "invalid_starter_count"
    for player in lineup:
        if player.provider_team_id not in team_ids:
            invalid_teams[player.provider_team_id] = "lineup_team_not_in_match"

    for key in duplicate_lineup_keys:
        mark_excluded(participants[key], "duplicate_lineup_player")
    for participant in participants.values():
        if participant.provider_team_id in invalid_teams:
            mark_excluded(
                participant,
                invalid_teams[participant.provider_team_id],
            )

    # Corrections cancel evidence in the raw eventId namespace, not the raw id
    # namespace.  This distinction is material for WhoScored payloads.
    cancelled_sequence_ids = {
        (event.provider_team_id, event.related_provider_event_sequence_id)
        for event in normalized_events
        if (event.is_deleted_event or event.is_rescinded_event)
        and event.related_provider_event_sequence_id
    }
    evidence_events = [
        event
        for event in normalized_events
        if (event.provider_team_id, event.provider_event_sequence_id)
        not in cancelled_sequence_ids
        and not event.is_deleted_event
        and not event.is_rescinded_event
        and (event.participation_action != "none" or event.dismissal_type in DISMISSALS)
    ]

    # Collapse exact duplicates and reject conflicting reuse of a source event id.
    deduplicated: list[ParticipationEventEvidence] = []
    seen_fingerprints: set[tuple[Any, ...]] = set()
    sequence_fingerprints: dict[tuple[str, str], tuple[Any, ...]] = {}
    for event in sorted(
        evidence_events,
        key=lambda item: (
            item.timeline_seconds if item.timeline_seconds is not None else 2**31,
            item.event_index,
        ),
    ):
        fingerprint = (
            event.provider_team_id,
            event.provider_player_id,
            event.timeline_seconds,
            event.participation_action,
            event.dismissal_type,
        )
        if fingerprint in seen_fingerprints:
            diagnostics["warnings"].append(
                {
                    "code": "duplicate_participation_event",
                    "event_index": event.event_index,
                }
            )
            continue
        seen_fingerprints.add(fingerprint)
        if event.provider_event_sequence_id:
            sequence_key = (
                event.provider_team_id,
                event.provider_event_sequence_id,
            )
            previous = sequence_fingerprints.get(sequence_key)
            if previous is not None and previous != fingerprint:
                for player_id in {event.provider_player_id, previous[1]} - {None}:
                    key = (event.provider_team_id, str(player_id))
                    participant = participants.get(key)
                    if participant is not None:
                        mark_excluded(
                            participant,
                            "conflicting_event_sequence_id",
                            event_sequence_id=event.provider_event_sequence_id,
                        )
                continue
            sequence_fingerprints[sequence_key] = fingerprint
        deduplicated.append(event)

    for event in deduplicated:
        if event.provider_player_id is None:
            continue
        key = (event.provider_team_id, event.provider_player_id)
        if key not in participants:
            participants[key] = ParticipantDraft(
                provider_team_id=event.provider_team_id,
                provider_player_id=event.provider_player_id,
                roster_role="added",
                position_role="unknown",
            )

    for key, pair_errors in substitution_pair_errors(deduplicated).items():
        participant = participants.get(key)
        if participant is not None:
            for error in pair_errors:
                mark_excluded(
                    participant,
                    error["code"],
                    **{k: v for k, v in error.items() if k != "code"},
                )

    active: dict[tuple[str, str], tuple[int, str, int | None, str | None]] = {}
    for key, participant in participants.items():
        if participant.roster_role == "starter" and participant.status != "excluded":
            active[key] = (match_start_second, "lineup_starter", None, None)

    for event in deduplicated:
        timestamp = event.timeline_seconds
        if timestamp is None or not match_start_second <= timestamp <= match_end_second:
            if event.provider_player_id is not None:
                participant = participants.get(
                    (event.provider_team_id, event.provider_player_id)
                )
                if participant is not None:
                    mark_excluded(
                        participant,
                        "invalid_participation_timestamp",
                        event_index=event.event_index,
                    )
            continue

        if event.dismissal_type in DISMISSALS and event.provider_player_id is None:
            for key, participant in participants.items():
                if key[0] == event.provider_team_id and key in active:
                    mark_excluded(
                        participant,
                        "dismissal_player_missing",
                        event_index=event.event_index,
                    )
            continue
        if event.provider_player_id is None:
            continue

        key = (event.provider_team_id, event.provider_player_id)
        participant = participants[key]
        if event.participation_action in ENTRY_ACTIONS:
            if key in active:
                mark_excluded(
                    participant,
                    "entry_while_active",
                    event_index=event.event_index,
                )
            else:
                active[key] = (
                    timestamp,
                    event.participation_action,
                    event.event_index,
                    event.provider_event_sequence_id,
                )
            continue

        exit_evidence = (
            event.participation_action
            if event.participation_action in EXIT_ACTIONS
            else None
        )
        if event.dismissal_type in DISMISSALS:
            exit_evidence = f"dismissal_{event.dismissal_type}"
        if exit_evidence is None:
            continue
        started = active.pop(key, None)
        if started is None:
            mark_excluded(
                participant,
                "exit_while_inactive",
                event_index=event.event_index,
            )
            continue
        start_second, start_evidence, start_index, start_sequence = started
        if timestamp <= start_second:
            mark_excluded(
                participant,
                "non_positive_interval",
                event_index=event.event_index,
            )
            continue
        participant.intervals.append(
            IntervalDraft(
                start_second=start_second,
                end_second=timestamp,
                start_evidence=start_evidence,
                end_evidence=exit_evidence,
                start_event_index=start_index,
                end_event_index=event.event_index,
                start_event_sequence_id=start_sequence,
                end_event_sequence_id=event.provider_event_sequence_id,
            )
        )

    for key, started in active.items():
        participant = participants[key]
        start_second, start_evidence, start_index, start_sequence = started
        if match_end_second <= start_second:
            mark_excluded(participant, "non_positive_interval")
            continue
        participant.intervals.append(
            IntervalDraft(
                start_second=start_second,
                end_second=match_end_second,
                start_evidence=start_evidence,
                end_evidence="match_end",
                start_event_index=start_index,
                start_event_sequence_id=start_sequence,
            )
        )

    for participant in participants.values():
        participant.intervals.sort(
            key=lambda interval: (interval.start_second, interval.end_second)
        )
        if participant.status == "excluded":
            continue
        if not participant.intervals:
            if participant.roster_role == "substitute":
                participant.status = "unused"
                participant.confidence = "verified"
            else:
                mark_excluded(participant, "no_verified_interval")

    ordered = tuple(
        sorted(
            participants.values(),
            key=lambda participant: (
                participant.provider_team_id,
                participant.provider_player_id,
            ),
        )
    )
    verified_count = sum(item.status == "verified" for item in ordered)
    excluded_count = sum(item.status == "excluded" for item in ordered)
    status = (
        "excluded"
        if not verified_count
        else "partial" if excluded_count else "verified"
    )
    diagnostics.update(
        {
            "invalid_teams": invalid_teams,
            "cancelled_event_sequence_ids": [
                {"provider_team_id": team_id, "event_sequence_id": sequence_id}
                for team_id, sequence_id in sorted(cancelled_sequence_ids)
            ],
            "participant_count": len(ordered),
            "verified_participant_count": verified_count,
            "excluded_participant_count": excluded_count,
        }
    )
    return ParticipationReconstruction(
        status=status, participants=ordered, diagnostics=diagnostics
    )


def state_age_bucket(age_seconds: int) -> str:
    if age_seconds < 0:
        raise ValueError("State age cannot be negative.")
    for lower, upper, label in STATE_AGE_BUCKETS:
        if age_seconds >= lower and (upper is None or age_seconds < upper):
            return label
    raise AssertionError("State-age buckets must cover all non-negative seconds.")


def split_exposure_by_state_age(
    *,
    start_second: int,
    end_second: int,
    episode_start_second: int,
    episode_state_age_at_start: int,
) -> list[tuple[int, int, int, int, str]]:
    """Split an overlap so each returned segment belongs to one age bucket."""
    if end_second <= start_second:
        return []
    start_age = episode_state_age_at_start + start_second - episode_start_second
    end_age = episode_state_age_at_start + end_second - episode_start_second
    cut_points = {start_second, end_second}
    for lower, _, _ in STATE_AGE_BUCKETS[1:]:
        if start_age < lower < end_age:
            cut_points.add(episode_start_second + lower - episode_state_age_at_start)
    points = sorted(cut_points)
    return [
        (
            segment_start,
            segment_end,
            episode_state_age_at_start + segment_start - episode_start_second,
            episode_state_age_at_start + segment_end - episode_start_second,
            state_age_bucket(
                episode_state_age_at_start + segment_start - episode_start_second
            ),
        )
        for segment_start, segment_end in zip(points, points[1:])
        if segment_end > segment_start
    ]


def canonical_identity_maps(
    provider_match,
    *,
    provider_player_ids: Iterable[str],
    provider_team_ids: Iterable[str],
):
    player_ids = set(provider_player_ids)
    team_ids = set(provider_team_ids)
    player_map = dict(
        ProviderPlayerMapping.objects.filter(
            provider=provider_match.provider,
            provider_player_id__in=player_ids,
        ).values_list("provider_player_id", "canonical_player_id")
    )
    team_map = dict(
        ProviderTeamMapping.objects.filter(
            provider=provider_match.provider,
            provider_team_id__in=team_ids,
        ).values_list("provider_team_id", "canonical_team_id")
    )
    return player_map, team_map


@transaction.atomic
def materialize_match_player_participation(
    provider_match,
    *,
    lineup_players: Iterable[Any],
    events: Iterable[Any] | None = None,
    calculated_at=None,
):
    """Transactionally replace one match's participation and exposure rows."""
    locked_match = ProviderMatch.objects.select_for_update().get(pk=provider_match.pk)
    normalized_lineup = [
        normalize_lineup_player(value, index)
        for index, value in enumerate(lineup_players)
    ]
    periods = list(
        ProviderMatchPlayedPeriod.objects.filter(provider_match=locked_match).order_by(
            "period_index"
        )
    )
    if not periods:
        ProviderMatchPlayerParticipationBuild.objects.filter(
            provider_match=locked_match
        ).delete()
        try:
            payload = locked_match.payload
        except ProviderMatchPayload.DoesNotExist:
            payload = None
        build = ProviderMatchPlayerParticipationBuild.objects.create(
            provider_match=locked_match,
            status="excluded" if normalized_lineup else "no_lineup",
            formula_version=PARTICIPATION_FORMULA_VERSION,
            source_payload_sha256=getattr(payload, "payload_sha256", ""),
            match_clock_version="",
            team_episode_version="",
            participant_count=len(normalized_lineup),
            verified_participant_count=0,
            excluded_participant_count=len(normalized_lineup),
            unused_player_count=0,
            interval_count=0,
            verified_seconds=0,
            diagnostics={"errors": [{"code": "match_clock_unverified"}]},
            calculated_at=calculated_at or timezone.now(),
        )
        player_map, team_map = canonical_identity_maps(
            locked_match,
            provider_player_ids=(item.provider_player_id for item in normalized_lineup),
            provider_team_ids=(item.provider_team_id for item in normalized_lineup),
        )
        ProviderMatchPlayerParticipation.objects.bulk_create(
            [
                ProviderMatchPlayerParticipation(
                    build=build,
                    provider_match=locked_match,
                    provider_team_id=item.provider_team_id,
                    team_id=team_map.get(item.provider_team_id),
                    provider_player_id=item.provider_player_id,
                    player_id=player_map.get(item.provider_player_id),
                    roster_role=item.starting_status,
                    position_role=item.position_role,
                    status="excluded",
                    confidence="unverified",
                    exclusion_reason="match_clock_unverified",
                    on_pitch_seconds=0,
                    excluded_seconds=0,
                    interval_count=0,
                    diagnostics={},
                )
                for item in normalized_lineup
            ],
            batch_size=1000,
        )
        return build
    match_start_second = periods[0].start_second
    match_end_second = periods[-1].end_second
    if any(
        current.end_second != following.start_second
        for current, following in zip(periods, periods[1:])
    ):
        raise ValueError("Played periods must form a continuous match clock.")

    event_rows = list(
        events
        if events is not None
        else ProviderMatchEvent.objects.filter(provider_match=locked_match).order_by(
            "event_index"
        )
    )
    reconstruction = reconstruct_player_intervals(
        lineup_players=normalized_lineup,
        events=event_rows,
        match_start_second=match_start_second,
        match_end_second=match_end_second,
        valid_team_ids=(
            locked_match.home_provider_team_id,
            locked_match.away_provider_team_id,
        ),
    )

    ProviderMatchPlayerParticipationBuild.objects.filter(
        provider_match=locked_match
    ).delete()
    try:
        payload = locked_match.payload
    except ProviderMatchPayload.DoesNotExist:
        payload = None
    clock_version = "+".join(sorted({period.calculation_version for period in periods}))
    build = ProviderMatchPlayerParticipationBuild.objects.create(
        provider_match=locked_match,
        status=reconstruction.status,
        formula_version=PARTICIPATION_FORMULA_VERSION,
        source_payload_sha256=getattr(payload, "payload_sha256", ""),
        match_clock_version=clock_version,
        team_episode_version="",
        participant_count=len(reconstruction.participants),
        verified_participant_count=sum(
            item.status == "verified" for item in reconstruction.participants
        ),
        excluded_participant_count=sum(
            item.status == "excluded" for item in reconstruction.participants
        ),
        unused_player_count=sum(
            item.status == "unused" for item in reconstruction.participants
        ),
        interval_count=sum(len(item.intervals) for item in reconstruction.participants),
        verified_seconds=sum(
            item.on_pitch_seconds
            for item in reconstruction.participants
            if item.status == "verified"
        ),
        diagnostics=reconstruction.diagnostics,
        calculated_at=calculated_at or timezone.now(),
    )

    player_map, team_map = canonical_identity_maps(
        locked_match,
        provider_player_ids=(
            item.provider_player_id for item in reconstruction.participants
        ),
        provider_team_ids=(
            item.provider_team_id for item in reconstruction.participants
        ),
    )
    stored_participants = []
    for draft in reconstruction.participants:
        participant = ProviderMatchPlayerParticipation.objects.create(
            build=build,
            provider_match=locked_match,
            provider_team_id=draft.provider_team_id,
            team_id=team_map.get(draft.provider_team_id),
            provider_player_id=draft.provider_player_id,
            player_id=player_map.get(draft.provider_player_id),
            roster_role=draft.roster_role,
            position_role=draft.position_role,
            status=draft.status,
            confidence=draft.confidence,
            exclusion_reason=draft.exclusion_reason,
            on_pitch_seconds=draft.on_pitch_seconds,
            excluded_seconds=0,
            interval_count=len(draft.intervals),
            diagnostics={"events": draft.diagnostics},
        )
        stored_participants.append((participant, draft))

    interval_rows = []
    for participant, draft in stored_participants:
        interval_rows.extend(
            ProviderMatchPlayerInterval(
                participation=participant,
                sequence=sequence,
                start_second=item.start_second,
                end_second=item.end_second,
                duration_seconds=item.duration_seconds,
                start_evidence=item.start_evidence,
                end_evidence=item.end_evidence,
                start_event_index=item.start_event_index,
                end_event_index=item.end_event_index,
                start_event_sequence_id=item.start_event_sequence_id,
                end_event_sequence_id=item.end_event_sequence_id,
                confidence=(
                    item.confidence if draft.status == "verified" else "unverified"
                ),
                exclusion_reason=item.exclusion_reason or draft.exclusion_reason,
            )
            for sequence, item in enumerate(draft.intervals)
        )
    if interval_rows:
        ProviderMatchPlayerInterval.objects.bulk_create(interval_rows, batch_size=1000)
    rebuild_match_player_state_exposure(locked_match)
    return build


def rebuild_match_player_state_exposure(provider_match) -> int:
    """Replace eligible player/episode intersections for one locked match."""
    ProviderMatchPlayerStateExposure.objects.filter(
        player_interval__participation__provider_match=provider_match
    ).delete()
    intervals = list(
        ProviderMatchPlayerInterval.objects.filter(
            participation__provider_match=provider_match,
            participation__status="verified",
            participation__team__isnull=False,
            participation__player__isnull=False,
            confidence="verified",
        ).select_related("participation")
    )
    episodes_by_team: dict[int, list[Any]] = defaultdict(list)
    episodes = list(
        ProviderMatchTeamGameStateEpisode.objects.filter(
            provider_match=provider_match
        ).order_by(
            "focal_team_id", "episode_index"
        )
    )
    for episode in episodes:
        episodes_by_team[episode.focal_team_id].append(episode)

    versions = sorted({episode.calculation_version for episode in episodes})
    ProviderMatchPlayerParticipationBuild.objects.filter(
        provider_match=provider_match
    ).update(
        team_episode_version="+".join(versions)
    )
    rows = []
    for interval in intervals:
        for episode in episodes_by_team.get(interval.participation.team_id, []):
            start_second = max(interval.start_second, episode.start_second)
            end_second = min(interval.end_second, episode.end_second)
            if end_second <= start_second:
                continue
            for (
                segment_start,
                segment_end,
                age_start,
                age_end,
                age_bucket,
            ) in split_exposure_by_state_age(
                start_second=start_second,
                end_second=end_second,
                episode_start_second=episode.start_second,
                episode_state_age_at_start=episode.state_age_seconds_at_start,
            ):
                rows.append(
                    ProviderMatchPlayerStateExposure(
                        player_interval=interval,
                        team_episode=episode,
                        start_second=segment_start,
                        end_second=segment_end,
                        duration_seconds=segment_end - segment_start,
                        coarse_state=episode.state,
                        goal_difference=episode.goal_difference,
                        phase=episode.phase,
                        provenance=episode.draw_provenance,
                        state_age_bucket=age_bucket,
                        state_age_start_seconds=age_start,
                        state_age_end_seconds=age_end,
                        formula_version=PLAYER_STATE_EXPOSURE_FORMULA_VERSION,
                    )
                )
    if rows:
        ProviderMatchPlayerStateExposure.objects.bulk_create(rows, batch_size=1000)
    return len(rows)
