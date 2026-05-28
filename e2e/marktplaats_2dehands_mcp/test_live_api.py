"""End-to-end tests against the live marktplaats.nl and 2dehands.be APIs.

These verify that the upstream Adevinta endpoints still respond with the
shape we expect. A failure here means the API has changed or is down — not
that our code is wrong. They are scheduled daily via the e2e workflow and
do not block PR merges.

The tools are looked up dynamically via the `server` module so the
autouse `_track_tool_calls` fixture in conftest can wrap them for
functional-coverage tracking before each call.
"""

import pytest

from marktplaats_2dehands_mcp import server as _s

pytestmark = pytest.mark.e2e


def search_listings(*a, **kw):
    return _s.search_listings(*a, **kw)


def get_listing_details(*a, **kw):
    return _s.get_listing_details(*a, **kw)


def get_seller_info(*a, **kw):
    return _s.get_seller_info(*a, **kw)


def list_categories(*a, **kw):
    return _s.list_categories(*a, **kw)


def get_category_filters(*a, **kw):
    return _s.get_category_filters(*a, **kw)


def save_search(*a, **kw):
    return _s.save_search(*a, **kw)


def list_saved_searches(*a, **kw):
    return _s.list_saved_searches(*a, **kw)


def delete_saved_search(*a, **kw):
    return _s.delete_saved_search(*a, **kw)


def check_saved_search(*a, **kw):
    return _s.check_saved_search(*a, **kw)


@pytest.mark.parametrize("site", ["marktplaats", "2dehands"])
def test_search_listings_returns_results(site: str, real_search_query: str):
    result = search_listings(site=site, query=real_search_query, limit=3)
    assert "error" not in result, result
    assert result["site"] == site
    assert result["total_count"] > 0
    assert len(result["listings"]) > 0
    sample = result["listings"][0]
    assert sample["id"]
    assert sample["title"]
    assert sample["link"].startswith("https://")


@pytest.mark.parametrize("site", ["marktplaats", "2dehands"])
def test_get_listing_details_for_first_search_hit(site: str, real_search_query: str):
    search = search_listings(site=site, query=real_search_query, limit=1)
    assert search["listings"], search
    listing_id = search["listings"][0]["id"]
    seller_id = search["listings"][0]["seller"]["id"]

    details = get_listing_details(listing_id=listing_id, site=site)
    assert "error" not in details, details
    assert details["id"] == listing_id
    assert details["site"] == site
    assert details["title"]

    if seller_id:
        seller = get_seller_info(seller_id=seller_id, site=site)
        assert "error" not in seller, seller
        assert seller["id"] == seller_id
        assert "verification" in seller


@pytest.mark.parametrize("site", ["marktplaats", "2dehands"])
def test_list_categories_returns_known_entries(site: str):
    result = list_categories(site=site)
    assert len(result["main_categories"]) >= 30
    names = {c["name"].lower() for c in result["main_categories"]}
    assert "fietsen en brommers" in names


@pytest.mark.parametrize("site", ["marktplaats", "2dehands"])
def test_get_category_filters_for_laptops(site: str):
    result = get_category_filters(subcategory="laptops", site=site)
    assert "error" not in result, result
    assert result["filters"], "expected at least one filter group for laptops"


@pytest.mark.parametrize("site", ["marktplaats", "2dehands"])
def test_saved_search_round_trip(tmp_path, monkeypatch, site: str, real_search_query: str):
    state_file = tmp_path / "state.json"
    from marktplaats_2dehands_mcp import saved_searches as ss

    monkeypatch.setattr(ss, "DEFAULT_STATE_FILE", state_file)
    for fn_name in ("save_search", "list_searches", "delete_search", "get_search", "record_check"):
        fn = getattr(ss, fn_name)
        if fn.__defaults__:
            monkeypatch.setattr(fn, "__defaults__", (*fn.__defaults__[:-1], state_file))

    name = f"e2e-{site}"
    save_search(name=name, params={"site": site, "query": real_search_query, "limit": 5})
    try:
        listed = list_saved_searches()
        assert any(s["name"] == name for s in listed["searches"])

        first = check_saved_search(name=name)
        assert "error" not in first, first
        assert first["first_check"] is True
        assert first["new_count"] == first["checked_count"]

        second = check_saved_search(name=name)
        assert second["new_count"] == 0
    finally:
        delete_saved_search(name=name)
