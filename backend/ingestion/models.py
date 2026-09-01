from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Provider(models.TextChoices):
    UNDERSTAT = "understat", "Understat"
    SOFASCORE = "sofascore", "Sofascore"
    WHOSCORED = "whoscored", "WhoScored"


class IngestionKind(models.TextChoices):
    REEP_SYNC = "reep_sync", "Reep sync"
    UNDERSTAT = "understat", "Understat"
    SOFASCORE = "sofascore", "Sofascore"
    SOFASCORE_TEAM = "sofascore_team", "Sofascore team"
    POSITION_RESOLUTION = "position_resolution", "Position resolution"
    MERGE = "merge", "Merge"
    TEAM_MERGE = "team_merge", "Team merge"
    DERIVED = "derived", "Derived stats"
    GALAXY = "galaxy", "Galaxy embeddings"
    WHOSCORED_FETCH = "whoscored_fetch", "WhoScored fetch"
    EVENT_PROFILES = "event_profiles", "Event profiles"
    PLAYER_ROLES = "player_roles", "Player roles"


class ProviderMatchStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    LIVE = "live", "Live"
    COMPLETED = "completed", "Completed"
    POSTPONED = "postponed", "Postponed"
    UNKNOWN = "unknown", "Unknown"


class ProviderPayloadStorage(models.TextChoices):
    DATABASE = "db", "Database"
    OBJECT = "object", "Object storage"


class ProviderPayloadLifecycle(models.TextChoices):
    PRELIMINARY = "preliminary", "Preliminary"
    FINAL = "final", "Final"


class MatchEventPeriod(models.IntegerChoices):
    UNKNOWN = 0, "Unknown"
    FIRST_HALF = 1, "First half"
    SECOND_HALF = 2, "Second half"
    FIRST_EXTRA_TIME = 3, "First period of extra time"
    SECOND_EXTRA_TIME = 4, "Second period of extra time"
    PENALTY_SHOOTOUT = 5, "Penalty shootout"
    POST_GAME = 6, "Post-game"


class MatchEventType(models.IntegerChoices):
    UNKNOWN = 0, "Unknown"
    PASS = 1, "Pass"
    BALL_TOUCH = 2, "Ball touch"
    TAKE_ON = 3, "Take-on"
    SHOT = 4, "Shot"
    BALL_RECOVERY = 5, "Ball recovery"
    TACKLE = 6, "Tackle"
    INTERCEPTION = 7, "Interception"
    CLEARANCE = 8, "Clearance"
    BLOCKED_PASS = 9, "Blocked pass"
    AERIAL = 10, "Aerial"
    CHALLENGE = 11, "Challenge"
    DISPOSSESSED = 12, "Dispossessed"
    FOUL = 13, "Foul"
    SAVE = 14, "Save"
    OFFSIDE = 15, "Offside"
    CARD = 16, "Card"
    SUBSTITUTION = 17, "Substitution"
    ADMINISTRATIVE = 18, "Administrative"
    OWN_GOAL = 19, "Own goal"


class MatchEventBodyPart(models.IntegerChoices):
    UNKNOWN = 0, "Unknown"
    RIGHT_FOOT = 1, "Right foot"
    LEFT_FOOT = 2, "Left foot"
    HEAD = 3, "Head"
    OTHER = 4, "Other"


class MatchEventShotSituation(models.IntegerChoices):
    UNKNOWN = 0, "Unknown"
    OPEN_PLAY = 1, "Open play"
    SET_PIECE = 2, "Set piece"
    CORNER = 3, "Corner"
    DIRECT_FREE_KICK = 4, "Direct free kick"
    PENALTY = 5, "Penalty"
    FAST_BREAK = 6, "Fast break"


class MatchEventShotOutcome(models.IntegerChoices):
    UNKNOWN = 0, "Unknown"
    GOAL = 1, "Goal"
    SAVED = 2, "Saved"
    BLOCKED = 3, "Blocked"
    OFF_TARGET = 4, "Off target"
    WOODWORK = 5, "Woodwork"


class MatchEventGameState(models.IntegerChoices):
    UNKNOWN = 0, "Unknown"
    DRAWING = 1, "Drawing"
    WINNING = 2, "Winning"
    LOSING = 3, "Losing"


class MatchGameStateStatus(models.TextChoices):
    VERIFIED = "verified", "Verified"
    VERIFIED_WITH_SHOOTOUT = "verified_with_shootout", "Verified with shootout"
    UNVERIFIED = "unverified", "Unverified"
    NO_EVENTS = "no_events", "No events"
    SCORE_MISMATCH = "score_mismatch", "Score mismatch"
    INVALID = "invalid", "Invalid"


class MatchGameStateExclusionReason(models.TextChoices):
    NOT_COMPLETED = "not_completed", "Match is not completed"
    NON_FINAL_PAYLOAD = "non_final_payload", "Payload is not final"
    TEAM_IDENTITY_UNRESOLVED = "team_identity_unresolved", "Team identity unresolved"
    SCORE_UNAVAILABLE = "score_unavailable", "Score unavailable"
    SCORE_MISMATCH = "score_mismatch", "Score mismatch"
    INVALID_SCORE_REPLAY = "invalid_score_replay", "Invalid score replay"
    CLOCK_METADATA_MISSING = "clock_metadata_missing", "Clock metadata missing"
    CLOCK_METADATA_INVALID = "clock_metadata_invalid", "Clock metadata invalid"
    EVENT_TIMESTAMP_INVALID = "event_timestamp_invalid", "Event timestamp invalid"
    NO_SUPPORTED_PLAY = "no_supported_play", "No supported play"
    ABANDONED_OR_INCOMPLETE = "abandoned_or_incomplete", "Abandoned or incomplete"


class MatchStatePhase(models.TextChoices):
    FIRST_HALF = "first_half", "First half"
    SECOND_HALF = "second_half", "Second half"
    FIRST_EXTRA_TIME = "first_extra_time", "First period of extra time"
    SECOND_EXTRA_TIME = "second_extra_time", "Second period of extra time"


class MatchStateDrawProvenance(models.TextChoices):
    NONE = "none", "Not a draw"
    NEUTRAL = "neutral", "Neutral draw"
    RESTORED = "restored", "Restored draw"
    SURRENDERED = "surrendered", "Surrendered draw"


class MatchParticipationAction(models.TextChoices):
    NONE = "none", "None"
    SUBSTITUTION_ON = "substitution_on", "Substitution on"
    SUBSTITUTION_OFF = "substitution_off", "Substitution off"
    PLAYER_ON = "player_on", "Player on"
    PLAYER_OFF = "player_off", "Player off"
    PLAYER_RETIRED = "player_retired", "Player retired"
    PLAYER_RETURNS = "player_returns", "Player returns"


class MatchDismissalType(models.TextChoices):
    NONE = "none", "None"
    RED = "red", "Red card"
    SECOND_YELLOW = "second_yellow", "Second yellow"


class MatchPlayerRosterRole(models.TextChoices):
    STARTER = "starter", "Starter"
    SUBSTITUTE = "substitute", "Substitute"
    ADDED = "added", "Added from event evidence"
    UNKNOWN = "unknown", "Unknown"


class MatchPlayerPositionRole(models.TextChoices):
    GOALKEEPER = "goalkeeper", "Goalkeeper"
    OUTFIELD = "outfield", "Outfield"
    UNKNOWN = "unknown", "Unknown"


class MatchPlayerParticipationStatus(models.TextChoices):
    VERIFIED = "verified", "Verified"
    PARTIAL = "partial", "Partial"
    EXCLUDED = "excluded", "Excluded"
    UNUSED = "unused", "Unused substitute"


class MatchPlayerParticipationBuildStatus(models.TextChoices):
    VERIFIED = "verified", "Verified"
    PARTIAL = "partial", "Partial"
    EXCLUDED = "excluded", "Excluded"
    NO_LINEUP = "no_lineup", "No lineup"


class MatchPlayerIntervalConfidence(models.TextChoices):
    VERIFIED = "verified", "Verified"
    PARTIAL = "partial", "Partial"
    UNVERIFIED = "unverified", "Unverified"


