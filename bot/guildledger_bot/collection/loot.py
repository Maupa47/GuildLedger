"""Loot outside the game, Discord side (shared/schema.md 7): posts to the loot channel and the queries behind
/dkp, /loot, /wishlist and /wish. Tables and merge rules: guildledger.loot (shared with the companion).

Posting (webhook [loot] webhook, off when empty):
- loot awards and points changes as compact lines, held `hold` seconds so every collector's copy is merged first;
- one summary embed per finished raid night: bosses, attendance, items, DKP standings (top N).
Rows older than the bot's first start (post_since) are archived but never posted.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from collections import OrderedDict
from datetime import datetime, tzinfo
from typing import Any

from guildledger import discord

log = logging.getLogger(__name__)

EXPORT_PREFIX = "GLW1"  # /wish export string: GLW1:<character>:<itemID>[o],<itemID>[o],... (o = off spec)
_ITEM_URL = re.compile(r"item[=/:](\d+)")


def _local(ts: int, tz: tzinfo | None) -> datetime:
    return datetime.fromtimestamp(ts, tz)


def _delta(d: float) -> str:
    return f"{d:+g}"


def _clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def main_guild(db: sqlite3.Connection) -> str | None:
    """The guild the commands answer for: the one with loot data (or the first known)."""
    for sql in ("SELECT guild FROM standings GROUP BY guild ORDER BY COUNT(*) DESC LIMIT 1",
                "SELECT guild FROM loot GROUP BY guild ORDER BY COUNT(*) DESC LIMIT 1",
                "SELECT guild FROM guilds LIMIT 1"):
        r = db.execute(sql).fetchone()
        if r:
            return r[0]
    return None


def display_names(db: sqlite3.Connection, guild: str) -> list[str]:
    return [r[0] for r in db.execute("SELECT name FROM members WHERE guild=?", (guild,))]


def nice(key: str, names: list[str]) -> str:
    """A hub player key ("Name-Realm" or a lower-case name) shown as the guild member's name when one matches.
    Matches whole names only (Forever names can contain spaces and hyphens)."""
    low = key.lower()
    best = None
    for n in names:
        nl = n.lower()
        if (low == nl or low.startswith(nl + "-")) and (best is None or len(n) > len(best)):
            best = n
    return best or key


# ---------------------------------------------------------------------- posting

class LootPoster:
    def __init__(self, db: sqlite3.Connection, hook: discord.Webhook | None, tz: tzinfo | None, hold: int = 600,
                 top: int = 10, now=time.time):
        self.db, self.hook, self.tz, self.hold, self.top, self.now = db, hook, tz, hold, top, now

    def run(self, since: int) -> int:
        """Post what is due; returns the number of rows marked posted."""
        if self.hook is None:
            return 0
        n = self._skip_before(since)
        cutoff = int(self.now()) - self.hold
        for (guild,) in self.db.execute("SELECT DISTINCT guild FROM loot WHERE posted=0 UNION "
                                        "SELECT DISTINCT guild FROM points WHERE posted=0 UNION "
                                        "SELECT DISTINCT guild FROM raids WHERE posted=0").fetchall():
            n += self._lines(guild, cutoff)
            n += self._raids(guild, cutoff)
        return n

    def _skip_before(self, since: int) -> int:
        n = 0
        with self.db:
            for table, col in (("loot", "ts_utc"), ("points", "ts_utc"), ("raids", "start_ts")):
                n += self.db.execute(f"UPDATE {table} SET posted=1 WHERE posted=0 AND {col} < ?", (since,)).rowcount
        return n

    def _lines(self, guild: str, cutoff: int) -> int:
        names = display_names(self.db, guild)
        items = self.db.execute("SELECT * FROM loot WHERE guild=? AND posted=0 AND ts_utc<=? ORDER BY ts_utc",
                                (guild, cutoff)).fetchall()
        pts = self.db.execute("SELECT * FROM points WHERE guild=? AND posted=0 AND ts_utc<=? ORDER BY ts_utc",
                              (guild, cutoff)).fetchall()
        entries: list[tuple[int, str, list[tuple[str, str]]]] = []
        for r in items:
            raid = f" ({discord.escape(r['raid'])})" if r["raid"] else ""
            entries.append((r["ts_utc"], f"`{_local(r['ts_utc'], self.tz):%H:%M}` 🎁 **{discord.escape(nice(r['name'], names))}**"
                            f" got **[{discord.escape(r['item_name'] or str(r['item_id'] or '?'))}]**{raid}",
                            [("loot", r["id"])]))
        groups: OrderedDict[tuple, list[Any]] = OrderedDict()
        for r in pts:  # one line per award: the same change to many players at once (boss kill, decay)
            groups.setdefault((r["ts_utc"], r["pool"], r["delta"], r["reason"], r["kind"], r["author"]), []).append(r)
        for (ts, pool, delta, reason, kind, author), rows in groups.items():
            who = ", ".join(discord.escape(nice(r["name"], names)) for r in rows)
            what = discord.escape(reason or kind or "")
            by = f" by {discord.escape(author)}" if author else ""
            core = f" [{discord.escape(pool)}]" if pool else ""
            entries.append((ts, _clip(f"`{_local(ts, self.tz):%H:%M}` 💰{core} **{_delta(delta)}** {what}{by}: {who}",
                                      1800), [("points", r["id"]) for r in rows]))
        if not entries:
            return 0
        entries.sort(key=lambda e: e[0])
        n, buf, ids, day = 0, [], [], None
        for ts, line, keys in entries:
            d = _local(ts, self.tz).strftime("%A %d.%m.%Y")
            head = f"**{d}**" if d != day else None
            extra = (len(head) + 1 if head else 0) + len(line) + 1
            if buf and sum(len(x) + 1 for x in buf) + extra > 1900:
                n += self._send(guild, "\n".join(buf), ids)
                buf, ids = [], []
            if head:
                buf.append(head)
                day = d
            buf.append(line)
            ids += keys
        if buf:
            n += self._send(guild, "\n".join(buf), ids)
        return n

    def _send(self, guild: str, content: str, ids: list[tuple[str, str]]) -> int:
        self.hook.post(content=content)
        with self.db:
            for table, rid in ids:
                self.db.execute(f"UPDATE {table} SET posted=1 WHERE guild=? AND id=?", (guild, rid))
        return len(ids)

    def _raids(self, guild: str, cutoff: int) -> int:
        n = 0
        for r in self.db.execute("SELECT * FROM raids WHERE guild=? AND posted=0 AND end_ts IS NOT NULL AND end_ts<=?"
                                 " ORDER BY start_ts", (guild, cutoff)).fetchall():
            if r["guild_raid"] == 0:  # the hub says: not a guild raid (under half guild members)
                with self.db:
                    self.db.execute("UPDATE raids SET posted=1 WHERE guild=? AND id=?", (guild, r["id"]))
                continue
            self.hook.post(embeds=[self.raid_embed(guild, r)])
            with self.db:
                self.db.execute("UPDATE raids SET posted=1 WHERE guild=? AND id=?", (guild, r["id"]))
            n += 1
        return n

    def raid_embed(self, guild: str, r: sqlite3.Row) -> dict[str, Any]:
        names = display_names(self.db, guild)
        start, end = r["start_ts"], r["end_ts"] or r["start_ts"]
        bosses = json.loads(r["bosses"] or "[]")
        kills = [b["name"] for b in bosses if b.get("ok")]
        wipes = sum(1 for b in bosses if not b.get("ok"))
        players = sorted({nice(p, names) for p in json.loads(r["players"] or "[]")}, key=str.lower)
        items = self.db.execute("SELECT name, item_name, item_id FROM loot WHERE guild=? AND ts_utc BETWEEN ? AND ?"
                                " ORDER BY ts_utc", (guild, start, end + 1800)).fetchall()
        fields = [
            {"name": f"Bosses killed ({len(kills)})", "value": _clip(", ".join(map(discord.escape, kills)) or "none", 1024)
             + (f"\n{wipes} wipe(s)" if wipes else ""), "inline": False},
            {"name": f"Attendance ({len(players)})", "value": _clip(", ".join(map(discord.escape, players)) or "-", 1024),
             "inline": False},
        ]
        if items:
            fields.append({"name": f"Loot ({len(items)})", "value": _clip("\n".join(
                f"{discord.escape(nice(i['name'], names))}: [{discord.escape(i['item_name'] or str(i['item_id']))}]"
                for i in items), 1024), "inline": False})
        pl = pools(self.db, guild)
        top = standings(self.db, guild, "" if "" in pl or not pl else pl[0], None, self.top)
        if top:
            fields.append({"name": f"Standings (top {len(top)})", "value": _clip("\n".join(
                f"{k}. {discord.escape(nice(s['name'], names))}: {s['current']:g}" for k, s in enumerate(top, 1)), 1024),
                "inline": False})
        minutes = max(0, (end - start) // 60)
        return {"title": _clip(f"Raid: {r['name']}", 256), "color": 0xD4AC0D,
                "description": f"{_local(start, self.tz):%A %d.%m.%Y %H:%M} - {_local(end, self.tz):%H:%M}"
                               f" ({minutes // 60} h {minutes % 60:02d} min)",
                "fields": fields, "footer": {"text": "GuildLedger · from Amazing Hub's raid tracker"}}


# ---------------------------------------------------------------------- queries for the slash commands

def standings(db: sqlite3.Connection, guild: str, pool: str = "", member: str | None = None,
              limit: int = 25) -> list[sqlite3.Row]:
    if member:
        return db.execute("SELECT * FROM standings WHERE guild=? AND pool=? AND member=?",
                          (guild, pool, member.strip().lower())).fetchall()
    return db.execute("SELECT * FROM standings WHERE guild=? AND pool=? ORDER BY current DESC, name LIMIT ?",
                      (guild, pool, limit)).fetchall()


def pools(db: sqlite3.Connection, guild: str) -> list[str]:
    return [r[0] for r in db.execute("SELECT DISTINCT pool FROM standings WHERE guild=? ORDER BY pool", (guild,))]


def recent_loot(db: sqlite3.Connection, guild: str, member: str | None = None, limit: int = 15) -> list[sqlite3.Row]:
    if member:
        return db.execute("SELECT * FROM loot WHERE guild=? AND member=? ORDER BY ts_utc DESC LIMIT ?",
                          (guild, member.strip().lower(), limit)).fetchall()
    return db.execute("SELECT * FROM loot WHERE guild=? ORDER BY ts_utc DESC LIMIT ?", (guild, limit)).fetchall()


def wishlist(db: sqlite3.Connection, guild: str, member: str) -> dict[str, Any]:
    """{name, game: [{item, name, off}], discord: [{item, name, off}], seen_at}"""
    m = member.strip().lower()
    g = db.execute("SELECT * FROM wishlists WHERE guild=? AND member=?", (guild, m)).fetchone()
    d = db.execute("SELECT * FROM wishes WHERE guild=? AND member=? ORDER BY added_at", (guild, m)).fetchall()
    return {"name": (g["name"] if g else (d[0]["name"] if d else member)),
            "game": json.loads(g["items"]) if g else [], "seen_at": g["seen_at"] if g else None,
            "discord": [{"item": r["item_id"], "name": r["item_name"], "off": bool(r["offspec"])} for r in d]}


def item_names(db: sqlite3.Connection, guild: str) -> dict[int, str]:
    """Item ID -> name, from everything the archive has seen (loot history, wishlists)."""
    out: dict[int, str] = {}
    for r in db.execute("SELECT item_id, item_name FROM loot WHERE guild=? AND item_id IS NOT NULL", (guild,)):
        if r["item_name"]:
            out[r["item_id"]] = r["item_name"]
    for r in db.execute("SELECT items FROM wishlists WHERE guild=?", (guild,)):
        for it in json.loads(r["items"]):
            if it.get("item") and it.get("name"):
                out.setdefault(int(it["item"]), it["name"])
    return out


def resolve_item(db: sqlite3.Connection, guild: str, text: str) -> tuple[int | None, str | None, str]:
    """An item typed in Discord: an item ID, a Wowhead link (…item=12345) or a name the archive knows.
    Returns (item_id, name, problem)."""
    from .. import catalog  # the generated item catalogue (shared/catalog), names for any wishable item
    t = text.strip()
    if t.isdigit():
        return int(t), item_names(db, guild).get(int(t)) or catalog.name_of(int(t)), ""
    m = _ITEM_URL.search(t)
    if m:
        iid = int(m.group(1))
        return iid, item_names(db, guild).get(iid) or catalog.name_of(iid), ""
    known = {i: c["name"] for i, c in catalog.items().items()}
    known.update(item_names(db, guild))
    exact = [(i, n) for i, n in known.items() if n.lower() == t.lower()]
    part = exact or [(i, n) for i, n in known.items() if t.lower() in n.lower()]
    if len(part) == 1:
        return part[0][0], part[0][1], ""
    if not part:
        return None, None, ("unknown item name; use the item ID or a Wowhead link (the number after item=)")
    return None, None, "several items match: " + ", ".join(f"{n} ({i})" for i, n in sorted(part, key=lambda x: x[1])[:8])


def wish_add(db: sqlite3.Connection, guild: str, character: str, item_id: int, item_name: str | None,
             offspec: bool, user_id: int) -> bool:
    with db:
        cur = db.execute("INSERT OR IGNORE INTO wishes(guild, member, name, item_id, item_name, offspec, added_by,"
                         " added_at) VALUES(?,?,?,?,?,?,?,?)",
                         (guild, character.strip().lower(), character.strip(), item_id, item_name, int(offspec),
                          user_id, int(time.time())))
    return cur.rowcount > 0


def wish_remove(db: sqlite3.Connection, guild: str, character: str, item_id: int | None) -> int:
    with db:
        if item_id is None:
            return db.execute("DELETE FROM wishes WHERE guild=? AND member=?",
                              (guild, character.strip().lower())).rowcount
        return db.execute("DELETE FROM wishes WHERE guild=? AND member=? AND item_id=?",
                          (guild, character.strip().lower(), item_id)).rowcount


def wish_export(db: sqlite3.Connection, guild: str, character: str) -> str | None:
    """The string to paste into the game: the Discord-entered wishes of one character, oldest first.
    GLW1:<character>:<itemID>[o],<itemID>[o],...  (o = off spec). None when there are none."""
    rows = db.execute("SELECT item_id, offspec, name FROM wishes WHERE guild=? AND member=? ORDER BY added_at",
                      (guild, character.strip().lower())).fetchall()
    if not rows:
        return None
    items = ",".join(f"{r['item_id']}{'o' if r['offspec'] else ''}" for r in rows)
    return f"{EXPORT_PREFIX}:{rows[0]['name']}:{items}"
