from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from ingestion.models import (
    CanonicalTeam,
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    MetadataAuthority,
    MergedPlayerSeason,
    PlayerDataMode,
    PositionGroup,
    Provider,
    ReepPlayerRow,
    SofascorePlayerSeasonSource,
    UnderstatPlayerSeasonSource,
)
from ingestion.position import normalize_position_group
from ingestion.services.identity import resolve_canonical_team
from ingestion.services.validation import can_merge_slice, latest_success_run


NATIVE_POSITION_LABELS = {
    "AM": "Attacking Midfield",
    "CENTRAL MIDFIELDER": "Central Midfield",
    "CENTRE-BACK": "Centre-Back",
    "CENTRE-FORWARD": "Centre-Forward",
    "CENTREBACK": "Centre-Back",
    "CENTREFORWARD": "Centre-Forward",
    "DC": "Centre-Back",
    "DEFENDER": "Defender",
    "DEFENSIVE MIDFIELDER": "Defensive Midfield",
    "DL": "Left-Back",
    "DM": "Defensive Midfield",
    "DR": "Right-Back",
    "F": "F",
    "FORWARD": "Forward",
    "FULL-BACK": "Full Back",
    "FULLBACK": "Full Back",
    "G": "Goalkeeper",
    "GK": "Goalkeeper",
    "GOALKEEPER": "Goalkeeper",
    "INSIDE FORWARD": "Inside Forward",
    "LW": "Left Winger",
    "MC": "Central Midfield",
    "MIDFIELDER": "Midfielder",
    "ML": "Left Midfield",
    "MR": "Right Midfield",
    "RIGHT WINGER": "Right Winger",
    "RW": "Right Winger",
    "ST": "Centre-Forward",
    "WINGER": "Winger",
}


def _canonical_native_position(raw: str) -> str:
    normalized = " ".join(raw.strip().replace("_", " ").split())
    return NATIVE_POSITION_LABELS.get(normalized.upper(), normalized)


def _secondary_display_team_ids(
    us: UnderstatPlayerSeasonSource | None,
    primary: CanonicalTeam | None,
    resolved_team_cache: dict[str, CanonicalTeam | None] | None = None,
) -> list[int]:
    """
    Multi-club Understat rows store official team ids in `provider_team_ids` (from the league
    teams payload). Resolve each id through Reep mappings; omit the SofaScore primary club.
    """
    if not us:
        return []
    raw_ids = us.provider_team_ids or []
    if len(raw_ids) <= 1:
        return []
    primary_id = primary.pk if primary else None
    cs = us.competition_season
    out: list[int] = []
    seen: set[int] = set()
    for tid in raw_ids:
        tid = str(tid).strip()
        if not tid:
            continue
        if resolved_team_cache is not None and tid in resolved_team_cache:
            ct = resolved_team_cache[tid]
        else:
            ct = resolve_canonical_team(
                competition_season=cs,
                provider=Provider.UNDERSTAT,
                provider_team_id=tid,
                team_name=us.team_name or "",
                run=None,
            )
            if resolved_team_cache is not None:
                resolved_team_cache[tid] = ct
        if not ct:
            continue
        if primary_id is not None and ct.pk == primary_id:
            continue
        if ct.pk in seen:
            continue
        seen.add(ct.pk)
        out.append(ct.pk)
    return out


def _resolve_position_metadata(
    *,
    us: UnderstatPlayerSeasonSource | None,
    ss: SofascorePlayerSeasonSource | None,
    reep_rows_by_id: dict[str, ReepPlayerRow] | None = None,
) -> tuple[str, str]:
    candidates: list[str] = []
    if ss and ss.position_raw:
        candidates.append(ss.position_raw)

    reep_row = None
    if us and us.canonical_player and us.canonical_player.reep_id:
        reep_row = (reep_rows_by_id or {}).get(us.canonical_player.reep_id)
        if reep_row is None and reep_rows_by_id is None:
            reep_row = ReepPlayerRow.objects.filter(reep_id=us.canonical_player.reep_id).first()
    elif ss and ss.canonical_player and ss.canonical_player.reep_id:
        reep_row = (reep_rows_by_id or {}).get(ss.canonical_player.reep_id)
        if reep_row is None and reep_rows_by_id is None:
            reep_row = ReepPlayerRow.objects.filter(reep_id=ss.canonical_player.reep_id).first()

    if reep_row:
        if reep_row.position_detail:
            candidates.append(reep_row.position_detail)
        if reep_row.position:
            candidates.append(reep_row.position)
    if us and us.position_raw:
        candidates.append(us.position_raw)

    for raw in candidates:
        group = normalize_position_group(raw)
        if group != PositionGroup.UNKNOWN:
            return _canonical_native_position(raw), group

    fallback_raw = candidates[0] if candidates else ""
    return _canonical_native_position(fallback_raw), normalize_position_group(fallback_raw)