class MatchPlayerIntervalStartEvidence(models.TextChoices):
    LINEUP_STARTER = "lineup_starter", "Lineup starter"
    SUBSTITUTION_ON = "substitution_on", "Substitution on"
    PLAYER_ON = "player_on", "Player on"
    PLAYER_RETURNS = "player_returns", "Player returns"


class MatchPlayerIntervalEndEvidence(models.TextChoices):
    SUBSTITUTION_OFF = "substitution_off", "Substitution off"
    PLAYER_OFF = "player_off", "Player off"
    PLAYER_RETIRED = "player_retired", "Player retired"
    DISMISSAL_RED = "dismissal_red", "Red-card dismissal"
    DISMISSAL_SECOND_YELLOW = "dismissal_second_yellow", "Second-yellow dismissal"
    MATCH_END = "match_end", "Match end"


class EventProfileSplitType(models.TextChoices):
    SEASON_TOTAL = "season_total", "Season total"
    TEAM = "team", "Team"


def _scaled_coordinate_field(**kwargs):
    """A nullable 0..100 source coordinate stored as an integer scaled to 0..10000."""

    return models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(10000)],
        **kwargs,
    )


class IngestionRunStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"


class IngestionBatchStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    RUNNING = "running", "Running"
    SUCCESS = "success", "Success"
    PARTIAL_SUCCESS = "partial_success", "Partial success"
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped"
    CANCELLED = "cancelled", "Cancelled"


class IngestionBatchItemStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped"
    CANCELLED = "cancelled", "Cancelled"


class MatchMethod(models.TextChoices):
    AUTO = "auto", "Automatic"
    MANUAL = "manual", "Manual"


class MetadataAuthority(models.TextChoices):
    UNDERSTAT = "understat", "Understat"
    SOFASCORE = "sofascore", "Sofascore"


class PlayerDataMode(models.TextChoices):
    FULL_MERGE = "full_merge", "Full merge"
    SOFASCORE_ONLY = "sofascore_only", "Sofascore only"


class PositionGroup(models.TextChoices):
    GK = "GK", "Goalkeeper"
    DEF = "DEF", "Defender"
    MID = "MID", "Midfielder"
    FWD = "FWD", "Forward"
    UNKNOWN = "UNK", "Unknown"


class PositionResolutionSource(models.TextChoices):
    EXISTING_SOURCE = "existing_source", "Existing source"
    HISTORICAL_PLAYER = "historical_player", "Historical player"
    SOFASCORE_ROSTER = "sofascore_roster", "Sofascore roster"
    SOFASCORE_PROFILE = "sofascore_profile", "Sofascore profile"
    MANUAL = "manual", "Manual"


class CompetitionType(models.TextChoices):
    DOMESTIC_LEAGUE = "domestic_league", "Domestic league"
    CONTINENTAL_CUP = "continental_cup", "Continental cup"


class Competition(models.Model):
    name = models.CharField(max_length=200)
    short_code = models.CharField(max_length=32, db_index=True)
    country = models.CharField(max_length=120, blank=True)
    competition_type = models.CharField(
        max_length=24,
        choices=CompetitionType.choices,
        default=CompetitionType.DOMESTIC_LEAGUE,
        db_index=True,
    )
    include_in_domestic_aggregates = models.BooleanField(default=True, db_index=True)
    minimum_eligible_minutes = models.PositiveSmallIntegerField(default=450)

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
    player_data_mode = models.CharField(
        max_length=24,
        choices=PlayerDataMode.choices,
        default=PlayerDataMode.FULL_MERGE,
    )
    has_understat = models.BooleanField(default=True)
    has_sofascore = models.BooleanField(default=True)
    understat_league = models.CharField(max_length=32, blank=True, null=True, default="EPL")
    understat_season_year = models.CharField(
        max_length=8,
        blank=True,
        null=True,
        help_text="Understat URL segment, e.g. 2025 for 2025-26 depending on Understat convention.",
    )
    sofascore_unique_tournament_id = models.PositiveIntegerField(null=True, blank=True)
    sofascore_season_id = models.PositiveIntegerField(null=True, blank=True)
    has_whoscored = models.BooleanField(default=False)
    whoscored_league = models.CharField(max_length=32, blank=True, default="")
    whoscored_season = models.CharField(max_length=32, blank=True, default="")
    whoscored_expected_match_count = models.PositiveSmallIntegerField(null=True, blank=True)
    expected_team_count = models.PositiveSmallIntegerField(default=20)
    min_merged_team_count = models.PositiveSmallIntegerField(default=18)
    min_team_stats_coverage_count = models.PositiveSmallIntegerField(default=18)
    metric_availability = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    is_published = models.BooleanField(default=False, db_index=True)
    refresh_enabled = models.BooleanField(default=False, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition", "season"],
                name="uniq_competition_season",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.competition.short_code} {self.season.label}"

    @property
    def minimum_eligible_minutes(self) -> int:
        return self.competition.minimum_eligible_minutes

    @property
    def supports_understat(self) -> bool:
        return self.has_understat and bool(self.understat_league and self.understat_season_year)

    @property
    def supports_sofascore(self) -> bool:
        return (
            self.has_sofascore
            and self.sofascore_unique_tournament_id is not None
            and self.sofascore_season_id is not None
        )

    @property
    def supports_whoscored(self) -> bool:
        return self.has_whoscored and bool(self.whoscored_league and self.whoscored_season)

    @property
    def requires_dual_provider_merge(self) -> bool:
        return self.player_data_mode == PlayerDataMode.FULL_MERGE


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


class IngestionBatch(models.Model):
    KIND_DAILY_REFRESH = "daily_refresh"
    KIND_WEEKLY_WHOSCORED = "weekly_whoscored"

    kind = models.CharField(max_length=32, default=KIND_DAILY_REFRESH, db_index=True)
    status = models.CharField(
        max_length=24,
        choices=IngestionBatchStatus.choices,
        default=IngestionBatchStatus.PLANNED,
        db_index=True,
    )
    scheduled_for_date = models.DateField(db_index=True)
    planned_start_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    manual = models.BooleanField(default=False)
    summary_stats = models.JSONField(default=dict, blank=True)
    aggregate_run_ids = models.JSONField(default=dict, blank=True)
    error_detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scheduled_for_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "scheduled_for_date"],
                name="uniq_ingestion_batch_kind_date",
                condition=models.Q(manual=False),
            ),
        ]
        indexes = [
            models.Index(fields=["kind", "status"], name="ing_batch_kind_status_idx"),
            models.Index(fields=["status", "planned_start_at"], name="ing_batch_status_start_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.scheduled_for_date} {self.status}"


class IngestionBatchItem(models.Model):
    batch = models.ForeignKey(
        IngestionBatch,
        on_delete=models.CASCADE,
        related_name="items",
    )
    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="ingestion_batch_items",
    )
    status = models.CharField(
        max_length=24,
        choices=IngestionBatchItemStatus.choices,
        default=IngestionBatchItemStatus.PENDING,
        db_index=True,
    )
    planned_order = models.PositiveSmallIntegerField(default=0)
    eta = models.DateTimeField(null=True, blank=True)
    current_stage = models.CharField(max_length=32, blank=True)
    stage_run_ids = models.JSONField(default=dict, blank=True)
    stage_stats = models.JSONField(default=dict, blank=True)
    error_detail = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["batch_id", "planned_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "competition_season"],
                name="uniq_ingestion_batch_item_slice",
            ),
        ]
        indexes = [
            models.Index(fields=["batch", "status"], name="ing_item_batch_status_idx"),
            models.Index(fields=["competition_season", "status"], name="ing_item_slice_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.batch_id}:{self.competition_season_id} {self.status}"


class IngestionLease(models.Model):
    key = models.CharField(max_length=128, unique=True)
    owner_token = models.CharField(max_length=64)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.key} until {self.expires_at.isoformat()}"


class MaterializedApiPayload(models.Model):
    """Cached public API JSON payload keyed by endpoint params and source version."""

    cache_key = models.CharField(max_length=255, unique=True, db_index=True)
    source_version = models.CharField(max_length=128, db_index=True)
    payload = models.JSONField(default=dict)
    payload_json = models.TextField(blank=True, default="")
    payload_etag = models.CharField(max_length=80, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["cache_key", "source_version"], name="ingestion_m_cache_k_9f2600_idx"),
            models.Index(fields=["updated_at"], name="ingestion_m_updated_9420a7_idx"),
        ]

    def __str__(self) -> str:
        return self.cache_key


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


