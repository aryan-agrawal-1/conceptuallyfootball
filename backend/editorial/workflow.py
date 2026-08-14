from __future__ import annotations

from datetime import datetime

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.text import slugify

from editorial.models import (
    Article,
    ArticlePublication,
    ArticleRevision,
    ArticleStatus,
    ArticleWorkflowAction,
    ArticleWorkflowEvent,
)
from editorial.relationships import references_payload, subjects_payload


EDITABLE_STATUSES = {ArticleStatus.DRAFT, ArticleStatus.CHANGES_REQUESTED}
REVIEW_STATUSES = {ArticleStatus.SUBMITTED, ArticleStatus.APPROVED, ArticleStatus.SCHEDULED}


class WorkflowConflict(Exception):
    pass


def can_approve(user) -> bool:
    return user.is_superuser or user.has_perm("accounts.approve_editorial_content")


def create_revision_checkpoint(article: Article, actor) -> None:
    ArticleRevision.objects.get_or_create(
        article=article,
        number=article.revision,
        defaults={
            "title": article.title,
            "subtitle": article.subtitle,
            "document": article.document,
            "subjects": subjects_payload(article),
            "topics": article.topics,
            "source_notes": article.source_notes,
            "created_by": actor,
        },
    )


def record_transition(
    article: Article,
    *,
    actor,
    action: str,
    from_status: str,
    note: str = "",
    metadata: dict | None = None,
) -> ArticleWorkflowEvent:
    return ArticleWorkflowEvent.objects.create(
        article=article,
        actor=actor,
        action=action,
        from_status=from_status,
        to_status=article.status,
        revision=article.revision,
        note=note,
        metadata=metadata or {},
    )


def create_publication(article: Article, actor, published_at: datetime) -> ArticlePublication:
    if not article.slug:
        title_slug = slugify(article.title)[:180] or "analysis"
        article.slug = f"{title_slug}-{article.id}"
        article.save(update_fields=("slug", "updated_at"))
    latest_version = article.publications.aggregate(latest=Max("version"))["latest"] or 0
    return ArticlePublication.objects.create(
        article=article,
        version=latest_version + 1,
        revision=article.revision,
        title=article.title,
        subtitle=article.subtitle,
        document=article.document,
        subjects=subjects_payload(article),
        references=references_payload(article),
        topics=article.topics,
        source_notes=article.source_notes,
        published_by=actor,
        published_at=published_at,
    )


def close_active_publication(article: Article, unpublished_at: datetime) -> None:
    article.publications.filter(unpublished_at__isnull=True).update(unpublished_at=unpublished_at)


@transaction.atomic
def transition_article(
    article_id,
    *,
    actor,
    action: str,
    note: str = "",
    publish_at: datetime | None = None,
) -> Article:
    article = Article.objects.select_for_update().select_related("author").get(id=article_id)
    from_status = article.status
    now = timezone.now()

    if action == "submit":
        if actor != article.author or article.status not in EDITABLE_STATUSES:
            raise WorkflowConflict("Only the writer can submit an editable article.")
        create_revision_checkpoint(article, actor)
        article.status = ArticleStatus.SUBMITTED
        article.submitted_at = now
        article.scheduled_for = None
        workflow_action = ArticleWorkflowAction.SUBMITTED
    elif action == "request_changes":
        if not can_approve(actor) or article.status not in REVIEW_STATUSES:
            raise WorkflowConflict("Changes can only be requested during review.")
        if not note:
            raise WorkflowConflict("Explain what the writer needs to change.")
        article.status = ArticleStatus.CHANGES_REQUESTED
        article.approved_at = None
        article.approved_by = None
        article.scheduled_for = None
        workflow_action = ArticleWorkflowAction.CHANGES_REQUESTED
    elif action == "approve":
        if not can_approve(actor) or article.status != ArticleStatus.SUBMITTED:
            raise WorkflowConflict("Only submitted articles can be approved.")
        article.status = ArticleStatus.APPROVED
        article.approved_at = now
        article.approved_by = actor
        article.scheduled_for = None
        workflow_action = ArticleWorkflowAction.APPROVED
    elif action == "publish":
        if not can_approve(actor) or article.status not in {
            ArticleStatus.SUBMITTED,
            ArticleStatus.APPROVED,
        }:
            raise WorkflowConflict("Only submitted or approved articles can be published.")
        create_revision_checkpoint(article, actor)
        article.approved_at = article.approved_at or now
        article.approved_by = article.approved_by or actor
        if publish_at and publish_at > now:
            article.status = ArticleStatus.SCHEDULED
            article.scheduled_for = publish_at
            workflow_action = ArticleWorkflowAction.SCHEDULED
        else:
            article.status = ArticleStatus.PUBLISHED
            article.scheduled_for = None
            article.published_at = now
            publication = create_publication(article, actor, now)
            workflow_action = ArticleWorkflowAction.PUBLISHED
    elif action == "unpublish":
        if not can_approve(actor) or article.status not in {
            ArticleStatus.PUBLISHED,
            ArticleStatus.SCHEDULED,
        }:
            raise WorkflowConflict("Only published or scheduled articles can be unpublished.")
        close_active_publication(article, now)
        article.status = ArticleStatus.APPROVED
        article.scheduled_for = None
        workflow_action = ArticleWorkflowAction.UNPUBLISHED
    elif action == "archive":
        if not can_approve(actor) or article.status == ArticleStatus.ARCHIVED:
            raise WorkflowConflict("Only an active article can be archived.")
        close_active_publication(article, now)
        article.status = ArticleStatus.ARCHIVED
        article.scheduled_for = None
        workflow_action = ArticleWorkflowAction.ARCHIVED
    elif action == "restore":
        if not can_approve(actor) or article.status != ArticleStatus.ARCHIVED:
            raise WorkflowConflict("Only archived articles can be restored.")
        article.status = ArticleStatus.DRAFT
        article.approved_at = None
        article.approved_by = None
        workflow_action = ArticleWorkflowAction.RESTORED
    else:
        raise WorkflowConflict("This workflow action is not supported.")

    article.save()
    metadata = {}
    if article.scheduled_for:
        metadata["scheduled_for"] = article.scheduled_for.isoformat()
    if action == "publish" and article.status == ArticleStatus.PUBLISHED:
        metadata["publication_version"] = publication.version
    record_transition(
        article,
        actor=actor,
        action=workflow_action,
        from_status=from_status,
        note=note,
        metadata=metadata,
    )
    return article


def publish_due_articles() -> int:
    due_ids = list(
        Article.objects.filter(
            status=ArticleStatus.SCHEDULED,
            scheduled_for__lte=timezone.now(),
        ).values_list("id", flat=True)
    )
    published_count = 0
    for article_id in due_ids:
        with transaction.atomic():
            article = Article.objects.select_for_update().filter(
                id=article_id,
                status=ArticleStatus.SCHEDULED,
                scheduled_for__lte=timezone.now(),
            ).first()
            if article is None:
                continue
            published_at = article.scheduled_for or timezone.now()
            from_status = article.status
            publication = create_publication(article, article.approved_by, published_at)
            article.status = ArticleStatus.PUBLISHED
            article.published_at = published_at
            article.scheduled_for = None
            article.save(update_fields=("status", "published_at", "scheduled_for", "updated_at"))
            record_transition(
                article,
                actor=None,
                action=ArticleWorkflowAction.PUBLISHED,
                from_status=from_status,
                metadata={
                    "automatic": True,
                    "publication_version": publication.version,
                },
            )
            published_count += 1
    return published_count
