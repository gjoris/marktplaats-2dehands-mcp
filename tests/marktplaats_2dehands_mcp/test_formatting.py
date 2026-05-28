"""Tests for formatting helpers."""

import pytest

from marktplaats_2dehands_mcp import formatting


class TestParsePrice:
    @pytest.mark.parametrize(
        "price_type,cents,expected",
        [
            ("FIXED", 1500, "€ 15.00"),
            ("BID", 0, "Bieden"),
            ("BID_FROM", 5000, "Bieden vanaf € 50.00"),
            ("FREE", 0, "Gratis"),
            ("RESERVED", 0, "Gereserveerd"),
            ("SEE_DESCRIPTION", 0, "Zie omschrijving"),
            ("TO_BE_AGREED_UPON", 0, "N.o.t.k."),
            ("ON_REQUEST", 0, "Op aanvraag"),
            ("EXCHANGE", 0, "Ruilen"),
            ("UNKNOWN_TYPE", 2500, "€ 25.00"),
        ],
    )
    def test_parse_price(self, price_type, cents, expected):
        assert formatting.parse_price(price_type, cents) == expected


class TestDetectSellerType:
    def test_business_via_traits(self):
        assert formatting.detect_seller_type(["VERIFIED_SELLER"]) == "business"
        assert formatting.detect_seller_type(["SHOPPING_CART", "OTHER"]) == "business"

    def test_private_default(self):
        assert formatting.detect_seller_type([]) == "private"
        assert formatting.detect_seller_type(["OTHER"]) == "private"


class TestFormatListing:
    def test_full_listing(self, listing_factory):
        listing = listing_factory(
            attributes=[{"key": "condition", "value": "Gebruikt"}],
        )
        result = formatting.format_listing(listing, "https://link.example/m1")
        assert result["id"] == "m1"
        assert result["title"] == "Test item"
        assert result["price"] == "€ 10.00"
        assert result["price_cents"] == 1000
        assert result["condition"] == "used"
        assert result["location"] == {"city": "Amsterdam", "distance_km": 5.0}
        assert result["seller"]["type"] == "private"
        assert result["image"] == "https://example.com/img.jpg"
        assert result["link"] == "https://link.example/m1"

    @pytest.mark.parametrize(
        "label,expected",
        [
            ("Nieuw", "new"),
            ("Zo goed als nieuw", "as_good_as_new"),
            ("Gebruikt", "used"),
            ("Refurbished", "refurbished"),
            ("Niet werkend", "not_working"),
        ],
    )
    def test_condition_labels_mapped(self, listing_factory, label, expected):
        listing = listing_factory(attributes=[{"key": "condition", "value": label}])
        result = formatting.format_listing(listing, "")
        assert result["condition"] == expected

    def test_unknown_condition_label_returns_none(self, listing_factory):
        listing = listing_factory(attributes=[{"key": "condition", "value": "Onbekend"}])
        result = formatting.format_listing(listing, "")
        assert result["condition"] is None

    def test_long_description_truncated(self, listing_factory):
        listing = listing_factory(description="x" * 250)
        result = formatting.format_listing(listing, "")
        assert result["description"].endswith("...")
        assert len(result["description"]) == 203

    def test_short_description_kept(self, listing_factory):
        listing = listing_factory(description="short text")
        result = formatting.format_listing(listing, "")
        assert result["description"] == "short text"

    def test_none_description(self, listing_factory):
        listing = listing_factory(description=None)
        result = formatting.format_listing(listing, "")
        assert result["description"] == ""

    def test_no_pictures(self, listing_factory):
        listing = listing_factory(pictures=[])
        result = formatting.format_listing(listing, "")
        assert result["image"] == ""

    def test_picture_already_https(self, listing_factory):
        listing = listing_factory(pictures=[{"mediumUrl": "https://cdn.example/img.jpg"}])
        result = formatting.format_listing(listing, "")
        assert result["image"] == "https://cdn.example/img.jpg"

    def test_negative_distance_not_shown(self, listing_factory):
        listing = listing_factory(location={"cityName": "X", "distanceMeters": -1})
        result = formatting.format_listing(listing, "")
        assert result["location"]["distance_km"] is None

    def test_no_distance(self, listing_factory):
        listing = listing_factory(location={"cityName": "X", "distanceMeters": None})
        result = formatting.format_listing(listing, "")
        assert result["location"]["distance_km"] is None

    def test_no_condition_attribute(self, listing_factory):
        listing = listing_factory(attributes=[{"key": "other", "value": "x"}])
        result = formatting.format_listing(listing, "")
        assert result["condition"] is None
