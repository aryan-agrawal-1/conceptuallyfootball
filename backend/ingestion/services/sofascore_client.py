from __future__ import annotations

"""
Sofascore HTTP client for season totals.

Verified 2026-04 against live JSON for:
  GET /api/v1/unique-tournament/17/season/61627/statistics
  (Premier League, historic season id 61627 — same schema as current seasons.)

Each `group` returns `results[]` rows shaped like:
  { <camelCase stat fields>, "player": {...}, "team": {...} }

Observed stat keys by group (non-player/team):
- summary: goals, expectedGoals, successfulDribbles, tackles, assists,
           accuratePassesPercentage, rating
  (minutesPlayed / appearances / games were NOT present on these samples;
   we still read them when the API includes them.)
- defence: tackles, interceptions, clearances, errorLeadToGoal, outfielderBlocks, rating
- passing: bigChancesCreated, assists, accuratePasses, accuratePassesPercentage,
            keyPasses, rating  (inaccuratePasses / totalPasses / accurateCrosses /
            accurateLongBalls appear on some players — read when present)
- goalkeeper: saves, cleanSheet, penaltySave, savedShotsFromInsideTheBox, runsOut, rating
- attack: goals, expectedGoals, bigChancesMissed, successfulDribbles, totalShots,
          goalConversionPercentage, rating  (stored in group_stats only; not merged
          into the Understat-owned attacking columns on MergedPlayerSeason.)
"""

import time
from dataclasses import dataclass
from typing import Any

try:
    from curl_cffi import requests as browser_requests
except Exception:  # noqa: BLE001
    browser_requests = None

import requests as plain_requests
from django.conf import settings

REQUEST_METRICS: dict[str, Any] = {
    "request_count": 0,
    "status_counts": {},
    "retry_count": 0,
    "blocked_count": 0,
    "proxy_enabled": False,
}
REQUEST_CAP: int | None = None


def set_request_cap(cap: int | None) -> None:
    global REQUEST_CAP
    REQUEST_CAP = cap


def reset_request_metrics() -> None:
    REQUEST_METRICS.clear()
    REQUEST_METRICS.update(
        {
            "request_count": 0,
            "status_counts": {},
            "retry_count": 0,
            "blocked_count": 0,
            "proxy_enabled": bool(_sofascore_proxy_url()),
        }
    )


def snapshot_request_metrics() -> dict[str, Any]:
    return {
        "request_count": int(REQUEST_METRICS.get("request_count") or 0),
        "status_counts": dict(REQUEST_METRICS.get("status_counts") or {}),
        "retry_count": int(REQUEST_METRICS.get("retry_count") or 0),
        "blocked_count": int(REQUEST_METRICS.get("blocked_count") or 0),
        "proxy_enabled": bool(REQUEST_METRICS.get("proxy_enabled")),
    }


@dataclass(frozen=True)
class SofascoreSeasonConfig:
    unique_tournament_id: int
    season_id: int


# Order matches production usage; attack is fetched for verbatim group_stats only.
STAT_GROUPS: tuple[str, ...] = (
    "summary",
    "defence",
    "passing",
    "goalkeeper",
    "attack",
)

