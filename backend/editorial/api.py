from __future__ import annotations

import json
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from accounts.access import access_error
from accounts.profiles import display_name_for, needs_writer_onboarding, social_links_for
from editorial.content import clean_text, normalize_document
from editorial.models import Article, ArticleRevision, ArticleStatus


def json_body(request: HttpRequest) -> dict:
    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def private_json(payload: dict, *, status: int = 200) -> JsonResponse:
    response = JsonResponse(payload, status=status)
    response["Cache-Control"] = "private, no-store"
    response["Vary"] = "Cookie"
    return response


def public_preview_json(payload: dict, *, status: int = 200) -> JsonResponse:
    response = JsonResponse(payload, status=status)
    response["Cache-Control"] = "private, no-store"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


def article_summary(article: Article) -> dict:
    return {
        "id": str(article.id),
        "title": article.title,
        "subtitle": article.subtitle,
        "status": article.status,
        "revision": article.revision,
        "preview_enabled": article.preview_enabled,
        "created_at": article.created_at.isoformat(),
        "updated_at": article.updated_at.isoformat(),
    }


def article_payload(article: Article, *, include_preview_token: bool = True) -> dict:
    payload = {
        **article_summary(article),
        "author": {
            "id": article.author_id,
            "display_name": display_name_for(article.author),
            "social_links": social_links_for(article.author),
        },
        "document": normalize_document(article.document),
        "revisions": [
            {"number": revision.number, "created_at": revision.created_at.isoformat()}
            for revision in article.revisions.all()[:20]
        ],
    }
    if include_preview_token:
        payload["preview_token"] = str(article.preview_token) if article.preview_enabled else None
    return payload


def editorial_error(request: HttpRequest) -> JsonResponse | None:
    error = access_error(request, "accounts.access_editorial_workspace")
    if error is not None:
        return error
    if needs_writer_onboarding(request.user):
        return private_json(
            {"detail": "Complete your writer profile to continue.", "code": "onboarding_required"},
            status=403,
        )
    return None


def owned_article(request: HttpRequest, article_id) -> Article:
    return get_object_or_404(
        Article.objects.select_related("author"),
        id=article_id,
        author=request.user,
    )


def validation_error(error: ValidationError) -> JsonResponse:
    return private_json(
        {"detail": "The article contains invalid content.", "errors": error.messages},
        status=400,
    )


@require_http_methods(["GET", "POST"])
@never_cache
def articles(request: HttpRequest) -> JsonResponse:
    error = editorial_error(request)
    if error is not None:
        return error

    if request.method == "GET":
        queryset = Article.objects.filter(author=request.user)
        query = request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(Q(title__icontains=query) | Q(subtitle__icontains=query))
        preview = request.GET.get("preview")
        if preview == "shared":
            queryset = queryset.filter(preview_enabled=True)
        return private_json({"articles": [article_summary(article) for article in queryset[:200]]})

    payload = json_body(request)
    try:
        title = clean_text(payload.get("title", "Untitled analysis"), field="Title", maximum=180).strip()
        article = Article.objects.create(
            author=request.user,
            title=title or "Untitled analysis",
        )
        ArticleRevision.objects.create(
            article=article,
            number=article.revision,
            title=article.title,
            subtitle=article.subtitle,
            document=article.document,
            created_by=request.user,
        )
    except ValidationError as validation:
        return validation_error(validation)
    article = owned_article(request, article.id)
    return private_json({"article": article_payload(article)}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
@never_cache
def article_detail(request: HttpRequest, article_id) -> JsonResponse:
    error = editorial_error(request)
    if error is not None:
        return error

    if request.method == "GET":
        return private_json({"article": article_payload(owned_article(request, article_id))})
    if request.method == "DELETE":
        article = owned_article(request, article_id)
        if article.status != ArticleStatus.DRAFT:
            return private_json({"detail": "Only drafts can be deleted."}, status=409)
        article.delete()
        return private_json({"deleted": True})

    payload = json_body(request)
    try:
        expected_revision = int(payload.get("revision"))
    except (TypeError, ValueError):
        return private_json({"detail": "A valid revision is required."}, status=400)

    with transaction.atomic():
        article = get_object_or_404(
            Article.objects.select_for_update().select_related("author"),
            id=article_id,
            author=request.user,
        )
        if expected_revision != article.revision:
            article = owned_article(request, article.id)
            return private_json(
                {
                    "detail": "This draft changed in another tab. Reload before saving again.",
                    "code": "revision_conflict",
                    "article": article_payload(article),
                },
                status=409,
            )
        try:
            title = clean_text(payload.get("title", article.title), field="Title", maximum=180).strip()
            subtitle = clean_text(
                payload.get("subtitle", article.subtitle),
                field="Subtitle",
                maximum=280,
            ).strip()
            document = normalize_document(payload.get("document", article.document))
        except ValidationError as validation:
            return validation_error(validation)

        title = title or "Untitled analysis"
        changed = (title, subtitle, document) != (article.title, article.subtitle, article.document)
        if changed:
            article.title = title
            article.subtitle = subtitle
            article.document = document
            article.revision += 1
            article.save(update_fields=("title", "subtitle", "document", "revision", "updated_at"))
            ArticleRevision.objects.create(
                article=article,
                number=article.revision,
                title=article.title,
                subtitle=article.subtitle,
                document=article.document,
                created_by=request.user,
            )
    article = owned_article(request, article.id)
    return private_json({"article": article_payload(article)})


@require_http_methods(["POST"])
@never_cache
def article_preview(request: HttpRequest, article_id) -> JsonResponse:
    error = editorial_error(request)
    if error is not None:
        return error
    article = owned_article(request, article_id)
    payload = json_body(request)
    enabled = payload.get("enabled")
    rotate = payload.get("rotate") is True
    if not isinstance(enabled, bool):
        return private_json({"detail": "Preview enabled must be true or false."}, status=400)
    was_enabled = article.preview_enabled
    article.preview_enabled = enabled
    if rotate or (enabled and not was_enabled):
        article.preview_token = uuid.uuid4()
    article.save(update_fields=("preview_enabled", "preview_token", "updated_at"))
    article = owned_article(request, article.id)
    return private_json({"article": article_payload(article)})


@require_GET
@never_cache
def shared_preview(request: HttpRequest, token) -> JsonResponse:
    article = get_object_or_404(
        Article.objects.select_related("author"),
        preview_token=token,
        preview_enabled=True,
    )
    return public_preview_json({"article": article_payload(article, include_preview_token=False)})
