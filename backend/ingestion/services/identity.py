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


def _resolve_player_from_slice_counterpart(
    *,
    competition_season: CompetitionSeason,
    provider: str,
    display_name: str,
) -> CanonicalPlayer | None:
    if not display_name:
        return None

    counterpart_config = _aggregate_counterpart(provider)
    if counterpart_config is None:
        return None
    other_provider, other_model = counterpart_config
    normalized_display_name = _normalize_player_name_for_match(display_name)
    if not normalized_display_name:
        return None

    candidates = [
        row
        for row in other_model.objects.filter(competition_season=competition_season)
        if _normalize_player_name_for_match(row.player_name) == normalized_display_name
    ]
    if len(candidates) != 1:
        return None

    counterpart = candidates[0]
    counterpart_pid = str(counterpart.provider_player_id or "")
    if not counterpart_pid:
        return None

    counterpart_mapping = (
        ProviderPlayerMapping.objects.filter(
            provider=other_provider,
            provider_player_id=counterpart_pid,
        )
        .select_related("canonical_player")
        .first()
    )
    if (
        counterpart_mapping
        and counterpart.canonical_player_id
        and counterpart_mapping.canonical_player_id != counterpart.canonical_player_id
    ):
        return None

    player = counterpart_mapping.canonical_player if counterpart_mapping else counterpart.canonical_player
    if player is None:
        player = CanonicalPlayer.objects.create(display_name=counterpart.player_name or display_name)
    elif not player.display_name and (counterpart.player_name or display_name):
        player.display_name = counterpart.player_name or display_name
        player.save(update_fields=["display_name"])

    ProviderPlayerMapping.objects.get_or_create(
        provider=other_provider,
        provider_player_id=counterpart_pid,
        defaults={"canonical_player": player, "match_method": MatchMethod.AUTO},
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
    return player


def _attach_provider_native_slice_counterpart(
    *,
    competition_season: CompetitionSeason,
    provider: str,
    display_name: str,
    alias_names: tuple[str, ...] = (),
    player: CanonicalPlayer,
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

    candidate_qs = other_model.objects.filter(competition_season=competition_season)
    candidates = [
        row
        for row in candidate_qs
        if _normalize_player_name_for_match(row.player_name) in normalized_aliases
    ]
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
        ):
            return
        counterpart_mapping.canonical_player = player
        counterpart_mapping.save(update_fields=["canonical_player", "updated_at"])
    else:
        if counterpart.canonical_player_id and counterpart.canonical_player.reep_id:
            return
        ProviderPlayerMapping.objects.create(
            provider=other_provider,
            provider_player_id=counterpart_pid,
            canonical_player=player,
            match_method=MatchMethod.AUTO,
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
            if _reep_row_missing_counterpart_id(row, provider):
                _attach_provider_native_slice_counterpart(
                    competition_season=competition_season,
                    provider=provider,
                    display_name=display_name,
                    alias_names=(row.full_name,),
                    player=player,
                )
            return player

        if (
            existing_map.match_method == MatchMethod.AUTO
            and existing_map.canonical_player.reep_id is None
        ):
            player = _resolve_player_from_slice_counterpart(
                competition_season=competition_season,
                provider=provider,
                display_name=display_name,
            )
            if player and player.id != existing_map.canonical_player_id:
                existing_map.canonical_player = player
                existing_map.save(update_fields=["canonical_player", "updated_at"])
                _mark_unmatched_player_resolved(
                    competition_season=competition_season,
                    provider=provider,
                    provider_player_id=pid,
                    player=player,
                )
                return player

        return existing_map.canonical_player

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
        player = _resolve_player_from_slice_counterpart(
            competition_season=competition_season,
            provider=provider,
            display_name=display_name,
        )
        if player is None:
            player = _get_or_create_provider_native_player(
                provider=provider,
                provider_player_id=pid,
                display_name=display_name,
            )
        else:
            ProviderPlayerMapping.objects.get_or_create(
                provider=provider,
                provider_player_id=pid,
                defaults={"canonical_player": player, "match_method": MatchMethod.AUTO},
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
    if _reep_row_missing_counterpart_id(row, provider):
        _attach_provider_native_slice_counterpart(
            competition_season=competition_season,
            provider=provider,
            display_name=display_name,
            alias_names=(row.full_name,),
            player=player,
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
) -> EventIdentityReport | None:
    """
    Attach provider event IDs only through existing mappings.

    Event feeds must never manufacture canonical identities from a provider name.
    Unknown IDs are retained on normalized rows and recorded for manual resolution.
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

    team_mappings = {
        mapping.provider_team_id: mapping.canonical_team
        for mapping in ProviderTeamMapping.objects.filter(
            provider=locked_match.provider,
            provider_team_id__in=team_ids,
        ).select_related("canonical_team")
    }
    player_mappings = {
        mapping.provider_player_id: mapping.canonical_player
        for mapping in ProviderPlayerMapping.objects.filter(
            provider=locked_match.provider,
            provider_player_id__in=player_ids,
        ).select_related("canonical_player")
    }

    for provider_team_id in team_ids:
        team = team_mappings.get(provider_team_id)
        if team is None:
            _record_unmatched_team(
                competition_season=locked_match.competition_season,
                provider=locked_match.provider,
                provider_team_id=provider_team_id,
                team_name=normalized_team_names.get(provider_team_id, ""),
                run=run,
            )
            continue
        UnmatchedProviderTeam.objects.filter(
            competition_season=locked_match.competition_season,
            provider=locked_match.provider,
            provider_team_id=provider_team_id,
        ).update(resolved_team=team, resolved_at=timezone.now())

    for provider_player_id in player_ids:
        player = player_mappings.get(provider_player_id)
        if player is None:
            _record_unmatched_player(
                competition_season=locked_match.competition_season,
                provider=locked_match.provider,
                provider_player_id=provider_player_id,
                player_name=normalized_player_names.get(provider_player_id, ""),
                run=run,
            )
            continue
        _mark_unmatched_player_resolved(
            competition_season=locked_match.competition_season,
            provider=locked_match.provider,
            provider_player_id=provider_player_id,
            player=player,
        )

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
    for provider_match in ProviderMatch.objects.filter(
        competition_season=competition_season,
        provider=provider,
    ):
        attach_provider_match_identities(
            provider_match,
            run=run,
            include_report=False,
        )
        match_count += 1
        event_count += provider_match.events.count()
    return match_count, event_count


def reattach_slice_identities(competition_season: CompetitionSeason) -> tuple[int, int, int]:
    """Re-resolve canonical FKs on all provider source rows for a slice (after manual mapping)."""

    u_count = 0
    for src in UnderstatPlayerSeasonSource.objects.filter(competition_season=competition_season):
        cplayer = resolve_canonical_player(
            competition_season=competition_season,
            provider=Provider.UNDERSTAT,
            provider_player_id=src.provider_player_id,
            display_name=src.player_name,
            run=None,
        )
        cteam = None
        if src.provider_team_id:
            cteam = resolve_canonical_team(
                competition_season=competition_season,
                provider=Provider.UNDERSTAT,
                provider_team_id=src.provider_team_id,
                team_name=src.team_name,
                run=None,
            )
        src.canonical_player = cplayer
        src.canonical_team = cteam
        src.save(update_fields=["canonical_player", "canonical_team"])
        u_count += 1

    s_count = 0
    for src in SofascorePlayerSeasonSource.objects.filter(competition_season=competition_season):
        cplayer = resolve_canonical_player(
            competition_season=competition_season,
            provider=Provider.SOFASCORE,
            provider_player_id=src.provider_player_id,
            display_name=src.player_name,
            run=None,
        )
        cteam = None
        if src.provider_team_id:
            cteam = resolve_canonical_team(
                competition_season=competition_season,
                provider=Provider.SOFASCORE,
                provider_team_id=src.provider_team_id,
                team_name=src.team_name,
                run=None,
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
