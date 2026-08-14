from django.urls import path

from editorial.api import (
    player_related_analysis,
    public_articles,
    public_article_detail,
    public_article_detail_by_id,
    public_sitemap,
    shared_preview,
    team_related_analysis,
)
from editorial.exports import public_analysis_feed, public_visual_asset


urlpatterns = [
    path("sitemap.xml", public_sitemap, name="editorial-public-sitemap"),
    path("feed.xml", public_analysis_feed, name="editorial-public-feed"),
    path("previews/<uuid:token>", shared_preview, name="editorial-shared-preview"),
    path("articles", public_articles, name="editorial-public-articles"),
    path(
        "articles/<uuid:article_id>",
        public_article_detail_by_id,
        name="editorial-public-article-detail",
    ),
    path("articles/<slug:slug>", public_article_detail, name="editorial-public-article-detail-by-slug"),
    path(
        "articles/<slug:slug>/visuals/<uuid:block_id>.<str:extension>",
        public_visual_asset,
        name="editorial-public-visual-asset",
    ),
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
