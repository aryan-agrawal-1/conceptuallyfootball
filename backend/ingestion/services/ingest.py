from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ingestion.models import (
    CompetitionSeason,
    IngestionRun,
    IngestionRunStatus,
    MergedTeamSeason,
    MergedPlayerSeason,
    Provider,
    SofascorePlayerSeasonSource,
    SofascoreTeamSeasonSource,
    UnderstatPlayerSeasonSource,
)
from ingestion.services.identity import resolve_canonical_player, resolve_canonical_team
from ingestion.services.merge import execute_merge_for_slice
from ingestion.services.sofascore_client import (
    SofascoreSeasonConfig,
    fetch_full_season_statistics,
    row_to_normalized_record,
)
from ingestion.services.sofascore_team_client import build_team_season_rows
from ingestion.services.team_merge import execute_team_merge_for_slice
from ingestion.services.understat_client import (
    UnderstatLeagueConfig,
    fetch_league_players,
    parse_float,
    parse_int,
)
from ingestion.services.validation import (
    validate_sofascore_slice,
    validate_sofascore_team_candidate,
    validate_sofascore_team_slice,
    validate_team_merge_candidate,
    validate_understat_slice,
)


def _mark_run_start(run: IngestionRun) -> None:
    run.status = IngestionRunStatus.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])


def _mark_run_success(run: IngestionRun, stats: dict | None = None) -> None:
    run.status = IngestionRunStatus.SUCCESS
    run.finished_at = timezone.now()
    run.error_detail = ""
    if stats is not None:
        run.stats = stats
    run.save(update_fields=["status", "finished_at", "error_detail", "stats"])


def _mark_run_failed(run: IngestionRun, message: str) -> None:
    run.status = IngestionRunStatus.FAILED
    run.finished_at = timezone.now()
    run.error_detail = message[:8000]
    run.save(update_fields=["status", "finished_at", "error_detail"])


def _min_rows() -> int:
    return int(getattr(settings, "STATBALLER_INGEST_MIN_ROWS", 200))


def ingest_understat_slice(competition_season: CompetitionSeason, *, run: IngestionRun) -> None:
    _mark_run_start(run)
    try:
        cfg = UnderstatLeagueConfig(
            league=competition_season.understat_league,
            season_year=competition_season.understat_season_year,
        )
        players = fetch_league_players(cfg)
    except Exception as exc:  # noqa: BLE001
        _mark_run_failed(run, f"Understat fetch failed: {exc}")
        return

    min_rows = _min_rows()
    if len(players) < min_rows:
        _mark_run_failed(
            run,
            f"Understat returned too few players ({len(players)}); minimum is {min_rows}.",
        )
        return

    try:
        with transaction.atomic():
            UnderstatPlayerSeasonSource.objects.filter(competition_season=competition_season).delete()
            for row in players:
                pid = str(row.get("id") or "")
                if not pid:
                    continue
                team_title = row.get("team_title") or ""
                team_id = str(row.get("team_id") or row.get("team") or "") or ""
                provider_team_ids = row.get("provider_team_ids")
                if not isinstance(provider_team_ids, list):
                    provider_team_ids = []
                src = UnderstatPlayerSeasonSource.objects.create(
                    competition_season=competition_season,
                    ingestion_run=run,
                    provider_player_id=pid,
                    provider_team_id=team_id,
                    provider_team_ids=[str(x) for x in provider_team_ids if x is not None and str(x).strip()],
                    player_name=row.get("player_name") or "",
                    team_name=team_title,
                    position_raw=(row.get("position") or "")[:64],
                    games=parse_int(row.get("games")),
                    minutes=parse_int(row.get("time")),
                    goals=parse_int(row.get("goals")),
                    assists=parse_int(row.get("assists")),
                    shots=parse_int(row.get("shots")),
                    key_passes=parse_int(row.get("key_passes")),
                    npg=parse_int(row.get("npg")),
                    xg=parse_float(row.get("xG")),
                    npxg=parse_float(row.get("npxG")),
                    xa=parse_float(row.get("xA")),
                    xgchain=parse_float(row.get("xGChain")),
                    xgbuildup=parse_float(row.get("xGBuildup")),
                    yellow_cards=parse_int(row.get("yellow_cards")),
                    red_cards=parse_int(row.get("red_cards")),
                )
                cplayer = resolve_canonical_player(
                    competition_season=competition_season,
                    provider=Provider.UNDERSTAT,
                    provider_player_id=pid,
                    display_name=src.player_name,
                    run=run,
                )
                cteam = None
                if team_id:
                    cteam = resolve_canonical_team(
                        competition_season=competition_season,
                        provider=Provider.UNDERSTAT,
                        provider_team_id=team_id,
                        team_name=team_title,
                        run=run,
                    )
                src.canonical_player = cplayer
                src.canonical_team = cteam
                src.save(update_fields=["canonical_player", "canonical_team"])
    except Exception as exc:  # noqa: BLE001
        _mark_run_failed(run, f"Understat persistence failed: {exc}")
        return

    v = validate_understat_slice(competition_season)
    if not v.ok:
        _mark_run_failed(run, v.message)
        return

    _mark_run_success(run, stats={"players": len(players)})


