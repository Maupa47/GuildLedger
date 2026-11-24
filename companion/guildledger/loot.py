"""Loot outside the game (shared/schema.md 7): Amazing Hub's points (DKP/EPGP), loot history, wishlists and raid
attendance, read from its own SavedVariables file (AmazingHub.lua, next to GuildLedger.lua) and merged into the
same SQLite file as the chat archive. The companion and the bot use the same tables and merge rules, so several
collectors uploading the same data produce each row once.

Nothing here is needed for chat or roster logging: a missing or unreadable AmazingHub.lua only skips this part.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable

from .svparse import as_dict, as_list

log = logging.getLogger(__name__)

ROW_TYPES = ("points", "standing", "loot", "wishlist", "raid")
LOOT_DUP_WINDOW = 300  # s: the same item to the same player within this is one award (each officer stamps it)
RAID_SAME_WINDOW = 2 * 3600  # s: sessions of the same raid starting this close are one raid night
_ITEM = re.compile(r"item:(\d+)")

DDL = """
CREATE TABLE IF NOT EXISTS points(
  guild TEXT NOT NULL, id TEXT NOT NULL, ts_utc INTEGER NOT NULL, pool TEXT NOT NULL, member TEXT NOT NULL,
  name TEXT NOT NULL, delta REAL NOT NULL, kind TEXT, reason TEXT, author TEXT, first_collector TEXT,
  uploaded INTEGER NOT NULL DEFAULT 0, posted INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (guild, id));
CREATE INDEX IF NOT EXISTS points_ts ON points(guild, ts_utc);
CREATE TABLE IF NOT EXISTS standings(
  guild TEXT NOT NULL, pool TEXT NOT NULL, member TEXT NOT NULL, name TEXT NOT NULL, class TEXT,
  current REAL NOT NULL DEFAULT 0, earned REAL NOT NULL DEFAULT 0, spent REAL NOT NULL DEFAULT 0, mode TEXT,
  seen_at INTEGER NOT NULL, uploaded INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (guild, pool, member));
CREATE TABLE IF NOT EXISTS loot(
  guild TEXT NOT NULL, id TEXT NOT NULL, ts_utc INTEGER NOT NULL, member TEXT NOT NULL, name TEXT NOT NULL,
  item_id INTEGER, item_name TEXT, item_link TEXT, quality INTEGER, raid TEXT, first_collector TEXT,
  uploaded INTEGER NOT NULL DEFAULT 0, posted INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (guild, id));
CREATE INDEX IF NOT EXISTS loot_ts ON loot(guild, ts_utc);
CREATE TABLE IF NOT EXISTS wishlists(
  guild TEXT NOT NULL, member TEXT NOT NULL, name TEXT NOT NULL, class TEXT, items TEXT NOT NULL,
  seen_at INTEGER NOT NULL, uploaded INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (guild, member));
CREATE TABLE IF NOT EXISTS wishes(
  guild TEXT NOT NULL, member TEXT NOT NULL, name TEXT NOT NULL, item_id INTEGER NOT NULL, item_name TEXT,
  offspec INTEGER NOT NULL DEFAULT 0, added_by INTEGER, added_at INTEGER NOT NULL,
  PRIMARY KEY (guild, member, item_id));
CREATE TABLE IF NOT EXISTS raids(
  guild TEXT NOT NULL, id TEXT NOT NULL, instance_id INTEGER, name TEXT NOT NULL, start_ts INTEGER NOT NULL,
  end_ts INTEGER, size INTEGER, guild_raid INTEGER, bosses TEXT NOT NULL DEFAULT '[]',
  players TEXT NOT NULL DEFAULT '[]', first_collector TEXT, uploaded INTEGER NOT NULL DEFAULT 0,
  posted INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (guild, id));
