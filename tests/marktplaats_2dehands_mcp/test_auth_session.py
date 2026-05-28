"""Tests for auth_session.make_session."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marktplaats_2dehands_mcp import auth, auth_session


@pytest.fixture(autouse=True)
def isolated_auth_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(auth, "DEFAULT_AUTH_DIR", tmp_path / "auth")
    yield


def _write_state(site: str) -> None:
    target = "marktplaats.nl" if site == "marktplaats" else "2dehands.be"
    state = {
        "cookies": [
            {"name": "MpSession", "value": "tok", "domain": f".{target}"},
        ]
    }
    path = auth.storage_state_path(site)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")


class TestMakeSession:
    def test_unknown_site_raises(self):
        with pytest.raises(ValueError, match="Unknown site"):
            auth_session.make_session("ebay")

    def test_no_cookies_raises_not_authenticated(self):
        with pytest.raises(auth_session.NotAuthenticatedError, match="No saved session"):
            auth_session.make_session("marktplaats")

    def test_session_loaded_with_cookies(self):
        _write_state("marktplaats")
        session = auth_session.make_session("marktplaats")
        assert session.cookies.get("MpSession") == "tok"
        assert session.headers["Referer"] == "https://www.marktplaats.nl/"
        assert session.headers["X-Requested-With"] == "XMLHttpRequest"

    def test_2dehands_referer(self):
        _write_state("2dehands")
        session = auth_session.make_session("2dehands")
        assert session.headers["Referer"] == "https://www.2dehands.be/"
