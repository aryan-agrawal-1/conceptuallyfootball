import importlib
import math

from django.db import migrations


PASS = 1
BALL_TOUCH = 2
TAKE_ON = 3
SHOT = 4
BALL_RECOVERY = 5
TACKLE = 6
INTERCEPTION = 7
CLEARANCE = 8
BLOCKED_PASS = 9
AERIAL = 10
CHALLENGE = 11
DISPOSSESSED = 12
FOUL = 13
SAVE = 14
OFFSIDE = 15
SUBSTITUTION = 17
ADMINISTRATIVE = 18
OWN_GOAL = 19
HEAD = 3

ACQUISITION_TYPES = frozenset({BALL_RECOVERY, SAVE, TACKLE, INTERCEPTION})
CONTROL_TYPES = frozenset({BALL_TOUCH, TAKE_ON})
END_TYPES = frozenset({PASS, BALL_TOUCH, TAKE_ON, SHOT})
ANCHOR_TYPES = frozenset({PASS} | ACQUISITION_TYPES | CONTROL_TYPES | END_TYPES)
BREAK_TYPES = frozenset(
    {
        AERIAL,
        CHALLENGE,
        CLEARANCE,
        BLOCKED_PASS,
        DISPOSSESSED,
        FOUL,
        OFFSIDE,
        SUBSTITUTION,
        ADMINISTRATIVE,
        OWN_GOAL,
    }
)


def located_anchor(event):
    return event.event_type in ANCHOR_TYPES and event.x is not None and event.y is not None


def phase_interrupted(events):
    return any(
        event.event_type in BREAK_TYPES
        or event.event_type in ANCHOR_TYPES
        or event.is_set_piece
        or event.is_throw_in
        or event.is_corner
        or event.is_free_kick
        or event.is_touch
        for event in events
    )


def valid_end(event):
    if event.event_type not in END_TYPES:
        return False
    if event.is_set_piece or event.is_throw_in or event.is_corner or event.is_free_kick:
        return False
    return not (event.event_type == SHOT and event.body_part == HEAD)


def start_position(previous, event):
    if (
        previous.event_type == PASS
        and previous.outcome_successful is True
        and previous.end_x is not None
        and previous.end_y is not None
    ):
        return previous.end_x, previous.end_y
    same_player = (
        previous.provider_player_id is not None
        and previous.provider_player_id == event.provider_player_id
    )
    if (
        same_player
        and previous.outcome_successful is True
        and previous.event_type in ACQUISITION_TYPES | CONTROL_TYPES
    ):
        return previous.x, previous.y
    return None


def distance_metres(start, end):
    return math.hypot(
        (end[0] - start[0]) * 105.0 / 10_000,
        (end[1] - start[1]) * 68.0 / 10_000,
    )


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
            if located_anchor(event)
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
            if not valid_end(event):
                continue
            start = start_position(previous, event)
            if start is None:
                continue
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


def restore_previous_carries(apps, schema_editor):
    previous = importlib.import_module(
        "ingestion.migrations.0031_carry_continuity_and_classifications"
    )
    previous.rebuild_carries(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [("ingestion", "0031_carry_continuity_and_classifications")]

    operations = [migrations.RunPython(rebuild_carries, restore_previous_carries)]
