from __future__ import annotations

from django.db import models


class Provider(models.TextChoices):
    UNDERSTAT = "understat", "Understat"
    SOFASCORE = "sofascore", "Sofascore"


class IngestionKind(models.TextChoices):
    REEP_SYNC = "reep_sync", "Reep sync"
    UNDERSTAT = "understat", "Understat"
    SOFASCORE = "sofascore", "Sofascore"
    SOFASCORE_TEAM = "sofascore_team", "Sofascore team"
    MERGE = "merge", "Merge"
    TEAM_MERGE = "team_merge", "Team merge"
    DERIVED = "derived", "Derived stats"
    GALAXY = "galaxy", "Galaxy embeddings"


class IngestionRunStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"


class MatchMethod(models.TextChoices):
    AUTO = "auto", "Automatic"
    MANUAL = "manual", "Manual"


class MetadataAuthority(models.TextChoices):
    UNDERSTAT = "understat", "Understat"
    SOFASCORE = "sofascore", "Sofascore"


class PositionGroup(models.TextChoices):
    GK = "GK", "Goalkeeper"
    DEF = "DEF", "Defender"
    MID = "MID", "Midfielder"
    FWD = "FWD", "Forward"
    UNKNOWN = "UNK", "Unknown"


class Competition(models.Model):
    name = models.CharField(max_length=200)
    short_code = models.CharField(max_length=32, db_index=True)
    country = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Season(models.Model):
    label = models.CharField(max_length=32, unique=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-sort_order", "label"]

    def __str__(self) -> str:
        return self.label


class CompetitionSeason(models.Model):
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name="seasons")
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="competition_links")
    understat_league = models.CharField(max_length=32, default="EPL")
    understat_season_year = models.CharField(
        max_length=8,
        help_text="Understat URL segment, e.g. 2025 for 2025-26 depending on Understat convention.",
    )
    sofascore_unique_tournament_id = models.PositiveIntegerField()
    sofascore_season_id = models.PositiveIntegerField()
    expected_team_count = models.PositiveSmallIntegerField(default=20)
    min_merged_team_count = models.PositiveSmallIntegerField(default=18)
    min_team_stats_coverage_count = models.PositiveSmallIntegerField(default=18)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition", "season"],
                name="uniq_competition_season",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.competition.short_code} {self.season.label}"


class IngestionRun(models.Model):
    kind = models.CharField(max_length=32, choices=IngestionKind.choices, db_index=True)
    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ingestion_runs",
    )
    status = models.CharField(
        max_length=16,
        choices=IngestionRunStatus.choices,
        default=IngestionRunStatus.PENDING,
        db_index=True,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_detail = models.TextField(blank=True)
    stats = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]

    def __str__(self) -> str:
        scope = self.competition_season or "global"
        return f"{self.kind} {self.status} {scope}"


class ReepPlayerRow(models.Model):
    """Scoped offline reep identity rows (subset import, not full public register)."""

    reep_id = models.CharField(max_length=128, unique=True, db_index=True)
    full_name = models.CharField(max_length=200)
    position = models.CharField(max_length=64, blank=True)
    position_detail = models.CharField(max_length=128, blank=True)
    understat_player_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    sofascore_player_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["understat_player_id"],
                condition=models.Q(understat_player_id__isnull=False),
                name="uniq_reep_player_understat_id",
            ),
            models.UniqueConstraint(
                fields=["sofascore_player_id"],
                condition=models.Q(sofascore_player_id__isnull=False),
                name="uniq_reep_player_sofascore_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.reep_id})"


class ReepTeamRow(models.Model):
    reep_id = models.CharField(max_length=128, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    understat_team_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    sofascore_team_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["understat_team_id"],
                condition=models.Q(understat_team_id__isnull=False),
                name="uniq_reep_team_understat_id",
            ),
            models.UniqueConstraint(
                fields=["sofascore_team_id"],
                condition=models.Q(sofascore_team_id__isnull=False),
                name="uniq_reep_team_sofascore_id",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class CanonicalPlayer(models.Model):
    reep_id = models.CharField(max_length=128, null=True, blank=True, unique=True, db_index=True)
    display_name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_name"]

    def __str__(self) -> str:
        return self.display_name


class CanonicalTeam(models.Model):
    reep_id = models.CharField(max_length=128, null=True, blank=True, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ProviderPlayerMapping(models.Model):
    canonical_player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.CASCADE,
        related_name="provider_mappings",
    )
    provider = models.CharField(max_length=32, choices=Provider.choices)
    provider_player_id = models.CharField(max_length=64, db_index=True)
    match_method = models.CharField(
        max_length=16,
        choices=MatchMethod.choices,
        default=MatchMethod.AUTO,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_player_id"],
                name="uniq_provider_player_mapping",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider} {self.provider_player_id} -> {self.canonical_player_id}"


class ProviderTeamMapping(models.Model):
    canonical_team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.CASCADE,
        related_name="provider_mappings",
    )
    provider = models.CharField(max_length=32, choices=Provider.choices)
    provider_team_id = models.CharField(max_length=64, db_index=True)
    match_method = models.CharField(
        max_length=16,
        choices=MatchMethod.choices,
        default=MatchMethod.AUTO,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_team_id"],
                name="uniq_provider_team_mapping",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider} {self.provider_team_id} -> {self.canonical_team_id}"


class UnmatchedProviderPlayer(models.Model):
    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="unmatched_players",
    )
    provider = models.CharField(max_length=32, choices=Provider.choices)
    provider_player_id = models.CharField(max_length=64, db_index=True)
    player_name = models.CharField(max_length=200, blank=True)
    first_seen_run = models.ForeignKey(
        IngestionRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="unmatched_players_introduced",
    )
    resolved_player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quarantine_resolutions",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition_season", "provider", "provider_player_id"],
                name="uniq_unmatched_player_slice",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider} {self.provider_player_id}"


