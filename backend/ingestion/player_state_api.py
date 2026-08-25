"""Public-safe player game-state exposure API."""

from __future__ import annotations

from collections import Counter

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Sum
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.derived_api import _resolve_competition_season
from ingestion.models import (
    CanonicalPlayer,
    PlayerSeasonDerivedStats,
    PlayerSeasonGkDerivedStats,
    ProviderMatchPlayerParticipation,
    ProviderMatchPlayerStateExposure,
)
from ingestion.services.player_participation import (
    PARTICIPATION_FORMULA_VERSION,
    PLAYER_STATE_EXPOSURE_FORMULA_VERSION,
)


def optional_team_id(request) -> int | None:
    value = request.query_params.get("team")
    if value in (None, ""):
        return None
    try:
        team_id = int(value)
    except ValueError as error:
        raise DjangoValidationError("team must be a canonical team ID.") from error
    if team_id <= 0:
        raise DjangoValidationError("team must be a canonical team ID.")
    return team_id


def public_match(
    match, reference: int, participant, *, reason: str | None = None
) -> dict:
    value = {
        "match_ref": reference,
        "kickoff_at": match.kickoff_at.isoformat(),
        "home_team_id": match.home_team_id,
        "home_team_name": match.home_team.name if match.home_team else None,
        "away_team_id": match.away_team_id,
        "away_team_name": match.away_team.name if match.away_team else None,
        "subject_team_id": participant.team_id,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "confidence": participant.confidence,
    }
    if reason is not None:
        value["reason"] = reason
    return value


def player_has_public_season(competition_season, player_id: int) -> bool:
    filters = {
        "competition_season": competition_season,
        "canonical_player_id": player_id,
        "is_current": True,
    }
    return (
        PlayerSeasonDerivedStats.objects.filter(**filters).exists()
        or PlayerSeasonGkDerivedStats.objects.filter(**filters).exists()
    )


def build_player_state_exposure_payload(
    competition_season,
    canonical_player_id: int,
    *,
    team_id: int | None = None,
) -> dict:
    player = CanonicalPlayer.objects.get(pk=canonical_player_id)
    participations = ProviderMatchPlayerParticipation.objects.filter(
        provider_match__competition_season=competition_season,
        player_id=canonical_player_id,
    ).select_related(
        "build",
        "team",
        "provider_match__home_team",
        "provider_match__away_team",
    )
    if team_id is not None:
        participations = participations.filter(team_id=team_id)
    participation_rows = list(
        participations.order_by("provider_match__kickoff_at", "provider_match_id", "id")
    )
    if not participation_rows:
        raise ProviderMatchPlayerParticipation.DoesNotExist

    exposures = ProviderMatchPlayerStateExposure.objects.filter(
        player_interval__participation__in=participation_rows,
        player_interval__participation__status="verified",
        player_interval__confidence="verified",
    )
    totals_by_participation = dict(
        exposures.values_list("player_interval__participation_id").annotate(
            seconds=Sum("duration_seconds")
        )
    )

    matches = sorted(
        {
            row.provider_match_id: row.provider_match for row in participation_rows
        }.values(),
        key=lambda match: (match.kickoff_at, match.id),
    )
    references = {match.id: index for index, match in enumerate(matches)}
    included_matches: list[dict] = []
    excluded_matches: list[dict] = []
    unused_matches: list[dict] = []
    exclusion_reasons: Counter[str] = Counter()
    included_participation_ids: list[int] = []

    for participant in participation_rows:
        match = participant.provider_match
        match_ref = references[match.id]
        if participant.status == "unused":
            unused_matches.append(public_match(match, match_ref, participant))
            continue
        exposure_seconds = totals_by_participation.get(participant.id, 0) or 0
        if (
            participant.status == "verified"
            and participant.confidence == "verified"
            and exposure_seconds == participant.on_pitch_seconds
            and exposure_seconds > 0
        ):
            value = public_match(match, match_ref, participant)
            value["exposure_seconds"] = exposure_seconds
            included_matches.append(value)
            included_participation_ids.append(participant.id)
            continue
        reason = participant.exclusion_reason or (
            "state_episode_coverage_mismatch"
            if participant.status == "verified"
            else "participation_unverified"
        )
        exclusion_reasons[reason] += 1
        value = public_match(match, match_ref, participant, reason=reason)
        value["candidate_seconds"] = participant.on_pitch_seconds
        excluded_matches.append(value)

    public_exposures = exposures.filter(
        player_interval__participation_id__in=included_participation_ids
    )
    dimension_rows = list(
        public_exposures.values(
            "coarse_state",
            "goal_difference",
            "phase",
            "provenance",
            "state_age_bucket",
        )
        .annotate(exposure_seconds=Sum("duration_seconds"))
        .order_by(
            "phase",
            "coarse_state",
            "goal_difference",
            "provenance",
            "state_age_bucket",
        )
    )
    for row in dimension_rows:
        row["exposure_minutes"] = round(row["exposure_seconds"] / 60, 4)

    build_versions = sorted({row.build.formula_version for row in participation_rows})
    episode_versions = sorted(
        {
            row.build.team_episode_version
            for row in participation_rows
            if row.build.team_episode_version
        }
    )
    total_exposure_seconds = sum(row["exposure_seconds"] for row in dimension_rows)
    excluded_candidate_seconds = sum(
        row.get("candidate_seconds", 0) for row in excluded_matches
    )
    confidence = (
        "unavailable"
        if not included_matches
        else "partial" if excluded_matches else "verified"
    )
    return {
        "canonical_player_id": player.id,
        "canonical_player_name": player.display_name,
        "canonical_team_id": team_id,
        "competition_season": competition_season.id,
        "competition_code": competition_season.competition.short_code,
        "season_label": competition_season.season.label,
        "coverage": {
            "included_match_count": len(included_matches),
            "excluded_match_count": len(excluded_matches),
            "unused_roster_match_count": len(unused_matches),
            "included_matches": included_matches,
            "excluded_matches": excluded_matches,
            "unused_roster_matches": unused_matches,
            "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
            "exposure_seconds": total_exposure_seconds,
            "exposure_minutes": round(total_exposure_seconds / 60, 4),
            "excluded_candidate_seconds": excluded_candidate_seconds,
            "confidence": confidence,
        },
        "materialization": {
            "formula_version": PLAYER_STATE_EXPOSURE_FORMULA_VERSION,
            "participation_formula_version": PARTICIPATION_FORMULA_VERSION,
            "participation_versions": build_versions,
            "team_episode_versions": episode_versions,
        },
        "dimensions": dimension_rows,
    }


class PlayerStateExposureApi(APIView):
    def get(self, request, canonical_player_id: int):
        try:
            competition_season = _resolve_competition_season(request)
            team_id = optional_team_id(request)
            if not player_has_public_season(competition_season, canonical_player_id):
                raise ProviderMatchPlayerParticipation.DoesNotExist
            payload = build_player_state_exposure_payload(
                competition_season,
                canonical_player_id,
                team_id=team_id,
            )
            return Response(payload)
        except DjangoValidationError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except (
            ProviderMatchPlayerParticipation.DoesNotExist,
            CanonicalPlayer.DoesNotExist,
        ):
            return Response(
                {"detail": "Public player state exposure not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
