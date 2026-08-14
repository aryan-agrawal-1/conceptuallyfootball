from __future__ import annotations

import io
import json
import uuid
import zipfile

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import StaffAccess, StaffRole, WriterProfile
from accounts.roles import configure_user_role
from editorial.models import Article, ArticlePublication, ArticleStatus


PNG_DATA_URL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
JPEG_DATA_URL = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAASABIAAD/4QCARXhpZgAATU0AKgAAAAgABAEaAAUAAAABAAAAPgEbAAUAAAABAAAARgEoAAMAAAABAAIAAIdpAAQAAAABAAAATgAAAAAAAABIAAAAAQAAAEgAAAABAAOgAQADAAAAAQABAACgAgAEAAAAAQAAAAKgAwAEAAAAAQAAAAIAAAAA/+0AOFBob3Rvc2hvcCAzLjAAOEJJTQQEAAAAAAAAOEJJTQQlAAAAAAAQ1B2M2Y8AsgTpgAmY7PhCfv/AABEIAAIAAgMBIgACEQEDEQH/xAAfAAABBQEBAQEBAQAAAAAAAAAAAQIDBAUGBwgJCgv/xAC1EAACAQMDAgQDBQUEBAAAAX0BAgMABBEFEiExQQYTUWEHInEUMoGRoQgjQrHBFVLR8CQzYnKCCQoWFxgZGiUmJygpKjQ1Njc4OTpDREVGR0hJSlNUVVZXWFlaY2RlZmdoaWpzdHV2d3h5eoOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4eLj5OXm5+jp6vHy8/T19vf4+fr/xAAfAQADAQEBAQEBAQEBAAAAAAAAAQIDBAUGBwgJCgv/xAC1EQACAQIEBAMEBwUEBAABAncAAQIDEQQFITEGEkFRB2FxEyIygQgUQpGhscEJIzNS8BVictEKFiQ04SXxFxgZGiYnKCkqNTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqCg4SFhoeIiYqSk5SVlpeYmZqio6Slpqeoqaqys7S1tre4ubrCw8TFxsfIycrS09TV1tfY2dri4+Tl5ufo6ery8/T19vf4+fr/2wBDAAICAgICAgMCAgMFAwMDBQYFBQUFBggGBgYGBggKCAgICAgICgoKCgoKCgoMDAwMDAwODg4ODg8PDw8PDw8PDw//2wBDAQICAgQEBAcEBAcQCwkLEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBD/3QAEAAH/2gAMAwEAAhEDEQA/AP22Hhzw9j/kF2v/AH4T/Cl/4Rzw9/0C7X/vwn+FbI6UV4594f/Z"


