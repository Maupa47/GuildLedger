"""mode = "upload": send new spool rows to the bot through the #gl-ingest webhook (shared/schema.md 4).

Each upload is one Discord message with one attachment: gzip-compressed JSON Lines, at most
MAX_FILE bytes. First line: {"type": "guild", "guild": <clubId>, "name": <name>}; then one object per row:
{"type": "chat"|"event", "guild": ..., "collector": ..., <row keys as in SavedVariables>}.
Message content: "gl1 <collector> <rowcount> <sha256 of the gz file>". Rows are marked uploaded only
after Discord confirmed the message; changed rows are uploaded again (the bot merges them).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from . import discord, loot
from .store import Spool

log = logging.getLogger(__name__)

MAX_FILE = 500 * 1024
FIRST_CHUNK = 4000  # rows per file to try first; halved while the file is too big
PROTOCOL = "gl1"


@dataclass
class UploadResult:
    files: int = 0
    rows: int = 0
    rosters: int = 0

    def summary(self) -> str:
        return f"uploaded {self.rows} row(s)" + (" and the member list" if self.rosters else "") + \
            f" in {self.files} file(s)"


def build_file(guild: str, name: str | None, collector: str, chat: list[dict[str, Any]],
               events: list[dict[str, Any]], roster: tuple[int, list[dict[str, Any]]] | None = None,
               links: list[dict[str, Any]] = (), extra: list[tuple[str, dict[str, Any]]] = ()) -> bytes:
    lines = [json.dumps({"type": "guild", "guild": guild, "name": name}, ensure_ascii=False)]
    if roster is not None:  # pack step R: one record with the whole snapshot (counts as one row)
        lines.append(json.dumps({"type": "roster", "guild": guild, "at": roster[0], "members": roster[1]},
                                ensure_ascii=False))
    for kind, rows in (("chat", chat), ("event", events), ("link", links)):
        for r in rows:
            lines.append(json.dumps({"type": kind, "guild": guild, "collector": collector, **r}, ensure_ascii=False))
    for kind, r in extra:  # loot data (shared/schema.md 7)
        lines.append(json.dumps({"type": kind, "guild": guild, "collector": collector, **r}, ensure_ascii=False))
    raw = ("\n".join(lines) + "\n").encode("utf-8")
    return gzip.compress(raw, compresslevel=9, mtime=0)


def describe(collector: str, rows: int, data: bytes) -> str:
    return f"{PROTOCOL} {collector} {rows} {hashlib.sha256(data).hexdigest()}"


class Uploader:
    def __init__(self, spool: Spool, hook: discord.Webhook, collector: str, now=time.time):
        self.spool, self.hook, self.collector, self.now = spool, hook, collector, now

    def run(self) -> UploadResult:
        res = UploadResult()
        names = self.spool.guild_names()
        for guild, name in names.items():
            chat, events = self.spool.pending_upload(guild)
            rows = [("chat", r) for r in chat] + [("event", r) for r in events]
            i, size = 0, FIRST_CHUNK
            while i < len(rows):
                part = rows[i:i + size]
                c = [r for k, r in part if k == "chat"]
                e = [r for k, r in part if k == "event"]
                data = build_file(guild, name if name != guild else None, self.collector, c, e)
                if len(data) > MAX_FILE and size > 1:
                    size = max(1, size // 2)
                    continue
                stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(self.now()))
                filename = f"gl-{guild}-{stamp}-{res.files + 1}.jsonl.gz"
                self.hook.post_file(describe(self.collector, len(part), data), filename, data)
                self.spool.mark_uploaded(guild, [(r["s"], r["id"]) for r in c], [r["id"] for r in e])
                res.files += 1
                res.rows += len(part)
                i += len(part)
            links = self.spool.pending_links(guild)
            if links:
                data = build_file(guild, name if name != guild else None, self.collector, [], [], None, links)
                stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(self.now()))
                self.hook.post_file(describe(self.collector, len(links), data),
                                    f"gl-{guild}-{stamp}-links.jsonl.gz", data)
                self.spool.mark_links_uploaded(guild, [r["id"] for r in links])
                res.files += 1
                res.rows += len(links)
            res.rows += self._loot(guild, name, res)
            roster = self.spool.pending_roster(guild)
            if roster is not None:
                data = build_file(guild, name if name != guild else None, self.collector, [], [], roster)
                stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(self.now()))
                self.hook.post_file(describe(self.collector, 1, data), f"gl-{guild}-{stamp}-roster.jsonl.gz", data)
                self.spool.mark_roster_uploaded(guild, roster[0])
                res.files += 1
                res.rosters += 1
        return res

    def _loot(self, guild: str, name: str, res: UploadResult) -> int:
        """Loot rows go in files of their own, so a bot that does not know them yet rejects only those."""
        rows = loot.pending(self.spool.db, guild)
        sent, i, size = 0, 0, FIRST_CHUNK
        while i < len(rows):
            part = rows[i:i + size]
            data = build_file(guild, name if name != guild else None, self.collector, [], [], None, (), part)
            if len(data) > MAX_FILE and size > 1:
                size = max(1, size // 2)
                continue
            stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(self.now()))
            self.hook.post_file(describe(self.collector, len(part), data), f"gl-{guild}-{stamp}-loot.jsonl.gz", data)
            loot.mark_uploaded(self.spool.db, guild, part)
            res.files += 1
            sent += len(part)
            i += len(part)
        return sent
