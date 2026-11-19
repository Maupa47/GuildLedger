"""GuildLedger companion CLI.

    python -m guildledger [--config config.toml] watch [--once]
    python -m guildledger import <GuildLedger.lua> [--collector NAME]
    python -m guildledger export [--since YYYY-MM-DD]
    python -m guildledger stats
    python -m guildledger post [--post-backlog]      (mode = "direct")
    python -m guildledger upload                       (mode = "upload")
    python -m guildledger update                       (officer folder: install the newest companion)
    python -m guildledger package [--out dist]         (admin: build the public update package)

Without sv_path in the config, watch finds every GuildLedger.lua itself (detect.py): all WoW accounts on this PC.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from . import __version__
from . import config as config_mod
from . import detect
from . import discord
from . import loot
from . import package as package_mod
from . import update as update_mod
from . import upload as upload_mod
from .direct import Poster
from .export import export
from .lock import InstanceLock
from .upload import Uploader
from .store import SchemaError, Spool
from .svparse import SVParseError, parse_file

log = logging.getLogger("guildledger")


def _open(cfg: config_mod.Config, db: str | None) -> Spool:
    return Spool(db or cfg.db_path)


def import_hub_file(spool: Spool, path: Path, collector: str, data: dict | None = None) -> loot.LootResult:
    """Amazing Hub's AmazingHub.lua: points, loot history, wishlists, raids (shared/schema.md 7)."""
    if data is None:
        data = parse_file(str(path))
    seen = int(path.stat().st_mtime)
    res = loot.import_hub(spool.db, data, spool.guild_names(), collector, seen)
    if res.changed:
        log.info("imported %s: %s", path.name, res.summary())
    return res


def import_file(spool: Spool, cfg: config_mod.Config, path: Path, collector: str, do_export: bool = True):
    data = parse_file(str(path))
    if "AmazingHubDB" in data and "GuildLedgerDB" not in data:
        return import_hub_file(spool, path, collector, data)
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


def _import_hub_if_changed(spool: Spool, cfg: config_mod.Config, hub: Path | None, hub_seen):
    """Import AmazingHub.lua when it changed (WoW writes it together with GuildLedger.lua). Never fatal."""
    if hub is None:
        return hub_seen
    sig = _signature(hub)
    if sig is None or sig == hub_seen:
        return hub_seen
    time.sleep(cfg.stable_seconds)
    if _signature(hub) != sig:
        return hub_seen
    try:
        import_hub_file(spool, hub, cfg.collector)
    except (SVParseError, OSError, UnicodeError) as e:
        log.warning("could not read %s (%s); loot data skipped until it changes", hub.name, e)
    return sig


REDETECT_EVERY = 60  # s: look again for data files (a first /reload, an alt on a second WoW account)
UPDATE_EVERY = 6 * 3600  # s: while running, only tell that an update exists (it installs at the next start)


