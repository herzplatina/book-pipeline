"""Shared utilities used across discovery, enrichment, and scoring modules."""

import json
import re

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique


def _extract_emails(*texts: str) -> list[str]:
    combined = "\n".join(text for text in texts if text)
    return _dedupe([email.rstrip(".,;:") for email in _EMAIL_RE.findall(combined)])


def _parse_json_object(text: str) -> dict:
    """Parse a JSON object, tolerating common markdown/code-fence wrappers."""
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise
        return json.loads(stripped[start : end + 1])
