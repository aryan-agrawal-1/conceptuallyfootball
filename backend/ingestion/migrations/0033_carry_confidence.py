import importlib
import math

from django.db import migrations, models


ACQUISITION_TYPES = frozenset({5, 6, 7, 14})


def classify_acquisition_carries(apps, schema_editor):
    ProviderMatch = apps.get_model("ingestion", "ProviderMatch")
    database = schema_editor.connection.alias

    matches = ProviderMatch.objects.using(database).prefetch_related("events", "derived_carries")
    for provider_match in matches.iterator(chunk_size=100):
        events = {event.event_index: event for event in provider_match.events.all()}
        rejected_ids = []
        low_confidence_ids = []
        for carry in provider_match.derived_carries.all():
            origin = events.get(carry.start_event_index)
            if origin is None or origin.event_type not in ACQUISITION_TYPES:
                continue
            elapsed_seconds = carry.match_seconds - origin.match_seconds
            distance = math.hypot(
                (carry.end_x - carry.x) * 105.0 / 10_000,
                (carry.end_y - carry.y) * 68.0 / 10_000,
            )
            if elapsed_seconds == 0 or (elapsed_seconds == 1 and distance > 6.0):
                rejected_ids.append(carry.id)
            elif elapsed_seconds == 1:
                low_confidence_ids.append(carry.id)
        if rejected_ids:
            provider_match.derived_carries.filter(id__in=rejected_ids).delete()
        if low_confidence_ids:
            provider_match.derived_carries.filter(id__in=low_confidence_ids).update(
                is_low_confidence=True
            )


def restore_previous_carries(apps, schema_editor):
    previous = importlib.import_module(
        "ingestion.migrations.0032_conservative_carry_continuity"
    )
    previous.rebuild_carries(apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0032_conservative_carry_continuity"),
    ]

    operations = [
        migrations.AddField(
            model_name="providermatchcarry",
            name="is_low_confidence",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(classify_acquisition_carries, restore_previous_carries),
    ]
