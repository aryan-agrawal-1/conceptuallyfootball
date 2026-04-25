from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0003_alter_ingestionrun_kind_playerseasonderivedstats"),
    ]

    operations = [
        migrations.AddField(
            model_name="reepplayerrow",
            name="position",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="reepplayerrow",
            name="position_detail",
            field=models.CharField(blank=True, max_length=128),
        ),
    ]
