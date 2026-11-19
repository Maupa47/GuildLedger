"""Find the addon's data files without asking: every `GuildLedger.lua` under a World of Warcraft folder.

WoW keeps one SavedVariables folder per game account (`<WoW>/_forever_/WTF/Account/<ACCOUNT>/SavedVariables`).
An officer who plays an alt on a second account has two of them, so `find_sv_files` returns all and the
watch loop reads each. Only looks at folder names and at files called GuildLedger.lua; never writes.
"""

from __future__ import annotations

import os
import string
from pathlib import Path

SV_NAME = "GuildLedger.lua"
WOW_DIR = "World of Warcraft"
# WoW: Forever's folder inside the WoW folder (and its name during the beta). Other game versions are never
# read: a GuildLedger.lua there would belong to another game, maybe another guild.
FLAVORS = ("_forever_", "_classic_beta_")
# Where people install it, relative to a drive or home folder.
_COMMON = ("", "Games", "Program Files (x86)", "Program Files", "Spiele", "Battle.net", "Blizzard")


def _registry_roots() -> list[Path]:
    """Windows: the install path Battle.net wrote to the registry (any game version of WoW)."""
    try:
        import winreg  # noqa: PLC0415 - Windows only
    except ImportError:
        return []
    out: list[Path] = []
    keys = (r"SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft",
            r"SOFTWARE\Blizzard Entertainment\World of Warcraft")
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for key in keys:
            try:
                with winreg.OpenKey(hive, key) as k:
                    value, _ = winreg.QueryValueEx(k, "InstallPath")
            except OSError:
                continue
            p = Path(str(value))
            # InstallPath points at one version's folder (…\World of Warcraft\_retail_\): its parent is the root.
            out.append(p.parent if p.name.startswith("_") and p.name.endswith("_") else p)
    return out


def candidate_roots(extra: list[Path] | None = None) -> list[Path]:
    """Folders that may be a World of Warcraft installation, most likely first (existing ones only)."""
    cands: list[Path] = list(extra or [])
    cands += _registry_roots()
    if os.name == "nt":
        drives = [Path(f"{d}:\\") for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    else:
        home = Path.home()
        drives = [home, Path("/Applications"),
                  home / ".wine" / "drive_c", home / "Games" / "battlenet" / "drive_c"]
    for d in drives:
        for sub in _COMMON:
            cands.append(d / sub / WOW_DIR if sub else d / WOW_DIR)
    seen: set[str] = set()
    out: list[Path] = []
    for c in cands:
        try:
            key = str(c.resolve()).lower()
            if key in seen or not c.is_dir():
                continue
        except OSError:
            continue
        seen.add(key)
        out.append(c)
    return out


def sv_files_in(root: Path) -> list[Path]:
    """Every GuildLedger.lua of WoW: Forever below one WoW folder (all accounts)."""
    found: list[Path] = []
    try:
        # `root` may be the WoW folder, one version's folder (_forever_) or its WTF folder: all work.
        for pattern in (*(f"{fl}/WTF/Account/*/SavedVariables/{SV_NAME}" for fl in FLAVORS),
                        f"WTF/Account/*/SavedVariables/{SV_NAME}",
                        f"Account/*/SavedVariables/{SV_NAME}"):
            found += [p for p in root.glob(pattern) if p.is_file()]
    except OSError:
        pass
    return sorted(found)


def find_sv_files(extra: list[Path] | None = None) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for root in candidate_roots(extra):
        for p in sv_files_in(root):
            key = str(p).lower()
            if key not in seen:
                seen.add(key)
                out.append(p)
    return out