class ProviderMatch(models.Model):
    provider = models.CharField(max_length=32, choices=Provider.choices)
    provider_match_id = models.CharField(max_length=64)
    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="provider_matches",
    )
    kickoff_at = models.DateTimeField()
    status = models.CharField(
        max_length=16,
        choices=ProviderMatchStatus.choices,
        default=ProviderMatchStatus.UNKNOWN,
    )
    home_provider_team_id = models.CharField(max_length=64)
    away_provider_team_id = models.CharField(max_length=64)
    home_team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="provider_home_matches",
    )
    away_team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="provider_away_matches",
    )
    home_score = models.PositiveSmallIntegerField(null=True, blank=True)
    away_score = models.PositiveSmallIntegerField(null=True, blank=True)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_match_id"],
                name="uniq_provider_match",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(home_score__isnull=True, away_score__isnull=True)
                    | models.Q(home_score__isnull=False, away_score__isnull=False)
                ),
                name="provider_match_scores_paired",
            ),
        ]
        indexes = [
            models.Index(
                fields=["competition_season", "kickoff_at"],
                name="prov_match_slice_kick_idx",
            ),
            models.Index(
                fields=["competition_season", "status"],
                name="prov_match_slice_stat_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider} match {self.provider_match_id}"


class ProviderMatchPayload(models.Model):
    provider_match = models.OneToOneField(
        ProviderMatch,
        on_delete=models.CASCADE,
        related_name="payload",
    )
    storage_backend = models.CharField(
        max_length=16,
        choices=ProviderPayloadStorage.choices,
        default=ProviderPayloadStorage.DATABASE,
    )
    payload_gzip = models.BinaryField(null=True, blank=True, editable=False)
    object_key = models.CharField(max_length=512, null=True, blank=True)
    payload_sha256 = models.CharField(max_length=64)
    payload_size_bytes = models.PositiveIntegerField()
    uncompressed_size_bytes = models.PositiveIntegerField()
    schema_version = models.PositiveSmallIntegerField(default=1)
    lifecycle_state = models.CharField(
        max_length=16,
        choices=ProviderPayloadLifecycle.choices,
    )
    preliminary_sha256 = models.CharField(max_length=64, null=True, blank=True)
    preliminary_fetched_at = models.DateTimeField(null=True, blank=True)
    final_sha256 = models.CharField(max_length=64, null=True, blank=True)
    final_fetched_at = models.DateTimeField(null=True, blank=True)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        storage_backend=ProviderPayloadStorage.DATABASE,
                        payload_gzip__isnull=False,
                        object_key__isnull=True,
                    )
                    | models.Q(
                        storage_backend=ProviderPayloadStorage.OBJECT,
                        payload_gzip__isnull=True,
                        object_key__isnull=False,
                    )
                ),
                name="provider_payload_location",
            ),
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(
                            preliminary_sha256__isnull=True,
                            preliminary_fetched_at__isnull=True,
                        )
                        | models.Q(
                            preliminary_sha256__isnull=False,
                            preliminary_fetched_at__isnull=False,
                        )
                    )
                    & (
                        models.Q(
                            final_sha256__isnull=True,
                            final_fetched_at__isnull=True,
                        )
                        | models.Q(
                            final_sha256__isnull=False,
                            final_fetched_at__isnull=False,
                        )
                    )
                    & (
                        models.Q(
                            lifecycle_state=ProviderPayloadLifecycle.PRELIMINARY,
                            preliminary_sha256__isnull=False,
                            preliminary_fetched_at__isnull=False,
                            final_sha256__isnull=True,
                            final_fetched_at__isnull=True,
                            payload_sha256=models.F("preliminary_sha256"),
                        )
                        | models.Q(
                            lifecycle_state=ProviderPayloadLifecycle.FINAL,
                            final_sha256__isnull=False,
                            final_fetched_at__isnull=False,
                            payload_sha256=models.F("final_sha256"),
                        )
                    )
                ),
                name="provider_payload_lifecycle",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    payload_size_bytes__gt=0,
                    uncompressed_size_bytes__gt=0,
                ),
                name="provider_payload_sizes_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"payload for {self.provider_match}"


