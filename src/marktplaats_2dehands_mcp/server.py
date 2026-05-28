"""MCP server exposing tools for marktplaats.nl and 2dehands.be."""

from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

from . import saved_searches as ss
from .api import REQUEST_HEADERS, REQUEST_TIMEOUT, SearchError, build_search_params, search
from .categories import L1_CATEGORIES, L2_CATEGORIES
from .formatting import format_listing, format_listing_compact
from .sites import SITES, listing_url, seller_url

mcp = FastMCP("marktplaats-2dehands")


def _make_listings(site: str, raw_listings: list[dict], compact: bool) -> list[dict]:
    if compact:
        return [format_listing_compact(l) for l in raw_listings]
    return [
        format_listing(l, listing_url(site, l.get("itemId", "")))
        for l in raw_listings
    ]


def _filter_by_seller_type(listings: list[dict], seller_type: str, compact: bool) -> list[dict]:
    st = seller_type.lower()
    if compact:
        if st in ("business", "zakelijk"):
            return [l for l in listings if l["seller"] == "B"]
        if st in ("private", "particulier"):
            return [l for l in listings if l["seller"] == "P"]
    else:
        if st in ("business", "zakelijk"):
            return [l for l in listings if l["seller"]["type"] == "business"]
        if st in ("private", "particulier"):
            return [l for l in listings if l["seller"]["type"] == "private"]
    return listings


@mcp.tool()
def search_listings(
    site: str = "marktplaats",
    query: str = "",
    category: str | None = None,
    subcategory: str | None = None,
    zip_code: str = "",
    distance_km: int = 1000,
    price_from: int | None = None,
    price_to: int | None = None,
    condition: str | None = None,
    seller_type: str | None = None,
    sort_by: str = "optimized",
    sort_order: str = "asc",
    limit: int = 10,
    offset: int = 0,
    offered_since_days: int | None = None,
    attribute_ids: list[int] | None = None,
    compact: bool = False,
) -> dict[str, Any]:
    """Search for listings on marktplaats.nl or 2dehands.be.

    Args:
        site: "marktplaats" (NL, default) or "2dehands" (BE).
        query: Search query text (required if no category specified).
        category: Main category name (e.g., "computers en software").
        subcategory: Subcategory name (e.g., "laptops", "elektrische fietsen").
        zip_code: Postal code for distance filtering. NL: "1016LV". BE: "2000".
        distance_km: Maximum distance in km (default 1000). Requires zip_code.
        price_from / price_to: Price range in euros.
        condition: "new", "as_good_as_new", "used", "refurbished", "not_working".
        seller_type: "business" / "zakelijk" or "private" / "particulier".
        sort_by: "date", "price", "optimized", "location".
        sort_order: "asc" or "desc".
        limit: 1-100 (default 10).
        offset: Pagination offset.
        offered_since_days: Only show items posted within the last N days.
        attribute_ids: Category-specific filter IDs (use get_category_filters).
        compact: Return minimal format (~75% smaller). B=business, P=private.

    Returns:
        Dict with total_count, returned_count, listings, optional next_offset.
    """
    if site not in SITES:
        return {"error": f"Unknown site: {site!r}. Use 'marktplaats' or '2dehands'."}
    if not query and not category and not subcategory:
        return {"error": "Provide a query, category, or subcategory."}

    try:
        params = build_search_params(
            query=query,
            category=category,
            subcategory=subcategory,
            zip_code=zip_code,
            distance_km=distance_km,
            price_from=price_from,
            price_to=price_to,
            condition=condition,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
            offered_since_days=offered_since_days,
            attribute_ids=attribute_ids,
        )
        data = search(site, params)
    except SearchError as e:
        return {"error": str(e)}

    listings = _make_listings(site, data.get("listings", []), compact)
    if seller_type:
        listings = _filter_by_seller_type(listings, seller_type, compact)

    total_count = data.get("totalResultCount", 0)

    if compact:
        result: dict[str, Any] = {"site": site, "total": total_count, "listings": listings}
        if offset + len(listings) < total_count:
            result["next"] = offset + len(listings)
        return result

    result = {
        "site": site,
        "total_count": total_count,
        "returned_count": len(listings),
        "offset": offset,
        "listings": listings,
    }
    if not zip_code:
        result["note"] = "Provide zip_code to enable distance filtering."
    if offset + len(listings) < total_count:
        result["next_offset"] = offset + len(listings)
    return result


