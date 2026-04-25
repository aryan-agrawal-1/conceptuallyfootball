from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings

from ingestion.models import ReepPlayerRow, ReepTeamRow


def release_reep_player_id_clashes(
    *,
    reep_id: str,
    understat_player_id: str | None,
    sofascore_player_id: str | None,
) -> None:
    """
    The public reep CSV can contain duplicate provider keys across different reep_id rows.
    We keep one row per reep_id; before assigning a provider id, drop it from any other row.
    """
    if understat_player_id:
        ReepPlayerRow.objects.filter(understat_player_id=understat_player_id).exclude(
            reep_id=reep_id
        ).update(understat_player_id=None)
    if sofascore_player_id:
        ReepPlayerRow.objects.filter(sofascore_player_id=sofascore_player_id).exclude(
            reep_id=reep_id
        ).update(sofascore_player_id=None)


def release_reep_team_id_clashes(
    *,
    reep_id: str,
    understat_team_id: str | None,
    sofascore_team_id: str | None,
) -> None:
    if understat_team_id:
        ReepTeamRow.objects.filter(understat_team_id=understat_team_id).exclude(reep_id=reep_id).update(
            understat_team_id=None
        )
    if sofascore_team_id:
        ReepTeamRow.objects.filter(sofascore_team_id=sofascore_team_id).exclude(reep_id=reep_id).update(
            sofascore_team_id=None
        )


def load_reep_document(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def sync_reep_from_path(path: Path) -> dict[str, int]:
    """
    Expected JSON shape (scoped subset):
    {
      "players": [{"reep_id": "...", "full_name": "...", "position": "...", "position_detail": "...", "understat_player_id": "1", "sofascore_player_id": "2"}],
      "teams": [{"reep_id": "...", "name": "...", "understat_team_id": "...", "sofascore_team_id": "..."}]
    }
    Omitted provider ids are stored as null.
    """
    doc = load_reep_document(path)
    players = doc.get("players") or []
    teams = doc.get("teams") or []
    p_count = 0
    t_count = 0
    for p in players:
        rid = str(p["reep_id"])
        under = _norm_id(p.get("understat_player_id"))
        sofa = _norm_id(p.get("sofascore_player_id"))
        release_reep_player_id_clashes(
            reep_id=rid,
            understat_player_id=under,
            sofascore_player_id=sofa,
        )
        ReepPlayerRow.objects.update_or_create(
            reep_id=rid,
            defaults={
                "full_name": p.get("full_name") or p.get("name") or "",
                "position": str(p.get("position") or "")[:64],
                "position_detail": str(p.get("position_detail") or "")[:128],
                "understat_player_id": under,
                "sofascore_player_id": sofa,
            },
        )
        p_count += 1
    for t in teams:
        rid = str(t["reep_id"])
        under = _norm_id(t.get("understat_team_id"))
        sofa = _norm_id(t.get("sofascore_team_id"))
        release_reep_team_id_clashes(
            reep_id=rid,
            understat_team_id=under,
            sofascore_team_id=sofa,
        )
        ReepTeamRow.objects.update_or_create(
            reep_id=rid,
            defaults={
                "name": t.get("name") or "",
                "understat_team_id": under,
                "sofascore_team_id": sofa,
            },
        )
        t_count += 1
    return {"players": p_count, "teams": t_count}


def _norm_id(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def default_reep_path() -> Path | None:
    raw = (settings.STATBALLER_REEP_DATA_PATH or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()
