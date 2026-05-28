"""Tests for the API client."""

from datetime import datetime
from unittest.mock import patch

import pytest
import responses

from marktplaats_2dehands_mcp import api
from marktplaats_2dehands_mcp.api import SearchError


def _kwargs(**overrides):
    base = {
        "query": "",
        "category": None,
        "subcategory": None,
        "zip_code": "",
        "distance_km": 1000,
        "price_from": None,
        "price_to": None,
        "condition": None,
        "sort_by": "optimized",
        "sort_order": "asc",
        "limit": 10,
        "offset": 0,
        "offered_since_days": None,
        "attribute_ids": None,
    }
    base.update(overrides)
    return base


class TestBuildSearchParams:
    def test_minimal_params(self):
        p = api.build_search_params(**_kwargs(query="bike"))
        assert p["query"] == "bike"
        assert p["limit"] == "10"
        assert p["offset"] == "0"
        assert p["distanceMeters"] == "1000000"
        assert p["sortBy"] == "OPTIMIZED"
        assert p["sortOrder"] == "INCREASING"
        assert p["searchInTitleAndDescription"] == "true"
        assert p["viewOptions"] == "list-view"

    def test_limit_clamped_low(self):
        p = api.build_search_params(**_kwargs(limit=0))
        assert p["limit"] == "1"

    def test_limit_clamped_high(self):
        p = api.build_search_params(**_kwargs(limit=999))
        assert p["limit"] == "100"

    def test_known_category(self):
        p = api.build_search_params(**_kwargs(category="fietsen en brommers"))
        assert p["l1CategoryId"] == "445"

    def test_unknown_category_raises(self):
        with pytest.raises(SearchError, match="Unknown category"):
            api.build_search_params(**_kwargs(category="not-a-category"))

    def test_known_subcategory_sets_both_levels(self):
        p = api.build_search_params(**_kwargs(subcategory="laptops"))
        assert p["l2CategoryId"] == "339"
        assert p["l1CategoryId"] == "322"

    def test_unknown_subcategory_raises(self):
        with pytest.raises(SearchError, match="Unknown subcategory"):
            api.build_search_params(**_kwargs(subcategory="phantom"))

    def test_subcategory_takes_precedence_over_category(self):
        # If both supplied, subcategory wins (sets both ids itself).
        p = api.build_search_params(
            **_kwargs(category="fietsen en brommers", subcategory="laptops")
        )
        assert p["l1CategoryId"] == "322"
        assert p["l2CategoryId"] == "339"

    def test_price_range_both_bounds(self):
        p = api.build_search_params(**_kwargs(price_from=10, price_to=100))
        assert p["attributeRanges[]"] == ["PriceCents:1000:10000"]

    def test_price_range_only_lower(self):
        p = api.build_search_params(**_kwargs(price_from=10))
        assert p["attributeRanges[]"] == ["PriceCents:1000:null"]

    def test_price_range_only_upper(self):
        p = api.build_search_params(**_kwargs(price_to=100))
        assert p["attributeRanges[]"] == ["PriceCents:null:10000"]

    def test_no_price_range_omits_param(self):
        p = api.build_search_params(**_kwargs())
        assert "attributeRanges[]" not in p

    def test_condition_added(self):
        p = api.build_search_params(**_kwargs(condition="used"))
        assert p["attributesById[]"] == [32]

    def test_condition_unknown_ignored(self):
        p = api.build_search_params(**_kwargs(condition="banana"))
        assert "attributesById[]" not in p

    def test_attribute_ids_only(self):
        p = api.build_search_params(**_kwargs(attribute_ids=[111, 222]))
        assert p["attributesById[]"] == [111, 222]

    def test_attribute_ids_combined_with_condition(self):
        p = api.build_search_params(**_kwargs(condition="new", attribute_ids=[111]))
        assert p["attributesById[]"] == [30, 111]

    def test_offered_since_days(self):
        with patch.object(api, "datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 25)
            p = api.build_search_params(**_kwargs(offered_since_days=7))
        assert "attributesByKey[]" in p
        assert p["attributesByKey[]"][0].startswith("offeredSince:")

    def test_invalid_sort_by_falls_back(self):
        p = api.build_search_params(**_kwargs(sort_by="wackysort"))
        assert p["sortBy"] == "OPTIMIZED"

    def test_invalid_sort_order_falls_back(self):
        p = api.build_search_params(**_kwargs(sort_order="random"))
        assert p["sortOrder"] == "INCREASING"


class TestSearch:
    def test_successful_request(self, mocked_responses, search_response_factory):
        mocked_responses.add(
            responses.GET,
            "https://www.marktplaats.nl/lrp/api/search",
            json=search_response_factory(total=42),
            status=200,
        )
        data = api.search("marktplaats", {"query": "x"})
        assert data["totalResultCount"] == 42

    def test_2dehands_uses_correct_host(self, mocked_responses, search_response_factory):
        mocked_responses.add(
            responses.GET,
            "https://www.2dehands.be/lrp/api/search",
            json=search_response_factory(),
            status=200,
        )
        api.search("2dehands", {"query": "x"})
        assert len(mocked_responses.calls) == 1
        assert "2dehands.be" in mocked_responses.calls[0].request.url

    def test_http_error_raises(self, mocked_responses):
        mocked_responses.add(
            responses.GET,
            "https://www.marktplaats.nl/lrp/api/search",
            status=500,
        )
        with pytest.raises(SearchError, match="Request failed"):
            api.search("marktplaats", {})

    def test_invalid_json_via_request_exception(self, mocked_responses):
        # requests.exceptions.JSONDecodeError inherits from RequestException,
        # so a body that fails JSON parsing is reported as a request failure.
        mocked_responses.add(
            responses.GET,
            "https://www.marktplaats.nl/lrp/api/search",
            body="not json",
            status=200,
            content_type="application/json",
        )
        with pytest.raises(SearchError, match="Request failed"):
            api.search("marktplaats", {})

    def test_pure_value_error_from_response_json(self, monkeypatch):
        # Reach the bare `except ValueError` branch by patching response.json
        # to raise a plain ValueError (not a RequestException subclass).
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                raise ValueError("plain value error")

        def fake_get(*args, **kwargs):
            return FakeResponse()

        monkeypatch.setattr("marktplaats_2dehands_mcp.api.requests.get", fake_get)
        with pytest.raises(SearchError, match="Invalid JSON"):
            api.search("marktplaats", {})
