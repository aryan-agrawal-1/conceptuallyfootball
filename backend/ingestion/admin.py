from django.contrib import admin, messages
from django.db import transaction
from django.utils.html import format_html_join

from ingestion.api_cache import invalidate_materialized_api_payloads
from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    GalaxyArchetype,
    GalaxyPlayerEmbedding,
    GalaxySimilarity,
    GalaxySnapshot,
    IngestionBatch,
    IngestionBatchItem,
    IngestionRun,
    MergedPlayerSeason,
    MergedTeamSeason,
    PlayerSeasonClubSpell,
    PlayerSeasonEmbedding,
    PlayerSeasonEventProfile,
    PlayerSeasonSimilarity,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchPlayedPeriod,
    ProviderMatchPlayerInterval,
    ProviderMatchPlayerParticipation,
    ProviderMatchPlayerParticipationBuild,
    ProviderMatchPlayerStateExposure,
    ProviderMatchPayload,
    ProviderMatchTeamGameStateEpisode,
    ProviderMatchTeamGameStateExposure,
    ProviderPlayerMapping,
    ProviderTeamMapping,
    ReepPlayerRow,
    ReepTeamRow,
    Season,
    SofascorePlayerSeasonSource,
    SofascoreTeamSeasonSource,
    TeamSeasonEventProfile,
    UnderstatPlayerSeasonSource,
    UnmatchedProviderPlayer,
    UnmatchedProviderTeam,
)
from ingestion.services.identity import (
    apply_manual_player_resolution,
    apply_manual_team_resolution,
    reattach_slice_identities,
    retry_unmatched_player_resolution,
    unmatched_player_identity_candidates,
)


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "short_code",
        "name",
        "country",
        "competition_type",
        "include_in_domestic_aggregates",
        "minimum_eligible_minutes",
    )
    list_filter = ("competition_type", "include_in_domestic_aggregates")
    search_fields = ("name", "short_code")

    def save_model(self, request, obj, form, change) -> None:
        super().save_model(request, obj, form, change)
        invalidate_materialized_api_payloads()


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ("id", "label", "sort_order")


@admin.register(CompetitionSeason)
class CompetitionSeasonAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "competition",
        "season",
        "player_data_mode",
        "has_understat",
        "has_sofascore",
        "has_whoscored",
        "understat_league",
        "understat_season_year",
        "sofascore_unique_tournament_id",
        "sofascore_season_id",
        "whoscored_league",
        "whoscored_season",
        "whoscored_expected_match_count",
        "refresh_enabled",
        "is_active",
        "is_published",
    )
    list_filter = (
        "refresh_enabled",
        "is_active",
        "is_published",
        "competition",
        "player_data_mode",
        "has_understat",
        "has_sofascore",
        "has_whoscored",
    )
    search_fields = ("season__label", "competition__short_code")
    readonly_fields = ("metric_availability", "is_published")


@admin.register(IngestionRun)
class IngestionRunAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "status", "competition_season", "started_at", "finished_at")
    list_filter = ("kind", "status")
    readonly_fields = ("stats", "error_detail", "started_at", "finished_at")


@admin.register(IngestionBatch)
class IngestionBatchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "kind",
        "scheduled_for_date",
        "status",
        "manual",
        "planned_start_at",
        "started_at",
        "finished_at",
    )
    list_filter = ("kind", "status", "manual", "scheduled_for_date")
    readonly_fields = (
        "summary_stats",
        "aggregate_run_ids",
        "error_detail",
        "created_at",
        "updated_at",
    )


@admin.register(IngestionBatchItem)
class IngestionBatchItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "batch",
        "competition_season",
        "planned_order",
        "status",
        "current_stage",
        "eta",
        "started_at",
        "finished_at",
    )
    list_filter = ("status", "current_stage", "competition_season")
    raw_id_fields = ("batch", "competition_season")
    readonly_fields = (
        "stage_run_ids",
        "stage_stats",
        "error_detail",
        "created_at",
        "updated_at",
    )


@admin.register(ProviderMatch)
class ProviderMatchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "provider",
        "provider_match_id",
        "competition_season",
        "kickoff_at",
        "status",
        "home_team",
        "away_team",
        "updated_at",
    )
    list_filter = ("provider", "status", "competition_season")
    search_fields = (
        "provider_match_id",
        "home_provider_team_id",
        "away_provider_team_id",
        "home_team__name",
        "away_team__name",
    )
    raw_id_fields = ("competition_season", "home_team", "away_team")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ProviderMatchPayload)
class ProviderMatchPayloadAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "provider_match",
        "storage_backend",
        "lifecycle_state",
        "payload_size_bytes",
        "uncompressed_size_bytes",
        "schema_version",
        "fetched_at",
    )
    list_filter = ("storage_backend", "lifecycle_state", "schema_version")
    search_fields = ("provider_match__provider_match_id", "payload_sha256")
    raw_id_fields = ("provider_match",)
    exclude = ("payload_gzip",)
    readonly_fields = (
        "payload_sha256",
        "payload_size_bytes",
        "uncompressed_size_bytes",
        "preliminary_sha256",
        "preliminary_fetched_at",
        "final_sha256",
        "final_fetched_at",
        "source_updated_at",
        "fetched_at",
    )


@admin.register(ProviderMatchEvent)
class ProviderMatchEventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "provider_match",
        "event_index",
        "period",
        "minute",
        "second",
        "event_type",
        "team",
        "player",
    )
    list_filter = ("event_type", "period", "outcome_successful")
    search_fields = (
        "provider_match__provider_match_id",
        "provider_event_id",
        "provider_team_id",
        "provider_player_id",
        "player__display_name",
    )
    raw_id_fields = ("provider_match", "team", "player")


@admin.register(ProviderMatchGameState)
class ProviderMatchGameStateAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "provider_match",
        "status",
        "event_count",
        "goal_event_count",
        "replayed_home_score",
        "replayed_away_score",
        "calculated_at",
    )
    list_filter = ("status", "calculation_version")
    search_fields = ("provider_match__provider_match_id",)
    raw_id_fields = ("provider_match",)
    readonly_fields = ("diagnostics", "calculated_at")


@admin.register(ProviderMatchPlayedPeriod)
class ProviderMatchPlayedPeriodAdmin(admin.ModelAdmin):
    list_display = (
        "provider_match",
        "period_index",
        "period",
        "start_second",
        "end_second",
        "duration_seconds",
    )
    raw_id_fields = ("provider_match",)


@admin.register(ProviderMatchTeamGameStateEpisode)
class ProviderMatchTeamGameStateEpisodeAdmin(admin.ModelAdmin):
    list_display = (
        "provider_match",
        "focal_team",
        "episode_index",
        "state",
        "goal_difference",
        "phase",
        "start_second",
        "end_second",
    )
    list_filter = ("state", "phase", "draw_provenance")
    raw_id_fields = ("provider_match", "focal_team", "entry_event")


@admin.register(ProviderMatchTeamGameStateExposure)
class ProviderMatchTeamGameStateExposureAdmin(admin.ModelAdmin):
    list_display = (
        "provider_match",
        "focal_team",
        "state",
        "goal_difference",
        "phase",
        "exposure_seconds",
    )
    list_filter = ("state", "phase", "draw_provenance")
    raw_id_fields = ("provider_match", "focal_team")


@admin.register(ProviderMatchPlayerParticipationBuild)
class ProviderMatchPlayerParticipationBuildAdmin(admin.ModelAdmin):
    list_display = (
        "provider_match",
        "status",
        "participant_count",
        "verified_participant_count",
        "excluded_participant_count",
        "interval_count",
        "calculated_at",
    )
    list_filter = ("status", "formula_version")
    raw_id_fields = ("provider_match",)
    readonly_fields = ("diagnostics", "calculated_at")


@admin.register(ProviderMatchPlayerParticipation)
class ProviderMatchPlayerParticipationAdmin(admin.ModelAdmin):
    list_display = (
        "provider_match",
        "player",
        "team",
        "roster_role",
        "status",
        "on_pitch_seconds",
    )
    list_filter = ("roster_role", "status", "confidence")
    raw_id_fields = ("build", "provider_match", "team", "player")


@admin.register(ProviderMatchPlayerInterval)
class ProviderMatchPlayerIntervalAdmin(admin.ModelAdmin):
    list_display = (
        "participation",
        "sequence",
        "start_second",
        "end_second",
        "duration_seconds",
        "confidence",
    )
    raw_id_fields = ("participation",)


@admin.register(ProviderMatchPlayerStateExposure)
class ProviderMatchPlayerStateExposureAdmin(admin.ModelAdmin):
    list_display = (
        "player_interval",
        "coarse_state",
        "goal_difference",
        "phase",
        "duration_seconds",
    )
    list_filter = ("coarse_state", "phase", "provenance")
    raw_id_fields = ("player_interval", "team_episode")


@admin.register(PlayerSeasonEventProfile)
class PlayerSeasonEventProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "competition_season",
        "player",
        "split_type",
        "team",
        "formula_version",
        "observed_match_count",
        "is_current",
        "created_at",
    )
    list_filter = ("competition_season", "split_type", "formula_version", "is_current")
    search_fields = ("player__display_name", "team__name")
    raw_id_fields = ("competition_season", "player", "team", "materialized_ingestion_run")
    readonly_fields = ("action_grid", "created_at")


