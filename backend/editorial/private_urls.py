from django.urls import path

from editorial.api import article_detail, article_preview, articles


urlpatterns = [
    path("articles", articles, name="editorial-articles"),
    path("articles/<uuid:article_id>", article_detail, name="editorial-article-detail"),
    path("articles/<uuid:article_id>/preview", article_preview, name="editorial-article-preview"),
]
