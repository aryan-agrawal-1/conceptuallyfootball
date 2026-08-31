from __future__ import annotations

"""Narrow source adapter around soccerdata's browser-backed WhoScored reader.

soccerdata 1.9's ``read_events(output_fmt="raw")`` returns only the events
array. The complete matchCentreData object is written to its cache. This
adapter deliberately asks soccerdata to populate that cache and then reads the
complete JSON object so callers cannot accidentally persist a partial payload.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Callable, Mapping, Protocol, Sequence


SHOT_EVENT_NAMES = frozenset({"Goal", "MissedShots", "SavedShot", "ShotOnPost"})
COORDINATE_FIELDS = (
    "x",
    "y",
    "endX",
    "endY",
    "goalMouthY",
    "goalMouthZ",
    "blockedX",
    "blockedY",
)


@dataclass(frozen=True)
class WhoScoredSourceConfig:
    league: str
    season: str
    data_dir: Path | None = None
    # VPS, pilot, retry, and scheduled acquisition all use this default. A
    # visible browser is only an explicit local debugging aid.
    headless: bool = True


FAILURE_MESSAGES = {
    "anti_bot_challenge": "The provider returned an access-control or anti-bot response.",
    "navigation_failure": "The browser could not complete provider navigation.",
    "payload_extraction_failure": "The browser response could not be extracted as a complete match payload.",
    "parser_failure": "The provider response could not be parsed.",
    "source_change": "The provider payload no longer satisfies the expected source contract.",
    "configuration_failure": "The WhoScored acquisition environment or configuration is invalid.",
}


def safe_failure_evidence(
    error: Exception,
    *,
    stage: str,
    headless: bool,
) -> dict[str, Any]:
    """Classify a failure without retaining source bodies, URLs, or browser state.

    Exception strings from browsers can contain page HTML, request URLs,
    headers, profiles, or filesystem paths. Operational evidence therefore
    stores only allowlisted metadata and a category-specific message.
    """
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and len(chain) < 5:
        chain.append(current)
        current = current.__cause__ or current.__context__
    error_types = [type(item).__name__ for item in chain]
    combined = " ".join(str(item).lower() for item in chain)

    access_markers = (
        "403", "429", "access denied", "access failure", "anti-bot", "blocked", "captcha",
        "challenge", "cloudflare", "forbidden", "too many requests",
    )
    source_markers = (
        "coordinate", "drift", "missing required", "normalization",
        "schema", "unknown event", "unknown qualifier", "validation",
    )
    extraction_markers = (
        "cache", "data endpoint", "empty response", "events list",
        "full payload", "match payload", "no events", "not an object",
    )
    parser_types = {"JSONDecodeError", "ParserError", "DecodeError"}
    navigation_types = {
        "ConnectionError", "MaxRetryError", "NoSuchWindowException",
        "TimeoutError", "TimeoutException", "WebDriverException",
    }

    if any(marker in combined for marker in access_markers):
        category = "anti_bot_challenge"
    elif any("Normalization" in error_type for error_type in error_types) or any(
        marker in combined for marker in source_markers
    ):
        category = "source_change"
    elif parser_types.intersection(error_types) or "json" in combined or "parse" in combined:
        category = "parser_failure"
    elif isinstance(error, FileNotFoundError) or any(
        marker in combined for marker in extraction_markers
    ):
        category = "payload_extraction_failure"
    elif navigation_types.intersection(error_types) or stage in {"schedule_navigation", "match_navigation"}:
        category = "navigation_failure"
    else:
        category = "configuration_failure" if stage == "configuration" else "source_change"

    return {
        "category": category,
        "stage": stage,
        "error_type": error_types[0],
        "cause_type": error_types[-1],
        "message": FAILURE_MESSAGES[category],
        "headless": headless,
    }


@dataclass(frozen=True)
class SourceMatch:
    match_id: int
    kickoff_at: datetime | None
    status: str
    home_team_id: int | None
    away_team_id: int | None
    home_team_name: str
    away_team_name: str
    home_score: int | None
    away_score: int | None
    source_league: str
    source_season: str
    source_updated_at: datetime | None = None


@dataclass(frozen=True)
class RetrievedMatchPayload:
    match_id: int
    payload: Mapping[str, Any]
    canonical_bytes: bytes
    sha256: str
    cache_path: Path


class WhoScoredProviderClient(Protocol):
    def list_matches(self, *, force_cache: bool = False) -> list[SourceMatch]: ...

    def fetch_match_payload(
        self,
        match_id: int,
        *,
        force: bool = False,
    ) -> RetrievedMatchPayload: ...


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    """Return stable UTF-8 bytes for hashing and compressed persistence."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def payload_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _display_name(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("displayName") or "")
    return str(value or "")


