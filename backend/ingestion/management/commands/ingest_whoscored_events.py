from datetime import date

from django.core.management.base import BaseCommand, CommandError

from ingestion.services.whoscored_client import safe_failure_evidence
from ingestion.services.whoscored_ingestion import (
    WhoScoredIngestionOptions,
    resolve_whoscored_competition_season,
    run_whoscored_ingestion,
    validate_ingestion_options,
)


class Command(BaseCommand):
    help = "Discover, fetch, validate, normalize, and map bounded WhoScored match events."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--competition", required=True)
        parser.add_argument("--season", required=True)
        parser.add_argument("--last-completed", type=int)
        parser.add_argument("--match-id", type=int)
        parser.add_argument("--limit", type=int)
        parser.add_argument("--from-date", type=date.fromisoformat)
        parser.add_argument("--to-date", type=date.fromisoformat)
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--allow-over-cap", "--override-request-cap", dest="allow_over_cap", action="store_true")
        parser.add_argument(
            "--headed-debug",
            action="store_true",
            help=(
                "LOCAL DEBUGGING ONLY: show the browser. VPS, pilot, retry, and "
                "scheduled ingestion are headless by default."
            ),
        )

    def handle(self, *args, **options) -> None:
        ingestion_options = WhoScoredIngestionOptions(
            last_completed=options["last_completed"], match_id=options["match_id"], limit=options["limit"],
            from_date=options["from_date"], to_date=options["to_date"], force=options["force"],
            dry_run=options["dry_run"], allow_over_cap=options["allow_over_cap"],
            headed_debug=options["headed_debug"],
        )
        try:
            validate_ingestion_options(ingestion_options)
            competition_season = resolve_whoscored_competition_season(options["competition"], options["season"])
        except ValueError as error:
            raise CommandError(str(error)) from error

        try:
            result = run_whoscored_ingestion(competition_season=competition_season, options=ingestion_options)
        except Exception as error:
            evidence = safe_failure_evidence(
                error,
                stage="command",
                headless=not ingestion_options.headed_debug,
            )
            raise CommandError(
                "WhoScored ingestion failed: "
                f"category={evidence['category']} stage={evidence['stage']} "
                f"error_type={evidence['error_type']} headless={evidence['headless']}; "
                f"{evidence['message']}"
            ) from error
        if result.run and result.run.status != "success":
            raise CommandError(result.run.error_detail or "WhoScored ingestion completed with failures.")
        description = "Dry run" if ingestion_options.dry_run else f"WhoScored run {result.run.id}"
        self.stdout.write(self.style.SUCCESS(f"{description} complete: {result.stats}"))
