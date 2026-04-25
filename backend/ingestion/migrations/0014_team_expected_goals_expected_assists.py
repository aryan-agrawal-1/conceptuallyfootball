from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0013_competitionseason_expected_team_count_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="sofascoreteamseasonsource",
            name="expected_goals",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="sofascoreteamseasonsource",
            name="expected_assists",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="mergedteamseason",
            name="expected_goals",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="mergedteamseason",
            name="expected_assists",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
