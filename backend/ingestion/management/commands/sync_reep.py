from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ingestion.models import IngestionKind, IngestionRun, IngestionRunStatus
from ingestion.services.reep_csv import sync_reep_from_csv_dir
from ingestion.services.reep_sync import sync_reep_from_path


class Command(BaseCommand):
    help = "Import scoped reep identity rows from a local JSON file or official reep CSV directory."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--path",
            type=str,
            default="",
            help="JSON file path (or override STATBALLER_REEP_DATA_PATH)",
        )
        parser.add_argument(
            "--csv-dir",
            type=str,
            default="",
            help="Directory containing people.csv and teams.csv (reep data/ layout)",
        )

    def handle(self, *args, **options) -> None:
        csv_dir = (options["csv_dir"] or getattr(settings, "STATBALLER_REEP_CSV_DIR", "") or "").strip()
        raw = (options["path"] or settings.STATBALLER_REEP_DATA_PATH or "").strip()

        run = IngestionRun.objects.create(
            kind=IngestionKind.REEP_SYNC,
            competition_season=None,
            status=IngestionRunStatus.RUNNING,
            started_at=timezone.now(),
        )
        try:
            if csv_dir:
                stats = sync_reep_from_csv_dir(Path(csv_dir).expanduser())
            elif raw:
                path = Path(raw).expanduser()
                if not path.is_file():
                    raise CommandError(f"reep file not found: {path}")
                stats = sync_reep_from_path(path)
            else:
                raise CommandError(
                    "Provide --csv-dir (people.csv + teams.csv), --path file.json, "
                    "STATBALLER_REEP_CSV_DIR, or STATBALLER_REEP_DATA_PATH"
                )
        except Exception as exc:  # noqa: BLE001
            run.status = IngestionRunStatus.FAILED
            run.error_detail = str(exc)[:8000]
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "error_detail", "finished_at"])
            raise CommandError(str(exc)) from exc

        run.status = IngestionRunStatus.SUCCESS
        run.stats = stats
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "stats", "finished_at"])
        self.stdout.write(self.style.SUCCESS(f"reep sync ok: {stats}"))
