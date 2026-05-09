from __future__ import annotations

"""
Import identity rows from official reep CSV dumps (https://github.com/withqwerty/reep).

Upstream layout:
  data/people.csv — players + coaches; use `type` == `player` for player matching.
  data/teams.csv  — clubs.

Relevant columns (people):
  reep_id, type, name, full_name, position, position_detail, key_understat,
  key_sofascore, ...

Relevant columns (teams):
  reep_id, name, key_sofascore, key_transfermarkt, ...  (there is typically NO
  `key_understat` on teams in the published schema, so Understat club IDs often
  cannot be auto-linked from reep alone — use manual team mappings in admin.)

Empty cells are normalized to NULL in the database.
"""

import csv
from pathlib import Path

from ingestion.models import ReepPlayerRow, ReepTeamRow
from ingestion.services.reep_sync import release_reep_player_id_clashes, release_reep_team_id_clashes

TEAM_CSV_PROVIDER_OVERRIDES: dict[str, dict[str, str | None]] = {
    # Local correction for bad/missing Understat IDs in the upstream reep team dump.
    "reep_tfa99f7f9": {"key_understat": "220"},  # Brighton & Hove Albion F.C.
    "reep_te6c8eca5": {"key_understat": "81"},  # West Ham United F.C.
    "reep_t70979bf6": {"key_understat": None},  # SC Freiburg should not own Brighton's Understat id.
    "reep_t52e2f188": {"key_sofascore": "2885"},  # Deportivo Alavés.
    "reep_t88b915a8": {"key_sofascore": "2849"},  # Levante UD.
}

PLAYER_CSV_PROVIDER_OVERRIDES: dict[str, dict[str, str | None]] = {
    # Upstream currently has this player as "Yamil yamil" with only a SofaScore key.
    # Keep the SofaScore key, attach the known Understat key, and expose the real name.
    "reep_p9aa62ce3": {
        "full_name": "Lamine Yamal",
        "name": "Lamine Yamal",
        "key_understat": "11527",
        "key_sofascore": "1402912",
    },
    # Local corrections for upstream/provider identity gaps observed in merged slices.
    "reep_p625fe6e2": {"key_sofascore": "825550"},  # Joe Johnson, Luton.
    "reep_p3695a227": {"key_sofascore": "2322979"},  # Sokratis Papastathopoulos, Real Betis.
    "reep_p52974f47": {
        "full_name": "Luis Javier Suárez",
        "name": "Luis Javier Suárez",
        "key_understat": "8978",
        "key_sofascore": "914213",
    },
    "reep_p96d752b4": {"key_understat": "11249"},  # Ousmane Camara, Auxerre.
}


def _cell(row: dict[str, str], *keys: str) -> str | None:
    for k in keys:
        v = (row.get(k) or "").strip()
        if v and v != "—" and v.lower() != "nan":
            return v
    return None


def _team_provider_value(row: dict[str, str], key: str) -> str | None:
    reep_id = _cell(row, "reep_id")
    override = TEAM_CSV_PROVIDER_OVERRIDES.get(reep_id or "", {})
    if key in override:
        value = override[key]
        return str(value) if value not in (None, "") else None
    return _cell(row, key)


def _player_provider_value(row: dict[str, str], key: str) -> str | None:
    reep_id = _cell(row, "reep_id")
    override = PLAYER_CSV_PROVIDER_OVERRIDES.get(reep_id or "", {})
    if key in override:
        value = override[key]
        return str(value) if value not in (None, "") else None
    return _cell(row, key)


def sync_reep_from_csv_dir(directory: Path) -> dict[str, int]:
    people_path = directory / "people.csv"
    teams_path = directory / "teams.csv"
    if not people_path.is_file():
        raise FileNotFoundError(f"Missing people.csv in {directory}")
    if not teams_path.is_file():
        raise FileNotFoundError(f"Missing teams.csv in {directory}")
    return {
        "players": _sync_people_csv(people_path),
        "teams": _sync_teams_csv(teams_path),
    }


def _sync_people_csv(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("type") or "").strip().lower() != "player":
                continue
            rid = _cell(row, "reep_id")
            if not rid:
                continue
            under = _player_provider_value(row, "key_understat")
            sofa = _player_provider_value(row, "key_sofascore")
            if not under and not sofa:
                continue
            display = (
                _player_provider_value(row, "full_name")
                or _player_provider_value(row, "name")
                or ""
            )
            release_reep_player_id_clashes(
                reep_id=rid,
                understat_player_id=under,
                sofascore_player_id=sofa,
            )
            ReepPlayerRow.objects.update_or_create(
                reep_id=rid,
                defaults={
                    "full_name": display,
                    "position": _cell(row, "position") or "",
                    "position_detail": _cell(row, "position_detail") or "",
                    "understat_player_id": under,
                    "sofascore_player_id": sofa,
                },
            )
            count += 1
    return count


def _sync_teams_csv(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rid = _cell(row, "reep_id")
            if not rid:
                continue
            name = _cell(row, "name") or ""
            under = _team_provider_value(row, "key_understat")
            sofa = _team_provider_value(row, "key_sofascore")
            if not under and not sofa:
                continue
            release_reep_team_id_clashes(
                reep_id=rid,
                understat_team_id=under,
                sofascore_team_id=sofa,
            )
            ReepTeamRow.objects.update_or_create(
                reep_id=rid,
                defaults={
                    "name": name,
                    "understat_team_id": under,
                    "sofascore_team_id": sofa,
                },
            )
            count += 1
    return count
