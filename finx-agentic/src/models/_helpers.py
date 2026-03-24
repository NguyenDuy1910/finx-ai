"""Shared validation/normalisation helpers for domain models."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def clean_list(values: list[str] | None) -> list[str]:
    """Deduplicated, stripped, non-empty string list."""
    if not values:
        return []

    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def clean_dict(values: dict[str, str] | None) -> dict[str, str]:
    """Stripped keys and values, dropping empties."""
    if not values:
        return {}
    result: dict[str, str] = {}
    for key, value in values.items():
        clean_key = str(key).strip()
        clean_value = str(value).strip()
        if clean_key and clean_value:
            result[clean_key] = clean_value
    return result


def parse_datetime(value: datetime | str | None) -> datetime | None:
    """Parse to UTC-aware datetime. Accepts ISO-8601 strings and datetimes."""
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    text = str(value).strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def sha256_text(value: str) -> str:
    """Deterministic SHA-256 hex digest of a UTF-8 string."""
    from hashlib import sha256

    return sha256(value.encode("utf-8")).hexdigest()
