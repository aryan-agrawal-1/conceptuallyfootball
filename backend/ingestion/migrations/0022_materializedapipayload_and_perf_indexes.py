from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0021_galaxyarchetype_galaxyplayerembedding_galaxysnapshot_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="MaterializedApiPayload",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cache_key", models.CharField(db_index=True, max_length=255, unique=True)),
                ("source_version", models.CharField(db_index=True, max_length=128)),
                ("payload", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["cache_key", "source_version"], name="ingestion_m_cache_k_9f2600_idx"),
                    models.Index(fields=["updated_at"], name="ingestion_m_updated_9420a7_idx"),
                ],
            },
        ),
        migrations.AddIndex(
            model_name="playerseasonderivedstats",
            index=models.Index(
                condition=models.Q(("is_current", True)),
                fields=["competition_season", "position_group", "minutes"],
                name="der_cur_pos_min_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="playerseasonderivedstats",
            index=models.Index(
                condition=models.Q(("is_current", True)),
                fields=["competition_season", "canonical_display_team"],
                name="derived_current_team_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="playerseasonderivedstats",
            index=models.Index(
                condition=models.Q(("is_current", True)),
                fields=["competition_season", "canonical_player"],
                name="derived_current_player_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="playerseasongkderivedstats",
            index=models.Index(
                condition=models.Q(("is_current", True)),
                fields=["competition_season", "canonical_display_team"],
                name="gk_current_team_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="playerseasongkderivedstats",
            index=models.Index(
                condition=models.Q(("is_current", True)),
                fields=["competition_season", "canonical_player"],
                name="gk_current_player_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="mergedplayerseason",
            index=models.Index(
                condition=models.Q(("is_current", True)),
                fields=["competition_season", "canonical_display_team"],
                name="merged_player_current_team_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="mergedplayerseason",
            index=models.Index(
                condition=models.Q(("is_current", True)),
                fields=["competition_season", "canonical_player"],
                name="mp_cur_player_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="galaxyplayerembedding",
            index=models.Index(fields=["snapshot", "minutes"], name="gal_emb_snap_min_idx"),
        ),
        migrations.AddIndex(
            model_name="galaxyplayerembedding",
            index=models.Index(
                fields=["snapshot", "position_group", "minutes"],
                name="galaxy_embedding_pos_min_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="galaxyplayerembedding",
            index=models.Index(
                fields=["snapshot", "canonical_display_team", "minutes"],
                name="galaxy_embedding_team_min_idx",
            ),
        ),
    ]
