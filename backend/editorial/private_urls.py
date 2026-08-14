from django.urls import path

from editorial.api import (
    article_detail,
    article_preview,
    article_revision_detail,
    article_workflow,
    articles,
)
from editorial.exports import article_export


urlpatterns = [
    path("articles", articles, name="editorial-articles"),
    path("articles/<uuid:article_id>", article_detail, name="editorial-article-detail"),
    path(
        "articles/<uuid:article_id>/revisions/<int:revision_number>",
        article_revision_detail,
        name="editorial-article-revision-detail",
    ),
    path("articles/<uuid:article_id>/preview", article_preview, name="editorial-article-preview"),
    path("articles/<uuid:article_id>/workflow", article_workflow, name="editorial-article-workflow"),
    path(
        "articles/<uuid:article_id>/exports/<str:export_format>",
        article_export,
        name="editorial-article-export",
    ),
]
