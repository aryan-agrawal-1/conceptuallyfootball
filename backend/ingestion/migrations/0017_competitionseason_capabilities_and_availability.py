from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0016_understat_provider_team_ids"),
    ]

    operations = [
        migrations.AddField(
            model_name="competitionseason",
            name="has_sofascore",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="competitionseason",
            name="has_understat",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="competitionseason",
            name="metric_availability",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="competitionseason",
            name="player_data_mode",
            field=models.CharField(
                choices=[("full_merge", "Full merge"), ("sofascore_only", "Sofascore only")],
                default="full_merge",
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name="competitionseason",
            name="sofascore_season_id",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="competitionseason",
            name="sofascore_unique_tournament_id",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="competitionseason",
            name="understat_league",
            field=models.CharField(blank=True, default="EPL", max_length=32, null=True),
        ),
        migrations.AlterField(
            model_name="competitionseason",
            name="understat_season_year",
            field=models.CharField(
                blank=True,
                help_text="Understat URL segment, e.g. 2025 for 2025-26 depending on Understat convention.",
                max_length=8,
                null=True,
            ),
        ),
    ]
