from datetime import date

from django.core.management.base import BaseCommand, CommandError

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

    def handle(self, *args, **options) -> None:
        ingestion_options = WhoScoredIngestionOptions(
            last_completed=options["last_completed"], match_id=options["match_id"], limit=options["limit"],
            from_date=options["from_date"], to_date=options["to_date"], force=options["force"],
            dry_run=options["dry_run"], allow_over_cap=options["allow_over_cap"],
        )
        try:
            validate_ingestion_options(ingestion_options)
            competition_season = resolve_whoscored_competition_season(options["competition"], options["season"])
            result = run_whoscored_ingestion(competition_season=competition_season, options=ingestion_options)
        except ValueError as error:
            raise CommandError(str(error)) from error
        except Exception as error:
            raise CommandError(f"WhoScored ingestion failed: {error}") from error
        if result.run and result.run.status != "success":
            raise CommandError(result.run.error_detail or "WhoScored ingestion completed with failures.")
        description = "Dry run" if ingestion_options.dry_run else f"WhoScored run {result.run.id}"
        self.stdout.write(self.style.SUCCESS(f"{description} complete: {result.stats}"))
