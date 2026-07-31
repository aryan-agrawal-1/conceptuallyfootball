from django.db import migrations, models
from django.db.models import Q


def publish_existing_materialized_slices(apps, schema_editor):
    CompetitionSeason = apps.get_model("ingestion", "CompetitionSeason")
    CompetitionSeason.objects.filter(
        Q(
            derived_rows__is_current=True,
            derived_rows__derived_ingestion_run__status="success",
        )
        | Q(
            gk_derived_rows__is_current=True,
            gk_derived_rows__derived_ingestion_run__status="success",
        )
    ).distinct().update(is_published=True)


def hide_all_slices(apps, schema_editor):
    CompetitionSeason = apps.get_model("ingestion", "CompetitionSeason")
    CompetitionSeason.objects.update(is_published=False)


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0026_competitionseason_has_whoscored_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="competition",
            name="competition_type",
            field=models.CharField(
                choices=[
                    ("domestic_league", "Domestic league"),
                    ("continental_cup", "Continental cup"),
                ],
                db_index=True,
                default="domestic_league",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="competition",
            name="include_in_domestic_aggregates",
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.AddField(
            model_name="competition",
            name="minimum_eligible_minutes",
            field=models.PositiveSmallIntegerField(default=450),
        ),
        migrations.AddField(
            model_name="competitionseason",
            name="is_published",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.RunPython(publish_existing_materialized_slices, hide_all_slices),
    ]
