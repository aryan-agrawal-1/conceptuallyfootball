from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0010_alter_ingestionrun_kind_playerseasonembedding_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="playerseasonembedding",
            name="cluster_label",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
