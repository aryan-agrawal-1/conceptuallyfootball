from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.utils import timezone

from ingestion.models import IngestionLease


@dataclass(frozen=True)
class LeaseHandle:
    key: str
    owner_token: str


def acquire_lease(
    key: str,
    *,
    ttl: timedelta,
    now=None,
) -> LeaseHandle | None:
    current = now or timezone.now()
    owner_token = uuid4().hex
    expires_at = current + ttl
    try:
        with transaction.atomic():
            lease = IngestionLease.objects.select_for_update().filter(key=key).first()
            if lease is None:
                IngestionLease.objects.create(
                    key=key,
                    owner_token=owner_token,
                    expires_at=expires_at,
                )
                return LeaseHandle(key, owner_token)
            if lease.expires_at > current:
                return None
            lease.owner_token = owner_token
            lease.expires_at = expires_at
            lease.save(update_fields=["owner_token", "expires_at", "updated_at"])
            return LeaseHandle(key, owner_token)
    except IntegrityError:
        return None


def renew_lease(handle: LeaseHandle, *, ttl: timedelta, now=None) -> bool:
    current = now or timezone.now()
    return bool(
        IngestionLease.objects.filter(
            key=handle.key,
            owner_token=handle.owner_token,
            expires_at__gt=current,
        ).update(expires_at=current + ttl)
    )


def release_lease(handle: LeaseHandle) -> bool:
    deleted, _ = IngestionLease.objects.filter(
        key=handle.key,
        owner_token=handle.owner_token,
    ).delete()
    return bool(deleted)
