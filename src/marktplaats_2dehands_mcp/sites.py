"""Site configuration for marktplaats.nl and 2dehands.be.

Both sites are operated by Adevinta and expose the same internal JSON API
under different hostnames. The endpoints, query parameters, and response
shapes are identical — only the host (and currency/locale defaults) differ.
"""

from typing import Literal

Site = Literal["marktplaats", "2dehands"]

SITES: dict[str, dict[str, str]] = {
    "marktplaats": {
        "host": "www.marktplaats.nl",
        "link_host": "link.marktplaats.nl",
        "country": "NL",
    },
    "2dehands": {
        "host": "www.2dehands.be",
        "link_host": "link.2dehands.be",
        "country": "BE",
    },
}


def resolve(site: str) -> dict[str, str]:
    """Return config for a site, raising ValueError if unknown."""
    site_lower = site.lower()
    if site_lower not in SITES:
        raise ValueError(
            f"Unknown site: {site!r}. Valid sites: {', '.join(SITES.keys())}"
        )
    return SITES[site_lower]


def search_url(site: str) -> str:
    return f"https://{resolve(site)['host']}/lrp/api/search"


def seller_url(site: str) -> str:
    return f"https://{resolve(site)['host']}/v/api/seller-profile"


def listing_url(site: str, item_id: str) -> str:
    return f"https://{resolve(site)['link_host']}/{item_id}"