@admin.register(TeamSeasonEventProfile)
class TeamSeasonEventProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "competition_season",
        "team",
        "formula_version",
        "observed_match_count",
        "expected_match_count",
        "coverage",
        "is_current",
        "created_at",
    )
    list_filter = ("competition_season", "formula_version", "is_current")
    search_fields = ("team__name",)
    raw_id_fields = ("competition_season", "team", "materialized_ingestion_run")
    readonly_fields = ("action_grid", "opponent_action_grid", "pass_flow", "created_at")


@admin.register(ReepPlayerRow)
class ReepPlayerRowAdmin(admin.ModelAdmin):
    list_display = ("reep_id", "full_name", "understat_player_id", "sofascore_player_id", "synced_at")
    search_fields = ("reep_id", "full_name", "understat_player_id", "sofascore_player_id")


@admin.register(ReepTeamRow)
class ReepTeamRowAdmin(admin.ModelAdmin):
    list_display = ("reep_id", "name", "understat_team_id", "sofascore_team_id", "synced_at")
    search_fields = ("reep_id", "name")


@admin.register(CanonicalPlayer)
class CanonicalPlayerAdmin(admin.ModelAdmin):
    list_display = ("id", "display_name", "reep_id", "created_at")
    search_fields = ("display_name", "reep_id")


@admin.register(CanonicalTeam)
class CanonicalTeamAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "reep_id", "created_at")
    search_fields = ("name", "reep_id")


@admin.register(ProviderPlayerMapping)
class ProviderPlayerMappingAdmin(admin.ModelAdmin):
    list_display = ("id", "provider", "provider_player_id", "canonical_player", "match_method", "updated_at")
    list_filter = ("provider", "match_method")
    search_fields = ("provider_player_id", "canonical_player__display_name")


@admin.register(ProviderTeamMapping)
class ProviderTeamMappingAdmin(admin.ModelAdmin):
    list_display = ("id", "provider", "provider_team_id", "canonical_team", "match_method", "updated_at")
    list_filter = ("provider", "match_method")


@admin.register(UnmatchedProviderPlayer)
class UnmatchedProviderPlayerAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "competition_season",
        "provider",
        "provider_player_id",
        "player_name",
        "resolved_player",
        "resolved_at",
    )
    list_filter = ("provider", "competition_season", "resolved_at")
    search_fields = (
        "provider_player_id",
        "player_name",
        "resolved_player__display_name",
        "resolved_player__reep_id",
    )
    autocomplete_fields = ("resolved_player",)
    raw_id_fields = ("first_seen_run",)
    readonly_fields = ("automatic_candidate_details", "resolved_at")
    actions = ("retry_automatic_resolution",)

    def has_add_permission(self, request):
        return False

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.resolved_player_id:
            fields.append("resolved_player")
        return tuple(fields)

    @admin.display(description="Automatic candidate evidence")
    def automatic_candidate_details(self, obj):
        if obj is None:
            return "Candidate evidence is available after ingestion creates a review case."
        if obj.resolved_player_id:
            return f"Resolved to {obj.resolved_player}."
        candidates = unmatched_player_identity_candidates(obj)
        if not candidates:
            return "No exact, team-scoped candidate. Select an existing canonical player manually."
        return format_html_join(
            "",
            "<div><strong>{}</strong> (#{}): {}; teams {}; sources {}</div>",
            (
                (
                    candidate.canonical_player.display_name,
                    candidate.canonical_player.id,
                    candidate.match_reason,
                    ", ".join(str(team_id) for team_id in candidate.canonical_team_ids) or "none",
                    ", ".join(candidate.source_providers),
                )
                for candidate in candidates
            ),
        )

    @admin.action(description="Retry conservative automatic identity resolution")
    def retry_automatic_resolution(self, request, queryset):
        resolved_count = 0
        unresolved_count = 0
        for unmatched in queryset.filter(resolved_player__isnull=True).select_related(
            "competition_season"
        ):
            if retry_unmatched_player_resolution(unmatched) is None:
                unresolved_count += 1
            else:
                resolved_count += 1
        self.message_user(
            request,
            f"Resolved {resolved_count}; left {unresolved_count} for manual review.",
            level=messages.SUCCESS if resolved_count else messages.WARNING,
        )

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            if obj.resolved_player and (not change or "resolved_player" in form.changed_data):
                apply_manual_player_resolution(obj, obj.resolved_player)


@admin.register(UnmatchedProviderTeam)
class UnmatchedProviderTeamAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "competition_season",
        "provider",
        "provider_team_id",
        "team_name",
        "resolved_team",
        "resolved_at",
    )
    list_filter = ("provider", "competition_season")
    raw_id_fields = ("resolved_team", "first_seen_run")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.resolved_team and (not change or "resolved_team" in form.changed_data):
            apply_manual_team_resolution(obj, obj.resolved_team)
            reattach_slice_identities(obj.competition_season)


