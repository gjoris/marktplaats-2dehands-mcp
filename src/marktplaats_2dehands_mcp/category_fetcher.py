"""Resolve category mappings dynamically with on-disk cache and fallback.

The Adevinta `/lrp/api/search` endpoint exposes the L1 categories under
`searchCategoryOptions` (36 entries). L2 lists are only returned when
filtered by a parent L1, so fetching the full L2 tree would require one
call per L1 — too expensive at every cache miss. The fetcher therefore
sources L1 dynamically and keeps the curated L2 mapping from
`categories.py` as-is.

Both marktplaats.nl and 2dehands.be share the same numeric IDs, but
results are cached per site so future locale-specific labels stay
correct.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

from .categories import L1_CATEGORIES, L2_CATEGORIES
from .sites import search_url

CATEGORY_CACHE_TTL_SECONDS = 7 * 86400

DEFAULT_CACHE_DIR = Path(
    os.environ.get("MARKTPLAATS_2DEHANDS_CACHE_DIR")
    or Path.home() / ".cache" / "marktplaats-2dehands-mcp"
)

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

REQUEST_TIMEOUT = 15


def _cache_path(site: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> Path:
    return cache_dir / f"categories-{site}.json"


def _read_cache(path: Path, ttl_seconds: int) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > ttl_seconds:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def _fallback() -> dict[str, Any]:
    return {
        "l1": dict(L1_CATEGORIES),
        "l2": {name: dict(info) for name, info in L2_CATEGORIES.items()},
    }


def _fetch_remote(site: str) -> dict[str, Any] | None:
    try:
        response = requests.get(
            search_url(site),
            params={"query": "*", "limit": "1"},
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return None

    options = payload.get("searchCategoryOptions")
    if not isinstance(options, list) or not options:
        return None

    l1: dict[str, int] = {}
    for option in options:
        if not isinstance(option, dict):
            continue
        name = option.get("fullName")
        cat_id = option.get("id")
        if not isinstance(name, str) or not isinstance(cat_id, int):
            continue
        if option.get("parentId") is not None:
            continue
        l1[name.lower()] = cat_id

    if not l1:
        return None

    return {
        "l1": l1,
        "l2": {name: dict(info) for name, info in L2_CATEGORIES.items()},
    }


def get_categories(
    site: str,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    ttl_seconds: int = CATEGORY_CACHE_TTL_SECONDS,
) -> dict[str, Any]:
    """Return `{"l1": {...}, "l2": {...}}` for `site`, refreshing cache as needed."""
    path = _cache_path(site, cache_dir)
    cached = _read_cache(path, ttl_seconds)
    if cached is not None:
        return cached

    fetched = _fetch_remote(site)
    if fetched is not None:
        _write_cache(path, fetched)
        return fetched

    return _fallback()
