from __future__ import annotations

import re

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\w)")
TOKEN_RE = re.compile(
    r"(?<!\w)(?:gh[pousr]_[A-Za-z0-9_\.]{4,}|[A-Za-z0-9_-]{4,}\.\.\.[A-Za-z0-9_-]{4,}|[A-Fa-f0-9]{24,})(?!\w)"
)
HANDLE_RE = re.compile(r"(?<!\w)@[A-Za-z0-9_]{3,}(?![A-Za-z0-9_])")
ZERO_WIDTH_RE = re.compile(r"[\u034f\u200b\u200c\u200d\ufeff]+")
WHITESPACE_RE = re.compile(r"[ \t]+")


def mask_sensitive_text(text: str, *, normalize_whitespace: bool = True) -> str:
    """Mask values that should not be posted into Discord or logs."""

    masked = ZERO_WIDTH_RE.sub("", text)
    masked = URL_RE.sub("[redacted-url]", masked)
    masked = EMAIL_RE.sub("[redacted-email]", masked)
    masked = PHONE_RE.sub("[redacted-phone]", masked)
    masked = TOKEN_RE.sub("[redacted-token]", masked)
    masked = HANDLE_RE.sub("[redacted-handle]", masked)
    if normalize_whitespace:
        masked = WHITESPACE_RE.sub(" ", masked)
    return masked.strip()


def truncate_text(text: str, max_chars: int = 280) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}… [truncated]"


def safe_display_text(text: str, max_chars: int = 280) -> str:
    return truncate_text(mask_sensitive_text(text), max_chars=max_chars)
