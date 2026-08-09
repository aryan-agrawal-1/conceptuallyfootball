from __future__ import annotations

import math

from django.core.exceptions import ValidationError as DjangoValidationError


DEFAULT_PAGE_SIZE = 200
MAX_PAGE_SIZE = 500


def parse_page(request) -> tuple[int, int]:
    try:
        page = int(request.query_params.get("page", "1"))
        page_size = int(request.query_params.get("page_size", str(DEFAULT_PAGE_SIZE)))
    except ValueError as exc:
        raise DjangoValidationError("page and page_size must be integers.") from exc
    if page < 1:
        raise DjangoValidationError("page must be at least 1.")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise DjangoValidationError(f"page_size must be between 1 and {MAX_PAGE_SIZE}.")
    return page, page_size


def page_bounds(page: int, page_size: int) -> tuple[int, int]:
    start = (page - 1) * page_size
    return start, start + page_size


def pagination_payload(*, count: int, page: int, page_size: int) -> dict:
    total_pages = math.ceil(count / page_size) if count else 0
    return {
        "count": count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_previous": page > 1 and total_pages > 0,
        "has_next": page < total_pages,
    }
