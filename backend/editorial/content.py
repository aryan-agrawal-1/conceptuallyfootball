from __future__ import annotations

import re
import uuid
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError


MAX_BLOCKS = 300
MAX_TEXT_LENGTH = 20_000
MAX_LIST_ITEMS = 100
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


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
                {**common, "level": level, "text": clean_text(block.get("text", ""), field="Heading")}
            )
        elif block_type in {"paragraph", "quote"}:
            normalized.append(
                {**common, "text": clean_text(block.get("text", ""), field=block_type.title())}
            )
        elif block_type == "callout":
            tone = block.get("tone", "note")
            if tone not in {"note", "insight", "warning"}:
                tone = "note"
            normalized.append(
                {
                    **common,
                    "tone": tone,
                    "text": clean_text(block.get("text", ""), field="Callout"),
                }
            )
        elif block_type in {"bulleted_list", "numbered_list"}:
            items = block.get("items")
            if not isinstance(items, list) or len(items) > MAX_LIST_ITEMS:
                raise ValidationError("List items are invalid.")
            normalized.append(
                {
                    **common,
                    "items": [clean_text(item, field="List item", maximum=2_000) for item in items],
                }
            )
        elif block_type == "link":
            normalized.append(
                {
                    **common,
                    "text": clean_text(block.get("text", ""), field="Link label", maximum=2_000),
                    "url": safe_url(block.get("url", ""), field="Link URL", allow_empty=True),
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
        elif block_type == "divider":
            normalized.append(common)
        else:
            raise ValidationError(f"Block type '{block_type}' is not supported.")

    return {"version": 1, "blocks": normalized}
