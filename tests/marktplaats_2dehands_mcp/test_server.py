"""Tests for the MCP server tool functions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import responses

from marktplaats_2dehands_mcp import server


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Point saved_searches at a tmp file for every test in this module.

    The path is bound as a default argument on each function in
    saved_searches.py, so we patch the function objects' __defaults__ to
    swap them in for the duration of the test.
    """
    from marktplaats_2dehands_mcp import saved_searches as ss

    state_file = tmp_path / "saved_searches.json"

    monkeypatch.setattr(ss, "DEFAULT_STATE_FILE", state_file)
    for fn_name in ("save_search", "list_searches", "delete_search", "get_search", "record_check"):
        fn = getattr(ss, fn_name)
        new_defaults = tuple(state_file if d == ss.DEFAULT_STATE_FILE else d for d in (fn.__defaults__ or ()))
        # __defaults__ is positional and the path arg is the last default in each fn,
        # so just rewrite the last entry.
        if fn.__defaults__:
            patched = (*fn.__defaults__[:-1], state_file)
            monkeypatch.setattr(fn, "__defaults__", patched)
    yield


def _add_search_response(
    mocked_responses: Any,
    site: str,
    payload: dict[str, Any],
    status: int = 200,
):
    host = "www.marktplaats.nl" if site == "marktplaats" else "www.2dehands.be"
    mocked_responses.add(
        responses.GET,
        f"https://{host}/lrp/api/search",
        json=payload,
        status=status,
    )


class TestSearchListings:
    def test_unknown_site_returns_error(self):
        result = server.search_listings(site="ebay", query="x")
        assert "error" in result
        assert "Unknown site" in result["error"]

    def test_no_query_returns_error(self):
        result = server.search_listings(site="marktplaats")
        assert "error" in result
        assert "Provide a query" in result["error"]

    def test_basic_marktplaats(
        self, mocked_responses, search_response_factory, listing_factory
    ):
        _add_search_response(
            mocked_responses,
            "marktplaats",
            search_response_factory(
                listings=[listing_factory(itemId="m100")],
                total=1,
            ),
        )
        result = server.search_listings(site="marktplaats", query="bike")
        assert result["site"] == "marktplaats"
        assert result["total_count"] == 1
        assert result["returned_count"] == 1
        assert result["listings"][0]["id"] == "m100"
        assert "note" in result  # zip_code missing

    def test_with_zip_code_omits_note(
        self, mocked_responses, search_response_factory
    ):
        _add_search_response(mocked_responses, "marktplaats", search_response_factory())
        result = server.search_listings(site="marktplaats", query="bike", zip_code="1016LV")
        assert "note" not in result

    def test_2dehands_uses_correct_host(
        self, mocked_responses, search_response_factory
    ):
        _add_search_response(mocked_responses, "2dehands", search_response_factory())
        result = server.search_listings(site="2dehands", query="bike")
        assert result["site"] == "2dehands"
        assert "2dehands.be" in mocked_responses.calls[0].request.url

    def test_pagination_offset(
        self, mocked_responses, search_response_factory, listing_factory
    ):
        _add_search_response(
            mocked_responses,
            "marktplaats",
            search_response_factory(
                listings=[listing_factory(itemId="m1")],
                total=10,
            ),
        )
        result = server.search_listings(site="marktplaats", query="x", offset=2)
        assert result["next_offset"] == 3

    def test_seller_type_filter_business_full(
        self, mocked_responses, search_response_factory, listing_factory
    ):
        _add_search_response(
            mocked_responses,
            "marktplaats",
            search_response_factory(
                listings=[
                    listing_factory(itemId="m1", traits=["VERIFIED_SELLER"]),
                    listing_factory(itemId="m2", traits=[]),
                ],
                total=2,
            ),
        )
        result = server.search_listings(
            site="marktplaats", query="x", seller_type="business"
        )
        assert len(result["listings"]) == 1
        assert result["listings"][0]["id"] == "m1"

    def test_seller_type_filter_private_full(
        self, mocked_responses, search_response_factory, listing_factory
    ):
        _add_search_response(
            mocked_responses,
            "marktplaats",
            search_response_factory(
                listings=[
                    listing_factory(itemId="m1", traits=["VERIFIED_SELLER"]),
                    listing_factory(itemId="m2", traits=[]),
                ],
                total=2,
            ),
        )
        result = server.search_listings(
            site="marktplaats", query="x", seller_type="particulier"
        )
        assert len(result["listings"]) == 1
        assert result["listings"][0]["id"] == "m2"

    def test_seller_type_unknown_value_no_filter(
        self, mocked_responses, search_response_factory, listing_factory
    ):
        _add_search_response(
            mocked_responses,
            "marktplaats",
            search_response_factory(
                listings=[listing_factory(itemId="m1")],
                total=1,
            ),
        )
        result = server.search_listings(
            site="marktplaats", query="x", seller_type="weird"
        )
        assert len(result["listings"]) == 1

    def test_unknown_category_returns_error(self):
        result = server.search_listings(site="marktplaats", category="not-real")
        assert "error" in result


