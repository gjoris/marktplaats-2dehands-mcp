"""Saved-search state, persisted to a JSON file in the user's home dir.

A saved search records the parameters of a query plus a `last_checked_at`
timestamp and `seen_ids` set. Calling `check` re-runs the query and returns
only listings whose item IDs we have not seen before.
"""

import json
import os
import time
from pathlib import Path
from typing import Any

DEFAULT_STATE_DIR = Path(
    os.environ.get("MARKTPLAATS_2DEHANDS_STATE_DIR")
    or Path.home() / ".local" / "share" / "marktplaats-2dehands-mcp"
)
DEFAULT_STATE_FILE = DEFAULT_STATE_DIR / "saved_searches.json"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "searches": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "searches": {}}


def _save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def save_search(name: str, params: dict[str, Any], path: Path = DEFAULT_STATE_FILE) -> dict[str, Any]:
    """Create or replace a saved search.

    Initial seen_ids is empty: the next `check` will surface all current
    matches as 'new'. To suppress the backfill, call check() right after.
    """
    data = _load(path)
    data["searches"][name] = {
        "params": params,
        "created_at": time.time(),
        "last_checked_at": None,
        "seen_ids": [],
    }
    _save(path, data)
    return {"name": name, "saved": True, "params": params}


def list_searches(path: Path = DEFAULT_STATE_FILE) -> list[dict[str, Any]]:
    data = _load(path)
    return [
        {
            "name": name,
            "params": entry["params"],
            "created_at": entry["created_at"],
            "last_checked_at": entry.get("last_checked_at"),
            "seen_count": len(entry.get("seen_ids", [])),
        }
        for name, entry in data["searches"].items()
    ]


def delete_search(name: str, path: Path = DEFAULT_STATE_FILE) -> bool:
    data = _load(path)
    if name not in data["searches"]:
        return False
    del data["searches"][name]
    _save(path, data)
    return True


def get_search(name: str, path: Path = DEFAULT_STATE_FILE) -> dict[str, Any] | None:
    data = _load(path)
    return data["searches"].get(name)


def record_check(
    name: str,
    new_ids: list[str],
    path: Path = DEFAULT_STATE_FILE,
) -> None:
    """Update last_checked_at and append the just-seen IDs."""
    data = _load(path)
    if name not in data["searches"]:
        return
    entry = data["searches"][name]
    entry["last_checked_at"] = time.time()
    seen = set(entry.get("seen_ids", []))
    seen.update(new_ids)
    # Cap seen_ids to last 5000 to prevent unbounded growth.
    entry["seen_ids"] = list(seen)[-5000:]
    _save(path, data)