CREATE INDEX IF NOT EXISTS raids_start ON raids(guild, start_ts);
"""


def ensure(db: sqlite3.Connection) -> None:
    db.row_factory = sqlite3.Row
    db.executescript(DDL)


@dataclass
class LootResult:
    points_new: int = 0
    standings: int = 0
    loot_new: int = 0
    loot_dup: int = 0
    wishlists: int = 0
    raids_new: int = 0
    raids_merged: int = 0
    skipped: int = 0

    @property
    def changed(self) -> int:
        return self.points_new + self.standings + self.loot_new + self.wishlists + self.raids_new + self.raids_merged

    def add(self, other: "LootResult") -> None:
        for k in self.__dataclass_fields__:
            setattr(self, k, getattr(self, k) + getattr(other, k))

    def summary(self) -> str:
        return (f"loot: points +{self.points_new}, standings {self.standings}, items +{self.loot_new},"
                f" wishlists {self.wishlists}, raids +{self.raids_new} (merged {self.raids_merged})")


# ---------------------------------------------------------------------- helpers

def _num(v: Any, default: float | None = None) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _int(v: Any) -> int | None:
    n = _num(v)
    return int(n) if n is not None else None


def _str(v: Any) -> str:
    return v if isinstance(v, str) else ""


def member_key(name: str) -> str:
    """The key a character is stored under: its name in lower case. Forever names may have a surname; the
    whole name is kept (never split on '-' or a space)."""
    return name.strip().lower()


def item_id_of(link: str, fallback: Any = None) -> int | None:
    m = _ITEM.search(link or "")
    return int(m.group(1)) if m else _int(fallback)


def item_name_of(link: str, fallback: str = "") -> str:
    m = re.search(r"\|h\[(.*?)\]\|h", link or "")
    return m.group(1) if m else fallback


def points_id(pool: str, ts: int, member: str, delta: float, kind: str, author: str, reason: str) -> str:
    h = hashlib.sha1(reason.encode("utf-8")).hexdigest()[:8]
    return f"{pool}|{ts}|{member}|{delta:g}|{kind}|{author}|{h}"


# ---------------------------------------------------------------------- AmazingHub.lua -> upload rows

def hub_guilds(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """{"<Guild>-<Realm>": guild db} from a parsed AmazingHub.lua (skips "_noguild-…" and account-wide keys)."""
    root = data.get("AmazingHubDB")
    out = {}
    for key, gdb in as_dict(root).items():
        if isinstance(key, str) and not key.startswith("_") and isinstance(gdb, dict) and "-" in key:
            out[key] = gdb
    # Pack 0.6 saved under "<Guild>-" (no realm) after Forever's patch of 2026-11-21; 0.7 copies that to
    # "<Guild>-<Realm>" and writes there (addon/hub-extra/PackMigrate.lua). The realmless copy is then stale.
    for key in [k for k in out if k.endswith("-")]:
        if any(o != key and o.startswith(key) for o in out):
            del out[key]
    return out


def match_guild(hub_key: str, guild_names: dict[str, str]) -> str | None:
    """The GuildLedger guild (club ID) a hub key "<Guild>-<Realm>" belongs to: by name; with only one guild in
    the spool, that one."""
    for club, name in guild_names.items():
        if name and hub_key.startswith(name + "-"):
            return club
    return next(iter(guild_names)) if len(guild_names) == 1 else None


def rows_from_hub(gdb: dict[str, Any], seen: int) -> dict[str, list[dict[str, Any]]]:
    """Upload rows (shared/schema.md 7) from one guild's Amazing Hub db."""
    out: dict[str, list[dict[str, Any]]] = {k: [] for k in ROW_TYPES}
    pools = [("", gdb.get("points"))]
    for core, c in as_dict(gdb.get("cores")).items():
        if isinstance(c, dict) and isinstance(c.get("points"), dict):
            pools.append((str(core), c["points"]))
    for pool, p in pools:
        if not isinstance(p, dict):
            continue
        mode = _str(p.get("mode")) or "dkp"
        for e in as_list(p.get("log")):
            if not isinstance(e, dict):
                continue
            ts, delta, name = _int(e.get("ts")), _num(e.get("delta")), _str(e.get("name")) or _str(e.get("key"))
            if ts is None or delta is None or not name:
                continue
            member = member_key(name)
            kind, author, reason = _str(e.get("kind")) or "adjust", _str(e.get("author")), _str(e.get("reason"))
            out["points"].append({"id": points_id(pool, ts, member, delta, kind, author, reason), "pool": pool,
                                  "t": ts, "member": member, "name": name, "delta": delta, "kind": kind,
                                  "reason": reason, "by": author})
        for key, s in as_dict(p.get("standings")).items():
            if not isinstance(s, dict):
                continue
            name = _str(s.get("name")) or str(key)
            out["standing"].append({"pool": pool, "member": member_key(name), "name": name,
                                    "class": _str(s.get("class")), "cur": _num(s.get("current"), 0),
                                    "earned": _num(s.get("earned"), 0), "spent": _num(s.get("spent"), 0),
                                    "mode": mode, "seen": seen})
    for e in as_list(gdb.get("lootHistory")):
        if not isinstance(e, dict):
            continue
        ts, name, link = _int(e.get("timestamp")), _str(e.get("player")), _str(e.get("itemLink"))
        if ts is None or not name:
            continue
        item = item_id_of(link, e.get("itemId"))
        member = member_key(name)
        out["loot"].append({"id": f"{member}|{item}|{ts // LOOT_DUP_WINDOW}", "t": ts, "member": member,
                            "name": name, "item": item, "item_name": _str(e.get("itemName")) or item_name_of(link),
                            "link": link, "q": _int(e.get("quality")), "raid": _str(e.get("raid"))})
    for key, w in as_dict(gdb.get("guildWishlists")).items():
        if not isinstance(w, dict):
            continue
        name = _str(w.get("name")) or str(key)
        items = []
        for it in as_list(w.get("wishlist")):
            if isinstance(it, dict) and _int(it.get("itemId")):
                link = _str(it.get("itemLink"))
                items.append({"item": _int(it.get("itemId")), "name": item_name_of(link), "ord": _int(it.get("order")),
                              "off": bool(it.get("isOffspec"))})
        items.sort(key=lambda i: (i["ord"] is None, i["ord"] or 0))
        out["wishlist"].append({"member": member_key(name), "name": name, "class": _str(w.get("class")),
                                "items": items, "seen": seen})
    for sid, s in as_dict(as_dict(gdb.get("raidTracker")).get("sessions")).items():
        if not isinstance(s, dict):
            continue
        start = _int(s.get("startTime")) or _int(sid)
        if start is None:
            continue
        inst = _int(s.get("instanceID"))
        bosses = []
        for b in as_list(s.get("encounters")):
            if isinstance(b, dict) and b.get("name"):
                bosses.append({"id": _int(b.get("id")), "name": _str(b.get("name")), "ok": bool(b.get("success")),
                               "t": _int(b.get("endTime")) or _int(b.get("startTime"))})
        players = sorted(str(k) for k, v in as_dict(s.get("players")).items() if v)
        guild_raid = s.get("isGuildRaid")
        out["raid"].append({"id": f"{inst}|{start}", "inst": inst, "name": _str(s.get("name")) or "Raid",
                            "start": start, "end": _int(s.get("endTime")), "size": _int(s.get("size")),
                            "guild_raid": None if guild_raid is None else bool(guild_raid),
                            "bosses": bosses, "players": players})
    return out


