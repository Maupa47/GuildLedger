"""Bot configuration (/etc/guildledger/config.toml on the server). The token and webhook URLs are
secrets: they live only in that file (mode 600) and are never logged."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    pass


@dataclass
class BotConfig:
    token: str = field(default="", repr=False)
    ingest_channel_id: int = 0
    collectors: dict[int, str] = field(default_factory=dict)  # webhook ID -> collector name
    chat_webhook: str = field(default="", repr=False)
    roster_webhook: str = field(default="", repr=False)
    db_path: Path = Path("/var/lib/guildledger/guildledger.db")
    timezone: str = "Europe/Zurich"
    meta: str = "summary"
    hold_chat: int = 600
    post_every: int = 30
    post_since: int | None = None  # unix s; default: the bot's first start (state in the database)
    backup_webhook: str = field(default="", repr=False)  # optional: private #gl-backup channel
    ops_webhook: str = field(default="", repr=False)  # optional: private #gl-ops (report + warnings)
    report_hour: int = 6
    alert_after_hours: float = 6
    server_id: int = 0  # Discord server for slash commands (0: commands everywhere, slow to appear)
    verified_role_id: int = 0  # [link] decision 5: role given to linked guild members (0 = off)
    rank_roles: dict[str, int] = field(default_factory=dict)  # guild rank name -> Discord role ID
    set_nickname: bool = False  # nickname = highest-level linked character in the guild
    grace_days: int = 7  # roles stay this long after the last linked character left the guild
    loot_webhook: str = field(default="", repr=False)  # [loot] #guild-loot channel (empty = no loot posts)
    loot_hold: int = 600  # s: loot and points wait this long, so every collector's copy is merged first
    loot_top: int = 10  # standings shown under a raid summary


def load(path: str | Path) -> BotConfig:
    path = Path(path)
    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    except FileNotFoundError as e:
        raise ConfigError(f"config file not found: {path}") from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from e

    cfg = BotConfig()
    discord_ = raw.get("discord", {}) or {}
    cfg.token = str(discord_.get("token", ""))
    cfg.server_id = int(discord_.get("server_id", 0) or 0)
    try:
        cfg.ingest_channel_id = int(discord_.get("ingest_channel_id", 0))
    except (TypeError, ValueError) as e:
        raise ConfigError("[discord] ingest_channel_id must be a number (right-click channel -> Copy ID)") from e
    post = raw.get("post", {}) or {}
    cfg.chat_webhook = str(post.get("chat_webhook", ""))
    cfg.roster_webhook = str(post.get("roster_webhook", ""))
    cfg.timezone = str(post.get("timezone", cfg.timezone))
    cfg.meta = str(post.get("meta", cfg.meta))
    cfg.hold_chat = int(post.get("hold_chat_seconds", cfg.hold_chat))
    cfg.post_every = int(post.get("every_seconds", cfg.post_every))
    if "since" in post:
        cfg.post_since = int(post["since"])
    cfg.backup_webhook = str((raw.get("backup", {}) or {}).get("webhook", ""))
    ops = raw.get("ops", {}) or {}
    cfg.ops_webhook = str(ops.get("webhook", ""))
    cfg.report_hour = int(ops.get("report_hour", cfg.report_hour))
    cfg.alert_after_hours = float(ops.get("alert_after_hours", cfg.alert_after_hours))
    link = raw.get("link", {}) or {}
    cfg.verified_role_id = int(link.get("verified_role_id", 0) or 0)
    cfg.rank_roles = {str(k): int(v) for k, v in (link.get("rank_roles", {}) or {}).items() if int(v or 0)}
    cfg.set_nickname = bool(link.get("set_nickname", False))
    cfg.grace_days = int(link.get("grace_days", cfg.grace_days))
    loot_ = raw.get("loot", {}) or {}
    cfg.loot_webhook = str(loot_.get("webhook", ""))
    cfg.loot_hold = int(loot_.get("hold_seconds", cfg.loot_hold))
    cfg.loot_top = int(loot_.get("standings_top", cfg.loot_top))
    storage = raw.get("storage", {}) or {}
    if "db_path" in storage:
        cfg.db_path = Path(storage["db_path"])
    for key, name in (raw.get("collectors", {}) or {}).items():
        try:
            cfg.collectors[int(key)] = str(name).strip()
        except ValueError as e:
            raise ConfigError(f"[collectors] key {key!r} must be a webhook ID (the number in the webhook URL)") from e

    if not cfg.token:
        raise ConfigError("[discord] token is missing")
    if not cfg.ingest_channel_id:
        raise ConfigError("[discord] ingest_channel_id is missing")
    if not cfg.collectors:
        raise ConfigError("[collectors] lists no webhook: every upload would be ignored")
    if cfg.meta not in ("summary", "lines", "skip"):
        raise ConfigError('[post] meta must be "summary", "lines" or "skip"')
    if not cfg.chat_webhook and not cfg.roster_webhook:
        raise ConfigError("[post] needs chat_webhook and/or roster_webhook")
    return cfg