def _load_state(cfg: config_mod.Config) -> dict:
    try:
        data = json.loads(cfg.state_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(cfg: config_mod.Config, state: dict) -> None:
    try:
        cfg.state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    except OSError as e:
        log.debug("could not save %s: %s", cfg.state_path.name, e)


def _targets(cfg: config_mod.Config, state: dict) -> list[Path]:
    """The data files to watch: the one from the config, else every GuildLedger.lua that can be found."""
    if cfg.sv_path:
        return [cfg.sv_path]
    extra = [Path(p) for p in (cfg.wow_dir, state.get("wow_dir")) if p]
    return detect.find_sv_files(extra)


def _ask_wow_dir(cfg: config_mod.Config, state: dict) -> None:
    """Nothing found in the usual places: ask once where WoW is (only in a window somebody can type in)."""
    if state.get("wow_dir_asked") or not sys.stdin or not sys.stdin.isatty():
        return
    state["wow_dir_asked"] = True
    print("\nI could not find your World of Warcraft folder in the usual places.")
    print(r"Paste its path here (for example D:\Spiele\World of Warcraft) and press Enter,")
    print("or just press Enter if GuildLedger has never run in the game on this PC yet:")
    try:
        answer = input("> ").strip().strip('"').strip("'")
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer:
        if Path(answer).is_dir():
            state["wow_dir"] = answer
        else:
            print("That folder does not exist; I keep looking in the usual places.")
    _save_state(cfg, state)


def _say_hello(cfg: config_mod.Config, state: dict, transport=None) -> None:
    """First start in upload mode: an empty upload proves the personal link works; the bot reports it."""
    key = hashlib.sha256(cfg.ingest_webhook.encode("utf-8")).hexdigest()[:16]
    if cfg.mode != "upload" or not cfg.ingest_webhook or state.get("hello") == key:
        return
    data = gzip.compress(b"", mtime=0)
    try:
        kw = {"transport": transport} if transport else {}
        discord.Webhook(cfg.ingest_webhook, "ingest", **kw).post_file(
            upload_mod.describe(cfg.collector, 0, data), "gl-hello.jsonl.gz", data)
    except discord.WebhookError as e:
        log.error("test upload failed: %s. Check the upload link in config.toml, or ask the admin for a new"
                  " collector package.", e)
        return
    log.info("test upload OK: Discord accepted your personal upload link")
    state["hello"] = key
    _save_state(cfg, state)


def _self_update(cfg: config_mod.Config, args) -> int | None:
    """Officer folder only: install a newer companion and start it. Returns its exit code, else None."""
    if args.once or not cfg.update_auto or os.environ.get("GUILDLEDGER_NO_UPDATE"):
        return None
    root = update_mod.install_root()
    if root is None:
        return None
    try:
        version = update_mod.update(root)
    except update_mod.UpdateError as e:
        log.info("update check skipped (%s)", e)
        return None
    if version is None:
        return None
    log.info("updated the companion %s -> %s (your settings were not touched); restarting",
             __version__, version)
    env = dict(os.environ, GUILDLEDGER_NO_UPDATE="1")  # the new copy must not loop
    return subprocess.call([sys.executable, "-m", "guildledger", *sys.argv[1:]], cwd=str(root), env=env)


def _import_changed(spool: Spool, cfg: config_mod.Config, path: Path) -> None:
    for attempt in (1, 2):
        try:
            import_file(spool, cfg, path, cfg.collector)
            return
        except (SVParseError, SchemaError, OSError, UnicodeError) as e:
            if attempt == 1:
                log.warning("could not read %s (%s); retrying once", path.name, e)
                time.sleep(cfg.stable_seconds)
            else:
                log.error("giving up on this version of %s: %s", path.name, e)


def cmd_watch(args, cfg) -> int:
    code = _self_update(cfg, args)
    if code is not None:
        return code
    lock = InstanceLock(cfg.data_dir / "watch.lock")
    if not lock.acquire():
        log.error("another GuildLedger companion is already running for this folder; close it first")
        return 1
    state = _load_state(cfg)
    direct = not args.no_post  # post (mode "direct") or upload (mode "upload")
    transport = getattr(args, "transport", None)
    seen: dict[Path, object] = {}  # data file -> signature of the version already imported
    hub_seen: dict[Path, object] = {}
    paths: list[Path] = []
    next_detect = next_post = 0.0
    next_update_note = time.monotonic() + UPDATE_EVERY
    told_missing = False
    with lock, _open(cfg, args.db) as spool:
        if direct and not args.once:
            _say_hello(cfg, state, transport)
        while True:
            now = time.monotonic()
            if now >= next_detect:
                next_detect = now + REDETECT_EVERY
                found = _targets(cfg, state)
                for p in found:
                    if p not in paths:
                        log.info("watching %s (collector %s, mode %s)", p, cfg.collector, cfg.mode)
                paths = found
                if not paths and not told_missing:
                    told_missing = True
                    if args.once:
                        log.error("no GuildLedger data file found (set sv_path in the config)")
                        return 1
                    _ask_wow_dir(cfg, state)
                    paths = _targets(cfg, state)
                    if not paths:
                        log.info("no GuildLedger data file yet: log in to WoW with the GuildLedger addon on and"
                                 " type /reload once. I keep looking.")
                        next_detect = now + 10
            if direct and now >= next_post:
                send_now(spool, cfg, args.post_backlog, transport)
                next_post = time.monotonic() + POST_EVERY
            if now >= next_update_note and cfg.update_auto and update_mod.install_root():
                next_update_note = now + UPDATE_EVERY
                try:
                    version, _ = update_mod.latest()
                    if update_mod.newer(version, __version__):
                        log.info("companion %s is available: close this window and start it again to update",
                                 version)
                except update_mod.UpdateError:
                    pass
            changed = False
            for path in paths:
                sig = _signature(path)
                hub = cfg.hub_for(path)
                if sig is not None and sig != seen.get(path):
                    time.sleep(cfg.stable_seconds)
                    if _signature(path) != sig:
                        changed = True  # WoW is still writing: look again right away
                        continue
                    _import_changed(spool, cfg, path)
                    seen[path] = sig
                    hub_seen[path] = _import_hub_if_changed(spool, cfg, hub, hub_seen.get(path))
                    changed = True
                elif hub is not None and _signature(hub) not in (None, hub_seen.get(path)):
                    hub_seen[path] = _import_hub_if_changed(spool, cfg, hub, hub_seen.get(path))
                elif sig is None and args.once:
                    log.error("file not found: %s", path)
                    return 1
            if changed:
                if direct and all(p in seen for p in paths):
                    send_now(spool, cfg, args.post_backlog, transport)
                    next_post = time.monotonic() + POST_EVERY
                if args.once and all(p in seen for p in paths):
                    return 0
                continue
            time.sleep(cfg.poll_seconds)


def cmd_package(args, cfg) -> int:  # noqa: ARG001
    zip_path, ver_path = package_mod.write_release(Path(args.out))
    print(f"wrote {zip_path} and {ver_path} ({ver_path.read_text(encoding='utf-8').strip()})")
    return 0


def cmd_update(args, cfg) -> int:  # noqa: ARG001
    root = update_mod.install_root()
    if root is None:
        log.error("this copy is not an unzipped collector package (a repository checkout updates with git)")
        return 2
    try:
        version = update_mod.update(root)
    except update_mod.UpdateError as e:
        log.error("update failed: %s", e)
        return 1
    print(f"updated to {version}; start the companion again" if version else f"already up to date ({__version__})")
    return 0


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

    u = sub.add_parser("update", help="officer folder: install the newest companion now (settings are kept)")
    u.set_defaults(func=cmd_update)

    pk = sub.add_parser("package", help="admin: build the public update package (zip + version file)")
    pk.add_argument("--out", default="dist", help="output folder (default: dist)")
    pk.set_defaults(func=cmd_package)

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
