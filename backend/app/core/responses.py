"""Standard success response envelope (docs/api-contract.md section 8)."""
from __future__ import annotations

from typing import Any

from app.core.logging import request_id_ctx


def envelope(data: Any, **extra_meta: Any) -> dict:
    return {"data": data, "meta": {"request_id": request_id_ctx.get(), **extra_meta}}


def collection_envelope(
    items: list, *, page: int, page_size: int, total: int
) -> dict:
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return {
        "data": items,
        "meta": {
            "request_id": request_id_ctx.get(),
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        },
    }
