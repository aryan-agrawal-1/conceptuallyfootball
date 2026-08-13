from django.urls import path

from editorial.api import (
    article_detail,
    article_preview,
    article_revision_detail,
    article_workflow,
    articles,
)


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
]
