"""HTTP session factory that authenticates via stored cookies.

Returns a `requests.Session` pre-loaded with the cookies captured during
`auth_setup` and the headers that the marktplaats web frontend sends. No
Playwright is needed at runtime.
"""

from __future__ import annotations

import requests

from .auth import load_cookies
from .sites import SITES

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class NotAuthenticatedError(RuntimeError):
    """Raised when an authenticated call is attempted without a saved session."""


def make_session(site: str) -> requests.Session:
    if site not in SITES:
        raise ValueError(f"Unknown site: {site!r}")

    cookies = load_cookies(site)
    if not cookies:
        raise NotAuthenticatedError(
            f"No saved session for {site!r}. Run auth_setup(site={site!r}) first."
        )

    referer = f"https://{SITES[site]['host']}/"

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/javascript, */*",
        "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
        "Referer": referer,
        "X-Requested-With": "XMLHttpRequest",
    })
    session.cookies.update(cookies)
    return session
