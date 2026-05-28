"""Authenticated account-level endpoints (inbox, listings, favorites, bids).

All functions return clean dicts that the MCP-tool wrappers in `server.py`
re-emit. Network errors are wrapped as `AccountError`.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import requests

from .auth_session import NotAuthenticatedError, make_session
from .sites import SITES

REQUEST_TIMEOUT = 15


class AccountError(Exception):
    """Raised when an authenticated endpoint call fails."""


def _get(site: str, path: str) -> Any:
    session = make_session(site)
    host = SITES[site]["host"]
    url = f"https://{host}{path}"
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise AccountError(f"Request failed: {e}") from e
    except ValueError as e:
        raise AccountError("Invalid JSON in response") from e


def get_unread_counts(site: str) -> dict[str, int]:
    messages = _get(site, "/header/messages/message-count")
    notifications = _get(site, "/header/notifications/notification-count")
    return {
        "unread_messages": messages.get("unreadMessagesCount", 0),
        "unread_notifications": notifications.get("unreadNotificationsCount", 0),
    }


def list_conversations(site: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    payload = json.dumps({"json": {"limit": limit, "offset": offset}})
    encoded = quote(payload, safe="")
    data = _get(site, f"/messages/api/rpc/conversations.getConversations?input={encoded}")
    conversations = (data.get("result") or {}).get("data") or []
    return {
        "limit": limit,
        "offset": offset,
        "count": len(conversations),
        "conversations": conversations,
    }


def list_my_listings(
    site: str,
    batch_number: int = 1,
    batch_size: int = 20,
    query: str = "",
) -> dict[str, Any]:
    path = (
        f"/my-account/sell/api/listings"
        f"?batchNumber={batch_number}&batchSize={batch_size}"
        f"&query={quote(query)}&categoryId=&inExpirationWindow="
    )
    data = _get(site, path)
    return {
        "batch_number": batch_number,
        "batch_size": batch_size,
        "total": data.get("totalNumberOfResults", 0),
        "listings": data.get("ads") or [],
    }


def list_favorites(site: str, batch_number: int = 1) -> dict[str, Any]:
    data = _get(site, f"/my-account/favorites/favorites.json?batchNumber={batch_number}")
    return {
        "batch_number": batch_number,
        "more_available": data.get("moreFavoritesAvailable", False),
        "favorites": data.get("favorites") or [],
    }


def list_bid_favorites(site: str) -> dict[str, Any]:
    data = _get(site, "/my-account/bids/favorites.json")
    return {
        "more_available": data.get("moreBidsAvailable", False),
        "bids": data.get("favorites") or [],
    }


def list_native_saved_searches(site: str) -> list[dict[str, Any]]:
    data = _get(site, "/header/searches/saved")
    if not isinstance(data, list):
        raise AccountError("Unexpected response shape for saved searches")
    return data


__all__ = [
    "AccountError",
    "NotAuthenticatedError",
    "get_unread_counts",
    "list_bid_favorites",
    "list_conversations",
    "list_favorites",
    "list_my_listings",
    "list_native_saved_searches",
]
