from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0036_player_season_role"),
    ]

    operations = [
        migrations.DeleteModel(name="PlayerSeasonRole"),
        migrations.CreateModel(
            name="PlayerSeasonRoleFeatureSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("feature_version", models.CharField(db_index=True, max_length=64)),
                ("features", models.JSONField(blank=True, default=dict)),
                ("verified_exposure_seconds", models.PositiveIntegerField(default=0)),
                ("source_event_version", models.CharField(max_length=64)),
                ("source_state_version", models.CharField(max_length=64)),
                ("source_participation_version", models.CharField(max_length=64)),
                ("source_possession_version", models.CharField(max_length=64)),
                ("calculated_through_date", models.DateField(blank=True, null=True)),
                ("is_current", models.BooleanField(db_index=True, default=True)),
                ("superseded_at", models.DateTimeField(blank=True, null=True)),
                ("calculated_at", models.DateTimeField(auto_now_add=True)),
                ("calculated_through_match", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="player_role_features_calculated_through", to="ingestion.providermatch")),
                ("competition_season", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="player_role_feature_snapshots", to="ingestion.competitionseason")),
                ("player", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="role_feature_snapshots", to="ingestion.canonicalplayer")),
                ("team", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="player_role_feature_snapshots", to="ingestion.canonicalteam")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["competition_season", "team", "player", "is_current"], name="player_role_feature_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(condition=models.Q(("is_current", True)), fields=("competition_season", "player", "team"), name="uniq_current_role_feature"),
                ],
            },
        ),
        migrations.CreateModel(
            name="PlayerSeasonRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("primary_archetype", models.CharField(blank=True, max_length=64, null=True)),
                ("primary_fit", models.FloatField(blank=True, null=True)),
                ("secondary_archetype", models.CharField(blank=True, max_length=64, null=True)),
                ("secondary_fit", models.FloatField(blank=True, null=True)),
                ("classification_shape", models.CharField(max_length=24)),
                ("evidence_confidence", models.CharField(max_length=24)),
                ("traits", models.JSONField(blank=True, default=list)),
                ("candidates", models.JSONField(blank=True, default=list)),
                ("evidence", models.JSONField(blank=True, default=dict)),
                ("scoring_version", models.CharField(db_index=True, max_length=64)),
                ("is_current", models.BooleanField(db_index=True, default=True)),
                ("superseded_at", models.DateTimeField(blank=True, null=True)),
                ("calculated_at", models.DateTimeField(auto_now_add=True)),
                ("competition_season", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="player_season_roles", to="ingestion.competitionseason")),
                ("feature_snapshot", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="classifications", to="ingestion.playerseasonrolefeaturesnapshot")),
                ("player", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="season_roles", to="ingestion.canonicalplayer")),
                ("team", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="player_season_roles", to="ingestion.canonicalteam")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["competition_season", "team", "player", "is_current"], name="player_team_role_idx"),
                    models.Index(fields=["competition_season", "primary_archetype", "is_current"], name="primary_archetype_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(condition=models.Q(("is_current", True)), fields=("competition_season", "player", "team"), name="uniq_current_player_team_role"),
                ],
            },
        ),
    ]