@admin.register(UnderstatPlayerSeasonSource)
class UnderstatPlayerSeasonSourceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "competition_season",
        "provider_player_id",
        "player_name",
        "canonical_player",
        "canonical_team",
        "ingestion_run",
    )
    list_filter = ("competition_season",)
    search_fields = ("player_name", "provider_player_id")
    raw_id_fields = ("canonical_player", "canonical_team", "ingestion_run")
    readonly_fields = ("provider_team_ids",)


@admin.register(SofascorePlayerSeasonSource)
class SofascorePlayerSeasonSourceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "competition_season",
        "provider_player_id",
        "player_name",
        "rating",
        "canonical_player",
        "canonical_team",
        "ingestion_run",
    )
    list_filter = ("competition_season",)
    search_fields = ("player_name", "provider_player_id")
    raw_id_fields = ("canonical_player", "canonical_team", "ingestion_run")
    readonly_fields = ("group_stats",)


@admin.register(SofascoreTeamSeasonSource)
class SofascoreTeamSeasonSourceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "competition_season",
        "provider_team_id",
        "team_name",
        "rank",
        "canonical_team",
        "has_overall_stats",
        "ingestion_run",
    )
    list_filter = ("competition_season", "has_overall_stats")
    search_fields = ("team_name", "provider_team_id", "canonical_team__name")
    raw_id_fields = ("canonical_team", "ingestion_run")
    readonly_fields = ("standings_row_json", "overall_stats_json")


@admin.register(PlayerSeasonClubSpell)
class PlayerSeasonClubSpellAdmin(admin.ModelAdmin):
    list_display = ("id", "canonical_player", "competition_season", "canonical_team", "minutes", "source_provider")


@admin.register(MergedPlayerSeason)
class MergedPlayerSeasonAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "competition_season",
        "canonical_player",
        "canonical_display_team",
        "position_group",
        "is_current",
        "superseded_at",
    )
    list_filter = ("is_current", "competition_season", "position_group")
    search_fields = ("canonical_player__display_name",)
    readonly_fields = ("superseded_at", "superseded_by", "created_at")


@admin.register(MergedTeamSeason)
class MergedTeamSeasonAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "competition_season",
        "canonical_team",
        "rank",
        "points",
        "is_current",
        "superseded_at",
    )
    list_filter = ("is_current", "competition_season")
    search_fields = ("canonical_team__name",)
    readonly_fields = ("superseded_at", "superseded_by", "created_at")


@admin.register(PlayerSeasonEmbedding)
class PlayerSeasonEmbeddingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "competition_season",
        "canonical_player",
        "cluster_id",
        "position_group",
        "minutes",
        "is_current",
    )
    list_filter = ("competition_season", "is_current", "position_group", "cluster_id")
    search_fields = ("canonical_player__display_name",)
    readonly_fields = ("created_at",)


@admin.register(PlayerSeasonSimilarity)
class PlayerSeasonSimilarityAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "competition_season",
        "canonical_player",
        "similar_player",
        "rank",
        "similarity",
        "is_current",
    )
    list_filter = ("competition_season", "is_current")
    search_fields = ("canonical_player__display_name", "similar_player__display_name")


@admin.register(GalaxySnapshot)
class GalaxySnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "scope_code",
        "season_label",
        "feature_profile",
        "min_minutes",
        "is_current",
        "created_at",
    )
    list_filter = ("scope_code", "season_label", "feature_profile", "is_current")
    readonly_fields = ("created_at", "superseded_at")


@admin.register(GalaxyArchetype)
class GalaxyArchetypeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "snapshot",
        "archetype_key",
        "position_group",
        "label",
        "size",
    )
    list_filter = ("snapshot", "position_group")
    search_fields = ("label", "archetype_key")
    readonly_fields = ("created_at",)


@admin.register(GalaxyPlayerEmbedding)
class GalaxyPlayerEmbeddingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "snapshot",
        "galaxy_player_id",
        "canonical_player",
        "competition_season",
        "position_group",
        "primary_archetype_label",
        "minutes",
    )
    list_filter = ("snapshot", "competition_season", "position_group", "primary_archetype")
    search_fields = ("galaxy_player_id", "canonical_player__display_name")
    readonly_fields = ("created_at",)


@admin.register(GalaxySimilarity)
class GalaxySimilarityAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "snapshot",
        "source_embedding",
        "similar_embedding",
        "rank",
        "profile_match_score",
        "match_context",
    )
    list_filter = ("snapshot", "match_context", "weak_absolute_fit")
    search_fields = (
        "source_embedding__canonical_player__display_name",
        "similar_embedding__canonical_player__display_name",
    )
    readonly_fields = ("created_at",)
