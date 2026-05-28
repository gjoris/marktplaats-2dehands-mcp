"""Meta-test enforcing 100% functional coverage of MCP tools per site.

Filename starts with `zz_` so pytest discovers and runs it last (after
every other e2e file has had a chance to log its tool calls into
CALL_LOG via the autouse `_track_tool_calls` fixture in conftest).

This is the e2e equivalent of unit-test code coverage: every public MCP
tool must be exercised against every supported site at least once during
the run, otherwise we have no signal that the upstream API still works
for that combination.
"""

import pytest

from .conftest import CALL_LOG

pytestmark = pytest.mark.e2e


def test_functional_coverage(
    expected_tools: list[str],
    expected_sites: list[str],
):
    missing: list[tuple[str, str]] = []
    for tool in expected_tools:
        sites_hit = CALL_LOG.get(tool, set())
        for site in expected_sites:
            if site not in sites_hit and "any" not in sites_hit:
                missing.append((tool, site))

    assert not missing, (
        "Functional coverage gap — these (tool, site) pairs were not "
        f"exercised by the e2e suite: {missing}"
    )


def test_no_unexpected_tools_called(expected_tools: list[str]):
    unexpected = set(CALL_LOG.keys()) - set(expected_tools)
    assert not unexpected, f"e2e called tools not in MCP inventory: {unexpected}"
