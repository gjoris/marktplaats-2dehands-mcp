"""Capture authenticated API responses and scrub them for use as e2e fixtures.

Run locally (NOT in CI) after `auth_setup` has stored a session for each site.
The mocked authenticated e2e tests replay these fixtures so CI can verify the
response-shape contract without needing live credentials.

Usage:
    python -m e2e.capture_authenticated_fixtures

Output:
    e2e/fixtures/<site>/<slug>.json  — committed, scrubbed
    e2e/fixtures/raw/<site>/<slug>.json  — gitignored, untouched (for diffing)

Review the scrubbed output before committing. Personal data leaks are
caller-fault, not script-fault: the scrubber is conservative but not exhaustive.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from marktplaats_2dehands_mcp.auth_session import make_session
from marktplaats_2dehands_mcp.sites import SITES

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "e2e" / "fixtures"
RAW_DIR = FIXTURES_DIR / "raw"

CONVERSATIONS_INPUT = quote(json.dumps({"json": {"limit": 20, "offset": 0}}), safe="")

ENDPOINTS: list[tuple[str, str]] = [
    ("unread_messages", "/header/messages/message-count"),
    ("unread_notifications", "/header/notifications/notification-count"),
    ("conversations", f"/messages/api/rpc/conversations.getConversations?input={CONVERSATIONS_INPUT}"),
    (
        "my_listings",
        "/my-account/sell/api/listings?batchNumber=1&batchSize=20&query=&categoryId=&inExpirationWindow=",
    ),
    ("favorites", "/my-account/favorites/favorites.json?batchNumber=1"),
    ("bid_favorites", "/my-account/bids/favorites.json"),
    ("saved_searches", "/header/searches/saved"),
]

SCRUB_KEYS_STRING: dict[str, str] = {
    "email": "test@example.com",
    "emailAddress": "test@example.com",
    "phone": "+31600000000",
    "phoneNumber": "+31600000000",
    "mobile": "+31600000000",
    "firstName": "Test",
    "lastName": "User",
    "nickname": "test-user",
    "displayName": "Test User",
    "fullName": "Test User",
    "name": "Sample name",
    "label": "Sample label",
    "iban": "NL00BANK0123456789",
    "street": "Teststraat",
    "streetName": "Teststraat",
    "houseNumber": "1",
    "city": "Amsterdam",
    "postalCode": "1000AA",
    "zipCode": "1000AA",
    "address": "Teststraat 1, 1000AA Amsterdam",
    "title": "Sample title",
    "subject": "Sample subject",
    "lastMessage": "Sample message body",
    "body": "Sample message body",
    "text": "Sample text",
    "description": "Sample description",
    "messageText": "Sample message body",
    "snippet": "Sample snippet",
    "vipUrl": "/v/example/m000000000-sample",
    "asqUrl": "/v/example/m000000000-sample",
    "url": "/v/example/m000000000-sample",
    "link": "/v/example/m000000000-sample",
    "itemId": "m000000000",
    "adId": "m000000000",
    "advertId": "m000000000",
    "id": "sample-id",
}

SCRUB_KEYS_INT: dict[str, int] = {
    "userId": 999999,
    "sellerId": 999999,
    "buyerId": 999999,
    "otherUserId": 999999,
    "otherParticipantId": 999999,
    "ownerId": 999999,
    "advertiserId": 999999,
    "id": 0,
    "categoryId": 0,
    "l1CategoryId": 0,
    "l2CategoryId": 0,
}

URL_KEY_HINTS = ("imageUrl", "imageUri", "thumbnail", "pictureUrl", "avatarUrl", "image")


def _is_url_like(value: str) -> bool:
    return value.startswith("http") or value.startswith("//") or value.startswith("/v/")


def _scrub(value: Any, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {k: _scrub(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v, key) for v in value]
    if key is None:
        return value
    if key in SCRUB_KEYS_STRING and isinstance(value, str):
        return SCRUB_KEYS_STRING[key]
    if key in SCRUB_KEYS_INT and isinstance(value, int):
        return SCRUB_KEYS_INT[key]
    if any(hint.lower() in key.lower() for hint in URL_KEY_HINTS) and isinstance(value, str) and _is_url_like(value):
        return "https://example.com/sample.jpg"
    return value


def capture_one(site: str, slug: str, path: str) -> tuple[Any, Any]:
    session = make_session(site)
    host = SITES[site]["host"]
    url = f"https://{host}{path}"
    response = session.get(url, timeout=15)
    response.raise_for_status()
    raw = response.json()
    scrubbed = _scrub(raw)
    return raw, scrubbed


def write_json(target: Path, data: Any) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    for site in SITES:
        print(f"\n=== {site} ===")
        for slug, path in ENDPOINTS:
            try:
                raw, scrubbed = capture_one(site, slug, path)
            except Exception as e:
                print(f"  [skip] {slug}: {e}")
                continue
            write_json(RAW_DIR / site / f"{slug}.json", raw)
            write_json(FIXTURES_DIR / site / f"{slug}.json", scrubbed)
            print(f"  [ok]   {slug}")

    print(f"\nFixtures written to {FIXTURES_DIR}")
    print("Review scrubbed output before committing — RAW dir is gitignored.")


if __name__ == "__main__":
    main()
