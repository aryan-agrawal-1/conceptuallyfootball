from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Mapping

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    CompetitionSeason,
    IngestionRun,
    MatchMethod,
    PlayerSeasonClubSpell,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderPlayerMapping,
    ProviderTeamMapping,
    ReepPlayerRow,
    ReepTeamRow,
    SofascorePlayerSeasonSource,
    SofascoreTeamSeasonSource,
    UnderstatPlayerSeasonSource,
    UnmatchedProviderPlayer,
    UnmatchedProviderTeam,
)

EVENT_IDENTITY_WARNING_PERCENT = Decimal("1")
EVENT_IDENTITY_PUBLICATION_FAILURE_PERCENT = Decimal("5")


class EventIdentityPublicationError(ValueError):
    pass


@dataclass(frozen=True)
class EventIdentityVolume:
    total_events: int
    player_events: int
    mapped_player_events: int
    unmapped_player_events: int
    playerless_events: int
    mapped_team_events: int
    unmapped_team_events: int

    @property
    def unmapped_player_percent(self) -> Decimal:
        if not self.player_events:
            return Decimal("0")
        return Decimal(self.unmapped_player_events * 100) / Decimal(self.player_events)

    @property
    def warning(self) -> bool:
        return self.unmapped_player_percent > EVENT_IDENTITY_WARNING_PERCENT

    @property
    def publication_failure(self) -> bool:
        return self.unmapped_player_percent > EVENT_IDENTITY_PUBLICATION_FAILURE_PERCENT

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "unmapped_player_percent": str(self.unmapped_player_percent),
            "warning": self.warning,
            "publication_failure": self.publication_failure,
        }


@dataclass(frozen=True)
class EventIdentityReport:
    competition_season_id: int
    volume: EventIdentityVolume
    by_match: tuple[dict[str, Any], ...]
    by_team: tuple[dict[str, Any], ...]

    @property
    def warning(self) -> bool:
        return self.volume.warning

    @property
    def publication_failure(self) -> bool:
        return self.volume.publication_failure

    def as_dict(self) -> dict[str, Any]:
        return {
            "competition_season_id": self.competition_season_id,
            "volume": self.volume.as_dict(),
            "by_match": list(self.by_match),
            "by_team": list(self.by_team),
            "warning": self.warning,
            "publication_failure": self.publication_failure,
        }


@dataclass(frozen=True)
class PlayerIdentityCandidate:
    canonical_player: CanonicalPlayer
    canonical_team_ids: tuple[int, ...]
    source_providers: tuple[str, ...]
    matched_aliases: tuple[str, ...]
    match_reason: str


def _aggregate_counterpart(provider: str) -> tuple[str, type[Any]] | None:
    if provider == Provider.UNDERSTAT:
        return Provider.SOFASCORE, SofascorePlayerSeasonSource
    if provider == Provider.SOFASCORE:
        return Provider.UNDERSTAT, UnderstatPlayerSeasonSource
    return None


def _reep_player_row(provider: str, provider_player_id: str) -> ReepPlayerRow | None:
    if provider == Provider.UNDERSTAT:
        return ReepPlayerRow.objects.filter(understat_player_id=provider_player_id).first()
    if provider == Provider.SOFASCORE:
        return ReepPlayerRow.objects.filter(sofascore_player_id=provider_player_id).first()
    return None


def _reep_team_row(provider: str, provider_team_id: str) -> ReepTeamRow | None:
    if provider == Provider.UNDERSTAT:
        return ReepTeamRow.objects.filter(understat_team_id=provider_team_id).first()
    if provider == Provider.SOFASCORE:
        return ReepTeamRow.objects.filter(sofascore_team_id=provider_team_id).first()
    return None


def _mark_unmatched_player_resolved(
    *,
    competition_season: CompetitionSeason,
    provider: str,
    provider_player_id: str,
    player: CanonicalPlayer,
) -> None:
    UnmatchedProviderPlayer.objects.filter(
        competition_season=competition_season,
        provider=provider,
        provider_player_id=provider_player_id,
    ).update(resolved_player=player, resolved_at=timezone.now())


def _record_unmatched_player(
    *,
    competition_season: CompetitionSeason,
    provider: str,
    provider_player_id: str,
    player_name: str,
    run: IngestionRun | None,
) -> None:
    unmatched, created = UnmatchedProviderPlayer.objects.get_or_create(
        competition_season=competition_season,
        provider=provider,
        provider_player_id=provider_player_id,
        defaults={"player_name": player_name, "first_seen_run": run},
    )
    if not created and player_name and unmatched.player_name != player_name:
        unmatched.player_name = player_name
        unmatched.save(update_fields=["player_name"])


def _record_unmatched_team(
    *,
    competition_season: CompetitionSeason,
    provider: str,
    provider_team_id: str,
    team_name: str,
    run: IngestionRun | None,
) -> None:
    unmatched, created = UnmatchedProviderTeam.objects.get_or_create(
        competition_season=competition_season,
        provider=provider,
        provider_team_id=provider_team_id,
        defaults={"team_name": team_name, "first_seen_run": run},
    )
    if not created and team_name and unmatched.team_name != team_name:
        unmatched.team_name = team_name
        unmatched.save(update_fields=["team_name"])


def _get_or_create_player_for_reep_row(
    *,
    row: ReepPlayerRow,
    fallback_name: str,
) -> CanonicalPlayer:
    display_name = row.full_name or fallback_name
    existing = CanonicalPlayer.objects.filter(reep_id=row.reep_id).first()
    if existing:
        if display_name and existing.display_name != display_name:
            existing.display_name = display_name
            existing.save(update_fields=["display_name"])
        return existing

    for provider, provider_player_id in (
        (Provider.UNDERSTAT, row.understat_player_id),
        (Provider.SOFASCORE, row.sofascore_player_id),
    ):
        if not provider_player_id:
            continue
        mapping = (
            ProviderPlayerMapping.objects.filter(
                provider=provider,
                provider_player_id=provider_player_id,
                match_method=MatchMethod.AUTO,
            )
            .select_related("canonical_player")
            .first()
        )
        if mapping and mapping.canonical_player.reep_id is None:
            player = mapping.canonical_player
            update_fields: list[str] = []
            if player.reep_id != row.reep_id:
                player.reep_id = row.reep_id
                update_fields.append("reep_id")
            if display_name and player.display_name != display_name:
                player.display_name = display_name
                update_fields.append("display_name")
            if update_fields:
                player.save(update_fields=update_fields)
            return player

    return CanonicalPlayer.objects.create(
        reep_id=row.reep_id,
        display_name=display_name,
    )


