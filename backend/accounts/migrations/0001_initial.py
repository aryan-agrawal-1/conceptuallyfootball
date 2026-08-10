from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_role_groups(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    content_type, created = ContentType.objects.get_or_create(app_label="accounts", model="staffaccess")
    permission_names = {
        "access_editorial_workspace": "Can access the editorial workspace",
        "approve_editorial_content": "Can approve editorial content",
        "access_operations_console": "Can access the operations console",
        "manage_staff_access": "Can manage staff access",
    }
    permissions = {}
    for codename, name in permission_names.items():
        permission, created = Permission.objects.get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": name},
        )
        permissions[codename] = permission

    group_permissions = {
        "Editorial Writers": ("access_editorial_workspace",),
        "Editorial Approvers": ("access_editorial_workspace", "approve_editorial_content"),
        "Operations Users": ("access_operations_console",),
    }
    for group_name, codenames in group_permissions.items():
        group, created = Group.objects.get_or_create(name=group_name)
        group.permissions.set([permissions[codename] for codename in codenames])


def remove_role_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(
        name__in=("Editorial Writers", "Editorial Approvers", "Operations Users")
    ).delete()


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffAccess",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("writer", "Editorial writer"), ("approver", "Editorial approver"), ("operations", "Operations user")], max_length=20)),
                ("must_change_password", models.BooleanField(default=True)),
                ("invited_at", models.DateTimeField(auto_now_add=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("invited_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="staff_invitations_created", to=settings.AUTH_USER_MODEL)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="staff_access", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "staff access",
                "verbose_name_plural": "staff access",
                "ordering": ("user__email",),
                "permissions": (("access_editorial_workspace", "Can access the editorial workspace"), ("approve_editorial_content", "Can approve editorial content"), ("access_operations_console", "Can access the operations console"), ("manage_staff_access", "Can manage staff access")),
            },
        ),
        migrations.CreateModel(
            name="AccessAuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("invited", "Invited"), ("role_changed", "Role changed"), ("revoked", "Access revoked"), ("reactivated", "Access reactivated"), ("password_change_required", "Password change required"), ("password_changed", "Password changed")], max_length=40)),
                ("reason", models.TextField(blank=True)),
                ("before_values", models.JSONField(blank=True, default=dict)),
                ("after_values", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="access_audit_actions", to=settings.AUTH_USER_MODEL)),
                ("target_user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="access_audit_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.RunPython(create_role_groups, remove_role_groups),
    ]
