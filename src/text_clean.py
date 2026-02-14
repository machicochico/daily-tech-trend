from __future__ import annotations

import html
import re
import unicodedata
from typing import Any

_INVISIBLE_RE = re.compile(r"[\u200B\u200C\u200D\uFEFF]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


def clean_text(value: str | None) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = _INVISIBLE_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    return text


def clean_for_html(value: str | None) -> str:
    if value is None:
        return ""
    # Avoid double-escape patterns like &amp;amp; by unescaping once before render-time escaping.
    return clean_text(html.unescape(str(value)))


def clean_json_like(value: Any) -> Any:
    if isinstance(value, str):
        return clean_for_html(value)
    if isinstance(value, list):
        return [clean_json_like(v) for v in value]
    if isinstance(value, dict):
        return {clean_for_html(str(k)): clean_json_like(v) for k, v in value.items()}
    return value