class ProviderMatchGameState(models.Model):
    """Audit record for the rebuildable score replay attached to a match."""

    provider_match = models.OneToOneField(
        ProviderMatch,
        on_delete=models.CASCADE,
        related_name="game_state",
    )
    status = models.CharField(
        max_length=32,
        choices=MatchGameStateStatus.choices,
        default=MatchGameStateStatus.UNVERIFIED,
    )
    eligible = models.BooleanField(default=False)
    exclusion_reason = models.CharField(
        max_length=40,
        choices=MatchGameStateExclusionReason.choices,
        null=True,
        blank=True,
    )
    calculation_version = models.CharField(max_length=64)
    source_checksum = models.CharField(max_length=64, blank=True, default="")
    event_count = models.PositiveIntegerField(default=0)
    goal_event_count = models.PositiveIntegerField(default=0)
    ignored_goal_event_count = models.PositiveIntegerField(default=0)
    shootout_goal_event_count = models.PositiveIntegerField(default=0)
    replayed_home_score = models.PositiveSmallIntegerField(null=True, blank=True)
    replayed_away_score = models.PositiveSmallIntegerField(null=True, blank=True)
    replayed_shootout_home_score = models.PositiveSmallIntegerField(
        null=True, blank=True
    )
    replayed_shootout_away_score = models.PositiveSmallIntegerField(
        null=True, blank=True
    )
    supported_start_second = models.PositiveIntegerField(null=True, blank=True)
    supported_end_second = models.PositiveIntegerField(null=True, blank=True)
    exposure_seconds = models.PositiveIntegerField(default=0)
    period_count = models.PositiveSmallIntegerField(default=0)
    episode_count = models.PositiveIntegerField(default=0)
    focal_team_count = models.PositiveSmallIntegerField(default=0)
    diagnostics = models.JSONField(default=dict, blank=True)
    calculated_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(
                fields=["status", "calculated_at"],
                name="prov_match_game_state_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"game state for {self.provider_match} ({self.status})"


class ProviderMatchPlayedPeriod(models.Model):
    provider_match = models.ForeignKey(
        ProviderMatch,
        on_delete=models.CASCADE,
        related_name="played_periods",
    )
    period = models.PositiveSmallIntegerField(choices=MatchEventPeriod.choices)
    period_index = models.PositiveSmallIntegerField()
    start_second = models.PositiveIntegerField()
    end_second = models.PositiveIntegerField()
    duration_seconds = models.PositiveIntegerField()
    calculation_version = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider_match", "period"],
                name="uniq_match_played_period",
            ),
            models.UniqueConstraint(
                fields=["provider_match", "period_index"],
                name="uniq_match_period_index",
            ),
            models.CheckConstraint(
                condition=models.Q(end_second__gt=models.F("start_second")),
                name="played_period_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=["provider_match", "period_index"],
                name="played_period_order_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider_match_id}:{self.period} [{self.start_second},{self.end_second})"


class ProviderMatchEvent(models.Model):
    provider_match = models.ForeignKey(
        ProviderMatch,
        on_delete=models.CASCADE,
        related_name="events",
        db_index=False,
    )
    event_index = models.PositiveIntegerField()
    provider_event_id = models.CharField(max_length=64, null=True, blank=True)
    provider_event_sequence_id = models.CharField(max_length=64, null=True, blank=True)
    related_provider_event_sequence_id = models.CharField(
        max_length=64, null=True, blank=True
    )
    provider_team_id = models.CharField(max_length=64)
    team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="provider_match_events",
        db_index=False,
    )
    provider_player_id = models.CharField(max_length=64, null=True, blank=True)
    related_provider_player_id = models.CharField(max_length=64, null=True, blank=True)
    player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="provider_match_events",
        db_index=False,
    )
    period = models.PositiveSmallIntegerField(
        choices=MatchEventPeriod.choices,
        default=MatchEventPeriod.UNKNOWN,
    )
    minute = models.PositiveSmallIntegerField()
    second = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(59)],
    )
    expanded_minute = models.PositiveSmallIntegerField(null=True, blank=True)
    match_seconds = models.PositiveIntegerField(null=True, blank=True)
    timeline_seconds = models.PositiveIntegerField(null=True, blank=True)
    event_type = models.PositiveSmallIntegerField(
        choices=MatchEventType.choices,
        default=MatchEventType.UNKNOWN,
    )
    source_event_type_id = models.PositiveSmallIntegerField(null=True, blank=True)
    is_goal_disallowed = models.BooleanField(default=False)
    is_deleted_event = models.BooleanField(default=False)
    participation_action = models.CharField(
        max_length=24,
        choices=MatchParticipationAction.choices,
        default=MatchParticipationAction.NONE,
    )
    dismissal_type = models.CharField(
        max_length=20,
        choices=MatchDismissalType.choices,
        default=MatchDismissalType.NONE,
    )
    outcome_successful = models.BooleanField(null=True, blank=True)
    x = _scaled_coordinate_field()
    y = _scaled_coordinate_field()
    end_x = _scaled_coordinate_field()
    end_y = _scaled_coordinate_field()
    goal_mouth_y = _scaled_coordinate_field()
    goal_mouth_z = _scaled_coordinate_field()
    blocked_x = _scaled_coordinate_field()
    blocked_y = _scaled_coordinate_field()
    is_touch = models.BooleanField(default=False)
    is_key_pass = models.BooleanField(default=False)
    is_shot_assist = models.BooleanField(default=False)
    is_intentional_assist = models.BooleanField(default=False)
    is_cross = models.BooleanField(default=False)
    is_long_ball = models.BooleanField(default=False)
    is_chipped = models.BooleanField(default=False)
    is_head_pass = models.BooleanField(default=False)
    is_through_ball = models.BooleanField(default=False)
    is_throw_in = models.BooleanField(default=False)
    is_corner = models.BooleanField(default=False)
    is_free_kick = models.BooleanField(default=False)
    is_set_piece = models.BooleanField(default=False)
    is_regular_play = models.BooleanField(default=False)
    is_big_chance = models.BooleanField(default=False)
    # WhoScored's ``Defensive`` qualifier is needed to distinguish defensive
    # Aerial/Challenge events from their attacking counterparts.
    is_defensive = models.BooleanField(default=False)
    body_part = models.PositiveSmallIntegerField(
        choices=MatchEventBodyPart.choices,
        default=MatchEventBodyPart.UNKNOWN,
    )
    shot_situation = models.PositiveSmallIntegerField(
        choices=MatchEventShotSituation.choices,
        default=MatchEventShotSituation.UNKNOWN,
    )
    shot_outcome = models.PositiveSmallIntegerField(
        choices=MatchEventShotOutcome.choices,
        default=MatchEventShotOutcome.UNKNOWN,
    )
    scoring_provider_team_id = models.CharField(max_length=64, null=True, blank=True)
    home_score_before = models.PositiveSmallIntegerField(null=True, blank=True)
    away_score_before = models.PositiveSmallIntegerField(null=True, blank=True)
    home_score_after = models.PositiveSmallIntegerField(null=True, blank=True)
    away_score_after = models.PositiveSmallIntegerField(null=True, blank=True)
    game_state_before = models.PositiveSmallIntegerField(
        choices=MatchEventGameState.choices,
        null=True,
        blank=True,
    )
    game_state_after = models.PositiveSmallIntegerField(
        choices=MatchEventGameState.choices,
        null=True,
        blank=True,
    )
    is_progressive_pass = models.BooleanField(default=False)
    is_final_third_entry = models.BooleanField(default=False)
    is_box_entry = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider_match", "event_index"],
                name="uniq_provider_match_event",
            ),
            models.CheckConstraint(
                condition=models.Q(second__gte=0, second__lte=59),
                name="provider_event_second_range",
            ),
            models.CheckConstraint(
                condition=(
                    (models.Q(x__isnull=True) | models.Q(x__gte=0, x__lte=10000))
                    & (models.Q(y__isnull=True) | models.Q(y__gte=0, y__lte=10000))
                    & (models.Q(end_x__isnull=True) | models.Q(end_x__gte=0, end_x__lte=10000))
                    & (models.Q(end_y__isnull=True) | models.Q(end_y__gte=0, end_y__lte=10000))
                    & (
                        models.Q(goal_mouth_y__isnull=True)
                        | models.Q(goal_mouth_y__gte=0, goal_mouth_y__lte=10000)
                    )
                    & (
                        models.Q(goal_mouth_z__isnull=True)
                        | models.Q(goal_mouth_z__gte=0, goal_mouth_z__lte=10000)
                    )
                    & (
                        models.Q(blocked_x__isnull=True)
                        | models.Q(blocked_x__gte=0, blocked_x__lte=10000)
                    )
                    & (
                        models.Q(blocked_y__isnull=True)
                        | models.Q(blocked_y__gte=0, blocked_y__lte=10000)
                    )
                ),
                name="provider_event_coords_range",
            ),
        ]
        indexes = [
            models.Index(
                fields=["player", "event_type", "provider_match"],
                name="prov_event_player_type_idx",
            ),
            models.Index(
                fields=["team", "event_type", "provider_match"],
                name="prov_event_team_type_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider_match_id}:{self.event_index}"


class ProviderMatchTeamGameStateEpisode(models.Model):
    provider_match = models.ForeignKey(
        ProviderMatch,
        on_delete=models.CASCADE,
        related_name="team_game_state_episodes",
    )
    focal_team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.PROTECT,
        related_name="game_state_episodes",
    )
    focal_is_home = models.BooleanField()
    episode_index = models.PositiveSmallIntegerField()
    period = models.PositiveSmallIntegerField(choices=MatchEventPeriod.choices)
    phase = models.CharField(max_length=24, choices=MatchStatePhase.choices)
    start_second = models.PositiveIntegerField()
    end_second = models.PositiveIntegerField()
    duration_seconds = models.PositiveIntegerField()
    is_added_time = models.BooleanField(default=False)
    focal_score = models.PositiveSmallIntegerField()
    opponent_score = models.PositiveSmallIntegerField()
    goal_difference = models.SmallIntegerField()
    state = models.PositiveSmallIntegerField(choices=MatchEventGameState.choices)
    previous_state = models.PositiveSmallIntegerField(
        choices=MatchEventGameState.choices,
        null=True,
        blank=True,
    )
    draw_provenance = models.CharField(
        max_length=16,
        choices=MatchStateDrawProvenance.choices,
        default=MatchStateDrawProvenance.NONE,
    )
    state_entry_second = models.PositiveIntegerField()
    state_age_seconds_at_start = models.PositiveIntegerField()
    entry_event = models.ForeignKey(
        ProviderMatchEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entered_game_state_episodes",
    )
    entry_event_index = models.PositiveIntegerField(null=True, blank=True)
    calculation_version = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider_match", "focal_team", "episode_index"],
                name="uniq_match_team_state_episode",
            ),
            models.CheckConstraint(
                condition=models.Q(end_second__gt=models.F("start_second")),
                name="state_episode_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(state_entry_second__lte=models.F("start_second")),
                name="state_entry_before_episode",
            ),
        ]
        indexes = [
            models.Index(
                fields=["provider_match", "focal_team", "start_second", "end_second"],
                name="team_state_episode_time_idx",
            ),
            models.Index(
                fields=["focal_team", "state", "phase"],
                name="team_state_scope_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider_match_id}:{self.focal_team_id}:{self.episode_index}"


class ProviderMatchTeamGameStateExposure(models.Model):
    provider_match = models.ForeignKey(
        ProviderMatch,
        on_delete=models.CASCADE,
        related_name="team_game_state_exposures",
    )
    focal_team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.PROTECT,
        related_name="game_state_exposures",
    )
    state = models.PositiveSmallIntegerField(choices=MatchEventGameState.choices)
    goal_difference = models.SmallIntegerField()
    phase = models.CharField(max_length=24, choices=MatchStatePhase.choices)
    draw_provenance = models.CharField(
        max_length=16,
        choices=MatchStateDrawProvenance.choices,
        default=MatchStateDrawProvenance.NONE,
    )
    exposure_seconds = models.PositiveIntegerField()
    episode_count = models.PositiveSmallIntegerField()
    calculation_version = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "provider_match",
                    "focal_team",
                    "state",
                    "goal_difference",
                    "phase",
                    "draw_provenance",
                ],
                name="uniq_match_team_state_exposure",
            ),
            models.CheckConstraint(
                condition=models.Q(exposure_seconds__gt=0),
                name="team_state_exposure_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=["focal_team", "state", "phase"],
                name="team_state_exposure_idx",
            ),
        ]


