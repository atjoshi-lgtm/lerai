from __future__ import annotations

import os

ERROR_TEXT_MAX_CHARS_ENV = "LERAI_ERROR_TEXT_MAX_CHARS"
DEFAULT_ERROR_TEXT_MAX_CHARS = 4000
ABSOLUTE_MAX_ERROR_TEXT_CHARS = 50000


def get_error_text_max_chars() -> int:
    raw = os.environ.get(ERROR_TEXT_MAX_CHARS_ENV)
    if raw is None:
        return DEFAULT_ERROR_TEXT_MAX_CHARS

    try:
        parsed = int(raw)
    except ValueError:
        return DEFAULT_ERROR_TEXT_MAX_CHARS

    if parsed <= 0:
        return DEFAULT_ERROR_TEXT_MAX_CHARS
    return min(parsed, ABSOLUTE_MAX_ERROR_TEXT_CHARS)


def truncate_with_marker(value: object, field_name: str, limit: int | None = None) -> str:
    text = "" if value is None else str(value)
    effective_limit = get_error_text_max_chars() if limit is None else min(
        max(limit, 1), ABSOLUTE_MAX_ERROR_TEXT_CHARS
    )

    if len(text) <= effective_limit:
        return text

    omitted = len(text) - effective_limit
    marker = (
        f"\n[TRUNCATED field={field_name} original_chars={len(text)} "
        f"shown_chars={effective_limit} omitted_chars={omitted}]"
    )
    return text[:effective_limit] + marker
