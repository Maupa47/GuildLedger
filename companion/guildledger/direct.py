"""mode = "direct": post new rows from the spool to the chat and roster webhooks (CLAUDE.md 3, 6, 7.4).

Rules
- A row is marked posted only after Discord confirmed its message; a failed run resumes where it stopped.
- Order: ts_utc per channel. Rows older than the newest already posted go into a "late entries" block
  with full dates; posted messages are never edited or deleted.
- First run for a guild marks everything already in the spool as posted, unless post_backlog.
- Superseded events are never posted; diff/log events wait HOLD_EVENTS seconds so a better row can arrive.
- Chat rows without text ("meta"): meta = "summary" (default) posts one line per run of them,
  "lines" posts each as "(text not captured)", "skip" posts nothing for them.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import tzinfo
from typing import Any

from . import discord
from .store import Spool

log = logging.getLogger(__name__)

HOLD_EVENTS = 600
META_MODES = ("summary", "lines", "skip")


@dataclass
class PostResult:
    chat_rows: int = 0
    chat_messages: int = 0
    events: int = 0
    skipped_backlog: int = 0

    def summary(self) -> str:
        s = f"posted {self.chat_rows} chat row(s) in {self.chat_messages} message(s), {self.events} roster event(s)"
        if self.skipped_backlog:
            s += f"; {self.skipped_backlog} older row(s) marked as posted without posting (first run)"
        return s


class Poster:
    def __init__(self, spool: Spool, chat: discord.Webhook | None, roster: discord.Webhook | None,
                 tz: tzinfo | None, meta: str = "summary", now=time.time, hold_chat: int = 0):
        if meta not in META_MODES:
            raise ValueError(f"meta must be one of {META_MODES}")
        self.spool, self.chat, self.roster, self.tz, self.meta, self.now = spool, chat, roster, tz, meta, now
        self.hold_chat = hold_chat  # bot: chat rows wait this long so another collector's copy can add text

    # ------------------------------------------------------------------ public

    def run(self, post_backlog: bool = False, since: int | None = None) -> PostResult:
        """since (bot): rows older than this are archived but marked posted without posting, instead of
        the direct-mode first-run rule."""
        res = PostResult()
        for guild in self.spool.guild_names():
            if since is not None:
                res.skipped_backlog += self._skip_before(guild, since)
            else:
                res.skipped_backlog += self._init_guild(guild, post_backlog)
            if self.chat:
                self._post_chat(guild, res)
            if self.roster:
                self._post_events(guild, res)
        return res

    # ------------------------------------------------------------------ first run

    def _init_guild(self, guild: str, post_backlog: bool) -> int:
        key = f"direct_init:{guild}"
        if self.spool.get_state(key):
            return 0
        if post_backlog:
            self.spool.set_state(key, "1")
            return 0
        db = self.spool.db
        with db:
            n = db.execute("UPDATE chat SET posted=1 WHERE guild=? AND posted=0", (guild,)).rowcount
            n += db.execute("UPDATE events SET posted=1 WHERE guild=? AND posted=0", (guild,)).rowcount
            hi = db.execute("SELECT MAX(ts_utc) FROM chat WHERE guild=?", (guild,)).fetchone()[0]
            hie = db.execute("SELECT MAX(ts_utc) FROM events WHERE guild=?", (guild,)).fetchone()[0]
        self.spool.set_state(key, "1")
        if hi is not None:
            self.spool.set_state(f"chat_last:{guild}", str(hi))
        if hie is not None:
            self.spool.set_state(f"events_last:{guild}", str(hie))
        return n

    def _skip_before(self, guild: str, since: int) -> int:
        db = self.spool.db
        with db:
            n = db.execute("UPDATE chat SET posted=1 WHERE guild=? AND posted=0 AND ts_utc < ?",
                           (guild, since)).rowcount
            n += db.execute("UPDATE events SET posted=1 WHERE guild=? AND posted=0 AND ts_utc < ?",
                            (guild, since)).rowcount
        return n

    # ------------------------------------------------------------------ chat

    def _post_chat(self, guild: str, res: PostResult) -> None:
        db = self.spool.db
        last = int(self.spool.get_state(f"chat_last:{guild}", "0") or 0)
        cutoff = int(self.now()) - self.hold_chat if self.hold_chat else 2 ** 62
        rows = db.execute("SELECT * FROM chat WHERE guild=? AND posted=0 AND ts_utc <= ? ORDER BY ts_utc, id",
                          (guild, cutoff)).fetchall()
        if not rows:
            return
        late = [r for r in rows if r["ts_utc"] < last]
        fresh = [r for r in rows if r["ts_utc"] >= last]
        messages: list[tuple[str, list[Any]]] = []
        if late:
            header = ("**Late entries** — older lines that arrived after newer ones were posted:")
            messages += discord.pack(self._lines(late, full_date=True, last_day=None), header)
        if fresh:
            last_day = self._day(last) if last else None
            messages += discord.pack(self._lines(fresh, full_date=False, last_day=last_day))
        for content, keys in messages:
            if content:
                self.chat.post(content=content)
                res.chat_messages += 1
            with db:
                db.executemany("UPDATE chat SET posted=1 WHERE guild=? AND stream=? AND id=?",
                               [(guild, s, i) for s, i in keys])
            res.chat_rows += len(keys)
            hi = max(db.execute("SELECT ts_utc FROM chat WHERE guild=? AND stream=? AND id=?", (guild, s, i))
                     .fetchone()[0] for s, i in keys)
            if hi > last:
                last = hi
                self.spool.set_state(f"chat_last:{guild}", str(last))

    def _day(self, ts: int) -> str:
        return discord._local(ts, self.tz).strftime("%Y-%m-%d")

    def _lines(self, rows, full_date: bool, last_day: str | None) -> list[tuple[str, list[Any]]]:
        out: list[tuple[str | None, list[Any]]] = []
        run: list[Any] = []  # consecutive meta rows (summary mode)

        def flush_run():
            if not run:
                return
            authors = len({r["guid"] or r["author"] for r in run if r["author"] != "?"})
            line = discord.gap_line(run[0]["ts_utc"], run[-1]["ts_utc"], len(run), authors, self.tz, full_date)
            out.append((line, [(r["stream"], r["id"]) for r in run]))
            run.clear()

        for r in rows:
            day = self._day(r["ts_utc"])
            if not full_date and day != last_day:
                flush_run()
                out.append((discord.date_header(r["ts_utc"], self.tz), []))
                last_day = day
            key = [(r["stream"], r["id"])]
            if r["text"] is None and self.meta != "lines":
                if self.meta == "skip":
                    out.append((None, key))  # marked posted with the next line, never shown
                else:
                    run.append(r)
                continue
            flush_run()
            out.append((discord.chat_line(r, self.tz, full_date), key))
        flush_run()
        # silent entries (skip mode) carry keys but no text: fold their keys into the neighbour line
        merged: list[tuple[str, list[Any]]] = []
        pending: list[Any] = []
        for line, keys in out:
            if line is None:
                pending += keys
                continue
            merged.append((line, keys + pending))
            pending = []
        if pending:
            merged.append(("", pending))
        return merged
    # ------------------------------------------------------------------ events

    def _post_events(self, guild: str, res: PostResult) -> None:
        db = self.spool.db
        cutoff = int(self.now()) - HOLD_EVENTS
        last = int(self.spool.get_state(f"events_last:{guild}", "0") or 0)
        rows = db.execute(
            "SELECT * FROM events WHERE guild=? AND posted=0 AND superseded_by IS NULL"
            " AND (src='sys' OR ts_utc <= ?) ORDER BY ts_utc, rowid", (guild, cutoff)).fetchall()
        for i in range(0, len(rows), discord.MAX_EMBEDS):
            batch = rows[i:i + discord.MAX_EMBEDS]
            self.roster.post(embeds=[discord.event_embed(r, late=r["ts_utc"] < last) for r in batch])
            with db:
                db.executemany("UPDATE events SET posted=1 WHERE guild=? AND id=?", [(guild, r["id"]) for r in batch])
            res.events += len(batch)
            hi = max(r["ts_utc"] for r in batch)
            if hi > last:
                last = hi
                self.spool.set_state(f"events_last:{guild}", str(last))
