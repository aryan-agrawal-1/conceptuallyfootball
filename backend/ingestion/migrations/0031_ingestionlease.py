from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ingestion", "0030_finalize_whoscored_data")]

    operations = [
        migrations.CreateModel(
            name="IngestionLease",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("key", models.CharField(max_length=128, unique=True)),
                ("owner_token", models.CharField(max_length=64)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