# ---------------------------------------------------------------------- merge (companion and bot)

def merge(db: sqlite3.Connection, guild: str, kind: str, rows: Iterable[dict[str, Any]], collector: str | None,
          spool: bool = False) -> LootResult:
    """Insert/update rows of one type. spool=True (companion): changed rows are marked for upload again."""
    res = LootResult()
    fn = {"points": _merge_points, "standing": _merge_standing, "loot": _merge_loot, "wishlist": _merge_wishlist,
          "raid": _merge_raid}.get(kind)
    if fn is None:
        return res
    with db:
        for r in rows:
            try:
                fn(db, guild, r, collector, spool, res)
            except (KeyError, TypeError, ValueError):
                res.skipped += 1
    return res


def _merge_points(db, guild, r, collector, spool, res):
    cur = db.execute("INSERT OR IGNORE INTO points(guild, id, ts_utc, pool, member, name, delta, kind, reason,"
                     " author, first_collector) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (guild, str(r["id"]), int(r["t"]), str(r.get("pool") or ""), str(r["member"]), str(r["name"]),
                      float(r["delta"]), r.get("kind"), r.get("reason"), r.get("by"), collector))
    res.points_new += cur.rowcount


def _merge_standing(db, guild, r, collector, spool, res):
    seen = int(r["seen"])
    key = (guild, str(r.get("pool") or ""), str(r["member"]))
    old = db.execute("SELECT seen_at, current, earned, spent, mode FROM standings WHERE guild=? AND pool=? AND member=?",
                     key).fetchone()
    if old and old[0] >= seen:
        return
    vals = (float(r.get("cur") or 0), float(r.get("earned") or 0), float(r.get("spent") or 0), r.get("mode"))
    if old and tuple(old)[1:] == vals:  # unchanged, newer sighting: no new upload for it
        db.execute("UPDATE standings SET seen_at=? WHERE guild=? AND pool=? AND member=?", (seen, *key))
        return
    db.execute("INSERT INTO standings(guild, pool, member, name, class, current, earned, spent, mode, seen_at, uploaded)"
               " VALUES(?,?,?,?,?,?,?,?,?,?,0) ON CONFLICT(guild, pool, member) DO UPDATE SET name=excluded.name,"
               " class=excluded.class, current=excluded.current, earned=excluded.earned, spent=excluded.spent,"
               " mode=excluded.mode, seen_at=excluded.seen_at, uploaded=0",
               (guild, str(r.get("pool") or ""), str(r["member"]), str(r["name"]), r.get("class"),
                float(r.get("cur") or 0), float(r.get("earned") or 0), float(r.get("spent") or 0), r.get("mode"), seen))
    res.standings += 1


