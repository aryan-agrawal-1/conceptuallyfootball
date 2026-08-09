from __future__ import annotations

import json

from django.contrib.auth import (
    authenticate,
    get_user_model,
    login,
    logout,
    password_validation,
    update_session_auth_hash,
)
from django.core.exceptions import ValidationError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from accounts.access import require_staff_permission
from accounts.models import AccessAuditAction, AccessAuditEvent, StaffAccess


User = get_user_model()


def json_body(request: HttpRequest) -> dict:
    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def private_json(payload: dict, *, status: int = 200) -> JsonResponse:
    response = JsonResponse(payload, status=status)
    response["Cache-Control"] = "private, no-store"
    response["Vary"] = "Cookie"
    return response


def staff_access_for(user) -> StaffAccess | None:
    try:
        return user.staff_access
    except StaffAccess.DoesNotExist:
        return None


def user_payload(user) -> dict:
    access = staff_access_for(user) if user.is_authenticated else None
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.get_full_name() or user.email or user.username,
        "role": access.role if access else "superuser" if user.is_superuser else None,
        "must_change_password": bool(access and access.must_change_password),
        "can_access_editorial": user.is_superuser
        or user.has_perm("accounts.access_editorial_workspace"),
        "can_approve_editorial": user.is_superuser
        or user.has_perm("accounts.approve_editorial_content"),
        "can_access_operations": user.is_superuser
        or (user.is_staff and user.has_perm("accounts.access_operations_console")),
    }


@require_GET
@ensure_csrf_cookie
@never_cache
def csrf_token(request: HttpRequest) -> JsonResponse:
    return private_json({"detail": "CSRF cookie set."})


@require_GET
@never_cache
def session(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return private_json({"authenticated": False})
    if not request.user.is_superuser:
        access = staff_access_for(request.user)
        if access is None or not access.is_access_active:
            return private_json(
                {"detail": "This account does not have active staff access.", "code": "access_denied"},
                status=403,
            )
    return private_json({"authenticated": True, "user": user_payload(request.user)})


@require_POST
@never_cache
def login_view(request: HttpRequest) -> JsonResponse:
    payload = json_body(request)
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    email_matches = list(User.objects.filter(email__iexact=email).only("username")[:2])
    username = email_matches[0].get_username() if len(email_matches) == 1 else email
    user = authenticate(request, username=username, password=password)
    if user is None:
        return private_json(
            {"detail": "The email or password is incorrect.", "code": "invalid_credentials"},
            status=401,
        )
    if not user.is_superuser:
        access = staff_access_for(user)
        if access is None or not access.is_access_active:
            return private_json(
                {"detail": "This account does not have active staff access.", "code": "access_denied"},
                status=403,
            )
    login(request, user)
    return private_json({"authenticated": True, "user": user_payload(user)})


@require_POST
@never_cache
def logout_view(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return private_json(
            {"detail": "Authentication credentials were not provided.", "code": "not_authenticated"},
            status=401,
        )
    logout(request)
    return private_json({"authenticated": False})


@require_POST
@never_cache
def change_password(request: HttpRequest) -> JsonResponse:
    user = request.user
    if not user.is_authenticated:
        return private_json(
            {"detail": "Authentication credentials were not provided.", "code": "not_authenticated"},
            status=401,
        )
    if not user.is_superuser:
        access = staff_access_for(user)
        if access is None or not access.is_access_active:
            return private_json(
                {"detail": "This account does not have active staff access.", "code": "access_denied"},
                status=403,
            )

    payload = json_body(request)
    current_password = str(payload.get("current_password", ""))
    new_password = str(payload.get("new_password", ""))
    if not user.check_password(current_password):
        return private_json(
            {"detail": "The current password is incorrect.", "code": "invalid_password"},
            status=400,
        )
    try:
        password_validation.validate_password(new_password, user)
    except ValidationError as error:
        return private_json(
            {"detail": "Choose a stronger password.", "code": "password_validation", "errors": error.messages},
            status=400,
        )

    user.set_password(new_password)
    user.save(update_fields=("password",))
    access = staff_access_for(user)
    if access and access.must_change_password:
        access.must_change_password = False
        access.save(update_fields=("must_change_password", "updated_at"))
    AccessAuditEvent.objects.create(
        actor=user,
        target_user=user,
        action=AccessAuditAction.PASSWORD_CHANGED,
        before_values={"must_change_password": True},
        after_values={"must_change_password": False},
    )
    update_session_auth_hash(request, user)
    return private_json({"authenticated": True, "user": user_payload(user)})


@require_GET
@require_staff_permission("accounts.access_editorial_workspace")
def editorial_workspace(request: HttpRequest) -> JsonResponse:
    return private_json({"user": user_payload(request.user), "workspace": {"status": "ready"}})


@require_GET
@require_staff_permission("accounts.access_operations_console")
def operations_status(request: HttpRequest) -> JsonResponse:
    if not request.user.is_staff and not request.user.is_superuser:
        return private_json(
            {"detail": "Staff status is required.", "code": "permission_denied"},
            status=403,
        )
    return private_json({"operations": {"status": "ready"}})