class UnmatchedProviderTeam(models.Model):
    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="unmatched_teams",
    )
    provider = models.CharField(max_length=32, choices=Provider.choices)
    provider_team_id = models.CharField(max_length=64, db_index=True)
    team_name = models.CharField(max_length=200, blank=True)
    first_seen_run = models.ForeignKey(
        IngestionRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="unmatched_teams_introduced",
    )
    resolved_team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quarantine_team_resolutions",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition_season", "provider", "provider_team_id"],
                name="uniq_unmatched_team_slice",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider} {self.provider_team_id}"


class UnderstatPlayerSeasonSource(models.Model):
    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="understat_sources",
    )
    ingestion_run = models.ForeignKey(
        IngestionRun,
        on_delete=models.CASCADE,
        related_name="understat_rows",
    )
    provider_player_id = models.CharField(max_length=64, db_index=True)
    provider_team_id = models.CharField(max_length=64, blank=True, db_index=True)
    provider_team_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="Ordered Understat team ids for each comma-separated club in team_title (from league teams payload).",
    )
    player_name = models.CharField(max_length=200, blank=True)
    team_name = models.CharField(max_length=200, blank=True)
    position_raw = models.CharField(max_length=64, blank=True)
    games = models.PositiveIntegerField(null=True, blank=True)
    minutes = models.PositiveIntegerField(null=True, blank=True)
    goals = models.PositiveIntegerField(null=True, blank=True)
    assists = models.PositiveIntegerField(null=True, blank=True)
    shots = models.PositiveIntegerField(null=True, blank=True)
    key_passes = models.PositiveIntegerField(null=True, blank=True)
    npg = models.PositiveIntegerField(null=True, blank=True)
    xg = models.FloatField(null=True, blank=True)
    npxg = models.FloatField(null=True, blank=True)
    xa = models.FloatField(null=True, blank=True)
    xgchain = models.FloatField(null=True, blank=True)
    xgbuildup = models.FloatField(null=True, blank=True)
    yellow_cards = models.PositiveIntegerField(null=True, blank=True)
    red_cards = models.PositiveIntegerField(null=True, blank=True)
    canonical_player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="understat_sources",
    )
    canonical_team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="understat_sources",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition_season", "provider_player_id"],
                name="uniq_understat_player_per_slice",
            ),
        ]


class SofascorePlayerSeasonSource(models.Model):
    """
    One normalized row per Sofascore player for a competition-season slice.

    Typed columns mirror Sofascore statistics API `group` payloads (camelCase in JSON).
    `group_stats` stores the verbatim per-group stat objects as returned by the API
    (excluding nested player/team), for debugging and forward-compatible fields.
    """

    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="sofascore_sources",
    )
    ingestion_run = models.ForeignKey(
        IngestionRun,
        on_delete=models.CASCADE,
        related_name="sofascore_rows",
    )
    provider_player_id = models.CharField(max_length=64, db_index=True)
    provider_team_id = models.CharField(max_length=64, blank=True, db_index=True)
    player_name = models.CharField(max_length=200, blank=True)
    team_name = models.CharField(max_length=200, blank=True)
    position_raw = models.CharField(max_length=64, blank=True)
    group_stats = models.JSONField(default=dict, blank=True)
    appearances = models.PositiveIntegerField(null=True, blank=True)
    minutes = models.PositiveIntegerField(null=True, blank=True)
    rating = models.FloatField(null=True, blank=True)
    summary_goals = models.PositiveIntegerField(null=True, blank=True)
    summary_assists = models.PositiveIntegerField(null=True, blank=True)
    summary_expected_goals = models.FloatField(null=True, blank=True)
    summary_successful_dribbles = models.PositiveIntegerField(null=True, blank=True)
    summary_accurate_passes_percentage = models.FloatField(null=True, blank=True)
    tackles = models.PositiveIntegerField(null=True, blank=True)
    interceptions = models.PositiveIntegerField(null=True, blank=True)
    clearances = models.PositiveIntegerField(null=True, blank=True)
    error_lead_to_goal = models.PositiveIntegerField(null=True, blank=True)
    outfielder_blocks = models.PositiveIntegerField(null=True, blank=True)
    big_chances_created = models.PositiveIntegerField(null=True, blank=True)
    accurate_passes = models.PositiveIntegerField(null=True, blank=True)
    inaccurate_passes = models.PositiveIntegerField(null=True, blank=True)
    total_passes = models.PositiveIntegerField(null=True, blank=True)
    key_passes = models.PositiveIntegerField(null=True, blank=True)
    tackles_won = models.PositiveIntegerField(null=True, blank=True)
    tackles_won_percentage = models.FloatField(null=True, blank=True)
    shots_on_target = models.PositiveIntegerField(null=True, blank=True)
    shots_off_target = models.PositiveIntegerField(null=True, blank=True)
    aerial_duels_won = models.PositiveIntegerField(null=True, blank=True)
    ground_duels_won = models.PositiveIntegerField(null=True, blank=True)
    ball_recoveries = models.PositiveIntegerField(null=True, blank=True)
    successful_dribbles_percentage = models.FloatField(null=True, blank=True)
    fouls = models.PositiveIntegerField(null=True, blank=True)
    offsides = models.PositiveIntegerField(null=True, blank=True)
    accurate_passes_percentage = models.FloatField(null=True, blank=True)
    accurate_crosses = models.PositiveIntegerField(null=True, blank=True)
    accurate_long_balls = models.PositiveIntegerField(null=True, blank=True)
    saves = models.PositiveIntegerField(null=True, blank=True)
    clean_sheet = models.PositiveIntegerField(null=True, blank=True)
    penalty_save = models.PositiveIntegerField(null=True, blank=True)
    saved_shots_from_inside_the_box = models.PositiveIntegerField(null=True, blank=True)
    runs_out = models.PositiveIntegerField(null=True, blank=True)
    canonical_player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sofascore_sources",
    )
    canonical_team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sofascore_sources",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition_season", "provider_player_id"],
                name="uniq_sofascore_player_per_slice",
            ),
        ]


