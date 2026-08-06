from __future__ import annotations

"""Canonical and aggregate season-label contracts."""

import re

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

CALENDAR_LABEL_PATTERN = re.compile(r"^(?P<year>\d{4})$")
SPLIT_LABEL_PATTERN = re.compile(r"^(?P<start>\d{4})-(?P<end>\d{2}|\d{4})$")


def aggregate_season_label(canonical_label: str) -> str:
    """Return the same-start-year split label used by cross-league aggregates."""
    label = canonical_label.strip()
    match = CALENDAR_LABEL_PATTERN.fullmatch(label)
    if not match:
        return label
    start_year = int(match.group("year"))
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def aggregate_constituent_season_labels(aggregate_label: str) -> list[str]:
    """Return canonical labels whose seasons belong to an aggregate label."""
    requested = aggregate_label.strip()
    canonical = aggregate_season_label(requested)
    labels = [canonical]
    match = SPLIT_LABEL_PATTERN.fullmatch(canonical)
    if not match:
        return labels

    start_year = int(match.group("start"))
    end = match.group("end")
    end_year = int(end) if len(end) == 4 else start_year - (start_year % 100) + int(end)
    if end_year <= start_year:
        end_year += 100
    if end_year == start_year + 1:
        labels.append(str(start_year))
    return labels


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
