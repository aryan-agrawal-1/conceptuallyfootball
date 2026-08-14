from django.db import migrations, models
from django.utils.text import slugify


def populate_published_slugs(apps, schema_editor):
    article_model = apps.get_model("editorial", "Article")
    for article in article_model.objects.filter(status="published", slug__isnull=True).iterator():
        title_slug = slugify(article.title)[:180] or "analysis"
        article.slug = f"{title_slug}-{article.id}"
        article.save(update_fields=("slug",))


class Migration(migrations.Migration):

    dependencies = [
        ("editorial", "0004_remove_legacy_subject_context"),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="slug",
            field=models.SlugField(blank=True, max_length=220, null=True, unique=True),
        ),
        migrations.RunPython(populate_published_slugs, reverse_code=migrations.RunPython.noop),
        migrations.AddField(
            model_name="article",
            name="topics",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="article",
            name="source_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="articlerevision",
            name="topics",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="articlerevision",
            name="source_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="articlepublication",
            name="topics",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="articlepublication",
            name="source_notes",
            field=models.TextField(blank=True),
        ),
    ]
