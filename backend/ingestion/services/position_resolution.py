from __future__ import annotations

import time
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from ingestion.models import (
    CompetitionSeason,
    IngestionRun,
    IngestionRunStatus,
    MergedPlayerSeason,
    PlayerPositionResolution,
    PositionGroup,
    PositionResolutionSource,
    Provider,
    ProviderPlayerMapping,
    ProviderTeamMapping,
    ReepPlayerRow,
    SofascorePlayerSeasonSource,
    SofascoreTeamSeasonSource,
    UnderstatPlayerSeasonSource,
)
from ingestion.position import normalize_position_group
from ingestion.services.sofascore_client import SofascoreSeasonConfig, fetch_player_profile
from ingestion.services.sofascore_team_client import fetch_season_teams, fetch_team_players


@dataclass
class ResolutionCandidate:
    source: str
    raw_position: str
    position_group: str
    confidence: float
    evidence: dict[str, Any]


@dataclass
class PositionResolutionStats:
    scanned_rows: int = 0
    existing_resolution: int = 0
    existing_source: int = 0
    historical_player: int = 0
    sofascore_roster: int = 0
    sofascore_profile: int = 0
    unresolved: int = 0
    written: int = 0
    would_write: int = 0
    affected_competition_season_ids: set[int] = field(default_factory=set)
    unresolved_examples: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scanned_rows": self.scanned_rows,
            "existing_resolution": self.existing_resolution,
            "existing_source": self.existing_source,
            "historical_player": self.historical_player,
            "sofascore_roster": self.sofascore_roster,
            "sofascore_profile": self.sofascore_profile,
            "unresolved": self.unresolved,
            "written": self.written,
            "would_write": self.would_write,
            "affected_competition_season_ids": sorted(self.affected_competition_season_ids),
            "unresolved_examples": self.unresolved_examples[:25],
        }


def resolve_unknown_positions(
    *,
    competition: str | None = None,
    season: str | None = None,
    current_only: bool = True,
    dry_run: bool = False,
    use_roster: bool = True,
    use_profile: bool = True,
    sleep_seconds: float | None = None,
) -> PositionResolutionStats:
    sleep_seconds = (
        float(getattr(settings, "STATBALLER_SOFASCORE_REQUEST_DELAY_SECONDS", 1.5))
        if sleep_seconds is None
        else sleep_seconds
    )
    stats = PositionResolutionStats()
    roster_cache = _RosterCache(sleep_seconds=sleep_seconds)
    seen_keys: set[tuple[int, int]] = set()

    rows = _unknown_rows(competition=competition, season=season, current_only=current_only)
    for row in rows.iterator():
        key = (row.competition_season_id, row.canonical_player_id)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        stats.scanned_rows += 1

        existing = PlayerPositionResolution.objects.filter(
            competition_season=row.competition_season,
            canonical_player=row.canonical_player,
        ).first()
        if existing and existing.position_group != PositionGroup.UNKNOWN:
            stats.existing_resolution += 1
            stats.affected_competition_season_ids.add(row.competition_season_id)
            continue

        candidate = (
            _from_existing_sources(row)
            or _from_historical_player(row)
            or (
                _from_sofascore_roster(row, roster_cache)
                if use_roster
                else None
            )
            or (
                _from_sofascore_profile(row)
                if use_profile
                else None
            )
        )

        if not candidate:
            stats.unresolved += 1
            if len(stats.unresolved_examples) < 25:
                stats.unresolved_examples.append(
                    {
                        "competition": row.competition_season.competition.short_code,
                        "season": row.competition_season.season.label,
                        "player": row.canonical_player.display_name,
                        "team": row.canonical_display_team.name if row.canonical_display_team else "",
                    }
                )
            continue

        _increment_source_stat(stats, candidate.source)
        stats.affected_competition_season_ids.add(row.competition_season_id)
        if dry_run:
            stats.would_write += 1
            continue
        if _write_resolution(row, candidate):
            stats.written += 1

    return stats


def run_position_resolution_job(competition_season: CompetitionSeason, *, run: IngestionRun) -> None:
    run.status = IngestionRunStatus.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])
    try:
        stats = resolve_unknown_positions(
            competition=competition_season.competition.short_code,
            season=competition_season.season.label,
            current_only=True,
        )
    except Exception as exc:  # noqa: BLE001
        run.status = IngestionRunStatus.FAILED
        run.error_detail = str(exc)[:8000]
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_detail", "finished_at"])
        return
    run.status = IngestionRunStatus.SUCCESS
    run.stats = stats.as_dict()
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "stats", "finished_at"])