def _get_or_create_provider_native_player(
    *,
    provider: str,
    provider_player_id: str,
    display_name: str,
) -> CanonicalPlayer:
    pid = str(provider_player_id)
    existing_map = (
        ProviderPlayerMapping.objects.filter(provider=provider, provider_player_id=pid)
        .select_related("canonical_player")
        .first()
    )
    if existing_map:
        return existing_map.canonical_player

    player = CanonicalPlayer.objects.create(
        display_name=display_name or f"{provider} player {pid}",
    )
    ProviderPlayerMapping.objects.create(
        provider=provider,
        provider_player_id=pid,
        canonical_player=player,
        match_method=MatchMethod.AUTO,
    )
    return player


def _normalize_player_name_for_match(name: str) -> str:
    value = html.unescape(name or "").casefold()
    value = "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _normalized_player_aliases(*names: str) -> set[str]:
    return {normalized for name in names if (normalized := _normalize_player_name_for_match(name))}


def _candidate_player_evidence(
    *,
    competition_season: CompetitionSeason,
    provider: str,
) -> dict[int, dict[str, Any]]:
    evidence: dict[int, dict[str, Any]] = {}
    source_configs = (
        (Provider.UNDERSTAT, UnderstatPlayerSeasonSource),
        (Provider.SOFASCORE, SofascorePlayerSeasonSource),
    )

    for source_provider, source_model in source_configs:
        rows = list(
            source_model.objects.filter(
                competition_season=competition_season,
            ).select_related("canonical_player", "canonical_team")
        )
        mapped_players = {
            mapping.provider_player_id: mapping.canonical_player
            for mapping in ProviderPlayerMapping.objects.filter(
                provider=source_provider,
                provider_player_id__in=[
                    str(source_row.provider_player_id) for source_row in rows
                ],
            ).select_related("canonical_player")
        }
        source_team_ids = {
            str(source_row.provider_team_id)
            for source_row in rows
            if source_row.provider_team_id
        }
        if source_provider == Provider.UNDERSTAT:
            source_team_ids.update(
                str(provider_team_id)
                for source_row in rows
                for provider_team_id in (source_row.provider_team_ids or [])
                if str(provider_team_id)
            )
        mapped_teams = {
            mapping.provider_team_id: mapping.canonical_team_id
            for mapping in ProviderTeamMapping.objects.filter(
                provider=source_provider,
                provider_team_id__in=source_team_ids,
            )
        }
        for row in rows:
            if source_provider == provider:
                continue
            player = row.canonical_player or mapped_players.get(str(row.provider_player_id))
            if player is None:
                continue
            player_evidence = evidence.setdefault(
                player.id,
                {
                    "player": player,
                    "aliases": set(),
                    "team_ids": set(),
                    "providers": set(),
                },
            )
            player_evidence["aliases"].update(
                _normalized_player_aliases(row.player_name)
            )
            player_evidence["providers"].add(source_provider)
            if row.canonical_team_id:
                player_evidence["team_ids"].add(row.canonical_team_id)
            elif row.provider_team_id and str(row.provider_team_id) in mapped_teams:
                player_evidence["team_ids"].add(
                    mapped_teams[str(row.provider_team_id)]
                )
            if source_provider == Provider.UNDERSTAT:
                player_evidence["team_ids"].update(
                    mapped_teams[str(provider_team_id)]
                    for provider_team_id in (row.provider_team_ids or [])
                    if str(provider_team_id) in mapped_teams
                )

    reep_rows = {
        row.reep_id: row
        for row in ReepPlayerRow.objects.filter(
            reep_id__in=[
                item["player"].reep_id
                for item in evidence.values()
                if item["player"].reep_id
            ]
        )
    }
    for item in evidence.values():
        reep_id = item["player"].reep_id
        if reep_id and reep_id in reep_rows:
            item["aliases"].update(
                _normalized_player_aliases(reep_rows[reep_id].full_name)
            )

    for player_id, canonical_team_id in PlayerSeasonClubSpell.objects.filter(
        competition_season=competition_season,
        canonical_player_id__in=evidence,
    ).values_list("canonical_player_id", "canonical_team_id"):
        evidence[player_id]["team_ids"].add(canonical_team_id)

    return evidence


def find_player_identity_candidates(
    *,
    competition_season: CompetitionSeason,
    provider: str,
    provider_player_id: str,
    display_name: str,
    canonical_team_ids: set[int] | tuple[int, ...] = (),
    require_team_match: bool = False,
    candidate_evidence: dict[int, dict[str, Any]] | None = None,
) -> tuple[PlayerIdentityCandidate, ...]:
    """
    Return conservative same-slice identity candidates.

    Exact normalized aliases are required. When team context is available, a
    candidate must also share a mapped team in the competition-season. This
    deliberately prefers an unresolved identity to a plausible false match.
    """

    normalized_name = _normalize_player_name_for_match(display_name)
    if not normalized_name:
        return ()

    target_team_ids = set(canonical_team_ids)
    if require_team_match and not target_team_ids:
        return ()
    candidates: list[PlayerIdentityCandidate] = []
    evidence = (
        candidate_evidence
        if candidate_evidence is not None
        else _candidate_player_evidence(
            competition_season=competition_season,
            provider=provider,
        )
    )
    for item in evidence.values():
        if normalized_name not in item["aliases"]:
            continue
        candidate_team_ids = set(item["team_ids"])
        if target_team_ids and not target_team_ids.intersection(candidate_team_ids):
            continue
        candidates.append(
            PlayerIdentityCandidate(
                canonical_player=item["player"],
                canonical_team_ids=tuple(sorted(candidate_team_ids)),
                source_providers=tuple(sorted(item["providers"])),
                matched_aliases=(normalized_name,),
                match_reason=(
                    "exact_name_and_team"
                    if target_team_ids
                    else "unique_exact_name_in_competition_season"
                ),
            )
        )
    return tuple(sorted(candidates, key=lambda candidate: candidate.canonical_player.id))