def ingest_sofascore_slice(competition_season: CompetitionSeason, *, run: IngestionRun) -> None:
    _mark_run_start(run)
    cfg = SofascoreSeasonConfig(
        unique_tournament_id=competition_season.sofascore_unique_tournament_id,
        season_id=competition_season.sofascore_season_id,
    )
    try:
        merged = fetch_full_season_statistics(cfg)
    except Exception as exc:  # noqa: BLE001
        _mark_run_failed(run, f"Sofascore fetch failed: {exc}")
        return

    min_rows = _min_rows()
    if len(merged) < min_rows:
        _mark_run_failed(
            run,
            f"Sofascore returned too few players ({len(merged)}); minimum is {min_rows}.",
        )
        return

    try:
        with transaction.atomic():
            SofascorePlayerSeasonSource.objects.filter(competition_season=competition_season).delete()
            for player_id, raw_row in merged.items():
                norm = row_to_normalized_record(player_id, raw_row)
                pid = norm["provider_player_id"]
                src = SofascorePlayerSeasonSource.objects.create(
                    competition_season=competition_season,
                    ingestion_run=run,
                    provider_player_id=pid,
                    provider_team_id=norm.get("provider_team_id") or "",
                    player_name=norm.get("player_name") or "",
                    team_name=norm.get("team_name") or "",
                    position_raw=norm.get("position_raw") or "",
                    group_stats=norm.get("group_stats") or {},
                    appearances=norm.get("appearances"),
                    minutes=norm.get("minutes"),
                    rating=norm.get("rating"),
                    summary_goals=norm.get("summary_goals"),
                    summary_assists=norm.get("summary_assists"),
                    summary_expected_goals=norm.get("summary_expected_goals"),
                    summary_successful_dribbles=norm.get("summary_successful_dribbles"),
                    summary_accurate_passes_percentage=norm.get(
                        "summary_accurate_passes_percentage"
                    ),
                    tackles=norm.get("tackles"),
                    interceptions=norm.get("interceptions"),
                    clearances=norm.get("clearances"),
                    error_lead_to_goal=norm.get("error_lead_to_goal"),
                    outfielder_blocks=norm.get("outfielder_blocks"),
                    big_chances_created=norm.get("big_chances_created"),
                    accurate_passes=norm.get("accurate_passes"),
                    inaccurate_passes=norm.get("inaccurate_passes"),
                    total_passes=norm.get("total_passes"),
                    key_passes=norm.get("key_passes"),
                    tackles_won=norm.get("tackles_won"),
                    tackles_won_percentage=norm.get("tackles_won_percentage"),
                    shots_on_target=norm.get("shots_on_target"),
                    shots_off_target=norm.get("shots_off_target"),
                    aerial_duels_won=norm.get("aerial_duels_won"),
                    ground_duels_won=norm.get("ground_duels_won"),
                    ball_recoveries=norm.get("ball_recoveries"),
                    successful_dribbles_percentage=norm.get("successful_dribbles_percentage"),
                    fouls=norm.get("fouls"),
                    offsides=norm.get("offsides"),
                    accurate_passes_percentage=norm.get("accurate_passes_percentage"),
                    accurate_crosses=norm.get("accurate_crosses"),
                    accurate_long_balls=norm.get("accurate_long_balls"),
                    saves=norm.get("saves"),
                    clean_sheet=norm.get("clean_sheet"),
                    penalty_save=norm.get("penalty_save"),
                    saved_shots_from_inside_the_box=norm.get("saved_shots_from_inside_the_box"),
                    runs_out=norm.get("runs_out"),
                )
                cplayer = resolve_canonical_player(
                    competition_season=competition_season,
                    provider=Provider.SOFASCORE,
                    provider_player_id=pid,
                    display_name=src.player_name,
                    run=run,
                )
                tid = src.provider_team_id
                cteam = None
                if tid:
                    cteam = resolve_canonical_team(
                        competition_season=competition_season,
                        provider=Provider.SOFASCORE,
                        provider_team_id=tid,
                        team_name=src.team_name,
                        run=run,
                    )
                src.canonical_player = cplayer
                src.canonical_team = cteam
                src.save(update_fields=["canonical_player", "canonical_team"])
    except Exception as exc:  # noqa: BLE001
        _mark_run_failed(run, f"Sofascore persistence failed: {exc}")
        return

    v = validate_sofascore_slice(competition_season)
    if not v.ok:
        _mark_run_failed(run, v.message)
        return

    _mark_run_success(run, stats={"players": len(merged)})


