from django.db import migrations


def remove_legacy_subject_context(apps, schema_editor):
    models = (
        apps.get_model("editorial", "ArticlePlayerSubject"),
        apps.get_model("editorial", "ArticleTeamSubject"),
    )
    with schema_editor.connection.cursor() as cursor:
        for model in models:
            table_name = model._meta.db_table
            columns = {
                column.name
                for column in schema_editor.connection.introspection.get_table_description(
                    cursor,
                    table_name,
                )
            }
            if "context" not in columns:
                continue
            quoted_table = schema_editor.quote_name(table_name)
            quoted_column = schema_editor.quote_name("context")
            schema_editor.execute(f"ALTER TABLE {quoted_table} DROP COLUMN {quoted_column}")


class Migration(migrations.Migration):

    dependencies = [
        ("editorial", "0003_article_publishing_workflow"),
    ]

    operations = [
        migrations.RunPython(
            remove_legacy_subject_context,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
