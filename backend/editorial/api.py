from __future__ import annotations

import json
import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from accounts.access import access_error
from accounts.profiles import display_name_for, needs_writer_onboarding, social_links_for
from editorial.content import clean_text, normalize_document
from editorial.models import (
    Article,
    ArticlePlayerReference,
    ArticlePlayerSubject,
    ArticlePublication,
    ArticleRevision,
    ArticleStatus,
    ArticleTeamReference,
    ArticleTeamSubject,
)
from editorial.relationships import (
    normalize_subjects,
    references_payload,
    save_subjects,
    subjects_payload,
    sync_references,
)
from editorial.workflow import (
    EDITABLE_STATUSES,
    WorkflowConflict,
    can_approve,
    publish_due_articles,
    transition_article,
)
from ingestion.models import CanonicalPlayer, CanonicalTeam


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
        "preview_expires_at": (
            article.preview_expires_at.isoformat() if article.preview_expires_at else None
        ),
        "submitted_at": article.submitted_at.isoformat() if article.submitted_at else None,
        "approved_at": article.approved_at.isoformat() if article.approved_at else None,
        "scheduled_for": article.scheduled_for.isoformat() if article.scheduled_for else None,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "author": {
            "id": article.author_id,
            "display_name": display_name_for(article.author),
        },
        "created_at": article.created_at.isoformat(),
        "updated_at": article.updated_at.isoformat(),
    }


def article_payload(
    article: Article,
    *,
    include_preview_token: bool = True,
    include_workflow: bool = True,
) -> dict:
    payload = {
        **article_summary(article),
        "author": {
            "id": article.author_id,
            "display_name": display_name_for(article.author),
            "social_links": social_links_for(article.author),
        },
        "document": normalize_document(article.document),
        "subjects": subjects_payload(article),
        "references": references_payload(article),
        "revisions": [
            {"number": revision.number, "created_at": revision.created_at.isoformat()}
            for revision in article.revisions.all()[:20]
        ],
    }
    if include_workflow:
        payload["workflow_events"] = [
            {
                "id": event.id,
                "action": event.action,
                "from_status": event.from_status,
                "to_status": event.to_status,
                "revision": event.revision,
                "note": event.note,
                "metadata": event.metadata,
                "actor": (
                    {
                        "id": event.actor_id,
                        "display_name": display_name_for(event.actor),
                    }
                    if event.actor
                    else None
                ),
                "created_at": event.created_at.isoformat(),
            }
            for event in article.workflow_events.select_related("actor").all()[:50]
        ]
    if include_preview_token:
        payload["preview_token"] = str(article.preview_token) if article.preview_enabled else None
    return payload


def article_revision_payload(revision: ArticleRevision) -> dict:
    return {
        "number": revision.number,
        "title": revision.title,
        "subtitle": revision.subtitle,
        "document": normalize_document(revision.document),
        "subjects": normalize_subjects(revision.subjects),
        "created_at": revision.created_at.isoformat(),
    }


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