class ProviderMatchPlayerParticipationBuild(models.Model):
    provider_match = models.OneToOneField(
        ProviderMatch,
        on_delete=models.CASCADE,
        related_name="player_participation_build",
    )
    status = models.CharField(
        max_length=16,
        choices=MatchPlayerParticipationBuildStatus.choices,
        default=MatchPlayerParticipationBuildStatus.EXCLUDED,
    )
    formula_version = models.CharField(max_length=64)
    source_payload_sha256 = models.CharField(max_length=64, blank=True, default="")
    match_clock_version = models.CharField(max_length=64, blank=True, default="")
    team_episode_version = models.CharField(max_length=64, blank=True, default="")
    participant_count = models.PositiveSmallIntegerField(default=0)
    verified_participant_count = models.PositiveSmallIntegerField(default=0)
    excluded_participant_count = models.PositiveSmallIntegerField(default=0)
    unused_player_count = models.PositiveSmallIntegerField(default=0)
    interval_count = models.PositiveSmallIntegerField(default=0)
    verified_seconds = models.PositiveIntegerField(default=0)
    diagnostics = models.JSONField(default=dict, blank=True)
    calculated_at = models.DateTimeField()


class ProviderMatchPlayerParticipation(models.Model):
    build = models.ForeignKey(
        ProviderMatchPlayerParticipationBuild,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    provider_match = models.ForeignKey(
        ProviderMatch,
        on_delete=models.CASCADE,
        related_name="player_participations",
    )
    provider_team_id = models.CharField(max_length=64)
    team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="provider_match_participations",
    )
    provider_player_id = models.CharField(max_length=64)
    player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="provider_match_participations",
    )
    roster_role = models.CharField(max_length=16, choices=MatchPlayerRosterRole.choices)
    position_role = models.CharField(
        max_length=16,
        choices=MatchPlayerPositionRole.choices,
        default=MatchPlayerPositionRole.UNKNOWN,
    )
    status = models.CharField(
        max_length=16,
        choices=MatchPlayerParticipationStatus.choices,
    )
    confidence = models.CharField(
        max_length=16,
        choices=MatchPlayerIntervalConfidence.choices,
    )
    exclusion_reason = models.CharField(max_length=64, null=True, blank=True)
    on_pitch_seconds = models.PositiveIntegerField(default=0)
    excluded_seconds = models.PositiveIntegerField(default=0)
    interval_count = models.PositiveSmallIntegerField(default=0)
    diagnostics = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["build", "provider_team_id", "provider_player_id"],
                name="uniq_match_player_participation",
            ),
        ]
        indexes = [
            models.Index(
                fields=["player", "team", "status"],
                name="player_participation_scope_idx",
            ),
        ]


class ProviderMatchPlayerInterval(models.Model):
    participation = models.ForeignKey(
        ProviderMatchPlayerParticipation,
        on_delete=models.CASCADE,
        related_name="intervals",
    )
    sequence = models.PositiveSmallIntegerField()
    start_second = models.PositiveIntegerField()
    end_second = models.PositiveIntegerField()
    duration_seconds = models.PositiveIntegerField()
    start_evidence = models.CharField(
        max_length=24,
        choices=MatchPlayerIntervalStartEvidence.choices,
    )
    end_evidence = models.CharField(
        max_length=32,
        choices=MatchPlayerIntervalEndEvidence.choices,
    )
    start_event_index = models.PositiveIntegerField(null=True, blank=True)
    end_event_index = models.PositiveIntegerField(null=True, blank=True)
    start_event_sequence_id = models.CharField(max_length=64, null=True, blank=True)
    end_event_sequence_id = models.CharField(max_length=64, null=True, blank=True)
    confidence = models.CharField(
        max_length=16,
        choices=MatchPlayerIntervalConfidence.choices,
    )
    exclusion_reason = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["participation", "sequence"],
                name="uniq_player_interval_sequence",
            ),
            models.CheckConstraint(
                condition=models.Q(end_second__gt=models.F("start_second")),
                name="player_interval_positive",
            ),
        ]


class ProviderMatchPlayerStateExposure(models.Model):
    player_interval = models.ForeignKey(
        ProviderMatchPlayerInterval,
        on_delete=models.CASCADE,
        related_name="state_exposures",
    )
    team_episode = models.ForeignKey(
        ProviderMatchTeamGameStateEpisode,
        on_delete=models.CASCADE,
        related_name="player_state_exposures",
    )
    start_second = models.PositiveIntegerField()
    end_second = models.PositiveIntegerField()
    duration_seconds = models.PositiveIntegerField()
    coarse_state = models.PositiveSmallIntegerField(choices=MatchEventGameState.choices)
    goal_difference = models.SmallIntegerField()
    phase = models.CharField(max_length=24, choices=MatchStatePhase.choices)
    provenance = models.CharField(
        max_length=16,
        choices=MatchStateDrawProvenance.choices,
        default=MatchStateDrawProvenance.NONE,
    )
    state_age_bucket = models.CharField(max_length=24)
    state_age_start_seconds = models.PositiveIntegerField()
    state_age_end_seconds = models.PositiveIntegerField()
    formula_version = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "player_interval",
                    "team_episode",
                    "start_second",
                    "end_second",
                ],
                name="uniq_player_state_exposure",
            ),
            models.CheckConstraint(
                condition=models.Q(end_second__gt=models.F("start_second")),
                name="player_state_exposure_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=["coarse_state", "phase", "provenance"],
                name="player_state_scope_idx",
            ),
        ]


class ProviderMatchCarry(models.Model):
    """A derived ball-carry between consecutive same-team on-ball actions.

    Opta/WhoScored does not publish carry events; these rows are rebuilt from
    the normalized event stream whenever a match's events are replaced. They
    are deliberately kept out of :class:`ProviderMatchEvent` so synthetic rows
    can never contaminate event counts or raw-event fidelity.
    """

    provider_match = models.ForeignKey(
        ProviderMatch,
        on_delete=models.CASCADE,
        related_name="derived_carries",
    )
    start_event_index = models.PositiveIntegerField()
    end_event_index = models.PositiveIntegerField()
    provider_team_id = models.CharField(max_length=64)
    team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="provider_match_carries",
        db_index=False,
    )
    provider_player_id = models.CharField(max_length=64, null=True, blank=True)
    player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="provider_match_carries",
        db_index=False,
    )
    period = models.PositiveSmallIntegerField(
        choices=MatchEventPeriod.choices,
        default=MatchEventPeriod.UNKNOWN,
    )
    minute = models.PositiveSmallIntegerField()
    second = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(59)],
        default=0,
    )
    match_seconds = models.PositiveIntegerField(null=True, blank=True)
    x = _scaled_coordinate_field()
    y = _scaled_coordinate_field()
    end_x = _scaled_coordinate_field()
    end_y = _scaled_coordinate_field()
    is_progressive_carry = models.BooleanField(default=False)
    is_final_third_entry = models.BooleanField(default=False)
    is_box_entry = models.BooleanField(default=False)
    is_low_confidence = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider_match", "start_event_index"],
                name="uniq_provider_match_carry",
            ),
            models.CheckConstraint(
                condition=(
                    (models.Q(x__isnull=True) | models.Q(x__gte=0, x__lte=10000))
                    & (models.Q(y__isnull=True) | models.Q(y__gte=0, y__lte=10000))
                    & (
                        models.Q(end_x__isnull=True)
                        | models.Q(end_x__gte=0, end_x__lte=10000)
                    )
                    & (
                        models.Q(end_y__isnull=True)
                        | models.Q(end_y__gte=0, end_y__lte=10000)
                    )
                    & models.Q(second__gte=0, second__lte=59)
                ),
                name="provider_carry_coords_range",
            ),
        ]
        indexes = [
            models.Index(
                fields=["player", "provider_match"],
                name="prov_carry_player_match_idx",
            ),
            models.Index(
                fields=["team", "provider_match"],
                name="prov_carry_team_match_idx",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.provider_match_id}:{self.start_event_index}"
            f"->{self.end_event_index}"
        )


