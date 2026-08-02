from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from ingestion.api_cache import invalidate_materialized_api_payloads
from ingestion.competition_seed_manifest import COMPETITION_SEED_MANIFEST
from ingestion.models import Competition, CompetitionSeason, CompetitionType, GalaxySnapshot, Season


def _reconcile_legacy_season_label(
    competition: Competition,
    season: Season,
    season_cfg: dict,
) -> CompetitionSeason | None:
    legacy_label = season_cfg.get("legacy_label_alias")
    if not legacy_label or legacy_label == season.label:
        return None

    target_exists = CompetitionSeason.objects.filter(
        competition=competition,
        season=season,
    ).exists()
    alias_rows = list(
        CompetitionSeason.objects.select_for_update()
        .filter(competition=competition, season__label=legacy_label)
        .order_by("id")
    )
    if len(alias_rows) > 1:
        raise ValueError(
            f"Cannot reconcile {competition.short_code} {legacy_label}: "
            f"found {len(alias_rows)} legacy rows; refusing to guess."
        )
    if target_exists and alias_rows:
        raise ValueError(
            f"Cannot reconcile {competition.short_code} {legacy_label} to {season.label}: "
            "both legacy and canonical slices exist."
        )
    if not alias_rows:
        return None

    slice_obj = alias_rows[0]
    slice_obj.season = season
    slice_obj.save(update_fields=["season"])
    return slice_obj


def _reconcile_legacy_galaxy_labels(
    competition: Competition,
    season: Season,
    season_cfg: dict,
) -> int:
    legacy_label = season_cfg.get("legacy_label_alias")
    if not legacy_label or legacy_label == season.label:
        return 0

    legacy_snapshots = list(
        GalaxySnapshot.objects.select_for_update()
        .filter(scope_code__iexact=competition.short_code, season_label=legacy_label)
        .order_by("id")
    )
    if not legacy_snapshots:
        return 0

    legacy_has_current = any(snapshot.is_current for snapshot in legacy_snapshots)
    canonical_has_current = GalaxySnapshot.objects.select_for_update().filter(
        scope_code__iexact=competition.short_code,
        season_label=season.label,
        is_current=True,
    ).exists()
    if legacy_has_current and canonical_has_current:
        raise ValueError(
            f"Cannot reconcile galaxy snapshots for {competition.short_code} "
            f"{legacy_label} to {season.label}: both labels have a current snapshot."
        )

    return GalaxySnapshot.objects.filter(pk__in=[row.pk for row in legacy_snapshots]).update(
        season_label=season.label,
    )


