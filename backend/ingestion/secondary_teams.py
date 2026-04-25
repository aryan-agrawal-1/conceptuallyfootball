from __future__ import annotations

from ingestion.models import CanonicalTeam, MergedPlayerSeason


def secondary_teams_payload(merged: MergedPlayerSeason | None) -> list[dict[str, int | str]]:
    """Ordered team badges for multi-club Understat seasons (from merged_player_season)."""
    if merged is None:
        return []
    ids = merged.secondary_display_team_ids or []
    if not ids:
        return []
    teams = CanonicalTeam.objects.filter(pk__in=ids)
    by_id = {t.pk: t.name for t in teams}
    return [
        {"canonical_team_id": pk, "canonical_team_name": by_id[pk]}
        for pk in ids
        if pk in by_id
    ]
