from __future__ import annotations

import hashlib


class ApiCacheHeadersMiddleware:
    """Attach browser-friendly cache headers to deterministic public API GETs."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.method != "GET" or not request.path.startswith("/api/v1/"):
            return response
        if response.status_code != 200 or response.streaming:
            return response

        response.setdefault("Cache-Control", "public, max-age=300, stale-while-revalidate=3600")
        response.setdefault("Vary", "Accept-Encoding")
        if "ETag" not in response:
            content = getattr(response, "content", b"")
            response["ETag"] = f'"{hashlib.sha256(content).hexdigest()}"'
        return response
