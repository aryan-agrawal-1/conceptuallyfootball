from __future__ import annotations

import json

from django.test import TestCase

from ingestion.api_cache import get_or_build_payload_response
from ingestion.models import MaterializedApiPayload


class ApiCacheTests(TestCase):
    def test_payload_response_uses_rendered_cache(self):
        MaterializedApiPayload.objects.create(
            cache_key="cache-key",
            source_version="v1",
            payload={"stale": True},
            payload_json='{"ok":true}',
            payload_etag='"etag"',
        )

        response, cached = get_or_build_payload_response(
            cache_key="cache-key",
            source_version="v1",
            builder=lambda: {"ok": False},
        )

        self.assertTrue(cached)
        self.assertEqual(json.loads(response.content), {"ok": True})
        self.assertEqual(response["ETag"], '"etag"')

    def test_payload_response_backfills_legacy_rendered_cache(self):
        row = MaterializedApiPayload.objects.create(
            cache_key="legacy-cache-key",
            source_version="v1",
            payload={"ok": True},
        )

        response, cached = get_or_build_payload_response(
            cache_key="legacy-cache-key",
            source_version="v1",
            builder=lambda: {"ok": False},
        )

        self.assertTrue(cached)
        self.assertEqual(json.loads(response.content), {"ok": True})
        row.refresh_from_db()
        self.assertTrue(row.payload_json)
        self.assertTrue(row.payload_etag)
