"""Build the companion package (a zip): the code, the Windows starters, the example settings and the guide.

Two uses, one builder:
- unpersonalised (`config_text=None`): `GuildLedger-companion.zip`, published with every release and
  fetched by update.py. Holds nothing personal.
- personalised: the same files plus a ready `config.toml` for one officer. The bot builds it for
  `/collector invite` (bot/guildledger_bot/collectors.py) and hands it to that officer only.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

from . import __version__

TOP_FILES = ("start-companion.cmd", "autostart-on.cmd", "autostart-off.cmd", "config.example.toml",
             "COLLECTOR.md")
_FIXED_TIME = (2026, 1, 1, 0, 0, 0)  # same input -> same zip (the checksum in companion-version.txt)


class PackageError(RuntimeError):
    pass


def find_root() -> Path:
    """The folder holding the starters and the guide: next to the code (checkout, officer folder), or
    where the server keeps its copy of the source (bot/deploy/setup.sh, Dockerfile)."""
    here = Path(__file__).resolve().parent.parent
    cands = [Path(p) for p in (os.environ.get("GUILDLEDGER_COMPANION_DIR"),) if p]
    cands += [here, Path("/opt/guildledger/src/companion"), Path("/app/companion")]
    for c in cands:
        if all((c / f).is_file() for f in TOP_FILES):
            return c
    raise PackageError("the companion's starter files were not found (set GUILDLEDGER_COMPANION_DIR to the"
                       " repository's companion folder)")


def render_config(ingest_webhook: str, collector: str, timezone: str = "Europe/Zurich") -> str:
    """A complete config.toml for one officer. The WoW folder is found by the companion itself."""
    q = lambda s: json.dumps(str(s), ensure_ascii=False)  # noqa: E731 - a TOML basic string
    return "\n".join([
        "# GuildLedger companion - your personal settings, made for you by your guild's GuildLedger bot.",
        "# This file holds your personal upload link: never send it to anyone, never post it.",
        "# Updates of the companion never change this file. Every setting: config.example.toml.",
        "",
        f"collector = {q(collector)}",
        "",
        "[upload]",
        f"ingest_webhook = {q(ingest_webhook)}",
        "",
        "[general]",
        'mode = "upload"',
        f"timezone = {q(timezone)}",
        "",
    ])


def build_zip(root: Path | None = None, config_text: str | None = None) -> bytes:
    root = root or find_root()
    code = Path(__file__).resolve().parent
    entries: list[tuple[str, bytes]] = []
    for name in TOP_FILES:
        data = (root / name).read_bytes()
        if name.endswith(".cmd"):  # batch files need Windows line endings, whatever git checked out
            data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        entries.append((name, data))
    for py in sorted(code.glob("*.py")):
        entries.append((f"guildledger/{py.name}", py.read_bytes()))
    if config_text is not None:
        entries.append(("config.toml", config_text.encode("utf-8")))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            info = zipfile.ZipInfo(name, _FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
    return buf.getvalue()


def write_release(out_dir: Path, root: Path | None = None) -> tuple[Path, Path]:
    """The two release assets update.py downloads: the zip and its version + checksum line."""
    from .update import VERSION_NAME, ZIP_NAME  # noqa: PLC0415

    out_dir.mkdir(parents=True, exist_ok=True)
    data = build_zip(root)
    zip_path, ver_path = out_dir / ZIP_NAME, out_dir / VERSION_NAME
    zip_path.write_bytes(data)
    ver_path.write_text(f"{__version__} {hashlib.sha256(data).hexdigest()}\n", encoding="utf-8")
    return zip_path, ver_path
