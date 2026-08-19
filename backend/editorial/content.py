from __future__ import annotations

import re
import uuid
from datetime import date
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError


MAX_BLOCKS = 300
MAX_TEXT_LENGTH = 20_000
MAX_LIST_ITEMS = 100
MAX_INLINE_RUNS = 500
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
VISUAL_TYPES = {
    "similar_players",
    "player_radar",
    "stat_card",
    "player_comparison",
    "custom_chart",
}
VISUAL_PLAYER_ONLY_TYPES = {
    "similar_players",
    "player_radar",
    "player_comparison",
}
VISUAL_CHART_TYPES = {"scatter", "bar", "radar", "dumbbell", "table"}
VISUAL_RATE_MODES = {"per90", "full"}
VISUAL_SCOPE_KINDS = {"competition", "league", "big5", "all"}
VISUAL_UPDATE_POLICIES = {"live_draft_freeze_on_publish", "frozen"}


def clean_text(value, *, field: str, maximum: int = MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text.")
    value = CONTROL_CHARACTERS.sub("", value)
    if len(value) > maximum:
        raise ValidationError(f"{field} is too long.")
    return value


def safe_url(value, *, field: str, allow_empty: bool = False) -> str:
    value = clean_text(value, field=field, maximum=2_000).strip()
    if allow_empty and not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValidationError(f"{field} must be a valid http or https URL.")
    return value


def block_id(value) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return str(uuid.uuid4())


def entity_integer(value, *, field: str) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be a number.")
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a number.") from None
    if normalized < 1:
        raise ValidationError(f"{field} is invalid.")
    return normalized


def normalize_entity_context(value) -> dict:
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise ValidationError("Entity context is invalid.")
    context = {}
    competition_code = clean_text(
        value.get("competition_code", ""), field="Entity competition", maximum=32
    ).strip().upper()
    season_label = clean_text(
        value.get("season_label", ""), field="Entity season", maximum=32
    ).strip()
    competition_season_id = value.get("competition_season_id")
    if competition_code:
        context["competition_code"] = competition_code
    if season_label:
        context["season_label"] = season_label
    if competition_season_id not in (None, ""):
        context["competition_season_id"] = entity_integer(
            competition_season_id, field="Entity competition season ID"
        )
    team = value.get("team")
    if team not in (None, {}):
        if not isinstance(team, dict):
            raise ValidationError("Entity club context is invalid.")
        team_name = clean_text(
            team.get("name", ""), field="Entity club name", maximum=240
        ).strip()
        if not team_name:
            raise ValidationError("Entity club context is incomplete.")
        context["team"] = {
            "id": entity_integer(team.get("id"), field="Entity club ID"),
            "name": team_name,
        }
    return context


def normalize_entity_reference(value) -> dict:
    if not isinstance(value, dict):
        raise ValidationError("Entity reference is invalid.")
    kind = value.get("kind")
    if kind not in {"player", "team"}:
        raise ValidationError("Entity reference type is invalid.")
    name = clean_text(value.get("name", ""), field="Entity name", maximum=240).strip()
    if not name:
        raise ValidationError("Entity reference name is required.")
    reference = {
        "kind": kind,
        "id": entity_integer(value.get("id"), field="Entity ID"),
        "name": name,
    }
    context = normalize_entity_context(value.get("context"))
    if context:
        reference["context"] = context
    return reference


def normalize_inline_content(value, *, field: str, maximum: int = MAX_TEXT_LENGTH) -> list[dict]:
    if not isinstance(value, list) or len(value) > MAX_INLINE_RUNS:
        raise ValidationError(f"{field} content is invalid.")

    normalized = []
    total_length = 0
    for run in value:
        if not isinstance(run, dict):
            raise ValidationError(f"{field} content is invalid.")
        text = clean_text(run.get("text", ""), field=field, maximum=maximum)
        total_length += len(text)
        if total_length > maximum:
            raise ValidationError(f"{field} is too long.")
        link = run.get("link")
        reference = run.get("reference")
        bold = run.get("bold")
        italic = run.get("italic")
        normalized_run = {"text": text}
        if (bold is not None and not isinstance(bold, bool)) or (
            italic is not None and not isinstance(italic, bool)
        ):
            raise ValidationError(f"{field} formatting is invalid.")
        if link is not None and reference is not None:
            raise ValidationError(f"{field} content cannot be both a link and an entity reference.")
        if link is not None:
            normalized_run["link"] = safe_url(link, field=f"{field} link")
        if reference is not None:
            normalized_reference = normalize_entity_reference(reference)
            if text != f"@{normalized_reference['name']}":
                raise ValidationError(f"{field} entity reference label is invalid.")
            normalized_run["reference"] = normalized_reference
        if bold:
            normalized_run["bold"] = True
        if italic:
            normalized_run["italic"] = True

        if (
            normalized
            and "reference" not in normalized[-1]
            and "reference" not in normalized_run
            and normalized[-1].get("link") == normalized_run.get("link")
            and normalized[-1].get("bold") == normalized_run.get("bold")
            and normalized[-1].get("italic") == normalized_run.get("italic")
        ):
            normalized[-1]["text"] += text
        else:
            normalized.append(normalized_run)

    return normalized or [{"text": ""}]


def block_inline_content(block: dict, *, field: str, maximum: int = MAX_TEXT_LENGTH) -> list[dict]:
    if "content" in block:
        return normalize_inline_content(block["content"], field=field, maximum=maximum)
    return [{"text": clean_text(block.get("text", ""), field=field, maximum=maximum)}]


def visual_integer(value, *, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be a number.")
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a number.") from None
    if normalized < minimum:
        raise ValidationError(f"{field} is invalid.")
    return normalized


def visual_string_list(value, *, field: str, maximum_items: int, maximum_length: int = 120) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum_items:
        raise ValidationError(f"{field} is invalid.")
    normalized = []
    for item in value:
        text = clean_text(item, field=field, maximum=maximum_length).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def normalize_visual_entity(value, *, expected_kind: str | None = None) -> dict:
    if not isinstance(value, dict):
        raise ValidationError("Visual entity is invalid.")
    kind = value.get("kind")
    if kind not in {"player", "team"} or (expected_kind and kind != expected_kind):
        raise ValidationError("Visual entity type is invalid.")
    entity = {
        "kind": kind,
        "id": visual_integer(value.get("id"), field="Visual entity ID", minimum=1),
        "name": clean_text(value.get("name", ""), field="Visual entity name", maximum=240).strip(),
        "source_competition": clean_text(
            value.get("source_competition", ""), field="Source competition", maximum=32
        ).strip().upper(),
        "season_label": clean_text(value.get("season_label", ""), field="Season", maximum=32).strip(),
        "competition_season_id": visual_integer(
            value.get("competition_season_id"), field="Competition season ID"
        ),
    }
    if not entity["name"] or not entity["source_competition"] or not entity["season_label"]:
        raise ValidationError("Visual entity context is incomplete.")
    if kind == "player":
        position_group = clean_text(
            value.get("position_group", "UNK"), field="Position group", maximum=8
        ).strip().upper()
        entity["position_group"] = position_group if position_group in {"FWD", "MID", "DEF", "GK", "UNK"} else "UNK"
        entity["team_name"] = clean_text(
            value.get("team_name", ""), field="Team name", maximum=240
        ).strip()
    return entity


def normalize_visual_context(value) -> dict:
    if not isinstance(value, dict):
        raise ValidationError("Visual comparison context is invalid.")
    scope_kind = value.get("scope_kind")
    if scope_kind not in VISUAL_SCOPE_KINDS:
        raise ValidationError("Visual comparison scope is invalid.")
    context = {
        "scope_kind": scope_kind,
        "scope_code": clean_text(value.get("scope_code", ""), field="Scope code", maximum=32).strip().upper(),
        "scope_label": clean_text(value.get("scope_label", ""), field="Scope label", maximum=120).strip(),
        "season_label": clean_text(value.get("season_label", ""), field="Scope season", maximum=32).strip(),
    }
    if not all(context.values()):
        raise ValidationError("Visual comparison context is incomplete.")
    return context


def normalize_visual_block(block: dict, common: dict) -> dict:
    visual_type = block.get("visual_type")
    if visual_type not in VISUAL_TYPES:
        raise ValidationError("Visual type is not supported.")
    config = block.get("config")
    if not isinstance(config, dict):
        raise ValidationError("Visual configuration is invalid.")

    entity_kind = config.get("entity_kind")
    if entity_kind not in {"player", "team"}:
        raise ValidationError("Visual entity type is invalid.")
    if visual_type in VISUAL_PLAYER_ONLY_TYPES and entity_kind != "player":
        raise ValidationError("This visual only supports players.")
    entities_value = config.get("entities")
    if not isinstance(entities_value, list) or len(entities_value) > 3:
        raise ValidationError("Visual entities are invalid.")
    entities = [normalize_visual_entity(entity, expected_kind=entity_kind) for entity in entities_value]
    minimum_entities = 2 if visual_type == "player_comparison" else 0 if visual_type == "custom_chart" else 1
    if len(entities) < minimum_entities:
        raise ValidationError("Select enough entities for this visual.")

    rate_mode = config.get("rate_mode", "per90")
    if rate_mode not in VISUAL_RATE_MODES:
        raise ValidationError("Visual rate mode is invalid.")
    chart_type = config.get("chart_type", "radar")
    if chart_type not in VISUAL_CHART_TYPES:
        raise ValidationError("Visual chart type is invalid.")
    metric_keys = visual_string_list(
        config.get("metric_keys", []), field="Visual metrics", maximum_items=12, maximum_length=120
    )
    if visual_type not in {"similar_players"} and not metric_keys:
        raise ValidationError("Select at least one metric for this visual.")
    if visual_type in {"player_radar", "player_comparison"} and len(metric_keys) < 3:
        raise ValidationError("Radar visuals need at least three metrics.")
    if visual_type == "custom_chart" and chart_type == "scatter" and len(metric_keys) < 2:
        raise ValidationError("Scatter charts need an x and y metric.")
    if visual_type == "custom_chart" and chart_type == "radar" and len(metric_keys) < 3:
        raise ValidationError("Radar charts need at least three metrics.")

    filters = config.get("filters", {})
    if not isinstance(filters, dict):
        raise ValidationError("Visual filters are invalid.")
    position_group = clean_text(
        filters.get("position_group", "ALL"), field="Position filter", maximum=8
    ).strip().upper()
    if position_group not in {"ALL", "FWD", "MID", "DEF", "GK"}:
        position_group = "ALL"
    normalized_config = {
        "entity_kind": entity_kind,
        "entities": entities,
        "context": normalize_visual_context(config.get("context")),
        "chart_type": chart_type,
        "metric_keys": metric_keys,
        "rate_mode": rate_mode,
        "filters": {
            "position_group": position_group,
            "team_names": visual_string_list(
                filters.get("team_names", []), field="Team filters", maximum_items=30, maximum_length=240
            ),
            "minimum_minutes": visual_integer(
                filters.get("minimum_minutes", 450), field="Minimum minutes"
            ),
            "labels": filters.get("labels", True) is True,
            "trendline": filters.get("trendline", False) is True,
            "bar_window": filters.get("bar_window", "top")
            if filters.get("bar_window", "top") in {"top", "bottom", "all"}
            else "top",
            "bar_count": min(
                20,
                max(5, visual_integer(filters.get("bar_count", 12), field="Bar count", minimum=1)),
            ),
        },
    }

    data_as_of = clean_text(block.get("data_as_of", ""), field="Data as-of date", maximum=10).strip()
    try:
        date.fromisoformat(data_as_of)
    except ValueError:
        raise ValidationError("Data as-of date must use YYYY-MM-DD.") from None
    update_policy = block.get("update_policy", "live_draft_freeze_on_publish")
    if update_policy not in VISUAL_UPDATE_POLICIES:
        raise ValidationError("Visual update policy is invalid.")

    alt = clean_text(block.get("alt", ""), field="Visual alt text", maximum=1_000).strip()
    source_note = clean_text(
        block.get("source_note", "Conceptually Football"), field="Visual source note", maximum=1_000
    ).strip()
    if not alt or not source_note:
        raise ValidationError("Visuals require alt text and a source note.")

    return {
        **common,
        "visual_type": visual_type,
        "title": clean_text(block.get("title", ""), field="Visual title", maximum=240).strip(),
        "caption": clean_text(block.get("caption", ""), field="Visual caption", maximum=2_000).strip(),
        "alt": alt,
        "source_note": source_note,
        "data_as_of": data_as_of,
        "update_policy": update_policy,
        "config": normalized_config,
    }


def normalize_document(value) -> dict:
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValidationError("The article document version is not supported.")
    blocks = value.get("blocks")
    if not isinstance(blocks, list):
        raise ValidationError("Article blocks must be a list.")
    if len(blocks) > MAX_BLOCKS:
        raise ValidationError("The article contains too many blocks.")

    normalized = []
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            raise ValidationError(f"Block {index + 1} is invalid.")
        block_type = block.get("type")
        common = {"id": block_id(block.get("id")), "type": block_type}

        if block_type == "heading":
            level = block.get("level", 2)
            if level not in {2, 3}:
                raise ValidationError("Heading levels must be 2 or 3.")
            normalized.append(
                {**common, "level": level, "content": block_inline_content(block, field="Heading")}
            )
        elif block_type in {"paragraph", "quote"}:
            normalized.append(
                {**common, "content": block_inline_content(block, field=block_type.title())}
            )
        elif block_type == "callout":
            tone = block.get("tone", "note")
            if tone not in {"note", "insight", "warning"}:
                tone = "note"
            normalized.append(
                {
                    **common,
                    "tone": tone,
                    "content": block_inline_content(block, field="Callout"),
                }
            )
        elif block_type in {"bulleted_list", "numbered_list"}:
            items = block.get("items")
            if not isinstance(items, list) or len(items) > MAX_LIST_ITEMS:
                raise ValidationError("List items are invalid.")
            normalized.append(
                {
                    **common,
                    "items": [
                        normalize_inline_content(item, field="List item", maximum=2_000)
                        if isinstance(item, list)
                        else [{"text": clean_text(item, field="List item", maximum=2_000)}]
                        for item in items
                    ],
                }
            )
        elif block_type == "link":
            url = safe_url(block.get("url", ""), field="Link URL", allow_empty=True)
            label = clean_text(block.get("text", ""), field="Link label", maximum=2_000)
            normalized.append(
                {
                    **common,
                    "type": "paragraph",
                    "content": [{"text": label or url, **({"link": url} if url else {})}],
                }
            )
        elif block_type == "image":
            normalized.append(
                {
                    **common,
                    "url": safe_url(block.get("url", ""), field="Image URL", allow_empty=True),
                    "caption": clean_text(block.get("caption", ""), field="Image caption", maximum=2_000),
                    "alt": clean_text(block.get("alt", ""), field="Image alt text", maximum=1_000),
                }
            )
        elif block_type == "visual":
            normalized.append(normalize_visual_block(block, common))
        elif block_type == "divider":
            normalized.append(common)
        else:
            raise ValidationError(f"Block type '{block_type}' is not supported.")

    return {"version": 1, "blocks": normalized}
