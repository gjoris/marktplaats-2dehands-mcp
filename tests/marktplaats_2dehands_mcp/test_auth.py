"""Tests for auth.py — session-state persistence helpers."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from marktplaats_2dehands_mcp import auth


@pytest.fixture(autouse=True)
def isolated_auth_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(auth, "DEFAULT_AUTH_DIR", tmp_path / "auth")
    yield


def _make_state(site: str, with_session: bool = True) -> dict:
    target = "marktplaats.nl" if site == "marktplaats" else "2dehands.be"
    cookies = []
    if with_session:
        cookies.append({"name": "MpSession", "value": "abc", "domain": f".{target}"})
    cookies.append({"name": "other", "value": "x", "domain": f".{target}"})
    return {"cookies": cookies, "origins": []}


class TestStoragePath:
    def test_path_for_marktplaats(self):
        path = auth.storage_state_path("marktplaats")
        assert path.name == "storage_state_marktplaats.json"

    def test_path_for_2dehands(self):
        assert auth.storage_state_path("2dehands").name == "storage_state_2dehands.json"


class TestIsAuthenticated:
    def test_no_file(self):
        assert auth.is_authenticated("marktplaats") is False

    def test_empty_file(self, tmp_path):
        path = auth.storage_state_path("marktplaats")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        assert auth.is_authenticated("marktplaats") is False

    def test_invalid_json(self):
        path = auth.storage_state_path("marktplaats")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json", encoding="utf-8")
        assert auth.is_authenticated("marktplaats") is False

    def test_no_session_cookie(self):
        path = auth.storage_state_path("marktplaats")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_make_state("marktplaats", with_session=False)))
        assert auth.is_authenticated("marktplaats") is False

    def test_session_cookie_present(self):
        path = auth.storage_state_path("marktplaats")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_make_state("marktplaats")))
        assert auth.is_authenticated("marktplaats") is True

    def test_2dehands_session(self):
        path = auth.storage_state_path("2dehands")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_make_state("2dehands")))
        assert auth.is_authenticated("2dehands") is True


class TestLoadCookies:
    def test_no_file_returns_empty(self):
        assert auth.load_cookies("marktplaats") == {}

    def test_invalid_json_returns_empty(self):
        path = auth.storage_state_path("marktplaats")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("garbage", encoding="utf-8")
        assert auth.load_cookies("marktplaats") == {}

    def test_returns_only_target_site_cookies(self):
        path = auth.storage_state_path("marktplaats")
        path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "cookies": [
                {"name": "MpSession", "value": "abc", "domain": ".marktplaats.nl"},
                {"name": "other", "value": "x", "domain": ".other.com"},
            ]
        }
        path.write_text(json.dumps(state))
        cookies = auth.load_cookies("marktplaats")
        assert cookies == {"MpSession": "abc"}


class TestSaveStorageState:
    def test_creates_dir_with_secure_perms(self, tmp_path):
        state = _make_state("marktplaats")
        path = auth.save_storage_state("marktplaats", state)
        assert path.exists()
        if sys.platform != "win32":
            mode = stat.S_IMODE(path.stat().st_mode)
            assert mode == 0o600
            dir_mode = stat.S_IMODE(path.parent.stat().st_mode)
            assert dir_mode == 0o700

    def test_writes_json(self):
        state = _make_state("marktplaats")
        path = auth.save_storage_state("marktplaats", state)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded == state


class TestClearSession:
    def test_no_session_returns_false(self):
        assert auth.clear_session("marktplaats") is False

    def test_existing_session_removed(self):
        path = auth.storage_state_path("marktplaats")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
        assert auth.clear_session("marktplaats") is True
        assert not path.exists()


class TestEnvOverride:
    def test_env_var_changes_default_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        monkeypatch.setenv("MARKTPLAATS_2DEHANDS_AUTH_DIR", str(tmp_path / "custom"))
        import importlib

        from marktplaats_2dehands_mcp import auth as auth_module
        reloaded = importlib.reload(auth_module)
        assert reloaded.DEFAULT_AUTH_DIR == tmp_path / "custom"
        monkeypatch.delenv("MARKTPLAATS_2DEHANDS_AUTH_DIR", raising=False)
        importlib.reload(auth_module)


