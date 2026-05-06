from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.db.models import Q

from ingestion.models import (
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    IngestionRunStatus,
    MergedPlayerSeason,
    PositionGroup,
    SofascorePlayerSeasonSource,
)
from ingestion.position import normalize_position_group
from ingestion.services.galaxy import materialize_galaxy_embeddings
from ingestion.services.ingest import run_merge_job
from ingestion.services.sofascore_client import fetch_player_profile
from ingestion.services.derived import materialize_derived_stats


def _profile_position(profile: dict) -> str:
    detailed = profile.get("positionsDetailed")
    if isinstance(detailed, list):
        for value in detailed:
            if value and normalize_position_group(str(value)) != PositionGroup.UNKNOWN:
                return str(value)
    position = profile.get("position")
    return str(position or "")


class Command(BaseCommand):
    help = "Backfill missing Sofascore player positions from /api/v1/player/{id} and rebuild affected slices."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--competition", help="Competition short code, e.g. SCO1.")
        parser.add_argument("--season", help="Season label, e.g. 2025-26.")
        parser.add_argument("--limit", type=int, help="Maximum provider players to fetch.")
        parser.add_argument("--sleep", type=float, default=0.05, help="Seconds to sleep between player profile requests.")
        parser.add_argument("--skip-galaxy", action="store_true", help="Skip galaxy rematerialization.")
        parser.add_argument("--dry-run", action="store_true", help="Fetch and report without writing or rematerializing.")

    def handle(self, *args, **options) -> None:
        source_qs = SofascorePlayerSeasonSource.objects.filter(Q(position_raw="") | Q(position_raw__isnull=True))
        if options.get("competition"):
            source_qs = source_qs.filter(
                competition_season__competition__short_code=options["competition"]
            )
        if options.get("season"):
            source_qs = source_qs.filter(competition_season__season__label=options["season"])

        unknown_player_ids = set(
            MergedPlayerSeason.objects.filter(
                is_current=True,
                position_group=PositionGroup.UNKNOWN,
                competition_season__in=source_qs.values("competition_season_id"),
            ).values_list("canonical_player_id", flat=True)
        )
        source_qs = source_qs.filter(canonical_player_id__in=unknown_player_ids)
        provider_ids = list(
            source_qs.order_by("provider_player_id")
            .values_list("provider_player_id", flat=True)
            .distinct()
        )
        if options.get("limit"):
            provider_ids = provider_ids[: options["limit"]]

        fetched = 0
        updated = 0
        affected_slice_ids: set[int] = set()
        dry_run = bool(options["dry_run"])

        for provider_id in provider_ids:
            fetched += 1
            try:
                profile = fetch_player_profile(provider_id)
            except Exception as exc:  # noqa: BLE001
                self.stdout.write(self.style.WARNING(f"{provider_id}: fetch failed: {exc}"))
                continue
            raw_position = _profile_position(profile)
            group = normalize_position_group(raw_position)
            if group == PositionGroup.UNKNOWN:
                self.stdout.write(self.style.WARNING(f"{provider_id}: no usable position ({raw_position!r})"))
                continue

            rows = list(source_qs.filter(provider_player_id=provider_id))
            affected_slice_ids.update(row.competition_season_id for row in rows)
            updated += len(rows)
            if not dry_run:
                SofascorePlayerSeasonSource.objects.filter(pk__in=[row.pk for row in rows]).update(
                    position_raw=raw_position[:64]
                )
            self.stdout.write(f"{provider_id}: {raw_position} -> {group} ({len(rows)} rows)")
            if options["sleep"]:
                time.sleep(float(options["sleep"]))

        self.stdout.write(
            self.style.SUCCESS(
                f"Fetched {fetched} player profiles; {'would update' if dry_run else 'updated'} {updated} source rows."
            )
        )
        if dry_run or not affected_slice_ids:
            return

        for cs in CompetitionSeason.objects.filter(pk__in=affected_slice_ids).order_by(
            "competition__short_code",
            "season__sort_order",
        ):
            merge_run = IngestionRun.objects.create(
                kind=IngestionKind.MERGE,
                competition_season=cs,
                status=IngestionRunStatus.PENDING,
            )
            run_merge_job(cs, run=merge_run)
            merge_run.refresh_from_db()
            if merge_run.status != IngestionRunStatus.SUCCESS:
                raise RuntimeError(merge_run.error_detail or f"Merge failed for {cs}")
            self.stdout.write(self.style.SUCCESS(f"{cs}: merge {merge_run.id} succeeded"))

            derived_run = IngestionRun.objects.create(
                kind=IngestionKind.DERIVED,
                competition_season=cs,
                status=IngestionRunStatus.PENDING,
            )
            materialize_derived_stats(cs, run=derived_run)
            derived_run.refresh_from_db()
            if derived_run.status != IngestionRunStatus.SUCCESS:
                raise RuntimeError(derived_run.error_detail or f"Derived failed for {cs}")
            self.stdout.write(self.style.SUCCESS(f"{cs}: derived {derived_run.id} succeeded"))

            if options["skip_galaxy"]:
                continue
            galaxy_run = IngestionRun.objects.create(
                kind=IngestionKind.GALAXY,
                competition_season=cs,
                status=IngestionRunStatus.PENDING,
            )
            materialize_galaxy_embeddings(cs, run=galaxy_run)
            galaxy_run.refresh_from_db()
            if galaxy_run.status != IngestionRunStatus.SUCCESS:
                raise RuntimeError(galaxy_run.error_detail or f"Galaxy failed for {cs}")
            self.stdout.write(self.style.SUCCESS(f"{cs}: galaxy {galaxy_run.id} succeeded"))
