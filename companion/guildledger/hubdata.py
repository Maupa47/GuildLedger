"""Hub data outside the game (shared/schema.md 8): every member's professions and recipes, the guild bank (tabs,
money, ledger) and the officers' alt links, read from Amazing Hub's own SavedVariables file (AmazingHub.lua) and
merged into the same SQLite file as the chat archive. Companion and bot use the same tables and merge rules, so
several collectors uploading the same data produce each row once. Same pattern as loot.py (section 7).

Nothing here is needed for chat or roster logging: a missing or unreadable AmazingHub.lua only skips this part.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable

from .loot import hub_guilds, match_guild
from .svparse import as_dict, as_list

log = logging.getLogger(__name__)

ROW_TYPES = ("prof", "bank_tab", "bank_money", "bank_log", "altlink")

DDL = """
CREATE TABLE IF NOT EXISTS hub_profs(
  guild TEXT NOT NULL, member TEXT NOT NULL, prof INTEGER NOT NULL, name TEXT NOT NULL, skill INTEGER, max INTEGER,
  spec INTEGER, recipes TEXT NOT NULL DEFAULT '[]', extra TEXT NOT NULL DEFAULT '[]', src TEXT, seen_at INTEGER NOT NULL,
  uploaded INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (guild, member, prof));
CREATE TABLE IF NOT EXISTS bank_tabs(
  guild TEXT NOT NULL, tab INTEGER NOT NULL, name TEXT, read_at INTEGER NOT NULL, read_by TEXT,
  slots TEXT NOT NULL DEFAULT '[]', uploaded INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (guild, tab));
