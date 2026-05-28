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

    def test_compact_mode(
        self, mocked_responses, search_response_factory, listing_factory
    ):
        _add_search_response(
            mocked_responses,
            "marktplaats",
            search_response_factory(
                listings=[listing_factory(itemId="m1")],
                total=5,
            ),
        )
        result = server.search_listings(site="marktplaats", query="x", compact=True)
        assert "total" in result
        assert "total_count" not in result
        assert result["next"] == 1  # offset 0 + 1 listing < total 5

    def test_compact_no_next_when_complete(
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
        result = server.search_listings(site="marktplaats", query="x", compact=True)
        assert "next" not in result

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

    def test_seller_type_filter_business_compact(
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
            site="marktplaats", query="x", seller_type="zakelijk", compact=True
        )
        assert len(result["listings"]) == 1
        assert result["listings"][0]["seller"] == "B"

    def test_seller_type_filter_private_compact(
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
            site="marktplaats", query="x", seller_type="private", compact=True
        )
        assert len(result["listings"]) == 1
        assert result["listings"][0]["seller"] == "P"

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

    def test_seller_type_unknown_value_compact(
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
            site="marktplaats", query="x", seller_type="weird", compact=True
        )
        assert len(result["listings"]) == 1

    def test_unknown_category_returns_error(self):
        result = server.search_listings(site="marktplaats", category="not-real")
        assert "error" in result


class TestGetListingDetails:
    def _add_listing_response(self, mocked_responses, site, body, status=200):
        host = "link.marktplaats.nl" if site == "marktplaats" else "link.2dehands.be"
        mocked_responses.add(
            responses.GET,
            f"https://{host}/m1",
            body=body,
            status=status,
            content_type="text/html",
        )

    def test_unknown_site_error(self):
        result = server.get_listing_details(listing_id="m1", site="ebay")
        assert "error" in result

    def test_missing_id_error(self):
        result = server.get_listing_details(listing_id="")
        assert "error" in result

    def test_prepends_m_prefix(self, mocked_responses):
        self._add_listing_response(mocked_responses, "marktplaats", "<html></html>")
        result = server.get_listing_details(listing_id="1", site="marktplaats")
        assert result["id"] == "m1"

    def test_request_failure(self, mocked_responses):
        mocked_responses.add(
            responses.GET,
            "https://link.marktplaats.nl/m1",
            status=500,
        )
        result = server.get_listing_details(listing_id="m1", site="marktplaats")
        assert "error" in result
        assert "Request failed" in result["error"]

    def test_404_returns_not_found(self, mocked_responses):
        # 404 raises_for_status, so caught as request failure.
        mocked_responses.add(
            responses.GET,
            "https://link.marktplaats.nl/m1",
            status=404,
            body="Pagina niet gevonden",
        )
        result = server.get_listing_details(listing_id="m1", site="marktplaats")
        assert "error" in result

    def test_niet_gevonden_in_body(self, mocked_responses):
        # 200 OK but body says listing not found -> handled separately.
        self._add_listing_response(
            mocked_responses,
            "marktplaats",
            "<html><body>De advertentie is niet gevonden</body></html>",
        )
        result = server.get_listing_details(listing_id="m1", site="marktplaats")
        assert result == {"error": "Listing not found"}

    def test_full_html_parsing(self, mocked_responses):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "Product",
              "name": "Test Bike",
              "description": "A nice bike.",
              "offers": {"price": "150", "availability": "InStock"},
              "image": ["//cdn.example/img1.jpg", "https://cdn.example/img2.jpg"]
            }
            </script>
          </head>
          <body>
            Beschrijving|||The full description.|||Kenmerken|||
            Locatie|||Amsterdam|||500x bekeken|||3x bewaard|||
            Sinds 10 jan '26
          </body>
        </html>
        """
        self._add_listing_response(mocked_responses, "marktplaats", html)
        result = server.get_listing_details(listing_id="m1", site="marktplaats")
        assert result["title"] == "Test Bike"
        assert result["price_cents"] == 15000
        assert result["image_count"] == 2
        assert result["images"][0] == "https://cdn.example/img1.jpg"
        assert result["images"][1] == "https://cdn.example/img2.jpg"
        assert "description_full" in result
        assert "statistics" in result
        assert result["statistics"]["views"] == "500"
        assert result["statistics"]["saved"] == 3

    def test_image_as_string(self, mocked_responses):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type": "Product", "name": "X", "offers": {"price": "1"}, "image": "//x.com/i.jpg"}
        </script></head><body></body></html>
        """
        self._add_listing_response(mocked_responses, "marktplaats", html)
        result = server.get_listing_details(listing_id="m1", site="marktplaats")
        assert result["images"] == ["https://x.com/i.jpg"]
        assert result["image_count"] == 1

    def test_https_image_unchanged(self, mocked_responses):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type": "Product", "name": "X", "offers": {"price": "1"}, "image": ["https://cdn.example/i.jpg"]}
        </script></head><body></body></html>
        """
        self._add_listing_response(mocked_responses, "marktplaats", html)
        result = server.get_listing_details(listing_id="m1", site="marktplaats")
        assert result["images"] == ["https://cdn.example/i.jpg"]

    def test_invalid_json_ld_skipped(self, mocked_responses):
        html = """
        <html><head>
        <script type="application/ld+json">{invalid json</script>
        </head><body></body></html>
        """
        self._add_listing_response(mocked_responses, "marktplaats", html)
        result = server.get_listing_details(listing_id="m1", site="marktplaats")
        # No 'title' since JSON parsing failed silently.
        assert "title" not in result

    def test_non_product_jsonld_skipped(self, mocked_responses):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type": "Organization", "name": "Marktplaats"}
        </script></head><body></body></html>
        """
        self._add_listing_response(mocked_responses, "marktplaats", html)
        result = server.get_listing_details(listing_id="m1", site="marktplaats")
        assert "title" not in result

    def test_description_stops_at_kenmerken(self, mocked_responses):
        html = """
        <html><body>
        Beschrijving|||part one|||part two|||Kenmerken|||should not appear
        </body></html>
        """
        self._add_listing_response(mocked_responses, "marktplaats", html)
        result = server.get_listing_details(listing_id="m1", site="marktplaats")
        assert "should not appear" not in result.get("description_full", "")

    def test_no_description_section(self, mocked_responses):
        html = "<html><body>Nothing here</body></html>"
        self._add_listing_response(mocked_responses, "marktplaats", html)
        result = server.get_listing_details(listing_id="m1", site="marktplaats")
        assert "description_full" not in result

    def test_description_marker_with_no_body(self, mocked_responses):
        # "Beschrijving" appears but is followed immediately by Kenmerken,
        # so the description loop iterates but collects no lines.
        html = "<html><body>Beschrijving|||Kenmerken</body></html>"
        self._add_listing_response(mocked_responses, "marktplaats", html)
        result = server.get_listing_details(listing_id="m1", site="marktplaats")
        assert "description_full" not in result

    def test_description_with_text_before_marker(self, mocked_responses):
        # Text comes before the "Beschrijving" marker — that text must be
        # skipped (in_desc still False).
        html = (
            "<html><body>preamble|||Beschrijving|||body line|||Kenmerken</body></html>"
        )
        self._add_listing_response(mocked_responses, "marktplaats", html)
        result = server.get_listing_details(listing_id="m1", site="marktplaats")
        assert "preamble" not in result.get("description_full", "")
        assert "body line" in result["description_full"]

    def test_description_marker_only(self, mocked_responses):
        # "Beschrijving" appears with no terminator and no body lines.
        html = "<html><body>Beschrijving|||</body></html>"
        self._add_listing_response(mocked_responses, "marktplaats", html)
        result = server.get_listing_details(listing_id="m1", site="marktplaats")
        assert "description_full" not in result

    def test_location_extraction(self, mocked_responses):
        html = "<html><body>Locatie:Amsterdam Centrum 500x bekeken</body></html>"
        self._add_listing_response(mocked_responses, "marktplaats", html)
        result = server.get_listing_details(listing_id="m1", site="marktplaats")
        assert "location" in result


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
