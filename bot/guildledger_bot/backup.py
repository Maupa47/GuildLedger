"""Daily backup of the archive (CLAUDE.md 7.5): SQLite online backup -> gzip -> keep N days,
optionally the newest file as an attachment to a private #gl-backup webhook. And a restore check."""

from __future__ import annotations

import gzip
import logging
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

log = logging.getLogger(__name__)

PREFIX = "guildledger-"
SUFFIX = ".db.gz"
DISCORD_LIMIT = 10 * 1024 * 1024  # free servers accept 10 MB per upload


def make_backup(db_path: Path, out_dir: Path, keep_days: int = 14, now: float | None = None) -> Path:
    now = time.time() if now is None else now
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    target = out_dir / f"{PREFIX}{stamp}{SUFFIX}"
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        plain = Path(tmp) / "snapshot.db"
        src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        dst = sqlite3.connect(plain)
        try:
            src.backup(dst)  # consistent copy while the bot keeps writing (WAL)
        finally:
            dst.close()
            src.close()
        partial = target.with_suffix(".partial")
        with open(plain, "rb") as fin, gzip.open(partial, "wb", compresslevel=9) as fout:
            shutil.copyfileobj(fin, fout)
        partial.replace(target)
    prune(out_dir, keep_days, now)
    log.info("backup written: %s (%d bytes)", target.name, target.stat().st_size)
    return target


def prune(out_dir: Path, keep_days: int, now: float) -> int:
    n = 0
    for f in out_dir.glob(f"{PREFIX}*{SUFFIX}"):
        if now - f.stat().st_mtime > keep_days * 86400:
            f.unlink()
            n += 1
    return n


def newest(out_dir: Path) -> Path | None:
    files = sorted(out_dir.glob(f"{PREFIX}*{SUFFIX}"))
    return files[-1] if files else None


def verify(backup: Path) -> dict[str, int]:
    """Unpack into a temporary database, run integrity_check and count rows. Raises on any problem."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "restore.db"
        with gzip.open(backup, "rb") as fin, open(db, "wb") as fout:
            shutil.copyfileobj(fin, fout)
        con = sqlite3.connect(db)
        try:
            ok = con.execute("PRAGMA integrity_check").fetchone()[0]
            if ok != "ok":
                raise RuntimeError(f"integrity_check: {ok}")
            counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                      for t in ("chat", "events", "uploads")}
        finally:
            con.close()
    return counts


def send_to_discord(backup: Path, webhook_url: str) -> bool:
    from guildledger import discord
    size = backup.stat().st_size
    if size > DISCORD_LIMIT:
        log.warning("backup %s is %d bytes, over Discord's limit; kept locally only", backup.name, size)
        return False
    hook = discord.Webhook(webhook_url, "backup")
    hook.post_file(f"GuildLedger backup {backup.name}", backup.name, backup.read_bytes())
    log.info("backup %s sent to the backup channel", backup.name)
    return True
