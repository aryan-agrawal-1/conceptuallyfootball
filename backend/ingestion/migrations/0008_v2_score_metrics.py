from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0007_playerseasonderivedstats_aerial_duels_won_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="accurate_crosses_per_90",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="accurate_crosses_per_90_percentile",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="accurate_long_balls_per_90",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="accurate_long_balls_per_90_percentile",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="aerial_duels_won_per_90",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="aerial_duels_won_per_90_percentile",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="ball_recoveries_per_90",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="ball_recoveries_per_90_percentile",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="errors_lead_to_goal_per_90",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="errors_lead_to_goal_per_90_percentile",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="fouls_per_90",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="fouls_per_90_percentile",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="ground_duels_won_per_90",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="ground_duels_won_per_90_percentile",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="inaccurate_pass_rate",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="inaccurate_pass_rate_percentile",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="kp_share_per90",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="kp_share_per90_percentile",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="offsides_per_90",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playerseasonderivedstats",
            name="offsides_per_90_percentile",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