class EditorialExportTests(TestCase):
    def setUp(self):
        self.writer = self.create_writer("writer@example.com")
        self.other_writer = self.create_writer("other@example.com")
        self.client.force_login(self.writer)

    def create_writer(self, email: str):
        user = User.objects.create_user(username=email, email=email, password="Touchline-Notebook-2026!")
        StaffAccess.objects.create(user=user, role=StaffRole.WRITER, must_change_password=False)
        configure_user_role(user, StaffRole.WRITER)
        WriterProfile.objects.create(
            user=user,
            display_name=email.split("@")[0].title(),
            completed_at=timezone.now(),
        )
        return User.objects.get(pk=user.pk)

    def document(self, *, paragraph: str = "A patient overload creates the chance."):
        visual_id = str(uuid.uuid4())
        return {
            "version": 1,
            "blocks": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "heading",
                    "level": 2,
                    "content": [{"text": "The decisive rotation"}],
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "paragraph",
                    "content": [
                        {"text": paragraph},
                        {"text": " Read the source.", "link": "https://example.com/source"},
                    ],
                },
                {
                    "id": visual_id,
                    "type": "visual",
                    "visual_type": "player_radar",
                    "title": "Midfielder percentile profile",
                    "caption": "Progression and creation stand out.",
                    "alt": "The player ranks highly for progressive passing and chance creation.",
                    "source_note": "Conceptually Football model; StatsBomb event data",
                    "data_as_of": "2026-08-14",
                    "update_policy": "frozen",
                    "config": {
                        "entity_kind": "player",
                        "entities": [
                            {
                                "kind": "player",
                                "id": 42,
                                "name": "Example Midfielder",
                                "source_competition": "ENG1",
                                "season_label": "2025/26",
                                "competition_season_id": 9,
                                "position_group": "MID",
                                "team_name": "Example FC",
                            }
                        ],
                        "context": {
                            "scope_kind": "league",
                            "scope_code": "ENG1",
                            "scope_label": "Premier League",
                            "season_label": "2025/26",
                        },
                        "chart_type": "radar",
                        "metric_keys": ["progressive_passes", "key_passes", "passes_into_box"],
                        "rate_mode": "per90",
                        "filters": {
                            "position_group": "MID",
                            "team_names": [],
                            "minimum_minutes": 450,
                            "labels": True,
                            "trendline": False,
                            "bar_window": "top",
                            "bar_count": 12,
                        },
                    },
                },
            ],
        }, visual_id

    def create_article(self, *, author=None, published=False, paragraph="A patient overload creates the chance."):
        document, visual_id = self.document(paragraph=paragraph)
        article = Article.objects.create(
            author=author or self.writer,
            title="Why the spare midfielder matters",
            subtitle="A structural explanation.",
            document=document,
            source_notes="Data checked against the match footage.",
            topics=["Tactics"],
            preview_enabled=True,
        )
        if published:
            article.status = ArticleStatus.PUBLISHED
            article.slug = "why-the-spare-midfielder-matters"
            article.published_at = timezone.now()
            article.save(update_fields=("status", "slug", "published_at"))
            ArticlePublication.objects.create(
                article=article,
                version=1,
                revision=article.revision,
                title=article.title,
                subtitle=article.subtitle,
                document=document,
                topics=article.topics,
                source_notes=article.source_notes,
                published_by=self.writer,
                published_at=article.published_at,
            )
        return article, visual_id

    def export_url(self, article, export_format):
        return reverse(
            "editorial-article-export",
            kwargs={"article_id": article.id, "export_format": export_format},
        )

    def test_writer_can_download_semantic_html_and_markdown_bundles_with_static_visuals(self):
        article, visual_id = self.create_article()

        html_response = self.client.get(self.export_url(article, "html"))
        markdown_response = self.client.get(self.export_url(article, "markdown"))

        self.assertEqual(html_response.status_code, 200)
        self.assertEqual(html_response["Content-Type"], "application/zip")
        self.assertIn("private", html_response["Cache-Control"])
        self.assertIn("no-store", html_response["Cache-Control"])
        with zipfile.ZipFile(io.BytesIO(html_response.content)) as archive:
            names = archive.namelist()
            html = archive.read("article.html").decode()
            manifest = json.loads(archive.read("export-manifest.json"))
            visual_name = next(name for name in names if name.endswith(".svg"))
            visual = archive.read(visual_name).decode()
        self.assertIn("<h2>The decisive rotation</h2>", html)
        self.assertIn("assets/visual-01", html)
        self.assertIn("conceptuallyfootball.com", visual)
        self.assertIn("progressive passing", visual.lower())
        self.assertEqual(manifest["visual_assets"], 1)
        self.assertNotIn(str(article.preview_token), html_response.content.decode("latin1"))

        self.assertEqual(markdown_response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(markdown_response.content)) as archive:
            markdown = archive.read("article.md").decode()
        self.assertIn("## The decisive rotation", markdown)
        self.assertIn("Source: Conceptually Football model", markdown)
        self.assertNotIn(str(article.preview_token), markdown)
        self.assertIn(visual_id, json.dumps(article.document))

    def test_pdf_is_private_readable_and_contains_attribution_without_secrets(self):
        article, _ = self.create_article()

        response = self.client.get(self.export_url(article, "pdf"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-1.4"))
        self.assertIn(b"Conceptually Football", response.content)
        self.assertIn(b"[VISUAL] Midfielder percentile profile", response.content)
        self.assertNotIn(str(article.preview_token).encode(), response.content)

    def test_browser_rendered_visuals_are_embedded_in_downloaded_exports(self):
        article, visual_id = self.create_article()

        html_response = self.client.post(
            self.export_url(article, "html"),
            data=json.dumps({"visuals": [{"block_id": visual_id, "data_url": PNG_DATA_URL}]}),
            content_type="application/json",
        )
        markdown_response = self.client.post(
            self.export_url(article, "markdown"),
            data=json.dumps({"visuals": [{"block_id": visual_id, "data_url": PNG_DATA_URL}]}),
            content_type="application/json",
        )
        pdf_response = self.client.post(
            self.export_url(article, "pdf"),
            data=json.dumps({"visuals": [{"block_id": visual_id, "data_url": JPEG_DATA_URL}]}),
            content_type="application/json",
        )

        self.assertEqual(html_response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(html_response.content)) as archive:
            html = archive.read("article.html").decode()
            manifest = json.loads(archive.read("export-manifest.json"))
            visual_name = next(name for name in archive.namelist() if name.endswith(".png"))
            visual = archive.read(visual_name)
        self.assertIn("assets/visual-01", html)
        self.assertIn(".png", html)
        self.assertTrue(visual.startswith(b"\x89PNG"))
        self.assertEqual(manifest["rendered_visual_assets"], 1)

        self.assertEqual(markdown_response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(markdown_response.content)) as archive:
            markdown = archive.read("article.md").decode()
            self.assertTrue(any(name.endswith(".png") for name in archive.namelist()))
        self.assertIn(".png)", markdown)

        self.assertEqual(pdf_response.status_code, 200)
        self.assertIn(b"/Subtype /Image", pdf_response.content)
        self.assertIn(b"/DCTDecode", pdf_response.content)

    def test_substack_payload_uses_rich_and_plain_formats_without_publishing_draft_assets(self):
        article, visual_id = self.create_article()

        response = self.client.get(self.export_url(article, "substack"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["is_public"])
        self.assertIsNone(payload["canonical_url"])
        self.assertIn('data-visual-block-id=', payload["html"])
        self.assertNotIn("/visuals/", payload["html"])
        self.assertNotIn(str(article.preview_token), json.dumps(payload))
        self.assertEqual(payload["visuals"][0]["block_id"], visual_id)
        self.assertIn("Why the spare midfielder matters", payload["text"])

    def test_published_exports_use_the_immutable_publication_snapshot(self):
        article, _ = self.create_article(published=True, paragraph="Published snapshot text.")
        article.document, _ = self.document(paragraph="Unpublished later edit.")
        article.save(update_fields=("document",))

        response = self.client.get(self.export_url(article, "substack"))

        self.assertTrue(response.json()["is_public"])
        self.assertIn("Published snapshot text.", response.json()["html"])
        self.assertNotIn("Unpublished later edit.", response.json()["html"])
        self.assertIn("Originally published", response.json()["html"])

    def test_public_feed_and_visual_assets_only_expose_active_publications(self):
        published, visual_id = self.create_article(published=True, paragraph="Full feed content.")
        draft, _ = self.create_article(paragraph="Private draft sentence.")

        feed = self.client.get(reverse("editorial-public-feed"))
        visual = self.client.get(
            reverse(
                "editorial-public-visual-asset",
                kwargs={
                    "slug": published.slug,
                    "block_id": visual_id,
                    "extension": "svg",
                },
            )
        )

        self.assertEqual(feed.status_code, 200)
        self.assertIn("application/rss+xml", feed["Content-Type"])
        content = feed.content.decode()
        self.assertIn("Full feed content.", content)
        self.assertIn("content:encoded", content)
        self.assertIn("<guid isPermaLink=\"true\">", content)
        self.assertIn(f"/visuals/{visual_id}.svg", content)
        self.assertIn(
            f"https://www.conceptuallyfootball.com/api/v1/analysis/articles/{published.slug}/visuals/{visual_id}.svg",
            content,
        )
        self.assertNotIn("Private draft sentence.", content)
        self.assertNotIn(str(draft.preview_token), content)
        self.assertEqual(visual.status_code, 200)
        self.assertEqual(visual["Content-Type"], "image/svg+xml")
        self.assertIn(b"The player ranks highly", visual.content)

        published.status = ArticleStatus.APPROVED
        published.save(update_fields=("status",))
        self.assertEqual(self.client.get(feed.wsgi_request.path).status_code, 200)
        self.assertNotIn("Full feed content.", self.client.get(feed.wsgi_request.path).content.decode())
        self.assertEqual(
            self.client.get(
                reverse(
                    "editorial-public-visual-asset",
                    kwargs={"slug": published.slug, "block_id": visual_id, "extension": "svg"},
                )
            ).status_code,
            404,
        )

    def test_exports_require_authentication_and_article_visibility(self):
        article, _ = self.create_article(author=self.other_writer)
        self.assertEqual(self.client.get(self.export_url(article, "pdf")).status_code, 404)
        anonymous = Client()
        self.assertEqual(anonymous.get(self.export_url(article, "pdf")).status_code, 401)
