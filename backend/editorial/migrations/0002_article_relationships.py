import django.db.models.deletion
from django.db import migrations, models

import editorial.models


class Migration(migrations.Migration):

    dependencies = [
        ("editorial", "0001_initial"),
        ("ingestion", "0028_providermatchevent_is_defensive"),
    ]

    operations = [
        migrations.AddField(
            model_name="articlerevision",
            name="subjects",
            field=models.JSONField(default=editorial.models.empty_subjects),
        ),
        migrations.CreateModel(
            name="ArticlePlayerSubject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveSmallIntegerField()),
                ("context", models.JSONField(blank=True, default=dict)),
                ("article", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="player_subject_links", to="editorial.article")),
                ("player", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="article_subject_links", to="ingestion.canonicalplayer")),
            ],
            options={"ordering": ("position", "id")},
        ),
        migrations.CreateModel(
            name="ArticleTeamSubject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveSmallIntegerField()),
                ("context", models.JSONField(blank=True, default=dict)),
                ("article", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="team_subject_links", to="editorial.article")),
                ("team", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="article_subject_links", to="ingestion.canonicalteam")),
            ],
            options={"ordering": ("position", "id")},
        ),
        migrations.CreateModel(
            name="ArticlePlayerReference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("article", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="player_reference_links", to="editorial.article")),
                ("player", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="article_reference_links", to="ingestion.canonicalplayer")),
            ],
        ),
        migrations.CreateModel(
            name="ArticleTeamReference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("article", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="team_reference_links", to="editorial.article")),
                ("team", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="article_reference_links", to="ingestion.canonicalteam")),
            ],
        ),
        migrations.AddConstraint(model_name="articleplayersubject", constraint=models.UniqueConstraint(fields=("article", "player"), name="unique_article_player_subject")),
        migrations.AddConstraint(model_name="articleplayersubject", constraint=models.UniqueConstraint(fields=("article", "position"), name="unique_article_player_subject_position")),
        migrations.AddIndex(model_name="articleplayersubject", index=models.Index(fields=["player", "article"], name="editorial_player_subject_idx")),
        migrations.AddConstraint(model_name="articleteamsubject", constraint=models.UniqueConstraint(fields=("article", "team"), name="unique_article_team_subject")),
        migrations.AddConstraint(model_name="articleteamsubject", constraint=models.UniqueConstraint(fields=("article", "position"), name="unique_article_team_subject_position")),
        migrations.AddIndex(model_name="articleteamsubject", index=models.Index(fields=["team", "article"], name="editorial_team_subject_idx")),
        migrations.AddConstraint(model_name="articleplayerreference", constraint=models.UniqueConstraint(fields=("article", "player"), name="unique_article_player_reference")),
        migrations.AddIndex(model_name="articleplayerreference", index=models.Index(fields=["player", "article"], name="editorial_player_reference_idx")),
        migrations.AddConstraint(model_name="articleteamreference", constraint=models.UniqueConstraint(fields=("article", "team"), name="unique_article_team_reference")),
        migrations.AddIndex(model_name="articleteamreference", index=models.Index(fields=["team", "article"], name="editorial_team_reference_idx")),
    ]
