from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from ingestion.models import (
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    MergedTeamSeason,
    SofascoreTeamSeasonSource,
)
from ingestion.services.validation import can_merge_team_slice, latest_success_run, validate_team_merge_candidate


@transaction.atomic
def execute_team_merge_for_slice(
    competition_season: CompetitionSeason,
    *,
    merge_run: IngestionRun | None = None,
) -> None:
    gate = can_merge_team_slice(competition_season)
    if not gate.ok:
        raise ValueError(gate.message)

    source_run = latest_success_run(competition_season, IngestionKind.SOFASCORE_TEAM)
    if source_run is None:
        raise ValueError("Team merge requires a successful Sofascore team ingestion run.")

    source_rows = list(
        SofascoreTeamSeasonSource.objects.filter(
            competition_season=competition_season,
            canonical_team__isnull=False,
        ).select_related("canonical_team")
    )

    candidate_check = validate_team_merge_candidate(competition_season, source_rows)
    if not candidate_check.ok:
        raise ValueError(candidate_check.message)

    now = timezone.now()
    to_create: list[MergedTeamSeason] = []
    for src in source_rows:
        to_create.append(
            MergedTeamSeason(
                competition_season=competition_season,
                canonical_team=src.canonical_team,
                matches=src.matches,
                rank=src.rank,
                points=src.points,
                wins=src.wins,
                draws=src.draws,
                losses=src.losses,
                goals_for=src.goals_for,
                goals_against=src.goals_against,
                goal_difference=src.goal_difference,
                assists=src.assists,
                average_ball_possession=src.average_ball_possession,
                clean_sheets=src.clean_sheets,
                own_goals=src.own_goals,
                shots=src.shots,
                shots_on_target=src.shots_on_target,
                shots_off_target=src.shots_off_target,
                shots_against=src.shots_against,
                shots_on_target_against=src.shots_on_target_against,
                shots_from_inside_the_box=src.shots_from_inside_the_box,
                shots_from_inside_the_box_against=src.shots_from_inside_the_box_against,
                shots_from_outside_the_box=src.shots_from_outside_the_box,
                shots_from_outside_the_box_against=src.shots_from_outside_the_box_against,
                big_chances=src.big_chances,
                big_chances_against=src.big_chances_against,
                big_chances_created=src.big_chances_created,
                big_chances_created_against=src.big_chances_created_against,
                big_chances_missed=src.big_chances_missed,
                corners=src.corners,
                corners_against=src.corners_against,
                accurate_passes=src.accurate_passes,
                accurate_passes_against=src.accurate_passes_against,
                total_passes=src.total_passes,
                accurate_passes_percentage=src.accurate_passes_percentage,
                accurate_long_balls=src.accurate_long_balls,
                total_long_balls=src.total_long_balls,
                accurate_long_balls_percentage=src.accurate_long_balls_percentage,
                accurate_crosses=src.accurate_crosses,
                total_crosses=src.total_crosses,
                accurate_crosses_percentage=src.accurate_crosses_percentage,
                ball_recovery=src.ball_recovery,
                possession_lost=src.possession_lost,
                tackles=src.tackles,
                tackles_against=src.tackles_against,
                interceptions=src.interceptions,
                interceptions_against=src.interceptions_against,
                clearances=src.clearances,
                clearances_against=src.clearances_against,
                saves=src.saves,
                duels_won=src.duels_won,
                duels_won_percentage=src.duels_won_percentage,
                aerial_duels_won=src.aerial_duels_won,
                aerial_duels_won_percentage=src.aerial_duels_won_percentage,
                ground_duels_won=src.ground_duels_won,
                ground_duels_won_percentage=src.ground_duels_won_percentage,
                successful_dribbles=src.successful_dribbles,
                fouls=src.fouls,
                yellow_cards=src.yellow_cards,
                red_cards=src.red_cards,
                yellow_cards_against=src.yellow_cards_against,
                red_cards_against=src.red_cards_against,
                offsides=src.offsides,
                offsides_against=src.offsides_against,
                penalties_taken=src.penalties_taken,
                penalty_goals=src.penalty_goals,
                penalty_goals_conceded=src.penalty_goals_conceded,
                goals_from_inside_the_box=src.goals_from_inside_the_box,
                goals_from_outside_the_box=src.goals_from_outside_the_box,
                headed_goals=src.headed_goals,
                hit_woodwork=src.hit_woodwork,
                expected_goals=src.expected_goals,
                expected_assists=src.expected_assists,
                sofascore_team_ingestion_run=source_run,
                team_merge_ingestion_run=merge_run,
                is_current=True,
            )
        )

    previous_rows = list(
        MergedTeamSeason.objects.filter(
            competition_season=competition_season,
            is_current=True,
        )
    )
    previous_by_team_id = {row.canonical_team_id: row for row in previous_rows}

    MergedTeamSeason.objects.filter(
        competition_season=competition_season,
        is_current=True,
    ).update(is_current=False, superseded_at=now)
    MergedTeamSeason.objects.bulk_create(to_create)

    if merge_run is not None:
        for new_row in MergedTeamSeason.objects.filter(
            competition_season=competition_season,
            team_merge_ingestion_run=merge_run,
            is_current=True,
        ):
            previous = previous_by_team_id.get(new_row.canonical_team_id)
            if previous:
                previous.superseded_by = new_row
                previous.save(update_fields=["superseded_by"])