class SofascoreTeamSeasonSource(models.Model):
    """
    One normalized row per Sofascore team for a competition-season slice.

    `standings_row_json` preserves the raw row from `/standings/total`.
    `overall_stats_json` preserves the raw `statistics` object from
    `/statistics/overall` for the same team and season.
    """

    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="sofascore_team_sources",
    )
    ingestion_run = models.ForeignKey(
        IngestionRun,
        on_delete=models.CASCADE,
        related_name="sofascore_team_rows",
    )
    provider_team_id = models.CharField(max_length=64, db_index=True)
    team_name = models.CharField(max_length=200, blank=True)
    standings_row_json = models.JSONField(default=dict, blank=True)
    overall_stats_json = models.JSONField(default=dict, blank=True)
    has_overall_stats = models.BooleanField(default=False, db_index=True)

    matches = models.PositiveIntegerField(null=True, blank=True)
    rank = models.PositiveIntegerField(null=True, blank=True)
    points = models.PositiveIntegerField(null=True, blank=True)
    wins = models.PositiveIntegerField(null=True, blank=True)
    draws = models.PositiveIntegerField(null=True, blank=True)
    losses = models.PositiveIntegerField(null=True, blank=True)
    goals_for = models.PositiveIntegerField(null=True, blank=True)
    goals_against = models.PositiveIntegerField(null=True, blank=True)
    goal_difference = models.IntegerField(null=True, blank=True)

    assists = models.PositiveIntegerField(null=True, blank=True)
    average_ball_possession = models.FloatField(null=True, blank=True)
    clean_sheets = models.PositiveIntegerField(null=True, blank=True)
    own_goals = models.PositiveIntegerField(null=True, blank=True)
    shots = models.PositiveIntegerField(null=True, blank=True)
    shots_on_target = models.PositiveIntegerField(null=True, blank=True)
    shots_off_target = models.PositiveIntegerField(null=True, blank=True)
    shots_against = models.PositiveIntegerField(null=True, blank=True)
    shots_on_target_against = models.PositiveIntegerField(null=True, blank=True)
    shots_from_inside_the_box = models.PositiveIntegerField(null=True, blank=True)
    shots_from_inside_the_box_against = models.PositiveIntegerField(null=True, blank=True)
    shots_from_outside_the_box = models.PositiveIntegerField(null=True, blank=True)
    shots_from_outside_the_box_against = models.PositiveIntegerField(null=True, blank=True)
    big_chances = models.PositiveIntegerField(null=True, blank=True)
    big_chances_against = models.PositiveIntegerField(null=True, blank=True)
    big_chances_created = models.PositiveIntegerField(null=True, blank=True)
    big_chances_created_against = models.PositiveIntegerField(null=True, blank=True)
    big_chances_missed = models.PositiveIntegerField(null=True, blank=True)
    corners = models.PositiveIntegerField(null=True, blank=True)
    corners_against = models.PositiveIntegerField(null=True, blank=True)
    accurate_passes = models.PositiveIntegerField(null=True, blank=True)
    accurate_passes_against = models.PositiveIntegerField(null=True, blank=True)
    total_passes = models.PositiveIntegerField(null=True, blank=True)
    accurate_passes_percentage = models.FloatField(null=True, blank=True)
    accurate_long_balls = models.PositiveIntegerField(null=True, blank=True)
    total_long_balls = models.PositiveIntegerField(null=True, blank=True)
    accurate_long_balls_percentage = models.FloatField(null=True, blank=True)
    accurate_crosses = models.PositiveIntegerField(null=True, blank=True)
    total_crosses = models.PositiveIntegerField(null=True, blank=True)
    accurate_crosses_percentage = models.FloatField(null=True, blank=True)
    ball_recovery = models.PositiveIntegerField(null=True, blank=True)
    possession_lost = models.PositiveIntegerField(null=True, blank=True)
    tackles = models.PositiveIntegerField(null=True, blank=True)
    tackles_against = models.PositiveIntegerField(null=True, blank=True)
    interceptions = models.PositiveIntegerField(null=True, blank=True)
    interceptions_against = models.PositiveIntegerField(null=True, blank=True)
    clearances = models.PositiveIntegerField(null=True, blank=True)
    clearances_against = models.PositiveIntegerField(null=True, blank=True)
    saves = models.PositiveIntegerField(null=True, blank=True)
    duels_won = models.PositiveIntegerField(null=True, blank=True)
    duels_won_percentage = models.FloatField(null=True, blank=True)
    aerial_duels_won = models.PositiveIntegerField(null=True, blank=True)
    aerial_duels_won_percentage = models.FloatField(null=True, blank=True)
    ground_duels_won = models.PositiveIntegerField(null=True, blank=True)
    ground_duels_won_percentage = models.FloatField(null=True, blank=True)
    successful_dribbles = models.PositiveIntegerField(null=True, blank=True)
    fouls = models.PositiveIntegerField(null=True, blank=True)
    yellow_cards = models.PositiveIntegerField(null=True, blank=True)
    red_cards = models.PositiveIntegerField(null=True, blank=True)
    yellow_cards_against = models.PositiveIntegerField(null=True, blank=True)
    red_cards_against = models.PositiveIntegerField(null=True, blank=True)
    offsides = models.PositiveIntegerField(null=True, blank=True)
    offsides_against = models.PositiveIntegerField(null=True, blank=True)
    penalties_taken = models.PositiveIntegerField(null=True, blank=True)
    penalty_goals = models.PositiveIntegerField(null=True, blank=True)
    penalty_goals_conceded = models.PositiveIntegerField(null=True, blank=True)
    goals_from_inside_the_box = models.PositiveIntegerField(null=True, blank=True)
    goals_from_outside_the_box = models.PositiveIntegerField(null=True, blank=True)
    headed_goals = models.PositiveIntegerField(null=True, blank=True)
    hit_woodwork = models.PositiveIntegerField(null=True, blank=True)

    # Sofascore overall statistics (when provided).
    expected_goals = models.FloatField(null=True, blank=True)
    expected_assists = models.FloatField(null=True, blank=True)

    # Source-only typed fields helpful for debugging/validation.
    awarded_matches = models.PositiveIntegerField(null=True, blank=True)
    blocked_scoring_attempt = models.PositiveIntegerField(null=True, blank=True)
    blocked_scoring_attempt_against = models.PositiveIntegerField(null=True, blank=True)
    errors_leading_to_goal = models.PositiveIntegerField(null=True, blank=True)
    errors_leading_to_goal_against = models.PositiveIntegerField(null=True, blank=True)
    errors_leading_to_shot = models.PositiveIntegerField(null=True, blank=True)
    errors_leading_to_shot_against = models.PositiveIntegerField(null=True, blank=True)
    free_kicks = models.PositiveIntegerField(null=True, blank=True)
    goal_kicks = models.PositiveIntegerField(null=True, blank=True)
    throw_ins = models.PositiveIntegerField(null=True, blank=True)

    canonical_team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sofascore_team_sources",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition_season", "provider_team_id"],
                name="uniq_sofascore_team_per_slice",
            ),
        ]
        indexes = [
            models.Index(fields=["competition_season", "canonical_team"]),
            models.Index(fields=["competition_season", "has_overall_stats"]),
        ]

    def __str__(self) -> str:
        return f"{self.team_name or self.provider_team_id} @ {self.competition_season}"


