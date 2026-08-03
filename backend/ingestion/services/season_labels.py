from __future__ import annotations

"""Competition-specific season label compatibility.

Only EST1 and NOR1 have legacy split-year labels for provider calendar seasons.
Aggregate scopes deliberately do not use these mappings: an ``ALL`` or ``BIG5``
request must continue to resolve the exact label supplied by the caller.
"""

CALENDAR_SEASON_LABEL_ALIASES: dict[str, dict[str, str]] = {
    "EST1": {
        "2021-22": "2021",
        "2022-23": "2022",
        "2023-24": "2023",
        "2024-25": "2024",
        "2025-26": "2025",
        "2026-27": "2026",
    },
    "NOR1": {
        "2021-22": "2021",
        "2022-23": "2022",
        "2023-24": "2023",
        "2024-25": "2024",
        "2025-26": "2025",
        "2026-27": "2026",
    },
}


def canonical_season_label(competition_code: str, season_label: str) -> str:
    code = competition_code.strip().upper()
    label = season_label.strip()
    return CALENDAR_SEASON_LABEL_ALIASES.get(code, {}).get(label, label)


def candidate_season_labels(competition_code: str, season_label: str) -> list[str]:
    """Return canonical and legacy labels accepted during deploy reconciliation."""
    code = competition_code.strip().upper()
    requested = season_label.strip()
    canonical = canonical_season_label(code, requested)
    candidates = [canonical]
    if requested not in candidates:
        candidates.append(requested)
    candidates.extend(alias for alias in season_label_aliases(code, canonical) if alias not in candidates)
    return candidates


def season_label_aliases(competition_code: str, canonical_label: str) -> list[str]:
    code = competition_code.strip().upper()
    label = canonical_label.strip()
    return sorted(
        alias
        for alias, canonical in CALENDAR_SEASON_LABEL_ALIASES.get(code, {}).items()
        if canonical == label
    )