def _unknown_rows(
    *,
    competition: str | None,
    season: str | None,
    current_only: bool,
):
    rows = (
        MergedPlayerSeason.objects.filter(
            position_group=PositionGroup.UNKNOWN,
            canonical_player__isnull=False,
        )
        .select_related(
            "canonical_player",
            "canonical_display_team",
            "competition_season",
            "competition_season__competition",
            "competition_season__season",
        )
        .order_by(
            "competition_season__season__sort_order",
            "competition_season__competition__short_code",
            "canonical_player_id",
        )
    )
    if current_only:
        rows = rows.filter(is_current=True)
    if competition:
        rows = rows.filter(competition_season__competition__short_code=competition)
    if season:
        rows = rows.filter(competition_season__season__label=season)
    return rows


def _from_existing_sources(row: MergedPlayerSeason) -> ResolutionCandidate | None:
    candidates: list[tuple[str, str, dict[str, Any]]] = []
    ss = SofascorePlayerSeasonSource.objects.filter(
        competition_season=row.competition_season,
        canonical_player=row.canonical_player,
    ).first()
    if ss and ss.position_raw:
        candidates.append(
            (
                ss.position_raw,
                PositionResolutionSource.EXISTING_SOURCE,
                {"source_model": "SofascorePlayerSeasonSource", "provider_player_id": ss.provider_player_id},
            )
        )

    reep_row = (
        ReepPlayerRow.objects.filter(reep_id=row.canonical_player.reep_id).first()
        if row.canonical_player.reep_id
        else None
    )
    if reep_row:
        if reep_row.position_detail:
            candidates.append(
                (
                    reep_row.position_detail,
                    PositionResolutionSource.EXISTING_SOURCE,
                    {"source_model": "ReepPlayerRow", "field": "position_detail"},
                )
            )
        if reep_row.position:
            candidates.append(
                (
                    reep_row.position,
                    PositionResolutionSource.EXISTING_SOURCE,
                    {"source_model": "ReepPlayerRow", "field": "position"},
                )
            )

    us = UnderstatPlayerSeasonSource.objects.filter(
        competition_season=row.competition_season,
        canonical_player=row.canonical_player,
    ).first()
    if us and us.position_raw:
        candidates.append(
            (
                us.position_raw,
                PositionResolutionSource.EXISTING_SOURCE,
                {"source_model": "UnderstatPlayerSeasonSource", "provider_player_id": us.provider_player_id},
            )
        )

    for raw, source, evidence in candidates:
        group = normalize_position_group(raw)
        if group != PositionGroup.UNKNOWN:
            return ResolutionCandidate(source, raw[:64], group, 1.0, evidence)
    return None


def _from_historical_player(row: MergedPlayerSeason) -> ResolutionCandidate | None:
    historical = (
        MergedPlayerSeason.objects.filter(
            canonical_player=row.canonical_player,
            is_current=True,
        )
        .exclude(pk=row.pk)
        .exclude(position_group=PositionGroup.UNKNOWN)
        .select_related("competition_season__competition", "competition_season__season")
        .order_by("-competition_season__season__sort_order", "-minutes", "-id")
        .first()
    )
    if not historical:
        return None
    raw = historical.native_position or historical.position_group
    group = normalize_position_group(raw)
    if group == PositionGroup.UNKNOWN:
        group = historical.position_group
    if group == PositionGroup.UNKNOWN:
        return None
    return ResolutionCandidate(
        PositionResolutionSource.HISTORICAL_PLAYER,
        raw[:64],
        group,
        0.85,
        {
            "source_row_id": historical.id,
            "competition": historical.competition_season.competition.short_code,
            "season": historical.competition_season.season.label,
            "native_position": historical.native_position,
            "position_group": historical.position_group,
        },
    )


class _RosterCache:
    def __init__(self, *, sleep_seconds: float):
        self.sleep_seconds = sleep_seconds
        self.season_teams_by_cs: dict[int, list[dict[str, Any]]] = {}
        self.roster_by_team_id: dict[str, list[dict[str, Any]]] = {}

    def season_teams(self, cs: CompetitionSeason) -> list[dict[str, Any]]:
        if cs.id not in self.season_teams_by_cs:
            cfg = SofascoreSeasonConfig(cs.sofascore_unique_tournament_id, cs.sofascore_season_id)
            self.season_teams_by_cs[cs.id] = fetch_season_teams(cfg)
            self._sleep()
        return self.season_teams_by_cs[cs.id]

    def roster(self, team_id: str | int) -> list[dict[str, Any]]:
        key = str(team_id)
        if key not in self.roster_by_team_id:
            self.roster_by_team_id[key] = fetch_team_players(team_id)
            self._sleep()
        return self.roster_by_team_id[key]

    def _sleep(self) -> None:
        if self.sleep_seconds:
            time.sleep(self.sleep_seconds)


