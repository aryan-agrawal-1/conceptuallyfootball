from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0035_possession_context"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlayerSeasonRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("team_context", models.JSONField(blank=True, default=list)),
                ("team_context_quality", models.CharField(max_length=32)),
                ("primary_role", models.CharField(blank=True, max_length=48, null=True)),
                ("primary_score", models.FloatField(blank=True, null=True)),
                ("runner_up_role", models.CharField(blank=True, max_length=48, null=True)),
                ("runner_up_score", models.FloatField(blank=True, null=True)),
                ("score_margin", models.FloatField(blank=True, null=True)),
                ("confidence", models.CharField(max_length=24)),
                ("state_coverage", models.JSONField(blank=True, default=dict)),
                ("verified_exposure_seconds", models.PositiveIntegerField(default=0)),
                ("evidence", models.JSONField(blank=True, default=dict)),
                ("calculation_version", models.CharField(db_index=True, max_length=64)),
                ("source_event_version", models.CharField(max_length=64)),
                ("source_state_version", models.CharField(max_length=64)),
                ("source_participation_version", models.CharField(max_length=64)),
                ("calculated_through_date", models.DateField(blank=True, null=True)),
                ("is_current", models.BooleanField(db_index=True, default=True)),
                ("superseded_at", models.DateTimeField(blank=True, null=True)),
                ("calculated_at", models.DateTimeField(auto_now_add=True)),
                ("calculated_through_match", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="player_roles_calculated_through", to="ingestion.providermatch")),
                ("competition_season", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="player_season_roles", to="ingestion.competitionseason")),
                ("player", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="season_roles", to="ingestion.canonicalplayer")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["competition_season", "player", "is_current"], name="player_season_role_idx"),
                    models.Index(fields=["competition_season", "primary_role", "is_current"], name="season_primary_role_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(condition=models.Q(("is_current", True)), fields=("competition_season", "player"), name="uniq_current_player_season_role"),
                ],
            },
        ),
    ]