# Mirrors ScraperFC's broad SofaScore league-stat projection.
WIDE_STAT_FIELDS: tuple[str, ...] = (
    "accurateChippedPasses",
    "accurateCrosses",
    "accurateCrossesPercentage",
    "accurateFinalThirdPasses",
    "accurateLongBalls",
    "accurateLongBallsPercentage",
    "accurateOppositionHalfPasses",
    "accurateOwnHalfPasses",
    "accuratePasses",
    "accuratePassesPercentage",
    "aerialDuelsWon",
    "aerialDuelsWonPercentage",
    "aerialLost",
    "appearances",
    "assists",
    "attemptPenaltyMiss",
    "attemptPenaltyPost",
    "attemptPenaltyTarget",
    "ballRecovery",
    "bigChancesCreated",
    "bigChancesMissed",
    "blockedShots",
    "cleanSheet",
    "clearances",
    "countRating",
    "crossesNotClaimed",
    "directRedCards",
    "dispossessed",
    "dribbledPast",
    "duelLost",
    "errorLeadToGoal",
    "errorLeadToShot",
    "expectedAssists",
    "expectedGoals",
    "fouls",
    "freeKickGoal",
    "goalConversionPercentage",
    "goalKicks",
    "goals",
    "goalsAssistsSum",
    "goalsConceded",
    "goalsConcededInsideTheBox",
    "goalsConcededOutsideTheBox",
    "goalsFromInsideTheBox",
    "goalsFromOutsideTheBox",
    "goalsPrevented",
    "groundDuelsWon",
    "groundDuelsWonPercentage",
    "headedGoals",
    "highClaims",
    "hitWoodwork",
    "inaccuratePasses",
    "interceptions",
    "keyPasses",
    "leftFootGoals",
    "matchesStarted",
    "minutesPlayed",
    "offsides",
    "outfielderBlocks",
    "ownGoals",
    "passToAssist",
    "penaltiesTaken",
    "penaltyConceded",
    "penaltyConversion",
    "penaltyFaced",
    "penaltyGoals",
    "penaltySave",
    "penaltyWon",
    "possessionLost",
    "possessionWonAttThird",
    "punches",
    "rating",
    "redCards",
    "rightFootGoals",
    "runsOut",
    "savedShotsFromInsideTheBox",
    "savedShotsFromOutsideTheBox",
    "saves",
    "savesCaught",
    "savesParried",
    "scoringFrequency",
    "setPieceConversion",
    "shotFromSetPiece",
    "shotsFromInsideTheBox",
    "shotsFromOutsideTheBox",
    "shotsOffTarget",
    "shotsOnTarget",
    "successfulDribbles",
    "successfulDribblesPercentage",
    "successfulRunsOut",
    "tackles",
    "tacklesWon",
    "tacklesWonPercentage",
    "totalAttemptAssist",
    "totalChippedPasses",
    "totalContest",
    "totalCross",
    "totalDuelsWon",
    "totalDuelsWonPercentage",
    "totalLongBalls",
    "totalOppositionHalfPasses",
    "totalOwnHalfPasses",
    "totalPasses",
    "totalRating",
    "totalShots",
    "totwAppearances",
    "touches",
    "wasFouled",
    "yellowCards",
    "yellowRedCards",
)


DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _sofascore_user_agent() -> str:
    configured = getattr(settings, "STATBALLER_HTTP_USER_AGENT", "")
    if configured and "StatballerIngestion" not in configured:
        return configured
    return DEFAULT_BROWSER_USER_AGENT


def _sofascore_proxy_url() -> str:
    return (
        getattr(settings, "STATBALLER_SOFASCORE_PROXY_URL", "")
        or getattr(settings, "STATBALLER_HTTP_PROXY_URL", "")
        or ""
    ).strip()


def sofascore_request_headers() -> dict[str, str]:
    return {
        "User-Agent": _sofascore_user_agent(),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.sofascore.com/",
        "Origin": "https://www.sofascore.com",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
    }


def _request_get(
    url: str,
    *,
    params: dict[str, Any],
    timeout: int,
):
    headers = sofascore_request_headers()
    proxy_url = _sofascore_proxy_url()
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    REQUEST_METRICS["proxy_enabled"] = bool(proxy_url)
    transient_statuses = {403, 429, 502, 503, 504}
    last_response = None
    retry_base_sleep_seconds = float(
        getattr(settings, "STATBALLER_SOFASCORE_RETRY_BASE_SLEEP_SECONDS", 8.0)
    )

    for attempt in range(4):
        if REQUEST_CAP is not None and int(REQUEST_METRICS.get("request_count") or 0) >= REQUEST_CAP:
            raise RuntimeError(f"Sofascore daily request cap reached ({REQUEST_CAP}).")
        if browser_requests is not None:
            kwargs = {
                "headers": headers,
                "params": params,
                "timeout": timeout,
                "impersonate": "chrome124",
            }
            if proxies:
                kwargs["proxies"] = proxies
            response = browser_requests.get(
                url,
                **kwargs,
            )
        else:
            response = plain_requests.get(
                url,
                headers=headers,
                params=params,
                timeout=timeout,
                proxies=proxies,
            )

        status_key = str(response.status_code)
        status_counts = REQUEST_METRICS.setdefault("status_counts", {})
        status_counts[status_key] = int(status_counts.get(status_key) or 0) + 1
        REQUEST_METRICS["request_count"] = int(REQUEST_METRICS.get("request_count") or 0) + 1
        if response.status_code in {403, 429}:
            REQUEST_METRICS["blocked_count"] = int(REQUEST_METRICS.get("blocked_count") or 0) + 1

        if response.status_code not in transient_statuses:
            return response

        last_response = response
        if attempt < 3:
            REQUEST_METRICS["retry_count"] = int(REQUEST_METRICS.get("retry_count") or 0) + 1
            time.sleep(retry_base_sleep_seconds * (attempt + 1))

    return last_response