def _from_sofascore_roster(
    row: MergedPlayerSeason,
    roster_cache: _RosterCache,
) -> ResolutionCandidate | None:
    if not row.competition_season.supports_sofascore or not row.canonical_display_team:
        return None
    team_id, team_evidence = _resolve_sofascore_team_id(row, roster_cache)
    if not team_id:
        return None

    try:
        roster = roster_cache.roster(team_id)
    except Exception:  # noqa: BLE001
        return None
    match = _best_roster_player_match(row.canonical_player.display_name, roster)
    if not match:
        return None
    player, confidence, match_evidence = match
    raw = _profile_position(player)
    group = normalize_position_group(raw)
    if group == PositionGroup.UNKNOWN:
        return None
    evidence = {
        **team_evidence,
        **match_evidence,
        "provider_team_id": str(team_id),
        "provider_player_id": str(player.get("id") or ""),
        "roster_position": player.get("position") or "",
        "positions_detailed": player.get("positionsDetailed") or [],
    }
    return ResolutionCandidate(
        PositionResolutionSource.SOFASCORE_ROSTER,
        raw[:64],
        group,
        confidence,
        evidence,
    )


def _from_sofascore_profile(row: MergedPlayerSeason) -> ResolutionCandidate | None:
    mapping = ProviderPlayerMapping.objects.filter(
        canonical_player=row.canonical_player,
        provider=Provider.SOFASCORE,
    ).first()
    if not mapping:
        return None
    try:
        profile = fetch_player_profile(mapping.provider_player_id)
    except Exception:  # noqa: BLE001
        return None
    raw = _profile_position(profile)
    group = normalize_position_group(raw)
    if group == PositionGroup.UNKNOWN:
        return None
    return ResolutionCandidate(
        PositionResolutionSource.SOFASCORE_PROFILE,
        raw[:64],
        group,
        0.95,
        {
            "provider_player_id": mapping.provider_player_id,
            "profile_position": profile.get("position") or "",
            "positions_detailed": profile.get("positionsDetailed") or [],
        },
    )


def _resolve_sofascore_team_id(
    row: MergedPlayerSeason,
    roster_cache: _RosterCache,
) -> tuple[str | None, dict[str, Any]]:
    existing = SofascoreTeamSeasonSource.objects.filter(
        competition_season=row.competition_season,
        canonical_team=row.canonical_display_team,
    ).first()
    if existing:
        return existing.provider_team_id, {"team_source": "SofascoreTeamSeasonSource"}

    mapped = ProviderTeamMapping.objects.filter(
        canonical_team=row.canonical_display_team,
        provider=Provider.SOFASCORE,
    ).first()
    if mapped:
        return mapped.provider_team_id, {"team_source": "ProviderTeamMapping"}

    try:
        teams = roster_cache.season_teams(row.competition_season)
    except Exception:  # noqa: BLE001
        return None, {}
    match = _best_team_match(row.canonical_display_team.name, teams)
    if not match:
        return None, {}
    team, confidence, matched_name = match
    return (
        str(team.get("id") or ""),
        {
            "team_source": "season_teams",
            "team_match_confidence": confidence,
            "team_match_name": matched_name,
        },
    )


def _best_team_match(
    team_name: str,
    teams: list[dict[str, Any]],
) -> tuple[dict[str, Any], float, str] | None:
    scored: list[tuple[float, dict[str, Any], str]] = []
    for team in teams:
        names = [
            team.get("name") or "",
            team.get("shortName") or "",
            team.get("slug") or "",
            team.get("nameCode") or "",
        ]
        for candidate in names:
            score = _name_score(team_name, candidate, allow_first_name=False)
            if score:
                scored.append((score, team, candidate))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    best = scored[0]
    if best[0] < 0.68:
        return None
    tied_team_ids = {str(item[1].get("id")) for item in scored if item[0] >= best[0] - 0.03}
    if len(tied_team_ids) > 1:
        return None
    return best[1], best[0], best[2]


