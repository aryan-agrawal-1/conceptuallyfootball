import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import editorial.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("editorial", "0002_article_relationships"),
    ]

    operations = [
        migrations.AlterField(
            model_name="article",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("submitted", "Submitted"),
                    ("changes_requested", "Changes requested"),
                    ("approved", "Approved"),
                    ("scheduled", "Scheduled"),
                    ("published", "Published"),
                    ("archived", "Archived"),
                ],
                default="draft",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="article",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="article",
            name="approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="editorial_articles_approved",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="article",
            name="preview_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="article",
            name="published_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="article",
            name="scheduled_for",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="article",
            name="submitted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="ArticleWorkflowEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("submitted", "Submitted for review"), ("changes_requested", "Changes requested"), ("approved", "Approved"), ("scheduled", "Scheduled"), ("published", "Published"), ("unpublished", "Unpublished"), ("archived", "Archived"), ("restored", "Restored")], max_length=32)),
                ("from_status", models.CharField(choices=[("draft", "Draft"), ("submitted", "Submitted"), ("changes_requested", "Changes requested"), ("approved", "Approved"), ("scheduled", "Scheduled"), ("published", "Published"), ("archived", "Archived")], max_length=20)),
                ("to_status", models.CharField(choices=[("draft", "Draft"), ("submitted", "Submitted"), ("changes_requested", "Changes requested"), ("approved", "Approved"), ("scheduled", "Scheduled"), ("published", "Published"), ("archived", "Archived")], max_length=20)),
                ("revision", models.PositiveIntegerField()),
                ("note", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="editorial_workflow_actions", to=settings.AUTH_USER_MODEL)),
                ("article", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="workflow_events", to="editorial.article")),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.CreateModel(
            name="ArticlePublication",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version", models.PositiveIntegerField()),
                ("revision", models.PositiveIntegerField()),
                ("title", models.CharField(max_length=180)),
                ("subtitle", models.CharField(blank=True, max_length=280)),
                ("document", models.JSONField()),
                ("subjects", models.JSONField(default=editorial.models.empty_subjects)),
                ("references", models.JSONField(default=editorial.models.empty_subjects)),
                ("published_at", models.DateTimeField()),
                ("unpublished_at", models.DateTimeField(blank=True, null=True)),
                ("article", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="publications", to="editorial.article")),
                ("published_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="editorial_publications_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-version",)},
        ),
        migrations.AddIndex(
            model_name="article",
            index=models.Index(fields=["status", "scheduled_for"], name="editorial_schedule_idx"),
        ),
        migrations.AddIndex(
            model_name="articleworkflowevent",
            index=models.Index(fields=["article", "-created_at"], name="editorial_workflow_article_idx"),
        ),
        migrations.AddConstraint(
            model_name="articlepublication",
            constraint=models.UniqueConstraint(fields=("article", "version"), name="unique_editorial_publication_version"),
        ),
    ]
