from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0022_materializedapipayload_and_perf_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="competitionseason",
            name="refresh_enabled",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.CreateModel(
            name="IngestionBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(db_index=True, default="daily_refresh", max_length=32)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("planned", "Planned"),
                            ("running", "Running"),
                            ("success", "Success"),
                            ("partial_success", "Partial success"),
                            ("failed", "Failed"),
                            ("skipped", "Skipped"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        default="planned",
                        max_length=24,
                    ),
                ),
                ("scheduled_for_date", models.DateField(db_index=True)),
                ("planned_start_at", models.DateTimeField(blank=True, null=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("manual", models.BooleanField(default=False)),
                ("summary_stats", models.JSONField(blank=True, default=dict)),
                ("aggregate_run_ids", models.JSONField(blank=True, default=dict)),
                ("error_detail", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-scheduled_for_date", "-id"],
            },
        ),
        migrations.CreateModel(
            name="IngestionBatchItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("success", "Success"),
                            ("failed", "Failed"),
                            ("skipped", "Skipped"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=24,
                    ),
                ),
                ("planned_order", models.PositiveSmallIntegerField(default=0)),
                ("eta", models.DateTimeField(blank=True, null=True)),
                ("current_stage", models.CharField(blank=True, max_length=32)),
                ("stage_run_ids", models.JSONField(blank=True, default=dict)),
                ("stage_stats", models.JSONField(blank=True, default=dict)),
                ("error_detail", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="ingestion.ingestionbatch",
                    ),
                ),
                (
                    "competition_season",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ingestion_batch_items",
                        to="ingestion.competitionseason",
                    ),
                ),
            ],
            options={
                "ordering": ["batch_id", "planned_order", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="ingestionbatch",
            constraint=models.UniqueConstraint(
                condition=models.Q(manual=False),
                fields=("kind", "scheduled_for_date"),
                name="uniq_ingestion_batch_kind_date",
            ),
        ),
        migrations.AddIndex(
            model_name="ingestionbatch",
            index=models.Index(fields=["kind", "status"], name="ing_batch_kind_status_idx"),
        ),
        migrations.AddIndex(
            model_name="ingestionbatch",
            index=models.Index(fields=["status", "planned_start_at"], name="ing_batch_status_start_idx"),
        ),
        migrations.AddConstraint(
            model_name="ingestionbatchitem",
            constraint=models.UniqueConstraint(
                fields=("batch", "competition_season"),
                name="uniq_ingestion_batch_item_slice",
            ),
        ),
        migrations.AddIndex(
            model_name="ingestionbatchitem",
            index=models.Index(fields=["batch", "status"], name="ing_item_batch_status_idx"),
        ),
        migrations.AddIndex(
            model_name="ingestionbatchitem",
            index=models.Index(fields=["competition_season", "status"], name="ing_item_slice_status_idx"),
        ),
    ]
