from __future__ import annotations

import base64
import binascii
import io
import json
import re
import textwrap
import zipfile
from dataclasses import dataclass
from datetime import datetime
from email.utils import format_datetime
from html import escape
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from accounts.profiles import display_name_for
from editorial.api import PUBLIC_SITE_URL, editorial_error, visible_article
from editorial.content import normalize_document
from editorial.models import Article, ArticlePublication, ArticleStatus


VISUAL_LABELS = {
    "similar_players": "Similar players",
    "player_radar": "Player percentile profile",
    "stat_card": "Key statistics",
    "player_comparison": "Player comparison",
    "custom_chart": "Custom chart",
}
MAX_RENDERED_VISUAL_BYTES = 12 * 1024 * 1024
MAX_RENDERED_VISUAL_TOTAL_BYTES = 48 * 1024 * 1024


@dataclass(frozen=True)
class ExportArticle:
    article_id: str
    slug: str | None
    title: str
    subtitle: str
    author: str
    document: dict
    topics: list[str]
    source_notes: str
    published_at: datetime | None
    canonical_url: str | None
    is_public: bool


@dataclass(frozen=True)
class RenderedVisual:
    data: bytes
    content_type: str
    extension: str
    width: int
    height: int


def active_publication(article: Article) -> ArticlePublication | None:
    if article.status != ArticleStatus.PUBLISHED or not article.slug:
        return None
    return article.publications.filter(unpublished_at__isnull=True).order_by("-version").first()


def export_article(article: Article) -> ExportArticle:
    publication = active_publication(article)
    if publication is not None:
        return ExportArticle(
            article_id=str(article.id),
            slug=article.slug,
            title=publication.title,
            subtitle=publication.subtitle,
            author=display_name_for(article.author),
            document=normalize_document(publication.document),
            topics=list(publication.topics),
            source_notes=publication.source_notes,
            published_at=publication.published_at,
            canonical_url=f"{PUBLIC_SITE_URL}/articles/{article.slug}",
            is_public=True,
        )
    return ExportArticle(
        article_id=str(article.id),
        slug=article.slug,
        title=article.title,
        subtitle=article.subtitle,
        author=display_name_for(article.author),
        document=normalize_document(article.document),
        topics=list(article.topics),
        source_notes=article.source_notes,
        published_at=None,
        canonical_url=None,
        is_public=False,
    )


def article_file_slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return normalized[:80] or "analysis"


def inline_plain(content: list[dict]) -> str:
    return "".join(run.get("text", "") for run in content)


def inline_html(content: list[dict]) -> str:
    values = []
    for run in content:
        text = escape(run.get("text", ""))
        link = run.get("link")
        values.append(f'<a href="{escape(link, quote=True)}">{text}</a>' if link else text)
    return "".join(values)


def inline_markdown(content: list[dict]) -> str:
    values = []
    for run in content:
        text = run.get("text", "").replace("[", "\\[").replace("]", "\\]")
        link = run.get("link")
        values.append(f"[{text}]({link})" if link else text)
    return "".join(values)


def visual_title(block: dict) -> str:
    if block.get("title"):
        return block["title"]
    entities = [entity.get("name", "") for entity in block.get("config", {}).get("entities", [])]
    names = [name for name in entities if name]
    visual_type = block.get("visual_type")
    if visual_type == "similar_players" and names:
        return f"Players most similar to {names[0]}"
    if visual_type == "player_radar" and names:
        return f"{names[0]} percentile profile"
    if visual_type == "player_comparison" and names:
        return " vs ".join(names)
    return VISUAL_LABELS.get(visual_type, "Analysis visual")


def human_metric(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("_", " ").replace("-", " ")).strip().title()


def visual_asset_name(index: int, block: dict, extension: str = "svg") -> str:
    return f"visual-{index + 1:02d}-{article_file_slug(visual_title(block))}.{extension}"