CREATE TABLE IF NOT EXISTS bank_money(
  guild TEXT NOT NULL PRIMARY KEY, read_at INTEGER NOT NULL, copper INTEGER NOT NULL, read_by TEXT,
  uploaded INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS bank_log(
  guild TEXT NOT NULL, id TEXT NOT NULL, ts_utc INTEGER NOT NULL, stream INTEGER NOT NULL, kind TEXT NOT NULL,
  who TEXT, item_id INTEGER, count INTEGER, copper INTEGER, tab2 INTEGER, first_collector TEXT,
  uploaded INTEGER NOT NULL DEFAULT 0, posted INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (guild, id));
CREATE INDEX IF NOT EXISTS bank_log_ts ON bank_log(guild, ts_utc);
CREATE TABLE IF NOT EXISTS alt_links(
  guild TEXT NOT NULL, alt TEXT NOT NULL, main TEXT, author TEXT, ts INTEGER NOT NULL DEFAULT 0,
  removed INTEGER NOT NULL DEFAULT 0, legacy INTEGER NOT NULL DEFAULT 0, uploaded INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (guild, alt));
"""


def ensure(db: sqlite3.Connection) -> None:
    db.row_factory = sqlite3.Row
    db.executescript(DDL)


@dataclass
class HubResult:
    profs: int = 0
    tabs: int = 0
    money: int = 0
    log_new: int = 0
    alts: int = 0
    skipped: int = 0

    @property
    def changed(self) -> int:
        return self.profs + self.tabs + self.money + self.log_new + self.alts

    def add(self, other: "HubResult") -> None:
        for k in self.__dataclass_fields__:
            setattr(self, k, getattr(self, k) + getattr(other, k))

    def summary(self) -> str:
        return (f"hub: professions {self.profs}, bank tabs {self.tabs}, money {self.money},"
                f" ledger +{self.log_new}, alt links {self.alts}")


def _int(v: Any) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _str(v: Any) -> str:
    return v if isinstance(v, str) else ""


def name_of(key: str) -> str:
    """The character name of a hub member key "<Name>-<Realm>": what comes before the first hyphen (Forever
    names never hold one; the surname is separated by a space and kept)."""
    return key.split("-", 1)[0].strip()


def member_of(key: str) -> str:
    return name_of(key).lower()


def _ids(v: Any) -> list[int]:
    out = {_int(x) for x in as_list(v)} | {_int(x) for x in as_dict(v).values() if not isinstance(x, (dict, list))}
    return sorted(x for x in out if x and x > 0)


def log_id(k: int, t: int, ty: str, n: str, item: int | None, c: int | None, g: int | None, t2: int | None) -> str:
    raw = "|".join(str(x if x is not None else "") for x in (k, t, ty, n, item, c, g, t2))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------- AmazingHub.lua -> upload rows

def rows_from_hub(gdb: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Upload rows (shared/schema.md 8) from one guild's Amazing Hub db."""
    out: dict[str, list[dict[str, Any]]] = {k: [] for k in ROW_TYPES}
    for key, rec in as_dict(gdb.get("professions")).items():
        if not isinstance(key, str) or not isinstance(rec, dict):
            continue
        seen, src = _int(rec.get("ts")) or 0, _str(rec.get("src")) or "native"
        for line, e in as_dict(rec.get("profs")).items():
            prof = _int(line)
            if not prof:
                continue
            e = e if isinstance(e, dict) else {}
            out["prof"].append({"member": member_of(key), "name": name_of(key), "prof": prof,
                                "skill": _int(e.get("rank")), "max": _int(e.get("max")), "spec": _int(e.get("spec")),
                                "recipes": _ids(e.get("recipes")), "extra": _ids(e.get("extra")), "src": src,
                                "seen": seen})
    bank = as_dict(gdb.get("guildBank"))
    tabs = bank.get("tabs")
    tab_items = list(enumerate(tabs, 1)) if isinstance(tabs, list) else list(as_dict(tabs).items())
    for idx, t in tab_items:
        tab, t = _int(idx), t if isinstance(t, dict) else None
        if not tab or not t or not _int(t.get("ts")):
            continue
        slot_items = list(enumerate(t["slots"], 1)) if isinstance(t.get("slots"), list) else list(as_dict(t.get("slots")).items())
        slots = []
        for s, v in slot_items:
            if isinstance(v, dict) and _int(v.get("id")) and _int(s):
                slots.append([_int(s), _int(v.get("id")), _int(v.get("c")) or 1])
        slots.sort()
        out["bank_tab"].append({"tab": tab, "name": _str(t.get("name")), "t": _int(t.get("ts")),
                                "by": _str(t.get("by")), "slots": slots})
    if _int(bank.get("moneyTs")) and _int(bank.get("moneyNow")) is not None:
        out["bank_money"].append({"t": _int(bank.get("moneyTs")), "copper": _int(bank.get("moneyNow")),
                                  "by": _str(bank.get("moneyBy"))})
    seen_ids: dict[str, int] = {}
    for e in as_list(bank.get("ledger")):
        if not isinstance(e, dict) or _int(e.get("t")) is None or not _str(e.get("ty")):
            continue
        k, t, ty, n = _int(e.get("k")) or 0, _int(e.get("t")), _str(e.get("ty")), _str(e.get("n"))
        item, c, g, t2 = _int(e.get("id")), _int(e.get("c")), _int(e.get("g")), _int(e.get("t2"))
        # Two equal deposits in one hour are two lines in the hub's ledger: the second gets "#2", and so on
        # (the hub syncs its ledger, so every client holds the same lines in the same order).
        lid = log_id(k, t, ty, n, item, c, g, t2)
        seen_ids[lid] = seen_ids.get(lid, 0) + 1
        if seen_ids[lid] > 1:
            lid = f"{lid}#{seen_ids[lid]}"
        out["bank_log"].append({"id": lid, "k": k, "t": t, "ty": ty, "n": n,
                                "item": item, "c": c, "g": g, "t2": t2})
    for alt, e in as_dict(as_dict(gdb.get("altSync")).get("links")).items():
        if not isinstance(alt, str) or not isinstance(e, dict):
            continue
        out["altlink"].append({"alt": alt, "main": _str(e.get("main")) or None, "author": _str(e.get("author")),
                               "t": _int(e.get("ts")) or 0, "removed": bool(e.get("removed")),
                               "legacy": bool(e.get("legacy"))})
    return out


# ---------------------------------------------------------------------- merge (companion and bot)

def merge(db: sqlite3.Connection, guild: str, kind: str, rows: Iterable[dict[str, Any]],
          collector: str | None) -> HubResult:
    res = HubResult()
    fn = {"prof": _merge_prof, "bank_tab": _merge_tab, "bank_money": _merge_money, "bank_log": _merge_log,
          "altlink": _merge_alt}.get(kind)
    if fn is None:
        return res
    with db:
        for r in rows:
            try:
                fn(db, guild, r, collector, res)
            except (KeyError, TypeError, ValueError):
                res.skipped += 1
    return res


def _merge_prof(db, guild, r, collector, res):
    seen, src = int(r["seen"]), str(r.get("src") or "native")
    key = (guild, str(r["member"]), int(r["prof"]))
    vals = (r.get("skill"), r.get("max"), r.get("spec"), json.dumps(sorted(r.get("recipes") or [])),
            json.dumps(sorted(r.get("extra") or [])), src)
    old = db.execute("SELECT seen_at, skill, max, spec, recipes, extra, src FROM hub_profs"
                     " WHERE guild=? AND member=? AND prof=?", key).fetchone()
    if old:
        if old[0] > seen or (old[0] == seen and not (old[6] == "native" and src == "addon")):
            return
        if tuple(old)[1:] == vals:
            db.execute("UPDATE hub_profs SET seen_at=? WHERE guild=? AND member=? AND prof=?", (seen, *key))
            return
    db.execute("INSERT INTO hub_profs(guild, member, prof, name, skill, max, spec, recipes, extra, src, seen_at, uploaded)"
               " VALUES(?,?,?,?,?,?,?,?,?,?,?,0) ON CONFLICT(guild, member, prof) DO UPDATE SET name=excluded.name,"
               " skill=excluded.skill, max=excluded.max, spec=excluded.spec, recipes=excluded.recipes,"
               " extra=excluded.extra, src=excluded.src, seen_at=excluded.seen_at, uploaded=0",
               (*key, str(r.get("name") or r["member"]), *vals, seen))
    res.profs += 1


def _merge_tab(db, guild, r, collector, res):
    t, tab = int(r["t"]), int(r["tab"])
    old = db.execute("SELECT read_at FROM bank_tabs WHERE guild=? AND tab=?", (guild, tab)).fetchone()
    if old and old[0] >= t:
        return
    db.execute("INSERT INTO bank_tabs(guild, tab, name, read_at, read_by, slots, uploaded) VALUES(?,?,?,?,?,?,0)"
               " ON CONFLICT(guild, tab) DO UPDATE SET name=excluded.name, read_at=excluded.read_at,"
               " read_by=excluded.read_by, slots=excluded.slots, uploaded=0",
               (guild, tab, r.get("name"), t, r.get("by"), json.dumps(r.get("slots") or [])))
    res.tabs += 1


def _merge_money(db, guild, r, collector, res):
    t = int(r["t"])
    old = db.execute("SELECT read_at FROM bank_money WHERE guild=?", (guild,)).fetchone()
    if old and old[0] >= t:
        return
    db.execute("INSERT INTO bank_money(guild, read_at, copper, read_by, uploaded) VALUES(?,?,?,?,0)"
               " ON CONFLICT(guild) DO UPDATE SET read_at=excluded.read_at, copper=excluded.copper,"
               " read_by=excluded.read_by, uploaded=0", (guild, t, int(r["copper"]), r.get("by")))
    res.money += 1


def _merge_log(db, guild, r, collector, res):
    cur = db.execute("INSERT OR IGNORE INTO bank_log(guild, id, ts_utc, stream, kind, who, item_id, count, copper, tab2,"
                     " first_collector) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (guild, str(r["id"]), int(r["t"]), int(r.get("k") or 0), str(r["ty"]), r.get("n"),
                      _int(r.get("item")), _int(r.get("c")), _int(r.get("g")), _int(r.get("t2")), collector))
    res.log_new += cur.rowcount


