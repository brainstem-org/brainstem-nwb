"""Custom fields (``extra_content_json``) and repository links (``repository_links_json``)."""

from __future__ import annotations

import json
from typing import Any


def key_values(raw: Any) -> list[tuple[str, str]]:
    """
    Normalize custom fields to ``(key, value)`` pairs in their stored order.

    The current schemas store a list of ``{"key", "value"}`` objects; older records hold a dict.
    Values that are not strings are written as compact JSON.
    """
    pairs: list[tuple[str, str]] = []
    if isinstance(raw, dict):
        items = list(raw.items())
    elif isinstance(raw, list):
        items = []
        for item in raw:
            if isinstance(item, dict) and "key" in item:
                items.append((item.get("key"), item.get("value")))
    else:
        return pairs
    for key, value in items:
        if key in (None, ""):
            continue
        pairs.append((str(key), _text(value)))
    return pairs


def repository_links(raw: Any) -> list[tuple[str, str]]:
    """Normalize repository links to ``(repository, url)`` pairs, skipping entries without a URL."""
    links: list[tuple[str, str]] = []
    if not isinstance(raw, list):
        return links
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not url:
            continue
        links.append((str(item.get("repository") or "unspecified"), str(url)))
    return links


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