def png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n") or data[12:16] != b"IHDR":
        raise ValueError("Rendered PNG is invalid.")
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def jpeg_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 4 or not data.startswith(b"\xff\xd8"):
        raise ValueError("Rendered JPEG is invalid.")
    position = 2
    start_of_frame = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while position + 4 <= len(data):
        if data[position] != 0xFF:
            position += 1
            continue
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            break
        marker = data[position]
        position += 1
        if marker in {0x01, *range(0xD0, 0xDA)}:
            continue
        if position + 2 > len(data):
            break
        segment_length = int.from_bytes(data[position : position + 2], "big")
        if segment_length < 2 or position + segment_length > len(data):
            break
        if marker in start_of_frame:
            if segment_length < 7:
                break
            height = int.from_bytes(data[position + 3 : position + 5], "big")
            width = int.from_bytes(data[position + 5 : position + 7], "big")
            if width > 0 and height > 0:
                return width, height
            break
        position += segment_length
    raise ValueError("Rendered JPEG dimensions could not be read.")


def rendered_visuals_from_request(request: HttpRequest, article: ExportArticle) -> dict[str, RenderedVisual]:
    if request.method != "POST":
        return {}
    if len(request.body) > MAX_RENDERED_VISUAL_TOTAL_BYTES * 2:
        raise ValueError("The rendered visual payload is too large.")
    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("The rendered visual payload is invalid.") from error
    values = payload.get("visuals", []) if isinstance(payload, dict) else []
    if not isinstance(values, list):
        raise ValueError("Rendered visuals must be a list.")
    expected_ids = {block["id"] for block in article.document["blocks"] if block["type"] == "visual"}
    if len(values) > len(expected_ids):
        raise ValueError("The rendered visual payload contains unexpected images.")
    assets = {}
    total_bytes = 0
    for value in values:
        if not isinstance(value, dict) or value.get("block_id") not in expected_ids:
            raise ValueError("The rendered visual payload contains an unknown block.")
        block_id = value["block_id"]
        if block_id in assets:
            raise ValueError("The rendered visual payload contains a duplicate block.")
        match = re.fullmatch(r"data:(image/(?:png|jpeg));base64,([A-Za-z0-9+/=]+)", value.get("data_url", ""))
        if not match:
            raise ValueError("Rendered visuals must be PNG or JPEG data URLs.")
        try:
            data = base64.b64decode(match.group(2), validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("A rendered visual could not be decoded.") from error
        if not data or len(data) > MAX_RENDERED_VISUAL_BYTES:
            raise ValueError("A rendered visual is too large.")
        total_bytes += len(data)
        if total_bytes > MAX_RENDERED_VISUAL_TOTAL_BYTES:
            raise ValueError("The rendered visual payload is too large.")
        content_type = match.group(1)
        width, height = png_dimensions(data) if content_type == "image/png" else jpeg_dimensions(data)
        assets[block_id] = RenderedVisual(
            data=data,
            content_type=content_type,
            extension="png" if content_type == "image/png" else "jpg",
            width=width,
            height=height,
        )
    return assets


def visual_svg(block: dict) -> bytes:
    title = visual_title(block)
    config = block.get("config", {})
    context = config.get("context", {})
    entities = ", ".join(entity.get("name", "") for entity in config.get("entities", []) if entity.get("name"))
    metrics = ", ".join(human_metric(key) for key in config.get("metric_keys", [])[:8])
    description = block.get("alt") or block.get("caption") or "Static analysis visual fallback."
    lines = textwrap.wrap(description, width=88)[:5]
    details = [
        value
        for value in (
            entities,
            " · ".join(filter(None, (context.get("scope_label"), context.get("season_label")))),
            f"Metrics: {metrics}" if metrics else "",
        )
        if value
    ]
    description_svg = "".join(
        f'<tspan x="72" dy="{0 if index == 0 else 30}">{xml_escape(line)}</tspan>'
        for index, line in enumerate(lines)
    )
    detail_svg = "".join(
        f'<text x="72" y="{430 + index * 34}" fill="#aeb8c8" font-size="20">{xml_escape(value)}</text>'
        for index, value in enumerate(details[:3])
    )
    source = block.get("source_note") or "Conceptually Football"
    data_as_of = block.get("data_as_of") or "Not recorded"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675" role="img" aria-labelledby="title description">
  <title id="title">{xml_escape(title)}</title>
  <desc id="description">{xml_escape(description)}</desc>
  <rect width="1200" height="675" fill="#070810"/>
  <rect x="36" y="36" width="1128" height="603" fill="#101522" stroke="#4a9ef5" stroke-opacity="0.38"/>
  <text x="72" y="92" fill="#4a9ef5" font-family="Arial, sans-serif" font-size="17" font-weight="700" letter-spacing="3">CONCEPTUALLY FOOTBALL · {xml_escape(VISUAL_LABELS.get(block.get('visual_type'), 'ANALYSIS VISUAL').upper())}</text>
  <text x="72" y="165" fill="#f5f7fb" font-family="Arial, sans-serif" font-size="42" font-weight="700">{xml_escape(title[:54])}</text>
  <text x="72" y="235" fill="#d8dee9" font-family="Arial, sans-serif" font-size="23">{description_svg}</text>
  {detail_svg}
  <line x1="72" y1="568" x2="1128" y2="568" stroke="#4a9ef5" stroke-opacity="0.25"/>
  <text x="72" y="608" fill="#8290a5" font-family="Arial, sans-serif" font-size="16">Source: {xml_escape(source[:90])} · Data as of {xml_escape(data_as_of)}</text>
  <text x="1128" y="608" text-anchor="end" fill="#4a9ef5" font-family="Arial, sans-serif" font-size="16">conceptuallyfootball.com</text>
</svg>'''.encode("utf-8")


def export_warnings(article: ExportArticle) -> list[str]:
    warnings = []
    for index, block in enumerate(article.document["blocks"]):
        if block["type"] == "image" and not block.get("url"):
            warnings.append(f"Image {index + 1} has no URL and was exported as accessible fallback text.")
        if block["type"] == "visual" and not (block.get("alt") or block.get("caption")):
            warnings.append(f"Visual {index + 1} has no accessible description.")
    return warnings


def render_html(
    article: ExportArticle,
    *,
    visual_url,
    substack: bool = False,
) -> str:
    body = []
    visual_index = 0
    for block in article.document["blocks"]:
        block_type = block["type"]
        if block_type == "heading":
            body.append(f'<h{block["level"]}>{inline_html(block["content"])}</h{block["level"]}>')
        elif block_type == "paragraph":
            body.append(f'<p>{inline_html(block["content"])}</p>')
        elif block_type == "quote":
            body.append(f'<blockquote>{inline_html(block["content"])}</blockquote>')
        elif block_type == "callout":
            body.append(f'<aside><p>{inline_html(block["content"])}</p></aside>')
        elif block_type in {"bulleted_list", "numbered_list"}:
            tag = "ol" if block_type == "numbered_list" else "ul"
            items = "".join(f"<li>{inline_html(item)}</li>" for item in block["items"])
            body.append(f"<{tag}>{items}</{tag}>")
        elif block_type == "image":
            if block.get("url"):
                caption = (
                    f'<figcaption>{escape(block.get("caption", ""))}</figcaption>'
                    if block.get("caption")
                    else ""
                )
                body.append(
                    f'<figure><img src="{escape(block["url"], quote=True)}" alt="{escape(block.get("alt", ""), quote=True)}">'
                    f"{caption}</figure>"
                )
            else:
                body.append(f'<p><em>{escape(block.get("alt") or block.get("caption") or "Image unavailable")}</em></p>')
        elif block_type == "visual":
            url = visual_url(visual_index, block)
            attributes = f' data-visual-block-id="{escape(block["id"], quote=True)}"'
            image = (
                f'<img src="{escape(url, quote=True)}" alt="{escape(block.get("alt", ""), quote=True)}"{attributes}>'
                if url
                else f'<div{attributes}><p><strong>{escape(visual_title(block))}</strong></p><p>{escape(block.get("alt", ""))}</p></div>'
            )
            notes = []
            if block.get("caption"):
                notes.append(f'<p>{escape(block["caption"])}</p>')
            notes.append(
                f'<p><small>Source: {escape(block.get("source_note", "Conceptually Football"))} · Data as of {escape(block.get("data_as_of", ""))}</small></p>'
            )
            body.append(f'<figure>{image}<figcaption>{"".join(notes)}</figcaption></figure>')
            visual_index += 1
        elif block_type == "divider":
            body.append("<hr>")

    meta = [] if substack else [f"By {escape(article.author)}"]
    if article.published_at:
        meta.append(article.published_at.strftime("%d %B %Y"))
    source_notes = (
        f'<section><h2>Source notes</h2><p>{escape(article.source_notes).replace(chr(10), "<br>")}</p></section>'
        if article.source_notes
        else ""
    )
    canonical = (
        f'<p><small>Originally published by <a href="{escape(article.canonical_url, quote=True)}">Conceptually Football</a>.</small></p>'
        if article.canonical_url
        else ""
    )
    subtitle = f'<p><strong>{escape(article.subtitle)}</strong></p>' if article.subtitle else ""
    meta_html = f'<p>{" · ".join(meta)}</p>' if meta else ""
    article_markup = (
        f'<article><header><h1>{escape(article.title)}</h1>'
        f'{subtitle}'
        f'{meta_html}</header>{"".join(body)}{source_notes}<footer>{canonical}<p><small>conceptuallyfootball.com</small></p></footer></article>'
    )
    if substack:
        return article_markup
    styles = """
body{margin:0;background:#f7f8fb;color:#151923;font:17px/1.7 Georgia,serif}article{box-sizing:border-box;max-width:820px;margin:0 auto;padding:64px 32px;background:#fff}h1,h2,h3{font-family:Arial,sans-serif;line-height:1.15}h1{font-size:46px}h2{margin-top:2em}a{color:#1768c4}img{display:block;max-width:100%;height:auto;margin:auto}figure{margin:2.2em 0}figcaption{color:#586174;font:14px/1.55 Arial,sans-serif}ul,ol{padding-left:1.75em}li{padding-left:.3em}li::marker{color:#1768c4;font:700 1.05em Arial,sans-serif}blockquote,aside{border-left:3px solid #4a9ef5;margin:2em 0;padding:.4em 0 .4em 1.4em}hr{border:0;border-top:1px solid #d9deea;margin:3em 0}footer{border-top:1px solid #d9deea;margin-top:4em;padding-top:1.5em;color:#586174}
"""
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{escape(article.title)}</title><style>{styles}</style></head><body>{article_markup}</body></html>'


def render_plain(article: ExportArticle) -> str:
    lines = [article.title]
    if article.subtitle:
        lines.extend((article.subtitle, ""))
    for block in article.document["blocks"]:
        block_type = block["type"]
        if block_type in {"heading", "paragraph", "quote", "callout"}:
            lines.extend((inline_plain(block["content"]), ""))
        elif block_type in {"bulleted_list", "numbered_list"}:
            for index, item in enumerate(block["items"]):
                marker = f"{index + 1}." if block_type == "numbered_list" else "-"
                lines.append(f"{marker} {inline_plain(item)}")
            lines.append("")
        elif block_type in {"image", "visual"}:
            lines.extend((block.get("title") or block.get("caption") or block.get("alt") or "Visual", block.get("alt", ""), ""))
    if article.source_notes:
        lines.extend(("Source notes", article.source_notes, ""))
    if article.canonical_url:
        lines.append(f"Originally published at {article.canonical_url}")
    lines.append("Conceptually Football · conceptuallyfootball.com")
    return "\n".join(lines).strip() + "\n"


def render_markdown(article: ExportArticle, *, visual_url) -> str:
    lines = [f"# {article.title}", ""]
    if article.subtitle:
        lines.extend((f"**{article.subtitle}**", ""))
    lines.extend((f"By {article.author}", ""))
    visual_index = 0
    for block in article.document["blocks"]:
        block_type = block["type"]
        if block_type == "heading":
            lines.extend((f'{"#" * block["level"]} {inline_markdown(block["content"])}', ""))
        elif block_type == "paragraph":
            lines.extend((inline_markdown(block["content"]), ""))
        elif block_type == "quote":
            lines.extend((f'> {inline_markdown(block["content"])}', ""))
        elif block_type == "callout":
            lines.extend((f'> **{block.get("tone", "note").title()}:** {inline_markdown(block["content"])}', ""))
        elif block_type in {"bulleted_list", "numbered_list"}:
            for index, item in enumerate(block["items"]):
                marker = f"{index + 1}." if block_type == "numbered_list" else "-"
                lines.append(f"{marker} {inline_markdown(item)}")
            lines.append("")
        elif block_type == "image":
            if block.get("url"):
                lines.extend((f'![{block.get("alt", "")}]({block["url"]})', block.get("caption", ""), ""))
            else:
                lines.extend((f'*{block.get("alt") or block.get("caption") or "Image unavailable"}*', ""))
        elif block_type == "visual":
            lines.extend((f'![{block.get("alt", "")}]({visual_url(visual_index, block)})',))
            if block.get("caption"):
                lines.append(block["caption"])
            lines.extend((f'Source: {block.get("source_note", "Conceptually Football")} · Data as of {block.get("data_as_of", "")}', ""))
            visual_index += 1
        elif block_type == "divider":
            lines.extend(("---", ""))
    if article.source_notes:
        lines.extend(("## Source notes", "", article.source_notes, ""))
    if article.canonical_url:
        lines.extend((f"Originally published by [Conceptually Football]({article.canonical_url}).", ""))
    lines.append("Conceptually Football · conceptuallyfootball.com")
    return "\n".join(lines).strip() + "\n"


def pdf_escape(value: str) -> str:
    return value.encode("cp1252", errors="replace").decode("cp1252").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf_lines(article: ExportArticle) -> list[tuple[str, int, bool]]:
    values: list[tuple[str, int, bool]] = [(article.title, 22, True)]
    if article.subtitle:
        values.append((article.subtitle, 12, False))
    values.extend(((f"By {article.author}", 9, False), ("", 10, False)))
    for block in article.document["blocks"]:
        block_type = block["type"]
        if block_type in {"heading", "paragraph", "quote", "callout"}:
            size = 16 if block_type == "heading" else 10
            prefix = "Quote: " if block_type == "quote" else f'{block.get("tone", "").title()}: ' if block_type == "callout" else ""
            values.append((prefix + inline_plain(block["content"]), size, block_type == "heading"))
        elif block_type in {"bulleted_list", "numbered_list"}:
            for index, item in enumerate(block["items"]):
                marker = f"{index + 1}. " if block_type == "numbered_list" else "- "
                values.append((marker + inline_plain(item), 10, False))
        elif block_type in {"image", "visual"}:
            title = visual_title(block) if block_type == "visual" else block.get("caption") or "Article image"
            values.extend(((f"[VISUAL] {title}", 12, True), (block.get("alt") or block.get("caption") or "Image unavailable", 9, False)))
            if block_type == "visual":
                values.append((f'Source: {block.get("source_note", "Conceptually Football")} · Data as of {block.get("data_as_of", "")}', 8, False))
        elif block_type == "divider":
            values.append(("----------------------------------------", 8, False))
        values.append(("", 6, False))
    if article.source_notes:
        values.extend((("Source notes", 14, True), (article.source_notes, 9, False)))
    if article.canonical_url:
        values.append((f"Originally published: {article.canonical_url}", 8, False))
    return values


def render_pdf(
    article: ExportArticle,
    rendered_visuals: dict[str, RenderedVisual] | None = None,
) -> bytes:
    page_width, page_height = 595, 842
    margin, y_start, y_floor = 54, 780, 62
    text_pages: list[list[tuple[str, int, bool]]] = [[]]
    y = y_start
    for value, size, bold in pdf_lines(article):
        width = max(28, int(92 * 10 / max(size, 8)))
        wrapped = textwrap.wrap(value, width=width, break_long_words=False, replace_whitespace=False) or [""]
        for line in wrapped:
            leading = max(12, int(size * 1.45))
            if y - leading < y_floor:
                text_pages.append([])
                y = y_start
            text_pages[-1].append((line, size, bold))
            y -= leading

    rendered_visuals = rendered_visuals or {}
    visual_pages = [
        (block, rendered_visuals[block["id"]])
        for block in article.document["blocks"]
        if block["type"] == "visual"
        and block["id"] in rendered_visuals
        and rendered_visuals[block["id"]].content_type == "image/jpeg"
    ]
    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    image_ids = {block["id"]: 5 + index for index, (block, asset) in enumerate(visual_pages)}
    page_start = 5 + len(visual_pages)
    page_count = len(text_pages) + len(visual_pages)
    page_ids = [page_start + index * 2 for index in range(page_count)]
    objects.append(f'<< /Type /Pages /Kids [{" ".join(f"{page_id} 0 R" for page_id in page_ids)}] /Count {len(page_ids)} >>'.encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    for block, asset in visual_pages:
        objects.append(
            (
                f"<< /Type /XObject /Subtype /Image /Width {asset.width} /Height {asset.height} "
                f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(asset.data)} >>\nstream\n"
            ).encode()
            + asset.data
            + b"\nendstream"
        )

    for page_number, lines in enumerate(text_pages, start=1):
        content = ["q", "0.08 0.10 0.15 rg", "54 814 487 2 re f", "Q"]
        y = y_start
        for line, size, bold in lines:
            leading = max(12, int(size * 1.45))
            font = "F2" if bold else "F1"
            color = "0.08 0.10 0.15" if bold else "0.20 0.23 0.30"
            content.append(f"BT /{font} {size} Tf {color} rg {margin} {y} Td ({pdf_escape(line)}) Tj ET")
            y -= leading
        footer = f"Conceptually Football · conceptuallyfootball.com · {page_number}/{page_count}"
        content.append(f"BT /F1 7 Tf 0.30 0.40 0.60 rg 54 34 Td ({pdf_escape(footer)}) Tj ET")
        stream = "\n".join(content).encode("cp1252", errors="replace")
        content_id = page_ids[page_number - 1] + 1
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_id} 0 R >>".encode())
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")

    for visual_index, (block, asset) in enumerate(visual_pages):
        page_number = len(text_pages) + visual_index + 1
        image_name = f"Im{visual_index + 1}"
        image_id = image_ids[block["id"]]
        display_width = 487
        display_height = min(520, display_width * asset.height / asset.width)
        image_y = 736 - display_height
        content = [
            "q",
            "0.08 0.10 0.15 rg",
            "54 814 487 2 re f",
            "Q",
            f"BT /F2 15 Tf 0.08 0.10 0.15 rg 54 780 Td ({pdf_escape(visual_title(block))}) Tj ET",
            f"q {display_width:.2f} 0 0 {display_height:.2f} 54 {image_y:.2f} cm /{image_name} Do Q",
        ]
        detail_y = image_y - 24
        for value, size in (
            (block.get("caption", ""), 9),
            (f'Source: {block.get("source_note", "Conceptually Football")} · Data as of {block.get("data_as_of", "")}', 8),
            (block.get("alt", ""), 8),
        ):
            for line in textwrap.wrap(value, width=104, break_long_words=False)[:3]:
                content.append(f"BT /F1 {size} Tf 0.25 0.29 0.38 rg 54 {detail_y:.2f} Td ({pdf_escape(line)}) Tj ET")
                detail_y -= max(12, int(size * 1.45))
        footer = f"Conceptually Football · conceptuallyfootball.com · {page_number}/{page_count}"
        content.append(f"BT /F1 7 Tf 0.30 0.40 0.60 rg 54 34 Td ({pdf_escape(footer)}) Tj ET")
        stream = "\n".join(content).encode("cp1252", errors="replace")
        page_id = page_ids[page_number - 1]
        content_id = page_id + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> /XObject << /{image_name} {image_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode()
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")

    output = io.BytesIO()
    output.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, value in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{object_id} 0 obj\n".encode())
        output.write(value)
        output.write(b"\nendobj\n")
    xref = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return output.getvalue()


def private_response(content: bytes | str, *, content_type: str, file_name: str) -> HttpResponse:
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{file_name}"'
    response["Cache-Control"] = "private, no-store"
    response["Vary"] = "Cookie"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def bundled_export(
    article: ExportArticle,
    export_format: str,
    rendered_visuals: dict[str, RenderedVisual] | None = None,
) -> bytes:
    stream = io.BytesIO()
    warnings = export_warnings(article)
    visuals = [block for block in article.document["blocks"] if block["type"] == "visual"]
    rendered_visuals = rendered_visuals or {}
    asset_names = {}
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, block in enumerate(visuals):
            rendered = rendered_visuals.get(block["id"])
            extension = rendered.extension if rendered else "svg"
            asset_name = visual_asset_name(index, block, extension)
            asset_names[block["id"]] = asset_name
            archive.writestr(f"assets/{asset_name}", rendered.data if rendered else visual_svg(block))
            if not rendered:
                warnings.append(f"Visual {index + 1} used the accessible fallback because no rendered image was supplied.")

        def resolver(index, block):
            return f"assets/{asset_names[block['id']]}"

        if export_format == "html":
            archive.writestr("article.html", render_html(article, visual_url=resolver))
        else:
            archive.writestr("article.md", render_markdown(article, visual_url=resolver))
        archive.writestr(
            "export-manifest.json",
            json.dumps(
                {
                    "title": article.title,
                    "format": export_format,
                    "exported_at": timezone.now().isoformat(),
                    "warnings": warnings,
                    "visual_assets": len(visuals),
                    "rendered_visual_assets": len(rendered_visuals),
                },
                indent=2,
            ),
        )
    return stream.getvalue()


@require_http_methods(["GET", "POST"])
@never_cache
def article_export(request: HttpRequest, article_id, export_format: str) -> HttpResponse:
    error = editorial_error(request)
    if error is not None:
        return error
    article = export_article(visible_article(request, article_id))
    slug = article_file_slug(article.title)
    try:
        rendered_visuals = rendered_visuals_from_request(request, article)
    except ValueError as error:
        return JsonResponse({"detail": str(error)}, status=400)
    if request.method == "POST" and export_format == "substack":
        return JsonResponse({"detail": "Substack copy is available as a browser clipboard action."}, status=405)
    if request.method == "POST" and export_format in {"html", "markdown", "pdf"}:
        visual_count = sum(block["type"] == "visual" for block in article.document["blocks"])
        if len(rendered_visuals) != visual_count:
            return JsonResponse(
                {"detail": "Every visual must be rendered before this export can be downloaded."},
                status=400,
            )
        required_content_type = "image/jpeg" if export_format == "pdf" else "image/png"
        if any(asset.content_type != required_content_type for asset in rendered_visuals.values()):
            return JsonResponse(
                {"detail": f"Rendered visuals for {export_format.upper()} use an unsupported image format."},
                status=400,
            )
    if export_format in {"html", "markdown"}:
        return private_response(
            bundled_export(article, export_format, rendered_visuals),
            content_type="application/zip",
            file_name=f"{slug}-{export_format}.zip",
        )
    if export_format == "pdf":
        return private_response(
            render_pdf(article, rendered_visuals),
            content_type="application/pdf",
            file_name=f"{slug}.pdf",
        )
    if export_format == "substack":
        def public_visual_url(index, block):
            if not article.is_public or not article.slug:
                return ""
            path = f"/api/v1/analysis/articles/{quote(article.slug)}/visuals/{quote(block['id'])}.svg"
            return f"{PUBLIC_SITE_URL}{path}"

        response = JsonResponse(
            {
                "html": render_html(article, visual_url=public_visual_url, substack=True),
                "text": render_plain(article),
                "is_public": article.is_public,
                "canonical_url": article.canonical_url,
                "warnings": export_warnings(article),
                "visuals": [
                    {
                        "block_id": block["id"],
                        "title": visual_title(block),
                        "alt": block.get("alt", ""),
                    }
                    for block in article.document["blocks"]
                    if block["type"] == "visual"
                ],
            }
        )
        response["Cache-Control"] = "private, no-store"
        response["Vary"] = "Cookie"
        return response
    raise Http404("Export format not found.")


def current_publication(slug: str) -> ArticlePublication:
    publication = (
        ArticlePublication.objects.select_related("article", "article__author")
        .filter(
            article__slug=slug,
            article__status=ArticleStatus.PUBLISHED,
            unpublished_at__isnull=True,
        )
        .order_by("-version")
        .first()
    )
    if publication is None:
        raise Http404("Published article not found.")
    return publication


@require_GET
def public_visual_asset(request: HttpRequest, slug: str, block_id, extension: str) -> HttpResponse:
    if extension != "svg":
        raise Http404("Visual format not found.")
    publication = current_publication(slug)
    document = normalize_document(publication.document)
    block = next((item for item in document["blocks"] if item["type"] == "visual" and item["id"] == str(block_id)), None)
    if block is None:
        raise Http404("Visual not found.")
    response = HttpResponse(visual_svg(block), content_type="image/svg+xml")
    response["Cache-Control"] = "public, max-age=300, stale-while-revalidate=3600"
    response["Content-Disposition"] = f'inline; filename="{visual_asset_name(0, block)}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


def cdata(value: str) -> str:
    return value.replace("]]>", "]]]]><![CDATA[>")


@require_GET
def public_analysis_feed(request: HttpRequest) -> HttpResponse:
    publications = ArticlePublication.objects.select_related("article", "article__author").filter(
        article__status=ArticleStatus.PUBLISHED,
        article__slug__isnull=False,
        unpublished_at__isnull=True,
    ).order_by("-published_at", "-id")
    items = []
    seen_articles = set()
    newest_publication = None
    for publication in publications:
        if publication.article_id in seen_articles:
            continue
        seen_articles.add(publication.article_id)
        newest_publication = newest_publication or publication
        article = export_article(publication.article)
        canonical = article.canonical_url or ""

        def visual_url(index, block):
            path = f"/api/v1/analysis/articles/{quote(article.slug or '')}/visuals/{quote(block['id'])}.svg"
            return f"{PUBLIC_SITE_URL}{path}"

        content = render_html(article, visual_url=visual_url, substack=True)
        items.append(
            "<item>"
            f"<title>{xml_escape(article.title)}</title>"
            f"<link>{xml_escape(canonical)}</link>"
            f'<guid isPermaLink="true">{xml_escape(canonical)}</guid>'
            f"<dc:creator>{xml_escape(article.author)}</dc:creator>"
            f"<pubDate>{format_datetime(publication.published_at)}</pubDate>"
            f"<description><![CDATA[{cdata(article.subtitle)}]]></description>"
            f"<content:encoded><![CDATA[{cdata(content)}]]></content:encoded>"
            "</item>"
        )
    last_build = newest_publication.published_at if newest_publication else timezone.now()
    feed_url = f"{PUBLIC_SITE_URL}{request.path}"
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:atom="http://www.w3.org/2005/Atom">'
        "<channel>"
        "<title>Conceptually Football Analysis</title>"
        f"<link>{xml_escape(f'{PUBLIC_SITE_URL}/analysis')}</link>"
        "<description>Football analysis and editorial from Conceptually Football.</description>"
        '<language>en-gb</language>'
        f'<atom:link href="{xml_escape(feed_url)}" rel="self" type="application/rss+xml"/>'
        f"<lastBuildDate>{format_datetime(last_build)}</lastBuildDate>"
        f'{"".join(items)}'
        "</channel></rss>"
    )
    response = HttpResponse(xml, content_type="application/rss+xml; charset=utf-8")
    response["Cache-Control"] = "public, max-age=300, stale-while-revalidate=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response