@mcp.tool()
def get_listing_details(listing_id: str, site: str = "marktplaats") -> dict[str, Any]:
    """Fetch a listing's full page (HTML) and extract title, price, description, images.

    Args:
        listing_id: e.g. "m2340580395" (the 'm' prefix is added if missing).
        site: "marktplaats" or "2dehands".
    """
    if site not in SITES:
        return {"error": f"Unknown site: {site!r}."}
    if not listing_id:
        return {"error": "Provide a listing_id."}
    if not listing_id.startswith("m"):
        listing_id = f"m{listing_id}"

    import json as _json
    import re

    from bs4 import BeautifulSoup

    headers = {**REQUEST_HEADERS, "Accept": "text/html,application/xhtml+xml"}
    try:
        response = requests.get(
            listing_url(site, listing_id),
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        return {"error": f"Request failed: {e}"}

    if response.status_code == 404 or "niet gevonden" in response.text.lower():
        return {"error": "Listing not found"}

    soup = BeautifulSoup(response.text, "html.parser")
    result: dict[str, Any] = {"id": listing_id, "site": site, "url": response.url}

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _json.loads(script.string or "")
            if isinstance(data, dict) and data.get("@type") == "Product":
                result["title"] = data.get("name")
                result["description_short"] = data.get("description")
                offers = data.get("offers", {}) or {}
                result["price"] = f"€ {offers.get('price', 0)}"
                result["price_cents"] = int(float(offers.get("price", 0)) * 100)
                images = data.get("image") or []
                if isinstance(images, str):
                    images = [images]
                result["images"] = [
                    img if img.startswith("http") else "https:" + img for img in images
                ]
                result["image_count"] = len(images)
        except (_json.JSONDecodeError, TypeError, ValueError):
            pass

    text = soup.get_text(separator="|||")
    if "Beschrijving" in text:
        parts = text.split("|||")
        in_desc = False
        lines: list[str] = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if part == "Beschrijving":
                in_desc = True
                continue
            if in_desc:
                if part in ("Kenmerken", "Locatie", "Bied nu", "Bericht", "Vragen aan verkoper"):
                    break
                lines.append(part)
        if lines:
            result["description_full"] = " ".join(lines)

    views = re.search(r"([\d.]+)x bekeken", text)
    saved = re.search(r"(\d+)x bewaard", text)
    since = re.search(r"Sinds (\d+ \w+ '\d+)", text)
    stats: dict[str, Any] = {}
    if views:
        stats["views"] = views.group(1)
    if saved:
        stats["saved"] = int(saved.group(1))
    if since:
        stats["online_since"] = since.group(1)
    if stats:
        result["statistics"] = stats

    location_match = re.search(r"Locatie[^\w]*(\w[\w\s]+?)(?:[\d.]+x bekeken|Toon|Op de kaart)", text)
    if location_match:
        result["location"] = location_match.group(1).strip()

    return result


@mcp.tool()
def get_seller_info(seller_id: int, site: str = "marktplaats") -> dict[str, Any]:
    """Fetch a seller profile (ratings, verification status, review count)."""
    if site not in SITES:
        return {"error": f"Unknown site: {site!r}."}
    if not seller_id:
        return {"error": "Provide a seller_id."}

    try:
        response = requests.get(
            f"{seller_url(site)}/{seller_id}",
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        return {"error": f"Request failed: {e}"}
    except ValueError:
        return {"error": "Invalid response"}

    return {
        "id": data.get("sellerId"),
        "site": site,
        "name": data.get("sellerName"),
        "is_verified": data.get("isVerified", False),
        "average_score": data.get("averageScore"),
        "number_of_reviews": data.get("numberOfReviews", 0),
        "verification": {
            "bank_account": data.get("bankAccountVerified", False),
            "identification": data.get("identificationVerified", False),
            "phone_number": data.get("phoneNumberVerified", False),
        },
    }


@mcp.tool()
def list_categories() -> dict[str, Any]:
    """List the supported main categories and common subcategories.

    Same IDs work on both marktplaats.nl and 2dehands.be.
    """
    return {
        "main_categories": [
            {"name": name.title(), "id": id_} for name, id_ in sorted(L1_CATEGORIES.items())
        ],
        "subcategories": [
            {"name": name.title(), "id": info["id"], "parent_id": info["parent"]}
            for name, info in sorted(L2_CATEGORIES.items())
        ],
        "note": "Use category names (not IDs) in search_listings.",
    }


@mcp.tool()
def get_category_filters(
    category: str | None = None,
    subcategory: str | None = None,
    site: str = "marktplaats",
) -> dict[str, Any]:
    """Discover the attribute filters available within a category."""
    if site not in SITES:
        return {"error": f"Unknown site: {site!r}."}
    if not category and not subcategory:
        return {"error": "Provide a category or subcategory."}

    params: dict[str, Any] = {"limit": "1", "query": ""}
    if subcategory:
        sub = subcategory.lower()
        if sub not in L2_CATEGORIES:
            return {"error": f"Unknown subcategory: {subcategory}"}
        params["l2CategoryId"] = str(L2_CATEGORIES[sub]["id"])
        params["l1CategoryId"] = str(L2_CATEGORIES[sub]["parent"])
    elif category:
        cat = category.lower()
        if cat not in L1_CATEGORIES:
            return {"error": f"Unknown category: {category}"}
        params["l1CategoryId"] = str(L1_CATEGORIES[cat])

    try:
        data = search(site, params)
    except SearchError as e:
        return {"error": str(e)}

    filters: dict[str, list[dict]] = {}
    skip_keys = {"PriceCents", "RelevantCategories", "offeredSince"}
    for facet in data.get("facets", []):
        if facet.get("key") in skip_keys:
            continue
        label = facet.get("label", facet.get("key"))
        options = []
        for attr in facet.get("attributeGroup") or []:
            attr_id = attr.get("attributeValueId")
            if attr_id is not None:
                options.append({
                    "name": attr.get("attributeValueLabel") or attr.get("attributeValueKey"),
                    "id": attr_id,
                    "count": attr.get("histogramCount", 0),
                })
        if options:
            filters[label] = options

    return {
        "site": site,
        "category": subcategory or category,
        "filters": filters,
        "usage": "Pass selected ids via 'attribute_ids' on search_listings.",
    }


@mcp.tool()
def save_search(name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Persist a search so it can be re-run via check_saved_search.

    Args:
        name: Identifier for the saved search (e.g. "trek-bike-antwerp").
        params: Same kwargs as search_listings (must include 'site').

    On creation, seen_ids is empty — the first check_saved_search call will
    return all current matches. To suppress that backfill, call check
    immediately after saving.
    """
    if "site" not in params:
        return {"error": "params must include 'site'."}
    return ss.save_search(name, params)


@mcp.tool()
def list_saved_searches() -> dict[str, Any]:
    """List all persisted searches."""
    return {"searches": ss.list_searches()}


@mcp.tool()
def delete_saved_search(name: str) -> dict[str, Any]:
    """Remove a persisted search."""
    return {"name": name, "deleted": ss.delete_search(name)}


@mcp.tool()
def check_saved_search(name: str, mark_seen: bool = True) -> dict[str, Any]:
    """Re-run a saved search and return only listings not seen before.

    Args:
        name: The saved search name.
        mark_seen: If True (default), record the returned IDs as seen so
            the next call returns only newer ones. Set False for a dry-run.
    """
    entry = ss.get_search(name)
    if entry is None:
        return {"error": f"No saved search named {name!r}"}

    params = dict(entry["params"])
    site = params.pop("site")
    if site not in SITES:
        return {"error": f"Saved search has unknown site: {site!r}"}

    # Force a manageable limit for monitoring; user can override via params.
    params.setdefault("limit", 50)
    params.setdefault("sort_by", "date")
    params.setdefault("sort_order", "desc")

    try:
        api_params = build_search_params(
            query=params.get("query", ""),
            category=params.get("category"),
            subcategory=params.get("subcategory"),
            zip_code=params.get("zip_code", ""),
            distance_km=params.get("distance_km", 1000),
            price_from=params.get("price_from"),
            price_to=params.get("price_to"),
            condition=params.get("condition"),
            sort_by=params.get("sort_by", "date"),
            sort_order=params.get("sort_order", "desc"),
            limit=params.get("limit", 50),
            offset=params.get("offset", 0),
            offered_since_days=params.get("offered_since_days"),
            attribute_ids=params.get("attribute_ids"),
        )
        data = search(site, api_params)
    except SearchError as e:
        return {"error": str(e)}

    seen_ids = set(entry.get("seen_ids", []))
    raw_listings = data.get("listings", [])
    new_raw = [l for l in raw_listings if l.get("itemId") not in seen_ids]

    new_listings = _make_listings(site, new_raw, compact=False)
    if params.get("seller_type"):
        new_listings = _filter_by_seller_type(new_listings, params["seller_type"], compact=False)

    if mark_seen:
        ss.record_check(name, [l.get("itemId") for l in raw_listings if l.get("itemId")])

    return {
        "name": name,
        "site": site,
        "checked_count": len(raw_listings),
        "new_count": len(new_listings),
        "new_listings": new_listings,
        "first_check": entry.get("last_checked_at") is None,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