def _unique_player_identity_candidate(
    *,
    competition_season: CompetitionSeason,
    provider: str,
    provider_player_id: str,
    display_name: str,
    canonical_team_ids: set[int] | tuple[int, ...] = (),
    require_team_match: bool = False,
    candidate_evidence: dict[int, dict[str, Any]] | None = None,
) -> CanonicalPlayer | None:
    candidates = find_player_identity_candidates(
        competition_season=competition_season,
        provider=provider,
        provider_player_id=provider_player_id,
        display_name=display_name,
        canonical_team_ids=canonical_team_ids,
        require_team_match=require_team_match,
        candidate_evidence=candidate_evidence,
    )
    if len(candidates) != 1:
        return None
    return candidates[0].canonical_player


def _attach_slice_sources_for_canonical_player(
    *,
    competition_season: CompetitionSeason,
    player: CanonicalPlayer,
) -> None:
    for source_provider, source_model in (
        (Provider.UNDERSTAT, UnderstatPlayerSeasonSource),
        (Provider.SOFASCORE, SofascorePlayerSeasonSource),
    ):
        provider_player_ids = ProviderPlayerMapping.objects.filter(
            provider=source_provider,
            canonical_player=player,
        ).values_list("provider_player_id", flat=True)
        source_model.objects.filter(
            competition_season=competition_season,
            provider_player_id__in=provider_player_ids,
        ).exclude(canonical_player=player).update(canonical_player=player)


def _auto_mapping_can_move_without_splitting_identity(
    mapping: ProviderPlayerMapping,
) -> bool:
    has_other_provider_mappings = ProviderPlayerMapping.objects.filter(
        canonical_player_id=mapping.canonical_player_id,
    ).exclude(pk=mapping.pk).exists()
    has_event_dependents = ProviderMatchEvent.objects.filter(
        player_id=mapping.canonical_player_id,
    ).exists()
    return not has_other_provider_mappings and not has_event_dependents


def _resolve_player_from_slice_counterpart(
    *,
    competition_season: CompetitionSeason,
    provider: str,
    provider_player_id: str,
    display_name: str,
    canonical_team_ids: set[int] | tuple[int, ...] = (),
    require_team_match: bool = False,
    candidate_evidence: dict[int, dict[str, Any]] | None = None,
) -> CanonicalPlayer | None:
    return _unique_player_identity_candidate(
        competition_season=competition_season,
        provider=provider,
        provider_player_id=provider_player_id,
        display_name=display_name,
        canonical_team_ids=canonical_team_ids,
        require_team_match=require_team_match,
        candidate_evidence=candidate_evidence,
    )


def _attach_provider_native_slice_counterpart(
    *,
    competition_season: CompetitionSeason,
    provider: str,
    display_name: str,
    alias_names: tuple[str, ...] = (),
    player: CanonicalPlayer,
    canonical_team_ids: set[int] | tuple[int, ...] = (),
    require_team_match: bool = False,
) -> None:
    """
    Reep rows are sometimes incomplete for one provider. If the opposite provider
    already made an auto provider-native player for a same unique normalized alias
    in this slice, attach it to the reep-backed canonical player.
    """
    counterpart_config = _aggregate_counterpart(provider)
    if counterpart_config is None:
        return
    other_provider, other_model = counterpart_config
    normalized_aliases = _normalized_player_aliases(display_name, *alias_names)
    if not normalized_aliases:
        return
    target_team_ids = set(canonical_team_ids)
    if require_team_match and not target_team_ids:
        return

    candidate_qs = other_model.objects.filter(
        competition_season=competition_season
    ).select_related("canonical_player", "canonical_team")
    candidates = []
    for candidate in candidate_qs:
        if _normalize_player_name_for_match(candidate.player_name) not in normalized_aliases:
            continue
        candidate_team_ids = {
            candidate.canonical_team_id
        } if candidate.canonical_team_id else set()
        provider_team_ids = {
            str(candidate.provider_team_id)
        } if candidate.provider_team_id else set()
        if other_provider == Provider.UNDERSTAT:
            provider_team_ids.update(
                str(provider_team_id)
                for provider_team_id in (candidate.provider_team_ids or [])
                if str(provider_team_id)
            )
        candidate_team_ids.update(
            ProviderTeamMapping.objects.filter(
                provider=other_provider,
                provider_team_id__in=provider_team_ids,
            ).values_list("canonical_team_id", flat=True)
        )
        if target_team_ids and not target_team_ids.intersection(candidate_team_ids):
            continue
        candidates.append(candidate)
    if len(candidates) != 1:
        return

    counterpart = candidates[0]
    counterpart_pid = str(counterpart.provider_player_id or "")
    if not counterpart_pid:
        return

    counterpart_mapping = (
        ProviderPlayerMapping.objects.filter(
            provider=other_provider,
            provider_player_id=counterpart_pid,
        )
        .select_related("canonical_player")
        .first()
    )
    if counterpart_mapping:
        if (
            counterpart_mapping.match_method != MatchMethod.AUTO
            or counterpart_mapping.canonical_player.reep_id
            or counterpart_mapping.canonical_player_id == player.id
            or not _auto_mapping_can_move_without_splitting_identity(
                counterpart_mapping
            )
        ):
            return
        counterpart_mapping.canonical_player = player
        counterpart_mapping.save(update_fields=["canonical_player", "updated_at"])
    else:
        if counterpart.canonical_player_id and counterpart.canonical_player.reep_id:
            return
        if counterpart.canonical_player_id and counterpart.canonical_player_id != player.id:
            return
        ProviderPlayerMapping.objects.get_or_create(
            provider=other_provider,
            provider_player_id=counterpart_pid,
            defaults={
                "canonical_player": player,
                "match_method": MatchMethod.AUTO,
            },
        )

    if counterpart.canonical_player_id != player.id:
        counterpart.canonical_player = player
        counterpart.save(update_fields=["canonical_player"])
    _mark_unmatched_player_resolved(
        competition_season=competition_season,
        provider=other_provider,
        provider_player_id=counterpart_pid,
        player=player,
    )


