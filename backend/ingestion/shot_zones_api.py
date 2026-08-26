from __future__ import annotations

from collections import defaultdict

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.api_cache import (
    get_or_build_payload_response,
    joined_version,
    model_version,
    stable_cache_key,
)
from ingestion.models import (
    MatchEventShotOutcome,
    MatchEventType,
    PlayerSeasonEventProfile,
    PlayerSeasonGkDerivedStats,
    Provider,
    ProviderMatch,
    ProviderMatchGameState,
    ProviderMatchPlayerStateExposure,
    ProviderMatchStatus,
)
from ingestion.event_profile_api import (
    PlayerEventProfileMixin,
    event_queryset,
    parse_optional_match,
    player_event_queryset,
    public_coordinate,
    resolve_event_profile_competition_season,
    scope_queryset_to_match,
)
from ingestion.services.shot_zones import (
    ShotPlacement,
    grid_metadata,
    keeper_variant,
    shooter_variant,
    split_variants,
)
from ingestion.services.player_state_comparison import (
    event_in_segments,
    exposure_segments,
    player_state_lens_metadata,
    scope_player_events,
)
from ingestion.state_lens import parse_state_lens

ZONES_API_VERSION = "v3"

# WhoScored source event-type ids for substitutions (Opta type dictionary).
SUBSTITUTION_OFF_SOURCE_ID = 18
SUBSTITUTION_ON_SOURCE_ID = 19

# Outcomes attributable to a goalkeeper's shot-facing record.
KEEPER_FACED_OUTCOMES = (
    MatchEventShotOutcome.GOAL,
    MatchEventShotOutcome.SAVED,
)

# Penalty shootouts are never part of shot-zone views.
IN_MATCH_PERIODS = (1, 2, 3, 4)


def shot_placement(event) -> ShotPlacement:
    return ShotPlacement(
        outcome=event.shot_outcome,
        situation=event.shot_situation,
        goal_mouth_y=public_coordinate(event.goal_mouth_y),
        goal_mouth_z=public_coordinate(event.goal_mouth_z),
    )


def zone_payload_base(competition_season, canonical_player_id: int) -> dict:
    return {
        "canonical_player_id": canonical_player_id,
        "competition_season": competition_season.id,
        "competition_code": competition_season.competition.short_code,
        "season_label": competition_season.season.label,
        "grid": grid_metadata(),
    }


