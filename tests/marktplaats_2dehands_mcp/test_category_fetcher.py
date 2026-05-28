"""Tests for dynamic category resolution with on-disk cache and fallback."""

from __future__ import annotations

import importlib
import json
import os
import time
from pathlib import Path

import pytest
import responses

from marktplaats_2dehands_mcp import categories, category_fetcher


SAMPLE_API_PAYLOAD = {
    "searchCategoryOptions": [
        {"fullName": "Antiek en Kunst", "id": 1, "key": "antiek-en-kunst"},
        {"fullName": "Computers en Software", "id": 322, "key": "computers-en-software"},
        # A subcategory that should be skipped (has parentId).
        {
            "fullName": "Laptops",
            "id": 339,
            "key": "laptops",
            "parentId": 322,
            "parentKey": "computers-en-software",
        },
    ],
}


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


def _add_search_response(mocked_responses, site: str = "marktplaats", **kwargs):
    host = "www.marktplaats.nl" if site == "marktplaats" else "www.2dehands.be"
    mocked_responses.add(
        responses.GET,
        f"https://{host}/lrp/api/search",
        **kwargs,
    )


class TestCachePath:
    def test_per_site(self, cache_dir: Path):
        assert category_fetcher._cache_path("marktplaats", cache_dir).name == "categories-marktplaats.json"
        assert category_fetcher._cache_path("2dehands", cache_dir).name == "categories-2dehands.json"


class TestGetCategories:
    def test_cache_hit_skips_http(self, cache_dir: Path):
        path = cache_dir / "categories-marktplaats.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"l1": {"foo": 1}, "l2": {}}
        path.write_text(json.dumps(payload), encoding="utf-8")

        with responses.RequestsMock():
            result = category_fetcher.get_categories(
                "marktplaats", cache_dir=cache_dir
            )
        assert result == payload

    def test_cache_miss_fetches_and_persists(
        self, cache_dir: Path, mocked_responses
    ):
        _add_search_response(mocked_responses, json=SAMPLE_API_PAYLOAD)

        result = category_fetcher.get_categories("marktplaats", cache_dir=cache_dir)
        assert result["l1"]["antiek en kunst"] == 1
        assert result["l1"]["computers en software"] == 322
        # Subcategory must not appear in L1.
        assert "laptops" not in result["l1"]
        # L2 falls back to the curated map.
        assert result["l2"]["laptops"] == {"id": 339, "parent": 322}

        cached_path = cache_dir / "categories-marktplaats.json"
        assert cached_path.exists()
        on_disk = json.loads(cached_path.read_text(encoding="utf-8"))
        assert on_disk["l1"]["antiek en kunst"] == 1

    def test_cache_stale_refetches(self, cache_dir: Path, mocked_responses):
        path = cache_dir / "categories-marktplaats.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"l1": {"old": 999}, "l2": {}}), encoding="utf-8")
        old = time.time() - 30 * 86400
        os.utime(path, (old, old))

        _add_search_response(mocked_responses, json=SAMPLE_API_PAYLOAD)
        result = category_fetcher.get_categories("marktplaats", cache_dir=cache_dir)
        assert "old" not in result["l1"]
        assert result["l1"]["antiek en kunst"] == 1

    def test_http_failure_falls_back(self, cache_dir: Path, mocked_responses):
        _add_search_response(mocked_responses, status=500)
        result = category_fetcher.get_categories("marktplaats", cache_dir=cache_dir)
        assert result["l1"] == dict(categories.L1_CATEGORIES)
        assert not (cache_dir / "categories-marktplaats.json").exists()

    def test_malformed_json_falls_back(self, cache_dir: Path, mocked_responses):
        _add_search_response(
            mocked_responses,
            body="not json",
            status=200,
            content_type="application/json",
        )
        result = category_fetcher.get_categories("marktplaats", cache_dir=cache_dir)
        assert result["l1"] == dict(categories.L1_CATEGORIES)

    def test_pure_value_error_falls_back(self, monkeypatch, cache_dir: Path):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                raise ValueError("boom")

        monkeypatch.setattr(
            "marktplaats_2dehands_mcp.category_fetcher.requests.get",
            lambda *a, **kw: FakeResponse(),
        )
        result = category_fetcher.get_categories("marktplaats", cache_dir=cache_dir)
        assert result["l1"] == dict(categories.L1_CATEGORIES)

    def test_missing_options_falls_back(self, cache_dir: Path, mocked_responses):
        _add_search_response(mocked_responses, json={"searchCategoryOptions": []})
        result = category_fetcher.get_categories("marktplaats", cache_dir=cache_dir)
        assert result["l1"] == dict(categories.L1_CATEGORIES)

    def test_options_not_a_list_falls_back(
        self, cache_dir: Path, mocked_responses
    ):
        _add_search_response(
            mocked_responses, json={"searchCategoryOptions": "broken"}
        )
        result = category_fetcher.get_categories("marktplaats", cache_dir=cache_dir)
        assert result["l1"] == dict(categories.L1_CATEGORIES)

    def test_options_with_only_subcategories_falls_back(
        self, cache_dir: Path, mocked_responses
    ):
        # Every entry has parentId — yields no L1, falls back.
        _add_search_response(
            mocked_responses,
            json={
                "searchCategoryOptions": [
                    {
                        "fullName": "Laptops",
                        "id": 339,
                        "parentId": 322,
                    }
                ]
            },
        )
        result = category_fetcher.get_categories("marktplaats", cache_dir=cache_dir)
        assert result["l1"] == dict(categories.L1_CATEGORIES)

    def test_skips_non_dict_and_malformed_entries(
        self, cache_dir: Path, mocked_responses
    ):
        _add_search_response(
            mocked_responses,
            json={
                "searchCategoryOptions": [
                    "not a dict",
                    {"fullName": None, "id": 5},
                    {"fullName": "Boeken", "id": "201"},  # id not int
                    {"fullName": "Boeken", "id": 201},
                ]
            },
        )
        result = category_fetcher.get_categories("marktplaats", cache_dir=cache_dir)
        assert result["l1"] == {"boeken": 201}

    def test_corrupt_cache_refetches(self, cache_dir: Path, mocked_responses):
        path = cache_dir / "categories-marktplaats.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json", encoding="utf-8")

        _add_search_response(mocked_responses, json=SAMPLE_API_PAYLOAD)
        result = category_fetcher.get_categories("marktplaats", cache_dir=cache_dir)
        assert result["l1"]["antiek en kunst"] == 1

    def test_unwritable_cache_does_not_crash(
        self, cache_dir: Path, mocked_responses, monkeypatch
    ):
        _add_search_response(mocked_responses, json=SAMPLE_API_PAYLOAD)

        def fail_mkdir(self, *args, **kwargs):
            raise OSError("read-only fs")

        monkeypatch.setattr(Path, "mkdir", fail_mkdir)
        result = category_fetcher.get_categories("marktplaats", cache_dir=cache_dir)
        assert result["l1"]["antiek en kunst"] == 1


class TestEnvDirOverride:
    def test_env_var_changes_default_cache_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        monkeypatch.setenv("MARKTPLAATS_2DEHANDS_CACHE_DIR", str(tmp_path))
        reloaded = importlib.reload(category_fetcher)
        assert reloaded.DEFAULT_CACHE_DIR == tmp_path
        monkeypatch.delenv("MARKTPLAATS_2DEHANDS_CACHE_DIR", raising=False)
        importlib.reload(category_fetcher)
