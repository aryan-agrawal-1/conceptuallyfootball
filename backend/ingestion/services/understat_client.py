from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class UnderstatLeagueConfig:
    """Slice parameters for Understat player-season stats via soccerdata."""

    league: str
    season_year: str


def _canonical_soccerdata_league(league: str) -> str:
    """
    Map configured league values to Understat league slug used in /getLeagueData/{slug}/{season}.

    Supports current DB slugs (e.g. EPL) and common canonical names.
    """
    raw = league.strip()
    if not raw:
        raise ValueError("League cannot be empty.")
    slug_map = {
        "EPL": "EPL",
        "LA_LIGA": "La_liga",
        "LA LIGA": "La_liga",
        "BUNDESLIGA": "Bundesliga",
        "SERIE_A": "Serie_A",
        "SERIE A": "Serie_A",
        "LIGUE_1": "Ligue_1",
        "LIGUE 1": "Ligue_1",
        "RFPL": "RFPL",
        "ENG-PREMIER LEAGUE": "EPL",
        "ESP-LA LIGA": "La_liga",
        "GER-BUNDESLIGA": "Bundesliga",
        "ITA-SERIE A": "Serie_A",
        "FRA-LIGUE 1": "Ligue_1",
        "RUS-PREMIER LEAGUE": "RFPL",
    }
    key = raw.upper()
    return slug_map.get(key, raw)


def _soccerdata_row_to_legacy_record(row: Any) -> dict[str, Any]:
    """Normalize soccerdata read_player_season_stats row to the legacy Understat JSON keys."""
    pid = row.get("player_id")
    tid = row.get("team_id")
    return {
        "id": str(int(pid)) if pid is not None and str(pid).strip() != "" else "",
        "player_name": row.get("player") or "",
        "team_title": row.get("team") or "",
        "team_id": str(int(tid)) if tid is not None and str(tid).strip() != "" else "",
        "games": row.get("matches"),
        "time": row.get("minutes"),
        "goals": row.get("goals"),
        "assists": row.get("assists"),
        "shots": row.get("shots"),
        "key_passes": row.get("key_passes"),
        "npg": row.get("np_goals"),
        "xG": row.get("xg"),
        "npxG": row.get("np_xg"),
        "xA": row.get("xa"),
        "xGChain": row.get("xg_chain"),
        "xGBuildup": row.get("xg_buildup"),
        "yellow_cards": row.get("yellow_cards"),
        "red_cards": row.get("red_cards"),
        "position": row.get("position") or "",
    }


def fetch_league_players(config: UnderstatLeagueConfig, timeout: int = 45) -> list[dict[str, Any]]:
    """Load player-season aggregates for one league/season directly from Understat API."""
    league_slug = _canonical_soccerdata_league(config.league)
    season = config.season_year.strip()
    url = f"https://understat.com/getLeagueData/{league_slug}/{season}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": f"https://understat.com/league/{league_slug}/{season}",
    }
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    players = payload.get("players") or []
    teams_payload = payload.get("teams") or {}
    team_name_to_id: dict[str, str] = {}
    for team_blob in teams_payload.values():
        team_name = str(team_blob.get("title") or "").strip()
        team_id = str(team_blob.get("id") or "").strip()
        if team_name and team_id:
            team_name_to_id[team_name] = team_id
    if not players:
        return []
    out: list[dict[str, Any]] = []
    for row in players:
        raw_team_title = str(row.get("team_title") or "").strip()
        # Understat can list multiple clubs separated by comma in season aggregates.
        primary_team_title = raw_team_title.split(",")[0].strip() if raw_team_title else ""
        provider_team_ids: list[str] = []
        if raw_team_title:
            for seg in raw_team_title.split(","):
                seg = seg.strip()
                uid = team_name_to_id.get(seg, "")
                if uid:
                    provider_team_ids.append(uid)
        rec = {
            "id": str(row.get("id") or ""),
            "player_name": row.get("player_name") or "",
            "team_title": raw_team_title,
            "team_id": team_name_to_id.get(primary_team_title, ""),
            "provider_team_ids": provider_team_ids,
            "games": row.get("games"),
            "time": row.get("time"),
            "goals": row.get("goals"),
            "assists": row.get("assists"),
            "shots": row.get("shots"),
            "key_passes": row.get("key_passes"),
            "npg": row.get("npg"),
            "xG": row.get("xG"),
            "npxG": row.get("npxG"),
            "xA": row.get("xA"),
            "xGChain": row.get("xGChain"),
            "xGBuildup": row.get("xGBuildup"),
            "yellow_cards": row.get("yellow_cards"),
            "red_cards": row.get("red_cards"),
            "position": row.get("position") or "",
        }
        if rec.get("id"):
            out.append(rec)
    return out


def parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
