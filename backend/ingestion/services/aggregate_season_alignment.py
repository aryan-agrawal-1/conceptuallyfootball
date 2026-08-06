from __future__ import annotations

from typing import Any

from ingestion.competition_scope import (
    domestic_aggregate_seasons,
    public_competition_seasons,
    resolve_public_scope,
)
from ingestion.models import (
    GalaxySnapshot,
    MergedTeamSeason,
    PlayerSeasonDerivedStats,
    PlayerSeasonGkDerivedStats,
)
from ingestion.services.season_labels import aggregate_season_label


def calendar_aggregate_coverage() -> dict[str, Any]:
    """Report whether every published calendar slice reaches its intended ALL cohort."""
    calendar_slices = list(
        domestic_aggregate_seasons(public_competition_seasons())
        .filter(season__label__regex=r"^\d{4}$")
        .select_related("competition", "season")
        .order_by("season__label", "competition__short_code")
    )
    aggregate_labels = sorted({aggregate_season_label(row.season.label) for row in calendar_slices})
    constituents_by_label: dict[str, set[int]] = {
        label: {row.id for row in resolve_public_scope("ALL", label)}
        for label in aggregate_labels
    }

    current_snapshots = {
        snapshot.season_label: snapshot
        for snapshot in GalaxySnapshot.objects.filter(
            scope_code="ALL",
            season_label__in=aggregate_labels,
            is_current=True,
        )
    }
    rows = []
    warnings = []
    for competition_season in calendar_slices:
        aggregate_label = aggregate_season_label(competition_season.season.label)
        expected_constituents = constituents_by_label[aggregate_label]
        included_in_scope = competition_season.id in expected_constituents
        snapshot = current_snapshots.get(aggregate_label)
        included_in_galaxy = bool(
            snapshot and competition_season.id in snapshot.included_competition_season_ids
        )
        counts = {
            "outfield_rows": PlayerSeasonDerivedStats.objects.filter(
                competition_season=competition_season,
                is_current=True,
            ).count(),
            "eligible_outfield_rows": PlayerSeasonDerivedStats.objects.filter(
                competition_season=competition_season,
                is_current=True,
                percentiles_eligible=True,
            ).count(),
            "goalkeeper_rows": PlayerSeasonGkDerivedStats.objects.filter(
                competition_season=competition_season,
                is_current=True,
            ).count(),
            "eligible_goalkeeper_rows": PlayerSeasonGkDerivedStats.objects.filter(
                competition_season=competition_season,
                is_current=True,
                percentiles_eligible=True,
            ).count(),
            "team_rows": MergedTeamSeason.objects.filter(
                competition_season=competition_season,
                is_current=True,
            ).count(),
            "aggregate_galaxy_rows": (
                snapshot.player_embeddings.filter(competition_season=competition_season).count()
                if snapshot
                else 0
            ),
        }
        row = {
            "competition_season_id": competition_season.id,
            "competition": competition_season.competition.short_code,
            "canonical_season": competition_season.season.label,
            "aggregate_season": aggregate_label,
            "aggregate_constituent_count": len(expected_constituents),
            "included_in_all_scope": included_in_scope,
            "included_in_current_all_galaxy": included_in_galaxy,
            **counts,
        }
        rows.append(row)
        if not included_in_scope:
            warnings.append(
                f"{competition_season} is omitted from ALL {aggregate_label} by season-label alignment."
            )
        if counts["eligible_outfield_rows"] and not included_in_galaxy:
            warnings.append(
                f"{competition_season} has eligible players but is absent from the current "
                f"ALL {aggregate_label} Galaxy snapshot."
            )

    aggregate_counts = {}
    for label, constituent_ids in sorted(constituents_by_label.items()):
        aggregate_counts[label] = {
            "competition_season_ids": sorted(constituent_ids),
            "outfield_rows": PlayerSeasonDerivedStats.objects.filter(
                competition_season_id__in=constituent_ids,
                is_current=True,
            ).count(),
            "eligible_outfield_rows": PlayerSeasonDerivedStats.objects.filter(
                competition_season_id__in=constituent_ids,
                is_current=True,
                percentiles_eligible=True,
            ).count(),
            "goalkeeper_rows": PlayerSeasonGkDerivedStats.objects.filter(
                competition_season_id__in=constituent_ids,
                is_current=True,
            ).count(),
            "eligible_goalkeeper_rows": PlayerSeasonGkDerivedStats.objects.filter(
                competition_season_id__in=constituent_ids,
                is_current=True,
                percentiles_eligible=True,
            ).count(),
            "team_rows": MergedTeamSeason.objects.filter(
                competition_season_id__in=constituent_ids,
                is_current=True,
            ).count(),
            "current_galaxy_rows": (
                current_snapshots[label].player_embeddings.count()
                if label in current_snapshots
                else 0
            ),
        }

    return {
        "ok": not warnings,
        "calendar_slices": rows,
        "aggregate_counts": aggregate_counts,
        "warnings": warnings,
    }
