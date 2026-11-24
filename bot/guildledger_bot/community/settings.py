"""Bot settings an admin changes in Discord (/setup ...), kept in the archive's `state` table.

Rule (docs/dev/PLAN_COMMUNITY.md 5.5): config.toml keeps only secrets and what the process needs to start;
everything else is set live. A setting not made in Discord falls back to the given default (often config.toml).
Pure database logic, no Discord.
"""

from __future__ import annotations

import json
from typing import Any

from ..store import Archive

PREFIX = "setup."


class Settings:
    def __init__(self, archive: Archive):
        self.a = archive

    def get(self, key: str, default: Any = None) -> Any:
        v = self.a.get_state(PREFIX + key)
        if v is None or v == "":
            return default
        try:
            return json.loads(v)
        except ValueError:
            return default

    def set(self, key: str, value: Any) -> None:
        self.a.set_state(PREFIX + key, "" if value is None else json.dumps(value, sort_keys=True,
                                                                           ensure_ascii=False))

    def get_int(self, key: str, default: int = 0) -> int:
        v = self.get(key, default)
        try:
            return int(v or 0)
        except (TypeError, ValueError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        v = self.get(key, None)
        return default if v is None else bool(v)

    def all(self) -> dict[str, Any]:
        out = {}
        for r in self.a.db.execute("SELECT key, value FROM state WHERE key LIKE ? ORDER BY key", (PREFIX + "%",)):
            if r[1] == "":
                continue
            try:
                out[r[0][len(PREFIX):]] = json.loads(r[1])
            except ValueError:
                pass
        return out
