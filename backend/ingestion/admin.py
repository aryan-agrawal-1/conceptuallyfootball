from django.contrib import admin

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
    PlayerSeasonEmbedding,
    PlayerSeasonClubSpell,
    PlayerSeasonSimilarity,
    ProviderPlayerMapping,
    ProviderTeamMapping,
    ReepPlayerRow,
    ReepTeamRow,
    Season,
    SofascorePlayerSeasonSource,
    SofascoreTeamSeasonSource,
    UnderstatPlayerSeasonSource,
    UnmatchedProviderPlayer,
    UnmatchedProviderTeam,
)
from ingestion.services.identity import (
    apply_manual_player_resolution,
    apply_manual_team_resolution,
    reattach_slice_identities,
)


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ("id", "short_code", "name", "country")
    search_fields = ("name", "short_code")


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
        "understat_league",
        "understat_season_year",
        "sofascore_unique_tournament_id",
        "sofascore_season_id",
        "refresh_enabled",
        "is_active",
    )
    list_filter = (
        "refresh_enabled",
        "is_active",
        "competition",
        "player_data_mode",
        "has_understat",
        "has_sofascore",
    )
    search_fields = ("season__label", "competition__short_code")
    readonly_fields = ("metric_availability",)


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
    list_filter = ("provider", "competition_season")
    search_fields = ("provider_player_id", "player_name")
    raw_id_fields = ("resolved_player", "first_seen_run")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.resolved_player and (not change or "resolved_player" in form.changed_data):
            apply_manual_player_resolution(obj, obj.resolved_player)
            reattach_slice_identities(obj.competition_season)


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
