import gzip
import json

from django.db import migrations, models


def classify_stored_own_goals(apps, schema_editor):
    ProviderMatchEvent = apps.get_model("ingestion", "ProviderMatchEvent")
    ProviderMatchPayload = apps.get_model("ingestion", "ProviderMatchPayload")
    payloads = ProviderMatchPayload.objects.exclude(payload_gzip=None).only(
        "provider_match_id", "payload_gzip"
    )
    for stored in payloads.iterator(chunk_size=100):
        wrapped = json.loads(gzip.decompress(bytes(stored.payload_gzip)))
        payload = wrapped.get("payload", wrapped)
        own_goal_ids = [
            str(event["id"])
            for event in payload.get("events", [])
            if event.get("id") is not None
            and any(
                qualifier.get("type", {}).get("displayName") == "OwnGoal"
                for qualifier in event.get("qualifiers", [])
            )
        ]
        if own_goal_ids:
            ProviderMatchEvent.objects.filter(
                provider_match_id=stored.provider_match_id,
                provider_event_id__in=own_goal_ids,
                event_type=4,
            ).update(event_type=19)


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0028_providermatchevent_is_defensive"),
    ]

    operations = [
        migrations.AlterField(
            model_name="providermatchevent",
            name="event_type",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (0, "Unknown"),
                    (1, "Pass"),
                    (2, "Ball touch"),
                    (3, "Take-on"),
                    (4, "Shot"),
                    (5, "Ball recovery"),
                    (6, "Tackle"),
                    (7, "Interception"),
                    (8, "Clearance"),
                    (9, "Blocked pass"),
                    (10, "Aerial"),
                    (11, "Challenge"),
                    (12, "Dispossessed"),
                    (13, "Foul"),
                    (14, "Save"),
                    (15, "Offside"),
                    (16, "Card"),
                    (17, "Substitution"),
                    (18, "Administrative"),
                    (19, "Own goal"),
                ],
                default=0,
            ),
        ),
        migrations.RunPython(classify_stored_own_goals, migrations.RunPython.noop),
    ]
