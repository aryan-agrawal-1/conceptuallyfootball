"""Verified player exposure and event/carry scoping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ingestion.models import (
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchPlayerParticipation,
    ProviderMatchPlayerStateExposure,
)
from ingestion.state_lens import STATE_VALUES, StateLensScope


@dataclass(frozen=True, slots=True)
class PlayerExposureSegment:
    match_id: int
    team_id: int | None
    start_second: int
    end_second: int
    episode_index: int

    @property
    def duration_seconds(self) -> int:
        return max(0, self.end_second - self.start_second)


def scope_age_bounds(
    row: ProviderMatchPlayerStateExposure,
    scope: StateLensScope,
) -> tuple[int, int] | None:
    """Return the intersection of an exposure row and a State Lens scope."""

    state = STATE_VALUES.get(scope.state)
    if state is not None and row.coarse_state != state:
        return None
    if scope.goal_difference is not None and row.goal_difference != scope.goal_difference:
        return None
    if scope.phase is not None and row.phase != scope.phase:
        return None
    if scope.draw_provenance is not None and row.provenance != scope.draw_provenance:
        return None
    start = row.start_second
    end = row.end_second
    entry = row.team_episode.state_entry_second
    if scope.minimum_state_age_seconds is not None:
        start = max(start, entry + scope.minimum_state_age_seconds)
    if scope.maximum_state_age_seconds is not None:
        end = min(end, entry + scope.maximum_state_age_seconds)
    if end <= start:
        return None
    return start, end


def participation_queryset(profile, match_ids: Iterable[int] | None = None):
    queryset = ProviderMatchPlayerParticipation.objects.filter(
        provider_match__competition_season=profile.competition_season,
        player_id=profile.player_id,
    ).select_related("provider_match", "team")
    if profile.team_id is not None:
        queryset = queryset.filter(team_id=profile.team_id)
    if match_ids is not None:
        queryset = queryset.filter(provider_match_id__in=list(match_ids))
    return queryset


def exposure_queryset(profile, match_ids: Iterable[int] | None = None):
    queryset = ProviderMatchPlayerStateExposure.objects.filter(
        player_interval__participation__provider_match__competition_season=profile.competition_season,
        player_interval__participation__player_id=profile.player_id,
        player_interval__participation__status="verified",
        player_interval__participation__confidence="verified",
        player_interval__confidence="verified",
    ).select_related(
        "player_interval__participation",
        "player_interval__participation__team",
        "team_episode",
    )
    if profile.team_id is not None:
        queryset = queryset.filter(player_interval__participation__team_id=profile.team_id)
    if match_ids is not None:
        queryset = queryset.filter(
            player_interval__participation__provider_match_id__in=list(match_ids)
        )
    return queryset.order_by(
        "player_interval__participation__provider_match_id",
        "start_second",
        "end_second",
        "id",
    )


def exposure_segments(
    profile,
    scope: StateLensScope,
    match_ids: Iterable[int] | None = None,
) -> list[PlayerExposureSegment]:
    segments: list[PlayerExposureSegment] = []
    for row in exposure_queryset(profile, match_ids):
        bounds = scope_age_bounds(row, scope)
        if bounds is None:
            continue
        participation = row.player_interval.participation
        segments.append(
            PlayerExposureSegment(
                match_id=participation.provider_match_id,
                team_id=participation.team_id,
                start_second=bounds[0],
                end_second=bounds[1],
                episode_index=row.team_episode.episode_index,
            )
        )
    return segments


def event_second(event) -> int | None:
    # Never fall back to the provider match clock: an unverifiable canonical
    # timeline must remain outside the State Lens denominator.
    return event.timeline_seconds


ANY_TEAM = object()


def value_in_segments(
    value,
    match_id: int,
    segments: Iterable[PlayerExposureSegment],
    team_id: int | None | object = ANY_TEAM,
) -> bool:
    """Check a timestamp against verified half-open player segments."""

    if value is None:
        return False
    return any(
        segment.match_id == match_id
        and (team_id is ANY_TEAM or segment.team_id == team_id)
        and segment.start_second <= value < segment.end_second
        for segment in segments
    )


def event_in_segments(
    event,
    segments: Iterable[PlayerExposureSegment],
    team_id: int | None | object = ANY_TEAM,
) -> bool:
    return value_in_segments(
        event_second(event),
        event.provider_match_id,
        segments,
        team_id,
    )


def carry_in_segments(
    carry,
    segments: Iterable[PlayerExposureSegment],
    team_id: int | None | object = ANY_TEAM,
) -> bool:
    # Carries retain the canonical clock of their normalized source events.
    return value_in_segments(
        carry.match_seconds,
        carry.provider_match_id,
        segments,
        team_id,
    )


def verified_event_ids(
    queryset,
    profile,
    scope: StateLensScope,
    match_ids: Iterable[int] | None = None,
) -> list[int]:
    segments = exposure_segments(profile, scope, match_ids)
    if not segments:
        return []
    return [
        event.id
        for event in queryset
        if event_in_segments(event, segments, event.team_id)
    ]


def scope_player_events(
    queryset,
    profile,
    scope: StateLensScope,
    match_ids: Iterable[int] | None = None,
):
    """Return only player events supported by verified exposure."""

    ids = verified_event_ids(queryset, profile, scope, match_ids)
    return queryset.filter(pk__in=ids) if ids else queryset.none()


def player_event_scope_segments(
    profile,
    scope: StateLensScope,
    match_ids: Iterable[int] | None = None,
):
    return exposure_segments(profile, scope, match_ids)


def scope_player_carries(
    carries: Iterable,
    profile,
    scope: StateLensScope,
    match_ids: Iterable[int] | None = None,
) -> list:
    segments = exposure_segments(profile, scope, match_ids)
    return [
        carry
        for carry in carries
        if carry_in_segments(carry, segments, carry.team_id)
    ]


def scope_match_ids(
    profile,
    match_ref: int | None = None,
) -> tuple[list[int], dict[int, int]]:
    """Resolve match references from the player's full event universe."""

    match_ids = list(
        ProviderMatchEvent.objects.filter(
            provider_match__competition_season=profile.competition_season,
            player_id=profile.player_id,
            **({"team_id": profile.team_id} if profile.team_id is not None else {}),
        )
        .values_list("provider_match_id", flat=True)
        .distinct()
    )
    matches = list(
        ProviderMatch.objects.filter(pk__in=match_ids).order_by("kickoff_at", "id")
    )
    references = {match.id: index for index, match in enumerate(matches)}
    selected = [
        match.id
        for match in matches
        if match_ref is None or references[match.id] == match_ref
    ]
    return selected, references