class PlayerSeasonClubSpell(models.Model):
    canonical_player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.CASCADE,
        related_name="club_spells",
    )
    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="club_spells",
    )
    canonical_team = models.ForeignKey(CanonicalTeam, on_delete=models.CASCADE)
    minutes = models.PositiveIntegerField(null=True, blank=True)
    source_provider = models.CharField(max_length=32, choices=Provider.choices)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["competition_season", "canonical_player"]),
        ]


class MergedPlayerSeason(models.Model):
    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="merged_rows",
    )
    canonical_player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.CASCADE,
        related_name="merged_seasons",
    )
    canonical_display_team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merged_display_team_rows",
    )
    secondary_display_team_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="Other canonical team ids from Understat multi-club season row (comma-separated team_title), excluding the primary SofaScore display team.",
    )
    position_group = models.CharField(
        max_length=8,
        choices=PositionGroup.choices,
        default=PositionGroup.UNKNOWN,
    )
    native_position = models.CharField(max_length=64, blank=True)
    minutes = models.PositiveIntegerField(null=True, blank=True)
    metadata_authority = models.CharField(
        max_length=16,
        choices=MetadataAuthority.choices,
        blank=True,
    )

    us_goals = models.PositiveIntegerField(null=True, blank=True)
    us_assists = models.PositiveIntegerField(null=True, blank=True)
    us_shots = models.PositiveIntegerField(null=True, blank=True)
    us_key_passes = models.PositiveIntegerField(null=True, blank=True)
    us_npg = models.PositiveIntegerField(null=True, blank=True)
    us_xg = models.FloatField(null=True, blank=True)
    us_npxg = models.FloatField(null=True, blank=True)
    us_xa = models.FloatField(null=True, blank=True)
    us_xgchain = models.FloatField(null=True, blank=True)
    us_xgbuildup = models.FloatField(null=True, blank=True)
    us_games = models.PositiveIntegerField(null=True, blank=True)
    us_yellow_cards = models.PositiveIntegerField(null=True, blank=True)
    us_red_cards = models.PositiveIntegerField(null=True, blank=True)

    ss_rating = models.FloatField(null=True, blank=True)
    ss_tackles = models.PositiveIntegerField(null=True, blank=True)
    ss_interceptions = models.PositiveIntegerField(null=True, blank=True)
    ss_clearances = models.PositiveIntegerField(null=True, blank=True)
    ss_error_lead_to_goal = models.PositiveIntegerField(null=True, blank=True)
    ss_outfielder_blocks = models.PositiveIntegerField(null=True, blank=True)
    ss_accurate_passes = models.PositiveIntegerField(null=True, blank=True)
    ss_inaccurate_passes = models.PositiveIntegerField(null=True, blank=True)
    ss_total_passes = models.PositiveIntegerField(null=True, blank=True)
    ss_key_passes = models.PositiveIntegerField(null=True, blank=True)
    ss_tackles_won = models.PositiveIntegerField(null=True, blank=True)
    ss_tackles_won_percentage = models.FloatField(null=True, blank=True)
    ss_shots_on_target = models.PositiveIntegerField(null=True, blank=True)
    ss_shots_off_target = models.PositiveIntegerField(null=True, blank=True)
    ss_aerial_duels_won = models.PositiveIntegerField(null=True, blank=True)
    ss_ground_duels_won = models.PositiveIntegerField(null=True, blank=True)
    ss_ball_recoveries = models.PositiveIntegerField(null=True, blank=True)
    ss_successful_dribbles_percentage = models.FloatField(null=True, blank=True)
    ss_fouls = models.PositiveIntegerField(null=True, blank=True)
    ss_offsides = models.PositiveIntegerField(null=True, blank=True)
    ss_accurate_crosses = models.PositiveIntegerField(null=True, blank=True)
    ss_accurate_long_balls = models.PositiveIntegerField(null=True, blank=True)
    ss_saves = models.PositiveIntegerField(null=True, blank=True)
    ss_clean_sheet = models.PositiveIntegerField(null=True, blank=True)
    ss_penalty_save = models.PositiveIntegerField(null=True, blank=True)
    ss_appearances = models.PositiveIntegerField(null=True, blank=True)
    ss_big_chances_created = models.PositiveIntegerField(null=True, blank=True)
    ss_accurate_passes_percentage = models.FloatField(null=True, blank=True)
    ss_saved_shots_from_inside_the_box = models.PositiveIntegerField(null=True, blank=True)
    ss_runs_out = models.PositiveIntegerField(null=True, blank=True)

    understat_ingestion_run = models.ForeignKey(
        IngestionRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merged_rows_understat",
    )
    sofascore_ingestion_run = models.ForeignKey(
        IngestionRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merged_rows_sofascore",
    )
    merge_ingestion_run = models.ForeignKey(
        IngestionRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merged_rows_merge_run",
    )

    is_current = models.BooleanField(default=True, db_index=True)
    superseded_at = models.DateTimeField(null=True, blank=True)
    superseded_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="predecessors",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition_season", "canonical_player"],
                condition=models.Q(is_current=True),
                name="uniq_current_merged_player_season",
            ),
        ]
        indexes = [
            models.Index(fields=["competition_season", "is_current"]),
            models.Index(fields=["competition_season", "canonical_display_team"]),
            models.Index(fields=["competition_season", "position_group"]),
        ]

    def __str__(self) -> str:
        return f"{self.canonical_player} @ {self.competition_season}"


