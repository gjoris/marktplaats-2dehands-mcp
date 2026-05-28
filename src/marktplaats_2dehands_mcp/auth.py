"""Authenticated session management for marktplaats.nl and 2dehands.be.

The authenticated tools need a Playwright login flow ONCE per ~weeks (the
session cookies live for a long time). After that, every request uses
plain `requests.Session` with the saved cookies — no browser per call.

This module is the only place that touches Playwright, and it's only
imported when the user actually invokes `auth_setup`. That keeps the
non-auth install footprint small.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

DEFAULT_AUTH_DIR = Path(
    os.environ.get("MARKTPLAATS_2DEHANDS_AUTH_DIR")
    or Path.home() / ".local" / "share" / "marktplaats-2dehands-mcp" / "auth"
)


def storage_state_path(site: str) -> Path:
    return DEFAULT_AUTH_DIR / f"storage_state_{site}.json"


def is_authenticated(site: str = "marktplaats") -> bool:
    """Return True if a usable storage_state file exists for the site."""
    path = storage_state_path(site)
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    cookies = data.get("cookies") or []
    return any(_is_session_cookie(c, site) for c in cookies)


def _is_session_cookie(cookie: dict, site: str) -> bool:
    domain = cookie.get("domain", "").lstrip(".")
    target = "marktplaats.nl" if site == "marktplaats" else "2dehands.be"
    return target in domain and "MpSession" in cookie.get("name", "")


def load_cookies(site: str) -> dict[str, str]:
    """Return a {name: value} dict of cookies for the given site."""
    path = storage_state_path(site)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    target = "marktplaats.nl" if site == "marktplaats" else "2dehands.be"
    return {
        c["name"]: c["value"]
        for c in data.get("cookies", [])
        if target in c.get("domain", "")
    }


def save_storage_state(site: str, raw_state: dict) -> Path:
    """Persist a Playwright storage_state dict to disk with secure perms."""
    DEFAULT_AUTH_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(DEFAULT_AUTH_DIR, stat.S_IRWXU)
    path = storage_state_path(site)
    path.write_text(json.dumps(raw_state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return path


def clear_session(site: str) -> bool:
    """Remove the saved storage_state for a site. Returns True if removed."""
    path = storage_state_path(site)
    if path.exists():
        path.unlink()
        return True
    return False


def run_login_flow(site: str) -> Path:  # pragma: no cover
    """Open a real browser, let the user log in, save the resulting state.

    Imports Playwright lazily so a base install (without the [auth] extra)
    doesn't need it. Raises ImportError with a helpful message if missing.

    Excluded from coverage: this is an interactive flow that needs a real
    browser and a real user. It is exercised manually during auth_setup.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise ImportError(
            "Playwright is required for auth_setup. Install with:\n"
            "  pip install -e '.[auth]'\n"
            "  playwright install chromium\n"
            f"(Original error: {e})"
        ) from e

    home_url = (
        "https://www.marktplaats.nl/" if site == "marktplaats"
        else "https://www.2dehands.be/"
    )
    login_marker = "Inloggen" if site == "marktplaats" else "Aanmelden"

    DEFAULT_AUTH_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(DEFAULT_AUTH_DIR, stat.S_IRWXU)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 "
                "Safari/537.36"
            ),
        )
        page = context.new_page()
        page.goto(home_url, wait_until="domcontentloaded")

        print("=" * 70)
        print(f"Browser opened on {home_url}")
        print(f"Click '{login_marker}' (top-right) and complete the login flow.")
        print("Then leave the browser open and run, in another terminal:")
        print(f"  touch {DEFAULT_AUTH_DIR}/done_{site}")
        print("=" * 70, flush=True)

        marker = DEFAULT_AUTH_DIR / f"done_{site}"
        marker.unlink(missing_ok=True)

        import time
        deadline = time.time() + 15 * 60
        while not marker.exists():
            if time.time() > deadline:  # pragma: no cover
                browser.close()
                raise TimeoutError("Login flow exceeded 15-minute window")
            time.sleep(1)
        marker.unlink(missing_ok=True)

        state = context.storage_state()
        path = save_storage_state(site, state)
        browser.close()
        return path
