# marktplaats-2dehands-mcp

An MCP (Model Context Protocol) server that lets AI assistants search
[marktplaats.nl](https://www.marktplaats.nl) (NL) and
[2dehands.be](https://www.2dehands.be) (BE) classifieds. Both sites are
operated by Adevinta and share the same internal JSON API, so a single
server covers both via a `site` parameter.

## Tools

| Tool | Description |
| --- | --- |
| `search_listings` | Keyword + filter search (price, distance, condition, category, seller type, …). |
| `get_listing_details` | Full title, description, images, stats, location for one listing. |
| `get_seller_info` | Ratings and verification status for a seller. |
| `list_categories` | Available main categories and common subcategories (shared between both sites). |
| `get_category_filters` | Per-category attribute filters (RAM, brand, frame size, …). |
| `save_search` | Persist a query as a named saved search. |
| `list_saved_searches` | Show all saved searches with last-checked timestamp. |
| `delete_saved_search` | Remove a saved search. |
| `check_saved_search` | Re-run a saved search and return only listings unseen since the last check. |

## Installation

Using `uvx` (recommended, no install needed):

```jsonc
// ~/.claude.json or claude_desktop_config.json
{
  "mcpServers": {
    "marktplaats-2dehands": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "git+https://github.com/gjoris/marktplaats-2dehands-mcp",
        "marktplaats-2dehands-mcp"
      ]
    }
  }
}
```

Or manually:

```bash
git clone https://github.com/gjoris/marktplaats-2dehands-mcp.git
cd marktplaats-2dehands-mcp
pip install -e .
```

then in your MCP config:

```jsonc
{
  "mcpServers": {
    "marktplaats-2dehands": { "command": "marktplaats-2dehands-mcp" }
  }
}
```

## Usage examples

```text
search_listings(site="2dehands", query="trek emonda", price_to=2000, zip_code="2000", distance_km=30)
search_listings(site="marktplaats", subcategory="laptops", condition="as_good_as_new")
get_listing_details(listing_id="m2404274827", site="marktplaats")

# Monitor for new bikes:
save_search(name="trek-bike-antwerp", params={
  "site": "2dehands", "query": "trek", "subcategory": "elektrische fietsen",
  "zip_code": "2000", "distance_km": 30, "price_to": 2000
})
check_saved_search(name="trek-bike-antwerp")
```

Saved-search state lives at `~/.local/share/marktplaats-2dehands-mcp/saved_searches.json`
(override with `MARKTPLAATS_2DEHANDS_STATE_DIR`).

## Anti-bot

The Adevinta `/lrp/api/search` endpoint on `www.marktplaats.nl` and
`www.2dehands.be` returns JSON, requires no auth, and currently has no
detected rate limiting. No headless browser, proxy, or stealth library is
needed. If that changes, the entry points to swap are in
`marktplaats_2dehands_mcp/api.py`.

## Attribution

This project's listing-formatting helpers (price/condition/seller-type
detection, JSON-LD parsing of detail pages) are
derived from
[PonClick/marktplaats-mcp](https://github.com/PonClick/marktplaats-mcp)
(MIT, © 2026 lessClick AI). Adapted to support both marktplaats.nl and
2dehands.be via a `site` parameter, plus saved-search persistence and a
slimmer module layout.

## License

MIT — see [LICENSE](LICENSE).
