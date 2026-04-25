from __future__ import annotations

import re

from ingestion.models import PositionGroup


_MID_TOKENS = {"DM", "CM", "LM", "RM", "CAM", "CDM", "MID", "MIDFIELD", "MIDFIELDER"}
_DEF_TOKENS = {
    "D",
    "DEF",
    "DEFENDER",
    "DEFENCE",
    "BACK",
    "CENTERBACK",
    "CENTREBACK",
    "CB",
    "LB",
    "RB",
    "LWB",
    "RWB",
    "WB",
    "FULLBACK",
    "WINGBACK",
}
_FWD_TOKENS = {
    "F",
    "FW",
    "ST",
    "CF",
    "LW",
    "RW",
    "AM",
    "SS",
    "FORWARD",
    "WINGER",
    "STRIKER",
}


def _position_tokens(raw: str) -> list[str]:
    cleaned = raw.strip().upper()
    if not cleaned:
        return []
    return [token for token in re.split(r"[^A-Z]+", cleaned) if token]


def normalize_position_group(raw: str | None) -> str:
    if not raw:
        return PositionGroup.UNKNOWN
    p = raw.strip().upper()
    tokens = _position_tokens(p)
    if p in ("GK", "G", "GOALKEEPER"):
        return PositionGroup.GK
    if "GOALKEEPER" in p or "GK" in tokens:
        return PositionGroup.GK
    if any(token in _MID_TOKENS for token in tokens):
        return PositionGroup.MID
    if any(token in _DEF_TOKENS for token in tokens):
        return PositionGroup.DEF
    if any(token in _FWD_TOKENS for token in tokens):
        return PositionGroup.FWD
    if p.startswith("D") or "DEF" in p:
        return PositionGroup.DEF
    if p.startswith("F"):
        return PositionGroup.FWD
    if p.startswith("M") or "MID" in p:
        return PositionGroup.MID
    return PositionGroup.UNKNOWN