class MergedTeamSeason(models.Model):
    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="merged_team_rows",
    )
    canonical_team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.CASCADE,
        related_name="merged_team_seasons",
    )

    matches = models.PositiveIntegerField(null=True, blank=True)
    rank = models.PositiveIntegerField(null=True, blank=True)
    points = models.PositiveIntegerField(null=True, blank=True)
    wins = models.PositiveIntegerField(null=True, blank=True)
    draws = models.PositiveIntegerField(null=True, blank=True)
    losses = models.PositiveIntegerField(null=True, blank=True)
    goals_for = models.PositiveIntegerField(null=True, blank=True)
    goals_against = models.PositiveIntegerField(null=True, blank=True)
    goal_difference = models.IntegerField(null=True, blank=True)

    assists = models.PositiveIntegerField(null=True, blank=True)
    average_ball_possession = models.FloatField(null=True, blank=True)
    clean_sheets = models.PositiveIntegerField(null=True, blank=True)
    own_goals = models.PositiveIntegerField(null=True, blank=True)
    shots = models.PositiveIntegerField(null=True, blank=True)
    shots_on_target = models.PositiveIntegerField(null=True, blank=True)
    shots_off_target = models.PositiveIntegerField(null=True, blank=True)
    shots_against = models.PositiveIntegerField(null=True, blank=True)
    shots_on_target_against = models.PositiveIntegerField(null=True, blank=True)
    shots_from_inside_the_box = models.PositiveIntegerField(null=True, blank=True)
    shots_from_inside_the_box_against = models.PositiveIntegerField(null=True, blank=True)
    shots_from_outside_the_box = models.PositiveIntegerField(null=True, blank=True)
    shots_from_outside_the_box_against = models.PositiveIntegerField(null=True, blank=True)
    big_chances = models.PositiveIntegerField(null=True, blank=True)
    big_chances_against = models.PositiveIntegerField(null=True, blank=True)
    big_chances_created = models.PositiveIntegerField(null=True, blank=True)
    big_chances_created_against = models.PositiveIntegerField(null=True, blank=True)
    big_chances_missed = models.PositiveIntegerField(null=True, blank=True)
    corners = models.PositiveIntegerField(null=True, blank=True)
    corners_against = models.PositiveIntegerField(null=True, blank=True)
    accurate_passes = models.PositiveIntegerField(null=True, blank=True)
    accurate_passes_against = models.PositiveIntegerField(null=True, blank=True)
    total_passes = models.PositiveIntegerField(null=True, blank=True)
    accurate_passes_percentage = models.FloatField(null=True, blank=True)
    accurate_long_balls = models.PositiveIntegerField(null=True, blank=True)
    total_long_balls = models.PositiveIntegerField(null=True, blank=True)
    accurate_long_balls_percentage = models.FloatField(null=True, blank=True)
    accurate_crosses = models.PositiveIntegerField(null=True, blank=True)
    total_crosses = models.PositiveIntegerField(null=True, blank=True)
    accurate_crosses_percentage = models.FloatField(null=True, blank=True)
    ball_recovery = models.PositiveIntegerField(null=True, blank=True)
    possession_lost = models.PositiveIntegerField(null=True, blank=True)
    tackles = models.PositiveIntegerField(null=True, blank=True)
    tackles_against = models.PositiveIntegerField(null=True, blank=True)
    interceptions = models.PositiveIntegerField(null=True, blank=True)
    interceptions_against = models.PositiveIntegerField(null=True, blank=True)
    clearances = models.PositiveIntegerField(null=True, blank=True)
    clearances_against = models.PositiveIntegerField(null=True, blank=True)
    saves = models.PositiveIntegerField(null=True, blank=True)
    duels_won = models.PositiveIntegerField(null=True, blank=True)
    duels_won_percentage = models.FloatField(null=True, blank=True)
    aerial_duels_won = models.PositiveIntegerField(null=True, blank=True)
    aerial_duels_won_percentage = models.FloatField(null=True, blank=True)
    ground_duels_won = models.PositiveIntegerField(null=True, blank=True)
    ground_duels_won_percentage = models.FloatField(null=True, blank=True)
    successful_dribbles = models.PositiveIntegerField(null=True, blank=True)
    fouls = models.PositiveIntegerField(null=True, blank=True)
    yellow_cards = models.PositiveIntegerField(null=True, blank=True)
    red_cards = models.PositiveIntegerField(null=True, blank=True)
    yellow_cards_against = models.PositiveIntegerField(null=True, blank=True)
    red_cards_against = models.PositiveIntegerField(null=True, blank=True)
    offsides = models.PositiveIntegerField(null=True, blank=True)
    offsides_against = models.PositiveIntegerField(null=True, blank=True)
    penalties_taken = models.PositiveIntegerField(null=True, blank=True)
    penalty_goals = models.PositiveIntegerField(null=True, blank=True)
    penalty_goals_conceded = models.PositiveIntegerField(null=True, blank=True)
    goals_from_inside_the_box = models.PositiveIntegerField(null=True, blank=True)
    goals_from_outside_the_box = models.PositiveIntegerField(null=True, blank=True)
    headed_goals = models.PositiveIntegerField(null=True, blank=True)
    hit_woodwork = models.PositiveIntegerField(null=True, blank=True)

    expected_goals = models.FloatField(null=True, blank=True)
    expected_assists = models.FloatField(null=True, blank=True)

    sofascore_team_ingestion_run = models.ForeignKey(
        IngestionRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merged_team_rows_sofascore",
    )
    team_merge_ingestion_run = models.ForeignKey(
        IngestionRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merged_team_rows_merge_run",
    )

    is_current = models.BooleanField(default=True, db_index=True)
    superseded_at = models.DateTimeField(null=True, blank=True)
    superseded_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_predecessors",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition_season", "canonical_team"],
                condition=models.Q(is_current=True),
                name="uniq_current_merged_team_season",
            ),
        ]
        indexes = [
            models.Index(fields=["competition_season", "is_current"]),
            models.Index(fields=["competition_season", "rank"]),
        ]

    def __str__(self) -> str:
        return f"{self.canonical_team} @ {self.competition_season}"


