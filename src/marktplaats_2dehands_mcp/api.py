"""Thin wrapper around the Adevinta /lrp/api/search endpoint."""

from datetime import datetime, timedelta
from typing import Any

import requests

from .categories import L1_CATEGORIES, L2_CATEGORIES
from .formatting import CONDITION_MAP, SortBy, SortOrder
from .sites import search_url

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

REQUEST_TIMEOUT = 15


class SearchError(Exception):
    """Raised when a search call fails or returns malformed JSON."""


def build_search_params(
    *,
    query: str,
    category: str | None,
    subcategory: str | None,
    zip_code: str,
    distance_km: int,
    price_from: int | None,
    price_to: int | None,
    condition: str | None,
    sort_by: str,
    sort_order: str,
    limit: int,
    offset: int,
    offered_since_days: int | None,
    attribute_ids: list[int] | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "limit": str(min(max(1, limit), 100)),
        "offset": str(offset),
        "query": query,
        "searchInTitleAndDescription": "true",
        "viewOptions": "list-view",
        "distanceMeters": str(distance_km * 1000),
        "postcode": zip_code,
        "sortBy": SortBy[sort_by.upper()].value if sort_by.upper() in SortBy.__members__ else SortBy.OPTIMIZED.value,
        "sortOrder": SortOrder[sort_order.upper()].value if sort_order.upper() in SortOrder.__members__ else SortOrder.ASC.value,
    }

    if subcategory:
        sub = subcategory.lower()
        if sub not in L2_CATEGORIES:
            raise SearchError(f"Unknown subcategory: {subcategory}")
        params["l2CategoryId"] = str(L2_CATEGORIES[sub]["id"])
        params["l1CategoryId"] = str(L2_CATEGORIES[sub]["parent"])
    elif category:
        cat = category.lower()
        if cat not in L1_CATEGORIES:
            raise SearchError(f"Unknown category: {category}")
        params["l1CategoryId"] = str(L1_CATEGORIES[cat])

    if price_from is not None or price_to is not None:
        pf = str(price_from * 100) if price_from is not None else "null"
        pt = str(price_to * 100) if price_to is not None else "null"
        params["attributeRanges[]"] = [f"PriceCents:{pf}:{pt}"]

    attribute_list: list[int] = []
    if condition and condition.lower() in CONDITION_MAP:
        attribute_list.append(CONDITION_MAP[condition.lower()])
    if attribute_ids:
        attribute_list.extend(attribute_ids)
    if attribute_list:
        params["attributesById[]"] = attribute_list

    if offered_since_days:
        since = datetime.now() - timedelta(days=offered_since_days)
        params["attributesByKey[]"] = [f"offeredSince:{int(since.timestamp()) * 1000}"]

    return params


def search(site: str, params: dict[str, Any]) -> dict[str, Any]:
    """Execute a search against the given site and return parsed JSON."""
    try:
        response = requests.get(
            search_url(site),
            params=params,
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise SearchError(f"Request failed: {e}") from e
    except ValueError as e:
        raise SearchError("Invalid JSON in response") from e
