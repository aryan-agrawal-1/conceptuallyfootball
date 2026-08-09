from __future__ import annotations

from functools import wraps

from django.http import JsonResponse
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView

from accounts.models import StaffAccess


def access_error(request, permission: str | None = None) -> JsonResponse | None:
    user = request.user
    if not user.is_authenticated:
        return JsonResponse(
            {"detail": "Authentication credentials were not provided.", "code": "not_authenticated"},
            status=401,
        )
    if user.is_superuser:
        return None

    try:
        access = user.staff_access
    except StaffAccess.DoesNotExist:
        return JsonResponse(
            {"detail": "This account does not have staff access.", "code": "access_denied"},
            status=403,
        )
    if not access.is_access_active:
        return JsonResponse(
            {"detail": "This account's access has been revoked.", "code": "access_revoked"},
            status=403,
        )
    if access.must_change_password:
        return JsonResponse(
            {"detail": "Change your temporary password to continue.", "code": "password_change_required"},
            status=403,
        )
    if permission and not user.has_perm(permission):
        return JsonResponse(
            {"detail": "You do not have permission to perform this action.", "code": "permission_denied"},
            status=403,
        )
    return None


def require_staff_permission(permission: str | None = None):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            error = access_error(request, permission)
            if error is not None:
                return error
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


class ActiveStaffAccessPermission(BasePermission):
    required_permission: str | None = None

    def has_permission(self, request, view) -> bool:
        permission = getattr(view, "required_staff_permission", self.required_permission)
        return access_error(request, permission) is None


class EditorialWorkspacePermission(ActiveStaffAccessPermission):
    required_permission = "accounts.access_editorial_workspace"


class OperationsConsolePermission(ActiveStaffAccessPermission):
    required_permission = "accounts.access_operations_console"


class StaffSessionAuthentication(SessionAuthentication):
    def authenticate_header(self, request) -> str:
        return "Session"


class PrivateStaffAPIView(APIView):
    authentication_classes = (StaffSessionAuthentication,)
    permission_classes = (ActiveStaffAccessPermission,)
