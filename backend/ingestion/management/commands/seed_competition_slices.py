from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from ingestion.competition_seed_manifest import COMPETITION_SEED_MANIFEST
from ingestion.models import Competition, CompetitionSeason, Season


class Command(BaseCommand):
    help = "Upsert competitions, seasons, and competition-season slices from the checked-in manifest."

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        competitions_created = 0
        competitions_updated = 0
        seasons_created = 0
        slices_created = 0
        slices_updated = 0

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
                )
                competitions_created += 1
            else:
                changed = False
                for field, value in (
                    ("short_code", comp_cfg["code"]),
                    ("name", comp_cfg["name"]),
                    ("country", comp_cfg.get("country") or ""),
                ):
                    if getattr(competition, field) != value:
                        setattr(competition, field, value)
                        changed = True
                if changed:
                    competition.save(update_fields=["short_code", "name", "country"])
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

                slice_obj, created = CompetitionSeason.objects.get_or_create(
                    competition=competition,
                    season=season,
                    defaults=defaults,
                )
                if created:
                    slices_created += 1
                    continue

                changed_fields: list[str] = []
                for field_name, value in defaults.items():
                    if getattr(slice_obj, field_name) != value:
                        setattr(slice_obj, field_name, value)
                        changed_fields.append(field_name)
                if changed_fields:
                    slice_obj.save(update_fields=changed_fields)
                    slices_updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded competitions="
                f"{competitions_created} created, {competitions_updated} updated; "
                f"seasons={seasons_created} created; "
                f"slices={slices_created} created, {slices_updated} updated."
            )
        )