def _merge_loot(db, guild, r, collector, spool, res):
    ts, member, item = int(r["t"]), str(r["member"]), _int(r.get("item"))
    if db.execute("SELECT 1 FROM loot WHERE guild=? AND (id=? OR (member=? AND item_id IS ? AND ts_utc BETWEEN ? AND ?))",
                  (guild, str(r["id"]), member, item, ts - LOOT_DUP_WINDOW, ts + LOOT_DUP_WINDOW)).fetchone():
        res.loot_dup += 1
        return
    db.execute("INSERT INTO loot(guild, id, ts_utc, member, name, item_id, item_name, item_link, quality, raid,"
               " first_collector) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
               (guild, str(r["id"]), ts, member, str(r["name"]), item, r.get("item_name"), r.get("link"),
                _int(r.get("q")), r.get("raid"), collector))
    res.loot_new += 1


def _merge_wishlist(db, guild, r, collector, spool, res):
    seen = int(r["seen"])
    old = db.execute("SELECT seen_at, items FROM wishlists WHERE guild=? AND member=?",
                     (guild, str(r["member"]))).fetchone()
    items = json.dumps(r.get("items") or [], ensure_ascii=False, sort_keys=True)
    if old and old[0] >= seen:
        return
    if old and old[1] == items:  # unchanged list, newer sighting: no new upload for it
        db.execute("UPDATE wishlists SET seen_at=? WHERE guild=? AND member=?", (seen, guild, str(r["member"])))
        return
    db.execute("INSERT INTO wishlists(guild, member, name, class, items, seen_at, uploaded) VALUES(?,?,?,?,?,?,0)"
               " ON CONFLICT(guild, member) DO UPDATE SET name=excluded.name, class=excluded.class,"
               " items=excluded.items, seen_at=excluded.seen_at, uploaded=0",
               (guild, str(r["member"]), str(r["name"]), r.get("class"), items, seen))
    res.wishlists += 1


def _merge_raid(db, guild, r, collector, spool, res):
    start, inst = int(r["start"]), _int(r.get("inst"))
    row = db.execute("SELECT * FROM raids WHERE guild=? AND (id=? OR ((instance_id IS ? AND name=?) AND"
                     " start_ts BETWEEN ? AND ?)) ORDER BY start_ts LIMIT 1",
                     (guild, str(r["id"]), inst, str(r.get("name") or "Raid"), start - RAID_SAME_WINDOW,
                      start + RAID_SAME_WINDOW)).fetchone()
    bosses_in = [b for b in (r.get("bosses") or []) if isinstance(b, dict)]
    players_in = [str(p) for p in (r.get("players") or [])]
    end = _int(r.get("end"))
    if row is None:
        db.execute("INSERT INTO raids(guild, id, instance_id, name, start_ts, end_ts, size, guild_raid, bosses, players,"
                   " first_collector) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (guild, str(r["id"]), inst, str(r.get("name") or "Raid"), start, end, _int(r.get("size")),
                    None if r.get("guild_raid") is None else int(bool(r["guild_raid"])),
                    json.dumps(bosses_in, ensure_ascii=False), json.dumps(sorted(set(players_in)), ensure_ascii=False),
                    collector))
        res.raids_new += 1
        return
    bosses = json.loads(row["bosses"])
    names = {(b.get("name"), b.get("ok")) for b in bosses}
    for b in bosses_in:
        if (b.get("name"), b.get("ok")) not in names:
            bosses.append(b)
            names.add((b.get("name"), b.get("ok")))
    players = sorted(set(json.loads(row["players"])) | set(players_in))
    new_end = max(x for x in (row["end_ts"], end) if x is not None) if (row["end_ts"] or end) else None
    changed = (json.dumps(bosses, ensure_ascii=False) != row["bosses"]
               or json.dumps(players, ensure_ascii=False) != row["players"] or new_end != row["end_ts"])
    if not changed:
        return
    db.execute("UPDATE raids SET bosses=?, players=?, end_ts=?, uploaded=0 WHERE guild=? AND id=?",
               (json.dumps(bosses, ensure_ascii=False), json.dumps(players, ensure_ascii=False), new_end, guild,
                row["id"]))
    res.raids_merged += 1