class TestGetListingDetails:
    def test_delegates_to_listing_module(self, monkeypatch):
        captured: dict[str, Any] = {}

        def fake(site, listing_id):
            captured["site"] = site
            captured["listing_id"] = listing_id
            return {"id": listing_id, "site": site, "url": "u"}

        monkeypatch.setattr(server, "fetch_listing_details", fake)
        result = server.get_listing_details(listing_id="m1", site="marktplaats")
        assert captured == {"site": "marktplaats", "listing_id": "m1"}
        assert result == {"id": "m1", "site": "marktplaats", "url": "u"}


class TestGetSellerInfo:
    def test_unknown_site(self):
        result = server.get_seller_info(seller_id=1, site="ebay")
        assert "error" in result

    def test_missing_id(self):
        result = server.get_seller_info(seller_id=0)
        assert "error" in result

    def test_full_response(self, mocked_responses):
        mocked_responses.add(
            responses.GET,
            "https://www.marktplaats.nl/v/api/seller-profile/123",
            json={
                "sellerId": 123,
                "sellerName": "Alice",
                "isVerified": True,
                "averageScore": 4.5,
                "numberOfReviews": 10,
                "bankAccountVerified": True,
                "identificationVerified": False,
                "phoneNumberVerified": True,
            },
            status=200,
        )
        result = server.get_seller_info(seller_id=123, site="marktplaats")
        assert result["id"] == 123
        assert result["site"] == "marktplaats"
        assert result["name"] == "Alice"
        assert result["verification"]["bank_account"] is True
        assert result["verification"]["identification"] is False

    def test_request_failure(self, mocked_responses):
        mocked_responses.add(
            responses.GET,
            "https://www.marktplaats.nl/v/api/seller-profile/123",
            status=500,
        )
        result = server.get_seller_info(seller_id=123, site="marktplaats")
        assert "error" in result
        assert "Request failed" in result["error"]

    def test_invalid_json(self, monkeypatch):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                raise ValueError("bad json")

        monkeypatch.setattr(
            "marktplaats_2dehands_mcp.server.requests.get",
            lambda *a, **kw: FakeResponse(),
        )
        result = server.get_seller_info(seller_id=1, site="marktplaats")
        assert result == {"error": "Invalid response"}


class TestListCategories:
    def test_returns_categories(self):
        result = server.list_categories()
        assert len(result["main_categories"]) >= 30
        assert len(result["subcategories"]) >= 10
        assert all("id" in c for c in result["main_categories"])

    def test_unknown_site_error(self):
        result = server.list_categories(site="ebay")
        assert "error" in result


class TestGetCategoryFilters:
    def test_unknown_site(self):
        result = server.get_category_filters(category="x", site="ebay")
        assert "error" in result

    def test_no_args(self):
        result = server.get_category_filters()
        assert "error" in result

    def test_unknown_subcategory(self):
        result = server.get_category_filters(subcategory="phantom", site="marktplaats")
        assert "error" in result

    def test_unknown_category(self):
        result = server.get_category_filters(category="phantom", site="marktplaats")
        assert "error" in result

    def test_subcategory_query(
        self, mocked_responses, search_response_factory
    ):
        _add_search_response(
            mocked_responses,
            "marktplaats",
            search_response_factory(
                facets=[
                    {
                        "key": "RAM",
                        "label": "Werkgeheugen",
                        "attributeGroup": [
                            {
                                "attributeValueId": 7,
                                "attributeValueLabel": "8GB",
                                "histogramCount": 5,
                            }
                        ],
                    }
                ],
            ),
        )
        result = server.get_category_filters(
            subcategory="laptops", site="marktplaats"
        )
        assert "Werkgeheugen" in result["filters"]
        assert result["filters"]["Werkgeheugen"][0]["id"] == 7

    def test_category_query(self, mocked_responses, search_response_factory):
        _add_search_response(
            mocked_responses,
            "marktplaats",
            search_response_factory(),
        )
        result = server.get_category_filters(
            category="fietsen en brommers", site="marktplaats"
        )
        assert result["filters"] == {}

    def test_skip_keys_filtered(self, mocked_responses, search_response_factory):
        _add_search_response(
            mocked_responses,
            "marktplaats",
            search_response_factory(
                facets=[
                    {"key": "PriceCents", "label": "Prijs", "attributeGroup": []},
                    {
                        "key": "Custom",
                        "label": "Custom",
                        "attributeGroup": [
                            {"attributeValueId": 1, "attributeValueKey": "k"}
                        ],
                    },
                ],
            ),
        )
        result = server.get_category_filters(category="boeken", site="marktplaats")
        assert "Prijs" not in result["filters"]
        assert "Custom" in result["filters"]

    def test_facet_without_id_skipped(
        self, mocked_responses, search_response_factory
    ):
        _add_search_response(
            mocked_responses,
            "marktplaats",
            search_response_factory(
                facets=[
                    {
                        "key": "X",
                        "label": "X",
                        "attributeGroup": [
                            {"attributeValueLabel": "no-id"}  # no attributeValueId
                        ],
                    }
                ],
            ),
        )
        result = server.get_category_filters(category="boeken", site="marktplaats")
        assert "X" not in result["filters"]

    def test_empty_facets_dropped(
        self, mocked_responses, search_response_factory
    ):
        _add_search_response(
            mocked_responses,
            "marktplaats",
            search_response_factory(
                facets=[{"key": "X", "label": "X", "attributeGroup": []}],
            ),
        )
        result = server.get_category_filters(category="boeken", site="marktplaats")
        assert result["filters"] == {}

    def test_search_error_propagates(self, mocked_responses):
        mocked_responses.add(
            responses.GET,
            "https://www.marktplaats.nl/lrp/api/search",
            status=500,
        )
        result = server.get_category_filters(category="boeken", site="marktplaats")
        assert "error" in result