def _best_roster_player_match(
    player_name: str,
    roster: list[dict[str, Any]],
) -> tuple[dict[str, Any], float, dict[str, Any]] | None:
    scored: list[tuple[float, dict[str, Any], str]] = []
    first_token_matches = 0
    target_tokens = _tokens(player_name)
    target_first = target_tokens[0] if target_tokens else ""

    for item in roster:
        player = item.get("player") or item
        candidate_names = _player_name_candidates(player)
        if target_first and any(_tokens(name)[:1] == [target_first] for name in candidate_names):
            first_token_matches += 1
        for candidate in candidate_names:
            score = _name_score(player_name, candidate, allow_first_name=True)
            if score:
                scored.append((score, player, candidate))

    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, player, matched_name = scored[0]
    if best_score < 0.72:
        return None
    tied_player_ids = {str(item[1].get("id")) for item in scored if item[0] >= best_score - 0.03}
    if len(tied_player_ids) > 1:
        return None
    if best_score == 0.72 and first_token_matches != 1:
        return None
    return (
        player,
        best_score,
        {
            "player_match_name": matched_name,
            "player_match_confidence": best_score,
            "target_player_name": player_name,
        },
    )


def _player_name_candidates(player: dict[str, Any]) -> list[str]:
    candidates = [
        player.get("name") or "",
        player.get("shortName") or "",
        " ".join([player.get("firstName") or "", player.get("lastName") or ""]).strip(),
        (player.get("slug") or "").replace("-", " "),
    ]
    return [candidate for candidate in candidates if candidate]


def _profile_position(profile: dict[str, Any]) -> str:
    detailed = profile.get("positionsDetailed")
    if isinstance(detailed, list):
        for value in detailed:
            if value and normalize_position_group(str(value)) != PositionGroup.UNKNOWN:
                return str(value)
    return str(profile.get("position") or "")


def _name_score(left: str, right: str, *, allow_first_name: bool) -> float:
    a = _normalized_name(left)
    b = _normalized_name(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) >= 6 and len(b) >= 6 and (a in b or b in a):
        return 0.9

    a_tokens = _tokens(a)
    b_tokens = _tokens(b)
    if not a_tokens or not b_tokens:
        return 0.0
    if set(a_tokens) == set(b_tokens):
        return 0.98
    if len(a_tokens) >= 2 and set(a_tokens).issubset(set(b_tokens)):
        return 0.92
    if len(b_tokens) >= 2 and set(b_tokens).issubset(set(a_tokens)):
        return 0.9
    if not allow_first_name and (set(a_tokens).issubset(set(b_tokens)) or set(b_tokens).issubset(set(a_tokens))):
        return 0.82
    if a_tokens[0] == b_tokens[0] and len(a_tokens) > 1 and len(b_tokens) > 1:
        if a_tokens[-1] == b_tokens[-1]:
            return 0.95
        if allow_first_name:
            return 0.72

    ratio = SequenceMatcher(None, a, b).ratio()
    return ratio if ratio >= 0.82 else 0.0


def _normalized_name(value: str) -> str:
    value = "".join(
        char for char in unicodedata.normalize("NFKD", value or "") if not unicodedata.combining(char)
    )
    lowered = value.casefold().replace("&", " and ")
    return " ".join("".join(char if char.isalnum() else " " for char in lowered).split())


def _tokens(value: str) -> list[str]:
    stop = {
        "ac",
        "afc",
        "as",
        "cd",
        "cf",
        "club",
        "de",
        "fc",
        "f",
        "c",
        "football",
        "la",
        "le",
        "rcd",
        "sc",
        "ss",
        "sv",
        "the",
        "calcio",
    }
    return [token for token in _normalized_name(value).split() if token not in stop]


def _increment_source_stat(stats: PositionResolutionStats, source: str) -> None:
    if source == PositionResolutionSource.EXISTING_SOURCE:
        stats.existing_source += 1
    elif source == PositionResolutionSource.HISTORICAL_PLAYER:
        stats.historical_player += 1
    elif source == PositionResolutionSource.SOFASCORE_ROSTER:
        stats.sofascore_roster += 1
    elif source == PositionResolutionSource.SOFASCORE_PROFILE:
        stats.sofascore_profile += 1


@transaction.atomic
def _write_resolution(row: MergedPlayerSeason, candidate: ResolutionCandidate) -> bool:
    defaults = {
        "canonical_team": row.canonical_display_team,
        "source": candidate.source,
        "raw_position": candidate.raw_position[:64],
        "position_group": candidate.position_group,
        "confidence": candidate.confidence,
        "evidence_json": candidate.evidence,
    }
    existing = PlayerPositionResolution.objects.filter(
        competition_season=row.competition_season,
        canonical_player=row.canonical_player,
    ).first()
    changed = existing is None or any(getattr(existing, field) != value for field, value in defaults.items())
    PlayerPositionResolution.objects.update_or_create(
        competition_season=row.competition_season,
        canonical_player=row.canonical_player,
        defaults=defaults,
    )
    return changed
