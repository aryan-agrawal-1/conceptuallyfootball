from django.urls import path

from editorial.api import player_related_analysis, shared_preview, team_related_analysis


urlpatterns = [
    path("previews/<uuid:token>", shared_preview, name="editorial-shared-preview"),
    path(
        "entities/player/<int:entity_id>/related",
        player_related_analysis,
        name="editorial-player-related-analysis",
    ),
    path(
        "entities/team/<int:entity_id>/related",
        team_related_analysis,
        name="editorial-team-related-analysis",
    ),
]