def visible_article(request: HttpRequest, article_id) -> Article:
    queryset = Article.objects.select_related("author")
    if not can_approve(request.user):
        queryset = queryset.filter(author=request.user)
    return get_object_or_404(
        queryset,
        id=article_id,
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
        publish_due_articles()
        queryset = Article.objects.select_related("author")
        if not can_approve(request.user):
            queryset = queryset.filter(author=request.user)
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
            subjects={"players": [], "teams": []},
            created_by=request.user,
        )
    except ValidationError as validation:
        return validation_error(validation)
    article = visible_article(request, article.id)
    return private_json({"article": article_payload(article)}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
@never_cache
def article_detail(request: HttpRequest, article_id) -> JsonResponse:
    error = editorial_error(request)
    if error is not None:
        return error

    if request.method == "GET":
        publish_due_articles()
        return private_json({"article": article_payload(visible_article(request, article_id))})
    if request.method == "DELETE":
        article = visible_article(request, article_id)
        if article.author_id != request.user.id:
            return private_json({"detail": "Only the writer can delete this article."}, status=403)
        if article.status != ArticleStatus.DRAFT:
            return private_json({"detail": "Only drafts can be deleted."}, status=409)
        article.delete()
        return private_json({"deleted": True})

    payload = json_body(request)
    create_revision = payload.get("create_revision") is True
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
        if article.status not in EDITABLE_STATUSES:
            return private_json(
                {"detail": "This article is locked while it is in the publishing workflow."},
                status=409,
            )
        if expected_revision != article.revision:
            article = visible_article(request, article.id)
            return private_json(
                {
                    "detail": "This draft changed in another tab. Reload before saving again.",
                    "code": "revision_conflict",
                    "article": article_payload(article),
                },
                status=409,
            )
        try:
            existing_subjects = subjects_payload(article)
            title = clean_text(payload.get("title", article.title), field="Title", maximum=180).strip()
            subtitle = clean_text(
                payload.get("subtitle", article.subtitle),
                field="Subtitle",
                maximum=280,
            ).strip()
            document = normalize_document(payload.get("document", article.document))
            subjects = normalize_subjects(payload.get("subjects", existing_subjects))
        except ValidationError as validation:
            return validation_error(validation)

        title = title or "Untitled analysis"
        content_changed = (title, subtitle, document) != (
            article.title,
            article.subtitle,
            article.document,
        )
        subjects_changed = subjects != existing_subjects
        changed = content_changed or subjects_changed
        if changed:
            try:
                sync_references(article, document)
                if subjects_changed:
                    save_subjects(article, subjects)
                article.title = title
                article.subtitle = subtitle
                article.document = document
                article.revision += 1
                article.save(update_fields=("title", "subtitle", "document", "revision", "updated_at"))
            except ValidationError as validation:
                return validation_error(validation)
        if create_revision and not ArticleRevision.objects.filter(
            article=article,
            number=article.revision,
        ).exists():
            ArticleRevision.objects.create(
                article=article,
                number=article.revision,
                title=article.title,
                subtitle=article.subtitle,
                document=article.document,
                subjects=subjects_payload(article),
                created_by=request.user,
            )
    article = visible_article(request, article.id)
    return private_json({"article": article_payload(article)})


@require_GET
@never_cache
def article_revision_detail(request: HttpRequest, article_id, revision_number: int) -> JsonResponse:
    error = editorial_error(request)
    if error is not None:
        return error
    article = visible_article(request, article_id)
    revision = get_object_or_404(
        ArticleRevision,
        article=article,
        number=revision_number,
    )
    return private_json({"revision": article_revision_payload(revision)})


@require_http_methods(["POST"])
@never_cache
def article_preview(request: HttpRequest, article_id) -> JsonResponse:
    error = editorial_error(request)
    if error is not None:
        return error
    article = visible_article(request, article_id)
    if article.author_id != request.user.id and not can_approve(request.user):
        return private_json({"detail": "You cannot manage this preview link."}, status=403)
    payload = json_body(request)
    enabled = payload.get("enabled")
    rotate = payload.get("rotate") is True
    if not isinstance(enabled, bool):
        return private_json({"detail": "Preview enabled must be true or false."}, status=400)
    was_enabled = article.preview_enabled
    article.preview_enabled = enabled
    if enabled:
        try:
            expires_in_hours = int(payload.get("expires_in_hours", 168))
        except (TypeError, ValueError):
            return private_json({"detail": "Preview expiry must be a number of hours."}, status=400)
        if expires_in_hours < 1 or expires_in_hours > 720:
            return private_json({"detail": "Preview links can last between 1 and 720 hours."}, status=400)
        article.preview_expires_at = timezone.now() + timedelta(hours=expires_in_hours)
    else:
        article.preview_expires_at = None
    if rotate or (enabled and not was_enabled):
        article.preview_token = uuid.uuid4()
    article.save(
        update_fields=("preview_enabled", "preview_token", "preview_expires_at", "updated_at")
    )
    article = visible_article(request, article.id)
    return private_json({"article": article_payload(article)})


@require_http_methods(["POST"])
@never_cache
def article_workflow(request: HttpRequest, article_id) -> JsonResponse:
    error = editorial_error(request)
    if error is not None:
        return error
    article = visible_article(request, article_id)
    payload = json_body(request)
    action = str(payload.get("action", "")).strip()
    try:
        note = clean_text(payload.get("note", ""), field="Workflow note", maximum=2000).strip()
    except ValidationError as validation:
        return validation_error(validation)
    publish_at = None
    if payload.get("publish_at"):
        publish_at = parse_datetime(str(payload["publish_at"]))
        if publish_at is None:
            return private_json({"detail": "Publication time must be a valid ISO date and time."}, status=400)
        if timezone.is_naive(publish_at):
            publish_at = timezone.make_aware(publish_at)
    try:
        article = transition_article(
            article.id,
            actor=request.user,
            action=action,
            note=note,
            publish_at=publish_at,
        )
    except WorkflowConflict as conflict:
        return private_json({"detail": str(conflict), "code": "workflow_conflict"}, status=409)
    article = visible_article(request, article.id)
    return private_json({"article": article_payload(article)})


@require_GET
@never_cache
def shared_preview(request: HttpRequest, token) -> JsonResponse:
    article = get_object_or_404(
        Article.objects.select_related("author"),
        preview_token=token,
        preview_enabled=True,
        preview_expires_at__gt=timezone.now(),
    )
    return public_preview_json(
        {
            "article": article_payload(
                article,
                include_preview_token=False,
                include_workflow=False,
            )
        }
    )


@require_GET
def public_article_detail(request: HttpRequest, article_id) -> JsonResponse:
    publish_due_articles()
    publication = get_object_or_404(
        ArticlePublication.objects.select_related("article", "article__author").filter(
            article_id=article_id,
            article__status=ArticleStatus.PUBLISHED,
            unpublished_at__isnull=True,
        ).order_by("-version")
    )
    response = JsonResponse(
        {
            "article": {
                "id": str(publication.article_id),
                "title": publication.title,
                "subtitle": publication.subtitle,
                "document": normalize_document(publication.document),
                "subjects": normalize_subjects(publication.subjects),
                "references": normalize_subjects(publication.references),
                "author": {
                    "id": publication.article.author_id,
                    "display_name": display_name_for(publication.article.author),
                    "social_links": social_links_for(publication.article.author),
                },
                "published_at": publication.published_at.isoformat(),
            }
        }
    )
    response["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    return response


@require_GET
def player_related_analysis(request: HttpRequest, entity_id: int) -> JsonResponse:
    player = get_object_or_404(CanonicalPlayer, id=entity_id)
    return related_analysis_payload(
        kind="player",
        entity_id=player.id,
        name=player.display_name,
    )


@require_GET
def team_related_analysis(request: HttpRequest, entity_id: int) -> JsonResponse:
    team = get_object_or_404(CanonicalTeam, id=entity_id)
    return related_analysis_payload(
        kind="team",
        entity_id=team.id,
        name=team.name,
    )


def related_analysis_payload(*, kind: str, entity_id: int, name: str) -> JsonResponse:
    publish_due_articles()
    subject_model = ArticlePlayerSubject if kind == "player" else ArticleTeamSubject
    reference_model = ArticlePlayerReference if kind == "player" else ArticleTeamReference
    entity_field = "player_id" if kind == "player" else "team_id"
    subject_links = subject_model.objects.filter(
        **{entity_field: entity_id},
        article__status="published",
    ).select_related("article", "article__author").order_by("-article__updated_at")
    subject_article_ids = subject_links.values_list("article_id", flat=True)
    reference_links = reference_model.objects.filter(
        **{entity_field: entity_id},
        article__status="published",
    ).exclude(article_id__in=subject_article_ids).select_related(
        "article", "article__author"
    ).order_by("-article__updated_at")
    response = JsonResponse(
        {
            "entity": {"kind": kind, "id": entity_id, "name": name},
            "subjects_of": [public_related_article(link.article) for link in subject_links[:50]],
            "referenced_by": [public_related_article(link.article) for link in reference_links[:50]],
        }
    )
    response["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    return response


def public_related_article(article: Article) -> dict:
    return {
        "id": str(article.id),
        "title": article.title,
        "subtitle": article.subtitle,
        "author": display_name_for(article.author),
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "updated_at": article.updated_at.isoformat(),
    }
