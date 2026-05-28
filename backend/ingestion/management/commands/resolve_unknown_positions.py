from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from ingestion.models import (
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    IngestionRunStatus,
)
from ingestion.services.derived import materialize_derived_stats
from ingestion.services.galaxy import materialize_galaxy_embeddings
from ingestion.services.ingest import run_merge_job
from ingestion.services.position_resolution import resolve_unknown_positions
from ingestion.services.sofascore_client import (
    reset_request_metrics,
    set_request_cap,
    snapshot_request_metrics,
)


class Command(BaseCommand):
    help = "Resolve UNK player position groups using existing sources, history, and SofaScore roster/profile fallbacks."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--competition", help="Competition short code, e.g. ENG1.")
        parser.add_argument("--season", help="Season label, e.g. 2025-26.")
        parser.add_argument(
            "--include-superseded",
            action="store_true",
            help="Scan superseded merged rows too. Default scans current merged rows across all seasons.",
        )
        parser.add_argument("--max-requests", type=int, default=25, help="Maximum SofaScore HTTP requests.")
        parser.add_argument("--sleep", type=float, help="Seconds to sleep after SofaScore roster/team requests.")
        parser.add_argument("--skip-roster", action="store_true", help="Skip SofaScore team roster lookup.")
        parser.add_argument("--skip-profile", action="store_true", help="Skip SofaScore player profile fallback.")
        parser.add_argument("--dry-run", action="store_true", help="Report resolutions without writing.")
        parser.add_argument(
            "--rebuild",
            action="store_true",
            help="Re-run merge, derived, and galaxy for affected competition-seasons after writing resolutions.",
        )
        parser.add_argument("--skip-galaxy", action="store_true", help="With --rebuild, skip galaxy rematerialization.")

    def handle(self, *args, **options) -> None:
        max_requests = options.get("max_requests")
        if max_requests is not None and max_requests < 0:
            raise CommandError("--max-requests must be >= 0")

        reset_request_metrics()
        set_request_cap(max_requests)
        try:
            stats = resolve_unknown_positions(
                competition=options.get("competition"),
                season=options.get("season"),
                current_only=not options["include_superseded"],
                dry_run=options["dry_run"],
                use_roster=not options["skip_roster"],
                use_profile=not options["skip_profile"],
                sleep_seconds=options.get("sleep"),
            )
            metrics = snapshot_request_metrics()
        finally:
            set_request_cap(None)

        payload = stats.as_dict()
        payload["sofascore_http"] = metrics
        for key, value in payload.items():
            self.stdout.write(f"{key}: {value}")

        if options["dry_run"] or not options["rebuild"] or not stats.affected_competition_season_ids:
            return

        for cs in CompetitionSeason.objects.filter(
            pk__in=stats.affected_competition_season_ids
        ).order_by("competition__short_code", "season__sort_order"):
            self._rebuild_slice(cs, skip_galaxy=options["skip_galaxy"])

    def _rebuild_slice(self, cs: CompetitionSeason, *, skip_galaxy: bool) -> None:
        merge_run = IngestionRun.objects.create(
            kind=IngestionKind.MERGE,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )
        run_merge_job(cs, run=merge_run)
        merge_run.refresh_from_db()
        if merge_run.status != IngestionRunStatus.SUCCESS:
            raise CommandError(merge_run.error_detail or f"Merge failed for {cs}")
        self.stdout.write(self.style.SUCCESS(f"{cs}: merge {merge_run.id} succeeded"))

        derived_run = IngestionRun.objects.create(
            kind=IngestionKind.DERIVED,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )
        materialize_derived_stats(cs, run=derived_run)
        derived_run.refresh_from_db()
        if derived_run.status != IngestionRunStatus.SUCCESS:
            raise CommandError(derived_run.error_detail or f"Derived failed for {cs}")
        self.stdout.write(self.style.SUCCESS(f"{cs}: derived {derived_run.id} succeeded"))

        if skip_galaxy:
            return
        galaxy_run = IngestionRun.objects.create(
            kind=IngestionKind.GALAXY,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )
        materialize_galaxy_embeddings(cs, run=galaxy_run)
        galaxy_run.refresh_from_db()
        if galaxy_run.status != IngestionRunStatus.SUCCESS:
            raise CommandError(galaxy_run.error_detail or f"Galaxy failed for {cs}")
        self.stdout.write(self.style.SUCCESS(f"{cs}: galaxy {galaxy_run.id} succeeded"))