class PlayerShotZonesApi(PlayerEventProfileMixin, APIView):
    """Goal-mouth shooting zones for one player season."""

    def get(self, request, canonical_player_id: int):
        try:
            profile = self.resolve_profile(request, canonical_player_id)
            match_ref = parse_optional_match(request)
            state_lens = parse_state_lens(request)
            cache_key = stable_cache_key(
                f"event-profile:{profile.competition_season_id}:player-shot-zones",
                {
                    "endpoint": "player-shot-zones",
                    "player": canonical_player_id,
                    "competition": profile.competition_season.competition.short_code,
                    "season": profile.competition_season.season.label,
                    "team": profile.team_id,
                    "match": match_ref,
                    "state_lens": state_lens.cache_scope(),
                    "formula_version": profile.formula_version,
                    "materialization_run": profile.materialized_ingestion_run_id,
                    "profile_version": profile.id,
                },
            )
            response, _ = get_or_build_payload_response(
                cache_key=cache_key,
                source_version=joined_version(
                    zones_source_version(profile.competition_season),
                    state_lens.source_token(),
                    model_version(
                        ProviderMatchGameState,
                        {"provider_match__competition_season": profile.competition_season_id},
                    ),
                    model_version(
                        ProviderMatchPlayerStateExposure,
                        {
                            "player_interval__participation__provider_match__competition_season": profile.competition_season_id,
                            "player_interval__participation__player_id": profile.player_id,
                        },
                    ),
                ),
                builder=lambda: self.build_payload(profile, match_ref, state_lens),
            )
            return response
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PlayerSeasonEventProfile.DoesNotExist:
            return Response(
                {"detail": "Public player event profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def build_payload(self, profile, match_ref: int | None, state_lens=None) -> dict:
        # Scope with the full event universe so match references align with
        # the main event-profile endpoint's match list; shots-only universes
        # silently shift every reference after a shotless match.
        scoped_events, matches, _references = scope_queryset_to_match(
            player_event_queryset(profile), match_ref
        )
        match_ids = list(scoped_events.values_list("provider_match_id", flat=True).distinct())
        if state_lens is not None and not state_lens.selected.is_default:
            scoped_events = scope_player_events(
                scoped_events, profile, state_lens.selected, match_ids
            )
        placements = [
            shot_placement(event)
            for event in scoped_events.filter(
                event_type=MatchEventType.SHOT,
                period__in=IN_MATCH_PERIODS,
            )
        ]
        payload = zone_payload_base(profile.competition_season, profile.player_id)
        payload.update(
            {
                "canonical_team_id": profile.team_id,
                "canonical_team_name": profile.team.name if profile.team else None,
                "shot_count": len(placements),
                "variants": split_variants(placements, shooter_variant),
                "matches": matches,
                "selected_match_ref": match_ref,
            }
        )
        if state_lens is not None:
            payload["state_lens"] = player_state_lens_metadata(profile, match_ids, state_lens)
        return payload


def zones_source_version(competition_season) -> str:
    return joined_version(
        "shot-zones",
        ZONES_API_VERSION,
        competition_season.id,
    )


def keeper_team_ids(competition_season, canonical_player_id: int) -> list[int]:
    """Canonical teams whose goal this player kept in the season."""
    rows = (
        event_queryset(competition_season)
        .filter(event_type=MatchEventType.SAVE, player_id=canonical_player_id)
        .values_list("team_id", flat=True)
        .distinct()
    )
    return [team_id for team_id in rows if team_id is not None]


def keeper_match_attribution(
    competition_season,
    canonical_player_id: int,
) -> tuple[list[int], list[int]]:
    """Split the keeper's team matches into certain vs uncertain attribution.

    A match counts only when exactly one goalkeeper is verifiable: the player
    recorded keeper events in it, no teammate did, and the player was never
    substituted off. Everything else is excluded outright rather than risk
    misattributed shots faced.
    """
    team_ids = keeper_team_ids(competition_season, canonical_player_id)
    if not team_ids:
        return [], []
    base_queryset = event_queryset(competition_season)
    keeper_events = list(
        base_queryset.filter(event_type=MatchEventType.SAVE, team_id__in=team_ids)
    )
    events_by_match: dict[int, list] = defaultdict(list)
    for event in keeper_events:
        events_by_match[event.provider_match_id].append(event)

    substitution_rows = base_queryset.filter(
        event_type=MatchEventType.SUBSTITUTION,
        source_event_type_id__in=(SUBSTITUTION_OFF_SOURCE_ID, SUBSTITUTION_ON_SOURCE_ID),
        team_id__in=team_ids,
    ).values_list(
        "provider_match_id", "source_event_type_id", "provider_player_id", "player_id"
    )
    substitutions_off_by_match: dict[int, set[int]] = defaultdict(set)
    for match_id, source_id, _provider_player_id, player_id in substitution_rows:
        if source_id == SUBSTITUTION_OFF_SOURCE_ID and player_id is not None:
            substitutions_off_by_match[match_id].add(player_id)

    provider_matches = sorted(
        ProviderMatch.objects.filter(
            competition_season=competition_season,
            provider=Provider.WHOSCORED,
            status=ProviderMatchStatus.COMPLETED,
        ).filter(
            Q(home_team_id__in=team_ids) | Q(away_team_id__in=team_ids)
        ),
        key=lambda match: match.id,
    )
    included: list[int] = []
    excluded: list[int] = []
    for provider_match in provider_matches:
        match_team_id = next(
            (
                team_id
                for team_id in team_ids
                if team_id in (provider_match.home_team_id, provider_match.away_team_id)
            ),
            None,
        )
        events = [
            event
            for event in events_by_match.get(provider_match.id, [])
            if event.team_id == match_team_id
        ]
        player_kept = any(event.player_id == canonical_player_id for event in events)
        teammate_kept = any(event.player_id != canonical_player_id for event in events)
        subbed_off = (
            canonical_player_id in substitutions_off_by_match.get(provider_match.id, set())
        )
        if player_kept and not teammate_kept and not subbed_off:
            included.append(provider_match.id)
        else:
            excluded.append(provider_match.id)
    return included, excluded


class PlayerGkShotZonesApi(APIView):
    """Goal-mouth zones where this goalkeeper was tested, with save rates."""

    def get(self, request, canonical_player_id: int):
        try:
            competition_season = resolve_event_profile_competition_season(request)
            if not PlayerSeasonGkDerivedStats.objects.filter(
                competition_season=competition_season,
                canonical_player_id=canonical_player_id,
                is_current=True,
            ).exists():
                raise PlayerSeasonGkDerivedStats.DoesNotExist
            match_ref = parse_optional_match(request)
            state_lens = parse_state_lens(request)
            cache_key = stable_cache_key(
                f"event-profile:{competition_season.id}:player-gk-shot-zones",
                {
                    "endpoint": "player-gk-shot-zones",
                    "player": canonical_player_id,
                    "competition": competition_season.competition.short_code,
                    "season": competition_season.season.label,
                    "match": match_ref,
                    "state_lens": state_lens.cache_scope(),
                },
            )
            response, _ = get_or_build_payload_response(
                cache_key=cache_key,
                source_version=joined_version(
                    zones_source_version(competition_season),
                    state_lens.source_token(),
                    model_version(
                        ProviderMatchGameState,
                        {"provider_match__competition_season": competition_season.id},
                    ),
                    model_version(
                        ProviderMatchPlayerStateExposure,
                        {
                            "player_interval__participation__provider_match__competition_season": competition_season.id,
                            "player_interval__participation__player_id": canonical_player_id,
                        },
                    ),
                ),
                builder=lambda: self.build_payload(
                    competition_season, canonical_player_id, match_ref, state_lens
                ),
            )
            return response
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PlayerSeasonGkDerivedStats.DoesNotExist:
            return Response(
                {"detail": "Goalkeeper event profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def build_payload(
        self,
        competition_season,
        canonical_player_id: int,
        match_ref: int | None,
        state_lens=None,
    ) -> dict:
        included_matches, excluded_matches = keeper_match_attribution(
            competition_season, canonical_player_id
        )
        # Match references must align with the main event-profile universe
        # (all of this player's matches), not just keeper-included ones.
        player_event_ids = event_queryset(competition_season).filter(
            player_id=canonical_player_id,
        )
        _scoped_queryset, all_matches, references = scope_queryset_to_match(
            player_event_ids, None
        )
        included_set = set(included_matches)
        selected_match_ids = sorted(included_set)
        selected_match_included = True
        if match_ref is not None:
            ref_match_ids = [
                match_id
                for match_id, reference in references.items()
                if reference == match_ref
            ]
            selected_match_ids = sorted(included_set & set(ref_match_ids))
            selected_match_included = bool(selected_match_ids)
        shots_faced = []
        if selected_match_ids:
            shots_faced = list(
                event_queryset(competition_season)
                .filter(
                    provider_match_id__in=selected_match_ids,
                    event_type=MatchEventType.SHOT,
                    shot_outcome__in=[outcome.value for outcome in KEEPER_FACED_OUTCOMES],
                    period__in=IN_MATCH_PERIODS,
                )
                .exclude(player_id=canonical_player_id)
            )
        profile = PlayerSeasonEventProfile.objects.filter(
            competition_season=competition_season,
            player_id=canonical_player_id,
            is_current=True,
            team__isnull=True,
        ).first()
        state_match_ids = selected_match_ids if match_ref is not None else list(references)
        state_metadata = None
        if state_lens is not None and not state_lens.selected.is_default:
            if profile is None:
                # A goalkeeper shot-facing record must never fall back to an
                # unverified shot list when the State Lens is active.
                shots_faced = []
            else:
                state_metadata = player_state_lens_metadata(
                    profile,
                    state_match_ids,
                    state_lens,
                )
                segments = exposure_segments(profile, state_lens.selected, state_match_ids)
                shots_faced = [
                    event for event in shots_faced
                    if event_in_segments(event, segments)
                ]
        elif state_lens is not None and profile is not None:
            state_metadata = player_state_lens_metadata(
                profile,
                state_match_ids,
                state_lens,
            )
        placements = [shot_placement(event) for event in shots_faced]
        payload = zone_payload_base(competition_season, canonical_player_id)
        payload.update(
            {
                "matches_included": len(included_matches),
                "matches_excluded": len(excluded_matches),
                "attribution_note": (
                    "Only matches with one verifiable goalkeeper are included; "
                    "blocked and off-target shots never faced the keeper."
                ),
                "selected_match_included": selected_match_included,
                "shots_faced": len(placements),
                "variants": split_variants(placements, keeper_variant),
                "matches": all_matches,
                "selected_match_ref": match_ref,
            }
        )
        if state_metadata is not None:
            payload["state_lens"] = state_metadata
        return payload