def _merge_alt(db, guild, r, collector, res):
    t, alt = int(r.get("t") or 0), str(r["alt"])
    vals = (r.get("main"), r.get("author"), t, int(bool(r.get("removed"))), int(bool(r.get("legacy"))))
    old = db.execute("SELECT main, author, ts, removed, legacy FROM alt_links WHERE guild=? AND alt=?",
                     (guild, alt)).fetchone()
    if old and (old[2] > t or tuple(old) == vals):
        return
    db.execute("INSERT INTO alt_links(guild, alt, main, author, ts, removed, legacy, uploaded) VALUES(?,?,?,?,?,?,?,0)"
               " ON CONFLICT(guild, alt) DO UPDATE SET main=excluded.main, author=excluded.author, ts=excluded.ts,"
               " removed=excluded.removed, legacy=excluded.legacy, uploaded=0", (guild, alt, *vals))
    res.alts += 1


def import_hub(db: sqlite3.Connection, data: dict[str, Any], guild_names: dict[str, str], collector: str) -> HubResult:
    """Companion: a parsed AmazingHub.lua into the spool."""
    total = HubResult()
    for key, gdb in hub_guilds(data).items():
        guild = match_guild(key, guild_names)
        if guild is None:
            continue
        for kind, rows in rows_from_hub(gdb).items():
            total.add(merge(db, guild, kind, rows, collector))
    return total