class TestSavedSearchTools:
    def test_save_requires_site(self):
        result = server.save_search(name="foo", params={"query": "x"})
        assert "error" in result

    def test_save_and_list(self):
        result = server.save_search(
            name="foo", params={"site": "marktplaats", "query": "x"}
        )
        assert result["saved"] is True

        listed = server.list_saved_searches()
        assert len(listed["searches"]) == 1
        assert listed["searches"][0]["name"] == "foo"

    def test_delete(self):
        server.save_search(name="foo", params={"site": "marktplaats"})
        result = server.delete_saved_search(name="foo")
        assert result["deleted"] is True

    def test_delete_missing(self):
        result = server.delete_saved_search(name="ghost")
        assert result["deleted"] is False


class TestCheckSavedSearch:
    def test_unknown_name(self):
        result = server.check_saved_search(name="ghost")
        assert "error" in result

    def test_unknown_site_in_saved(self):
        server.save_search(name="bad", params={"site": "ebay"})
        result = server.check_saved_search(name="bad")
        assert "error" in result

    def test_first_check_returns_all(
        self, mocked_responses, search_response_factory, listing_factory
    ):
        server.save_search(
            name="foo", params={"site": "marktplaats", "query": "bike"}
        )
        _add_search_response(
            mocked_responses,
            "marktplaats",
            search_response_factory(
                listings=[
                    listing_factory(itemId="m1"),
                    listing_factory(itemId="m2"),
                ],
            ),
        )
        result = server.check_saved_search(name="foo")
        assert result["first_check"] is True
        assert result["new_count"] == 2

    def test_second_check_dedupes(
        self, mocked_responses, search_response_factory, listing_factory
    ):
        server.save_search(name="foo", params={"site": "marktplaats", "query": "x"})
        payload = search_response_factory(
            listings=[listing_factory(itemId="m1")],
        )
        _add_search_response(mocked_responses, "marktplaats", payload)
        _add_search_response(mocked_responses, "marktplaats", payload)
        server.check_saved_search(name="foo")
        result = server.check_saved_search(name="foo")
        assert result["new_count"] == 0
        assert result["first_check"] is False

    def test_dry_run_does_not_record(
        self, mocked_responses, search_response_factory, listing_factory
    ):
        server.save_search(name="foo", params={"site": "marktplaats", "query": "x"})
        payload = search_response_factory(
            listings=[listing_factory(itemId="m1")],
        )
        _add_search_response(mocked_responses, "marktplaats", payload)
        _add_search_response(mocked_responses, "marktplaats", payload)
        server.check_saved_search(name="foo", mark_seen=False)
        result = server.check_saved_search(name="foo")
        assert result["new_count"] == 1  # not deduped — first call was a dry-run

    def test_search_error_returns_error(self, mocked_responses):
        server.save_search(name="foo", params={"site": "marktplaats", "query": "x"})
        mocked_responses.add(
            responses.GET,
            "https://www.marktplaats.nl/lrp/api/search",
            status=500,
        )
        result = server.check_saved_search(name="foo")
        assert "error" in result

    def test_seller_type_filter_in_saved(
        self, mocked_responses, search_response_factory, listing_factory
    ):
        server.save_search(
            name="foo",
            params={
                "site": "marktplaats",
                "query": "x",
                "seller_type": "private",
            },
        )
        _add_search_response(
            mocked_responses,
            "marktplaats",
            search_response_factory(
                listings=[
                    listing_factory(itemId="m1", traits=["VERIFIED_SELLER"]),
                    listing_factory(itemId="m2", traits=[]),
                ],
            ),
        )
        result = server.check_saved_search(name="foo")
        assert result["new_count"] == 1
        assert result["new_listings"][0]["id"] == "m2"


class TestMain:
    def test_main_runs(self, monkeypatch):
        called = []
        monkeypatch.setattr(server.mcp, "run", lambda: called.append(True))
        server.main()
        assert called == [True]
