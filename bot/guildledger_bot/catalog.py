"""The item and recipe catalogue (shared/catalog/*.json, made by tools/build-catalog.py), read-only.

Found next to the code: the repository's shared/catalog (development), or /opt/guildledger/src/shared/catalog
(the server, copied by bot/deploy/setup.sh), or the folder in the environment variable GUILDLEDGER_CATALOG.
Missing files mean an empty catalogue; nothing fails.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path


def _dirs() -> list[Path]:
    out = []
    if os.environ.get("GUILDLEDGER_CATALOG"):
        out.append(Path(os.environ["GUILDLEDGER_CATALOG"]))
    here = Path(__file__).resolve()
    out += [here.parents[2] / "shared" / "catalog", Path("/opt/guildledger/src/shared/catalog"),
            Path("/app/shared/catalog")]
    return out


def _load(name: str, key: str):
    for d in _dirs():
        f = d / name
        if f.is_file():
            try:
                return json.loads(f.read_text("utf-8")).get(key, [])
            except (OSError, ValueError):
                return []
    return []


@lru_cache(maxsize=1)
def items() -> dict[int, dict]:
    return {int(i["id"]): i for i in _load("items.json", "items")}


@lru_cache(maxsize=1)
def recipes() -> list[dict]:
    return _load("recipes.json", "recipes")


@lru_cache(maxsize=1)
def names() -> dict[int, str]:
    """Every item's name by ID (names.json): materials, crafted goods, anything in the guild bank."""
    raw = _load("names.json", "names")
    return {int(k): v for k, v in raw.items()} if isinstance(raw, dict) else {}


def name_of(item_id: int) -> str | None:
    i = items().get(int(item_id))
    return i["name"] if i else names().get(int(item_id))


QUALITY = {2: "uncommon", 3: "rare", 4: "epic", 5: "legendary"}


def search_items(text: str, limit: int = 25) -> list[dict]:
    """Items whose name starts with the text first, then those containing it."""
    t = (text or "").strip().lower()
    if len(t) < 2:
        return []
    starts, contains = [], []
    for i in items().values():
        n = i["name"].lower()
        if n.startswith(t):
            starts.append(i)
        elif t in n:
            contains.append(i)
    key = lambda i: (i["name"], -i.get("ilvl", 0))  # noqa: E731
    return (sorted(starts, key=key) + sorted(contains, key=key))[:limit]


def label(i: dict) -> str:
    return f"{i['name']} ({QUALITY.get(i['quality'], '')} {i['slot']}, ilvl {i.get('ilvl', '?')})"[:100]
