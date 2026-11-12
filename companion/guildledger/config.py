"""config.toml loading. Webhook URLs are secrets: never print or log them."""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from datetime import timezone, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

log = logging.getLogger(__name__)

MODES = ("direct", "upload")


@dataclass
class Config:
    sv_path: Path | None = None
    timezone: str = "Europe/Zurich"
    mode: str = "direct"
    collector: str = "collector"
    data_dir: Path = field(default_factory=lambda: Path("."))
    chat_webhook: str = field(default="", repr=False)
    roster_webhook: str = field(default="", repr=False)
    ingest_webhook: str = field(default="", repr=False)
    meta: str = "summary"  # direct mode: chat rows without text -> "summary" | "lines" | "skip"
    poll_seconds: float = 2.0
    stable_seconds: float = 1.0

    @property
    def db_path(self) -> Path:
        return self.data_dir / "spool.db"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    def tz(self) -> tzinfo | None:
        return resolve_tz(self.timezone)


class ConfigError(ValueError):
    pass


def load(path: str | Path | None) -> Config:
    """Load ``path``; with ``None`` or a missing default file, return defaults rooted at the cwd."""
    if path is None:
        default = Path("config.toml")
        if not default.exists():
            return Config()
        path = default
    path = Path(path)
    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    except FileNotFoundError as e:
        raise ConfigError(f"config file not found: {path}") from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from e

    base = path.resolve().parent
    cfg = Config(data_dir=base)
    if "sv_path" in raw:
        cfg.sv_path = Path(raw["sv_path"])
    cfg.timezone = str(raw.get("timezone", cfg.timezone))
    cfg.mode = str(raw.get("mode", cfg.mode))
    if cfg.mode not in MODES:
        raise ConfigError(f"mode must be one of {MODES}, not {cfg.mode!r}")
    cfg.collector = str(raw.get("collector", cfg.collector)).strip() or "collector"
    if "data_dir" in raw:
        d = Path(raw["data_dir"])
        cfg.data_dir = d if d.is_absolute() else base / d
    direct = raw.get("direct", {}) or {}
    cfg.chat_webhook = str(direct.get("chat_webhook", ""))
    cfg.roster_webhook = str(direct.get("roster_webhook", ""))
    cfg.meta = str(direct.get("meta", cfg.meta))
    if cfg.meta not in ("summary", "lines", "skip"):
        raise ConfigError(f'[direct] meta must be "summary", "lines" or "skip", not {cfg.meta!r}')
    upload = raw.get("upload", {}) or {}
    cfg.ingest_webhook = str(upload.get("ingest_webhook", ""))
    watch = raw.get("watch", {}) or {}
    cfg.poll_seconds = float(watch.get("poll_seconds", cfg.poll_seconds))
    cfg.stable_seconds = float(watch.get("stable_seconds", cfg.stable_seconds))
    return cfg


_warned: set[str] = set()


def resolve_tz(name: str) -> tzinfo | None:
    """IANA zone by name, or ``None`` meaning "this computer's local time" (use with
    ``datetime.fromtimestamp(ts, tz)``, which handles DST for ``None`` too). Falls back to ``None`` when
    there is no tz database (Windows without the ``tzdata`` package): a collector PC normally runs in the
    guild's zone anyway."""
    if name.upper() in ("UTC", "Z"):
        return timezone.utc
    if name.lower() == "local":
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        if name not in _warned:
            _warned.add(name)
            log.warning("time zone %r not available (pip install tzdata); using this computer's local time", name)
        return None
