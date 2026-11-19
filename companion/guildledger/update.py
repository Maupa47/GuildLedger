"""Self-update for an officer's companion folder: fetch the newest public package and replace the code.

The package (`GuildLedger-companion.zip`, built by package.py, published as a GitHub release asset) holds no
personal data. `config.toml` (the upload link), the spool database, logs and state are never in it and are
never touched, so one unpersonalised file updates every officer. A repository checkout (the admin's PC) and
a pip-installed copy (the server) are never updated this way.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from . import __version__

log = logging.getLogger(__name__)

REPO = "Maupa47/GuildLedger"
BASE_URL = f"https://github.com/{REPO}/releases/latest/download/"
ZIP_NAME = "GuildLedger-companion.zip"
VERSION_NAME = "companion-version.txt"  # one line: "<version> <sha256 of the zip>"
MAX_ZIP = 5 * 1024 * 1024
PROTECTED = {"config.toml", "spool.db", "state.json", "watch.lock"}
_TOP_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(cmd|md|toml|txt)$")
_CODE_OK = re.compile(r"^guildledger/[A-Za-z0-9_]+\.py$")

Fetch = Callable[[str], bytes]


class UpdateError(RuntimeError):
    pass


def http_fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "GuildLedger-companion"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - fixed https URL
            return r.read(MAX_ZIP + 1)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise UpdateError(str(e)) from e


def _parts(v: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", v))


def newer(candidate: str, current: str) -> bool:
    return _parts(candidate) > _parts(current)


def install_root() -> Path | None:
    """The folder to update, or None when this copy is not an officer's unzipped package."""
    root = Path(__file__).resolve().parent.parent
    if not (root / "start-companion.cmd").is_file():
        return None  # pip-installed (server) or something else
    if (root.parent / ".git").exists() or (root / ".git").exists():
        return None  # a repository checkout updates with git
    return root


def latest(fetch: Fetch = http_fetch) -> tuple[str, str]:
    """(version, sha256) of the newest published package."""
    text = fetch(BASE_URL + VERSION_NAME).decode("utf-8", errors="replace").strip()
    m = re.fullmatch(r"v?(\d+(?:\.\d+)+)\s+([0-9a-f]{64})", text)
    if not m:
        raise UpdateError("unexpected version file")
    return m.group(1), m.group(2)


def apply_zip(data: bytes, root: Path) -> list[str]:
    """Unpack the package over `root`. Only known kinds of files, never a protected one, never outside root."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise UpdateError("the downloaded package is not a zip file") from e
    todo: list[tuple[str, bytes]] = []
    with zf:
        for info in zf.infolist():
            name = info.filename
            if info.is_dir():
                continue
            if name in PROTECTED or not (_TOP_OK.match(name) or _CODE_OK.match(name)):
                raise UpdateError(f"unexpected file in the package: {name!r}")
            todo.append((name, zf.read(info)))
    if not any(n == "guildledger/__init__.py" for n, _ in todo):
        raise UpdateError("the package has no companion code")
    written = []
    for name, content in todo:
        dest = root / name
        try:
            if dest.is_file() and dest.read_bytes() == content:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".new")
            tmp.write_bytes(content)
            os.replace(tmp, dest)
        except OSError as e:
            raise UpdateError(f"could not write {name}: {e}") from e
        written.append(name)
    return written


def update(root: Path, current: str = __version__, fetch: Fetch = http_fetch) -> str | None:
    """Install the newest package if it is newer than `current`. Returns the new version, or None."""
    version, sha = latest(fetch)
    if not newer(version, current):
        return None
    data = fetch(BASE_URL + ZIP_NAME)
    if len(data) > MAX_ZIP:
        raise UpdateError("the package is unexpectedly large")
    if hashlib.sha256(data).hexdigest() != sha:
        raise UpdateError("the package does not match its checksum")
    apply_zip(data, root)
    return version
