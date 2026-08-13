from __future__ import annotations

import json
import math
import re
import uuid
from datetime import timedelta
from xml.sax.saxutils import escape

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
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


PUBLIC_SITE_URL = "https://www.conceptuallyfootball.com"
TOPIC_LIMIT = 8
TOPIC_LENGTH = 40
WORD_PATTERN = re.compile(r"\b[\w’'-]+\b", re.UNICODE)


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


def normalize_topics(value) -> list[str]:
    if not isinstance(value, list):
        raise ValidationError("Topics must be a list.")
    topics = []
    seen = set()
    for raw_topic in value:
        topic = clean_text(raw_topic, field="Topic", maximum=TOPIC_LENGTH).strip()
        key = topic.casefold()
        if not topic or key in seen:
            continue
        seen.add(key)
        topics.append(topic)
    if len(topics) > TOPIC_LIMIT:
        raise ValidationError(f"Articles can have at most {TOPIC_LIMIT} topics.")
    return topics


def article_summary(article: Article) -> dict:
    return {
        "id": str(article.id),
        "title": article.title,
        "subtitle": article.subtitle,
        "slug": article.slug,
        "topics": normalize_topics(article.topics),
        "source_notes": article.source_notes,
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
        "topics": normalize_topics(revision.topics),
        "source_notes": revision.source_notes,
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
            topics=[],
            source_notes="",
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
            topics = normalize_topics(payload.get("topics", article.topics))
            source_notes = clean_text(
                payload.get("source_notes", article.source_notes),
                field="Source notes",
                maximum=2000,
            ).strip()
        except ValidationError as validation:
            return validation_error(validation)

        title = title or "Untitled analysis"
        content_changed = (title, subtitle, document, topics, source_notes) != (
            article.title,
            article.subtitle,
            article.document,
            article.topics,
            article.source_notes,
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
                article.topics = topics
                article.source_notes = source_notes
                article.revision += 1
                article.save(update_fields=(
                    "title",
                    "subtitle",
                    "document",
                    "topics",
                    "source_notes",
                    "revision",
                    "updated_at",
                ))
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
                topics=article.topics,
                source_notes=article.source_notes,
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


def active_publications():
    return ArticlePublication.objects.select_related("article", "article__author").filter(
        article__status=ArticleStatus.PUBLISHED,
        article__slug__isnull=False,
        unpublished_at__isnull=True,
    ).order_by("-published_at", "-id")


def public_response(payload: dict) -> JsonResponse:
    response = JsonResponse(payload)
    response["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    return response


def reading_minutes(document: dict) -> int:
    words = 0
    for block in normalize_document(document)["blocks"]:
        if block["type"] in {"paragraph", "heading", "quote", "callout"}:
            words += sum(len(WORD_PATTERN.findall(run.get("text", ""))) for run in block["content"])
        elif block["type"] in {"bulleted_list", "numbered_list"}:
            words += sum(
                len(WORD_PATTERN.findall(run.get("text", "")))
                for item in block["items"]
                for run in item
            )
        elif block["type"] in {"image", "visual"}:
            words += len(WORD_PATTERN.findall(block.get("caption", "")))
    return max(1, math.ceil(words / 220))


def document_search_text(document: dict) -> str:
    values = []
    for block in normalize_document(document)["blocks"]:
        if block["type"] in {"paragraph", "heading", "quote", "callout"}:
            values.extend(run.get("text", "") for run in block["content"])
        elif block["type"] in {"bulleted_list", "numbered_list"}:
            values.extend(run.get("text", "") for item in block["items"] for run in item)
        elif block["type"] in {"image", "visual"}:
            values.extend((block.get("title", ""), block.get("caption", ""), block.get("source_note", "")))
    return " ".join(values)


def publication_context(publication: ArticlePublication) -> dict:
    competitions = set()
    seasons = set()
    relationships = (normalize_subjects(publication.subjects), normalize_subjects(publication.references))
    for relationship in relationships:
        for entity in [*relationship["players"], *relationship["teams"]]:
            context = entity.get("context") or {}
            if context.get("competition_code"):
                competitions.add(context["competition_code"])
            if context.get("season_label"):
                seasons.add(context["season_label"])
    for block in normalize_document(publication.document)["blocks"]:
        if block["type"] != "visual":
            continue
        context = block.get("config", {}).get("context", {})
        if context.get("scope_code"):
            competitions.add(context["scope_code"])
        if context.get("season_label"):
            seasons.add(context["season_label"])
    return {"competitions": sorted(competitions), "seasons": sorted(seasons, reverse=True)}


def publication_summary(publication: ArticlePublication) -> dict:
    article = publication.article
    return {
        "id": str(publication.article_id),
        "slug": article.slug,
        "canonical_path": f"/articles/{article.slug}",
        "title": publication.title,
        "subtitle": publication.subtitle,
        "topics": normalize_topics(publication.topics),
        "author": {
            "id": article.author_id,
            "display_name": display_name_for(article.author),
        },
        "published_at": publication.published_at.isoformat(),
        "reading_minutes": reading_minutes(publication.document),
        "context": publication_context(publication),
    }


def publication_matches_entity(
    publication: ArticlePublication,
    *,
    kind: str,
    entity_id: int,
    relationship: str,
) -> bool:
    key = "players" if kind == "player" else "teams"
    subject_ids = {entity["id"] for entity in normalize_subjects(publication.subjects)[key]}
    reference_ids = {entity["id"] for entity in normalize_subjects(publication.references)[key]}
    if relationship == "subject":
        return entity_id in subject_ids
    if relationship == "reference":
        return entity_id in reference_ids and entity_id not in subject_ids
    return entity_id in subject_ids or entity_id in reference_ids


def public_facets(publications: list[ArticlePublication]) -> dict:
    authors = {}
    topics = set()
    competitions = set()
    seasons = set()
    players = {}
    teams = {}
    for publication in publications:
        author = publication.article.author
        authors[author.id] = display_name_for(author)
        topics.update(normalize_topics(publication.topics))
        context = publication_context(publication)
        competitions.update(context["competitions"])
        seasons.update(context["seasons"])
        for relationship in (publication.subjects, publication.references):
            normalized = normalize_subjects(relationship)
            players.update({entity["id"]: entity["name"] for entity in normalized["players"]})
            teams.update({entity["id"]: entity["name"] for entity in normalized["teams"]})
    return {
        "authors": [{"id": key, "name": value} for key, value in sorted(authors.items(), key=lambda item: item[1])],
        "topics": sorted(topics),
        "competitions": sorted(competitions),
        "seasons": sorted(seasons, reverse=True),
        "players": [{"id": key, "name": value} for key, value in sorted(players.items(), key=lambda item: item[1])],
        "teams": [{"id": key, "name": value} for key, value in sorted(teams.items(), key=lambda item: item[1])],
    }


@require_GET
def public_articles(request: HttpRequest) -> JsonResponse:
    publish_due_articles()
    publications = list(active_publications()[:500])
    facets = public_facets(publications)
    query = request.GET.get("q", "").strip().casefold()
    topic = request.GET.get("topic", "").strip().casefold()
    competition = request.GET.get("competition", "").strip().casefold()
    season = request.GET.get("season", "").strip().casefold()
    relationship = request.GET.get("relationship", "").strip()
    kind = request.GET.get("entity_kind", "").strip()
    author_id = request.GET.get("author", "").strip()
    published_from = parse_date(request.GET.get("from", ""))
    published_to = parse_date(request.GET.get("to", ""))
    try:
        entity_id = int(request.GET.get("entity_id", ""))
    except (TypeError, ValueError):
        entity_id = None

    filtered = []
    for publication in publications:
        summary = publication_summary(publication)
        searchable = " ".join(
            [
                summary["title"],
                summary["subtitle"],
                summary["author"]["display_name"],
                publication.source_notes,
                document_search_text(publication.document),
                *summary["topics"],
            ]
        ).casefold()
        if query and query not in searchable:
            continue
        if topic and topic not in {value.casefold() for value in summary["topics"]}:
            continue
        if competition and competition not in {value.casefold() for value in summary["context"]["competitions"]}:
            continue
        if season and season not in {value.casefold() for value in summary["context"]["seasons"]}:
            continue
        if author_id and author_id != str(summary["author"]["id"]):
            continue
        if published_from and publication.published_at.date() < published_from:
            continue
        if published_to and publication.published_at.date() > published_to:
            continue
        if entity_id and kind in {"player", "team"} and not publication_matches_entity(
            publication,
            kind=kind,
            entity_id=entity_id,
            relationship=relationship,
        ):
            continue
        filtered.append(summary)

    try:
        page = max(1, int(request.GET.get("page", "1")))
        page_size = min(48, max(1, int(request.GET.get("page_size", "18"))))
    except ValueError:
        page, page_size = 1, 18
    start = (page - 1) * page_size
    total = len(filtered)
    return public_response(
        {
            "articles": filtered[start:start + page_size],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": math.ceil(total / page_size) if total else 0,
            },
            "facets": facets,
        }
    )


def public_article_payload(publication: ArticlePublication) -> dict:
    summary = publication_summary(publication)
    document = normalize_document(publication.document)
    first_image = next(
        (
            block.get("url")
            for block in document["blocks"]
            if block["type"] == "image" and block.get("url", "").startswith(("https://", "http://"))
        ),
        None,
    )
    return {
        **summary,
        "document": document,
        "subjects": normalize_subjects(publication.subjects),
        "references": normalize_subjects(publication.references),
        "source_notes": publication.source_notes,
        "social_image": first_image,
        "author": {
            **summary["author"],
            "social_links": social_links_for(publication.article.author),
        },
    }


def public_article_response(publication: ArticlePublication) -> JsonResponse:
    return public_response({"article": public_article_payload(publication)})


@require_GET
def public_article_detail(request: HttpRequest, slug: str) -> JsonResponse:
    publish_due_articles()
    return public_article_response(get_object_or_404(active_publications(), article__slug=slug))


@require_GET
def public_article_detail_by_id(request: HttpRequest, article_id) -> JsonResponse:
    publish_due_articles()
    return public_article_response(get_object_or_404(active_publications(), article_id=article_id))


@require_GET
def public_sitemap(request: HttpRequest) -> HttpResponse:
    publish_due_articles()
    static_paths = ("/", "/articles", "/galaxy", "/create-charts", "/comparisons", "/regression-lab")
    urls = [
        f"  <url><loc>{escape(PUBLIC_SITE_URL + path)}</loc></url>"
        for path in static_paths
    ]
    urls.extend(
        "  <url>"
        f"<loc>{escape(PUBLIC_SITE_URL + '/articles/' + publication.article.slug)}</loc>"
        f"<lastmod>{publication.published_at.date().isoformat()}</lastmod>"
        "</url>"
        for publication in active_publications()
    )
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n"
    response = HttpResponse(xml, content_type="application/xml; charset=utf-8")
    response["Cache-Control"] = "public, max-age=300, stale-while-revalidate=3600"
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
        article__status=ArticleStatus.PUBLISHED,
        article__publications__isnull=False,
        article__publications__unpublished_at__isnull=True,
    ).select_related("article", "article__author").distinct().order_by("-article__published_at")
    subject_article_ids = subject_links.values_list("article_id", flat=True)
    reference_links = reference_model.objects.filter(
        **{entity_field: entity_id},
        article__status=ArticleStatus.PUBLISHED,
        article__publications__isnull=False,
        article__publications__unpublished_at__isnull=True,
    ).exclude(article_id__in=subject_article_ids).select_related(
        "article", "article__author"
    ).distinct().order_by("-article__published_at")
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
    publication = article.publications.filter(unpublished_at__isnull=True).order_by("-version").first()
    if publication is None:
        return {}
    summary = publication_summary(publication)
    return {**summary, "author": summary["author"]["display_name"]}