def _reep_row_missing_counterpart_id(row: ReepPlayerRow, provider: str) -> bool:
    if provider == Provider.SOFASCORE:
        return not row.understat_player_id
    if provider == Provider.UNDERSTAT:
        return not row.sofascore_player_id
    return False


def resolve_canonical_player(
    *,
    competition_season: CompetitionSeason,
    provider: str,
    provider_player_id: str,
    display_name: str,
    run: IngestionRun | None,
    canonical_team_ids: set[int] | tuple[int, ...] = (),
    require_team_match: bool = False,
    candidate_evidence: dict[int, dict[str, Any]] | None = None,
    allow_shared_fallback: bool = True,
) -> CanonicalPlayer | None:
    pid = str(provider_player_id)
    if not pid:
        return None
    row = _reep_player_row(provider, pid)

    existing_map = (
        ProviderPlayerMapping.objects.filter(
            provider=provider,
            provider_player_id=pid,
        )
        .select_related("canonical_player")
        .first()
    )
    if existing_map:
        if _aggregate_counterpart(provider) is None:
            _mark_unmatched_player_resolved(
                competition_season=competition_season,
                provider=provider,
                provider_player_id=pid,
                player=existing_map.canonical_player,
            )
            return existing_map.canonical_player
        if row and existing_map.match_method == MatchMethod.AUTO:
            player = _get_or_create_player_for_reep_row(row=row, fallback_name=display_name)
            if existing_map.canonical_player_id != player.id:
                existing_map.canonical_player = player
                existing_map.save(update_fields=["canonical_player", "updated_at"])
            _mark_unmatched_player_resolved(
                competition_season=competition_season,
                provider=provider,
                provider_player_id=pid,
                player=player,
            )
            if allow_shared_fallback and _reep_row_missing_counterpart_id(row, provider):
                _attach_provider_native_slice_counterpart(
                    competition_season=competition_season,
                    provider=provider,
                    display_name=display_name,
                    alias_names=(row.full_name,),
                    player=player,
                    canonical_team_ids=canonical_team_ids,
                    require_team_match=require_team_match,
                )
            return player

        if (
            allow_shared_fallback
            and existing_map.match_method == MatchMethod.AUTO
            and existing_map.canonical_player.reep_id is None
        ):
            player = _resolve_player_from_slice_counterpart(
                competition_season=competition_season,
                provider=provider,
                provider_player_id=pid,
                display_name=display_name,
                canonical_team_ids=canonical_team_ids,
                require_team_match=require_team_match,
                candidate_evidence=candidate_evidence,
            )
            if (
                player
                and player.id != existing_map.canonical_player_id
                and _auto_mapping_can_move_without_splitting_identity(existing_map)
            ):
                existing_map.canonical_player = player
                existing_map.save(update_fields=["canonical_player", "updated_at"])
                _mark_unmatched_player_resolved(
                    competition_season=competition_season,
                    provider=provider,
                    provider_player_id=pid,
                    player=player,
                )
                _attach_slice_sources_for_canonical_player(
                    competition_season=competition_season,
                    player=player,
                )
                return player

        return existing_map.canonical_player

    shared_candidate = (
        None
        if row or not allow_shared_fallback
        else _resolve_player_from_slice_counterpart(
            competition_season=competition_season,
            provider=provider,
            provider_player_id=pid,
            display_name=display_name,
            canonical_team_ids=canonical_team_ids,
            require_team_match=require_team_match,
            candidate_evidence=candidate_evidence,
        )
    )
    if shared_candidate is not None:
        mapping, _ = ProviderPlayerMapping.objects.get_or_create(
            provider=provider,
            provider_player_id=pid,
            defaults={
                "canonical_player": shared_candidate,
                "match_method": MatchMethod.AUTO,
            },
        )
        shared_candidate = mapping.canonical_player
        _mark_unmatched_player_resolved(
            competition_season=competition_season,
            provider=provider,
            provider_player_id=pid,
            player=shared_candidate,
        )
        _attach_slice_sources_for_canonical_player(
            competition_season=competition_season,
            player=shared_candidate,
        )
        return shared_candidate

    if _aggregate_counterpart(provider) is None:
        _record_unmatched_player(
            competition_season=competition_season,
            provider=provider,
            provider_player_id=pid,
            player_name=display_name,
            run=run,
        )
        return None

    if not row:
        player = _get_or_create_provider_native_player(
            provider=provider,
            provider_player_id=pid,
            display_name=display_name,
        )
        _mark_unmatched_player_resolved(
            competition_season=competition_season,
            provider=provider,
            provider_player_id=pid,
            player=player,
        )
        return player

    player = _get_or_create_player_for_reep_row(row=row, fallback_name=display_name)

    ProviderPlayerMapping.objects.get_or_create(
        provider=provider,
        provider_player_id=pid,
        defaults={"canonical_player": player, "match_method": MatchMethod.AUTO},
    )
    if allow_shared_fallback and _reep_row_missing_counterpart_id(row, provider):
        _attach_provider_native_slice_counterpart(
            competition_season=competition_season,
            provider=provider,
            display_name=display_name,
            alias_names=(row.full_name,),
            player=player,
            canonical_team_ids=canonical_team_ids,
            require_team_match=require_team_match,
        )
    _mark_unmatched_player_resolved(
        competition_season=competition_season,
        provider=provider,
        provider_player_id=pid,
        player=player,
    )
    return player


