from __future__ import annotations

import json

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccessAuditAction, AccessAuditEvent, StaffAccess, StaffRole
from accounts.roles import ROLE_GROUPS, configure_user_role


TEMPORARY_PASSWORD = "Touchline-Notebook-2026!"
NEW_PASSWORD = "Pressbox-Analysis-2026!"


class StaffAccessApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="writer@example.com",
            email="writer@example.com",
            password=TEMPORARY_PASSWORD,
        )
        self.access = StaffAccess.objects.create(user=self.user, role=StaffRole.WRITER)
        configure_user_role(self.user, StaffRole.WRITER)
        self.client = Client(enforce_csrf_checks=True)

    def csrf_token(self) -> str:
        response = self.client.get(reverse("staff-csrf"))
        self.assertEqual(response.status_code, 200)
        return response.cookies["csrftoken"].value

    def post_json(self, name: str, payload: dict, token: str):
        return self.client.post(
            reverse(name),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )

    def sign_in(self, token: str):
        return self.post_json(
            "staff-login",
            {"email": self.user.email, "password": TEMPORARY_PASSWORD},
            token,
        )

    def test_invited_writer_must_replace_temporary_password_before_workspace_access(self):
        token = self.csrf_token()
        login_response = self.sign_in(token)

        self.assertEqual(login_response.status_code, 200)
        self.assertTrue(login_response.json()["user"]["must_change_password"])

        blocked_response = self.client.get(reverse("editorial-workspace"))
        self.assertEqual(blocked_response.status_code, 403)
        self.assertEqual(blocked_response.json()["code"], "password_change_required")

        token = self.client.cookies["csrftoken"].value
        password_response = self.post_json(
            "staff-change-password",
            {"current_password": TEMPORARY_PASSWORD, "new_password": NEW_PASSWORD},
            token,
        )
        self.assertEqual(password_response.status_code, 200)
        self.assertFalse(password_response.json()["user"]["must_change_password"])
        self.assertEqual(self.client.get(reverse("editorial-workspace")).status_code, 200)
        self.assertTrue(
            AccessAuditEvent.objects.filter(
                target_user=self.user,
                action=AccessAuditAction.PASSWORD_CHANGED,
            ).exists()
        )

    def test_private_endpoint_distinguishes_unauthenticated_and_unauthorized_users(self):
        unauthenticated_response = self.client.get(reverse("editorial-workspace"))
        self.assertEqual(unauthenticated_response.status_code, 401)

        token = self.csrf_token()
        self.sign_in(token)
        self.access.must_change_password = False
        self.access.save(update_fields=("must_change_password", "updated_at"))
        unauthorized_response = self.client.get(reverse("operations-status"))
        self.assertEqual(unauthorized_response.status_code, 403)
        self.assertEqual(unauthorized_response.json()["code"], "permission_denied")

    def test_revoked_account_cannot_log_in_or_keep_using_private_endpoints(self):
        token = self.csrf_token()
        self.sign_in(token)
        self.access.must_change_password = False
        self.access.revoked_at = timezone.now()
        self.access.save(update_fields=("must_change_password", "revoked_at", "updated_at"))
        self.assertEqual(self.client.get(reverse("staff-session")).status_code, 403)
        self.user.is_active = False
        self.user.save(update_fields=("is_active",))

        self.assertEqual(self.client.get(reverse("editorial-workspace")).status_code, 401)
        fresh_client = Client(enforce_csrf_checks=True)
        fresh_client.get(reverse("staff-csrf"))
        response = fresh_client.post(
            reverse("staff-login"),
            data=json.dumps({"email": self.user.email, "password": TEMPORARY_PASSWORD}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=fresh_client.cookies["csrftoken"].value,
        )
        self.assertEqual(response.status_code, 401)

    def test_authentication_posts_require_csrf(self):
        response = self.client.post(
            reverse("staff-login"),
            data=json.dumps({"email": self.user.email, "password": TEMPORARY_PASSWORD}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_private_responses_are_never_publicly_cached(self):
        response = self.client.get(reverse("staff-session"))
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("Cookie", response["Vary"])

    def test_superuser_can_sign_in_with_email_when_username_is_different(self):
        User.objects.create_superuser(
            username="site-owner",
            email="owner@example.com",
            password=TEMPORARY_PASSWORD,
        )
        token = self.csrf_token()
        response = self.post_json(
            "staff-login",
            {"email": "owner@example.com", "password": TEMPORARY_PASSWORD},
            token,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["role"], "superuser")


class StaffRoleTests(TestCase):
    def create_access(self, email: str, role: str):
        user = User.objects.create_user(username=email, email=email, password=TEMPORARY_PASSWORD)
        access = StaffAccess.objects.create(
            user=user,
            role=role,
            must_change_password=False,
        )
        configure_user_role(user, role)
        user = User.objects.get(pk=user.pk)
        return user, access

    def test_writer_is_not_django_staff_and_has_only_editorial_access(self):
        user, access = self.create_access("writer-role@example.com", StaffRole.WRITER)

        self.assertFalse(user.is_staff)
        self.assertTrue(user.has_perm("accounts.access_editorial_workspace"))
        self.assertFalse(user.has_perm("accounts.approve_editorial_content"))
        self.assertFalse(user.has_perm("accounts.access_operations_console"))
        self.assertEqual(user.groups.get().name, ROLE_GROUPS[StaffRole.WRITER])

    def test_approver_is_not_django_staff_and_can_approve(self):
        user, access = self.create_access("approver@example.com", StaffRole.APPROVER)

        self.assertFalse(user.is_staff)
        self.assertTrue(user.has_perm("accounts.access_editorial_workspace"))
        self.assertTrue(user.has_perm("accounts.approve_editorial_content"))
        self.assertFalse(user.has_perm("accounts.access_operations_console"))

    def test_operations_user_is_staff_without_editorial_permissions(self):
        user, access = self.create_access("operations@example.com", StaffRole.OPERATIONS)

        self.assertTrue(user.is_staff)
        self.assertTrue(user.has_perm("accounts.access_operations_console"))
        self.assertFalse(user.has_perm("accounts.access_editorial_workspace"))


class StaffAccessAdminTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="owner@example.com",
            email="owner@example.com",
            password=TEMPORARY_PASSWORD,
        )
        self.client.force_login(self.superuser)

    def test_superuser_can_invite_writer_from_staff_access_admin(self):
        response = self.client.post(
            reverse("admin:accounts_staffaccess_add"),
            data={
                "email": "new-writer@example.com",
                "first_name": "New",
                "last_name": "Writer",
                "temporary_password": TEMPORARY_PASSWORD,
                "role": StaffRole.WRITER,
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="new-writer@example.com")
        self.assertTrue(user.check_password(TEMPORARY_PASSWORD))
        self.assertFalse(user.is_staff)
        self.assertTrue(user.staff_access.must_change_password)
        self.assertEqual(user.staff_access.invited_by, self.superuser)
        self.assertTrue(
            AccessAuditEvent.objects.filter(
                actor=self.superuser,
                target_user=user,
                action=AccessAuditAction.INVITED,
            ).exists()
        )
