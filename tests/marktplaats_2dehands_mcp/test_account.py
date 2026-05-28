"""Tests for the authenticated account endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import responses

from marktplaats_2dehands_mcp import account, auth


@pytest.fixture(autouse=True)
def isolated_auth_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(auth, "DEFAULT_AUTH_DIR", tmp_path / "auth")
    # Drop a fake session for marktplaats so make_session works.
    state = {
        "cookies": [
            {"name": "MpSession", "value": "tok", "domain": ".marktplaats.nl"},
        ]
    }
    path = auth.storage_state_path("marktplaats")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")
    yield


def _add(mocked, method, path, **kwargs):
    mocked.add(method, f"https://www.marktplaats.nl{path}", **kwargs)


class TestGetUnreadCounts:
    def test_returns_counts(self, mocked_responses):
        _add(mocked_responses, responses.GET, "/header/messages/message-count",
             json={"unreadMessagesCount": 3}, status=200)
        _add(mocked_responses, responses.GET, "/header/notifications/notification-count",
             json={"unreadNotificationsCount": 1}, status=200)
        result = account.get_unread_counts("marktplaats")
        assert result == {"unread_messages": 3, "unread_notifications": 1}

    def test_missing_keys_default_to_zero(self, mocked_responses):
        _add(mocked_responses, responses.GET, "/header/messages/message-count",
             json={}, status=200)
        _add(mocked_responses, responses.GET, "/header/notifications/notification-count",
             json={}, status=200)
        result = account.get_unread_counts("marktplaats")
        assert result == {"unread_messages": 0, "unread_notifications": 0}


class TestListConversations:
    def test_with_data(self, mocked_responses):
        _add(mocked_responses, responses.GET,
             "/messages/api/rpc/conversations.getConversations",
             json={"result": {"data": [{"id": "c1"}, {"id": "c2"}]}},
             status=200, match_querystring=False)
        result = account.list_conversations("marktplaats", limit=5)
        assert result["count"] == 2
        assert result["limit"] == 5
        assert result["conversations"][0]["id"] == "c1"

    def test_empty_result(self, mocked_responses):
        _add(mocked_responses, responses.GET,
             "/messages/api/rpc/conversations.getConversations",
             json={"result": {"data": []}}, status=200, match_querystring=False)
        result = account.list_conversations("marktplaats")
        assert result["count"] == 0

    def test_missing_result_key(self, mocked_responses):
        _add(mocked_responses, responses.GET,
             "/messages/api/rpc/conversations.getConversations",
             json={}, status=200, match_querystring=False)
        result = account.list_conversations("marktplaats")
        assert result["conversations"] == []


class TestListMyListings:
    def test_with_data(self, mocked_responses):
        _add(mocked_responses, responses.GET, "/my-account/sell/api/listings",
             json={"ads": [{"itemId": "m1"}], "totalNumberOfResults": 1},
             status=200, match_querystring=False)
        result = account.list_my_listings("marktplaats")
        assert result["total"] == 1
        assert result["listings"][0]["itemId"] == "m1"

    def test_query_param_passed(self, mocked_responses):
        _add(mocked_responses, responses.GET, "/my-account/sell/api/listings",
             json={"ads": [], "totalNumberOfResults": 0},
             status=200, match_querystring=False)
        account.list_my_listings("marktplaats", query="bike")
        assert "query=bike" in mocked_responses.calls[0].request.url

    def test_missing_keys(self, mocked_responses):
        _add(mocked_responses, responses.GET, "/my-account/sell/api/listings",
             json={}, status=200, match_querystring=False)
        result = account.list_my_listings("marktplaats")
        assert result["total"] == 0
        assert result["listings"] == []


class TestListFavorites:
    def test_with_items(self, mocked_responses):
        _add(mocked_responses, responses.GET, "/my-account/favorites/favorites.json",
             json={"favorites": [{"itemId": "a1"}], "moreFavoritesAvailable": True},
             status=200, match_querystring=False)
        result = account.list_favorites("marktplaats")
        assert result["more_available"] is True
        assert result["favorites"][0]["itemId"] == "a1"

    def test_empty(self, mocked_responses):
        _add(mocked_responses, responses.GET, "/my-account/favorites/favorites.json",
             json={"favorites": []}, status=200, match_querystring=False)
        result = account.list_favorites("marktplaats")
        assert result["favorites"] == []
        assert result["more_available"] is False


class TestListBidFavorites:
    def test_with_items(self, mocked_responses):
        _add(mocked_responses, responses.GET, "/my-account/bids/favorites.json",
             json={"favorites": [{"itemId": "a1"}], "moreBidsAvailable": True},
             status=200)
        result = account.list_bid_favorites("marktplaats")
        assert result["more_available"] is True
        assert len(result["bids"]) == 1


class TestListNativeSavedSearches:
    def test_returns_list(self, mocked_responses):
        _add(mocked_responses, responses.GET, "/header/searches/saved",
             json=[{"query": "fiets"}, {"query": "auto"}], status=200)
        result = account.list_native_saved_searches("marktplaats")
        assert len(result) == 2
        assert result[0]["query"] == "fiets"

    def test_unexpected_shape_raises(self, mocked_responses):
        _add(mocked_responses, responses.GET, "/header/searches/saved",
             json={"not": "a list"}, status=200)
        with pytest.raises(account.AccountError, match="Unexpected"):
            account.list_native_saved_searches("marktplaats")


class TestErrors:
    def test_http_error_wrapped(self, mocked_responses):
        _add(mocked_responses, responses.GET, "/header/messages/message-count",
             status=500)
        with pytest.raises(account.AccountError, match="Request failed"):
            account.get_unread_counts("marktplaats")

    def test_invalid_json_wrapped(self, monkeypatch):
        class FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                raise ValueError("bad json")

        from marktplaats_2dehands_mcp import account as acc_mod

        class FakeSession:
            def __init__(self):
                self.cookies = {}

            def get(self, *a, **kw):
                return FakeResp()

        monkeypatch.setattr(acc_mod, "make_session", lambda site: FakeSession())
        with pytest.raises(account.AccountError, match="Invalid JSON"):
            account.get_unread_counts("marktplaats")
