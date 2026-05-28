from __future__ import annotations

import time
from typing import Any

from django.conf import settings

from ingestion.services.sofascore_client import SofascoreSeasonConfig, _request_get


def _num(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _flt(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_season_teams(
    config: SofascoreSeasonConfig,
    timeout: int = 45,
) -> list[dict[str, Any]]:
    url = (
        f"https://www.sofascore.com/api/v1/unique-tournament/"
        f"{config.unique_tournament_id}/season/{config.season_id}/teams"
    )
    resp = _request_get(url, params={}, timeout=timeout)
    resp.raise_for_status()
    return (resp.json().get("teams") or [])


def fetch_total_standings(
    config: SofascoreSeasonConfig,
    timeout: int = 45,
) -> list[dict[str, Any]]:
    url = (
        f"https://www.sofascore.com/api/v1/unique-tournament/"
        f"{config.unique_tournament_id}/season/{config.season_id}/standings/total"
    )
    resp = _request_get(url, params={}, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    standings = payload.get("standings") or []
    if not standings:
        return []
    return standings[0].get("rows") or []


def fetch_team_overall_statistics(
    config: SofascoreSeasonConfig,
    team_id: int,
    timeout: int = 45,
) -> dict[str, Any]:
    url = (
        f"https://www.sofascore.com/api/v1/team/{team_id}/unique-tournament/"
        f"{config.unique_tournament_id}/season/{config.season_id}/statistics/overall"
    )
    resp = _request_get(url, params={}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def fetch_team_players(
    team_id: int | str,
    timeout: int = 45,
) -> list[dict[str, Any]]:
    url = f"https://www.sofascore.com/api/v1/team/{team_id}/players"
    resp = _request_get(url, params={}, timeout=timeout)
    resp.raise_for_status()
    return resp.json().get("players") or []


def build_team_season_rows(
    config: SofascoreSeasonConfig,
    *,
    delay_seconds: float | None = None,
) -> list[dict[str, Any]]:
    if delay_seconds is None:
        delay_seconds = float(
            getattr(settings, "STATBALLER_SOFASCORE_REQUEST_DELAY_SECONDS", 1.5)
        )
    teams = fetch_season_teams(config)
    standings_rows = fetch_total_standings(config)
    standings_by_team_id = {
        int((row.get("team") or {}).get("id")): row
        for row in standings_rows
        if (row.get("team") or {}).get("id") is not None
    }

    rows: list[dict[str, Any]] = []
    for team in teams:
        team_id = int(team["id"])
        standings_row = standings_by_team_id.get(team_id) or {}
        overall_payload: dict[str, Any] = {}
        try:
            overall_payload = fetch_team_overall_statistics(config, team_id)
        except Exception:  # noqa: BLE001
            overall_payload = {}
        rows.append(normalize_team_season_row(team, standings_row, overall_payload))
        time.sleep(delay_seconds)
    return rows


def normalize_team_season_row(
    team: dict[str, Any],
    standings_row: dict[str, Any] | None,
    overall_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    standings_row = standings_row or {}
    overall_stats = (overall_payload or {}).get("statistics") or {}

    def s(key: str) -> Any:
        return overall_stats.get(key)

    goal_diff = _num(standings_row.get("scoreDiffFormatted"))
    if goal_diff is None:
        scores_for = _num(standings_row.get("scoresFor"))
        scores_against = _num(standings_row.get("scoresAgainst"))
        if scores_for is not None and scores_against is not None:
            goal_diff = scores_for - scores_against

    return {
        "provider_team_id": str(team.get("id") or ""),
        "team_name": team.get("name") or "",
        "standings_row_json": standings_row,
        "overall_stats_json": overall_stats,
        "has_overall_stats": bool(overall_stats),
        "matches": _num(standings_row.get("matches")),
        "rank": _num(standings_row.get("position")),
        "points": _num(standings_row.get("points")),
        "wins": _num(standings_row.get("wins")),
        "draws": _num(standings_row.get("draws")),
        "losses": _num(standings_row.get("losses")),
        "goals_for": _num(standings_row.get("scoresFor")),
        "goals_against": _num(standings_row.get("scoresAgainst")),
        "goal_difference": goal_diff,
        "assists": _num(s("assists")),
        "average_ball_possession": _flt(s("averageBallPossession")),
        "clean_sheets": _num(s("cleanSheets")),
        "own_goals": _num(s("ownGoals")),
        "shots": _num(s("shots")),
        "shots_on_target": _num(s("shotsOnTarget")),
        "shots_off_target": _num(s("shotsOffTarget")),
        "shots_against": _num(s("shotsAgainst")),
        "shots_on_target_against": _num(s("shotsOnTargetAgainst")),
        "shots_from_inside_the_box": _num(s("shotsFromInsideTheBox")),
        "shots_from_inside_the_box_against": _num(s("shotsFromInsideTheBoxAgainst")),
        "shots_from_outside_the_box": _num(s("shotsFromOutsideTheBox")),
        "shots_from_outside_the_box_against": _num(s("shotsFromOutsideTheBoxAgainst")),
        "big_chances": _num(s("bigChances")),
        "big_chances_against": _num(s("bigChancesAgainst")),
        "big_chances_created": _num(s("bigChancesCreated")),
        "big_chances_created_against": _num(s("bigChancesCreatedAgainst")),
        "big_chances_missed": _num(s("bigChancesMissed")),
        "corners": _num(s("corners")),
        "corners_against": _num(s("cornersAgainst")),
        "accurate_passes": _num(s("accuratePasses")),
        "accurate_passes_against": _num(s("accuratePassesAgainst")),
        "total_passes": _num(s("totalPasses")),
        "accurate_passes_percentage": _flt(s("accuratePassesPercentage")),
        "accurate_long_balls": _num(s("accurateLongBalls")),
        "total_long_balls": _num(s("totalLongBalls")),
        "accurate_long_balls_percentage": _flt(s("accurateLongBallsPercentage")),
        "accurate_crosses": _num(s("accurateCrosses")),
        "total_crosses": _num(s("totalCrosses")),
        "accurate_crosses_percentage": _flt(s("accurateCrossesPercentage")),
        "ball_recovery": _num(s("ballRecovery")),
        "possession_lost": _num(s("possessionLost")),
        "tackles": _num(s("tackles")),
        "tackles_against": _num(s("tacklesAgainst")),
        "interceptions": _num(s("interceptions")),
        "interceptions_against": _num(s("interceptionsAgainst")),
        "clearances": _num(s("clearances")),
        "clearances_against": _num(s("clearancesAgainst")),
        "saves": _num(s("saves")),
        "duels_won": _num(s("duelsWon")),
        "duels_won_percentage": _flt(s("duelsWonPercentage")),
        "aerial_duels_won": _num(s("aerialDuelsWon")),
        "aerial_duels_won_percentage": _flt(s("aerialDuelsWonPercentage")),
        "ground_duels_won": _num(s("groundDuelsWon")),
        "ground_duels_won_percentage": _flt(s("groundDuelsWonPercentage")),
        "successful_dribbles": _num(s("successfulDribbles")),
        "fouls": _num(s("fouls")),
        "yellow_cards": _num(s("yellowCards")),
        "red_cards": _num(s("redCards")),
        "yellow_cards_against": _num(s("yellowCardsAgainst")),
        "red_cards_against": _num(s("redCardsAgainst")),
        "offsides": _num(s("offsides")),
        "offsides_against": _num(s("offsidesAgainst")),
        "penalties_taken": _num(s("penaltiesTaken")),
        "penalty_goals": _num(s("penaltyGoals")),
        "penalty_goals_conceded": _num(s("penaltyGoalsConceded")),
        "goals_from_inside_the_box": _num(s("goalsFromInsideTheBox")),
        "goals_from_outside_the_box": _num(s("goalsFromOutsideTheBox")),
        "headed_goals": _num(s("headedGoals")),
        "hit_woodwork": _num(s("hitWoodwork")),
        "expected_goals": _flt(s("expectedGoals")),
        "expected_assists": _flt(s("expectedAssists")),
        "awarded_matches": _num(s("awardedMatches")),
        "blocked_scoring_attempt": _num(s("blockedScoringAttempt")),
        "blocked_scoring_attempt_against": _num(s("blockedScoringAttemptAgainst")),
        "errors_leading_to_goal": _num(s("errorsLeadingToGoal")),
        "errors_leading_to_goal_against": _num(s("errorsLeadingToGoalAgainst")),
        "errors_leading_to_shot": _num(s("errorsLeadingToShot")),
        "errors_leading_to_shot_against": _num(s("errorsLeadingToShotAgainst")),
        "free_kicks": _num(s("freeKicks")),
        "goal_kicks": _num(s("goalKicks")),
        "throw_ins": _num(s("throwIns")),
    }
