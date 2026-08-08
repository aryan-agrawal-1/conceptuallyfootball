from __future__ import annotations

from ingestion.models import (
    EventProfileSplitType,
    PlayerSeasonEventProfile,
    TeamSeasonEventProfile,
)
from ingestion.services.event_profiles import event_profile_availability


def unavailable_event_profile_flag() -> dict:
    return {
        "available": False,
        "coverage": None,
        "formula_version": None,
        "materialization_run_id": None,
        "profile_version": None,
    }


def player_event_profile_flag(competition_season, canonical_player_id: int) -> dict:
    profile = (
        PlayerSeasonEventProfile.objects.filter(
            competition_season=competition_season,
            player_id=canonical_player_id,
            split_type=EventProfileSplitType.SEASON_TOTAL,
            team__isnull=True,
            is_current=True,
        )
        .select_related("materialized_ingestion_run")
        .first()
    )
    if profile is None:
        return unavailable_event_profile_flag()

    modules = event_profile_availability(
        profile.pass_attempts,
        profile.shots,
        profile.valid_location_actions,
    )
    available = any(module["available"] for module in modules.values())
    run_coverage = profile.materialized_ingestion_run.stats.get("coverage", {})
    return {
        "available": available,
        "coverage": {
            "observed_matches": profile.observed_match_count,
            "competition_complete": bool(run_coverage.get("complete", False)),
        },
        "formula_version": profile.formula_version,
        "materialization_run_id": profile.materialized_ingestion_run_id,
        "profile_version": profile.id,
    }


def team_event_profile_flag(competition_season, canonical_team_id: int) -> dict:
    profile = TeamSeasonEventProfile.objects.filter(
        competition_season=competition_season,
        team_id=canonical_team_id,
        is_current=True,
    ).first()
    if profile is None:
        return unavailable_event_profile_flag()
    return {
        "available": True,
        "coverage": {
            "observed_matches": profile.observed_match_count,
            "expected_matches": profile.expected_match_count,
            "ratio": profile.coverage,
        },
        "formula_version": profile.formula_version,
        "materialization_run_id": profile.materialized_ingestion_run_id,
        "profile_version": profile.id,
    }
