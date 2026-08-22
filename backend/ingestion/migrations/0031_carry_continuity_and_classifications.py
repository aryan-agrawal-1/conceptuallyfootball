import math

from django.db import migrations, models


ACTION_EVENT_TYPES = frozenset(range(1, 13))
AERIAL_AND_CHALLENGE = frozenset({10, 11})
PHASE_BREAK_EVENT_TYPES = frozenset({13, 15, 17, 18})


def is_action(event):
    if event.event_type in AERIAL_AND_CHALLENGE:
        return event.is_defensive
    return event.event_type in ACTION_EVENT_TYPES


def located_action(event):
    return is_action(event) and event.x is not None and event.y is not None


def phase_interrupted(events):
    return any(
        event.event_type in PHASE_BREAK_EVENT_TYPES
        or event.is_set_piece
        or event.is_throw_in
        or event.is_corner
        or event.is_free_kick
        or event.is_touch
        or is_action(event)
        for event in events
    )


def action_end_position(event):
    if (
        event.event_type == 1
        and event.outcome_successful is True
        and event.end_x is not None
        and event.end_y is not None
    ):
        return event.end_x, event.end_y
    return event.x, event.y


def distance_metres(start, end):
    delta_x = (end[0] - start[0]) * 105.0 / 10_000
    delta_y = (end[1] - start[1]) * 68.0 / 10_000
    return math.hypot(delta_x, delta_y)


def progressive(start, end):
    start_m = (start[0] / 10_000 * 105, start[1] / 10_000 * 68)
    end_m = (end[0] / 10_000 * 105, end[1] / 10_000 * 68)
    progress = math.dist(start_m, (105, 34)) - math.dist(end_m, (105, 34))
    if start[0] < 5000 and end[0] < 5000:
        return progress >= 30
    if start[0] < 5000 <= end[0]:
        return progress >= 15
    return progress >= 10


def inside_box(point):
    return point[0] >= 8350 and 2110 <= point[1] <= 7890


def rebuild_carries(apps, schema_editor):
    ProviderMatch = apps.get_model("ingestion", "ProviderMatch")
    ProviderMatchCarry = apps.get_model("ingestion", "ProviderMatchCarry")
    database = schema_editor.connection.alias

    ProviderMatchCarry.objects.using(database).all().delete()
    rows = []
    matches = ProviderMatch.objects.using(database).prefetch_related("events").iterator(chunk_size=100)
    for provider_match in matches:
        event_stream = sorted(provider_match.events.all(), key=lambda event: event.event_index)
        located = [
            (stream_index, event)
            for stream_index, event in enumerate(event_stream)
            if located_action(event)
        ]
        for (previous_index, previous), (event_index, event) in zip(located, located[1:]):
            if (
                event.provider_player_id is None
                or not event.provider_team_id
                or event.provider_team_id != previous.provider_team_id
                or event.period != previous.period
                or event.match_seconds is None
                or previous.match_seconds is None
            ):
                continue
            elapsed_seconds = event.match_seconds - previous.match_seconds
            if not 0 <= elapsed_seconds <= 10:
                continue
            if phase_interrupted(event_stream[previous_index + 1 : event_index]):
                continue
            if event.is_set_piece or event.is_throw_in or event.is_corner or event.is_free_kick:
                continue
            if event.event_type == 4 and event.body_part == 3:
                continue

            start = action_end_position(previous)
            end = (event.x, event.y)
            if not 3.0 <= distance_metres(start, end) <= 60.0:
                continue
            rows.append(
                ProviderMatchCarry(
                    provider_match_id=provider_match.id,
                    start_event_index=previous.event_index,
                    end_event_index=event.event_index,
                    provider_team_id=event.provider_team_id,
                    team_id=event.team_id,
                    provider_player_id=event.provider_player_id,
                    player_id=event.player_id,
                    period=event.period,
                    minute=event.minute,
                    second=event.second,
                    match_seconds=event.match_seconds,
                    x=start[0],
                    y=start[1],
                    end_x=end[0],
                    end_y=end[1],
                    is_progressive_carry=progressive(start, end),
                    is_final_third_entry=start[0] < 6670 <= end[0],
                    is_box_entry=not inside_box(start) and inside_box(end),
                )
            )
            if len(rows) >= 5000:
                ProviderMatchCarry.objects.using(database).bulk_create(rows, batch_size=1000)
                rows = []
    if rows:
        ProviderMatchCarry.objects.using(database).bulk_create(rows, batch_size=1000)


def rebuild_legacy_carries(apps, schema_editor):
    ProviderMatch = apps.get_model("ingestion", "ProviderMatch")
    ProviderMatchCarry = apps.get_model("ingestion", "ProviderMatchCarry")
    database = schema_editor.connection.alias

    ProviderMatchCarry.objects.using(database).all().delete()
    rows = []
    matches = ProviderMatch.objects.using(database).prefetch_related("events").iterator(chunk_size=100)
    for provider_match in matches:
        located = sorted(
            (
                event
                for event in provider_match.events.all()
                if event.is_touch and event.x is not None and event.y is not None
            ),
            key=lambda event: event.event_index,
        )
        for previous, event in zip(located, located[1:]):
            if (
                event.provider_player_id is None
                or event.provider_player_id != previous.provider_player_id
                or event.team_id != previous.team_id
            ):
                continue
            start = action_end_position(previous)
            end = (event.x, event.y)
            if not 3.0 <= distance_metres(start, end) <= 60.0:
                continue
            rows.append(
                ProviderMatchCarry(
                    provider_match_id=provider_match.id,
                    start_event_index=previous.event_index,
                    end_event_index=event.event_index,
                    provider_team_id=event.provider_team_id,
                    team_id=event.team_id,
                    provider_player_id=event.provider_player_id,
                    player_id=event.player_id,
                    period=event.period,
                    minute=event.minute,
                    second=event.second,
                    match_seconds=event.match_seconds,
                    x=start[0],
                    y=start[1],
                    end_x=end[0],
                    end_y=end[1],
                )
            )
            if len(rows) >= 5000:
                ProviderMatchCarry.objects.using(database).bulk_create(rows, batch_size=1000)
                rows = []
    if rows:
        ProviderMatchCarry.objects.using(database).bulk_create(rows, batch_size=1000)


class Migration(migrations.Migration):
    dependencies = [("ingestion", "0030_providermatchcarry")]

    operations = [
        migrations.AddField(
            model_name="providermatchcarry",
            name="is_box_entry",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="providermatchcarry",
            name="is_final_third_entry",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="providermatchcarry",
            name="is_progressive_carry",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(rebuild_carries, rebuild_legacy_carries),
    ]