def _get_or_create_provider_native_team(
    *,
    provider: str,
    provider_team_id: str,
    team_name: str,
) -> CanonicalTeam:
    tid = str(provider_team_id)
    existing_map = (
        ProviderTeamMapping.objects.filter(provider=provider, provider_team_id=tid)
        .select_related("canonical_team")
        .first()
    )
    if existing_map:
        return existing_map.canonical_team

    team = CanonicalTeam.objects.create(name=team_name or f"{provider} team {tid}")
    ProviderTeamMapping.objects.create(
        provider=provider,
        provider_team_id=tid,
        canonical_team=team,
        match_method=MatchMethod.AUTO,
    )
    return team


def _unique_team_identity_candidate(
    *,
    competition_season: CompetitionSeason,
    provider: str,
    provider_team_id: str,
    team_name: str,
) -> CanonicalTeam | None:
    normalized_name = _normalize_player_name_for_match(team_name)
    if not normalized_name:
        return None

    candidates: dict[int, CanonicalTeam] = {}
    source_configs = (
        (Provider.UNDERSTAT, UnderstatPlayerSeasonSource),
        (Provider.SOFASCORE, SofascorePlayerSeasonSource),
        (Provider.SOFASCORE, SofascoreTeamSeasonSource),
    )
    for source_provider, source_model in source_configs:
        rows = source_model.objects.filter(
            competition_season=competition_season,
            canonical_team__isnull=False,
        ).select_related("canonical_team")
        for source_row in rows:
            if (
                source_provider == provider
                and str(source_row.provider_team_id) == str(provider_team_id)
            ):
                continue
            aliases = _normalized_player_aliases(
                source_row.team_name,
            )
            if normalized_name in aliases:
                candidates[source_row.canonical_team_id] = source_row.canonical_team

    if len(candidates) != 1:
        return None
    return next(iter(candidates.values()))


def resolve_canonical_team(
    *,
    competition_season: CompetitionSeason,
    provider: str,
    provider_team_id: str,
    team_name: str,
    run: IngestionRun | None,
) -> CanonicalTeam | None:
    tid = str(provider_team_id)
    if not tid:
        return None
    row = _reep_team_row(provider, tid)

    existing_map = (
        ProviderTeamMapping.objects.filter(
            provider=provider,
            provider_team_id=tid,
        )
        .select_related("canonical_team")
        .first()
    )
    if existing_map:
        if _aggregate_counterpart(provider) is None:
            UnmatchedProviderTeam.objects.filter(
                competition_season=competition_season,
                provider=provider,
                provider_team_id=tid,
            ).update(resolved_team=existing_map.canonical_team, resolved_at=timezone.now())
            return existing_map.canonical_team
        if (
            row
            and existing_map.match_method == MatchMethod.AUTO
            and existing_map.canonical_team.reep_id != row.reep_id
        ):
            team, _ = CanonicalTeam.objects.get_or_create(
                reep_id=row.reep_id,
                defaults={"name": row.name or team_name},
            )
            existing_map.canonical_team = team
            existing_map.save(update_fields=["canonical_team", "updated_at"])
            return team
        return existing_map.canonical_team

    shared_candidate = (
        None
        if row
        else _unique_team_identity_candidate(
            competition_season=competition_season,
            provider=provider,
            provider_team_id=tid,
            team_name=team_name,
        )
    )
    if shared_candidate is not None:
        mapping, _ = ProviderTeamMapping.objects.get_or_create(
            provider=provider,
            provider_team_id=tid,
            defaults={
                "canonical_team": shared_candidate,
                "match_method": MatchMethod.AUTO,
            },
        )
        shared_candidate = mapping.canonical_team
        UnmatchedProviderTeam.objects.filter(
            competition_season=competition_season,
            provider=provider,
            provider_team_id=tid,
        ).update(resolved_team=shared_candidate, resolved_at=timezone.now())
        return shared_candidate

    if _aggregate_counterpart(provider) is None:
        _record_unmatched_team(
            competition_season=competition_season,
            provider=provider,
            provider_team_id=tid,
            team_name=team_name,
            run=run,
        )
        return None

    if not row:
        team = _get_or_create_provider_native_team(
            provider=provider,
            provider_team_id=tid,
            team_name=team_name,
        )
        unmatched, _ = UnmatchedProviderTeam.objects.get_or_create(
            competition_season=competition_season,
            provider=provider,
            provider_team_id=tid,
            defaults={"team_name": team_name, "first_seen_run": run},
        )
        unmatched.resolved_team = team
        unmatched.resolved_at = timezone.now()
        unmatched.save(update_fields=["resolved_team", "resolved_at"])
        return team

    team, _ = CanonicalTeam.objects.get_or_create(
        reep_id=row.reep_id,
        defaults={"name": row.name or team_name},
    )
    ProviderTeamMapping.objects.get_or_create(
        provider=provider,
        provider_team_id=tid,
        defaults={"canonical_team": team, "match_method": MatchMethod.AUTO},
    )
    UnmatchedProviderTeam.objects.filter(
        competition_season=competition_season,
        provider=provider,
        provider_team_id=tid,
    ).update(resolved_team=team, resolved_at=timezone.now())
    return team


