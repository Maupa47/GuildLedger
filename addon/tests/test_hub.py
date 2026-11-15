"""Amazing Hub (addon/AmazingHub, built by tools/rebrand-hub.py from GuildOS): guard, defaults, upstream checks."""

from __future__ import annotations

import glob
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HUB = ROOT / "addon" / "AmazingHub"
VENDOR = ROOT / "vendor-ref" / "GuildOS"

# GuildOS's own checks (addon/AmazingHub/tools) that fail on purpose in the hub, and why. Anything else failing is a
# regression. (Baseline at the pinned commit: compat-core and retail-stats fail there too.)
EXPECTED_FAIL = {
    "chat-click.lua": "whisper to a non-member (recruiting) is blocked",
    "retail-namesakes.lua": "whisper to a non-member is blocked",
    "recruit-network.lua": "messages to non-members are blocked",
    "gossip.lua": "the mesh's public channel is blocked",
    "probe-channel.lua": "addon messages to a channel are blocked",
    "trade-icons.lua": "posting to trade channels is blocked",
    "client-detection.lua": "web is off until tested",
    "launch-flags.lua": "founding is off until tested",
    "command-settings.lua": "recruitment module off by default",
    "dashboard-countdown.lua": "recruitment card hidden (module off)",
    "dashboard-recruit.lua": "recruitment module off by default",
    "recruit-channels.lua": "recruitment module off by default",
    "recruit-module-off.lua": "recruitment module off by default",
    "startup-isolation.lua": "recruitment module off: its officer stage never starts",
    "guild-chat.lua": "GuildLedger keeps the guild chat",
    "secret-values.lua": "stops at GuildChat:Initialize (off); passes with it on",
    "window-shell.lua": "slash commands renamed to /amazing, /amazinghub",
    "no-brutus.lua": "needs `git ls-files` of the folder (fails until committed)",
    "compat-core.lua": "fails upstream too (needs a luajit CLI)",
    "retail-stats.lua": "fails upstream too",
}


def _luajit():
    return pytest.importorskip("lupa.luajit21")


def _run_lua(lj, path: Path, addon: Path) -> str:
    L = lj.LuaRuntime(unpack_returned_tuples=True)
    L.execute('os.exit = function(c) error("__EXIT__" .. tostring(c), 0) end; io.write = function() end;'
              ' print = function() end; io.stderr = { write = function() end }')
    L.globals().ADDON = str(addon).replace("\\", "/")
    try:
        L.execute(f"dofile([[{path.as_posix()}]])")
        return "ok"
    except Exception as e:  # lupa.LuaError
        msg = str(e)
        return "ok" if ("__EXIT__0" in msg or "__EXIT__true" in msg) else msg.splitlines()[0][:200]


def test_outbound_guard():
    lj = _luajit()
    assert _run_lua(lj, Path(__file__).with_name("hub_guard.lua"), HUB) == "ok"


def test_ledger_tab():
    lj = _luajit()
    assert _run_lua(lj, Path(__file__).with_name("hub_ledger.lua"), HUB) == "ok"


def test_settings_sections_and_world_map():
    lj = _luajit()
    assert _run_lua(lj, Path(__file__).with_name("hub_settings.lua"), HUB) == "ok"


def test_ledger_tab_is_built_in():
    toc = (HUB / "AmazingHub.toc").read_text("utf-8")
    assert toc.rstrip().endswith("UI\\PackTweaks.lua\nUI\\LedgerPanel.lua\nUI\\SettingsPlus.lua")
    for name in ("PackTweaks.lua", "LedgerPanel.lua", "SettingsPlus.lua"):
        assert (HUB / "UI" / name).read_bytes() == (ROOT / "tools" / "hub-extra" / name).read_bytes()


def test_no_upstream_names_left():
    """In game nothing says GuildOS or Chehul (admin's decision 2026-11-14). The MIT notice stays in LICENSE
    and the TOC's X-Upstream line (neither is shown in game) and in THIRD_PARTY.md."""
    old = re.compile(r"guild[ -]?os|chehul|danielcosta|amazing\.me", re.I)
    hits = []
    for f in HUB.rglob("*"):
        if not f.is_file() or f.name == "LICENSE" or f.suffix.lower() in {".tga", ".ttf", ".blp", ".png", ".ogg"}:
            continue
        for n, line in enumerate(f.read_text("utf-8", errors="replace").splitlines(), 1):
            if old.search(line) and not line.startswith("## X-Upstream:"):
                hits.append(f"{f.relative_to(HUB)}:{n}")
    assert hits == []