class Command(BaseCommand):
    help = "Upsert competitions, seasons, and competition-season slices from the checked-in manifest."

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        competitions_created = 0
        competitions_updated = 0
        seasons_created = 0
        slices_created = 0
        slices_updated = 0
        slices_relabelled = 0
        galaxy_snapshots_relabelled = 0

        for comp_cfg in COMPETITION_SEED_MANIFEST:
            aliases = comp_cfg.get("aliases") or []
            competition = Competition.objects.filter(short_code=comp_cfg["code"]).first()
            if competition is None and aliases:
                competition = Competition.objects.filter(short_code__in=aliases).first()
            if competition is None:
                competition = Competition.objects.filter(name=comp_cfg["name"]).first()

            if competition is None:
                competition = Competition.objects.create(
                    short_code=comp_cfg["code"],
                    name=comp_cfg["name"],
                    country=comp_cfg.get("country") or "",
                    competition_type=comp_cfg.get("competition_type", CompetitionType.DOMESTIC_LEAGUE),
                    include_in_domestic_aggregates=comp_cfg.get("include_in_domestic_aggregates", True),
                    minimum_eligible_minutes=comp_cfg.get("minimum_eligible_minutes", 450),
                )
                competitions_created += 1
            else:
                changed = False
                for field, value in (
                    ("short_code", comp_cfg["code"]),
                    ("name", comp_cfg["name"]),
                    ("country", comp_cfg.get("country") or ""),
                    ("competition_type", comp_cfg.get("competition_type", CompetitionType.DOMESTIC_LEAGUE)),
                    ("include_in_domestic_aggregates", comp_cfg.get("include_in_domestic_aggregates", True)),
                    ("minimum_eligible_minutes", comp_cfg.get("minimum_eligible_minutes", 450)),
                ):
                    if getattr(competition, field) != value:
                        setattr(competition, field, value)
                        changed = True
                if changed:
                    competition.save(
                        update_fields=[
                            "short_code",
                            "name",
                            "country",
                            "competition_type",
                            "include_in_domestic_aggregates",
                            "minimum_eligible_minutes",
                        ]
                    )
                    competitions_updated += 1

            for season_cfg in comp_cfg["seasons"]:
                season, created = Season.objects.get_or_create(
                    label=season_cfg["label"],
                    defaults={"sort_order": season_cfg["sort_order"]},
                )
                if created:
                    seasons_created += 1
                elif season.sort_order != season_cfg["sort_order"]:
                    season.sort_order = season_cfg["sort_order"]
                    season.save(update_fields=["sort_order"])

                defaults = {
                    "player_data_mode": comp_cfg["player_data_mode"],
                    "has_understat": comp_cfg["has_understat"],
                    "has_sofascore": comp_cfg["has_sofascore"],
                    "understat_league": season_cfg.get("understat_league"),
                    "understat_season_year": season_cfg.get("understat_season_year"),
                    "sofascore_unique_tournament_id": season_cfg.get("sofascore_unique_tournament_id"),
                    "sofascore_season_id": season_cfg.get("sofascore_season_id"),
                    "expected_team_count": comp_cfg["expected_team_count"],
                    "min_merged_team_count": comp_cfg["min_merged_team_count"],
                    "min_team_stats_coverage_count": comp_cfg["min_team_stats_coverage_count"],
                    "is_active": season_cfg.get("is_active", True),
                    "refresh_enabled": season_cfg.get("refresh_enabled", False),
                }
                season_threshold_overrides = {
                    field_name: season_cfg[field_name]
                    for field_name in (
                        "expected_team_count",
                        "min_merged_team_count",
                        "min_team_stats_coverage_count",
                    )
                    if field_name in season_cfg
                }

                reconciled_slice = _reconcile_legacy_season_label(competition, season, season_cfg)
                if reconciled_slice is not None:
                    slice_obj, created = reconciled_slice, False
                    slices_relabelled += 1
                else:
                    slice_obj, created = CompetitionSeason.objects.get_or_create(
                        competition=competition,
                        season=season,
                        defaults=defaults,
                    )
                galaxy_snapshots_relabelled += _reconcile_legacy_galaxy_labels(
                    competition,
                    season,
                    season_cfg,
                )
                if created:
                    slices_created += 1
                    continue

                changed_fields: list[str] = []
                for field_name, value in defaults.items():
                    # Threshold metadata can be pinned per season.  If a row
                    # has no explicit override, leave its existing historical
                    # value alone so changing a competition default cannot
                    # rewrite already-validated slices during a later seed.
                    if (
                        field_name
                        in {
                            "expected_team_count",
                            "min_merged_team_count",
                            "min_team_stats_coverage_count",
                        }
                        and field_name not in season_threshold_overrides
                    ):
                        continue
                    if getattr(slice_obj, field_name) != value:
                        setattr(slice_obj, field_name, value)
                        changed_fields.append(field_name)
                if changed_fields:
                    slice_obj.save(update_fields=changed_fields)
                    slices_updated += 1

        if (
            competitions_created
            or competitions_updated
            or seasons_created
            or slices_created
            or slices_updated
            or slices_relabelled
            or galaxy_snapshots_relabelled
        ):
            invalidate_materialized_api_payloads()

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded competitions="
                f"{competitions_created} created, {competitions_updated} updated; "
                f"seasons={seasons_created} created; "
                f"slices={slices_created} created, {slices_updated} updated, "
                f"{slices_relabelled} relabelled; "
                f"galaxy snapshots={galaxy_snapshots_relabelled} relabelled."
            )
        )
