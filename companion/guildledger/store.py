"""Local SQLite spool (spool.db). Same tables as the bot's archive plus ``uploaded``.

Import is idempotent: rows are keyed by the IDs in shared/schema.md, so importing the same
SavedVariables file twice adds nothing.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from . import loot
from .svparse import as_dict, as_list

log = logging.getLogger(__name__)

SCHEMAS_READ = (1, 2, 3)  # 2: chat key rb -> relayed_by; 3: guilds[..].links (Discord link requests)
STREAMS = {"g", "o", "d", "x"}
CHAT_SRC = {"live", "meta", "event"}
EVENT_KINDS = {"join", "leave", "kick", "promote", "demote"}
EVENT_SRC = {"sys", "diff", "log"}
MERGE_WINDOW = 3  # seconds, event row <-> club row
SYS_BUCKET = 5  # seconds, sys event ID bucket
UNKNOWN_AUTHOR = "?"  # addon writes this when the club message had no readable author name
SUPERSEDE_WINDOW = 12 * 3600
LOG_DUP_WINDOW = 2 * 3600  # log rows: elapsed-hour times drift into the neighbouring bucket
FAMILY = {"join": ("join",), "leave": ("leave", "kick"), "kick": ("leave", "kick"),
          "promote": ("promote",), "demote": ("demote",)}  # leave/kick: both mean "gone"

_DDL = """
CREATE TABLE IF NOT EXISTS guilds(
  guild TEXT PRIMARY KEY, name TEXT);
CREATE TABLE IF NOT EXISTS chat(
  guild TEXT NOT NULL, id TEXT NOT NULL, stream TEXT NOT NULL, ts_utc INTEGER NOT NULL,
  author TEXT NOT NULL, guid TEXT, text TEXT, from_discord INTEGER NOT NULL DEFAULT 0,
  edited INTEGER NOT NULL DEFAULT 0, deleted INTEGER NOT NULL DEFAULT 0, src TEXT NOT NULL,
  first_collector TEXT, posted INTEGER NOT NULL DEFAULT 0, uploaded INTEGER NOT NULL DEFAULT 0,
  relayed_by TEXT,
  PRIMARY KEY (guild, stream, id));
CREATE INDEX IF NOT EXISTS chat_ts ON chat(guild, ts_utc);
CREATE INDEX IF NOT EXISTS chat_stream_ts ON chat(guild, stream, ts_utc);
CREATE TABLE IF NOT EXISTS events(
  guild TEXT NOT NULL, id TEXT NOT NULL, ts_utc INTEGER NOT NULL, precise INTEGER NOT NULL,
  kind TEXT NOT NULL, name TEXT NOT NULL, guid TEXT, actor TEXT, detail TEXT, src TEXT NOT NULL,
  first_collector TEXT, superseded_by TEXT, posted INTEGER NOT NULL DEFAULT 0,
  uploaded INTEGER NOT NULL DEFAULT 0, window_from INTEGER,
  PRIMARY KEY (guild, id));
CREATE INDEX IF NOT EXISTS events_ts ON events(guild, ts_utc);
CREATE TABLE IF NOT EXISTS members(
  guild TEXT NOT NULL, guid TEXT NOT NULL, name TEXT NOT NULL, first_seen INTEGER,
  last_seen INTEGER, in_guild INTEGER NOT NULL DEFAULT 1,
  rank_name TEXT, rank_index INTEGER, level INTEGER, class TEXT,
  PRIMARY KEY (guild, guid));
CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS link_rows(
  guild TEXT NOT NULL, id TEXT NOT NULL, ts_utc INTEGER NOT NULL, kind TEXT NOT NULL, code TEXT, tag TEXT NOT NULL,
  name TEXT NOT NULL, guid TEXT, first_collector TEXT, uploaded INTEGER NOT NULL DEFAULT 0,
  processed INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (guild, id));
