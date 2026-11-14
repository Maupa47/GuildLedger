"""GuildLedger companion CLI.

    python -m guildledger [--config config.toml] watch [--once]
    python -m guildledger import <GuildLedger.lua> [--collector NAME]
    python -m guildledger export [--since YYYY-MM-DD]
    python -m guildledger stats
    python -m guildledger post [--post-backlog]      (mode = "direct")
    python -m guildledger upload                       (mode = "upload")
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from . import config as config_mod
from . import discord
from .direct import Poster
from .export import export
from .lock import InstanceLock
from .upload import Uploader
from .store import SchemaError, Spool
from .svparse import SVParseError, parse_file

log = logging.getLogger("guildledger")


def _open(cfg: config_mod.Config, db: str | None) -> Spool:
    return Spool(db or cfg.db_path)


def import_file(spool: Spool, cfg: config_mod.Config, path: Path, collector: str, do_export: bool = True):
    data = parse_file(str(path))
    res = spool.import_sv(data, collector)
    log.info("imported %s: %s", path.name, res.summary())
    if do_export and res.min_ts is not None:
        files = export(spool, cfg.logs_dir, cfg.tz(), since=res.min_ts)
        log.info("exported %d log file(s) to %s", len(files), cfg.logs_dir)
    return res


def cmd_import(args, cfg) -> int:
    with _open(cfg, args.db) as spool:
        import_file(spool, cfg, Path(args.file), args.collector or cfg.collector, not args.no_export)
    return 0


def cmd_export(args, cfg) -> int:
    since = None
    if args.since:
        since = int(datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=cfg.tz()).timestamp())
    with _open(cfg, args.db) as spool:
        files = export(spool, args.out or cfg.logs_dir, cfg.tz(), since=since)
    print(f"wrote {len(files)} file(s) to {args.out or cfg.logs_dir}")
    return 0


POST_EVERY = 60  # s: watch retries failed posts and releases held roster events this often


def make_poster(spool: Spool, cfg: config_mod.Config, transport=None) -> Poster:
    kw = {"transport": transport} if transport else {}
    chat = discord.Webhook(cfg.chat_webhook, "chat", **kw) if cfg.chat_webhook else None
    roster = discord.Webhook(cfg.roster_webhook, "roster", **kw) if cfg.roster_webhook else None
    if not chat and not roster:
        raise discord.WebhookError("neither chat_webhook nor roster_webhook is set in [direct]")
    return Poster(spool, chat, roster, cfg.tz(), cfg.meta)


def post_now(spool: Spool, cfg: config_mod.Config, post_backlog: bool = False, transport=None) -> bool:
    try:
        res = make_poster(spool, cfg, transport).run(post_backlog=post_backlog)
    except discord.WebhookError as e:
        log.error("Discord: %s (will retry)", e)
        return False
    if res.chat_rows or res.events or res.skipped_backlog:
        log.info("Discord: %s", res.summary())
    return True


def _dry_run(spool: Spool, cfg: config_mod.Config, post_backlog: bool) -> int:
    """Run the poster against an in-memory copy of the spool; print instead of sending."""
    import json
    import sqlite3

    copy = Spool(":memory:")
    spool.db.backup(copy.db)

    def show(url: str, data: bytes, content_type: str = "application/json") -> discord.Response:
        role = "chat" if url.startswith("dry:chat") else "roster"
        payload = json.loads(data)
        if "content" in payload:
            print(f"----- [{role}] message -----\n{payload['content']}")
        for e in payload.get("embeds", []):
            fields = "; ".join(f"{f['name']}: {f['value']}" for f in e.get("fields", []))
            print(f"----- [{role}] embed: {e['description']} | {fields} | {e['footer']['text']}")
        return discord.Response(200, {}, b"{}")

    chat = discord.Webhook("https://dry:chat", "chat", show) if cfg.chat_webhook else None
    roster = discord.Webhook("https://dry:roster", "roster", show) if cfg.roster_webhook else None
    chat = chat and _rename(chat, "dry:chat")
    roster = roster and _rename(roster, "dry:roster")
    try:
        res = Poster(copy, chat, roster, cfg.tz(), cfg.meta).run(post_backlog=post_backlog)
    except sqlite3.Error as e:
        log.error("dry run failed: %s", e)
        return 1
    finally:
        copy.close()
    print(f"(dry run, nothing sent) {res.summary()}")
    return 0


def _rename(hook: discord.Webhook, url: str) -> discord.Webhook:
    hook._url = url  # dry run: the transport only needs to tell the two apart
    return hook


def cmd_post(args, cfg) -> int:
    if cfg.mode != "direct":
        log.error('post is for mode = "direct"; this config uses mode = %r', cfg.mode)
        return 2
    with _open(cfg, args.db) as spool:
        if args.dry_run:
            return _dry_run(spool, cfg, args.post_backlog)
        return 0 if post_now(spool, cfg, args.post_backlog, getattr(args, "transport", None)) else 1


def upload_now(spool: Spool, cfg: config_mod.Config, transport=None) -> bool:
    try:
        kw = {"transport": transport} if transport else {}
        hook = discord.Webhook(cfg.ingest_webhook, "ingest", **kw)
        res = Uploader(spool, hook, cfg.collector).run()
    except discord.WebhookError as e:
        log.error("Discord: %s (will retry)", e)
        return False
    if res.rows:
        log.info("Discord: %s", res.summary())
    return True


def send_now(spool: Spool, cfg: config_mod.Config, post_backlog: bool = False, transport=None) -> bool:
    if cfg.mode == "upload":
        return upload_now(spool, cfg, transport)
    return post_now(spool, cfg, post_backlog, transport)


def cmd_upload(args, cfg) -> int:
    if cfg.mode != "upload":
        log.error('upload is for mode = "upload"; this config uses mode = %r', cfg.mode)
        return 2
    with _open(cfg, args.db) as spool:
        return 0 if upload_now(spool, cfg, getattr(args, "transport", None)) else 1


def _fmt_ts(ts, tz) -> str:
    return datetime.fromtimestamp(ts, tz).strftime("%Y-%m-%d %H:%M") if ts else "-"


def cmd_stats(args, cfg) -> int:
    tz = cfg.tz()
    with _open(cfg, args.db) as spool:
        rows = spool.stats()
    if not rows:
        print("spool is empty")
        return 0
    for s in rows:
        print(f"{s['name']} (club {s['guild']})")
        print(f"  chat     {s['chat']} rows: {s['chat_with_text']} with text, {s['chat_meta_only']} without text;"
              f" {_fmt_ts(s['chat_first'], tz)} .. {_fmt_ts(s['chat_last'], tz)}")
        print(f"           not posted {s['chat_unposted']}, not uploaded {s['chat_unuploaded']}")
        kinds = ", ".join(f"{k} {n}" for k, n in sorted(s["event_kinds"].items())) or "none"
        print(f"  events   {s['events']} ({kinds}; superseded {s['events_superseded']})")
        print(f"  members  {s['members_in_guild']} in guild, {s['members']} known")
    return 0


def _signature(path: Path):
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return (st.st_mtime_ns, st.st_size)


def cmd_watch(args, cfg) -> int:
    if not cfg.sv_path:
        log.error("sv_path is not set in the config")
        return 2
    path = cfg.sv_path
    lock = InstanceLock(cfg.data_dir / "watch.lock")
    if not lock.acquire():
        log.error("another GuildLedger companion is already running for this folder; close it first")
        return 1
    log.info("watching %s (collector %s, mode %s)", path, cfg.collector, cfg.mode)
    seen = None
    direct = not args.no_post  # post (mode "direct") or upload (mode "upload")
    transport = getattr(args, "transport", None)
    next_post = 0.0
    with lock, _open(cfg, args.db) as spool:
        while True:
            if direct and time.monotonic() >= next_post:
                send_now(spool, cfg, args.post_backlog, transport)
                next_post = time.monotonic() + POST_EVERY
            sig = _signature(path)
            if sig is not None and sig != seen:
                time.sleep(cfg.stable_seconds)
                if _signature(path) == sig:  # WoW has finished writing
                    for attempt in (1, 2):
                        try:
                            import_file(spool, cfg, path, cfg.collector)
                            break
                        except (SVParseError, SchemaError, OSError, UnicodeError) as e:
                            if attempt == 1:
                                log.warning("could not read %s (%s); retrying once", path.name, e)
                                time.sleep(cfg.stable_seconds)
                            else:
                                log.error("giving up on this version of %s: %s", path.name, e)
                    seen = sig
                    if direct:
                        send_now(spool, cfg, args.post_backlog, transport)
                        next_post = time.monotonic() + POST_EVERY
                    if args.once:
                        return 0
                    continue
            elif sig is None and args.once:
                log.error("file not found: %s", path)
                return 1
            time.sleep(cfg.poll_seconds)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m guildledger", description="GuildLedger companion")
    p.add_argument("--config", help="path to config.toml (default: ./config.toml if present)")
    p.add_argument("--db", help="spool database path (default: <config dir>/spool.db)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("watch", help="import the SavedVariables file whenever WoW writes it")
    w.add_argument("--once", action="store_true", help="import once and exit")
    w.add_argument("--no-post", action="store_true", help="do not post or upload to Discord")
    w.add_argument("--post-backlog", action="store_true",
                   help="first run: also post rows that were already in the spool")
    w.set_defaults(func=cmd_watch)

    i = sub.add_parser("import", help="import one SavedVariables file")
    i.add_argument("file")
    i.add_argument("--collector", help="collector name (default: from config)")
    i.add_argument("--no-export", action="store_true", help="do not update the log files")
    i.set_defaults(func=cmd_import)

    e = sub.add_parser("export", help="rewrite the plain-text log files")
    e.add_argument("--since", help="YYYY-MM-DD (local date); default: everything")
    e.add_argument("--out", help="output folder (default: <config dir>/logs)")
    e.set_defaults(func=cmd_export)

    pp = sub.add_parser("post", help='mode "direct": post new rows to the two webhooks now')
    pp.add_argument("--post-backlog", action="store_true",
                    help="first run: also post rows that were already in the spool")
    pp.add_argument("--dry-run", action="store_true", help="print what would be posted; send and mark nothing")
    pp.set_defaults(func=cmd_post)

    up = sub.add_parser("upload", help='mode "upload": send new rows to the bot now')
    up.set_defaults(func=cmd_upload)

    s = sub.add_parser("stats", help="show what the spool holds")
    s.set_defaults(func=cmd_stats)

    args = p.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to a legacy code page
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        cfg = config_mod.load(args.config)
    except config_mod.ConfigError as e:
        log.error("%s", e)
        return 2
    try:
        return args.func(args, cfg)
    except (SVParseError, SchemaError) as e:
        log.error("%s", e)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
