from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Print a reproducible database/table/index storage baseline as JSON."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--output",
            type=Path,
            help="Optional path for the report; stdout is always written.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if connection.vendor != "postgresql":
            raise CommandError(
                "Storage baseline requires PostgreSQL pg_* size functions; "
                f"active vendor is {connection.vendor!r}."
            )

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_database(), pg_database_size(current_database())"
            )
            database_name, database_size = cursor.fetchone()
            cursor.execute(
                """
                SELECT
                    relname,
                    pg_total_relation_size(relid) AS total_bytes,
                    pg_relation_size(relid) AS table_bytes,
                    pg_indexes_size(relid) AS index_bytes,
                    n_live_tup
                FROM pg_stat_user_tables
                ORDER BY total_bytes DESC, relname
                """
            )
            relations = [
                {
                    "relation": relation,
                    "total_bytes": total_bytes,
                    "table_bytes": table_bytes,
                    "index_bytes": index_bytes,
                    "estimated_live_rows": estimated_live_rows,
                }
                for (
                    relation,
                    total_bytes,
                    table_bytes,
                    index_bytes,
                    estimated_live_rows,
                ) in cursor.fetchall()
            ]

        report = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "vendor": connection.vendor,
            "database": database_name,
            "database_size_bytes": database_size,
            "user_relations_total_bytes": sum(row["total_bytes"] for row in relations),
            "user_relations_table_bytes": sum(row["table_bytes"] for row in relations),
            "user_relations_index_bytes": sum(row["index_bytes"] for row in relations),
            "relation_count": len(relations),
            "relations": relations,
        }
        rendered = json.dumps(report, indent=2, sort_keys=True)
        if options["output"]:
            output_path: Path = options["output"]
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered + "\n", encoding="utf-8")
        self.stdout.write(rendered)
