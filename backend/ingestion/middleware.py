from __future__ import annotations

import hashlib

from django.conf import settings


PRIVATE_API_PREFIXES = ("/api/v1/auth/", "/api/v1/private/")


def is_private_api_path(path: str) -> bool:
    return path.startswith(PRIVATE_API_PREFIXES)


class PublicApiSessionBypassMiddleware:
    """Do not decode browser sessions for public JSON API reads."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/v1/") and not is_private_api_path(request.path):
            request.COOKIES.pop(settings.SESSION_COOKIE_NAME, None)
        return self.get_response(request)


class ApiCacheHeadersMiddleware:
    """Attach browser-friendly cache headers to deterministic public API GETs."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            request.method != "GET"
            or not request.path.startswith("/api/v1/")
            or is_private_api_path(request.path)
        ):
            return response
        if response.status_code != 200 or response.streaming:
            return response

        response.setdefault("Cache-Control", "public, max-age=300, stale-while-revalidate=3600")
        response.setdefault("Vary", "Accept-Encoding")
        if "ETag" not in response:
            content = getattr(response, "content", b"")
            response["ETag"] = f'"{hashlib.sha256(content).hexdigest()}"'
        return response