def test_upstream_checks(monkeypatch):
    lj = _luajit()
    monkeypatch.chdir(HUB)
    failed, passed = {}, 0
    for f in sorted(glob.glob("tools/*.lua")):
        src = open(f, "rb").read()
        if b"checks" not in src and b"check(" not in src:
            continue
        res = _run_lua(lj, Path(f), Path("."))
        if res == "ok":
            passed += 1
        else:
            failed[os.path.basename(f)] = res
    unexpected = {k: v for k, v in failed.items() if k not in EXPECTED_FAIL}
    assert not unexpected, f"new failures in GuildOS's checks: {unexpected}"
    assert passed >= 100, f"only {passed} upstream checks passed"


CHAT_GLOBALS = re.compile(r"(?<![.\w:\"])(SendChatMessage|JoinChannelByName|JoinTemporaryChannel)(?!\w)")


def _code(path: Path) -> str:
    return "\n".join(l for l in path.read_text("utf-8").split("\n") if not l.lstrip().startswith("--"))


def test_every_direct_chat_call_is_shadowed():
    for f in HUB.rglob("*.lua"):
        rel = f.relative_to(HUB).as_posix()
        if rel.startswith("tools/") or rel == "Core/Compat.lua":
            continue
        names = {m.group(1) for m in CHAT_GLOBALS.finditer(_code(f))}
        head = f.read_text("utf-8").split("\n", 6)[:5]
        for n in names:
            assert any(l.startswith(f"local {n} =") for l in head), f"{rel} calls {n} without the guard"


def test_raw_addon_sends_only_in_guarded_places():
    allowed = {"Core/Compat.lua", "Libs/LibAmzHubMesh.lua", "Libs/ChatThrottleLib.lua", "Libs/AceComm-3.0.lua",
               "Libs/LibSerialize.lua", "Core/Probe.lua"}
    for f in HUB.rglob("*.lua"):
        rel = f.relative_to(HUB).as_posix()
        if rel.startswith("tools/") or rel in allowed:
            continue
        code = _code(f)
        assert "C_ChatInfo.SendAddonMessage" not in code and "SendCommMessage" not in code, rel


def test_defaults_and_names():
    core = (HUB / "Core" / "Core.lua").read_text("utf-8")
    assert "local OFF_UNTIL_TESTED = { alliance = true, recruitment = true, web = true, founding = true }" in core
    for k in ("lootMaster", "consumableChecker", "recruitment"):
        assert re.search(rf"\n\s+{k} = false,", core), k
    assert 'M.PREFIX_ROOT = "AmzHub"' in (HUB / "Libs" / "LibAmzHubMesh.lua").read_text("utf-8")
    toc = (HUB / "AmazingHub.toc").read_text("utf-8")
    assert "## Interface: 16001\n" in toc and "## SavedVariables: AmazingHubDB\n" in toc
    assert "## OptionalDeps: GuildLedger\n" in toc
    cmds = (HUB / "Core" / "Commands.lua").read_text("utf-8")
    assert 'SLASH_AMAZINGHUB1 = "/amazing"' in cmds and 'SLASH_AMAZINGHUB2 = "/amazinghub"' in cmds
    # every file the TOC loads exists
    for line in toc.splitlines():
        if line and not line.startswith("#"):
            assert (HUB / line.replace("\\", "/")).is_file(), line


@pytest.mark.skipif(not (VENDOR / ".git").exists(), reason="vendor-ref/GuildOS not checked out")
def test_hub_matches_the_script(tmp_path):
    """addon/AmazingHub is exactly what tools/rebrand-hub.py builds: nobody edited it by hand."""
    out = tmp_path / "AmazingHub"
    subprocess.run([sys.executable, str(ROOT / "tools" / "rebrand-hub.py"), "--out", str(out)], check=True,
                   capture_output=True)
    built = {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    have = {p.relative_to(HUB).as_posix(): p.read_bytes() for p in HUB.rglob("*") if p.is_file()}
    assert built.keys() == have.keys()
    assert [k for k in built if built[k] != have[k]] == []


def test_classic_style_is_the_default():
    style = (HUB / "Core" / "Style.lua").read_text("utf-8")
    assert 'Style.DEFAULT = "forever"' in style and 'Style.ORDER = { "forever", "amazinghub" }' in style
    assert 'name = "Classic"' in style and 'name = "Modern"' in style
    assert 'Style.ALIASES = { classic = "forever", modern = "amazinghub" }' in style