class PlayerSeasonDerivedStats(models.Model):
    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="derived_rows",
    )
    canonical_player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.CASCADE,
        related_name="derived_seasons",
    )
    canonical_display_team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_display_team_rows",
    )
    merged_player_season = models.ForeignKey(
        MergedPlayerSeason,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_rows",
    )
    derived_ingestion_run = models.ForeignKey(
        IngestionRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_rows",
    )
    formula_version = models.CharField(max_length=32, default="v1", db_index=True)
    position_group = models.CharField(
        max_length=8,
        choices=PositionGroup.choices,
        default=PositionGroup.UNKNOWN,
    )
    native_position = models.CharField(max_length=64, blank=True)
    minutes = models.PositiveIntegerField(null=True, blank=True)
    percentiles_eligible = models.BooleanField(default=False)
    percentiles_ineligibility_reason = models.CharField(max_length=64, blank=True)
    scores_eligible = models.BooleanField(default=False)
    scores_ineligibility_reason = models.CharField(max_length=64, blank=True)

    npxg = models.FloatField(null=True, blank=True)
    npxg_percentile = models.FloatField(null=True, blank=True)
    npxg_per_90 = models.FloatField(null=True, blank=True)
    npxg_per_90_percentile = models.FloatField(null=True, blank=True)
    xa = models.FloatField(null=True, blank=True)
    xa_percentile = models.FloatField(null=True, blank=True)
    xa_per_90 = models.FloatField(null=True, blank=True)
    xa_per_90_percentile = models.FloatField(null=True, blank=True)
    xgchain = models.FloatField(null=True, blank=True)
    xgchain_percentile = models.FloatField(null=True, blank=True)
    xgchain_per_90 = models.FloatField(null=True, blank=True)
    xgchain_per_90_percentile = models.FloatField(null=True, blank=True)
    xgbuildup = models.FloatField(null=True, blank=True)
    xgbuildup_percentile = models.FloatField(null=True, blank=True)
    xgbuildup_per_90 = models.FloatField(null=True, blank=True)
    xgbuildup_per_90_percentile = models.FloatField(null=True, blank=True)

    shots_per_90 = models.FloatField(null=True, blank=True)
    shots_per_90_percentile = models.FloatField(null=True, blank=True)
    goals_per_90 = models.FloatField(null=True, blank=True)
    goals_per_90_percentile = models.FloatField(null=True, blank=True)
    assists_per_90 = models.FloatField(null=True, blank=True)
    assists_per_90_percentile = models.FloatField(null=True, blank=True)
    key_passes_per_90 = models.FloatField(null=True, blank=True)
    key_passes_per_90_percentile = models.FloatField(null=True, blank=True)
    big_chances_created_per_90 = models.FloatField(null=True, blank=True)
    big_chances_created_per_90_percentile = models.FloatField(null=True, blank=True)
    successful_dribbles_per_90 = models.FloatField(null=True, blank=True)
    successful_dribbles_per_90_percentile = models.FloatField(null=True, blank=True)
    completed_passes_per_90 = models.FloatField(null=True, blank=True)
    completed_passes_per_90_percentile = models.FloatField(null=True, blank=True)

    goals_minus_xg = models.FloatField(null=True, blank=True)
    goals_minus_xg_percentile = models.FloatField(null=True, blank=True)
    goals_minus_npxg = models.FloatField(null=True, blank=True)
    goals_minus_npxg_percentile = models.FloatField(null=True, blank=True)
    npxg_per_shot = models.FloatField(null=True, blank=True)
    npxg_per_shot_percentile = models.FloatField(null=True, blank=True)
    xa_per_key_pass = models.FloatField(null=True, blank=True)
    xa_per_key_pass_percentile = models.FloatField(null=True, blank=True)
    buildup_share = models.FloatField(null=True, blank=True)
    buildup_share_percentile = models.FloatField(null=True, blank=True)
    chance_involvement_per_90 = models.FloatField(null=True, blank=True)
    chance_involvement_per_90_percentile = models.FloatField(null=True, blank=True)
    pass_accuracy = models.FloatField(null=True, blank=True)
    pass_accuracy_percentile = models.FloatField(null=True, blank=True)

    tackles_per_90 = models.FloatField(null=True, blank=True)
    tackles_per_90_percentile = models.FloatField(null=True, blank=True)
    interceptions_per_90 = models.FloatField(null=True, blank=True)
    interceptions_per_90_percentile = models.FloatField(null=True, blank=True)
    clearances_per_90 = models.FloatField(null=True, blank=True)
    clearances_per_90_percentile = models.FloatField(null=True, blank=True)
    blocks_per_90 = models.FloatField(null=True, blank=True)
    blocks_per_90_percentile = models.FloatField(null=True, blank=True)
    defensive_action_density = models.FloatField(null=True, blank=True)
    defensive_action_density_percentile = models.FloatField(null=True, blank=True)
    tackles_won = models.FloatField(null=True, blank=True)
    tackles_won_percentile = models.FloatField(null=True, blank=True)
    tackles_won_percentage = models.FloatField(null=True, blank=True)
    tackles_won_percentage_percentile = models.FloatField(null=True, blank=True)
    shots_on_target = models.FloatField(null=True, blank=True)
    shots_on_target_percentile = models.FloatField(null=True, blank=True)
    shots_off_target = models.FloatField(null=True, blank=True)
    shots_off_target_percentile = models.FloatField(null=True, blank=True)
    aerial_duels_won = models.FloatField(null=True, blank=True)
    aerial_duels_won_percentile = models.FloatField(null=True, blank=True)
    ground_duels_won = models.FloatField(null=True, blank=True)
    ground_duels_won_percentile = models.FloatField(null=True, blank=True)
    ball_recoveries = models.FloatField(null=True, blank=True)
    ball_recoveries_percentile = models.FloatField(null=True, blank=True)
    successful_dribbles_percentage = models.FloatField(null=True, blank=True)
    successful_dribbles_percentage_percentile = models.FloatField(null=True, blank=True)
    fouls = models.FloatField(null=True, blank=True)
    fouls_percentile = models.FloatField(null=True, blank=True)
    offsides = models.FloatField(null=True, blank=True)
    offsides_percentile = models.FloatField(null=True, blank=True)
    accurate_crosses_per_90 = models.FloatField(null=True, blank=True)
    accurate_crosses_per_90_percentile = models.FloatField(null=True, blank=True)
    accurate_long_balls_per_90 = models.FloatField(null=True, blank=True)
    accurate_long_balls_per_90_percentile = models.FloatField(null=True, blank=True)
    ball_recoveries_per_90 = models.FloatField(null=True, blank=True)
    ball_recoveries_per_90_percentile = models.FloatField(null=True, blank=True)
    ground_duels_won_per_90 = models.FloatField(null=True, blank=True)
    ground_duels_won_per_90_percentile = models.FloatField(null=True, blank=True)
    aerial_duels_won_per_90 = models.FloatField(null=True, blank=True)
    aerial_duels_won_per_90_percentile = models.FloatField(null=True, blank=True)
    fouls_per_90 = models.FloatField(null=True, blank=True)
    fouls_per_90_percentile = models.FloatField(null=True, blank=True)
    errors_lead_to_goal_per_90 = models.FloatField(null=True, blank=True)
    errors_lead_to_goal_per_90_percentile = models.FloatField(null=True, blank=True)
    offsides_per_90 = models.FloatField(null=True, blank=True)
    offsides_per_90_percentile = models.FloatField(null=True, blank=True)
    kp_share_per90 = models.FloatField(null=True, blank=True)
    kp_share_per90_percentile = models.FloatField(null=True, blank=True)
    inaccurate_pass_rate = models.FloatField(null=True, blank=True)
    inaccurate_pass_rate_percentile = models.FloatField(null=True, blank=True)

    finishing_shrunk_delta_per_shot = models.FloatField(null=True, blank=True)
    finishing_shrunk_delta_per_shot_percentile = models.FloatField(null=True, blank=True)
    sot_rate = models.FloatField(null=True, blank=True)
    sot_rate_percentile = models.FloatField(null=True, blank=True)

    finishing_score_raw = models.FloatField(null=True, blank=True)
    finishing_score = models.FloatField(null=True, blank=True)
    creation_score_raw = models.FloatField(null=True, blank=True)
    creation_score = models.FloatField(null=True, blank=True)
    buildup_score_raw = models.FloatField(null=True, blank=True)
    buildup_score = models.FloatField(null=True, blank=True)
    ball_winning_score_raw = models.FloatField(null=True, blank=True)
    ball_winning_score = models.FloatField(null=True, blank=True)
    involvement_score_raw = models.FloatField(null=True, blank=True)
    involvement_score = models.FloatField(null=True, blank=True)

    is_current = models.BooleanField(default=True, db_index=True)
    superseded_at = models.DateTimeField(null=True, blank=True)
    superseded_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="predecessor_rows",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition_season", "canonical_player"],
                condition=models.Q(is_current=True),
                name="uniq_current_derived_player_season",
            ),
        ]
        indexes = [
            models.Index(fields=["competition_season", "is_current"]),
            models.Index(fields=["competition_season", "position_group"]),
            models.Index(fields=["competition_season", "canonical_display_team"]),
            models.Index(fields=["competition_season", "formula_version"]),
        ]

    def __str__(self) -> str:
        return f"derived {self.canonical_player} @ {self.competition_season}"


