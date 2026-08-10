from __future__ import annotations

import json

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import StaffAccess, StaffRole
from accounts.roles import configure_user_role
from editorial.models import Article, ArticleRevision


class EditorialApiTests(TestCase):
    def setUp(self):
        self.writer = self.create_writer("writer@example.com")
        self.other_writer = self.create_writer("other@example.com")
        self.client.force_login(self.writer)

    def create_writer(self, email: str):
        user = User.objects.create_user(username=email, email=email, password="Touchline-Notebook-2026!")
        StaffAccess.objects.create(user=user, role=StaffRole.WRITER, must_change_password=False)
        configure_user_role(user, StaffRole.WRITER)
        return User.objects.get(pk=user.pk)

    def create_article(self) -> dict:
        response = self.client.post(
            reverse("editorial-articles"),
            data=json.dumps({"title": "The spare midfielder"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["article"]

    def patch_article(self, article_id: str, payload: dict):
        return self.client.patch(
            reverse("editorial-article-detail", kwargs={"article_id": article_id}),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_writer_can_create_save_reopen_and_filter_own_draft(self):
        created = self.create_article()
        response = self.patch_article(
            created["id"],
            {
                "revision": created["revision"],
                "title": "The spare midfielder",
                "subtitle": "How a small rotation opens the pitch.",
                "document": {
                    "version": 1,
                    "blocks": [
                        {"id": "not-a-uuid", "type": "heading", "level": 2, "text": "The rotation"},
                        {"id": "also-not-a-uuid", "type": "paragraph", "text": "The winger stays wide."},
                    ],
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        saved = response.json()["article"]
        self.assertEqual(saved["revision"], 2)
        self.assertEqual(saved["document"]["blocks"][0]["type"], "heading")
        self.assertEqual(ArticleRevision.objects.filter(article_id=created["id"]).count(), 2)

        reopened = self.client.get(
            reverse("editorial-article-detail", kwargs={"article_id": created["id"]})
        )
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.json()["article"]["subtitle"], "How a small rotation opens the pitch.")
        listed = self.client.get(reverse("editorial-articles"), {"q": "midfielder"})
        self.assertEqual([item["id"] for item in listed.json()["articles"]], [created["id"]])

    def test_stale_revision_cannot_overwrite_a_newer_save(self):
        created = self.create_article()
        document = created["document"]
        first = self.patch_article(
            created["id"],
            {"revision": 1, "title": "First tab", "subtitle": "", "document": document},
        )
        self.assertEqual(first.status_code, 200)

        stale = self.patch_article(
            created["id"],
            {"revision": 1, "title": "Second tab", "subtitle": "", "document": document},
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["code"], "revision_conflict")
        self.assertEqual(stale.json()["article"]["title"], "First tab")

    def test_other_writer_cannot_read_change_or_delete_draft(self):
        created = self.create_article()
        other_client = Client()
        other_client.force_login(self.other_writer)
        detail_url = reverse("editorial-article-detail", kwargs={"article_id": created["id"]})

        self.assertEqual(other_client.get(detail_url).status_code, 404)
        self.assertEqual(
            other_client.patch(
                detail_url,
                data=json.dumps({"revision": 1, "title": "Taken", "document": created["document"]}),
                content_type="application/json",
            ).status_code,
            404,
        )
        self.assertEqual(other_client.delete(detail_url).status_code, 404)
        self.assertTrue(Article.objects.filter(id=created["id"], author=self.writer).exists())

    def test_writer_can_delete_own_draft_and_revision_history(self):
        created = self.create_article()
        detail_url = reverse("editorial-article-detail", kwargs={"article_id": created["id"]})

        response = self.client.delete(detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Article.objects.filter(id=created["id"]).exists())
        self.assertFalse(ArticleRevision.objects.filter(article_id=created["id"]).exists())

    def test_preview_link_is_private_revocable_and_not_indexable(self):
        created = self.create_article()
        article = Article.objects.get(id=created["id"])
        preview_url = reverse("editorial-shared-preview", kwargs={"token": article.preview_token})
        anonymous = Client()
        self.assertEqual(anonymous.get(preview_url).status_code, 404)

        enabled = self.client.post(
            reverse("editorial-article-preview", kwargs={"article_id": created["id"]}),
            data=json.dumps({"enabled": True}),
            content_type="application/json",
        )
        self.assertEqual(enabled.status_code, 200)
        active_token = enabled.json()["article"]["preview_token"]
        preview_url = reverse("editorial-shared-preview", kwargs={"token": active_token})
        shared = anonymous.get(preview_url)
        self.assertEqual(shared.status_code, 200)
        self.assertIn("private", shared["Cache-Control"])
        self.assertIn("no-store", shared["Cache-Control"])
        self.assertEqual(shared["X-Robots-Tag"], "noindex, nofollow, noarchive")
        self.assertNotIn("preview_token", shared.json()["article"])

        disabled = self.client.post(
            reverse("editorial-article-preview", kwargs={"article_id": created["id"]}),
            data=json.dumps({"enabled": False}),
            content_type="application/json",
        )
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(anonymous.get(preview_url).status_code, 404)

        reenabled = self.client.post(
            reverse("editorial-article-preview", kwargs={"article_id": created["id"]}),
            data=json.dumps({"enabled": True}),
            content_type="application/json",
        )
        self.assertEqual(reenabled.status_code, 200)
        self.assertNotEqual(reenabled.json()["article"]["preview_token"], active_token)
        self.assertEqual(anonymous.get(preview_url).status_code, 404)

    def test_structured_content_rejects_unsafe_urls_and_unknown_blocks(self):
        created = self.create_article()
        unsafe = self.patch_article(
            created["id"],
            {
                "revision": 1,
                "title": "Unsafe",
                "subtitle": "",
                "document": {
                    "version": 1,
                    "blocks": [{"id": "x", "type": "link", "text": "Run", "url": "javascript:alert(1)"}],
                },
            },
        )
        self.assertEqual(unsafe.status_code, 400)

        unknown = self.patch_article(
            created["id"],
            {
                "revision": 1,
                "title": "Unsafe",
                "subtitle": "",
                "document": {"version": 1, "blocks": [{"id": "x", "type": "raw_html", "html": "<script>alert(1)</script>"}]},
            },
        )
        self.assertEqual(unknown.status_code, 400)
        article = Article.objects.get(id=created["id"])
        self.assertEqual(article.revision, 1)

    def test_unauthenticated_requests_cannot_access_drafts(self):
        anonymous = Client()
        response = anonymous.get(reverse("editorial-articles"))
        self.assertEqual(response.status_code, 401)

    def test_editorial_writes_require_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.writer)

        response = csrf_client.post(
            reverse("editorial-articles"),
            data=json.dumps({"title": "No token"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
