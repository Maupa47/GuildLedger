"""GuildLedger bot.

    python -m guildledger_bot [--config /etc/guildledger/config.toml] run       # normal service
    python -m guildledger_bot [--config ...] backfill                           # catch up, post, exit
    python -m guildledger_bot [--config ...] check                              # config + archive stats, offline
    python -m guildledger_bot [--config ...] export <dir>                       # plain-text logs of the archive
    python -m guildledger_bot [--config ...] backup [--dir D] [--keep-days N]   # daily backup (systemd timer)
    python -m guildledger_bot [--config ...] verify-backup [file]               # restore check of a backup
    python -m guildledger_bot [--config ...] report [--day YYYY-MM-DD]          # coverage report (stdout)
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import config as config_mod

log = logging.getLogger("guildledger_bot")
DEFAULT_CONFIG = "/etc/guildledger/config.toml"


def cmd_check(cfg) -> int:
    from .store import Archive
    with Archive(cfg.db_path) as a:
        stats = a.stats()
        uploads = a.db.execute("SELECT status, COUNT(*) FROM uploads GROUP BY status").fetchall()
        since = a.get_state("post_since")
    print(f"config ok: ingest channel {cfg.ingest_channel_id}, collectors: {', '.join(sorted(cfg.collectors.values()))}")
    print(f"archive {cfg.db_path}: uploads {dict(uploads) or 'none'}; posting rows since {since or '(first start)'}")
    for s in stats:
        print(f"  {s['name']}: chat {s['chat']} ({s['chat_with_text']} with text, {s['chat_unposted']} not posted),"
              f" events {s['events']} ({s['events_unposted']} not posted, {s['events_superseded']} superseded)")
    return 0


def cmd_export(cfg, out: str) -> int:
    from guildledger.config import resolve_tz
    from guildledger.export import export

    from .store import Archive
    with Archive(cfg.db_path) as a:
        files = export(a, out, resolve_tz(cfg.timezone))
    print(f"wrote {len(files)} file(s) to {out}")
    return 0


def cmd_backup(cfg, out_dir: str | None, keep_days: int) -> int:
    from pathlib import Path

    from . import backup
    target = backup.make_backup(cfg.db_path, Path(out_dir) if out_dir else cfg.db_path.parent / "backups", keep_days)
    counts = backup.verify(target)
    print(f"backup {target} ok: {counts}")
    if cfg.backup_webhook:
        try:
            backup.send_to_discord(target, cfg.backup_webhook)
        except Exception as e:  # noqa: BLE001 - the local backup exists; report and carry on
            log.error("sending the backup to Discord failed: %s", e)
            return 1
    return 0


def cmd_verify(cfg, path: str | None) -> int:
    from pathlib import Path

    from . import backup
    f = Path(path) if path else backup.newest(cfg.db_path.parent / "backups")
    if f is None:
        log.error("no backup found")
        return 1
    try:
        counts = backup.verify(f)
    except Exception as e:  # noqa: BLE001
        log.error("backup %s does NOT restore: %s", f, e)
        return 1
    print(f"backup {f} restores into a working database: {counts}")
    return 0


def cmd_report(cfg, day: str | None) -> int:
    from datetime import datetime, timedelta

    from guildledger.config import resolve_tz

    from .ops import build_report, day_bounds
    from .store import Archive
    tz = resolve_tz(cfg.timezone)
    when = datetime.strptime(day, "%Y-%m-%d") if day else datetime.now(tz) - timedelta(days=1)
    start, end = day_bounds(when, tz)
    with Archive(cfg.db_path) as a:
        print(build_report(a, start, end, tz))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m guildledger_bot", description="GuildLedger bot")
    p.add_argument("--config", default=DEFAULT_CONFIG)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="connect, catch up on #gl-ingest, then process uploads and post")
    sub.add_parser("backfill", help="process every upload newer than the last processed one, post, exit")
    sub.add_parser("check", help="check the config and show archive stats (no Discord connection)")
    e = sub.add_parser("export", help="write the plain-text logs of the whole archive")
    e.add_argument("out")
    b = sub.add_parser("backup", help="back up the archive (gzip), keep N days, optionally send to #gl-backup")
    b.add_argument("--dir", help="backup folder (default: backups/ next to the database)")
    b.add_argument("--keep-days", type=int, default=14)
    r = sub.add_parser("report", help="print the coverage report of a day (default: yesterday)")
    r.add_argument("--day", help="YYYY-MM-DD (local)")
    v = sub.add_parser("verify-backup", help="check that a backup restores into a working database")
    v.add_argument("file", nargs="?", help="default: the newest backup")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    logging.getLogger("discord").setLevel(logging.WARNING)
    try:
        cfg = config_mod.load(args.config)
    except config_mod.ConfigError as e:
        log.error("%s", e)
        return 2

    if args.cmd == "check":
        return cmd_check(cfg)
    if args.cmd == "export":
        return cmd_export(cfg, args.out)
    if args.cmd == "backup":
        return cmd_backup(cfg, args.dir, args.keep_days)
    if args.cmd == "verify-backup":
        return cmd_verify(cfg, args.file)
    if args.cmd == "report":
        return cmd_report(cfg, args.day)

    from .client import LedgerBot
    bot = LedgerBot(cfg, once=args.cmd == "backfill")
    try:
        bot.run(cfg.token, log_handler=None)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