class ProviderMatchPossessionBuild(models.Model):
    """Audit record for one deterministic possession-context rebuild."""

    provider_match = models.OneToOneField(
        ProviderMatch, on_delete=models.CASCADE, related_name="possession_build"
    )
    calculation_version = models.CharField(max_length=64)
    source_checksum = models.CharField(max_length=64, blank=True, default="")
    possession_count = models.PositiveIntegerField(default=0)
    included_event_count = models.PositiveIntegerField(default=0)
    excluded_event_count = models.PositiveIntegerField(default=0)
    ambiguous_event_count = models.PositiveIntegerField(default=0)
    diagnostics = models.JSONField(default=dict, blank=True)
    calculated_at = models.DateTimeField()


class ProviderMatchPossession(models.Model):
    """Provider-neutral continuous team control derived from normalized events."""

    build = models.ForeignKey(
        ProviderMatchPossessionBuild,
        on_delete=models.CASCADE,
        related_name="possessions",
    )
    provider_match = models.ForeignKey(
        ProviderMatch, on_delete=models.CASCADE, related_name="possessions"
    )
    possession_index = models.PositiveIntegerField()
    identity = models.CharField(max_length=160)
    provider_team_id = models.CharField(max_length=64)
    team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="provider_match_possessions",
    )
    period = models.PositiveSmallIntegerField(choices=MatchEventPeriod.choices)
    start_second = models.PositiveIntegerField()
    end_second = models.PositiveIntegerField()
    duration_seconds = models.PositiveIntegerField()
    start_x = _scaled_coordinate_field()
    start_y = _scaled_coordinate_field()
    end_x = _scaled_coordinate_field()
    end_y = _scaled_coordinate_field()
    action_count = models.PositiveIntegerField()
    termination_reason = models.CharField(max_length=32)
    launch_type = models.CharField(max_length=32)
    is_ambiguous = models.BooleanField(default=False)
    exclusion_reason = models.CharField(max_length=64, null=True, blank=True)
    establishment_second = models.PositiveIntegerField(null=True, blank=True)
    establishment_event_index = models.PositiveIntegerField(null=True, blank=True)
    is_settled = models.BooleanField(default=False)
    is_counter_launch = models.BooleanField(default=False)
    counter_final_third_arrival = models.BooleanField(default=False)
    counter_box_arrival = models.BooleanField(default=False)
    counter_shot = models.BooleanField(default=False)
    counter_outcome = models.CharField(max_length=24, null=True, blank=True)
    counter_elapsed_seconds = models.PositiveIntegerField(null=True, blank=True)
    counter_forward_metres = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    counter_speed_mps = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    provider_fast_break_shot_count = models.PositiveSmallIntegerField(default=0)
    settled_defensive_action_count = models.PositiveSmallIntegerField(default=0)
    settled_defensive_average_x = _scaled_coordinate_field()
    settled_block_height = models.CharField(max_length=8, null=True, blank=True)
    state_segments = models.JSONField(default=list, blank=True)
    diagnostics = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider_match", "possession_index"],
                name="uniq_match_possession_index",
            ),
            models.UniqueConstraint(
                fields=["provider_match", "identity"],
                name="uniq_match_possession_identity",
            ),
        ]
        indexes = [
            models.Index(
                fields=["team", "is_counter_launch"],
                name="possession_team_counter_idx",
            ),
            models.Index(
                fields=["provider_match", "period", "start_second"],
                name="possession_match_time_idx",
            ),
        ]


class ProviderMatchPossessionEvent(models.Model):
    possession = models.ForeignKey(
        ProviderMatchPossession, on_delete=models.CASCADE, related_name="event_links"
    )
    event = models.OneToOneField(
        ProviderMatchEvent,
        on_delete=models.CASCADE,
        related_name="possession_link",
    )
    sequence = models.PositiveSmallIntegerField()
    is_control_action = models.BooleanField(default=False)
    is_settled_defensive_action = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["possession", "sequence"],
                name="uniq_possession_event_sequence",
            )
        ]


class ProviderMatchPossessionParticipant(models.Model):
    possession = models.ForeignKey(
        ProviderMatchPossession, on_delete=models.CASCADE, related_name="participants"
    )
    provider_player_id = models.CharField(max_length=64)
    player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="provider_match_possessions",
    )
    first_event_index = models.PositiveIntegerField()
    action_count = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["possession", "provider_player_id"],
                name="uniq_possession_participant",
            )
        ]


class PlayerSeasonEventProfile(models.Model):
    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="player_event_profiles",
    )
    player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.CASCADE,
        related_name="season_event_profiles",
    )
    team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="player_season_event_profiles",
    )
    split_type = models.CharField(
        max_length=16,
        choices=EventProfileSplitType.choices,
    )
    formula_version = models.CharField(
        max_length=32,
        default="event_profiles_v1",
        db_index=True,
    )
    materialized_ingestion_run = models.ForeignKey(
        IngestionRun,
        on_delete=models.PROTECT,
        related_name="player_event_profiles",
    )
    observed_match_count = models.PositiveSmallIntegerField(default=0)
    observed_event_minutes = models.PositiveIntegerField(default=0)
    minutes = models.PositiveIntegerField(default=0)
    valid_location_actions = models.PositiveIntegerField(default=0)
    touches = models.PositiveIntegerField(default=0)
    pass_attempts = models.PositiveIntegerField(default=0)
    pass_completions = models.PositiveIntegerField(default=0)
    progressive_pass_attempts = models.PositiveIntegerField(default=0)
    progressive_pass_completions = models.PositiveIntegerField(default=0)
    final_third_entries = models.PositiveIntegerField(default=0)
    box_entries = models.PositiveIntegerField(default=0)
    key_passes = models.PositiveIntegerField(default=0)
    crosses = models.PositiveIntegerField(default=0)
    long_balls = models.PositiveIntegerField(default=0)
    shots = models.PositiveIntegerField(default=0)
    goals = models.PositiveIntegerField(default=0)
    big_chance_shots = models.PositiveIntegerField(default=0)
    take_ons_attempted = models.PositiveIntegerField(default=0)
    take_ons_successful = models.PositiveIntegerField(default=0)
    defensive_actions = models.PositiveIntegerField(default=0)
    average_touch_x = _scaled_coordinate_field()
    average_touch_y = _scaled_coordinate_field()
    action_grid = models.JSONField(default=list, blank=True)
    is_current = models.BooleanField(default=True, db_index=True)
    superseded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(split_type=EventProfileSplitType.SEASON_TOTAL, team__isnull=True)
                    | models.Q(split_type=EventProfileSplitType.TEAM, team__isnull=False)
                ),
                name="player_event_profile_scope",
            ),
            models.UniqueConstraint(
                fields=["competition_season", "player"],
                condition=models.Q(
                    is_current=True,
                    split_type=EventProfileSplitType.SEASON_TOTAL,
                ),
                name="uniq_cur_player_event_total",
            ),
            models.UniqueConstraint(
                fields=["competition_season", "player", "team"],
                condition=models.Q(
                    is_current=True,
                    split_type=EventProfileSplitType.TEAM,
                ),
                name="uniq_cur_player_event_team",
            ),
        ]
        indexes = [
            models.Index(
                fields=["competition_season", "player", "is_current"],
                name="player_event_profile_idx",
            ),
            models.Index(
                fields=["competition_season", "team", "is_current"],
                name="player_event_team_idx",
            ),
        ]

    def __str__(self) -> str:
        scope = self.team_id if self.team_id is not None else "total"
        return f"{self.player} @ {self.competition_season} ({scope})"


