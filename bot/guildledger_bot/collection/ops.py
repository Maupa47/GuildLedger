"""Operations channel (#gl-ops, optional webhook): a daily coverage report and health warnings.

- Report (once a day after `report_hour` local time, for the previous day): chat lines, share with text,
  lines filled by members (relay), the longest stretches without text, uploads per collector, roster changes.
- Warning when no upload arrived for `alert_after_hours`; a note when uploads resume.
- A note for every rejected upload (sent by the client).
Pure functions take the archive; `Ops.tick` decides what is due. Runs on the bot's worker thread.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, tzinfo
from typing import Any

from guildledger import discord
from guildledger.config import resolve_tz

from ..store import Archive

log = logging.getLogger(__name__)

GAP_MIN_SECONDS = 1800  # a stretch without text shorter than this is not listed
GAP_MIN_LINES = 5
GAPS_LISTED = 5


def day_bounds(day: datetime, tz: tzinfo | None) -> tuple[int, int]:
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    if tz is None:
        start = datetime(day.year, day.month, day.day)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def _gaps(rows: list[Any]) -> list[tuple[int, int, int]]:
    """Stretches of consecutive lines without text: (first ts, last ts, lines), longest first."""
    out, run = [], []
    for r in rows:
        if r["text"] is None:
            run.append(r["ts_utc"])
            continue
        if run:
            out.append((run[0], run[-1], len(run)))
            run = []
    if run:
        out.append((run[0], run[-1], len(run)))
    out = [g for g in out if g[1] - g[0] >= GAP_MIN_SECONDS and g[2] >= GAP_MIN_LINES]
    out.sort(key=lambda g: g[1] - g[0], reverse=True)
    return out[:GAPS_LISTED]


def build_report(archive: Archive, start: int, end: int, tz: tzinfo | None) -> str:
    db = archive.db
    day = datetime.fromtimestamp(start, tz).strftime("%A, %Y-%m-%d")
    hm = lambda ts: datetime.fromtimestamp(ts, tz).strftime("%H:%M")  # noqa: E731
    lines = [f"**GuildLedger report — {day}**"]
    for guild, name in archive.guild_names().items():
        rows = db.execute("SELECT ts_utc, text, relayed_by FROM chat WHERE guild=? AND stream='g'"
                          " AND ts_utc >= ? AND ts_utc < ? ORDER BY ts_utc, id", (guild, start, end)).fetchall()
        total = len(rows)
        with_text = sum(1 for r in rows if r["text"] is not None)
        relayed = sum(1 for r in rows if r["relayed_by"])
        pct = f"{100 * with_text // total}%" if total else "-"
        head = f"__{discord.escape(name)}__ · " if len(archive.guild_names()) > 1 else ""
        lines.append(f"{head}Chat: **{total}** lines · **{pct}** with text ({with_text})"
                     f" · filled by members: {relayed} · without text: {total - with_text}")
        gaps = _gaps(rows)
        if gaps:
            lines.append("Longest stretches without text: " + ", ".join(
                f"{hm(a)}–{hm(b)} ({n} lines)" for a, b, n in gaps))
        ev = dict(db.execute("SELECT kind, COUNT(*) FROM events WHERE guild=? AND superseded_by IS NULL"
                             " AND ts_utc >= ? AND ts_utc < ? GROUP BY kind", (guild, start, end)).fetchall())
        if ev:
            lines.append("Roster: " + ", ".join(f"{k} {v}" for k, v in sorted(ev.items())))
    up = db.execute("SELECT collector, COUNT(*), SUM(rows), SUM(status='rejected') FROM uploads"
                    " WHERE received_at >= ? AND received_at < ? GROUP BY collector ORDER BY collector",
                    (start, end)).fetchall()
    if up:
        lines.append("Uploads: " + ", ".join(
            f"{discord.escape(c)} {n} ({rows or 0} rows" + (f", {bad} rejected" if bad else "") + ")"
            for c, n, rows, bad in up))
    else:
        lines.append("Uploads: **none** that day")
    return "\n".join(lines)


class Ops:
    def __init__(self, archive: Archive, webhook: discord.Webhook | None, tz_name: str,
                 report_hour: int = 6, alert_after_hours: float = 6, now=time.time):
        self.archive, self.hook, self.tz = archive, webhook, resolve_tz(tz_name)
        self.report_hour, self.alert_after, self.now = report_hour, alert_after_hours * 3600, now

    def send(self, text: str) -> bool:
        if self.hook is None:
            return False
        try:
            self.hook.post(content=text[:1900])
            return True
        except discord.WebhookError as e:
            log.error("ops channel: %s", e)
            return False

    def tick(self) -> None:
        """Called every posting round; sends what is due (each at most once)."""
        if self.hook is None:
            return
        self._report()
        self._health()

    def _report(self) -> None:
        now = datetime.fromtimestamp(self.now(), self.tz)
        if now.hour < self.report_hour:
            return
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        if self.archive.get_state("report_day") == yesterday:
            return
        start, end = day_bounds(now - timedelta(days=1), self.tz)
        if self.send(build_report(self.archive, start, end, self.tz)):
            self.archive.set_state("report_day", yesterday)

    def _health(self) -> None:
        last = self.archive.db.execute("SELECT MAX(received_at) FROM uploads WHERE status='ok'").fetchone()[0]
        if last is None:
            return
        open_alert = self.archive.get_state("alert_since")
        silent = self.now() - last
        if silent >= self.alert_after and open_alert != str(last):
            hours = int(silent // 3600)
            when = datetime.fromtimestamp(last, self.tz).strftime("%Y-%m-%d %H:%M")
            if self.send(f"⚠️ **No upload for {hours} h** (last one {when}). Is a collector's companion running?"
                         f" Guild chat is not reaching the archive until one uploads again."):
                self.archive.set_state("alert_since", str(last))
        elif open_alert and int(open_alert) != last and silent < self.alert_after:
            if self.send("✅ Uploads are arriving again."):
                self.archive.set_state("alert_since", "")
