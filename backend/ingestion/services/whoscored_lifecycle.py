from __future__ import annotations

import gzip
import hashlib
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone as datetime_timezone
from typing import Callable, Iterable, Mapping

from django.db import transaction
from django.utils import timezone

from ingestion.models import (
    CompetitionSeason,
    IngestionRun,
    Provider,
    ProviderMatch,
    ProviderMatchPayload,
    ProviderMatchStatus,
    ProviderPayloadLifecycle,
    ProviderPayloadStorage,
    ProviderTeamMapping,
)
from ingestion.services.whoscored_client import (
    RetrievedMatchPayload,
    SourceMatch,
    WhoScoredProviderClient,
)
from ingestion.services.whoscored_normalization import (
    RAW_PAYLOAD_SCHEMA_VERSION,
    NormalizationPolicy,
    NormalizedMatch,
    canonical_raw_payload_bytes,
    parse_match_payload,
    replace_match_events,
)


ACCESS_FAILURE_MARKERS = (
    "403",
    "429",
    "access denied",
    "anti-bot",
    "blocked",
    "captcha",
    "cloudflare",
    "forbidden",
    "too many requests",
)


class WhoScoredAccessCutoffError(RuntimeError):
    """Raised after the configured number of consecutive source access failures."""


@dataclass(frozen=True)
class WhoScoredFetchPolicy:
    settlement_delay: timedelta = timedelta(hours=12)
    maximum_attempts: int = 4
    minimum_match_delay_seconds: float = 5.0
    maximum_match_delay_seconds: float = 10.0
    retry_base_delay_seconds: float = 5.0
    access_failure_limit: int = 5

    def __post_init__(self) -> None:
        if self.maximum_attempts < 1:
            raise ValueError("maximum_attempts must include at least one request.")
        if self.minimum_match_delay_seconds < 0:
            raise ValueError("minimum_match_delay_seconds cannot be negative.")
        if self.maximum_match_delay_seconds < self.minimum_match_delay_seconds:
            raise ValueError(
                "maximum_match_delay_seconds cannot be below minimum_match_delay_seconds."
            )
        if self.retry_base_delay_seconds < 0:
            raise ValueError("retry_base_delay_seconds cannot be negative.")
        if self.access_failure_limit < 1:
            raise ValueError("access_failure_limit must be positive.")


@dataclass
class WhoScoredRequestStats:
    requests: int = 0
    retries: int = 0
    access_failures: int = 0
    consecutive_access_failures: int = 0


