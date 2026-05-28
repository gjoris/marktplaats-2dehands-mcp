"""Tests for the listing detail fetcher."""

from __future__ import annotations

import json
from typing import Any

import responses

from marktplaats_2dehands_mcp import listing


def _config_block(payload: dict[str, Any]) -> str:
    return f"<script>window.__CONFIG__ = {json.dumps(payload)};</script>"


def _wrap_html(*, config: dict[str, Any] | None, description_html: str = "") -> str:
    parts = ["<html><body>"]
    if description_html:
        parts.append(
            f'<div data-collapsable="description">{description_html}</div>'
        )
    if config is not None:
        parts.append(_config_block(config))
    parts.append("</body></html>")
    return "".join(parts)


def _add_listing(mocked_responses: Any, body: str, *, status: int = 200) -> None:
    mocked_responses.add(
        responses.GET,
        "https://link.marktplaats.nl/m1",
        body=body,
        status=status,
        content_type="text/html",
    )


class TestFetchListingDetails:
    def test_unknown_site(self):
        result = listing.fetch_listing_details("ebay", "m1")
        assert "error" in result

    def test_missing_id(self):
        result = listing.fetch_listing_details("marktplaats", "")
        assert "error" in result

    def test_prepends_m_prefix(self, mocked_responses):
        _add_listing(mocked_responses, _wrap_html(config={"listing": {"title": "x"}}))
        result = listing.fetch_listing_details("marktplaats", "1")
        assert result["id"] == "m1"

    def test_request_failure(self, mocked_responses):
        mocked_responses.add(
            responses.GET, "https://link.marktplaats.nl/m1", status=500
        )
        result = listing.fetch_listing_details("marktplaats", "m1")
        assert "Request failed" in result["error"]

    def test_404_returns_request_failed(self, mocked_responses):
        mocked_responses.add(
            responses.GET, "https://link.marktplaats.nl/m1", status=404,
            body="Pagina niet gevonden",
        )
        result = listing.fetch_listing_details("marktplaats", "m1")
        assert "Request failed" in result["error"]

    def test_no_config_block_returns_not_found(self, mocked_responses):
        _add_listing(mocked_responses, "<html><body>nothing here</body></html>")
        result = listing.fetch_listing_details("marktplaats", "m1")
        assert result == {"error": "Listing not found"}

    def test_invalid_config_json(self, mocked_responses):
        body = "<html><body><script>window.__CONFIG__ = {bad json};</script></body></html>"
        _add_listing(mocked_responses, body)
        result = listing.fetch_listing_details("marktplaats", "m1")
        assert result == {"error": "Invalid listing payload"}

    def test_config_without_listing_key(self, mocked_responses):
        _add_listing(mocked_responses, _wrap_html(config={"other": 1}))
        result = listing.fetch_listing_details("marktplaats", "m1")
        assert result == {"error": "Listing not found"}

    def test_listing_value_not_object(self, mocked_responses):
        _add_listing(mocked_responses, _wrap_html(config={"listing": "string"}))
        result = listing.fetch_listing_details("marktplaats", "m1")
        assert result == {"error": "Listing not found"}

    def test_full_payload(self, mocked_responses):
        config = {
            "listing": {
                "title": "Test Bike",
                "priceInfo": {"priceCents": 15000, "priceType": "FIXED"},
                "gallery": {
                    "imageUrls": [
                        "//cdn.example/img1.jpg",
                        "https://cdn.example/img2.jpg",
                    ]
                },
                "stats": {
                    "viewCount": 500,
                    "favoritedCount": 3,
                    "since": "2026-05-28T07:49:18Z",
                },
                "seller": {"location": {"cityName": "Amsterdam"}},
            }
        }
        description_html = (
            "Line one.<br /><br />Line two.<br />Line three."
        )
        _add_listing(
            mocked_responses,
            _wrap_html(config=config, description_html=description_html),
        )
        result = listing.fetch_listing_details("marktplaats", "m1")
        assert result["title"] == "Test Bike"
        assert result["price_cents"] == 15000
        assert result["price"] == "€ 150.00"
        assert result["images"] == [
            "https://cdn.example/img1.jpg",
            "https://cdn.example/img2.jpg",
        ]
        assert result["image_count"] == 2
        assert result["description_full"] == "Line one.\nLine two.\nLine three."
        assert result["description_short"].startswith("Line one.")
        assert result["statistics"] == {
            "views": 500,
            "saved": 3,
            "online_since": "2026-05-28T07:49:18Z",
        }
        assert result["location"] == "Amsterdam"

    def test_short_description_truncation(self, mocked_responses):
        long = "A" * 300
        _add_listing(
            mocked_responses,
            _wrap_html(
                config={"listing": {"title": "x"}}, description_html=long
            ),
        )
        result = listing.fetch_listing_details("marktplaats", "m1")
        assert len(result["description_short"]) == 160
        assert result["description_full"] == long

    def test_empty_listing_object_returns_minimal(self, mocked_responses):
        _add_listing(mocked_responses, _wrap_html(config={"listing": {}}))
        result = listing.fetch_listing_details("marktplaats", "m1")
        assert result == {
            "id": "m1",
            "site": "marktplaats",
            "url": "https://link.marktplaats.nl/m1",
        }

    def test_price_cents_non_int_skipped(self, mocked_responses):
        _add_listing(
            mocked_responses,
            _wrap_html(
                config={"listing": {"priceInfo": {"priceCents": "750"}}}
            ),
        )
        result = listing.fetch_listing_details("marktplaats", "m1")
        assert "price" not in result
        assert "price_cents" not in result

    def test_partial_stats(self, mocked_responses):
        _add_listing(
            mocked_responses,
            _wrap_html(config={"listing": {"stats": {"viewCount": 7}}}),
        )
        result = listing.fetch_listing_details("marktplaats", "m1")
        assert result["statistics"] == {"views": 7}

    def test_missing_seller_location(self, mocked_responses):
        _add_listing(
            mocked_responses,
            _wrap_html(config={"listing": {"seller": {}}}),
        )
        result = listing.fetch_listing_details("marktplaats", "m1")
        assert "location" not in result

    def test_2dehands_host(self, mocked_responses):
        mocked_responses.add(
            responses.GET,
            "https://link.2dehands.be/m1",
            body=_wrap_html(config={"listing": {"title": "x"}}),
            status=200,
            content_type="text/html",
        )
        result = listing.fetch_listing_details("2dehands", "m1")
        assert result["site"] == "2dehands"
        assert result["title"] == "x"

    def test_no_description_div(self, mocked_responses):
        _add_listing(
            mocked_responses,
            _wrap_html(config={"listing": {"title": "x"}}),
        )
        result = listing.fetch_listing_details("marktplaats", "m1")
        assert "description_full" not in result
        assert "description_short" not in result

    def test_unicode_escaped_image_urls(self, mocked_responses):
        # The real site emits image URLs with / escapes.
        body = (
            "<html><body>"
            "<script>window.__CONFIG__ = {\"listing\":{"
            "\"gallery\":{\"imageUrls\":[\"\\u002F\\u002Fcdn.example\\u002Fa.jpg\"]}"
            "}};</script></body></html>"
        )
        _add_listing(mocked_responses, body)
        result = listing.fetch_listing_details("marktplaats", "m1")
        assert result["images"] == ["https://cdn.example/a.jpg"]