class PlayerSeasonRoleFeatureSnapshot(models.Model):
    """Versioned evidence snapshot for one player-team-season role context."""

    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="player_role_feature_snapshots",
    )
    player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.CASCADE,
        related_name="role_feature_snapshots",
    )
    team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.PROTECT,
        related_name="player_role_feature_snapshots",
    )
    feature_version = models.CharField(max_length=64, db_index=True)
    features = models.JSONField(default=dict, blank=True)
    verified_exposure_seconds = models.PositiveIntegerField(default=0)
    source_event_version = models.CharField(max_length=64)
    source_state_version = models.CharField(max_length=64)
    source_participation_version = models.CharField(max_length=64)
    source_possession_version = models.CharField(max_length=64)
    calculated_through_match = models.ForeignKey(
        ProviderMatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="player_role_features_calculated_through",
    )
    calculated_through_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=True, db_index=True)
    superseded_at = models.DateTimeField(null=True, blank=True)
    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition_season", "player", "team"],
                condition=models.Q(is_current=True),
                name="uniq_current_role_feature",
            ),
        ]
        indexes = [
            models.Index(
                fields=["competition_season", "team", "player", "is_current"],
                name="player_role_feature_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.player} @ {self.team}, {self.competition_season} features"


class PlayerSeasonRole(models.Model):
    """Versioned archetype and trait classification for one player-team stint."""

    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="player_season_roles",
    )
    player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.CASCADE,
        related_name="season_roles",
    )
    team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.PROTECT,
        related_name="player_season_roles",
    )
    feature_snapshot = models.ForeignKey(
        PlayerSeasonRoleFeatureSnapshot,
        on_delete=models.PROTECT,
        related_name="classifications",
    )
    primary_archetype = models.CharField(max_length=64, null=True, blank=True)
    primary_fit = models.FloatField(null=True, blank=True)
    secondary_archetype = models.CharField(max_length=64, null=True, blank=True)
    secondary_fit = models.FloatField(null=True, blank=True)
    classification_shape = models.CharField(max_length=24)
    evidence_confidence = models.CharField(max_length=24)
    traits = models.JSONField(default=list, blank=True)
    candidates = models.JSONField(default=list, blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    scoring_version = models.CharField(max_length=64, db_index=True)
    is_current = models.BooleanField(default=True, db_index=True)
    superseded_at = models.DateTimeField(null=True, blank=True)
    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition_season", "player", "team"],
                condition=models.Q(is_current=True),
                name="uniq_current_player_team_role",
            ),
        ]
        indexes = [
            models.Index(
                fields=["competition_season", "team", "player", "is_current"],
                name="player_team_role_idx",
            ),
            models.Index(
                fields=["competition_season", "primary_archetype", "is_current"],
                name="primary_archetype_idx",
            ),
        ]

    def __str__(self) -> str:
        label = self.primary_archetype or "unclassified"
        return f"{self.player} @ {self.team}, {self.competition_season}: {label}"


