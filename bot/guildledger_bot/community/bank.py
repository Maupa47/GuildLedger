"""The guild bank in Discord (docs/dev/PLAN_COMMUNITY.md D5), from the hub data the collectors upload (bank_tabs,
bank_money, bank_log; shared/schema.md 8) and the item catalogue for names.

Pure logic, no Discord: what the bank channel shows (`Board.wanted`: one message per tab, items by name with
counts, when and by whom it was read; one message for the gold), which writes bring the channel there
(`Board.plan`), the ledger lines for the officers' channel (`ledger_batches`), and `/bank item:` (`search`,
`answer`). The Discord side is bank_ui.py.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .. import catalog
from .common import esc

MAX_MESSAGE = 1900
WRITES_PER_ROUND = 10
LEDGER_LINES_PER_ROUND = 200

_DDL = """
CREATE TABLE IF NOT EXISTS bank_posts(
  key TEXT PRIMARY KEY, message_ids TEXT NOT NULL DEFAULT '[]', hash TEXT, channel_id INTEGER, updated_at INTEGER);
"""

ITEM_VERBS = {"d": "deposited", "w": "took", "m": "moved"}
MONEY_VERBS = {"d": "deposited", "w": "withdrew", "r": "repaired for", "b": "bought a tab for", "s": "deposited"}


def gold(copper: int | None) -> str:
    c = int(copper or 0)
    g, s, k = c // 10000, (c // 100) % 100, c % 100
    parts = [f"{g:,}g".replace(",", "'")] if g else []
    if s or (g and k):
        parts.append(f"{s}s")
    if k or not parts:
        parts.append(f"{k}c")
    return " ".join(parts)


def item_name(item_id: int | None) -> str:
    if not item_id:
        return "?"
    return catalog.name_of(int(item_id)) or f"item {item_id}"


def bank_guild(db) -> str | None:
    r = db.execute("SELECT guild FROM bank_tabs GROUP BY guild ORDER BY MAX(read_at) DESC LIMIT 1").fetchone()
    return r[0] if r else None


def _split(header: str, lines: list[str]) -> list[str]:
    out, buf = [], header
    for line in lines:
        if len(buf) + 1 + len(line) > MAX_MESSAGE:
            out.append(buf)
            buf = line
        else:
            buf = f"{buf}\n{line}"
    out.append(buf)
    return out


@dataclass
class Write:
    action: str               # "create", "edit", "delete"
    key: str
    messages: list[str]
    message_ids: list[int] = field(default_factory=list)
    hash: str | None = None


class Board:
    def __init__(self, archive, now=time.time):
        self.db, self.now = archive.db, now
        self.db.executescript(_DDL)

    # ------------------------------------------------------------------ the bank channel

    def wanted(self) -> dict[str, list[str]]:
        """{key: messages}: "money" first, then "tab:<n>" per tab of the newest picture."""
        g = bank_guild(self.db)
        if g is None:
            return {}
        out: dict[str, list[str]] = {}
        m = self.db.execute("SELECT * FROM bank_money WHERE guild=?", (g,)).fetchone()
        if m:
            out["money"] = [f"**Guild bank gold: {gold(m['copper'])}**\nRead <t:{m['read_at']}:R>"
                            + (f" by {esc(m['read_by'])}" if m["read_by"] else "")]
        for t in self.db.execute("SELECT * FROM bank_tabs WHERE guild=? ORDER BY tab", (g,)):
            totals: dict[int, int] = defaultdict(int)
            for _slot, item, count in json.loads(t["slots"] or "[]"):
                totals[int(item)] += int(count or 1)
            lines = [f"{esc(item_name(i))} x{n}" for i, n in
                     sorted(totals.items(), key=lambda x: item_name(x[0]).lower())]
            title = f"**Tab {t['tab']}: {esc(t['name'] or '?')}** ({len(totals)} items)"
            read = f"Read <t:{t['read_at']}:R>" + (f" by {esc(t['read_by'])}" if t["read_by"] else "")
            out[f"tab:{t['tab']}"] = _split(f"{title}\n{read}", lines or ["(empty)"])
        return out

    def stored(self, channel_id: int) -> dict[str, dict[str, Any]]:
        return {r["key"]: {"ids": json.loads(r["message_ids"]), "hash": r["hash"]}
                for r in self.db.execute("SELECT * FROM bank_posts WHERE channel_id=?", (channel_id,))}

    @staticmethod
    def digest(messages: list[str]) -> str:
        return hashlib.sha256("\n\x00".join(messages).encode("utf-8")).hexdigest()[:16]

    def plan(self, channel_id: int, limit: int = WRITES_PER_ROUND) -> list[Write]:
        want, have = self.wanted(), self.stored(channel_id)
        out = [Write("delete", k, [], s["ids"]) for k, s in have.items() if k not in want]
        for k, msgs in want.items():
            h = self.digest(msgs)
            s = have.get(k)
            if s is None or not s["ids"]:
                out.append(Write("create", k, msgs, [], h))
            elif s["hash"] != h:
                out.append(Write("edit", k, msgs, s["ids"], h))
        return out[:limit]

    def done(self, channel_id: int, w: Write, ids: list[int] | None = None) -> None:
        with self.db:
            if w.action == "delete":
                self.db.execute("DELETE FROM bank_posts WHERE key=? AND channel_id=?", (w.key, channel_id))
                return
            self.db.execute("INSERT OR REPLACE INTO bank_posts VALUES(?,?,?,?,?)",
                            (w.key, json.dumps(ids or []), w.hash, channel_id, int(self.now())))

    # ------------------------------------------------------------------ the ledger (officers' channel)

    def start_ledger(self) -> int:
        """First use of a ledger channel: what is already archived counts as posted (no flood of old lines)."""
        with self.db:
            return self.db.execute("UPDATE bank_log SET posted=1 WHERE posted=0").rowcount

    def ledger_batches(self, limit: int = LEDGER_LINES_PER_ROUND) -> tuple[list[str], list[tuple[str, str]]]:
        """(messages, [(guild, id) …]) of ledger lines not posted yet, oldest first."""
        tabs = {(r["guild"], r["tab"]): r["name"] for r in self.db.execute("SELECT guild, tab, name FROM bank_tabs")}
        rows = list(self.db.execute("SELECT * FROM bank_log WHERE posted=0 ORDER BY ts_utc, id LIMIT ?", (limit,)))
        lines, keys = [], []
        for r in rows:
            who = esc(r["who"] or "?")
            if r["stream"] == 0:
                what = f"{MONEY_VERBS.get(r['kind'], r['kind'])} {gold(r['copper'])}"
                where = ""
            else:
                tab = tabs.get((r["guild"], r["stream"])) or f"Tab {r['stream']}"
                n = f"{r['count']}x " if r["count"] and r["count"] > 1 else ""
                what = f"{ITEM_VERBS.get(r['kind'], r['kind'])} {n}{esc(item_name(r['item_id']))}"
                if r["kind"] == "m" and r["tab2"]:
                    other = tabs.get((r["guild"], r["tab2"])) or f"Tab {r['tab2']}"
                    where = f" ({esc(tab)} -> {esc(other)})"
                else:
                    where = f" ({esc(tab)})"
            lines.append(f"<t:{r['ts_utc']}:f> **{who}** {what}{where}")
            keys.append((r["guild"], r["id"]))
        if not lines:
            return [], []
        out, buf = [], ""
        for line in lines:
            if buf and len(buf) + 1 + len(line) > MAX_MESSAGE:
                out.append(buf)
                buf = line
            else:
                buf = f"{buf}\n{line}" if buf else line
        out.append(buf)
        return out, keys

    def ledger_posted(self, keys: list[tuple[str, str]]) -> None:
        with self.db:
            self.db.executemany("UPDATE bank_log SET posted=1 WHERE guild=? AND id=?", keys)


# ---------------------------------------------------------------------- /bank

def _holdings(db) -> tuple[dict[int, dict[int, int]], dict[int, str], dict[int, int]]:
    """{item: {tab: count}}, {tab: name}, {tab: read_at} of the bank's newest picture."""
    g = bank_guild(db)
    held: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    names, reads = {}, {}
    if g is None:
        return {}, {}, {}
    for t in db.execute("SELECT * FROM bank_tabs WHERE guild=?", (g,)):
        names[t["tab"]], reads[t["tab"]] = t["name"] or f"Tab {t['tab']}", t["read_at"]
        for _slot, item, count in json.loads(t["slots"] or "[]"):
            held[int(item)][t["tab"]] += int(count or 1)
    return held, names, reads


def search(db, text: str, limit: int = 25) -> list[tuple[str, int]]:
    t = (text or "").strip().lower()
    held, _, _ = _holdings(db)
    hits = []
    for item, tabs in held.items():
        name = item_name(item)
        if not t or t in name.lower():
            hits.append((not name.lower().startswith(t), name.lower(), f"{name} (x{sum(tabs.values())})"[:100], item))
    hits.sort()
    return [(label, item) for _, _, label, item in hits[:limit]]


def resolve(db, text: str) -> int | None:
    t = (text or "").strip()
    if t.isdigit():
        return int(t)
    hits = search(db, t, 1)
    return hits[0][1] if hits else None


def answer(db, item: int) -> str:
    held, names, reads = _holdings(db)
    if not names:
        return "No picture of the guild bank yet: it comes once a member with Amazing Hub opens the bank."
    tabs = held.get(int(item))
    if not tabs:
        return f"The guild bank holds no **{esc(item_name(item))}** (as last read)."
    parts = [f"{esc(names[t])}: {n} (read <t:{reads[t]}:R>)" for t, n in sorted(tabs.items())]
    return f"**{esc(item_name(item))}** x{sum(tabs.values())} in the guild bank\n" + "\n".join(parts)
