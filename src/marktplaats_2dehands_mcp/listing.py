"""Fetch and parse a single listing detail page.

The listing page on `www.marktplaats.nl` / `www.2dehands.be` is server-rendered
and embeds the full structured listing payload as a JSON object assigned to
`window.__CONFIG__`. This module pulls that JSON out and exposes the relevant
fields, avoiding fragile text scraping.
"""

from __future__ import annotations

import json
import re
from typing import Any

import requests

from .api import REQUEST_HEADERS, REQUEST_TIMEOUT
from .sites import SITES, listing_url

_CONFIG_RE = re.compile(r"window\.__CONFIG__\s*=\s*(\{.*?\});</script>", re.DOTALL)
_DESCRIPTION_RE = re.compile(
    r'data-collapsable="description"[^>]*>(.*?)</div>', re.DOTALL
)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_BLANK_LINES_RE = re.compile(r"\n{2,}")


def fetch_listing_details(site: str, listing_id: str) -> dict[str, Any]:
    """Fetch a listing page and return its parsed details.

    Returns a dict shaped for the MCP tool response (see server.get_listing_details
    for the public schema), or `{"error": "..."}` on failure.
    """
    if site not in SITES:
        return {"error": f"Unknown site: {site!r}."}
    if not listing_id:
        return {"error": "Provide a listing_id."}
    if not listing_id.startswith("m"):
        listing_id = f"m{listing_id}"

    url = listing_url(site, listing_id)
    headers = {**REQUEST_HEADERS, "Accept": "text/html,application/xhtml+xml"}
    try:
        response = requests.get(
            url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=True
        )
        response.raise_for_status()
    except requests.RequestException as e:
        return {"error": f"Request failed: {e}"}

    body = response.text
    config_match = _CONFIG_RE.search(body)
    if not config_match:
        return {"error": "Listing not found"}

    try:
        config = json.loads(config_match.group(1))
    except json.JSONDecodeError:
        return {"error": "Invalid listing payload"}

    listing = config.get("listing")
    if not isinstance(listing, dict):
        return {"error": "Listing not found"}

    return _build_result(listing_id, site, response.url, listing, body)


def _build_result(
    listing_id: str,
    site: str,
    url: str,
    listing: dict[str, Any],
    html: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {"id": listing_id, "site": site, "url": url}

    title = listing.get("title")
    if title:
        result["title"] = title

    price_info = listing.get("priceInfo") or {}
    price_cents = price_info.get("priceCents")
    if isinstance(price_cents, int):
        result["price_cents"] = price_cents
        result["price"] = f"€ {price_cents / 100:.2f}"

    images = _extract_images(listing)
    if images:
        result["images"] = images
        result["image_count"] = len(images)

    description_full = _extract_description(html)
    if description_full:
        result["description_full"] = description_full
        result["description_short"] = description_full[:160]

    stats = _extract_statistics(listing)
    if stats:
        result["statistics"] = stats

    location = _extract_location(listing)
    if location:
        result["location"] = location

    return result


def _extract_images(listing: dict[str, Any]) -> list[str]:
    gallery = listing.get("gallery") or {}
    raw = gallery.get("imageUrls") or []
    return [u if u.startswith("http") else "https:" + u for u in raw]


def _extract_description(html: str) -> str:
    match = _DESCRIPTION_RE.search(html)
    if not match:
        return ""
    inner = _BR_RE.sub("\n", match.group(1))
    inner = _TAG_RE.sub("", inner)
    inner = _BLANK_LINES_RE.sub("\n", inner)
    return inner.strip()


def _extract_statistics(listing: dict[str, Any]) -> dict[str, Any]:
    stats_raw = listing.get("stats") or {}
    out: dict[str, Any] = {}
    if "viewCount" in stats_raw:
        out["views"] = stats_raw["viewCount"]
    if "favoritedCount" in stats_raw:
        out["saved"] = stats_raw["favoritedCount"]
    if stats_raw.get("since"):
        out["online_since"] = stats_raw["since"]
    return out


def _extract_location(listing: dict[str, Any]) -> str:
    seller = listing.get("seller") or {}
    location = seller.get("location") or {}
    city = location.get("cityName")
    return city or ""