# ---------------------------------------------------------------------- upload side (companion)

def pending(db: sqlite3.Connection, guild: str) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for r in db.execute("SELECT * FROM hub_profs WHERE guild=? AND uploaded=0", (guild,)):
        out.append(("prof", {"member": r["member"], "name": r["name"], "prof": r["prof"], "skill": r["skill"],
                             "max": r["max"], "spec": r["spec"], "recipes": json.loads(r["recipes"]),
                             "extra": json.loads(r["extra"]), "src": r["src"], "seen": r["seen_at"]}))
    for r in db.execute("SELECT * FROM bank_tabs WHERE guild=? AND uploaded=0", (guild,)):
        out.append(("bank_tab", {"tab": r["tab"], "name": r["name"], "t": r["read_at"], "by": r["read_by"],
                                 "slots": json.loads(r["slots"])}))
    for r in db.execute("SELECT * FROM bank_money WHERE guild=? AND uploaded=0", (guild,)):
        out.append(("bank_money", {"t": r["read_at"], "copper": r["copper"], "by": r["read_by"]}))
    for r in db.execute("SELECT * FROM bank_log WHERE guild=? AND uploaded=0 ORDER BY ts_utc", (guild,)):
        out.append(("bank_log", {"id": r["id"], "k": r["stream"], "t": r["ts_utc"], "ty": r["kind"], "n": r["who"],
                                 "item": r["item_id"], "c": r["count"], "g": r["copper"], "t2": r["tab2"]}))
    for r in db.execute("SELECT * FROM alt_links WHERE guild=? AND uploaded=0", (guild,)):
        out.append(("altlink", {"alt": r["alt"], "main": r["main"], "author": r["author"], "t": r["ts"],
                                "removed": bool(r["removed"]), "legacy": bool(r["legacy"])}))
    return out


def mark_uploaded(db: sqlite3.Connection, guild: str, rows: list[tuple[str, dict[str, Any]]]) -> None:
    with db:
        for kind, r in rows:
            if kind == "prof":
                db.execute("UPDATE hub_profs SET uploaded=1 WHERE guild=? AND member=? AND prof=? AND seen_at=?",
                           (guild, r["member"], r["prof"], r["seen"]))
            elif kind == "bank_tab":
                db.execute("UPDATE bank_tabs SET uploaded=1 WHERE guild=? AND tab=? AND read_at=?",
                           (guild, r["tab"], r["t"]))
            elif kind == "bank_money":
                db.execute("UPDATE bank_money SET uploaded=1 WHERE guild=? AND read_at=?", (guild, r["t"]))
            elif kind == "bank_log":
                db.execute("UPDATE bank_log SET uploaded=1 WHERE guild=? AND id=?", (guild, r["id"]))
            elif kind == "altlink":
                db.execute("UPDATE alt_links SET uploaded=1 WHERE guild=? AND alt=? AND ts=?", (guild, r["alt"], r["t"]))