@transaction.atomic
def attach_provider_match_identities(
    provider_match: ProviderMatch,
    *,
    run: IngestionRun | None = None,
    team_names: Mapping[str, str] | None = None,
    player_names: Mapping[str, str] | None = None,
    include_report: bool = True,
    candidate_evidence: dict[int, dict[str, Any]] | None = None,
) -> EventIdentityReport | None:
    """
    Attach event IDs through existing mappings or one conservative shared resolver.

    The resolver may reuse a unique exact-name canonical identity from the same
    competition-season (and mapped team when available). Event feeds never
    manufacture canonical identities from provider names. Ambiguous or unknown
    IDs remain on normalized rows and are recorded for manual resolution.
    """

    locked_match = (
        ProviderMatch.objects.select_for_update()
        .select_related("competition_season")
        .get(pk=provider_match.pk)
    )
    normalized_team_names = {str(key): value for key, value in (team_names or {}).items()}
    normalized_player_names = {str(key): value for key, value in (player_names or {}).items()}
    team_ids = set(
        locked_match.events.exclude(provider_team_id="")
        .values_list("provider_team_id", flat=True)
        .distinct()
    )
    team_ids.update(
        provider_team_id
        for provider_team_id in (
            locked_match.home_provider_team_id,
            locked_match.away_provider_team_id,
        )
        if provider_team_id
    )
    player_ids = set(
        locked_match.events.exclude(provider_player_id__isnull=True)
        .exclude(provider_player_id="")
        .values_list("provider_player_id", flat=True)
        .distinct()
    )
    stored_team_names = {
        unmatched.provider_team_id: unmatched.team_name
        for unmatched in UnmatchedProviderTeam.objects.filter(
            competition_season=locked_match.competition_season,
            provider=locked_match.provider,
            provider_team_id__in=team_ids,
        )
    }
    stored_player_names = {
        unmatched.provider_player_id: unmatched.player_name
        for unmatched in UnmatchedProviderPlayer.objects.filter(
            competition_season=locked_match.competition_season,
            provider=locked_match.provider,
            provider_player_id__in=player_ids,
        )
    }

    for provider_team_id in team_ids:
        resolve_canonical_team(
            competition_season=locked_match.competition_season,
            provider=locked_match.provider,
            provider_team_id=provider_team_id,
            team_name=(
                normalized_team_names.get(provider_team_id)
                or stored_team_names.get(provider_team_id, "")
            ),
            run=run,
        )

    team_mappings = {
        mapping.provider_team_id: mapping.canonical_team
        for mapping in ProviderTeamMapping.objects.filter(
            provider=locked_match.provider,
            provider_team_id__in=team_ids,
        ).select_related("canonical_team")
    }
    already_mapped_player_ids = set(
        ProviderPlayerMapping.objects.filter(
            provider=locked_match.provider,
            provider_player_id__in=player_ids,
        ).values_list("provider_player_id", flat=True)
    )
    active_candidate_evidence = (
        candidate_evidence
        if candidate_evidence is not None
        else (
            _candidate_player_evidence(
                competition_season=locked_match.competition_season,
                provider=locked_match.provider,
            )
            if player_ids.difference(already_mapped_player_ids)
            else {}
        )
    )
    for provider_player_id in player_ids:
        provider_team_ids = set(
            locked_match.events.filter(provider_player_id=provider_player_id)
            .exclude(provider_team_id="")
            .values_list("provider_team_id", flat=True)
        )
        canonical_team_ids = {
            team_mappings[provider_team_id].id
            for provider_team_id in provider_team_ids
            if provider_team_id in team_mappings
        }
        resolve_canonical_player(
            competition_season=locked_match.competition_season,
            provider=locked_match.provider,
            provider_player_id=provider_player_id,
            display_name=(
                normalized_player_names.get(provider_player_id)
                or stored_player_names.get(provider_player_id, "")
            ),
            run=run,
            canonical_team_ids=canonical_team_ids,
            require_team_match=bool(provider_team_ids),
            candidate_evidence=active_candidate_evidence,
        )

    player_mappings = {
        mapping.provider_player_id: mapping.canonical_player
        for mapping in ProviderPlayerMapping.objects.filter(
            provider=locked_match.provider,
            provider_player_id__in=player_ids,
        ).select_related("canonical_player")
    }
    locked_match.home_team = team_mappings.get(locked_match.home_provider_team_id)
    locked_match.away_team = team_mappings.get(locked_match.away_provider_team_id)
    locked_match.save(update_fields=["home_team", "away_team", "updated_at"])

    locked_match.events.update(team=None, player=None)
    for provider_team_id, team in team_mappings.items():
        locked_match.events.filter(provider_team_id=provider_team_id).update(team=team)
    for provider_player_id, player in player_mappings.items():
        locked_match.events.filter(provider_player_id=provider_player_id).update(player=player)

    if include_report:
        return build_event_identity_report(locked_match.competition_season)
    return None


def _empty_event_identity_counts() -> dict[str, int]:
    return {
        "total_events": 0,
        "player_events": 0,
        "mapped_player_events": 0,
        "unmapped_player_events": 0,
        "playerless_events": 0,
        "mapped_team_events": 0,
        "unmapped_team_events": 0,
    }


def _add_event_identity_row(counts: dict[str, int], row: Mapping[str, Any]) -> None:
    counts["total_events"] += 1
    if row["team_id"] is None:
        counts["unmapped_team_events"] += 1
    else:
        counts["mapped_team_events"] += 1

    if not row["provider_player_id"]:
        counts["playerless_events"] += 1
    elif row["player_id"] is None:
        counts["player_events"] += 1
        counts["unmapped_player_events"] += 1
    else:
        counts["player_events"] += 1
        counts["mapped_player_events"] += 1


def _volume_from_counts(counts: Mapping[str, int]) -> EventIdentityVolume:
    return EventIdentityVolume(
        total_events=counts["total_events"],
        player_events=counts["player_events"],
        mapped_player_events=counts["mapped_player_events"],
        unmapped_player_events=counts["unmapped_player_events"],
        playerless_events=counts["playerless_events"],
        mapped_team_events=counts["mapped_team_events"],
        unmapped_team_events=counts["unmapped_team_events"],
    )