class PlayerSeasonGkDerivedStats(models.Model):
    """
    Per-season goalkeeper metrics for the stat matrix (Sofascore-heavy; percentiles within GK cohort).
    """

    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="gk_derived_rows",
    )
    canonical_player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.CASCADE,
        related_name="gk_derived_seasons",
    )
    canonical_display_team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gk_derived_display_team_rows",
    )
    merged_player_season = models.ForeignKey(
        MergedPlayerSeason,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gk_derived_rows",
    )
    derived_ingestion_run = models.ForeignKey(
        IngestionRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gk_derived_rows",
    )
    formula_version = models.CharField(max_length=32, default="gk_v1", db_index=True)
    minutes = models.PositiveIntegerField(null=True, blank=True)
    appearances = models.PositiveIntegerField(null=True, blank=True)
    percentiles_eligible = models.BooleanField(default=False)
    percentiles_ineligibility_reason = models.CharField(max_length=64, blank=True)

    rating = models.FloatField(null=True, blank=True)
    rating_percentile = models.FloatField(null=True, blank=True)

    saves = models.PositiveIntegerField(null=True, blank=True)
    saves_percentile = models.FloatField(null=True, blank=True)
    saves_per_90 = models.FloatField(null=True, blank=True)
    saves_per_90_percentile = models.FloatField(null=True, blank=True)

    clean_sheets = models.PositiveIntegerField(null=True, blank=True)
    clean_sheets_percentile = models.FloatField(null=True, blank=True)
    clean_sheet_rate = models.FloatField(null=True, blank=True)
    clean_sheet_rate_percentile = models.FloatField(null=True, blank=True)

    penalty_saves = models.PositiveIntegerField(null=True, blank=True)
    penalty_saves_percentile = models.FloatField(null=True, blank=True)

    saved_shots_inside_box = models.PositiveIntegerField(null=True, blank=True)
    saved_shots_inside_box_percentile = models.FloatField(null=True, blank=True)
    saved_shots_inside_box_per_90 = models.FloatField(null=True, blank=True)
    saved_shots_inside_box_per_90_percentile = models.FloatField(null=True, blank=True)

    runs_out = models.PositiveIntegerField(null=True, blank=True)
    runs_out_percentile = models.FloatField(null=True, blank=True)
    runs_out_per_90 = models.FloatField(null=True, blank=True)
    runs_out_per_90_percentile = models.FloatField(null=True, blank=True)

    pass_accuracy = models.FloatField(null=True, blank=True)
    pass_accuracy_percentile = models.FloatField(null=True, blank=True)
    completed_passes_per_90 = models.FloatField(null=True, blank=True)
    completed_passes_per_90_percentile = models.FloatField(null=True, blank=True)
    accurate_long_balls_per_90 = models.FloatField(null=True, blank=True)
    accurate_long_balls_per_90_percentile = models.FloatField(null=True, blank=True)

    is_current = models.BooleanField(default=True, db_index=True)
    superseded_at = models.DateTimeField(null=True, blank=True)
    superseded_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="predecessor_gk_derived_rows",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition_season", "canonical_player"],
                condition=models.Q(is_current=True),
                name="uniq_current_gk_derived_player_season",
            ),
        ]
        indexes = [
            models.Index(fields=["competition_season", "is_current"]),
            models.Index(fields=["competition_season", "canonical_display_team"]),
        ]

    def __str__(self) -> str:
        return f"gk_derived {self.canonical_player} @ {self.competition_season}"


