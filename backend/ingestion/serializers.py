from rest_framework import serializers

from ingestion.models import CanonicalTeam, MergedPlayerSeason, MergedTeamSeason


class MergedPlayerSeasonSerializer(serializers.ModelSerializer):
    canonical_player_id = serializers.IntegerField(read_only=True)
    canonical_player_name = serializers.CharField(source="canonical_player.display_name", read_only=True)
    canonical_team_id = serializers.IntegerField(
        source="canonical_display_team_id",
        read_only=True,
        allow_null=True,
    )
    canonical_team_name = serializers.CharField(
        source="canonical_display_team.name",
        read_only=True,
        allow_null=True,
    )
    secondary_canonical_team_ids = serializers.ListField(
        child=serializers.IntegerField(),
        source="secondary_display_team_ids",
        read_only=True,
    )
    secondary_canonical_team_names = serializers.SerializerMethodField()
    competition_code = serializers.CharField(
        source="competition_season.competition.short_code",
        read_only=True,
    )
    season_label = serializers.CharField(
        source="competition_season.season.label",
        read_only=True,
    )

    def get_secondary_canonical_team_names(self, obj: MergedPlayerSeason) -> list[str]:
        ids = obj.secondary_display_team_ids or []
        if not ids:
            return []
        teams = CanonicalTeam.objects.filter(pk__in=ids)
        by_id = {t.pk: t.name for t in teams}
        return [by_id[i] for i in ids if i in by_id]

    class Meta:
        model = MergedPlayerSeason
        fields = [
            "id",
            "canonical_player_id",
            "canonical_player_name",
            "canonical_team_id",
            "canonical_team_name",
            "secondary_canonical_team_ids",
            "secondary_canonical_team_names",
            "competition_season",
            "competition_code",
            "season_label",
            "position_group",
            "native_position",
            "minutes",
            "metadata_authority",
            "us_goals",
            "us_assists",
            "us_shots",
            "us_key_passes",
            "us_npg",
            "us_xg",
            "us_npxg",
            "us_xa",
            "us_xgchain",
            "us_xgbuildup",
            "us_games",
            "us_yellow_cards",
            "us_red_cards",
            "ss_rating",
            "ss_tackles",
            "ss_interceptions",
            "ss_clearances",
            "ss_error_lead_to_goal",
            "ss_outfielder_blocks",
            "ss_accurate_passes",
            "ss_inaccurate_passes",
            "ss_total_passes",
            "ss_key_passes",
            "ss_accurate_crosses",
            "ss_accurate_long_balls",
            "ss_saves",
            "ss_clean_sheet",
            "ss_penalty_save",
            "ss_appearances",
            "ss_big_chances_created",
            "ss_accurate_passes_percentage",
            "ss_saved_shots_from_inside_the_box",
            "ss_runs_out",
            "is_current",
            "superseded_at",
        ]


class MergedTeamSeasonSerializer(serializers.ModelSerializer):
    canonical_team_id = serializers.IntegerField(read_only=True)
    canonical_team_name = serializers.CharField(source="canonical_team.name", read_only=True)
    competition_code = serializers.CharField(
        source="competition_season.competition.short_code",
        read_only=True,
    )
    season_label = serializers.CharField(
        source="competition_season.season.label",
        read_only=True,
    )

    class Meta:
        model = MergedTeamSeason
        fields = [
            "id",
            "canonical_team_id",
            "canonical_team_name",
            "competition_season",
            "competition_code",
            "season_label",
            "matches",
            "rank",
            "points",
            "wins",
            "draws",
            "losses",
            "goals_for",
            "goals_against",
            "goal_difference",
            "assists",
            "average_ball_possession",
            "clean_sheets",
            "own_goals",
            "shots",
            "shots_on_target",
            "shots_off_target",
            "shots_against",
            "shots_on_target_against",
            "shots_from_inside_the_box",
            "shots_from_inside_the_box_against",
            "shots_from_outside_the_box",
            "shots_from_outside_the_box_against",
            "big_chances",
            "big_chances_against",
            "big_chances_created",
            "big_chances_created_against",
            "big_chances_missed",
            "corners",
            "corners_against",
            "accurate_passes",
            "accurate_passes_against",
            "total_passes",
            "accurate_passes_percentage",
            "accurate_long_balls",
            "total_long_balls",
            "accurate_long_balls_percentage",
            "accurate_crosses",
            "total_crosses",
            "accurate_crosses_percentage",
            "ball_recovery",
            "possession_lost",
            "tackles",
            "tackles_against",
            "interceptions",
            "interceptions_against",
            "clearances",
            "clearances_against",
            "saves",
            "duels_won",
            "duels_won_percentage",
            "aerial_duels_won",
            "aerial_duels_won_percentage",
            "ground_duels_won",
            "ground_duels_won_percentage",
            "successful_dribbles",
            "fouls",
            "yellow_cards",
            "red_cards",
            "yellow_cards_against",
            "red_cards_against",
            "offsides",
            "offsides_against",
            "penalties_taken",
            "penalty_goals",
            "penalty_goals_conceded",
            "goals_from_inside_the_box",
            "goals_from_outside_the_box",
            "headed_goals",
            "hit_woodwork",
            "expected_goals",
            "expected_assists",
            "is_current",
            "superseded_at",
        ]