def fetch_statistics_page(
    config: SofascoreSeasonConfig,
    group: str,
    offset: int,
    limit: int = 100,
    timeout: int = 45,
) -> dict[str, Any]:
    url = (
        f"https://www.sofascore.com/api/v1/unique-tournament/"
        f"{config.unique_tournament_id}/season/{config.season_id}/statistics"
    )
    params = {
        "limit": limit,
        "order": "-rating",
        "offset": offset,
        "accumulation": "total",
        "group": group,
    }
    resp = _request_get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def fetch_wide_statistics_page(
    config: SofascoreSeasonConfig,
    offset: int,
    limit: int = 100,
    timeout: int = 45,
) -> dict[str, Any]:
    url = (
        f"https://www.sofascore.com/api/v1/unique-tournament/"
        f"{config.unique_tournament_id}/season/{config.season_id}/statistics"
    )
    params = {
        "limit": limit,
        "offset": offset,
        "accumulation": "total",
        "fields": ",".join(WIDE_STAT_FIELDS),
        "filters": "position.in.G~D~M~F",
    }
    resp = _request_get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def fetch_player_profile(player_id: str | int, timeout: int = 20) -> dict[str, Any]:
    url = f"https://www.sofascore.com/api/v1/player/{player_id}"
    resp = _request_get(url, params={}, timeout=timeout)
    resp.raise_for_status()
    return resp.json().get("player") or {}


def merge_player_stat_dicts(target: dict[int, dict[str, Any]], group: str, page_rows: list[dict]) -> None:
    for row in page_rows:
        player = row.get("player") or {}
        pid = player.get("id")
        if pid is None:
            continue
        bucket = target.setdefault(int(pid), {})
        bucket.setdefault("_player", player)
        team = row.get("team") or {}
        if team:
            bucket.setdefault("_team", team)
        for k, v in row.items():
            if k in ("player", "team"):
                continue
            bucket[f"{group}:{k}"] = v


def merge_player_wide_stat_dicts(target: dict[int, dict[str, Any]], page_rows: list[dict]) -> None:
    for row in page_rows:
        player = row.get("player") or {}
        pid = player.get("id")
        if pid is None:
            continue
        bucket = target.setdefault(int(pid), {})
        bucket.setdefault("_player", player)
        team = row.get("team") or {}
        if team:
            bucket.setdefault("_team", team)
        for k, v in row.items():
            if k in ("player", "team"):
                continue
            # Keep wide stats in group_stats without requiring schema changes.
            bucket[f"league_stats:{k}"] = v


def fetch_full_season_statistics(
    config: SofascoreSeasonConfig,
    delay_seconds: float | None = None,
) -> dict[int, dict[str, Any]]:
    if delay_seconds is None:
        delay_seconds = float(
            getattr(settings, "STATBALLER_SOFASCORE_REQUEST_DELAY_SECONDS", 1.5)
        )
    merged: dict[int, dict[str, Any]] = {}
    for group in STAT_GROUPS:
        offset = 0
        while True:
            payload = fetch_statistics_page(config, group, offset)
            results = payload.get("results") or []
            if not results:
                break
            merge_player_stat_dicts(merged, group, results)
            page = int(payload.get("page") or 1)
            pages = int(payload.get("pages") or 1)
            if page >= pages:
                break
            offset += len(results)
            time.sleep(delay_seconds)
        time.sleep(delay_seconds)
    offset = 0
    while True:
        payload = fetch_wide_statistics_page(config, offset)
        results = payload.get("results") or []
        if not results:
            break
        merge_player_wide_stat_dicts(merged, results)
        page = int(payload.get("page") or 1)
        pages = int(payload.get("pages") or 1)
        if page >= pages:
            break
        offset += len(results)
        time.sleep(delay_seconds)
    for bucket in merged.values():
        bucket["_group_stats"] = flat_row_to_group_stats(bucket)
    return merged


