from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection


MODEL_NAMES = (
    "ProviderMatch",
    "ProviderMatchPayload",
    "ProviderMatchEvent",
    "ProviderMatchCarry",
    "ProviderMatchGameState",
    "ProviderMatchPlayedPeriod",
    "ProviderMatchTeamGameStateEpisode",
    "ProviderMatchTeamGameStateExposure",
    "ProviderMatchPlayerParticipationBuild",
    "ProviderMatchPlayerParticipation",
    "ProviderMatchPlayerInterval",
    "ProviderMatchPlayerStateExposure",
    "ProviderMatchPossessionBuild",
    "ProviderMatchPossession",
    "ProviderMatchPossessionEvent",
    "ProviderMatchPossessionParticipant",
    "PlayerSeasonEventProfile",
    "PlayerSeasonRoleFeatureSnapshot",
    "PlayerSeasonRole",
)


def update_digest(digest, value) -> None:
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        digest.update(b"bytes:")
        digest.update(str(len(value)).encode())
        digest.update(b":")
        digest.update(value)
    else:
        digest.update(
            json.dumps(
                value,
                default=str,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        )
    digest.update(b"\x1f")


def model_manifest(model) -> dict[str, Any]:
    fields = [field.attname for field in model._meta.concrete_fields]
    digest = hashlib.sha256()
    count = 0
    rows = model.objects.order_by(model._meta.pk.attname).values_list(*fields)
    for row in rows.iterator(chunk_size=1000):
        for value in row:
            update_digest(digest, value)
        digest.update(b"\n")
        count += 1
    return {
        "count": count,
        "sha256": digest.hexdigest(),
    }


class Command(BaseCommand):
    help = "Print exact row counts and stable hashes for persisted WhoScored data."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--output",
            type=Path,
            help="Optional path for the JSON report; stdout is always written.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        tables = {
            model_name: model_manifest(apps.get_model("ingestion", model_name))
            for model_name in MODEL_NAMES
        }
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT name
                FROM django_migrations
                WHERE app = 'ingestion'
                ORDER BY name
                """
            )
            applied_migrations = [row[0] for row in cursor.fetchall()]

        report = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "database_vendor": connection.vendor,
            "applied_ingestion_migrations": applied_migrations,
            "tables": tables,
        }
        rendered = json.dumps(report, indent=2, sort_keys=True)
        if options["output"]:
            output_path: Path = options["output"]
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered + "\n", encoding="utf-8")
        self.stdout.write(rendered)
