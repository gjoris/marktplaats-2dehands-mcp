"""Mocked e2e tests for authenticated MCP tools.

These run without credentials by replaying captured fixtures from
`e2e/fixtures/<site>/`. They verify the response-shape contract of every
authenticated tool against every supported site, so the functional-coverage
meta-test is satisfied even when no live session is available.

Live API drift IS NOT detected here — for that, see
`test_authenticated_live.py` which runs only when MARKTPLAATS_AUTH_STATE_*
secrets are present.

The fixtures were captured by `e2e/capture_authenticated_fixtures.py` against
a real account, then scrubbed of PII before commit.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import pytest
import requests
import responses

from marktplaats_2dehands_mcp import account as _account_mod
from marktplaats_2dehands_mcp import auth_session as _auth_session_mod
from marktplaats_2dehands_mcp import server as _s
from marktplaats_2dehands_mcp.sites import SITES

pytestmark = pytest.mark.e2e

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"

CONVERSATIONS_INPUT = quote(json.dumps({"json": {"limit": 20, "offset": 0}}), safe="")


def _load(site: str, slug: str) -> dict | list:
    return json.loads((FIXTURES_DIR / site / f"{slug}.json").read_text(encoding="utf-8"))


def _host(site: str) -> str:
    return SITES[site]["host"]


@pytest.fixture
def mock_session(monkeypatch):
    """Bypass cookie-loading so make_session works without storage_state."""

    def fake_make_session(site: str) -> requests.Session:
        session = requests.Session()
        session.headers.update({"User-Agent": "test"})
        return session

    monkeypatch.setattr(_account_mod, "make_session", fake_make_session)
    monkeypatch.setattr(_auth_session_mod, "make_session", fake_make_session)


@pytest.mark.parametrize("site", ["marktplaats", "2dehands"])
def test_auth_status_without_session(tmp_path, monkeypatch, site: str):
    monkeypatch.setattr(
        "marktplaats_2dehands_mcp.auth.DEFAULT_AUTH_DIR", tmp_path
    )
    result = _s.auth_status(site=site)
    assert result == {"authenticated": False, "site": site}


@pytest.mark.parametrize("site", ["marktplaats", "2dehands"])
def test_auth_logout_no_session_is_noop(tmp_path, monkeypatch, site: str):
    monkeypatch.setattr(
        "marktplaats_2dehands_mcp.auth.DEFAULT_AUTH_DIR", tmp_path
    )
    result = _s.auth_logout(site=site)
    assert result == {"site": site, "removed": False}


@pytest.mark.parametrize("site", ["marktplaats", "2dehands"])
def test_auth_setup_without_playwright(monkeypatch, site: str):
    """auth_setup surfaces ImportError when playwright extra isn't installed."""

    def boom(_site: str):
        raise ImportError("Playwright is required for auth_setup. Install with [auth].")

    monkeypatch.setattr("marktplaats_2dehands_mcp.auth.run_login_flow", boom)
    result = _s.auth_setup(site=site)
    assert result.get("needs_auth_extra") is True
    assert "Playwright" in result["error"]


@pytest.mark.parametrize("site", ["marktplaats", "2dehands"])
@responses.activate
def test_get_unread_counts(site: str, mock_session):
    host = _host(site)
    responses.add(
        responses.GET,
        f"https://{host}/header/messages/message-count",
        json=_load(site, "unread_messages"),
    )
    responses.add(
        responses.GET,
        f"https://{host}/header/notifications/notification-count",
        json=_load(site, "unread_notifications"),
    )
    result = _s.get_unread_counts(site=site)
    assert "error" not in result, result
    data = result["data"]
    assert "unread_messages" in data
    assert "unread_notifications" in data
    assert isinstance(data["unread_messages"], int)
    assert isinstance(data["unread_notifications"], int)


@pytest.mark.parametrize("site", ["marktplaats", "2dehands"])
@responses.activate
def test_list_my_messages(site: str, mock_session):
    host = _host(site)
    responses.add(
        responses.GET,
        f"https://{host}/messages/api/rpc/conversations.getConversations?input={CONVERSATIONS_INPUT}",
        json=_load(site, "conversations"),
    )
    result = _s.list_my_messages(site=site)
    assert "error" not in result, result
    data = result["data"]
    assert data["limit"] == 20
    assert data["offset"] == 0
    assert isinstance(data["conversations"], list)
    assert data["count"] == len(data["conversations"])


@pytest.mark.parametrize("site", ["marktplaats", "2dehands"])
@responses.activate
def test_list_my_listings(site: str, mock_session):
    host = _host(site)
    responses.add(
        responses.GET,
        f"https://{host}/my-account/sell/api/listings",
        json=_load(site, "my_listings"),
    )
    result = _s.list_my_listings(site=site)
    assert "error" not in result, result
    data = result["data"]
    assert data["batch_number"] == 1
    assert data["batch_size"] == 20
    assert isinstance(data["listings"], list)
    assert isinstance(data["total"], int)


@pytest.mark.parametrize("site", ["marktplaats", "2dehands"])
@responses.activate
def test_list_my_favorites(site: str, mock_session):
    host = _host(site)
    responses.add(
        responses.GET,
        f"https://{host}/my-account/favorites/favorites.json",
        json=_load(site, "favorites"),
    )
    result = _s.list_my_favorites(site=site)
    assert "error" not in result, result
    data = result["data"]
    assert data["batch_number"] == 1
    assert isinstance(data["favorites"], list)
    assert isinstance(data["more_available"], bool)


@pytest.mark.parametrize("site", ["marktplaats", "2dehands"])
@responses.activate
def test_list_my_bids(site: str, mock_session):
    host = _host(site)
    responses.add(
        responses.GET,
        f"https://{host}/my-account/bids/favorites.json",
        json=_load(site, "bid_favorites"),
    )
    result = _s.list_my_bids(site=site)
    assert "error" not in result, result
    data = result["data"]
    assert isinstance(data["bids"], list)
    assert isinstance(data["more_available"], bool)


@pytest.mark.parametrize("site", ["marktplaats", "2dehands"])
@responses.activate
def test_list_native_saved_searches(site: str, mock_session):
    host = _host(site)
    responses.add(
        responses.GET,
        f"https://{host}/header/searches/saved",
        json=_load(site, "saved_searches"),
    )
    result = _s.list_native_saved_searches(site=site)
    assert "error" not in result, result
    assert isinstance(result["data"], list)