class PlayerSeasonEmbedding(models.Model):
    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="embedding_rows",
    )
    canonical_player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.CASCADE,
        related_name="embedding_seasons",
    )
    canonical_display_team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="embedding_display_team_rows",
    )
    embedding_ingestion_run = models.ForeignKey(
        IngestionRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="embedding_rows",
    )
    position_group = models.CharField(
        max_length=8,
        choices=PositionGroup.choices,
        default=PositionGroup.UNKNOWN,
    )
    minutes = models.PositiveIntegerField(null=True, blank=True)
    cluster_id = models.PositiveSmallIntegerField(default=0, db_index=True)
    cluster_label = models.CharField(max_length=64, blank=True, default="")
    umap_x = models.FloatField()
    umap_y = models.FloatField()
    umap_z = models.FloatField()
    is_current = models.BooleanField(default=True, db_index=True)
    superseded_at = models.DateTimeField(null=True, blank=True)
    superseded_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="predecessor_embedding_rows",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition_season", "canonical_player"],
                condition=models.Q(is_current=True),
                name="uniq_current_embedding_player_season",
            ),
        ]
        indexes = [
            models.Index(fields=["competition_season", "is_current"]),
            models.Index(fields=["competition_season", "position_group"]),
            models.Index(fields=["competition_season", "canonical_display_team"]),
            models.Index(fields=["competition_season", "cluster_id"]),
        ]

    def __str__(self) -> str:
        return f"embedding {self.canonical_player} @ {self.competition_season}"


class PlayerSeasonSimilarity(models.Model):
    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="similarity_rows",
    )
    canonical_player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.CASCADE,
        related_name="similar_players",
    )
    similar_player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.CASCADE,
        related_name="similar_to_players",
    )
    similarity = models.FloatField()
    rank = models.PositiveSmallIntegerField()
    is_current = models.BooleanField(default=True, db_index=True)
    superseded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition_season", "canonical_player", "rank"],
                condition=models.Q(is_current=True),
                name="uniq_current_similarity_rank",
            ),
            models.UniqueConstraint(
                fields=["competition_season", "canonical_player", "similar_player"],
                condition=models.Q(is_current=True),
                name="uniq_current_similarity_pair",
            ),
        ]
        indexes = [
            models.Index(fields=["competition_season", "is_current"]),
            models.Index(fields=["competition_season", "canonical_player", "rank"]),
        ]

    def __str__(self) -> str:
        return (
            f"sim {self.canonical_player_id}->{self.similar_player_id} "
            f"({self.similarity:.3f}) @ {self.competition_season_id}"
        )
