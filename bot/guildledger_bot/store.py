"""The archive (SQLite, WAL). Same tables and merge rules as the companion's spool (guildledger.store),
plus `uploads`: every #gl-ingest message is processed once."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from guildledger import loot
from guildledger.store import ImportResult, Spool

from .collection import ingest

log = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS uploads(
  message_id INTEGER PRIMARY KEY, collector TEXT NOT NULL, rows INTEGER NOT NULL, sha256 TEXT,
  received_at INTEGER NOT NULL, status TEXT NOT NULL, reason TEXT);
"""


@dataclass
class Outcome:
    status: str  # "ok", "rejected", "seen" (already processed)
    reason: str = ""
    result: ImportResult | None = None
    loot_result: loot.LootResult | None = None


class Archive(Spool):
    def __init__(self, path: str | Path):
        super().__init__(path)
        self.db.executescript(_DDL)

    def process_upload(self, message_id: int, collector: str, content: str, data: bytes | None) -> Outcome:
        """Check and merge one upload. `collector` comes from the webhook ID, never from the file."""
        if self.db.execute("SELECT 1 FROM uploads WHERE message_id=?", (message_id,)).fetchone():
            return Outcome("seen")
        try:
            header = ingest.parse_content(content)
            if data is None:
                raise ingest.Rejected("no attachment")
            guilds = ingest.decode(data, header)
        except ingest.Rejected as e:
            self._record(message_id, collector, 0, None, "rejected", str(e))
            return Outcome("rejected", str(e))
        total = ImportResult()
        lres = loot.LootResult()
        for guild, rows in guilds.items():
            res = self.import_rows(guild, rows.name, rows.chat, rows.events, collector)
            if rows.roster is not None:
                with self.db:
                    self.import_roster(guild, rows.roster[0], rows.roster[1], res)
            if rows.links:
                with self.db:
                    self.import_links(guild, rows.links, collector, res)
            if rows.loot:
                for kind in loot.ROW_TYPES:
                    lres.add(loot.merge(self.db, guild, kind, [r for k, r in rows.loot if k == kind], collector))
            for k in ("chat_new", "chat_updated", "chat_merged", "chat_dup", "events_new", "events_dup",
                      "events_updated", "members_new", "links_new", "skipped"):
                setattr(total, k, getattr(total, k) + getattr(res, k))
            total.guilds.append(guild)
        self._record(message_id, collector, header.rows, header.sha256, "ok", "")
        return Outcome("ok", result=total, loot_result=lres)

    def _record(self, message_id: int, collector: str, rows: int, sha: str | None, status: str, reason: str):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO uploads(message_id, collector, rows, sha256, received_at, status,"
                            " reason) VALUES(?,?,?,?,?,?,?)",
                            (message_id, collector, rows, sha, int(time.time()), status, reason))
            last = int(self.get_state("last_ingest_id", "0") or 0)
            if message_id > last:
                self.db.execute("INSERT INTO state(key, value) VALUES('last_ingest_id', ?) "
                                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(message_id),))

    def last_ingest_id(self) -> int:
        return int(self.get_state("last_ingest_id", "0") or 0)

    def post_since(self, configured: int | None) -> int:
        """Rows older than this are archived but never posted (direct mode posted them already)."""
        if configured is not None:
            return configured
        v = self.get_state("post_since")
        if v is None:
            v = str(int(time.time()))
            self.set_state("post_since", v)
        return int(v)