def import_hub(db: sqlite3.Connection, data: dict[str, Any], guild_names: dict[str, str], collector: str,
               seen: int) -> LootResult:
    """Companion: a parsed AmazingHub.lua into the spool."""
    total = LootResult()
    for key, gdb in hub_guilds(data).items():
        guild = match_guild(key, guild_names)
        if guild is None:
            log.info("AmazingHub.lua: no GuildLedger guild matches %r; skipped", key)
            continue
        for kind, rows in rows_from_hub(gdb, seen).items():
            total.add(merge(db, guild, kind, rows, collector, spool=True))
    return total


# ---------------------------------------------------------------------- upload side (companion)

def pending(db: sqlite3.Connection, guild: str) -> list[tuple[str, dict[str, Any]]]:
    """Rows to upload, as (type, row) in the upload format."""
    out: list[tuple[str, dict[str, Any]]] = []
    for r in db.execute("SELECT * FROM points WHERE guild=? AND uploaded=0 ORDER BY ts_utc", (guild,)):
        out.append(("points", {"id": r["id"], "pool": r["pool"], "t": r["ts_utc"], "member": r["member"],
                               "name": r["name"], "delta": r["delta"], "kind": r["kind"], "reason": r["reason"],
                               "by": r["author"]}))
    for r in db.execute("SELECT * FROM standings WHERE guild=? AND uploaded=0", (guild,)):
        out.append(("standing", {"pool": r["pool"], "member": r["member"], "name": r["name"], "class": r["class"],
                                 "cur": r["current"], "earned": r["earned"], "spent": r["spent"], "mode": r["mode"],
                                 "seen": r["seen_at"]}))
    for r in db.execute("SELECT * FROM loot WHERE guild=? AND uploaded=0 ORDER BY ts_utc", (guild,)):
        out.append(("loot", {"id": r["id"], "t": r["ts_utc"], "member": r["member"], "name": r["name"],
                             "item": r["item_id"], "item_name": r["item_name"], "link": r["item_link"],
                             "q": r["quality"], "raid": r["raid"]}))
    for r in db.execute("SELECT * FROM wishlists WHERE guild=? AND uploaded=0", (guild,)):
        out.append(("wishlist", {"member": r["member"], "name": r["name"], "class": r["class"],
                                 "items": json.loads(r["items"]), "seen": r["seen_at"]}))
    for r in db.execute("SELECT * FROM raids WHERE guild=? AND uploaded=0 ORDER BY start_ts", (guild,)):
        out.append(("raid", {"id": r["id"], "inst": r["instance_id"], "name": r["name"], "start": r["start_ts"],
                             "end": r["end_ts"], "size": r["size"],
                             "guild_raid": None if r["guild_raid"] is None else bool(r["guild_raid"]),
                             "bosses": json.loads(r["bosses"]), "players": json.loads(r["players"])}))
    return out


def mark_uploaded(db: sqlite3.Connection, guild: str, rows: list[tuple[str, dict[str, Any]]]) -> None:
    with db:
        for kind, r in rows:
            if kind == "points":
                db.execute("UPDATE points SET uploaded=1 WHERE guild=? AND id=?", (guild, r["id"]))
            elif kind == "loot":
                db.execute("UPDATE loot SET uploaded=1 WHERE guild=? AND id=?", (guild, r["id"]))
            elif kind == "raid":
                db.execute("UPDATE raids SET uploaded=1 WHERE guild=? AND id=?", (guild, r["id"]))
            elif kind == "standing":
                db.execute("UPDATE standings SET uploaded=1 WHERE guild=? AND pool=? AND member=? AND seen_at=?",
                           (guild, r["pool"], r["member"], r["seen"]))
            elif kind == "wishlist":
                db.execute("UPDATE wishlists SET uploaded=1 WHERE guild=? AND member=? AND seen_at=?",
                           (guild, r["member"], r["seen"]))
