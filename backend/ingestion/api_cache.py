from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.db.models import Max, Model
from django.db.models import TextField
from django.db.models.functions import Cast
from django.http import HttpResponse
from django.http import HttpRequest

from ingestion.models import MaterializedApiPayload


def canonical_query_params(
    request: HttpRequest,
    *,
    include: Iterable[str] | None = None,
    exclude: Iterable[str] = (),
) -> str:
    included = set(include) if include is not None else None
    excluded = set(exclude)
    pairs: list[tuple[str, str]] = []
    for key in sorted(request.GET.keys()):
        if key in excluded or (included is not None and key not in included):
            continue
        for value in sorted(request.GET.getlist(key)):
            pairs.append((key, value))
    return json.dumps(pairs, separators=(",", ":"), ensure_ascii=True)


def stable_cache_key(namespace: str, parts: Mapping[str, Any]) -> str:
    raw = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"


def model_version(model: type[Model], filters: Mapping[str, Any] | None = None) -> str:
    queryset = model.objects.all()
    if filters:
        queryset = queryset.filter(**filters)
    agg = queryset.aggregate(max_id=Max("id"))
    return str(agg["max_id"] or 0)


def joined_version(*parts: Any) -> str:
    return "|".join(str(part) for part in parts)


def render_payload_json(payload: dict) -> str:
    return json.dumps(
        payload,
        cls=DjangoJSONEncoder,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def payload_etag(rendered: str) -> str:
    return f'"{hashlib.sha256(rendered.encode("utf-8")).hexdigest()}"'


def json_payload_response(rendered: str, etag: str = "") -> HttpResponse:
    response = HttpResponse(rendered, content_type="application/json")
    if etag:
        response["ETag"] = etag
    return response


def get_or_build_payload(
    *,
    cache_key: str,
    source_version: str,
    builder: Callable[[], dict],
) -> tuple[dict, bool]:
    cached = MaterializedApiPayload.objects.filter(
        cache_key=cache_key,
        source_version=source_version,
    ).first()
    if cached is not None:
        return cached.payload, True

    payload = builder()
    rendered = render_payload_json(payload)
    etag = payload_etag(rendered)
    try:
        with transaction.atomic():
            MaterializedApiPayload.objects.update_or_create(
                cache_key=cache_key,
                defaults={
                    "source_version": source_version,
                    "payload": payload,
                    "payload_json": rendered,
                    "payload_etag": etag,
                },
            )
    except IntegrityError:
        MaterializedApiPayload.objects.filter(cache_key=cache_key).update(
            source_version=source_version,
            payload=payload,
            payload_json=rendered,
            payload_etag=etag,
        )
    return payload, False


def get_or_build_payload_response(
    *,
    cache_key: str,
    source_version: str,
    builder: Callable[[], dict],
) -> tuple[HttpResponse, bool]:
    cached = (
        MaterializedApiPayload.objects.filter(
            cache_key=cache_key,
            source_version=source_version,
        )
        .values("id", "payload_json", "payload_etag")
        .first()
    )
    if cached is not None:
        rendered = cached["payload_json"]
        etag = cached["payload_etag"]
        updates = {}
        if not rendered:
            rendered = (
                MaterializedApiPayload.objects.filter(pk=cached["id"])
                .annotate(payload_text=Cast("payload", TextField()))
                .values_list("payload_text", flat=True)
                .first()
                or "{}"
            )
            updates["payload_json"] = rendered
        if not etag:
            etag = payload_etag(rendered)
            updates["payload_etag"] = etag
        if updates:
            MaterializedApiPayload.objects.filter(pk=cached["id"]).update(**updates)
        return json_payload_response(rendered, etag), True

    payload = builder()
    rendered = render_payload_json(payload)
    etag = payload_etag(rendered)
    try:
        with transaction.atomic():
            MaterializedApiPayload.objects.update_or_create(
                cache_key=cache_key,
                defaults={
                    "source_version": source_version,
                    "payload": payload,
                    "payload_json": rendered,
                    "payload_etag": etag,
                },
            )
    except IntegrityError:
        MaterializedApiPayload.objects.filter(cache_key=cache_key).update(
            source_version=source_version,
            payload=payload,
            payload_json=rendered,
            payload_etag=etag,
        )
    return json_payload_response(rendered, etag), False


def invalidate_materialized_api_payloads() -> int:
    deleted, _ = MaterializedApiPayload.objects.all().delete()
    return deleted
