from django.contrib import admin

from editorial.models import Article, ArticlePublication, ArticleWorkflowEvent


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "status", "scheduled_for", "published_at", "updated_at")
    list_filter = ("status", "created_at", "published_at")
    search_fields = ("title", "subtitle", "author__email")
    readonly_fields = (
        "id",
        "revision",
        "preview_token",
        "submitted_at",
        "approved_at",
        "approved_by",
        "published_at",
        "created_at",
        "updated_at",
    )


@admin.register(ArticleWorkflowEvent)
class ArticleWorkflowEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "article", "action", "from_status", "to_status", "actor")
    list_filter = ("action", "from_status", "to_status", "created_at")
    search_fields = ("article__title", "article__author__email", "actor__email", "note")
    readonly_fields = (
        "article",
        "actor",
        "action",
        "from_status",
        "to_status",
        "revision",
        "note",
        "metadata",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(ArticlePublication)
class ArticlePublicationAdmin(admin.ModelAdmin):
    list_display = ("article", "version", "revision", "published_at", "unpublished_at", "published_by")
    list_filter = ("published_at", "unpublished_at")
    search_fields = ("article__title", "article__author__email", "published_by__email")
    readonly_fields = (
        "article",
        "version",
        "revision",
        "title",
        "subtitle",
        "document",
        "subjects",
        "references",
        "published_by",
        "published_at",
        "unpublished_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
