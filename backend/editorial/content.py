from __future__ import annotations

import re
import uuid
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError


MAX_BLOCKS = 300
MAX_TEXT_LENGTH = 20_000
MAX_LIST_ITEMS = 100
MAX_INLINE_RUNS = 500
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
        normalized_run = {"text": text}
        if link is not None:
            normalized_run["link"] = safe_url(link, field=f"{field} link")

        if normalized and normalized[-1].get("link") == normalized_run.get("link"):
            normalized[-1]["text"] += text
        else:
            normalized.append(normalized_run)

    return normalized or [{"text": ""}]


def block_inline_content(block: dict, *, field: str, maximum: int = MAX_TEXT_LENGTH) -> list[dict]:
    if "content" in block:
        return normalize_inline_content(block["content"], field=field, maximum=maximum)
    return [{"text": clean_text(block.get("text", ""), field=field, maximum=maximum)}]


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
        elif block_type == "divider":
            normalized.append(common)
        else:
            raise ValidationError(f"Block type '{block_type}' is not supported.")

    return {"version": 1, "blocks": normalized}