def coordinate_range_errors(payload: Mapping[str, Any]) -> list[str]:
    """Describe every event coordinate outside WhoScored's 0..100 range."""
    errors: list[str] = []
    for index, event in enumerate(payload.get("events") or []):
        if not isinstance(event, Mapping):
            errors.append(f"events[{index}] is not an object")
            continue
        for field in COORDINATE_FIELDS:
            value = event.get(field)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(f"events[{index}].{field} is not numeric")
            elif not 0 <= float(value) <= 100:
                errors.append(f"events[{index}].{field}={value!r} is outside 0..100")
    return errors


def shot_orientation_summary(
    payload: Mapping[str, Any],
    *,
    minimum_shots: int = 3,
    minimum_median_x: float = 50.0,
) -> list[dict[str, Any]]:
    """Summarize the acting-team-attacks-to-x=100 assumption.

    A team is only assessed when enough shots are present. The deliberately
    conservative median threshold catches reversed coordinates without making
    the foundation probe a tactical shot-location model.
    """
    by_team: dict[str, list[float]] = {}
    for event in payload.get("events") or []:
        if not isinstance(event, Mapping):
            continue
        if _display_name(event.get("type")) not in SHOT_EVENT_NAMES:
            continue
        team_id = event.get("teamId")
        x = event.get("x")
        if team_id is None or isinstance(x, bool) or not isinstance(x, (int, float)):
            continue
        by_team.setdefault(str(team_id), []).append(float(x))

    rows = []
    for team_id, xs in sorted(by_team.items()):
        shot_median = median(xs)
        assessed = len(xs) >= minimum_shots
        rows.append(
            {
                "team_id": team_id,
                "shot_count": len(xs),
                "median_x": shot_median,
                "assessed": assessed,
                "attacks_toward_x100": None if not assessed else shot_median >= minimum_median_x,
            }
        )
    return rows