@transaction.atomic
def execute_merge_for_slice(
    competition_season: CompetitionSeason,
    *,
    merge_run: IngestionRun | None = None,
) -> None:
    gate = can_merge_slice(competition_season)
    if not gate.ok:
        raise ValueError(gate.message)

    us_run = latest_success_run(competition_season, IngestionKind.UNDERSTAT)
    ss_run = latest_success_run(competition_season, IngestionKind.SOFASCORE)
    if competition_season.player_data_mode == PlayerDataMode.FULL_MERGE:
        assert us_run and ss_run
    elif not ss_run:
        raise ValueError("Sofascore-only merge requires a successful Sofascore run.")

    us_map = {
        r.canonical_player_id: r
        for r in UnderstatPlayerSeasonSource.objects.filter(
            competition_season=competition_season,
            canonical_player__isnull=False,
        ).select_related("canonical_player")
    }
    ss_map = {
        r.canonical_player_id: r
        for r in SofascorePlayerSeasonSource.objects.filter(
            competition_season=competition_season,
            canonical_player__isnull=False,
        ).select_related("canonical_player")
    }
    player_ids = set(us_map.keys()) | set(ss_map.keys())
    reep_ids = {
        row.canonical_player.reep_id
        for row in [*us_map.values(), *ss_map.values()]
        if row.canonical_player and row.canonical_player.reep_id
    }
    reep_rows_by_id = {
        row.reep_id: row
        for row in ReepPlayerRow.objects.filter(reep_id__in=reep_ids)
    }
    secondary_team_cache: dict[str, CanonicalTeam | None] = {}

    MergedPlayerSeason.objects.filter(
        competition_season=competition_season,
        is_current=True,
    ).update(is_current=False, superseded_at=timezone.now())

    to_create: list[MergedPlayerSeason] = []
    for cid in sorted(player_ids):
        us = us_map.get(cid)
        ss = ss_map.get(cid)

        if us:
            authority = MetadataAuthority.UNDERSTAT
            minutes = us.minutes if us.minutes is not None else (ss.minutes if ss else None)
        elif ss:
            authority = MetadataAuthority.SOFASCORE
            minutes = ss.minutes
        else:
            continue

        # Primary display club: SofaScore when present (current roster), else Understat.
        display_team = None
        if ss:
            display_team = ss.canonical_team
        if display_team is None and us:
            display_team = us.canonical_team

        secondary_team_ids = _secondary_display_team_ids(us, display_team, secondary_team_cache)

        native_pos, pos_group = _resolve_position_metadata(
            us=us,
            ss=ss,
            reep_rows_by_id=reep_rows_by_id,
        )

        to_create.append(
            MergedPlayerSeason(
                competition_season=competition_season,
                canonical_player_id=cid,
                canonical_display_team=display_team,
                secondary_display_team_ids=secondary_team_ids,
                position_group=pos_group,
                native_position=native_pos[:64],
                minutes=minutes,
                metadata_authority=authority,
                us_goals=us.goals if us else None,
                us_assists=us.assists if us else None,
                us_shots=us.shots if us else None,
                us_key_passes=us.key_passes if us else None,
                us_npg=us.npg if us else None,
                us_xg=us.xg if us else None,
                us_npxg=us.npxg if us else None,
                us_xa=us.xa if us else None,
                us_xgchain=us.xgchain if us else None,
                us_xgbuildup=us.xgbuildup if us else None,
                us_games=us.games if us else None,
                us_yellow_cards=us.yellow_cards if us else None,
                us_red_cards=us.red_cards if us else None,
                ss_rating=ss.rating if ss else None,
                ss_goals=ss.summary_goals if ss else None,
                ss_assists=ss.summary_assists if ss else None,
                ss_expected_goals=ss.summary_expected_goals if ss else None,
                ss_expected_assists=ss.summary_expected_assists
                if ss
                else None,
                ss_total_shots=ss.total_shots if ss else None,
                ss_tackles=ss.tackles if ss else None,
                ss_interceptions=ss.interceptions if ss else None,
                ss_clearances=ss.clearances if ss else None,
                ss_error_lead_to_goal=ss.error_lead_to_goal if ss else None,
                ss_outfielder_blocks=ss.outfielder_blocks if ss else None,
                ss_accurate_passes=ss.accurate_passes if ss else None,
                ss_inaccurate_passes=ss.inaccurate_passes if ss else None,
                ss_total_passes=ss.total_passes if ss else None,
                ss_key_passes=ss.key_passes if ss else None,
                ss_tackles_won=ss.tackles_won if ss else None,
                ss_tackles_won_percentage=ss.tackles_won_percentage if ss else None,
                ss_shots_on_target=ss.shots_on_target if ss else None,
                ss_shots_off_target=ss.shots_off_target if ss else None,
                ss_aerial_duels_won=ss.aerial_duels_won if ss else None,
                ss_ground_duels_won=ss.ground_duels_won if ss else None,
                ss_ball_recoveries=ss.ball_recoveries if ss else None,
                ss_successful_dribbles_percentage=ss.successful_dribbles_percentage if ss else None,
                ss_fouls=ss.fouls if ss else None,
                ss_offsides=ss.offsides if ss else None,
                ss_accurate_crosses=ss.accurate_crosses if ss else None,
                ss_accurate_long_balls=ss.accurate_long_balls if ss else None,
                ss_saves=ss.saves if ss else None,
                ss_clean_sheet=ss.clean_sheet if ss else None,
                ss_penalty_save=ss.penalty_save if ss else None,
                ss_appearances=ss.appearances if ss else None,
                ss_big_chances_created=ss.big_chances_created if ss else None,
                ss_accurate_passes_percentage=ss.accurate_passes_percentage
                if ss
                else None,
                ss_saved_shots_from_inside_the_box=ss.saved_shots_from_inside_the_box
                if ss
                else None,
                ss_runs_out=ss.runs_out if ss else None,
                understat_ingestion_run=us_run,
                sofascore_ingestion_run=ss_run,
                merge_ingestion_run=merge_run,
                is_current=True,
            )
        )

    MergedPlayerSeason.objects.bulk_create(to_create)
