from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model, password_validation
from django.db import transaction
from django.utils import timezone
from django.utils.html import format_html

from accounts.models import AccessAuditAction, AccessAuditEvent, StaffAccess, WriterProfile
from accounts.roles import configure_user_role


User = get_user_model()


class StaffAccessInvitationForm(forms.ModelForm):
    email = forms.EmailField(help_text="The writer will use this email to sign in.")
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    temporary_password = forms.CharField(
        widget=forms.PasswordInput,
        help_text="Share this temporary password securely. The user must replace it after signing in.",
    )

    class Meta:
        model = StaffAccess
        fields = ("role",)

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username__iexact=email).exists() or User.objects.filter(
            email__iexact=email
        ).exists():
            raise forms.ValidationError("An account already exists for this email.")
        return email

    def clean_temporary_password(self) -> str:
        password = self.cleaned_data["temporary_password"]
        password_validation.validate_password(password)
        return password


class StaffAccessChangeForm(forms.ModelForm):
    temporary_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput,
        help_text="Optional. Setting a temporary password forces another password change.",
    )

    class Meta:
        model = StaffAccess
        fields = ("role",)

    def clean_temporary_password(self) -> str:
        password = self.cleaned_data.get("temporary_password", "")
        if password:
            password_validation.validate_password(password, self.instance.user)
        return password


@admin.register(StaffAccess)
class StaffAccessAdmin(admin.ModelAdmin):
    add_form = StaffAccessInvitationForm
    form = StaffAccessChangeForm
    list_display = (
        "account",
        "role",
        "access_status",
        "must_change_password",
        "invited_by",
        "invited_at",
    )
    list_filter = ("role", "must_change_password", "revoked_at")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    readonly_fields = (
        "user_link",
        "must_change_password",
        "invited_by",
        "invited_at",
        "revoked_at",
        "updated_at",
    )
    actions = ("revoke_access", "reactivate_access", "require_password_change")

    def get_form(self, request, obj=None, **kwargs):
        kwargs["form"] = self.add_form if obj is None else self.form
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return (
                ("Invitee", {"fields": ("email", "first_name", "last_name")}),
                ("Access", {"fields": ("role", "temporary_password")}),
            )
        return (
            ("Account", {"fields": ("user_link", "role", "temporary_password")}),
            ("Security", {"fields": ("must_change_password", "revoked_at")}),
            ("Invitation", {"fields": ("invited_by", "invited_at", "updated_at")}),
        )

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Account", ordering="user__email")
    def account(self, obj):
        return obj.user.get_full_name() or obj.user.email

    @admin.display(description="User")
    def user_link(self, obj):
        if obj is None:
            return "Created when the invitation is saved."
        return format_html(
            '<a href="../../../auth/user/{}/change/">{}</a>',
            obj.user_id,
            obj.user.email or obj.user.username,
        )

    @admin.display(description="Status", boolean=True)
    def access_status(self, obj):
        return obj.is_access_active

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if not change:
            email = form.cleaned_data["email"]
            user = User.objects.create_user(
                username=email,
                email=email,
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                password=form.cleaned_data["temporary_password"],
            )
            obj.user = user
            obj.invited_by = request.user
            obj.must_change_password = True
            super().save_model(request, obj, form, change)
            configure_user_role(user, obj.role)
            AccessAuditEvent.objects.create(
                actor=request.user,
                target_user=user,
                action=AccessAuditAction.INVITED,
                after_values={"role": obj.role, "active": True},
            )
            return

        previous = StaffAccess.objects.get(pk=obj.pk)
        temporary_password = form.cleaned_data.get("temporary_password", "")
        if temporary_password:
            obj.user.set_password(temporary_password)
            obj.user.save(update_fields=("password",))
            obj.must_change_password = True
        super().save_model(request, obj, form, change)
        configure_user_role(obj.user, obj.role)
        if previous.role != obj.role:
            AccessAuditEvent.objects.create(
                actor=request.user,
                target_user=obj.user,
                action=AccessAuditAction.ROLE_CHANGED,
                before_values={"role": previous.role},
                after_values={"role": obj.role},
            )
        if temporary_password:
            AccessAuditEvent.objects.create(
                actor=request.user,
                target_user=obj.user,
                action=AccessAuditAction.PASSWORD_CHANGE_REQUIRED,
                after_values={"must_change_password": True},
            )

    @admin.action(description="Revoke selected access")
    def revoke_access(self, request, queryset):
        changed = 0
        for access in queryset.select_related("user").filter(revoked_at__isnull=True):
            access.revoked_at = timezone.now()
            access.user.is_active = False
            access.user.save(update_fields=("is_active",))
            access.save(update_fields=("revoked_at", "updated_at"))
            AccessAuditEvent.objects.create(
                actor=request.user,
                target_user=access.user,
                action=AccessAuditAction.REVOKED,
                before_values={"active": True},
                after_values={"active": False},
            )
            changed += 1
        self.message_user(request, f"Revoked {changed} account(s).", messages.SUCCESS)

    @admin.action(description="Reactivate selected access")
    def reactivate_access(self, request, queryset):
        changed = 0
        for access in queryset.select_related("user").filter(revoked_at__isnull=False):
            access.revoked_at = None
            access.must_change_password = True
            access.user.is_active = True
            access.user.save(update_fields=("is_active",))
            access.save(update_fields=("revoked_at", "must_change_password", "updated_at"))
            AccessAuditEvent.objects.create(
                actor=request.user,
                target_user=access.user,
                action=AccessAuditAction.REACTIVATED,
                before_values={"active": False},
                after_values={"active": True, "must_change_password": True},
            )
            changed += 1
        self.message_user(request, f"Reactivated {changed} account(s).", messages.SUCCESS)

    @admin.action(description="Require a password change")
    def require_password_change(self, request, queryset):
        for access in queryset.select_related("user"):
            access.must_change_password = True
            access.save(update_fields=("must_change_password", "updated_at"))
            AccessAuditEvent.objects.create(
                actor=request.user,
                target_user=access.user,
                action=AccessAuditAction.PASSWORD_CHANGE_REQUIRED,
                after_values={"must_change_password": True},
            )
        self.message_user(request, "Password change required for selected accounts.", messages.SUCCESS)


@admin.register(WriterProfile)
class WriterProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "completed_at", "updated_at")
    list_filter = ("completed_at",)
    search_fields = ("display_name", "user__email", "user__first_name", "user__last_name")
    readonly_fields = ("completed_at", "updated_at")


@admin.register(AccessAuditEvent)
class AccessAuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "target_user", "actor")
    list_filter = ("action", "created_at")
    search_fields = ("target_user__email", "actor__email", "reason")
    readonly_fields = (
        "created_at",
        "actor",
        "target_user",
        "action",
        "reason",
        "before_values",
        "after_values",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        return {}
