"""Live auth e2e tests — local-only smoke for authenticated endpoints.

Sister of `test_live_api.py` for the *authenticated* endpoints, used to detect
upstream API drift in the auth-required parts. Auto-skips when no
storage_state file is present, so they're effectively local-only: CI never
ships session cookies as secrets.

Run locally with `pytest e2e/marktplaats_2dehands_mcp/test_authenticated_live.py`
after `auth_setup` has stored a session.
"""

from __future__ import annotations

import pytest

from marktplaats_2dehands_mcp import auth as _auth
from marktplaats_2dehands_mcp import server as _s

pytestmark = [pytest.mark.e2e, pytest.mark.live_auth]


def _skip_unless_authenticated(site: str) -> None:
    if not _auth.is_authenticated(site):
        pytest.skip(f"No saved session for {site!r} — run auth_setup locally first.")


@pytest.mark.parametrize("site", ["marktplaats", "2dehands"])
def test_get_unread_counts_live(site: str):
    _skip_unless_authenticated(site)
    result = _s.get_unread_counts(site=site)
    assert "error" not in result, result
    data = result["data"]
    assert isinstance(data["unread_messages"], int)
    assert isinstance(data["unread_notifications"], int)


@pytest.mark.parametrize("site", ["marktplaats", "2dehands"])
def test_list_native_saved_searches_live(site: str):
    _skip_unless_authenticated(site)
    result = _s.list_native_saved_searches(site=site)
    assert "error" not in result, result
    assert isinstance(result["data"], list)


@pytest.mark.parametrize("site", ["marktplaats", "2dehands"])
def test_list_my_favorites_live(site: str):
    _skip_unless_authenticated(site)
    result = _s.list_my_favorites(site=site)
    assert "error" not in result, result
    data = result["data"]
    assert isinstance(data["favorites"], list)
    assert isinstance(data["more_available"], bool)