class WhoScoredRequestController:
    """Serialize browser requests and apply pacing, retries, and the access cutoff."""

    def __init__(
        self,
        *,
        policy: WhoScoredFetchPolicy | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        random_uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.policy = policy or WhoScoredFetchPolicy()
        self.sleeper = sleeper
        self.random_uniform = random_uniform
        self.stats = WhoScoredRequestStats()
        self.last_match_id: int | None = None
        self.stopped = False

    def fetch(
        self,
        client: WhoScoredProviderClient,
        match_id: int,
        *,
        force: bool,
    ) -> RetrievedMatchPayload:
        if self.stopped:
            raise WhoScoredAccessCutoffError(
                "WhoScored requests are stopped after consecutive access failures."
            )

        match_id = int(match_id)
        if self.last_match_id is not None and self.last_match_id != match_id:
            self.sleeper(
                self.random_uniform(
                    self.policy.minimum_match_delay_seconds,
                    self.policy.maximum_match_delay_seconds,
                )
            )
        self.last_match_id = match_id

        for attempt in range(self.policy.maximum_attempts):
            self.stats.requests += 1
            try:
                result = client.fetch_match_payload(match_id, force=force)
            except Exception as error:
                access_failure = is_access_failure(error)
                if access_failure:
                    self.stats.access_failures += 1
                    self.stats.consecutive_access_failures += 1
                    if (
                        self.stats.consecutive_access_failures
                        >= self.policy.access_failure_limit
                    ):
                        self.stopped = True
                        raise WhoScoredAccessCutoffError(
                            "WhoScored access failure cutoff reached."
                        ) from error

                retryable = access_failure or is_transient_failure(error)
                if not retryable or attempt + 1 >= self.policy.maximum_attempts:
                    raise
                self.stats.retries += 1
                self.sleeper(self.policy.retry_base_delay_seconds * (attempt + 1))
                continue

            self.stats.consecutive_access_failures = 0
            return result

        raise RuntimeError("WhoScored request loop exited without a result.")


@dataclass(frozen=True)
class WhoScoredMatchResult:
    provider_match_id: str
    action: str
    lifecycle_state: str
    payload_sha256: str | None
    normalized_event_count: int
    affected_player_ids: tuple[int, ...] = ()
    affected_team_ids: tuple[int, ...] = ()

    @property
    def fetched(self) -> bool:
        return self.action not in {"reused_final", "awaiting_settlement"}

    @property
    def events_replaced(self) -> bool:
        return self.action in {"stored", "replaced"}


@dataclass(frozen=True)
class WhoScoredMatchFailure:
    provider_match_id: str
    error_type: str
    message: str


@dataclass
class WhoScoredBatchResult:
    matches: list[WhoScoredMatchResult] = field(default_factory=list)
    failures: list[WhoScoredMatchFailure] = field(default_factory=list)


class WhoScoredLifecycleService:
    def __init__(
        self,
        *,
        competition_season: CompetitionSeason,
        client: WhoScoredProviderClient,
        request_controller: WhoScoredRequestController | None = None,
        clock: Callable[[], object] = timezone.now,
        run: IngestionRun | None = None,
        normalization_policy: NormalizationPolicy | None = None,
    ) -> None:
        if not competition_season.supports_whoscored:
            raise ValueError(
                "WhoScored is not configured for this competition season."
            )
        self.competition_season = competition_season
        self.client = client
        self.request_controller = request_controller or WhoScoredRequestController()
        self.clock = clock
        self.run = run
        self.normalization_policy = normalization_policy

    def discover_matches(self, *, force_cache: bool = False) -> list[ProviderMatch]:
        source_matches = self.client.list_matches(force_cache=force_cache)
        return [self.upsert_match(source_match) for source_match in source_matches]

    def upsert_match(self, source_match: SourceMatch) -> ProviderMatch:
        if source_match.kickoff_at is None:
            raise ValueError(
                f"WhoScored match {source_match.match_id} has no kickoff timestamp."
            )
        if source_match.home_team_id is None or source_match.away_team_id is None:
            raise ValueError(
                f"WhoScored match {source_match.match_id} has incomplete team identifiers."
            )

        score_values = (source_match.home_score, source_match.away_score)
        home_score, away_score = score_values
        if (home_score is None) != (away_score is None):
            home_score = None
            away_score = None

        home_provider_team_id = str(source_match.home_team_id)
        away_provider_team_id = str(source_match.away_team_id)
        team_mappings = {
            mapping.provider_team_id: mapping.canonical_team
            for mapping in ProviderTeamMapping.objects.filter(
                provider=Provider.WHOSCORED,
                provider_team_id__in=[
                    home_provider_team_id,
                    away_provider_team_id,
                ],
            ).select_related("canonical_team")
        }
        defaults = {
            "competition_season": self.competition_season,
            "kickoff_at": source_match.kickoff_at,
            "status": normalized_match_status(source_match.status),
            "home_provider_team_id": home_provider_team_id,
            "away_provider_team_id": away_provider_team_id,
            "home_team": team_mappings.get(home_provider_team_id),
            "away_team": team_mappings.get(away_provider_team_id),
            "home_score": home_score,
            "away_score": away_score,
            "source_updated_at": source_match.source_updated_at,
        }
        provider_match, _ = ProviderMatch.objects.update_or_create(
            provider=Provider.WHOSCORED,
            provider_match_id=str(source_match.match_id),
            defaults=defaults,
        )
        return provider_match

    def process_match(
        self,
        provider_match: ProviderMatch,
        *,
        historical: bool,
        force: bool = False,
    ) -> WhoScoredMatchResult:
        if provider_match.provider != Provider.WHOSCORED:
            raise ValueError("WhoScored lifecycle cannot process another provider.")
        if provider_match.competition_season_id != self.competition_season.id:
            raise ValueError("Provider match belongs to another competition season.")
        if provider_match.status != ProviderMatchStatus.COMPLETED:
            raise ValueError("Only completed matches can enter the payload lifecycle.")

        now = self.clock()
        current_payload = ProviderMatchPayload.objects.filter(
            provider_match=provider_match
        ).first()
        if (
            current_payload
            and current_payload.lifecycle_state == ProviderPayloadLifecycle.FINAL
            and not force
        ):
            return lifecycle_result(
                provider_match,
                current_payload,
                action="reused_final",
            )
        if (
            current_payload
            and current_payload.lifecycle_state == ProviderPayloadLifecycle.PRELIMINARY
            and not historical
            and not force
            and current_payload.preliminary_fetched_at
            and now
            < current_payload.preliminary_fetched_at
            + self.request_controller.policy.settlement_delay
        ):
            return lifecycle_result(
                provider_match,
                current_payload,
                action="awaiting_settlement",
            )

        target_lifecycle = (
            ProviderPayloadLifecycle.FINAL
            if historical
            or (
                current_payload
                and current_payload.lifecycle_state
                in {
                    ProviderPayloadLifecycle.PRELIMINARY,
                    ProviderPayloadLifecycle.FINAL,
                }
            )
            else ProviderPayloadLifecycle.PRELIMINARY
        )
        retrieved = self.request_controller.fetch(
            self.client,
            int(provider_match.provider_match_id),
            force=force
            or bool(
                current_payload
                and current_payload.lifecycle_state
                == ProviderPayloadLifecycle.PRELIMINARY
                and target_lifecycle == ProviderPayloadLifecycle.FINAL
            ),
        )
        wrapped_bytes = canonical_raw_payload_bytes(retrieved.payload)
        checksum = hashlib.sha256(wrapped_bytes).hexdigest()
        changed = current_payload is None or current_payload.payload_sha256 != checksum
        normalized_match = None
        if changed:
            normalized_match = parse_match_payload(
                retrieved.payload,
                policy=self.normalization_policy,
                changed_payload=current_payload is not None,
            )

        return self.persist_payload(
            provider_match=provider_match,
            retrieved=retrieved,
            wrapped_bytes=wrapped_bytes,
            checksum=checksum,
            target_lifecycle=target_lifecycle,
            fetched_at=now,
            normalized_match=normalized_match,
        )

    def persist_payload(
        self,
        *,
        provider_match: ProviderMatch,
        retrieved: RetrievedMatchPayload,
        wrapped_bytes: bytes,
        checksum: str,
        target_lifecycle: str,
        fetched_at,
        normalized_match: NormalizedMatch | None,
    ) -> WhoScoredMatchResult:
        with transaction.atomic():
            locked_match = ProviderMatch.objects.select_for_update().get(
                pk=provider_match.pk
            )
            current_payload = (
                ProviderMatchPayload.objects.select_for_update()
                .filter(provider_match=locked_match)
                .first()
            )
            if current_payload and current_payload.payload_sha256 == checksum:
                if (
                    target_lifecycle == ProviderPayloadLifecycle.FINAL
                    and current_payload.lifecycle_state
                    == ProviderPayloadLifecycle.PRELIMINARY
                ):
                    current_payload.lifecycle_state = ProviderPayloadLifecycle.FINAL
                    current_payload.final_sha256 = checksum
                    current_payload.final_fetched_at = fetched_at
                    current_payload.fetched_at = fetched_at
                    current_payload.save(
                        update_fields=[
                            "lifecycle_state",
                            "final_sha256",
                            "final_fetched_at",
                            "fetched_at",
                        ]
                    )
                    return lifecycle_result(
                        locked_match,
                        current_payload,
                        action="finalized_unchanged",
                    )
                return lifecycle_result(
                    locked_match,
                    current_payload,
                    action="unchanged",
                )

            if normalized_match is None:
                raise ValueError("A changed payload requires normalized events.")

            old_player_ids, old_team_ids = affected_entity_ids(locked_match)
            compressed_bytes = gzip.compress(wrapped_bytes, mtime=0)
            preliminary_sha256 = None
            preliminary_fetched_at = None
            if target_lifecycle == ProviderPayloadLifecycle.PRELIMINARY:
                preliminary_sha256 = checksum
                preliminary_fetched_at = fetched_at
            elif current_payload:
                preliminary_sha256 = current_payload.preliminary_sha256
                preliminary_fetched_at = current_payload.preliminary_fetched_at

            payload_values = {
                "storage_backend": ProviderPayloadStorage.DATABASE,
                "payload_gzip": compressed_bytes,
                "object_key": None,
                "payload_sha256": checksum,
                "payload_size_bytes": len(compressed_bytes),
                "uncompressed_size_bytes": len(wrapped_bytes),
                "schema_version": RAW_PAYLOAD_SCHEMA_VERSION,
                "lifecycle_state": target_lifecycle,
                "preliminary_sha256": preliminary_sha256,
                "preliminary_fetched_at": preliminary_fetched_at,
                "final_sha256": (
                    checksum
                    if target_lifecycle == ProviderPayloadLifecycle.FINAL
                    else None
                ),
                "final_fetched_at": (
                    fetched_at
                    if target_lifecycle == ProviderPayloadLifecycle.FINAL
                    else None
                ),
                "source_updated_at": source_updated_at(retrieved.payload)
                or locked_match.source_updated_at,
                "fetched_at": fetched_at,
            }
            if current_payload:
                for field_name, value in payload_values.items():
                    setattr(current_payload, field_name, value)
                current_payload.save(update_fields=list(payload_values))
                stored_payload = current_payload
                action = "replaced"
            else:
                stored_payload = ProviderMatchPayload.objects.create(
                    provider_match=locked_match,
                    **payload_values,
                )
                action = "stored"

            replace_match_events(
                locked_match,
                normalized_match,
                run=self.run,
            )
            new_player_ids, new_team_ids = affected_entity_ids(locked_match)

            return WhoScoredMatchResult(
                provider_match_id=locked_match.provider_match_id,
                action=action,
                lifecycle_state=stored_payload.lifecycle_state,
                payload_sha256=stored_payload.payload_sha256,
                normalized_event_count=len(normalized_match.events),
                affected_player_ids=tuple(
                    sorted(old_player_ids | new_player_ids)
                ),
                affected_team_ids=tuple(sorted(old_team_ids | new_team_ids)),
            )

    def process_matches(
        self,
        provider_matches: Iterable[ProviderMatch],
        *,
        historical: bool,
        force: bool = False,
    ) -> WhoScoredBatchResult:
        result = WhoScoredBatchResult()
        for provider_match in provider_matches:
            try:
                match_result = self.process_match(
                    provider_match,
                    historical=historical,
                    force=force,
                )
            except WhoScoredAccessCutoffError:
                raise
            except Exception as error:
                result.failures.append(
                    WhoScoredMatchFailure(
                        provider_match_id=provider_match.provider_match_id,
                        error_type=type(error).__name__,
                        message=str(error)[:1000],
                    )
                )
                continue
            result.matches.append(match_result)
        return result


def is_access_failure(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in ACCESS_FAILURE_MARKERS)


def is_transient_failure(error: Exception) -> bool:
    if isinstance(error, (ConnectionError, TimeoutError)):
        return True
    message = str(error).lower()
    return any(
        marker in message
        for marker in ("connection", "temporar", "timeout", "502", "503", "504")
    )


def normalized_match_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    allowed = {choice for choice, _ in ProviderMatchStatus.choices}
    return normalized if normalized in allowed else ProviderMatchStatus.UNKNOWN


def source_updated_at(payload: Mapping[str, object]) -> datetime | None:
    for key in ("lastUpdated", "lastUpdatedTime", "lastUpdatedUtc", "updatedAt"):
        value = payload.get(key)
        if not value:
            continue
        if hasattr(value, "tzinfo"):
            parsed = value
        else:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime_timezone.utc)
        return parsed
    return None


def affected_entity_ids(provider_match: ProviderMatch) -> tuple[set[int], set[int]]:
    player_ids = set(
        provider_match.events.exclude(player_id=None).values_list(
            "player_id", flat=True
        )
    )
    team_ids = set(
        provider_match.events.exclude(team_id=None).values_list("team_id", flat=True)
    )
    team_ids.update(
        team_id
        for team_id in (provider_match.home_team_id, provider_match.away_team_id)
        if team_id is not None
    )
    return player_ids, team_ids


def lifecycle_result(
    provider_match: ProviderMatch,
    payload: ProviderMatchPayload,
    *,
    action: str,
) -> WhoScoredMatchResult:
    return WhoScoredMatchResult(
        provider_match_id=provider_match.provider_match_id,
        action=action,
        lifecycle_state=payload.lifecycle_state,
        payload_sha256=payload.payload_sha256,
        normalized_event_count=provider_match.events.count(),
    )
