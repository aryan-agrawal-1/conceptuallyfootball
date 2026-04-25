from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    CompetitionSeason,
    IngestionRun,
    MatchMethod,
    Provider,
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


def _resolve_player_from_slice_counterpart(
    *,
    competition_season: CompetitionSeason,
    provider: str,
    display_name: str,
) -> CanonicalPlayer | None:
    if not display_name:
        return None

    other_provider = Provider.SOFASCORE if provider == Provider.UNDERSTAT else Provider.UNDERSTAT
    other_model = (
        SofascorePlayerSeasonSource if provider == Provider.UNDERSTAT else UnderstatPlayerSeasonSource
    )
    candidates = list(
        other_model.objects.filter(
            competition_season=competition_season,
            player_name__iexact=display_name,
        )
    )
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


def resolve_canonical_player(
    *,
    competition_season: CompetitionSeason,
    provider: str,
    provider_player_id: str,
    display_name: str,
    run: IngestionRun | None,
) -> CanonicalPlayer | None:
    pid = str(provider_player_id)
    if provider == Provider.UNDERSTAT:
        row = ReepPlayerRow.objects.filter(understat_player_id=pid).first()
    else:
        row = ReepPlayerRow.objects.filter(sofascore_player_id=pid).first()

    existing_map = ProviderPlayerMapping.objects.filter(
        provider=provider,
        provider_player_id=pid,
    ).first()
    if existing_map:
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
            return player
        return existing_map.canonical_player

    if not row:
        player = _resolve_player_from_slice_counterpart(
            competition_season=competition_season,
            provider=provider,
            display_name=display_name,
        )
        if player:
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
        UnmatchedProviderPlayer.objects.get_or_create(
            competition_season=competition_season,
            provider=provider,
            provider_player_id=pid,
            defaults={"player_name": display_name, "first_seen_run": run},
        )
        return None

    player = _get_or_create_player_for_reep_row(row=row, fallback_name=display_name)

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
    if provider == Provider.UNDERSTAT:
        row = ReepTeamRow.objects.filter(understat_team_id=tid).first()
    else:
        row = ReepTeamRow.objects.filter(sofascore_team_id=tid).first()

    existing_map = ProviderTeamMapping.objects.filter(
        provider=provider,
        provider_team_id=tid,
    ).first()
    if existing_map:
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

    if not row:
        UnmatchedProviderTeam.objects.get_or_create(
            competition_season=competition_season,
            provider=provider,
            provider_team_id=tid,
            defaults={"team_name": team_name, "first_seen_run": run},
        )
        return None

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