def build_event_identity_report(
    competition_season: CompetitionSeason,
    *,
    provider: str = Provider.WHOSCORED,
) -> EventIdentityReport:
    events: QuerySet[ProviderMatchEvent] = ProviderMatchEvent.objects.filter(
        provider_match__competition_season=competition_season,
        provider_match__provider=provider,
    )
    rows = events.values(
        "provider_match_id",
        "provider_match__provider_match_id",
        "provider_team_id",
        "provider_player_id",
        "team_id",
        "player_id",
    )
    slice_counts = _empty_event_identity_counts()
    match_counts: dict[tuple[int, str], dict[str, int]] = {}
    team_counts: dict[str, dict[str, int]] = {}
    for row in rows.iterator():
        match_key = (
            row["provider_match_id"],
            row["provider_match__provider_match_id"],
        )
        match_volume = match_counts.setdefault(match_key, _empty_event_identity_counts())
        team_volume = team_counts.setdefault(
            row["provider_team_id"],
            _empty_event_identity_counts(),
        )
        _add_event_identity_row(slice_counts, row)
        _add_event_identity_row(match_volume, row)
        _add_event_identity_row(team_volume, row)

    by_match = tuple(
        {
            "provider_match_database_id": database_id,
            "provider_match_id": provider_match_id,
            **_volume_from_counts(counts).as_dict(),
        }
        for (database_id, provider_match_id), counts in sorted(
            match_counts.items(),
            key=lambda item: (item[0][1], item[0][0]),
        )
    )
    by_team = tuple(
        {
            "provider_team_id": provider_team_id,
            **_volume_from_counts(counts).as_dict(),
        }
        for provider_team_id, counts in sorted(team_counts.items())
    )
    return EventIdentityReport(
        competition_season_id=competition_season.pk,
        volume=_volume_from_counts(slice_counts),
        by_match=by_match,
        by_team=by_team,
    )


def validate_event_identity_publication(report: EventIdentityReport) -> None:
    if report.publication_failure:
        raise EventIdentityPublicationError(
            "Unmapped player-event volume "
            f"{report.volume.unmapped_player_percent}% exceeds the "
            f"{EVENT_IDENTITY_PUBLICATION_FAILURE_PERCENT}% publication limit."
        )


def record_event_identity_diagnostics(
    run: IngestionRun,
    report: EventIdentityReport | None = None,
) -> EventIdentityReport:
    if run.competition_season is None:
        raise ValueError("Event identity diagnostics require a competition-season run.")
    active_report = report or build_event_identity_report(run.competition_season)
    stats = dict(run.stats)
    stats["event_identity"] = active_report.as_dict()
    run.stats = stats
    run.save(update_fields=["stats"])
    return active_report


def reattach_event_identities(
    competition_season: CompetitionSeason,
    *,
    provider: str = Provider.WHOSCORED,
    run: IngestionRun | None = None,
) -> tuple[int, int]:
    match_count = 0
    event_count = 0
    candidate_evidence = _candidate_player_evidence(
        competition_season=competition_season,
        provider=provider,
    )
    for provider_match in ProviderMatch.objects.filter(
        competition_season=competition_season,
        provider=provider,
    ):
        attach_provider_match_identities(
            provider_match,
            run=run,
            include_report=False,
            candidate_evidence=candidate_evidence,
        )
        match_count += 1
        event_count += provider_match.events.count()
    return match_count, event_count


def reattach_slice_identities(competition_season: CompetitionSeason) -> tuple[int, int, int]:
    """Re-resolve canonical FKs on all provider source rows for a slice (after manual mapping)."""

    u_count = 0
    for src in UnderstatPlayerSeasonSource.objects.filter(competition_season=competition_season):
        cteam = None
        if src.provider_team_id:
            cteam = resolve_canonical_team(
                competition_season=competition_season,
                provider=Provider.UNDERSTAT,
                provider_team_id=src.provider_team_id,
                team_name=src.team_name,
                run=None,
            )
        canonical_team_ids = {cteam.id} if cteam else set()
        canonical_team_ids.update(
            ProviderTeamMapping.objects.filter(
                provider=Provider.UNDERSTAT,
                provider_team_id__in=[
                    str(provider_team_id)
                    for provider_team_id in (src.provider_team_ids or [])
                    if str(provider_team_id)
                ],
            ).values_list("canonical_team_id", flat=True)
        )
        cplayer = resolve_canonical_player(
            competition_season=competition_season,
            provider=Provider.UNDERSTAT,
            provider_player_id=src.provider_player_id,
            display_name=src.player_name,
            run=None,
            canonical_team_ids=canonical_team_ids,
            require_team_match=bool(
                src.provider_team_id or (src.provider_team_ids or [])
            ),
        )
        src.canonical_player = cplayer
        src.canonical_team = cteam
        src.save(update_fields=["canonical_player", "canonical_team"])
        u_count += 1

    s_count = 0
    for src in SofascorePlayerSeasonSource.objects.filter(competition_season=competition_season):
        cteam = None
        if src.provider_team_id:
            cteam = resolve_canonical_team(
                competition_season=competition_season,
                provider=Provider.SOFASCORE,
                provider_team_id=src.provider_team_id,
                team_name=src.team_name,
                run=None,
            )
        cplayer = resolve_canonical_player(
            competition_season=competition_season,
            provider=Provider.SOFASCORE,
            provider_player_id=src.provider_player_id,
            display_name=src.player_name,
            run=None,
            canonical_team_ids={cteam.id} if cteam else set(),
            require_team_match=bool(src.provider_team_id),
        )
        src.canonical_player = cplayer
        src.canonical_team = cteam
        src.save(update_fields=["canonical_player", "canonical_team"])
        s_count += 1

    t_count = 0
    for src in SofascoreTeamSeasonSource.objects.filter(competition_season=competition_season):
        cteam = None
        if src.provider_team_id:
            cteam = resolve_canonical_team(
                competition_season=competition_season,
                provider=Provider.SOFASCORE,
                provider_team_id=src.provider_team_id,
                team_name=src.team_name,
                run=None,
            )
        src.canonical_team = cteam
        src.save(update_fields=["canonical_team"])
        t_count += 1

    reattach_event_identities(competition_season)
    return u_count, s_count, t_count


def _unmatched_player_team_context(
    unmatched: UnmatchedProviderPlayer,
) -> tuple[set[int], bool]:
    rows = ProviderMatchEvent.objects.filter(
        provider_match__competition_season=unmatched.competition_season,
        provider_match__provider=unmatched.provider,
        provider_player_id=unmatched.provider_player_id,
    ).values_list("provider_team_id", "team_id")
    canonical_team_ids: set[int] = set()
    has_provider_team = False
    provider_team_ids: set[str] = set()
    for provider_team_id, canonical_team_id in rows:
        if provider_team_id:
            has_provider_team = True
            provider_team_ids.add(str(provider_team_id))
        if canonical_team_id:
            canonical_team_ids.add(canonical_team_id)
    canonical_team_ids.update(
        ProviderTeamMapping.objects.filter(
            provider=unmatched.provider,
            provider_team_id__in=provider_team_ids,
        ).values_list("canonical_team_id", flat=True)
    )
    return canonical_team_ids, has_provider_team


