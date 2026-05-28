"""Shared fixtures for the marktplaats-2dehands-mcp test suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import responses

from marktplaats_2dehands_mcp import categories, category_fetcher


@pytest.fixture(autouse=True)
def _isolated_category_cache(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep tests off the real category cache and out of HTTP for category lookups.

    Tests that exercise the fetcher directly pass an explicit `cache_dir` so
    they bypass this stub.
    """
    cache_dir = tmp_path_factory.mktemp("category_cache")
    monkeypatch.setattr(category_fetcher, "DEFAULT_CACHE_DIR", cache_dir)

    def _stub(site: str, **_kwargs: Any) -> dict[str, Any]:
        return {
            "l1": dict(categories.L1_CATEGORIES),
            "l2": {n: dict(i) for n, i in categories.L2_CATEGORIES.items()},
        }

    monkeypatch.setattr("marktplaats_2dehands_mcp.api.get_categories", _stub)
    monkeypatch.setattr("marktplaats_2dehands_mcp.server.get_categories", _stub)


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    """A clean JSON state file path for saved-search tests."""
    return tmp_path / "saved_searches.json"


@pytest.fixture
def state_dir_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Override MARKTPLAATS_2DEHANDS_STATE_DIR for the test."""
    monkeypatch.setenv("MARKTPLAATS_2DEHANDS_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def mocked_responses() -> Any:
    """Activate the `responses` mock so any requests-call must be registered."""
    with responses.RequestsMock() as rsps:
        yield rsps


@pytest.fixture
def listing_factory():
    """Build a minimally-shaped listing dict matching the Adevinta API."""

    def _build(**overrides: Any) -> dict[str, Any]:
        base = {
            "itemId": "m1",
            "title": "Test item",
            "description": "Description",
            "priceInfo": {"priceType": "FIXED", "priceCents": 1000},
            "location": {"cityName": "Amsterdam", "distanceMeters": 5000},
            "sellerInformation": {
                "sellerId": 100,
                "sellerName": "alice",
                "isVerified": False,
            },
            "traits": [],
            "attributes": [],
            "pictures": [{"mediumUrl": "//example.com/img.jpg"}],
            "date": "Vandaag",
        }
        base.update(overrides)
        return base

    return _build


@pytest.fixture
def search_response_factory(listing_factory):
    """Build a minimal /lrp/api/search JSON response."""

    def _build(
        listings: list[dict[str, Any]] | None = None,
        total: int = 0,
        facets: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        listings = listings if listings is not None else []
        return {
            "listings": listings,
            "totalResultCount": total or len(listings),
            "facets": facets or [],
            "categoriesById": {},
            "attributeHierarchy": {},
            "alternativeLocales": [],
            "correlationId": "test",
            "hasErrors": False,
            "hubPage": False,
            "isSearchSaved": False,
        }

    return _build


@pytest.fixture
def write_state(state_path: Path):
    """Helper that writes a saved-searches state file directly."""

    def _write(data: dict[str, Any]) -> Path:
        state_path.write_text(json.dumps(data), encoding="utf-8")
        return state_path

    return _write
