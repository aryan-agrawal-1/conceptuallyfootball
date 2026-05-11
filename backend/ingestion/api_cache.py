from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Max, Model
from django.http import HttpRequest

from ingestion.models import MaterializedApiPayload


def canonical_query_params(request: HttpRequest, *, exclude: Iterable[str] = ()) -> str:
    excluded = set(exclude)
    pairs: list[tuple[str, str]] = []
    for key in sorted(request.GET.keys()):
        if key in excluded:
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
    try:
        with transaction.atomic():
            MaterializedApiPayload.objects.update_or_create(
                cache_key=cache_key,
                defaults={
                    "source_version": source_version,
                    "payload": payload,
                },
            )
    except IntegrityError:
        MaterializedApiPayload.objects.filter(cache_key=cache_key).update(
            source_version=source_version,
            payload=payload,
        )
    return payload, False