class TeamSeasonEventProfile(models.Model):
    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="team_event_profiles",
    )
    team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.CASCADE,
        related_name="season_event_profiles",
    )
    formula_version = models.CharField(
        max_length=32,
        default="event_profiles_v1",
        db_index=True,
    )
    materialized_ingestion_run = models.ForeignKey(
        IngestionRun,
        on_delete=models.PROTECT,
        related_name="team_event_profiles",
    )
    observed_match_count = models.PositiveSmallIntegerField(default=0)
    expected_match_count = models.PositiveSmallIntegerField(null=True, blank=True)
    coverage = models.FloatField(null=True, blank=True)
    valid_location_actions = models.PositiveIntegerField(default=0)
    touches = models.PositiveIntegerField(default=0)
    pass_attempts = models.PositiveIntegerField(default=0)
    pass_completions = models.PositiveIntegerField(default=0)
    progressive_pass_attempts = models.PositiveIntegerField(default=0)
    progressive_pass_completions = models.PositiveIntegerField(default=0)
    final_third_entries = models.PositiveIntegerField(default=0)
    box_entries = models.PositiveIntegerField(default=0)
    key_passes = models.PositiveIntegerField(default=0)
    crosses = models.PositiveIntegerField(default=0)
    long_balls = models.PositiveIntegerField(default=0)
    shots_for = models.PositiveIntegerField(default=0)
    goals_for = models.PositiveIntegerField(default=0)
    big_chance_shots_for = models.PositiveIntegerField(default=0)
    shots_against = models.PositiveIntegerField(default=0)
    goals_against = models.PositiveIntegerField(default=0)
    big_chance_shots_against = models.PositiveIntegerField(default=0)
    take_ons_attempted = models.PositiveIntegerField(default=0)
    take_ons_successful = models.PositiveIntegerField(default=0)
    defensive_actions = models.PositiveIntegerField(default=0)
    action_grid = models.JSONField(default=list, blank=True)
    opponent_action_grid = models.JSONField(default=list, blank=True)
    pass_flow = models.JSONField(default=list, blank=True)
    is_current = models.BooleanField(default=True, db_index=True)
    superseded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(coverage__isnull=True)
                    | models.Q(coverage__gte=0.0, coverage__lte=1.0)
                ),
                name="team_event_coverage_range",
            ),
            models.UniqueConstraint(
                fields=["competition_season", "team"],
                condition=models.Q(is_current=True),
                name="uniq_cur_team_event_profile",
            ),
        ]
        indexes = [
            models.Index(
                fields=["competition_season", "team", "is_current"],
                name="team_event_profile_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.team} @ {self.competition_season}"


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
    summary_expected_assists = models.FloatField(null=True, blank=True)
    total_shots = models.PositiveIntegerField(null=True, blank=True)
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
    points = models.IntegerField(null=True, blank=True)
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


class PlayerPositionResolution(models.Model):
    """
    Provenance-backed position fallback used only when normal source metadata
    still normalizes to UNK during merge.
    """

    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="position_resolutions",
    )
    canonical_player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.CASCADE,
        related_name="position_resolutions",
    )
    canonical_team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="player_position_resolutions",
    )
    source = models.CharField(
        max_length=32,
        choices=PositionResolutionSource.choices,
    )
    raw_position = models.CharField(max_length=64)
    position_group = models.CharField(max_length=8, choices=PositionGroup.choices)
    confidence = models.FloatField(default=1.0)
    evidence_json = models.JSONField(default=dict, blank=True)
    fetched_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition_season", "canonical_player"],
                name="uniq_position_resolution_per_player_slice",
            ),
        ]
        indexes = [
            models.Index(fields=["competition_season", "position_group"]),
            models.Index(fields=["source", "fetched_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.canonical_player} @ {self.competition_season}: {self.position_group}"


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
    ss_goals = models.PositiveIntegerField(null=True, blank=True)
    ss_assists = models.PositiveIntegerField(null=True, blank=True)
    ss_expected_goals = models.FloatField(null=True, blank=True)
    ss_expected_assists = models.FloatField(null=True, blank=True)
    ss_total_shots = models.PositiveIntegerField(null=True, blank=True)
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
            models.Index(
                fields=["competition_season", "canonical_display_team"],
                condition=models.Q(is_current=True),
                name="merged_player_current_team_idx",
            ),
            models.Index(
                fields=["competition_season", "canonical_player"],
                condition=models.Q(is_current=True),
                name="mp_cur_player_idx",
            ),
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
    points = models.IntegerField(null=True, blank=True)
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

    xg = models.FloatField(null=True, blank=True)
    xg_percentile = models.FloatField(null=True, blank=True)
    xg_per_90 = models.FloatField(null=True, blank=True)
    xg_per_90_percentile = models.FloatField(null=True, blank=True)
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
            models.Index(
                fields=["competition_season", "position_group", "minutes"],
                condition=models.Q(is_current=True),
                name="der_cur_pos_min_idx",
            ),
            models.Index(
                fields=["competition_season", "canonical_display_team"],
                condition=models.Q(is_current=True),
                name="derived_current_team_idx",
            ),
            models.Index(
                fields=["competition_season", "canonical_player"],
                condition=models.Q(is_current=True),
                name="derived_current_player_idx",
            ),
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
            models.Index(
                fields=["competition_season", "canonical_display_team"],
                condition=models.Q(is_current=True),
                name="gk_current_team_idx",
            ),
            models.Index(
                fields=["competition_season", "canonical_player"],
                condition=models.Q(is_current=True),
                name="gk_current_player_idx",
            ),
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


class GalaxySnapshot(models.Model):
    scope_code = models.CharField(max_length=32, db_index=True)
    season_label = models.CharField(max_length=32, db_index=True)
    ingestion_run = models.ForeignKey(
        IngestionRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="galaxy_snapshots",
    )
    model_version = models.CharField(max_length=32, default="galaxy_v2", db_index=True)
    feature_profile = models.CharField(max_length=64, blank=True, default="")
    min_minutes = models.PositiveIntegerField(default=450)
    default_min_minutes = models.PositiveIntegerField(default=900)
    top_k = models.PositiveSmallIntegerField(default=15)
    included_competition_season_ids = models.JSONField(default=list, blank=True)
    excluded_competitions = models.JSONField(default=list, blank=True)
    feature_names = models.JSONField(default=list, blank=True)
    feature_weights = models.JSONField(default=dict, blank=True)
    feature_groups = models.JSONField(default=dict, blank=True)
    imputation_values = models.JSONField(default=dict, blank=True)
    scaling = models.JSONField(default=dict, blank=True)
    position_penalties = models.JSONField(default=dict, blank=True)
    diagnostics = models.JSONField(default=dict, blank=True)
    is_current = models.BooleanField(default=True, db_index=True)
    superseded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scope_code", "season_label"],
                condition=models.Q(is_current=True),
                name="uniq_current_galaxy_snapshot_scope_season",
            ),
        ]
        indexes = [
            models.Index(fields=["scope_code", "season_label", "is_current"]),
            models.Index(fields=["feature_profile"]),
        ]

    def __str__(self) -> str:
        return f"galaxy {self.scope_code} {self.season_label} ({self.feature_profile})"


class GalaxyArchetype(models.Model):
    snapshot = models.ForeignKey(
        GalaxySnapshot,
        on_delete=models.CASCADE,
        related_name="archetypes",
    )
    archetype_key = models.CharField(max_length=64)
    position_group = models.CharField(
        max_length=8,
        choices=PositionGroup.choices,
        default=PositionGroup.UNKNOWN,
    )
    cluster_id = models.PositiveSmallIntegerField(default=0)
    label = models.CharField(max_length=80)
    color = models.CharField(max_length=16, blank=True, default="")
    size = models.PositiveIntegerField(default=0)
    centroid = models.JSONField(default=dict, blank=True)
    feature_signature = models.JSONField(default=dict, blank=True)
    representative_players = models.JSONField(default=list, blank=True)
    diagnostics = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "archetype_key"],
                name="uniq_galaxy_archetype_key_per_snapshot",
            ),
        ]
        indexes = [
            models.Index(fields=["snapshot", "position_group"]),
            models.Index(fields=["snapshot", "cluster_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.label} @ {self.snapshot}"


class GalaxyPlayerEmbedding(models.Model):
    snapshot = models.ForeignKey(
        GalaxySnapshot,
        on_delete=models.CASCADE,
        related_name="player_embeddings",
    )
    galaxy_player_id = models.CharField(max_length=80, db_index=True)
    competition_season = models.ForeignKey(
        CompetitionSeason,
        on_delete=models.CASCADE,
        related_name="galaxy_player_embeddings",
    )
    canonical_player = models.ForeignKey(
        CanonicalPlayer,
        on_delete=models.CASCADE,
        related_name="galaxy_embeddings",
    )
    canonical_display_team = models.ForeignKey(
        CanonicalTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="galaxy_display_team_rows",
    )
    derived_stats = models.ForeignKey(
        PlayerSeasonDerivedStats,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="galaxy_embeddings",
    )
    primary_archetype = models.ForeignKey(
        GalaxyArchetype,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_players",
    )
    secondary_archetype = models.ForeignKey(
        GalaxyArchetype,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="secondary_players",
    )
    position_group = models.CharField(
        max_length=8,
        choices=PositionGroup.choices,
        default=PositionGroup.UNKNOWN,
    )
    native_position = models.CharField(max_length=64, blank=True)
    minutes = models.PositiveIntegerField(null=True, blank=True)
    primary_archetype_label = models.CharField(max_length=80, blank=True, default="")
    primary_archetype_confidence = models.FloatField(null=True, blank=True)
    secondary_archetype_label = models.CharField(max_length=80, blank=True, default="")
    secondary_archetype_confidence = models.FloatField(null=True, blank=True)
    archetype_margin = models.FloatField(null=True, blank=True)
    archetype_diagnostics = models.JSONField(default=dict, blank=True)
    feature_values = models.JSONField(default=dict, blank=True)
    scaled_features = models.JSONField(default=dict, blank=True)
    imputed_features = models.JSONField(default=list, blank=True)
    umap_x = models.FloatField()
    umap_y = models.FloatField()
    umap_z = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "galaxy_player_id"],
                name="uniq_galaxy_player_id_per_snapshot",
            ),
            models.UniqueConstraint(
                fields=["snapshot", "competition_season", "canonical_player"],
                name="uniq_galaxy_competition_player_per_snapshot",
            ),
        ]
        indexes = [
            models.Index(fields=["snapshot", "position_group"]),
            models.Index(fields=["snapshot", "canonical_display_team"]),
            models.Index(fields=["snapshot", "primary_archetype"]),
            models.Index(fields=["competition_season", "canonical_player"]),
            models.Index(fields=["snapshot", "minutes"], name="gal_emb_snap_min_idx"),
            models.Index(
                fields=["snapshot", "position_group", "minutes"],
                name="galaxy_embedding_pos_min_idx",
            ),
            models.Index(
                fields=["snapshot", "canonical_display_team", "minutes"],
                name="galaxy_embedding_team_min_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.galaxy_player_id} @ {self.snapshot}"


class GalaxySimilarity(models.Model):
    snapshot = models.ForeignKey(
        GalaxySnapshot,
        on_delete=models.CASCADE,
        related_name="similarities",
    )
    source_embedding = models.ForeignKey(
        GalaxyPlayerEmbedding,
        on_delete=models.CASCADE,
        related_name="similarity_rows",
    )
    similar_embedding = models.ForeignKey(
        GalaxyPlayerEmbedding,
        on_delete=models.CASCADE,
        related_name="similar_to_rows",
    )
    rank = models.PositiveSmallIntegerField()
    base_distance = models.FloatField()
    distance = models.FloatField()
    position_multiplier = models.FloatField(default=1.0)
    candidate_percentile_score = models.FloatField()
    absolute_fit_score = models.FloatField()
    profile_match_score = models.FloatField()
    weak_absolute_fit = models.BooleanField(default=False)
    match_context = models.CharField(max_length=32, blank=True, default="")
    explanation = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "source_embedding", "rank"],
                name="uniq_galaxy_similarity_rank_per_source",
            ),
            models.UniqueConstraint(
                fields=["snapshot", "source_embedding", "similar_embedding"],
                name="uniq_galaxy_similarity_pair_per_snapshot",
            ),
        ]
        indexes = [
            models.Index(fields=["snapshot", "source_embedding", "rank"]),
            models.Index(fields=["snapshot", "profile_match_score"]),
        ]

    def __str__(self) -> str:
        return (
            f"galaxy sim {self.source_embedding_id}->{self.similar_embedding_id} "
            f"({self.profile_match_score:.1f}) @ {self.snapshot_id}"
        )