def run_merge_job(competition_season: CompetitionSeason, *, run: IngestionRun) -> None:
    _mark_run_start(run)
    try:
        execute_merge_for_slice(competition_season, merge_run=run)
    except Exception as exc:  # noqa: BLE001
        _mark_run_failed(run, str(exc))
        return
    count = MergedPlayerSeason.objects.filter(
        competition_season=competition_season,
        is_current=True,
    ).count()
    if count == 0:
        _mark_run_failed(run, "Merge produced zero rows (no matched players in both sources).")
        return
    _mark_run_success(run, stats={"merged_rows": count})


def ingest_sofascore_team_slice(competition_season: CompetitionSeason, *, run: IngestionRun) -> None:
    _mark_run_start(run)
    cfg = SofascoreSeasonConfig(
        unique_tournament_id=competition_season.sofascore_unique_tournament_id,
        season_id=competition_season.sofascore_season_id,
    )
    try:
        rows = build_team_season_rows(cfg)
    except Exception as exc:  # noqa: BLE001
        _mark_run_failed(run, f"Sofascore team fetch failed: {exc}")
        return

    candidate_check = validate_sofascore_team_candidate(competition_season, rows)
    if not candidate_check.ok:
        _mark_run_failed(run, candidate_check.message)
        return

    try:
        with transaction.atomic():
            SofascoreTeamSeasonSource.objects.filter(competition_season=competition_season).delete()
            for row in rows:
                provider_team_id = row.get("provider_team_id") or ""
                src = SofascoreTeamSeasonSource.objects.create(
                    competition_season=competition_season,
                    ingestion_run=run,
                    provider_team_id=provider_team_id,
                    team_name=row.get("team_name") or "",
                    standings_row_json=row.get("standings_row_json") or {},
                    overall_stats_json=row.get("overall_stats_json") or {},
                    has_overall_stats=bool(row.get("has_overall_stats")),
                    matches=row.get("matches"),
                    rank=row.get("rank"),
                    points=row.get("points"),
                    wins=row.get("wins"),
                    draws=row.get("draws"),
                    losses=row.get("losses"),
                    goals_for=row.get("goals_for"),
                    goals_against=row.get("goals_against"),
                    goal_difference=row.get("goal_difference"),
                    assists=row.get("assists"),
                    average_ball_possession=row.get("average_ball_possession"),
                    clean_sheets=row.get("clean_sheets"),
                    own_goals=row.get("own_goals"),
                    shots=row.get("shots"),
                    shots_on_target=row.get("shots_on_target"),
                    shots_off_target=row.get("shots_off_target"),
                    shots_against=row.get("shots_against"),
                    shots_on_target_against=row.get("shots_on_target_against"),
                    shots_from_inside_the_box=row.get("shots_from_inside_the_box"),
                    shots_from_inside_the_box_against=row.get("shots_from_inside_the_box_against"),
                    shots_from_outside_the_box=row.get("shots_from_outside_the_box"),
                    shots_from_outside_the_box_against=row.get(
                        "shots_from_outside_the_box_against"
                    ),
                    big_chances=row.get("big_chances"),
                    big_chances_against=row.get("big_chances_against"),
                    big_chances_created=row.get("big_chances_created"),
                    big_chances_created_against=row.get("big_chances_created_against"),
                    big_chances_missed=row.get("big_chances_missed"),
                    corners=row.get("corners"),
                    corners_against=row.get("corners_against"),
                    accurate_passes=row.get("accurate_passes"),
                    accurate_passes_against=row.get("accurate_passes_against"),
                    total_passes=row.get("total_passes"),
                    accurate_passes_percentage=row.get("accurate_passes_percentage"),
                    accurate_long_balls=row.get("accurate_long_balls"),
                    total_long_balls=row.get("total_long_balls"),
                    accurate_long_balls_percentage=row.get("accurate_long_balls_percentage"),
                    accurate_crosses=row.get("accurate_crosses"),
                    total_crosses=row.get("total_crosses"),
                    accurate_crosses_percentage=row.get("accurate_crosses_percentage"),
                    ball_recovery=row.get("ball_recovery"),
                    possession_lost=row.get("possession_lost"),
                    tackles=row.get("tackles"),
                    tackles_against=row.get("tackles_against"),
                    interceptions=row.get("interceptions"),
                    interceptions_against=row.get("interceptions_against"),
                    clearances=row.get("clearances"),
                    clearances_against=row.get("clearances_against"),
                    saves=row.get("saves"),
                    duels_won=row.get("duels_won"),
                    duels_won_percentage=row.get("duels_won_percentage"),
                    aerial_duels_won=row.get("aerial_duels_won"),
                    aerial_duels_won_percentage=row.get("aerial_duels_won_percentage"),
                    ground_duels_won=row.get("ground_duels_won"),
                    ground_duels_won_percentage=row.get("ground_duels_won_percentage"),
                    successful_dribbles=row.get("successful_dribbles"),
                    fouls=row.get("fouls"),
                    yellow_cards=row.get("yellow_cards"),
                    red_cards=row.get("red_cards"),
                    yellow_cards_against=row.get("yellow_cards_against"),
                    red_cards_against=row.get("red_cards_against"),
                    offsides=row.get("offsides"),
                    offsides_against=row.get("offsides_against"),
                    penalties_taken=row.get("penalties_taken"),
                    penalty_goals=row.get("penalty_goals"),
                    penalty_goals_conceded=row.get("penalty_goals_conceded"),
                    goals_from_inside_the_box=row.get("goals_from_inside_the_box"),
                    goals_from_outside_the_box=row.get("goals_from_outside_the_box"),
                    headed_goals=row.get("headed_goals"),
                    hit_woodwork=row.get("hit_woodwork"),
                    expected_goals=row.get("expected_goals"),
                    expected_assists=row.get("expected_assists"),
                    awarded_matches=row.get("awarded_matches"),
                    blocked_scoring_attempt=row.get("blocked_scoring_attempt"),
                    blocked_scoring_attempt_against=row.get("blocked_scoring_attempt_against"),
                    errors_leading_to_goal=row.get("errors_leading_to_goal"),
                    errors_leading_to_goal_against=row.get("errors_leading_to_goal_against"),
                    errors_leading_to_shot=row.get("errors_leading_to_shot"),
                    errors_leading_to_shot_against=row.get("errors_leading_to_shot_against"),
                    free_kicks=row.get("free_kicks"),
                    goal_kicks=row.get("goal_kicks"),
                    throw_ins=row.get("throw_ins"),
                )
                cteam = None
                if provider_team_id:
                    cteam = resolve_canonical_team(
                        competition_season=competition_season,
                        provider=Provider.SOFASCORE,
                        provider_team_id=provider_team_id,
                        team_name=src.team_name,
                        run=run,
                    )
                src.canonical_team = cteam
                src.save(update_fields=["canonical_team"])
    except Exception as exc:  # noqa: BLE001
        _mark_run_failed(run, f"Sofascore team persistence failed: {exc}")
        return

    published_check = validate_sofascore_team_slice(competition_season)
    if not published_check.ok:
        _mark_run_failed(run, published_check.message)
        return

    _mark_run_success(
        run,
        stats={
            "teams": len(rows),
            "overall_stats_coverage": sum(1 for row in rows if row.get("has_overall_stats")),
        },
    )


def run_team_merge_job(competition_season: CompetitionSeason, *, run: IngestionRun) -> None:
    _mark_run_start(run)
    try:
        execute_team_merge_for_slice(competition_season, merge_run=run)
    except Exception as exc:  # noqa: BLE001
        _mark_run_failed(run, str(exc))
        return

    source_rows = list(
        SofascoreTeamSeasonSource.objects.filter(
            competition_season=competition_season,
            canonical_team__isnull=False,
        )
    )
    candidate_check = validate_team_merge_candidate(competition_season, source_rows)
    if not candidate_check.ok:
        _mark_run_failed(run, candidate_check.message)
        return

    count = MergedTeamSeason.objects.filter(
        competition_season=competition_season,
        is_current=True,
    ).count()
    if count == 0:
        _mark_run_failed(run, "Team merge produced zero rows.")
        return
    _mark_run_success(run, stats={"merged_rows": count})