def flat_row_to_group_stats(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Strip flattened 'group:key' entries back into nested {group: {apiKey: value}}."""
    payload: dict[str, dict[str, Any]] = {}
    for k, v in row.items():
        if k in ("_player", "_team") or k.startswith("_"):
            continue
        if ":" not in k:
            continue
        grp, key = k.split(":", 1)
        payload.setdefault(grp, {})[key] = v
    return payload


def pick_flat(row: dict[str, Any], group: str, key: str) -> Any:
    value = row.get(f"{group}:{key}")
    if value is not None:
        return value
    # Fallback for broad SofaScore stats loaded via `fields=...`.
    return row.get(f"league_stats:{key}")


def row_to_normalized_record(player_id: int, row: dict[str, Any]) -> dict[str, Any]:
    player = row.get("_player") or {}
    team = row.get("_team") or {}
    g = lambda grp, k: pick_flat(row, grp, k)  # noqa: E731

    def num(grp: str, k: str) -> int | None:
        v = g(grp, k)
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            try:
                return int(float(v))
            except (TypeError, ValueError):
                return None

    def flt(grp: str, k: str) -> float | None:
        v = g(grp, k)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def rating() -> float | None:
        for grp in ("summary", "defence", "passing", "goalkeeper"):
            r = flt(grp, "rating")
            if r is not None:
                return r
        return flt("attack", "rating")

    def tackles() -> int | None:
        v = num("defence", "tackles")
        if v is not None:
            return v
        return num("summary", "tackles")

    return {
        "provider_player_id": str(player_id),
        "player_name": player.get("name") or "",
        "position_raw": (player.get("position") or "")[:64],
        "provider_team_id": str(team.get("id") or "") or "",
        "team_name": team.get("name") or "",
        "group_stats": row.get("_group_stats") or flat_row_to_group_stats(row),
        "appearances": num("summary", "appearances") or num("summary", "games"),
        "minutes": num("summary", "minutesPlayed"),
        "rating": rating(),
        "summary_goals": num("summary", "goals"),
        "summary_assists": num("summary", "assists"),
        "summary_expected_goals": flt("summary", "expectedGoals"),
        "summary_expected_assists": flt("league_stats", "expectedAssists"),
        "total_shots": num("league_stats", "totalShots") or num("attack", "totalShots"),
        "summary_successful_dribbles": num("summary", "successfulDribbles"),
        "summary_accurate_passes_percentage": flt("summary", "accuratePassesPercentage"),
        "tackles": tackles(),
        "interceptions": num("defence", "interceptions"),
        "clearances": num("defence", "clearances"),
        "error_lead_to_goal": num("defence", "errorLeadToGoal"),
        "outfielder_blocks": num("defence", "outfielderBlocks"),
        "big_chances_created": num("passing", "bigChancesCreated"),
        "accurate_passes": num("passing", "accuratePasses"),
        "inaccurate_passes": num("passing", "inaccuratePasses"),
        "total_passes": num("passing", "totalPasses"),
        "key_passes": num("passing", "keyPasses"),
        "tackles_won": num("league_stats", "tacklesWon"),
        "tackles_won_percentage": flt("league_stats", "tacklesWonPercentage"),
        "shots_on_target": num("league_stats", "shotsOnTarget"),
        "shots_off_target": num("league_stats", "shotsOffTarget"),
        "aerial_duels_won": num("league_stats", "aerialDuelsWon"),
        "ground_duels_won": num("league_stats", "groundDuelsWon"),
        "ball_recoveries": num("league_stats", "ballRecovery"),
        "successful_dribbles_percentage": flt("league_stats", "successfulDribblesPercentage"),
        "fouls": num("league_stats", "fouls"),
        "offsides": num("league_stats", "offsides"),
        "accurate_passes_percentage": flt("passing", "accuratePassesPercentage"),
        "accurate_crosses": num("passing", "accurateCrosses"),
        "accurate_long_balls": num("passing", "accurateLongBalls"),
        "saves": num("goalkeeper", "saves"),
        "clean_sheet": num("goalkeeper", "cleanSheet"),
        "penalty_save": num("goalkeeper", "penaltySave"),
        "saved_shots_from_inside_the_box": num("goalkeeper", "savedShotsFromInsideTheBox"),
        "runs_out": num("goalkeeper", "runsOut"),
    }
