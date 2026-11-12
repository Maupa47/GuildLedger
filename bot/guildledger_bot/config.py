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
