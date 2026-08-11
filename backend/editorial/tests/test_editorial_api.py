from __future__ import annotations

import json

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import StaffAccess, StaffRole, WriterProfile
from accounts.roles import configure_user_role
from editorial.models import (
    Article,
    ArticlePlayerReference,
    ArticlePlayerSubject,
    ArticleRevision,
    ArticleTeamReference,
    ArticleTeamSubject,
)
from ingestion.models import CanonicalPlayer, CanonicalTeam


class EditorialApiTests(TestCase):
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
                "create_revision": True,
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
        self.assertEqual(saved["document"]["blocks"][0]["content"], [{"text": "The rotation"}])
        self.assertEqual(ArticleRevision.objects.filter(article_id=created["id"]).count(), 2)

        reopened = self.client.get(
            reverse("editorial-article-detail", kwargs={"article_id": created["id"]})
        )
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.json()["article"]["subtitle"], "How a small rotation opens the pitch.")
        listed = self.client.get(reverse("editorial-articles"), {"q": "midfielder"})
        self.assertEqual([item["id"] for item in listed.json()["articles"]], [created["id"]])

    def test_autosave_updates_the_live_draft_without_creating_a_revision_until_checkpoint(self):
        created = self.create_article()
        document = {
            "version": 1,
            "blocks": [{"id": "draft", "type": "paragraph", "content": [{"text": "Autosaved"}]}],
        }

        autosaved = self.patch_article(
            created["id"],
            {"revision": 1, "title": "Live draft", "subtitle": "", "document": document},
        )

        self.assertEqual(autosaved.status_code, 200)
        self.assertEqual(autosaved.json()["article"]["revision"], 2)
        self.assertEqual(ArticleRevision.objects.filter(article_id=created["id"]).count(), 1)
        saved_document = autosaved.json()["article"]["document"]

        checkpoint = self.patch_article(
            created["id"],
            {
                "revision": 2,
                "title": "Live draft",
                "subtitle": "",
                "document": saved_document,
                "create_revision": True,
            },
        )

        self.assertEqual(checkpoint.status_code, 200)
        self.assertEqual(checkpoint.json()["article"]["revision"], 2)
        self.assertEqual(
            list(ArticleRevision.objects.filter(article_id=created["id"]).values_list("number", flat=True)),
            [2, 1],
        )

        repeated = self.patch_article(
            created["id"],
            {
                "revision": 2,
                "title": "Live draft",
                "subtitle": "",
                "document": saved_document,
                "create_revision": True,
            },
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(ArticleRevision.objects.filter(article_id=created["id"]).count(), 2)

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

    def test_writer_can_open_and_restore_an_owned_revision_without_losing_newer_history(self):
        created = self.create_article()
        first_document = created["document"]
        first_revision = self.client.get(
            reverse(
                "editorial-article-revision-detail",
                kwargs={"article_id": created["id"], "revision_number": 1},
            )
        )

        self.assertEqual(first_revision.status_code, 200)
        snapshot = first_revision.json()["revision"]
        self.assertEqual(snapshot["title"], "The spare midfielder")
        self.assertEqual(snapshot["document"], first_document)

        changed = self.patch_article(
            created["id"],
            {
                "revision": 1,
                "title": "A newer direction",
                "subtitle": "Keep this version in the trail.",
                "document": first_document,
                "create_revision": True,
            },
        ).json()["article"]
        restored = self.patch_article(
            created["id"],
            {
                "revision": changed["revision"],
                "title": snapshot["title"],
                "subtitle": snapshot["subtitle"],
                "document": snapshot["document"],
                "create_revision": True,
            },
        )

        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["article"]["title"], "The spare midfielder")
        self.assertEqual(
            list(ArticleRevision.objects.filter(article_id=created["id"]).values_list("number", flat=True)),
            [3, 2, 1],
        )

        other_client = Client()
        other_client.force_login(self.other_writer)
        self.assertEqual(
            other_client.get(
                reverse(
                    "editorial-article-revision-detail",
                    kwargs={"article_id": created["id"], "revision_number": 1},
                )
            ).status_code,
            404,
        )

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

    def test_inline_links_are_normalized_and_legacy_link_blocks_are_upgraded(self):
        created = self.create_article()
        response = self.patch_article(
            created["id"],
            {
                "revision": 1,
                "title": "Linked",
                "subtitle": "",
                "document": {
                    "version": 1,
                    "blocks": [
                        {
                            "id": "one",
                            "type": "paragraph",
                            "content": [
                                {"text": "Read "},
                                {"text": "the report", "link": "https://example.com/report"},
                                {"text": " next."},
                            ],
                        },
                        {"id": "two", "type": "link", "text": "Legacy source", "url": "https://example.com"},
                    ],
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        blocks = response.json()["article"]["document"]["blocks"]
        self.assertEqual(blocks[0]["content"][1]["link"], "https://example.com/report")
        self.assertEqual(blocks[1]["type"], "paragraph")
        self.assertEqual(blocks[1]["content"], [{"text": "Legacy source", "link": "https://example.com"}])

    def test_writer_assigns_separate_canonical_subjects_and_inline_references(self):
        subject_player = CanonicalPlayer.objects.create(display_name="Subject Player")
        referenced_player = CanonicalPlayer.objects.create(display_name="Referenced Player")
        subject_team = CanonicalTeam.objects.create(name="Subject FC")
        referenced_team = CanonicalTeam.objects.create(name="Referenced FC")
        created = self.create_article()

        response = self.patch_article(
            created["id"],
            {
                "revision": 1,
                "title": "Canonical relationships",
                "subtitle": "Subjects are not inferred from mentions.",
                "subjects": {
                    "players": [
                        {
                            "kind": "player",
                            "id": subject_player.id,
                            "name": "Ignored client name",
                            "context": {
                                "competition_code": "ENG1",
                                "season_label": "2025-26",
                            },
                        }
                    ],
                    "teams": [{"kind": "team", "id": subject_team.id, "name": "Subject FC"}],
                },
                "document": {
                    "version": 1,
                    "blocks": [
                        {
                            "id": "mentions",
                            "type": "paragraph",
                            "content": [
                                {"text": "Compare "},
                                {
                                    "text": "@Referenced Player",
                                    "reference": {
                                        "kind": "player",
                                        "id": referenced_player.id,
                                        "name": "Referenced Player",
                                    },
                                },
                                {"text": " with "},
                                {
                                    "text": "@Referenced FC",
                                    "reference": {
                                        "kind": "team",
                                        "id": referenced_team.id,
                                        "name": "Referenced FC",
                                    },
                                },
                                {"text": "."},
                            ],
                        }
                    ],
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        article = response.json()["article"]
        self.assertEqual(article["subjects"]["players"][0]["name"], "Subject Player")
        self.assertNotIn("context", article["subjects"]["players"][0])
        self.assertEqual(article["subjects"]["teams"][0]["id"], subject_team.id)
        self.assertEqual(article["references"]["players"][0]["id"], referenced_player.id)
        self.assertEqual(article["references"]["teams"][0]["id"], referenced_team.id)
        self.assertTrue(
            ArticlePlayerSubject.objects.filter(article_id=created["id"], player=subject_player).exists()
        )
        self.assertTrue(
            ArticleTeamSubject.objects.filter(article_id=created["id"], team=subject_team).exists()
        )
        self.assertTrue(
            ArticlePlayerReference.objects.filter(
                article_id=created["id"], player=referenced_player
            ).exists()
        )
        self.assertTrue(
            ArticleTeamReference.objects.filter(
                article_id=created["id"], team=referenced_team
            ).exists()
        )

    def test_subject_limits_and_reference_identity_are_enforced_server_side(self):
        players = [CanonicalPlayer.objects.create(display_name=f"Player {index}") for index in range(3)]
        created = self.create_article()
        too_many = self.patch_article(
            created["id"],
            {
                "revision": 1,
                "title": created["title"],
                "subtitle": "",
                "subjects": {
                    "players": [
                        {"kind": "player", "id": player.id, "name": player.display_name}
                        for player in players
                    ],
                    "teams": [],
                },
                "document": created["document"],
            },
        )
        self.assertEqual(too_many.status_code, 400)

        mismatched_reference = self.patch_article(
            created["id"],
            {
                "revision": 1,
                "title": created["title"],
                "subtitle": "",
                "document": {
                    "version": 1,
                    "blocks": [
                        {
                            "id": "mention",
                            "type": "paragraph",
                            "content": [
                                {
                                    "text": "@Wrong Name",
                                    "reference": {
                                        "kind": "player",
                                        "id": players[0].id,
                                        "name": "Wrong Name",
                                    },
                                }
                            ],
                        }
                    ],
                },
            },
        )
        self.assertEqual(mismatched_reference.status_code, 400)
        self.assertEqual(Article.objects.get(id=created["id"]).revision, 1)

    def test_related_analysis_separates_subject_articles_from_reference_only_articles(self):
        player = CanonicalPlayer.objects.create(display_name="The Playmaker")
        subject_article = self.create_article()
        subject_response = self.patch_article(
            subject_article["id"],
            {
                "revision": 1,
                "title": "Built around the playmaker",
                "subtitle": "",
                "subjects": {
                    "players": [{"kind": "player", "id": player.id, "name": player.display_name}],
                    "teams": [],
                },
                "document": {
                    "version": 1,
                    "blocks": [
                        {
                            "id": "subject-mention",
                            "type": "paragraph",
                            "content": [
                                {
                                    "text": "@The Playmaker",
                                    "reference": {"kind": "player", "id": player.id, "name": player.display_name},
                                }
                            ],
                        }
                    ],
                },
            },
        )
        reference_article = self.create_article()
        reference_response = self.patch_article(
            reference_article["id"],
            {
                "revision": 1,
                "title": "A passing comparison",
                "subtitle": "",
                "document": {
                    "version": 1,
                    "blocks": [
                        {
                            "id": "reference-only",
                            "type": "paragraph",
                            "content": [
                                {
                                    "text": "@The Playmaker",
                                    "reference": {"kind": "player", "id": player.id, "name": player.display_name},
                                }
                            ],
                        }
                    ],
                },
            },
        )
        self.assertEqual(subject_response.status_code, 200)
        self.assertEqual(reference_response.status_code, 200)
        private_response = Client().get(
            reverse("editorial-player-related-analysis", kwargs={"entity_id": player.id})
        )
        self.assertEqual(private_response.json()["subjects_of"], [])
        self.assertEqual(private_response.json()["referenced_by"], [])
        Article.objects.filter(id__in=[subject_article["id"], reference_article["id"]]).update(
            status="published"
        )

        response = Client().get(
            reverse("editorial-player-related-analysis", kwargs={"entity_id": player.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [article["title"] for article in response.json()["subjects_of"]],
            ["Built around the playmaker"],
        )
        self.assertEqual(
            [article["title"] for article in response.json()["referenced_by"]],
            ["A passing comparison"],
        )

    def test_structured_content_rejects_unsafe_inline_urls_and_unknown_blocks(self):
        created = self.create_article()
        unsafe = self.patch_article(
            created["id"],
            {
                "revision": 1,
                "title": "Unsafe",
                "subtitle": "",
                "document": {
                    "version": 1,
                    "blocks": [
                        {
                            "id": "x",
                            "type": "paragraph",
                            "content": [{"text": "Run", "link": "javascript:alert(1)"}],
                        }
                    ],
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

    def test_visual_blocks_preserve_canonical_context_accessibility_and_export_metadata(self):
        created = self.create_article()
        visual = {
            "id": "visual",
            "type": "visual",
            "visual_type": "custom_chart",
            "title": "Chance creation leaders",
            "caption": "The highlighted players combine volume and quality.",
            "alt": "Scatter chart comparing expected assists and key passes per 90.",
            "source_note": "Conceptually Football · Understat and Sofascore",
            "data_as_of": "2026-08-10",
            "update_policy": "live_draft_freeze_on_publish",
            "config": {
                "entity_kind": "player",
                "entities": [
                    {
                        "kind": "player",
                        "id": 42,
                        "name": "Example Player",
                        "source_competition": "eng1",
                        "season_label": "2025/26",
                        "competition_season_id": 12,
                        "position_group": "MID",
                        "team_name": "Example FC",
                    }
                ],
                "context": {
                    "scope_kind": "big5",
                    "scope_code": "big5",
                    "scope_label": "Big 5 leagues",
                    "season_label": "2025/26",
                },
                "chart_type": "scatter",
                "metric_keys": ["xA_per90", "key_passes_per90"],
                "rate_mode": "per90",
                "filters": {
                    "position_group": "MID",
                    "team_names": [],
                    "minimum_minutes": 900,
                },
            },
        }

        response = self.patch_article(
            created["id"],
            {
                "revision": 1,
                "title": "Visual analysis",
                "subtitle": "",
                "document": {"version": 1, "blocks": [visual]},
            },
        )

        self.assertEqual(response.status_code, 200)
        saved = response.json()["article"]["document"]["blocks"][0]
        self.assertEqual(saved["visual_type"], "custom_chart")
        self.assertEqual(saved["config"]["entities"][0]["id"], 42)
        self.assertEqual(saved["config"]["entities"][0]["source_competition"], "ENG1")
        self.assertEqual(saved["config"]["context"]["scope_code"], "BIG5")
        self.assertEqual(saved["config"]["metric_keys"], ["xA_per90", "key_passes_per90"])
        self.assertEqual(saved["alt"], visual["alt"])
        self.assertEqual(saved["update_policy"], "live_draft_freeze_on_publish")

    def test_visual_blocks_reject_missing_accessibility_and_invalid_chart_configuration(self):
        created = self.create_article()
        invalid = {
            "id": "visual",
            "type": "visual",
            "visual_type": "player_comparison",
            "title": "Comparison",
            "caption": "",
            "alt": "",
            "source_note": "Conceptually Football",
            "data_as_of": "not-a-date",
            "config": {
                "entity_kind": "team",
                "entities": [],
                "context": {"scope_kind": "league", "scope_code": "ENG1", "scope_label": "Premier League", "season_label": "2025/26"},
                "chart_type": "scatter",
                "metric_keys": ["xG"],
                "rate_mode": "per90",
                "filters": {"position_group": "ALL", "team_names": [], "minimum_minutes": 450},
            },
        }

        response = self.patch_article(
            created["id"],
            {
                "revision": 1,
                "title": "Invalid visual",
                "subtitle": "",
                "document": {"version": 1, "blocks": [invalid]},
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Article.objects.get(id=created["id"]).revision, 1)

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