"""


class SchemaError(ValueError):
    pass


@dataclass
class ImportResult:
    chat_new: int = 0
    chat_updated: int = 0
    chat_merged: int = 0  # event rows folded into a club row
    chat_dup: int = 0  # event rows dropped because the club row already has text
    events_new: int = 0
    events_dup: int = 0
    events_updated: int = 0  # actor filled in on a log row
    members_new: int = 0
    links_new: int = 0
    skipped: int = 0  # malformed rows
    min_ts: int | None = None  # oldest timestamp among changed chat/event rows
    guilds: list[str] = field(default_factory=list)

    def touch(self, ts: int) -> None:
        self.min_ts = ts if self.min_ts is None else min(self.min_ts, ts)

    @property
    def changed(self) -> int:
        return (self.chat_new + self.chat_updated + self.chat_merged + self.events_new + self.events_updated
                + self.members_new + self.links_new)

    def summary(self) -> str:
        return (f"chat +{self.chat_new} (updated {self.chat_updated}, merged {self.chat_merged}), "
                f"events +{self.events_new}, members +{self.members_new}, skipped {self.skipped}")


class Spool:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(_DDL)
        loot.ensure(self.db)  # Amazing Hub's loot data (shared/schema.md 7)
        self._migrate()

    def _migrate(self) -> None:
        """Additive column changes for spools created by older versions."""
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(events)")}
        if "window_from" not in cols:
            with self.db:
                self.db.execute("ALTER TABLE events ADD COLUMN window_from INTEGER")
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(chat)")}
        if "relayed_by" not in cols:  # schema 2
            with self.db:
                self.db.execute("ALTER TABLE chat ADD COLUMN relayed_by TEXT")
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(members)")}
        with self.db:  # pack step R: roster details for the bot
            for col, typ in (("rank_name", "TEXT"), ("rank_index", "INTEGER"), ("level", "INTEGER"),
                             ("class", "TEXT")):
                if col not in cols:
                    self.db.execute(f"ALTER TABLE members ADD COLUMN {col} {typ}")

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Spool":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ------------------------------------------------------------------ import

    def import_sv(self, data: dict[str, Any], collector: str) -> ImportResult:
        """Import a parsed SavedVariables chunk (the dict from svparse.parse)."""
        root = data.get("GuildLedgerDB")
        if not isinstance(root, dict):
            raise SchemaError("no GuildLedgerDB table in file")
        schema = root.get("schema")
        if schema not in SCHEMAS_READ:
            raise SchemaError(f"unsupported schema {schema!r} (this version reads {SCHEMAS_READ})")
        res = ImportResult()
        with self.db:
            for club_id, g in as_dict(root.get("guilds")).items():
                if not isinstance(g, dict):
                    continue
                guild = str(club_id)
                res.guilds.append(guild)
                self._guild(guild, g.get("name"))
                for row in as_list(g.get("chat")):
                    self._chat(guild, row, collector, res)
                for row in as_list(g.get("ev")):
                    self._event(guild, row, collector, res)
                self.import_links(guild, as_list(g.get("links")), collector, res)
                roster = as_dict(g.get("roster"))
                if roster:
                    members = [dict(m, g=guid) for guid, m in roster.items() if isinstance(m, dict)]
                    self.import_roster(guild, _int(g.get("rosterAt")), members, res)
                self._supersede(guild)
        return res

    def import_rows(self, guild: str, name: str | None, chat: list[Any], events: list[Any],
                    collector: str) -> ImportResult:
        """Import rows in SavedVariables key format (the upload format, shared/schema.md 4)."""
        res = ImportResult(guilds=[guild])
        with self.db:
            self._guild(guild, name)
            for row in chat:
                self._chat(guild, row, collector, res)
            for row in events:
                self._event(guild, row, collector, res)
            self._supersede(guild)
        return res

    def _guild(self, guild: str, name: Any) -> None:
        name = name if isinstance(name, str) and name else None
        self.db.execute(
            "INSERT INTO guilds(guild, name) VALUES(?, ?) "
            "ON CONFLICT(guild) DO UPDATE SET name = COALESCE(excluded.name, guilds.name)",
            (guild, name),
        )

    # chat ---------------------------------------------------------------------

    def _chat(self, guild: str, r: Any, collector: str, res: ImportResult) -> None:
        row = _chat_row(r)
        if row is None:
            res.skipped += 1
            return
        db = self.db
        cur = db.execute(
            "SELECT text, edited, deleted, author, from_discord, posted FROM chat WHERE guild=? AND stream=? AND id=?",
            (guild, row["stream"], row["id"]),
        ).fetchone()
        if cur is not None:
            sets, args = [], []
            if row["edited"] and not cur["edited"]:
                sets.append("edited=1")
            if row["deleted"] and not cur["deleted"]:
                sets.append("deleted=1")
            if cur["text"] is None and row["text"] is not None:
                sets += ["text=?", "src='live'", "relayed_by=?"]
                args += [row["text"], row["relayed_by"]]
                if cur["posted"] and not row["posted"]:
                    # it went out as "text not captured": post it again, now with text, as a late entry
                    sets.append("posted=0")
            if cur["author"] == UNKNOWN_AUTHOR and row["author"] != UNKNOWN_AUTHOR:
                sets.append("author=?")
                args.append(row["author"])
            if row["fd"] and not cur["from_discord"]:
                sets.append("from_discord=1")
            if row["posted"] and not cur["posted"]:
                # another collector's copy, but this collector showed it in Discord already (direct mode)
                db.execute("UPDATE chat SET posted=1 WHERE guild=? AND stream=? AND id=?",
                           (guild, row["stream"], row["id"]))
            if sets:
                sets.append("uploaded=0")  # the improved row goes to the bot again
                db.execute(f"UPDATE chat SET {', '.join(sets)} WHERE guild=? AND stream=? AND id=?",
                           (*args, guild, row["stream"], row["id"]))
                res.chat_updated += 1
                res.touch(row["t"])
            return

        replaced = False
        if row["src"] == "event":
            partner = self._near(guild, row, "src IN ('meta','live')",
                                 order="(text IS NOT NULL), ABS(ts_utc - ?)")
            if partner is not None:
                if partner["text"] is None:
                    db.execute("UPDATE chat SET text=?, src='live', uploaded=0 WHERE guild=? AND stream=? AND id=?",
                               (row["text"], guild, row["stream"], partner["id"]))
                    res.chat_merged += 1
                    res.touch(row["t"])
                else:
                    res.chat_dup += 1
                return
        else:
            ev = self._near(guild, row, "src='event'", order="ABS(ts_utc - ?)")
            if ev is not None:
                # The club row takes over: keep its ID, take the text if it has none, inherit flags.
                if row["text"] is None:
                    row["text"], row["src"] = ev["text"], "live"
                row["posted"], row["uploaded"] = max(row["posted"], ev["posted"]), 0  # new ID: bot has not seen it
                db.execute("DELETE FROM chat WHERE guild=? AND stream=? AND id=?", (guild, row["stream"], ev["id"]))
                res.chat_merged += 1
                replaced = True

        db.execute(
            "INSERT INTO chat(guild, id, stream, ts_utc, author, guid, text, from_discord, edited, deleted, src,"
            " first_collector, posted, uploaded, relayed_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (guild, row["id"], row["stream"], row["t"], row["author"], row["guid"], row["text"], row["fd"],
             row["edited"], row["deleted"], row["src"], collector, row.get("posted", 0), row.get("uploaded", 0),
             row["relayed_by"]),
        )
        if not replaced:
            res.chat_new += 1
        res.touch(row["t"])

    def _near(self, guild: str, row: dict[str, Any], cond: str, order: str) -> sqlite3.Row | None:
        """A row of the same author in the same stream within ±MERGE_WINDOW s."""
        return self.db.execute(
            f"SELECT id, text, posted, uploaded FROM chat WHERE guild=? AND stream=? AND {cond}"
            " AND ts_utc BETWEEN ? AND ? AND ((guid IS NOT NULL AND guid = ?) OR author = ?)"
            f" ORDER BY {order} LIMIT 1",
            (guild, row["stream"], row["t"] - MERGE_WINDOW, row["t"] + MERGE_WINDOW, row["guid"],
             row["author"], row["t"]),
        ).fetchone()

    # events -------------------------------------------------------------------

    def _event(self, guild: str, r: Any, collector: str, res: ImportResult) -> None:
        row = _event_row(r)
        if row is None:
            res.skipped += 1
            return
        db = self.db
        same = db.execute("SELECT actor FROM events WHERE guild=? AND id=?", (guild, row["id"])).fetchone()
        if same:
            if same["actor"] is None and row["actor"] is not None:
                db.execute("UPDATE events SET actor=?, uploaded=0 WHERE guild=? AND id=?",
                           (row["actor"], guild, row["id"]))
                res.events_updated += 1
                res.touch(row["t"])
            else:
                res.events_dup += 1
            return
        if row["src"] == "sys":
            # Two collectors may land in adjacent 5 s buckets for the same system message.
            near = db.execute(
                "SELECT 1 FROM events WHERE guild=? AND src='sys' AND kind=? AND name=? AND COALESCE(actor,'')=?"
                " AND ABS(ts_utc - ?) < ?",
                (guild, row["kind"], row["name"], row["actor"] or "", row["t"], 2 * SYS_BUCKET),
            ).fetchone()
            if near:
                res.events_dup += 1
                return
        elif row["src"] == "log":
            # A log entry may arrive once without its actor and once with it: a missing actor matches.
            near = db.execute(
                "SELECT id, actor FROM events WHERE guild=? AND src='log' AND kind=? AND name=?"
                " AND (actor IS NULL OR ? IS NULL OR actor=?) AND ABS(ts_utc - ?) <= ?"
                " ORDER BY (actor IS NULL), ABS(ts_utc - ?) LIMIT 1",
                (guild, row["kind"], row["name"], row["actor"], row["actor"], row["t"], LOG_DUP_WINDOW, row["t"]),
            ).fetchone()
            if near:
                if near["actor"] is None and row["actor"] is not None:
                    db.execute("UPDATE events SET actor=?, uploaded=0 WHERE guild=? AND id=?",
                               (row["actor"], guild, near["id"]))
                    res.events_updated += 1
                    res.touch(row["t"])
                else:
                    res.events_dup += 1
                return
        elif row["src"] == "diff" and self._merge_diff(guild, row, res):
            return
        db.execute(
            "INSERT INTO events(guild, id, ts_utc, precise, kind, name, guid, actor, detail, src, first_collector,"
            " window_from, posted) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (guild, row["id"], row["t"], row["p"], row["kind"], row["name"], row["guid"], row["actor"],
             row["detail"], row["src"], collector, row["w"], row["posted"]),
        )
        res.events_new += 1
        res.touch(row["t"])

    def _merge_diff(self, guild: str, row: dict[str, Any], res: ImportResult) -> bool:
        """Two collectors' roster comparisons of the same change: same kind and member, overlapping
        windows [w, t]. Keep one row with the intersection (the tighter window)."""
        w = row["w"] if row["w"] is not None else row["t"] - SUPERSEDE_WINDOW
        other = self.db.execute(
            "SELECT id, ts_utc, window_from, posted FROM events WHERE guild=? AND src='diff' AND kind=?"
            " AND ((guid IS NOT NULL AND guid=?) OR name=?) AND superseded_by IS NULL"
            " AND COALESCE(window_from, ts_utc - ?) < ? AND ts_utc > ? LIMIT 1",  # windows overlap
            (guild, row["kind"], row["guid"], row["name"], SUPERSEDE_WINDOW, row["t"], w),
        ).fetchone()
        if other is None:
            return False
        lo = max(w, other["window_from"] if other["window_from"] is not None else other["ts_utc"] - SUPERSEDE_WINDOW)
        hi = min(row["t"], other["ts_utc"])
        if not other["posted"] and (hi < other["ts_utc"] or lo != other["window_from"]):
            self.db.execute("UPDATE events SET ts_utc=?, window_from=?, uploaded=0 WHERE guild=? AND id=?",
                            (hi, lo, guild, other["id"]))
            res.events_updated += 1
        else:
            res.events_dup += 1
        return True

    # ------------------------------------------------------------------ upload (companion, mode "upload")

    def pending_upload(self, guild: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Rows not yet uploaded, in the SavedVariables key format of shared/schema.md 1."""
        chat = [_chat_wire(r) for r in self.db.execute(
            "SELECT * FROM chat WHERE guild=? AND uploaded=0 ORDER BY ts_utc, id", (guild,))]
        events = [_event_wire(r) for r in self.db.execute(
            "SELECT * FROM events WHERE guild=? AND uploaded=0 ORDER BY ts_utc, rowid", (guild,))]
        return chat, events

    def mark_uploaded(self, guild: str, chat_keys: list[tuple[str, str]], event_ids: list[str]) -> None:
        with self.db:
            self.db.executemany("UPDATE chat SET uploaded=1 WHERE guild=? AND stream=? AND id=?",
                                [(guild, s, i) for s, i in chat_keys])
            self.db.executemany("UPDATE events SET uploaded=1 WHERE guild=? AND id=?",
                                [(guild, i) for i in event_ids])

    def _supersede(self, guild: str) -> None:
        """diff/log rows lose to a sys row of the same family+target within 12 h; log beats diff."""
        db = self.db
        weak = db.execute(
            "SELECT id, ts_utc, kind, name, src FROM events"
            " WHERE guild=? AND src IN ('diff','log') AND superseded_by IS NULL AND posted=0",
            (guild,),
        ).fetchall()
        for w in weak:
            better_src = "('sys')" if w["src"] == "log" else "('sys','log')"
            kinds = FAMILY.get(w["kind"], (w["kind"],))
            b = db.execute(
                f"SELECT id FROM events WHERE guild=? AND src IN {better_src}"
                f" AND kind IN ({','.join('?' * len(kinds))}) AND name=?"
                " AND superseded_by IS NULL AND ABS(ts_utc - ?) <= ?"
                " ORDER BY CASE src WHEN 'sys' THEN 0 ELSE 1 END, ABS(ts_utc - ?) LIMIT 1",
                (guild, *kinds, w["name"], w["ts_utc"], SUPERSEDE_WINDOW, w["ts_utc"]),
            ).fetchone()
            if b is not None:
                db.execute("UPDATE events SET superseded_by=? WHERE guild=? AND id=?", (b["id"], guild, w["id"]))

    # members ------------------------------------------------------------------

    def import_roster(self, guild: str, at: int | None, members: list[Any], res: ImportResult | None = None) -> None:
        """A trusted roster snapshot (addon `roster`, keys g n r rn l c fs ls) taken at `at`.

        Every listed member is updated (name, rank, level, class; first_seen only goes down, last_seen only
        up). Only the newest snapshot decides who is *in* the guild: an older one, e.g. from a collector
        who uploads late, never marks a member as gone.
        """
        res = res or ImportResult()
        db = self.db
        key = f"roster_at:{guild}"
        newest = int(self.get_state(key, "0") or 0)
        is_newest = at is not None and at >= newest
        present = []
        for m in members:
            guid, name = _str(m.get("g")), _str(m.get("n"))
            if guid is None or name is None:
                res.skipped += 1
                continue
            present.append(guid)
            fs, ls = _int(m.get("fs")), _int(m.get("ls"))
            r, lvl = _int(m.get("r")), _int(m.get("l"))
            rn, cls = _str(m.get("rn")), _str(m.get("c"))
            cur = db.execute("SELECT 1 FROM members WHERE guild=? AND guid=?", (guild, guid)).fetchone()
            if cur is None:
                db.execute("INSERT INTO members(guild, guid, name, first_seen, last_seen, in_guild, rank_name,"
                           " rank_index, level, class) VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (guild, guid, name, fs, ls, 1 if is_newest else 0, rn, r, lvl, cls))
                res.members_new += 1
            else:
                db.execute(
                    "UPDATE members SET name=?,"
                    " first_seen=MIN(COALESCE(first_seen, ?), COALESCE(?, first_seen)),"
                    " last_seen=MAX(COALESCE(last_seen, ?), COALESCE(?, last_seen))"
                    + (", in_guild=1, rank_name=COALESCE(?, rank_name), rank_index=COALESCE(?, rank_index),"
                       " level=COALESCE(?, level), class=COALESCE(?, class)" if is_newest else "")
                    + " WHERE guild=? AND guid=?",
                    (name, fs, fs, ls, ls, *((rn, r, lvl, cls) if is_newest else ()), guild, guid),
                )
        if is_newest and present:
            marks = ",".join("?" * len(present))
            db.execute(f"UPDATE members SET in_guild=0 WHERE guild=? AND guid NOT IN ({marks})", (guild, *present))
            db.execute("INSERT INTO state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (key, str(at)))

    # ------------------------------------------------------------------ Discord link requests (schema 3)

    def import_links(self, guild: str, rows: list[Any], collector: str, res: ImportResult | None = None) -> None:
        """Link requests a collector heard in game (addon `links`, keys id t k code tag n g). Insert if absent."""
        res = res or ImportResult()
        for r in rows:
            if not isinstance(r, dict):
                res.skipped += 1
                continue
            rid, t, kind = _str(r.get("id")), _int(r.get("t")), r.get("k")
            tag, name = _str(r.get("tag")), _str(r.get("n"))
            if rid is None or t is None or kind not in ("link", "alt") or tag is None or name is None:
                res.skipped += 1
                continue
            cur = self.db.execute(
                "INSERT OR IGNORE INTO link_rows(guild, id, ts_utc, kind, code, tag, name, guid, first_collector)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (guild, rid, t, kind, _str(r.get("code")), tag, name, _str(r.get("g")), collector))
            if cur.rowcount:
                res.links_new += 1

    def pending_links(self, guild: str) -> list[dict[str, Any]]:
        out = []
        for r in self.db.execute("SELECT * FROM link_rows WHERE guild=? AND uploaded=0 ORDER BY ts_utc", (guild,)):
            row = {"id": r["id"], "t": r["ts_utc"], "k": r["kind"], "tag": r["tag"], "n": r["name"]}
            if r["code"]:
                row["code"] = r["code"]
            if r["guid"]:
                row["g"] = r["guid"]
            out.append(row)
        return out

    def mark_links_uploaded(self, guild: str, ids: list[str]) -> None:
        with self.db:
            self.db.executemany("UPDATE link_rows SET uploaded=1 WHERE guild=? AND id=?", [(guild, i) for i in ids])

    # ------------------------------------------------------------------ roster upload (companion)

    def pending_roster(self, guild: str) -> tuple[int, list[dict[str, Any]]] | None:
        """The current roster for upload, if a newer snapshot arrived since the last upload."""
        at = int(self.get_state(f"roster_at:{guild}", "0") or 0)
        if not at or at <= int(self.get_state(f"roster_uploaded:{guild}", "0") or 0):
            return None
        rows = self.db.execute("SELECT * FROM members WHERE guild=? AND in_guild=1 ORDER BY guid", (guild,)).fetchall()
        members = []
        for r in rows:
            m: dict[str, Any] = {"g": r["guid"], "n": r["name"]}
            for key, col in (("r", "rank_index"), ("rn", "rank_name"), ("l", "level"), ("c", "class"),
                             ("fs", "first_seen"), ("ls", "last_seen")):
                if r[col] is not None:
                    m[key] = r[col]
            members.append(m)
        return at, members

    def mark_roster_uploaded(self, guild: str, at: int) -> None:
        self.set_state(f"roster_uploaded:{guild}", str(at))

    # ------------------------------------------------------------------ queries

    def guild_names(self) -> dict[str, str]:
        return {r["guild"]: r["name"] or r["guild"] for r in self.db.execute("SELECT guild, name FROM guilds")}

    def chat_rows(self, guild: str, since: int | None = None) -> Iterator[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM chat WHERE guild=? AND ts_utc >= ? ORDER BY ts_utc, id", (guild, since or 0))

    def event_rows(self, guild: str, since: int | None = None, include_superseded: bool = False) -> Iterator[sqlite3.Row]:
        extra = "" if include_superseded else " AND superseded_by IS NULL"
        return self.db.execute(
            f"SELECT * FROM events WHERE guild=? AND ts_utc >= ?{extra} ORDER BY ts_utc, id", (guild, since or 0))

    def stats(self) -> list[dict[str, Any]]:
        out = []
        for guild, name in self.guild_names().items():
            q = lambda sql: self.db.execute(sql, (guild,)).fetchone()  # noqa: E731
            c = q("SELECT COUNT(*) n, SUM(text IS NOT NULL) txt, SUM(src='meta' AND text IS NULL) meta,"
                  " SUM(src='event') ev, MIN(ts_utc) lo, MAX(ts_utc) hi, SUM(posted=0) unposted,"
                  " SUM(uploaded=0) unuploaded FROM chat WHERE guild=?")
            e = q("SELECT COUNT(*) n, SUM(superseded_by IS NOT NULL) sup, SUM(posted=0) unposted FROM events WHERE guild=?")
            m = q("SELECT COUNT(*) n, SUM(in_guild) cur FROM members WHERE guild=?")
            kinds = dict(self.db.execute(
                "SELECT kind, COUNT(*) FROM events WHERE guild=? AND superseded_by IS NULL GROUP BY kind", (guild,)
            ).fetchall())
            out.append({
                "guild": guild, "name": name,
                "chat": c["n"], "chat_with_text": c["txt"] or 0, "chat_meta_only": c["meta"] or 0,
                "chat_event_only": c["ev"] or 0, "chat_first": c["lo"], "chat_last": c["hi"],
                "chat_unposted": c["unposted"] or 0, "chat_unuploaded": c["unuploaded"] or 0,
                "events": e["n"], "events_superseded": e["sup"] or 0, "events_unposted": e["unposted"] or 0,
                "event_kinds": kinds, "members": m["n"], "members_in_guild": m["cur"] or 0,
            })
        return out

    def get_state(self, key: str, default: str | None = None) -> str | None:
        r = self.db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def set_state(self, key: str, value: str) -> None:
        with self.db:
            self.db.execute("INSERT INTO state(key, value) VALUES(?, ?) "
                            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


# ---------------------------------------------------------------------- row validation

def _int(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v == v:
        return int(v)
    return None


def _str(v: Any) -> str | None:
    return v if isinstance(v, str) and v != "" else None


def _chat_row(r: Any) -> dict[str, Any] | None:
    if not isinstance(r, dict):
        return None
    rid, t, author = _str(r.get("id")), _int(r.get("t")), _str(r.get("a"))
    stream = r.get("s", "g")
    src = r.get("src", "live")
    if src == "club":  # pre-Phase-0 spelling
        src = "live"
    if rid is None or t is None or author is None or stream not in STREAMS or src not in CHAT_SRC:
        return None
    text = r.get("m")
    text = text if isinstance(text, str) else None
    if src == "event" and text is None:
        return None
    return {
        "id": rid, "t": t, "stream": stream, "author": author, "guid": _str(r.get("g")), "text": text,
        "fd": 1 if r.get("fd") is True else 0, "edited": 1 if r.get("ed") is True else 0,
        "deleted": 1 if r.get("del") is True else 0, "src": src,
        "posted": 1 if r.get("pd") is True else 0,  # upload: direct mode already posted it
        "relayed_by": _str(r.get("rb")) if text is not None else None,  # schema 2
    }


def _chat_wire(r: sqlite3.Row) -> dict[str, Any]:
    out: dict[str, Any] = {"id": r["id"], "t": r["ts_utc"], "s": r["stream"], "a": r["author"], "src": r["src"]}
    if r["guid"]:
        out["g"] = r["guid"]
    if r["text"] is not None:
        out["m"] = r["text"]
    if r["relayed_by"]:
        out["rb"] = r["relayed_by"]
    for key, col in (("fd", "from_discord"), ("ed", "edited"), ("del", "deleted")):
        if r[col]:
            out[key] = True
    if r["posted"]:
        out["pd"] = True  # already posted by this collector in direct mode: the bot must not post it again
    return out


def _event_wire(r: sqlite3.Row) -> dict[str, Any]:
    out: dict[str, Any] = {"id": r["id"], "t": r["ts_utc"], "p": bool(r["precise"]), "k": r["kind"],
                           "n": r["name"], "src": r["src"]}
    for key, col in (("g", "guid"), ("by", "actor"), ("d", "detail"), ("w", "window_from")):
        if r[col] is not None:
            out[key] = r[col]
    if r["posted"]:
        out["pd"] = True
    return out


def _event_row(r: Any) -> dict[str, Any] | None:
    if not isinstance(r, dict):
        return None
    rid, t, name = _str(r.get("id")), _int(r.get("t")), _str(r.get("n"))
    kind, src = r.get("k"), r.get("src")
    if rid is None or t is None or name is None or kind not in EVENT_KINDS or src not in EVENT_SRC:
        return None
    return {
        "id": rid, "t": t, "p": 1 if r.get("p") is True else 0, "kind": kind, "name": name,
        "guid": _str(r.get("g")), "actor": _str(r.get("by")), "detail": _str(r.get("d")), "src": src,
        "w": _int(r.get("w")) if src != "sys" else None,
        "posted": 1 if r.get("pd") is True else 0,
    }
