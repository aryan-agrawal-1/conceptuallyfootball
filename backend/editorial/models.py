from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


def empty_document() -> dict:
    return {
        "version": 1,
        "blocks": [
            {
                "id": str(uuid.uuid4()),
                "type": "paragraph",
                "content": [{"text": ""}],
            }
        ],
    }


def empty_subjects() -> dict:
    return {"players": [], "teams": []}


class ArticleStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    CHANGES_REQUESTED = "changes_requested", "Changes requested"
    APPROVED = "approved", "Approved"
    SCHEDULED = "scheduled", "Scheduled"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class ArticleWorkflowAction(models.TextChoices):
    SUBMITTED = "submitted", "Submitted for review"
    CHANGES_REQUESTED = "changes_requested", "Changes requested"
    APPROVED = "approved", "Approved"
    SCHEDULED = "scheduled", "Scheduled"
    PUBLISHED = "published", "Published"
    UNPUBLISHED = "unpublished", "Unpublished"
    ARCHIVED = "archived", "Archived"
    RESTORED = "restored", "Restored"


class Article(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="editorial_articles",
    )
    title = models.CharField(max_length=180, default="Untitled analysis")
    subtitle = models.CharField(max_length=280, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ArticleStatus.choices,
        default=ArticleStatus.DRAFT,
    )
    document = models.JSONField(default=empty_document)
    revision = models.PositiveIntegerField(default=1)
    preview_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    preview_enabled = models.BooleanField(default=False)
    preview_expires_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="editorial_articles_approved",
    )
    scheduled_for = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-created_at")
        indexes = (
            models.Index(fields=("author", "status", "-updated_at"), name="editorial_author_status_idx"),
            models.Index(fields=("status", "scheduled_for"), name="editorial_schedule_idx"),
        )

    def __str__(self) -> str:
        return self.title


class ArticlePlayerSubject(models.Model):
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="player_subject_links",
    )
    player = models.ForeignKey(
        "ingestion.CanonicalPlayer",
        on_delete=models.PROTECT,
        related_name="article_subject_links",
    )
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ("position", "id")
        constraints = (
            models.UniqueConstraint(
                fields=("article", "player"),
                name="unique_article_player_subject",
            ),
            models.UniqueConstraint(
                fields=("article", "position"),
                name="unique_article_player_subject_position",
            ),
        )
        indexes = (
            models.Index(fields=("player", "article"), name="editorial_player_subject_idx"),
        )


class ArticleTeamSubject(models.Model):
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="team_subject_links",
    )
    team = models.ForeignKey(
        "ingestion.CanonicalTeam",
        on_delete=models.PROTECT,
        related_name="article_subject_links",
    )
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ("position", "id")
        constraints = (
            models.UniqueConstraint(
                fields=("article", "team"),
                name="unique_article_team_subject",
            ),
            models.UniqueConstraint(
                fields=("article", "position"),
                name="unique_article_team_subject_position",
            ),
        )
        indexes = (
            models.Index(fields=("team", "article"), name="editorial_team_subject_idx"),
        )


class ArticlePlayerReference(models.Model):
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="player_reference_links",
    )
    player = models.ForeignKey(
        "ingestion.CanonicalPlayer",
        on_delete=models.PROTECT,
        related_name="article_reference_links",
    )

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=("article", "player"),
                name="unique_article_player_reference",
            ),
        )
        indexes = (
            models.Index(fields=("player", "article"), name="editorial_player_reference_idx"),
        )


class ArticleTeamReference(models.Model):
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="team_reference_links",
    )
    team = models.ForeignKey(
        "ingestion.CanonicalTeam",
        on_delete=models.PROTECT,
        related_name="article_reference_links",
    )

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=("article", "team"),
                name="unique_article_team_reference",
            ),
        )
        indexes = (
            models.Index(fields=("team", "article"), name="editorial_team_reference_idx"),
        )


class ArticleRevision(models.Model):
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="revisions",
    )
    number = models.PositiveIntegerField()
    title = models.CharField(max_length=180)
    subtitle = models.CharField(max_length=280, blank=True)
    document = models.JSONField()
    subjects = models.JSONField(default=empty_subjects)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="editorial_revisions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-number",)
        constraints = (
            models.UniqueConstraint(
                fields=("article", "number"),
                name="unique_editorial_article_revision",
            ),
        )

    def __str__(self) -> str:
        return f"{self.article_id} revision {self.number}"


class ArticleWorkflowEvent(models.Model):
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="workflow_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="editorial_workflow_actions",
    )
    action = models.CharField(max_length=32, choices=ArticleWorkflowAction.choices)
    from_status = models.CharField(max_length=20, choices=ArticleStatus.choices)
    to_status = models.CharField(max_length=20, choices=ArticleStatus.choices)
    revision = models.PositiveIntegerField()
    note = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = (
            models.Index(fields=("article", "-created_at"), name="editorial_workflow_article_idx"),
        )


class ArticlePublication(models.Model):
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="publications",
    )
    version = models.PositiveIntegerField()
    revision = models.PositiveIntegerField()
    title = models.CharField(max_length=180)
    subtitle = models.CharField(max_length=280, blank=True)
    document = models.JSONField()
    subjects = models.JSONField(default=empty_subjects)
    references = models.JSONField(default=empty_subjects)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="editorial_publications_created",
    )
    published_at = models.DateTimeField()
    unpublished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-version",)
        constraints = (
            models.UniqueConstraint(
                fields=("article", "version"),
                name="unique_editorial_publication_version",
            ),
        )

    def __str__(self) -> str:
        return f"{self.article_id} publication {self.version}"
