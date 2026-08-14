from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class StaffRole(models.TextChoices):
    WRITER = "writer", "Editorial writer"
    APPROVER = "approver", "Editorial approver"
    OPERATIONS = "operations", "Operations user"


class StaffAccess(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_access",
    )
    role = models.CharField(max_length=20, choices=StaffRole.choices)
    must_change_password = models.BooleanField(default=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="staff_invitations_created",
    )
    invited_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user__email",)
        permissions = (
            ("access_editorial_workspace", "Can access the editorial workspace"),
            ("approve_editorial_content", "Can approve editorial content"),
            ("access_operations_console", "Can access the operations console"),
            ("manage_staff_access", "Can manage staff access"),
        )
        verbose_name = "staff access"
        verbose_name_plural = "staff access"

    def __str__(self) -> str:
        return f"{self.user.email or self.user.username} — {self.get_role_display()}"

    @property
    def is_access_active(self) -> bool:
        return self.user.is_active and self.revoked_at is None


class WriterProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="writer_profile",
    )
    display_name = models.CharField(max_length=100)
    social_links = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("display_name",)

    def __str__(self) -> str:
        return self.display_name

    @property
    def is_complete(self) -> bool:
        return bool(self.display_name.strip() and self.completed_at)

    def mark_complete(self) -> None:
        if self.completed_at is None:
            self.completed_at = timezone.now()


class AccessAuditAction(models.TextChoices):
    INVITED = "invited", "Invited"
    ROLE_CHANGED = "role_changed", "Role changed"
    REVOKED = "revoked", "Access revoked"
    REACTIVATED = "reactivated", "Access reactivated"
    PASSWORD_CHANGE_REQUIRED = "password_change_required", "Password change required"
    PASSWORD_CHANGED = "password_changed", "Password changed"


class AccessAuditEvent(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="access_audit_actions",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="access_audit_events",
    )
    action = models.CharField(max_length=40, choices=AccessAuditAction.choices)
    reason = models.TextField(blank=True)
    before_values = models.JSONField(default=dict, blank=True)
    after_values = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return f"{self.get_action_display()}: {self.target_user}"
