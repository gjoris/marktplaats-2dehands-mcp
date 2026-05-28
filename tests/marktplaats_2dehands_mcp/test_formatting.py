"""Tests for formatting helpers."""

from datetime import datetime, timedelta
from unittest.mock import patch

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

    def test_business_via_name_pattern(self):
        assert formatting.detect_seller_type([], "MyShop Webshop") == "business"
        assert formatting.detect_seller_type([], "Acme B.V.") == "business"
        assert formatting.detect_seller_type([], "example.nl") == "business"
        assert formatting.detect_seller_type([], "example.com") == "business"
        assert formatting.detect_seller_type([], "example.be") == "business"
        assert formatting.detect_seller_type([], "Used Products") == "business"
        assert formatting.detect_seller_type([], "Buy & Sell Co") == "business"
        assert formatting.detect_seller_type([], "Mediahoek") == "business"
        assert formatting.detect_seller_type([], "IT-Resale") == "business"
        assert formatting.detect_seller_type([], "Acme Handel") == "business"
        assert formatting.detect_seller_type([], "Best Electronics") == "business"
        assert formatting.detect_seller_type([], "Refurbished Pro") == "business"
        assert formatting.detect_seller_type([], "Phone Outlet") == "business"
        assert formatting.detect_seller_type([], "Cool Store") == "business"

    def test_private_default(self):
        assert formatting.detect_seller_type([]) == "private"
        assert formatting.detect_seller_type([], "Jan Jansen") == "private"

    def test_traits_take_precedence(self):
        assert formatting.detect_seller_type(["VERIFIED_SELLER"], "Jan Jansen") == "business"


class TestFormatDateShort:
    def test_empty_returns_empty(self):
        assert formatting.format_date_short("") == ""

    @pytest.mark.parametrize(
        "input_str,expected",
        [
            ("Vandaag", "0d"),
            ("Gisteren", "1d"),
            ("Eergisteren", "2d"),
        ],
    )
    def test_keyword_dates(self, input_str, expected):
        assert formatting.format_date_short(input_str) == expected

    def test_dutch_date_days(self):
        # Pin "now" so the calculation is deterministic.
        with patch.object(formatting, "datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 25)
            mock_dt.side_effect = datetime
            assert formatting.format_date_short("22 jan '26") == "3d"

    def test_dutch_date_weeks(self):
        with patch.object(formatting, "datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 25)
            mock_dt.side_effect = datetime
            assert formatting.format_date_short("10 jan '26") == "2w"

    def test_dutch_date_months(self):
        with patch.object(formatting, "datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 25)
            mock_dt.side_effect = datetime
            assert formatting.format_date_short("10 jan '26") == "5m"

    def test_unparseable_date_returned_as_is(self):
        assert formatting.format_date_short("zomaar wat tekst") == "zomaar wat tekst"

    def test_invalid_month_falls_through(self):
        # Three-letter token that isn't in the month map.
        result = formatting.format_date_short("10 xyz '26")
        assert result == "10 xyz '26"

    def test_invalid_day_returns_input(self):
        # "32 jan" raises ValueError inside datetime — should fall through.
        result = formatting.format_date_short("32 jan '26")
        assert result == "32 jan '26"


class TestFormatConditionShort:
    @pytest.mark.parametrize(
        "input_str,expected",
        [
            (None, ""),
            ("", ""),
            ("Nieuw", "N"),
            ("Zo goed als nieuw", "Z"),
            ("Gebruikt", "G"),
            ("Refurbished", "R"),
            ("Defect", "D"),
            ("Niet werkend", "D"),
            ("onbekende staat", ""),
        ],
    )
    def test_format_condition_short(self, input_str, expected):
        assert formatting.format_condition_short(input_str) == expected


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
        assert result["condition"] == "Gebruikt"
        assert result["location"] == {"city": "Amsterdam", "distance_km": 5.0}
        assert result["seller"]["type"] == "private"
        assert result["image"] == "https://example.com/img.jpg"
        assert result["link"] == "https://link.example/m1"

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


class TestFormatListingCompact:
    def test_compact_basic(self, listing_factory):
        listing = listing_factory(
            attributes=[{"key": "condition", "value": "Nieuw"}],
        )
        result = formatting.format_listing_compact(listing)
        assert result["id"] == "m1"
        assert result["price"] == 10
        assert result["seller"] == "P"
        assert result["cond"] == "N"
        assert result["age"] == "0d"
        assert result["km"] == 5.0

    # The `or price_cents == 0` short-circuit makes any 0-cent listing return 0
    # regardless of the priceType. We lock in this pre-existing upstream behavior
    # for the baseline; the compact mode is dropped in PR2 anyway.
    @pytest.mark.parametrize(
        "price_type,cents,expected",
        [
            ("FIXED", 1500, 15),
            ("RESERVED", 1500, 15),
            ("FREE", 0, 0),
            ("FIXED", 0, 0),
            ("BID", 100, "bid"),
            ("BID", 0, 0),
            ("BID_FROM", 1000, ">10"),
            ("SEE_DESCRIPTION", 100, "?"),
            ("SEE_DESCRIPTION", 0, 0),
            ("TO_BE_AGREED_UPON", 100, "notk"),
            ("EXCHANGE", 100, "ruil"),
            ("WEIRD_TYPE", 1234, 12),
            ("WEIRD_TYPE", 0, 0),
        ],
    )
    def test_price_variants(self, listing_factory, price_type, cents, expected):
        listing = listing_factory(priceInfo={"priceType": price_type, "priceCents": cents})
        result = formatting.format_listing_compact(listing)
        assert result["price"] == expected

    def test_business_seller(self, listing_factory):
        listing = listing_factory(
            sellerInformation={"sellerId": 1, "sellerName": "Acme Webshop"},
        )
        result = formatting.format_listing_compact(listing)
        assert result["seller"] == "B"

    def test_optional_fields_omitted(self, listing_factory):
        listing = listing_factory(
            location={"cityName": "X", "distanceMeters": None},
            attributes=[],
            date="",
        )
        result = formatting.format_listing_compact(listing)
        assert "km" not in result
        assert "cond" not in result
        assert "age" not in result
