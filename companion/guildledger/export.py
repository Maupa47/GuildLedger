"""Plain-text archive: logs/<guild>/chat-YYYY-MM-DD.log and logs/<guild>/roster-YYYY.log.

Files are regenerated from the spool (whole day / whole year), so re-running is idempotent and
late rows land in the right place.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Any

from .store import Spool
from .wowtext import plain

NO_TEXT = "(text not captured)"
_UNSAFE = re.compile(r"[^\w .-]+", re.UNICODE)


def guild_dir_name(name: str, guild: str) -> str:
    safe = _UNSAFE.sub("_", name).strip(" ._")
    return safe or guild


def _local(ts: int, tz: tzinfo | None) -> datetime:
    return datetime.fromtimestamp(ts, tz)


def _day_start(ts: int, tz: tzinfo | None) -> int:
    d = _local(ts, tz)
    return int(datetime(d.year, d.month, d.day, tzinfo=tz).timestamp())


def _year_start(ts: int, tz: tzinfo | None) -> int:
    return int(datetime(_local(ts, tz).year, 1, 1, tzinfo=tz).timestamp())


def chat_line(r: Any, tz: tzinfo | None) -> str:
    when = _local(r["ts_utc"], tz).strftime("%Y-%m-%d %H:%M:%S")
    tag = r["stream"].upper() + (" Discord" if r["from_discord"] else "")
    text = plain(r["text"]) if r["text"] is not None else NO_TEXT
    flags = (" (edited)" if r["edited"] else "") + (" (deleted)" if r["deleted"] else "")
    return f"[{when}] [{tag}] {r['author']}: {text}{flags}"


_KIND = {"join": "JOIN", "leave": "LEAVE", "kick": "KICK", "promote": "PROMOTE", "demote": "DEMOTE"}


def event_line(r: Any, tz: tzinfo | None) -> str:
    when = _local(r["ts_utc"], tz).strftime("%Y-%m-%d %H:%M:%S")
    s = f"[{when}] {_KIND.get(r['kind'], r['kind'].upper())} {r['name']}"
    if r["actor"]:
        s += f" by {r['actor']}"
    if r["detail"]:
        s += f" -> {r['detail']}"
    if not r["precise"]:
        w = r["window_from"] if "window_from" in r.keys() else None
        if w is not None and w < r["ts_utc"]:
            s += f" (between {_local(w, tz).strftime('%Y-%m-%d %H:%M')} and then, {r['src']})"
        else:
            s += f" (approx., {r['src']})"
    return s


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, path)


def export(spool: Spool, logs_dir: str | Path, tz: tzinfo | None, since: int | None = None) -> list[Path]:
    """Write log files for everything at or after ``since`` (unix s; None = all). Returns files written."""
    logs_dir = Path(logs_dir)
    written: list[Path] = []
    for guild, name in spool.guild_names().items():
        base = logs_dir / guild_dir_name(name, guild)

        days: dict[str, list[str]] = defaultdict(list)
        start = _day_start(since, tz) if since else None
        for r in spool.chat_rows(guild, start):
            days[_local(r["ts_utc"], tz).strftime("%Y-%m-%d")].append(chat_line(r, tz))
        for day, lines in sorted(days.items()):
            p = base / f"chat-{day}.log"
            _write(p, lines)
            written.append(p)

        years: dict[int, list[str]] = defaultdict(list)
        start = _year_start(since, tz) if since else None
        for r in spool.event_rows(guild, start):
            years[_local(r["ts_utc"], tz).year].append(event_line(r, tz))
        for year, lines in sorted(years.items()):
            p = base / f"roster-{year}.log"
            _write(p, lines)
            written.append(p)
    return written