def unmatched_player_identity_candidates(
    unmatched: UnmatchedProviderPlayer,
) -> tuple[PlayerIdentityCandidate, ...]:
    canonical_team_ids, require_team_match = _unmatched_player_team_context(unmatched)
    return find_player_identity_candidates(
        competition_season=unmatched.competition_season,
        provider=unmatched.provider,
        provider_player_id=unmatched.provider_player_id,
        display_name=unmatched.player_name,
        canonical_team_ids=canonical_team_ids,
        require_team_match=require_team_match,
    )


@transaction.atomic
def retry_unmatched_player_resolution(
    unmatched: UnmatchedProviderPlayer,
    *,
    candidate_evidence: dict[int, dict[str, Any]] | None = None,
) -> CanonicalPlayer | None:
    locked_unmatched = (
        UnmatchedProviderPlayer.objects.select_for_update()
        .select_related("competition_season")
        .get(pk=unmatched.pk)
    )
    if locked_unmatched.resolved_player_id:
        return locked_unmatched.resolved_player
    provider_team_ids = set(
        ProviderMatchEvent.objects.filter(
            provider_match__competition_season=locked_unmatched.competition_season,
            provider_match__provider=locked_unmatched.provider,
            provider_player_id=locked_unmatched.provider_player_id,
        )
        .exclude(provider_team_id="")
        .values_list("provider_team_id", flat=True)
    )
    stored_team_names = {
        unmatched_team.provider_team_id: unmatched_team.team_name
        for unmatched_team in UnmatchedProviderTeam.objects.filter(
            competition_season=locked_unmatched.competition_season,
            provider=locked_unmatched.provider,
            provider_team_id__in=provider_team_ids,
        )
    }
    for provider_team_id in provider_team_ids:
        team = resolve_canonical_team(
            competition_season=locked_unmatched.competition_season,
            provider=locked_unmatched.provider,
            provider_team_id=provider_team_id,
            team_name=stored_team_names.get(provider_team_id, ""),
            run=None,
        )
        if team is not None:
            ProviderMatchEvent.objects.filter(
                provider_match__competition_season=locked_unmatched.competition_season,
                provider_match__provider=locked_unmatched.provider,
                provider_team_id=provider_team_id,
            ).update(team=team)
    canonical_team_ids, require_team_match = _unmatched_player_team_context(
        locked_unmatched
    )
    player = resolve_canonical_player(
        competition_season=locked_unmatched.competition_season,
        provider=locked_unmatched.provider,
        provider_player_id=locked_unmatched.provider_player_id,
        display_name=locked_unmatched.player_name,
        run=None,
        canonical_team_ids=canonical_team_ids,
        require_team_match=require_team_match,
        candidate_evidence=candidate_evidence,
    )
    if player is not None:
        ProviderMatchEvent.objects.filter(
            provider_match__competition_season=locked_unmatched.competition_season,
            provider_match__provider=locked_unmatched.provider,
            provider_player_id=locked_unmatched.provider_player_id,
        ).update(player=player)
    return player



@transaction.atomic
def apply_manual_player_resolution(
    unmatched: UnmatchedProviderPlayer,
    canonical_player: CanonicalPlayer,
) -> None:
    ProviderPlayerMapping.objects.update_or_create(
        provider=unmatched.provider,
        provider_player_id=unmatched.provider_player_id,
        defaults={
            "canonical_player": canonical_player,
            "match_method": MatchMethod.MANUAL,
        },
    )
    unmatched.resolved_player = canonical_player
    unmatched.resolved_at = timezone.now()
    unmatched.save(update_fields=["resolved_player", "resolved_at"])
    if unmatched.provider == Provider.UNDERSTAT:
        UnderstatPlayerSeasonSource.objects.filter(
            competition_season=unmatched.competition_season,
            provider_player_id=unmatched.provider_player_id,
        ).update(canonical_player=canonical_player)
    elif unmatched.provider == Provider.SOFASCORE:
        SofascorePlayerSeasonSource.objects.filter(
            competition_season=unmatched.competition_season,
            provider_player_id=unmatched.provider_player_id,
        ).update(canonical_player=canonical_player)
    ProviderMatchEvent.objects.filter(
        provider_match__competition_season=unmatched.competition_season,
        provider_match__provider=unmatched.provider,
        provider_player_id=unmatched.provider_player_id,
    ).update(player=canonical_player)


@transaction.atomic
def apply_manual_team_resolution(
    unmatched: UnmatchedProviderTeam,
    canonical_team: CanonicalTeam,
) -> None:
    ProviderTeamMapping.objects.update_or_create(
        provider=unmatched.provider,
        provider_team_id=unmatched.provider_team_id,
        defaults={
            "canonical_team": canonical_team,
            "match_method": MatchMethod.MANUAL,
        },
    )
    unmatched.resolved_team = canonical_team
    unmatched.resolved_at = timezone.now()
    unmatched.save(update_fields=["resolved_team", "resolved_at"])
    ProviderMatchEvent.objects.filter(
        provider_match__competition_season=unmatched.competition_season,
        provider_match__provider=unmatched.provider,
        provider_team_id=unmatched.provider_team_id,
    ).update(team=canonical_team)
    ProviderMatch.objects.filter(
        competition_season=unmatched.competition_season,
        provider=unmatched.provider,
        home_provider_team_id=unmatched.provider_team_id,
    ).update(home_team=canonical_team)
    ProviderMatch.objects.filter(
        competition_season=unmatched.competition_season,
        provider=unmatched.provider,
        away_provider_team_id=unmatched.provider_team_id,
    ).update(away_team=canonical_team)
