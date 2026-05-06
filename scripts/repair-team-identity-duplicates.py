from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

import django  # noqa: E402

django.setup()

from django.db import transaction  # noqa: E402

from ingestion.models import (  # noqa: E402
    CanonicalTeam,
    MergedPlayerSeason,
    MergedTeamSeason,
    PlayerSeasonClubSpell,
    PlayerSeasonDerivedStats,
    PlayerSeasonEmbedding,
    PlayerSeasonGkDerivedStats,
    Provider,
    ProviderTeamMapping,
    ReepTeamRow,
    SofascorePlayerSeasonSource,
    SofascoreTeamSeasonSource,
    UnderstatPlayerSeasonSource,
    UnmatchedProviderTeam,
)


MERGES = [
    # Understat created "Strasbourg" separately from SofaScore "RC Strasbourg".
    {"source_id": 79, "target_id": 97, "target_name": "RC Strasbourg"},
    # Keep the Reep-backed Understat canonical rows for these, and attach SofaScore to them.
    {"source_id": 377, "target_id": 307, "target_name": "Deportivo Alavés"},
    {"source_id": 387, "target_id": 308, "target_name": "Levante UD"},
]

REEP_PROVIDER_FIXES = [
    {
        "reep_id": "reep_t52e2f188",
        "name": "Deportivo Alavés",
        "understat_team_id": "158",
        "sofascore_team_id": "2885",
    },
    {
        "reep_id": "reep_t88b915a8",
        "name": "Levante UD",
        "understat_team_id": "151",
        "sofascore_team_id": "2849",
    },
]


def replace_secondary_team_ids(source_id: int, target_id: int) -> int:
    changed = 0
    for row in MergedPlayerSeason.objects.filter(secondary_display_team_ids__contains=[source_id]):
        ids = row.secondary_display_team_ids or []
        next_ids = []
        seen = set()
        for team_id in ids:
            replacement = target_id if team_id == source_id else team_id
            if replacement not in seen:
                next_ids.append(replacement)
                seen.add(replacement)
        if next_ids != ids:
            row.secondary_display_team_ids = next_ids
            row.save(update_fields=["secondary_display_team_ids"])
            changed += 1
    return changed


def merge_team(source_id: int, target_id: int, target_name: str) -> dict[str, int]:
    source = CanonicalTeam.objects.get(pk=source_id)
    target = CanonicalTeam.objects.get(pk=target_id)
    target.name = target_name
    target.save(update_fields=["name"])

    counts: dict[str, int] = {}
    counts["provider_mappings"] = ProviderTeamMapping.objects.filter(canonical_team=source).update(
        canonical_team=target
    )
    counts["unmatched_resolutions"] = UnmatchedProviderTeam.objects.filter(resolved_team=source).update(
        resolved_team=target
    )
    counts["understat_sources"] = UnderstatPlayerSeasonSource.objects.filter(canonical_team=source).update(
        canonical_team=target
    )
    counts["sofascore_sources"] = SofascorePlayerSeasonSource.objects.filter(canonical_team=source).update(
        canonical_team=target
    )
    counts["sofascore_team_sources"] = SofascoreTeamSeasonSource.objects.filter(canonical_team=source).update(
        canonical_team=target
    )
    counts["club_spells"] = PlayerSeasonClubSpell.objects.filter(canonical_team=source).update(
        canonical_team=target
    )
    counts["merged_player_rows"] = MergedPlayerSeason.objects.filter(canonical_display_team=source).update(
        canonical_display_team=target
    )
    counts["derived_rows"] = PlayerSeasonDerivedStats.objects.filter(canonical_display_team=source).update(
        canonical_display_team=target
    )
    counts["gk_derived_rows"] = PlayerSeasonGkDerivedStats.objects.filter(canonical_display_team=source).update(
        canonical_display_team=target
    )
    counts["embedding_rows"] = PlayerSeasonEmbedding.objects.filter(canonical_display_team=source).update(
        canonical_display_team=target
    )
    counts["merged_team_rows"] = MergedTeamSeason.objects.filter(canonical_team=source).update(
        canonical_team=target
    )
    counts["secondary_team_ids"] = replace_secondary_team_ids(source_id, target_id)
    source.delete()
    return counts


@transaction.atomic
def main() -> None:
    for fix in REEP_PROVIDER_FIXES:
        ReepTeamRow.objects.update_or_create(
            reep_id=fix["reep_id"],
            defaults={
                "name": fix["name"],
                "understat_team_id": fix["understat_team_id"],
                "sofascore_team_id": fix["sofascore_team_id"],
            },
        )

    # Ensure provider maps exist before and after the FK merge.
    ProviderTeamMapping.objects.update_or_create(
        provider=Provider.UNDERSTAT,
        provider_team_id="225",
        defaults={"canonical_team_id": 97},
    )
    ProviderTeamMapping.objects.update_or_create(
        provider=Provider.SOFASCORE,
        provider_team_id="1659",
        defaults={"canonical_team_id": 97},
    )
    ProviderTeamMapping.objects.update_or_create(
        provider=Provider.UNDERSTAT,
        provider_team_id="158",
        defaults={"canonical_team_id": 307},
    )
    ProviderTeamMapping.objects.update_or_create(
        provider=Provider.SOFASCORE,
        provider_team_id="2885",
        defaults={"canonical_team_id": 307},
    )
    ProviderTeamMapping.objects.update_or_create(
        provider=Provider.UNDERSTAT,
        provider_team_id="151",
        defaults={"canonical_team_id": 308},
    )
    ProviderTeamMapping.objects.update_or_create(
        provider=Provider.SOFASCORE,
        provider_team_id="2849",
        defaults={"canonical_team_id": 308},
    )

    for merge in MERGES:
        counts = merge_team(**merge)
        print(f"{merge['source_id']} -> {merge['target_id']}: {counts}")


if __name__ == "__main__":
    main()
