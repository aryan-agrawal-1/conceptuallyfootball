from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0004_reepplayerrow_position_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="assists_per_90",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="assists_per_90_percentile",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="goals_per_90",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="goals_per_90_percentile",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
