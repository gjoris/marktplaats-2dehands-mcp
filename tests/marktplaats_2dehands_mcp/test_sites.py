"""Tests for the site-resolution helpers."""

import pytest

from marktplaats_2dehands_mcp import sites


class TestResolve:
    def test_resolves_marktplaats(self):
        cfg = sites.resolve("marktplaats")
        assert cfg["host"] == "www.marktplaats.nl"
        assert cfg["country"] == "NL"

    def test_resolves_2dehands(self):
        cfg = sites.resolve("2dehands")
        assert cfg["host"] == "www.2dehands.be"
        assert cfg["country"] == "BE"

    def test_case_insensitive(self):
        assert sites.resolve("MARKTPLAATS")["country"] == "NL"
        assert sites.resolve("2Dehands")["country"] == "BE"

    def test_unknown_site_raises(self):
        with pytest.raises(ValueError, match="Unknown site"):
            sites.resolve("ebay")


class TestUrls:
    def test_search_url(self):
        assert sites.search_url("marktplaats") == "https://www.marktplaats.nl/lrp/api/search"
        assert sites.search_url("2dehands") == "https://www.2dehands.be/lrp/api/search"

    def test_seller_url(self):
        assert sites.seller_url("marktplaats") == "https://www.marktplaats.nl/v/api/seller-profile"
        assert sites.seller_url("2dehands") == "https://www.2dehands.be/v/api/seller-profile"

    def test_listing_url(self):
        assert sites.listing_url("marktplaats", "m123") == "https://link.marktplaats.nl/m123"
        assert sites.listing_url("2dehands", "m456") == "https://link.2dehands.be/m456"

    def test_url_helpers_propagate_unknown_site(self):
        with pytest.raises(ValueError):
            sites.search_url("nope")
        with pytest.raises(ValueError):
            sites.seller_url("nope")
        with pytest.raises(ValueError):
            sites.listing_url("nope", "m1")