def summarize_match_payload(match_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build a safe probe report; no raw event or player data is returned."""
    event_counts: dict[str, int] = {}
    missing_player_id_count = 0
    for event in payload.get("events") or []:
        if not isinstance(event, Mapping):
            continue
        name = _display_name(event.get("type")) or "Unknown"
        event_counts[name] = event_counts.get(name, 0) + 1
        if event.get("playerId") is None:
            missing_player_id_count += 1

    coordinate_errors = coordinate_range_errors(payload)
    return {
        "match_id": match_id,
        "event_count": sum(event_counts.values()),
        "event_type_counts": dict(sorted(event_counts.items())),
        "missing_player_id_count": missing_player_id_count,
        "coordinate_error_count": len(coordinate_errors),
        "coordinate_errors": coordinate_errors[:10],
        "shot_orientation": shot_orientation_summary(payload),
        "payload_sha256": payload_sha256(payload),
        "canonical_size_bytes": len(canonical_json_bytes(payload)),
    }


def shot_orientation_gate(
    reports: Sequence[Mapping[str, Any]],
    *,
    minimum_assessed_team_sides: int = 2,
) -> dict[str, Any]:
    """Evaluate whether a probe sample meaningfully confirms source orientation."""
    rows = [
        row
        for report in reports
        for row in report.get("shot_orientation", [])
        if isinstance(row, Mapping)
    ]
    assessed = [row for row in rows if row.get("assessed") is True]
    failed = [
        row for row in assessed if row.get("attacks_toward_x100") is not True
    ]
    return {
        "passed": len(assessed) >= minimum_assessed_team_sides and not failed,
        "minimum_assessed_team_sides": minimum_assessed_team_sides,
        "assessed_team_sides": len(assessed),
        "failed_team_sides": len(failed),
    }


def _default_data_dir() -> Path:
    # soccerdata binds its logging/cache paths at import time. Set and create
    # them before the lazy import below, including when used outside manage.py.
    project_backend = Path(__file__).resolve().parents[2]
    soccerdata_home = Path(os.environ.get("SOCCERDATA_DIR", project_backend / ".soccerdata"))
    os.environ.setdefault("SOCCERDATA_DIR", str(soccerdata_home))
    (soccerdata_home / "logs").mkdir(parents=True, exist_ok=True)
    return soccerdata_home / "data" / "WhoScored"


def _validated_json_document(url: str, body_text: Any) -> str:
    """Return a JSON endpoint body after verifying its response shape.

    Recent Chrome versions expose WhoScored's ``/data/`` response inside an
    HTML document. soccerdata 1.9 serializes that wrapper and subsequently
    passes it to ``json.load``. Keep the compatibility workaround local to the
    exact endpoint and fail closed if WhoScored returns a challenge/error page.
    """
    if "/data/" not in url:
        raise ValueError("JSON document extraction is only valid for WhoScored data endpoints.")
    if not isinstance(body_text, str) or not body_text.strip():
        raise ValueError("WhoScored data endpoint returned an empty response.")
    parsed = json.loads(body_text)
    if not isinstance(parsed, Mapping):
        raise ValueError("WhoScored data endpoint did not return a JSON object.")
    return body_text


class CachedScheduleMixin:
    """Reuse one immutable schedule frame for the lifetime of a source reader."""

    cached_schedule = None

    def read_schedule(self, force_cache: bool = False):
        if self.cached_schedule is None:
            self.cached_schedule = super().read_schedule(force_cache=force_cache)
        return self.cached_schedule


class SoccerdataWhoScoredClient:
    def __init__(
        self,
        config: WhoScoredSourceConfig,
        *,
        reader_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config
        self.data_dir = Path(config.data_dir) if config.data_dir else _default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._reader_factory = reader_factory
        self._reader: Any | None = None
        self._matches: dict[int, SourceMatch] = {}

    @property
    def reader(self) -> Any:
        if self._reader is None:
            factory = self._reader_factory
            if factory is None:
                from soccerdata import WhoScored

                class CompatibleWhoScored(CachedScheduleMixin, WhoScored):
                    @classmethod
                    def _all_leagues(cls) -> dict[str, str]:
                        # soccerdata keys its built-in league map by the reader
                        # class name, so a compatibility subclass must delegate.
                        return WhoScored._all_leagues()

                    def _validate_page(self, url: str) -> str:
                        if "/data/" in url:
                            body_text = self._driver.execute_script(
                                "return document.body.innerText"
                            )
                            return _validated_json_document(url, body_text)
                        return super()._validate_page(url)

                factory = CompatibleWhoScored
            reader = factory(
                leagues=self.config.league,
                seasons=self.config.season,
                data_dir=self.data_dir,
                no_store=False,
                headless=self.config.headless,
            )
            # soccerdata logs WebDriver startup failures and returns a reader
            # without ``_driver``. Failing here prevents a production command
            # from appearing healthy merely because stale schedule/payload
            # cache files remain readable after browser startup failed.
            if getattr(reader, "_driver", None) is None:
                raise RuntimeError("WhoScored browser failed to initialize.")
            self._reader = reader
        return self._reader

    def list_matches(self, *, force_cache: bool = False) -> list[SourceMatch]:
        frame = self.reader.read_schedule(force_cache=force_cache)
        if hasattr(frame, "reset_index"):
            rows: Sequence[Mapping[str, Any]] = frame.reset_index().to_dict("records")
        elif isinstance(frame, Sequence):
            rows = frame
        else:
            raise TypeError("WhoScored schedule must be a dataframe or sequence of objects.")

        matches = [_normalize_schedule_row(row, self.config) for row in rows]
        self._matches = {match.match_id: match for match in matches}
        return sorted(
            matches,
            key=lambda match: (
                match.kickoff_at or datetime.min.replace(tzinfo=timezone.utc),
                match.match_id,
            ),
        )

    def fetch_match_payload(
        self,
        match_id: int,
        *,
        force: bool = False,
    ) -> RetrievedMatchPayload:
        match_id = int(match_id)
        if match_id <= 0:
            raise ValueError("WhoScored match_id must be a positive integer.")
        if match_id not in self._matches:
            self.list_matches(force_cache=not force)
        if match_id not in self._matches:
            raise ValueError(f"Match {match_id} is not present in the configured schedule.")

        # output_fmt=None avoids holding/returning the misleading events-only
        # "raw" result. no_store=False above guarantees a full cache file.
        self.reader.read_events(
            match_id=match_id,
            # Schedule discovery has already happened above. Keep soccerdata
            # on that schedule snapshot so a forced event refetch does not
            # re-scrape the league calendar once per match.
            force_cache=True,
            live=force,
            output_fmt=None,
            retry_missing=True,
            on_error="raise",
        )
        cache_path = self._cache_path(self._matches[match_id])
        with cache_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, Mapping):
            raise ValueError(f"Cached WhoScored match {match_id} payload is not an object.")
        if not isinstance(payload.get("events"), list):
            raise ValueError(f"Cached WhoScored match {match_id} payload has no events list.")

        canonical = canonical_json_bytes(payload)
        return RetrievedMatchPayload(
            match_id=match_id,
            payload=payload,
            canonical_bytes=canonical,
            sha256=hashlib.sha256(canonical).hexdigest(),
            cache_path=cache_path,
        )

    def _cache_path(self, match: SourceMatch) -> Path:
        preferred = self.data_dir / (
            f"events/{match.source_league}_{match.source_season}/{match.match_id}.json"
        )
        if preferred.is_file():
            return preferred
        candidates = list((self.data_dir / "events").glob(f"*/*/{match.match_id}.json"))
        if not candidates:
            candidates = list((self.data_dir / "events").glob(f"*/{match.match_id}.json"))
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise FileNotFoundError(
                f"soccerdata did not store the full payload for match {match.match_id}."
            )
        raise RuntimeError(
            f"Multiple soccerdata cache files found for match {match.match_id}; "
            "league/season cache identity is ambiguous."
        )


def _normalize_schedule_row(
    row: Mapping[str, Any],
    config: WhoScoredSourceConfig,
) -> SourceMatch:
    match_id = _optional_int(row.get("game_id", row.get("id")))
    if match_id is None or match_id <= 0:
        raise ValueError("WhoScored schedule row has no valid game_id.")
    kickoff_at = _optional_datetime(row.get("date", row.get("start_time_utc")))
    home_score, away_score = _scores(row)
    return SourceMatch(
        match_id=match_id,
        kickoff_at=kickoff_at,
        status=_status(row, home_score, away_score),
        home_team_id=_optional_int(row.get("home_team_id", row.get("homeTeamId"))),
        away_team_id=_optional_int(row.get("away_team_id", row.get("awayTeamId"))),
        home_team_name=str(row.get("home_team", row.get("homeTeamName")) or ""),
        away_team_name=str(row.get("away_team", row.get("awayTeamName")) or ""),
        home_score=home_score,
        away_score=away_score,
        source_league=str(row.get("league") or config.league),
        source_season=str(row.get("season") or config.season),
        source_updated_at=_optional_datetime(
            row.get("source_updated_at", row.get("updated_at", row.get("lastUpdated")))
        ),
    )


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _optional_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _scores(row: Mapping[str, Any]) -> tuple[int | None, int | None]:
    home_score = _optional_int(row.get("home_score"))
    away_score = _optional_int(row.get("away_score"))
    scores = row.get("scores")
    if isinstance(scores, Sequence) and not isinstance(scores, (str, bytes)) and len(scores) >= 2:
        home_score = home_score if home_score is not None else _optional_int(scores[0])
        away_score = away_score if away_score is not None else _optional_int(scores[1])
    return home_score, away_score


def _status(
    row: Mapping[str, Any],
    home_score: int | None,
    away_score: int | None,
) -> str:
    raw = str(row.get("status_code", row.get("status", "")) or "").strip().lower()
    if bool(row.get("is_result")) or raw in {"ft", "aet", "pen", "finished", "completed"}:
        return "completed"
    if raw in {"live", "ht", "1h", "2h", "inprogress", "in progress"}:
        return "live"
    if raw in {"postponed", "cancelled", "canceled", "abandoned"}:
        return "postponed"
    if raw in {"scheduled", "fixture", "notstarted", "not started"}:
        return "scheduled"
    if home_score is not None and away_score is not None:
        return "completed"
    return "unknown"
