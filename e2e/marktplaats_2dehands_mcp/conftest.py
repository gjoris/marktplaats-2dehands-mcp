"""Shared config for the E2E suite.

These tests hit the real marktplaats.nl and 2dehands.be backends. They live
under `e2e/` (top-level, sibling to `tests/`) so they're never picked up by
the default `pytest tests/` run. The dedicated `e2e` GitHub Actions
workflow invokes them on a daily schedule with `pytest e2e/ --no-cov`.

We track which (tool, site) pairs are exercised so the meta-test
`test_functional_coverage` can assert every MCP tool has been hit against
every supported site at least once during the run.
"""

import asyncio
from collections import defaultdict
from typing import Callable

import pytest

from marktplaats_2dehands_mcp import server as _server_mod
from marktplaats_2dehands_mcp.server import mcp
from marktplaats_2dehands_mcp.sites import SITES

CALL_LOG: dict[str, set[str]] = defaultdict(set)


def _wrap(name: str, fn: Callable) -> Callable:
    def wrapper(*args, **kwargs):
        site = kwargs.get("site")
        if site is None and args:
            # search_listings has site as positional arg 0; others as kw.
            # In the e2e suite all calls use kwargs, so this fallback is
            # just defensive.
            site = args[0] if isinstance(args[0], str) else None
        if site is None:
            site = "any"
        CALL_LOG[name].add(site)
        return fn(*args, **kwargs)

    wrapper.__wrapped__ = fn
    return wrapper


@pytest.fixture(autouse=True, scope="session")
def _track_tool_calls():
    tool_names = [t.name for t in asyncio.run(mcp.list_tools())]
    originals = {}
    for name in tool_names:
        original = getattr(_server_mod, name)
        originals[name] = original
        setattr(_server_mod, name, _wrap(name, original))
    yield
    for name, original in originals.items():
        setattr(_server_mod, name, original)


@pytest.fixture
def real_search_query() -> str:
    return "fiets"


@pytest.fixture(scope="session")
def expected_tools() -> list[str]:
    return [t.name for t in asyncio.run(mcp.list_tools())]


@pytest.fixture(scope="session")
def expected_sites() -> list[str]:
    return list(SITES.keys())
