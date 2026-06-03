from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0024_alter_ingestionrun_kind_playerpositionresolution"),
    ]

    operations = [
        migrations.AddField(
            model_name="materializedapipayload",
            name="payload_json",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="materializedapipayload",
            name="payload_etag",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
    ]
