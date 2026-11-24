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
    "engagement-panel.lua": "Leadership's Engagement sub-tab is removed (recruiting and addon invites blocked on Forever)",
    "secret-values.lua": "stops at GuildChat:Initialize (off); passes with it on",
    "window-shell.lua": "slash commands renamed to /amazing, /amazinghub",
    "no-brutus.lua": "needs `git ls-files` of the folder (fails until committed)",
    "compat-core.lua": "fails upstream too (needs a luajit CLI)",
    "retail-stats.lua": "fails upstream too",
    # 1.40.0 (HUB_AUDIT section 10)
    "alliance-link.lua": "the alliance link never starts (A1)",
    "alt-sync.lua": "our own versions decide who is a legacy alt client (LEGACY_ALT_MAX 0.6.99)",
    "dashboard-layout.lua": "recruitment card hidden (module off)",
    "recruiting-layout.lua": "recruitment module off by default",
    "roster-table.lua": "Trials is off (it belongs to recruitment)",
    "lfg-board.lua": "group lines in guild chat start off (decision 7)",
    "addon-reminder.lua": "whisper to a non-member is blocked",
    "site-night.lua": "whisper to a non-member is blocked",
    "whisper-not-found.lua": "whisper to a non-member is blocked",
    "whisper-queue.lua": "whisper to a non-member is blocked",
}

# Checks of the tools that act for the player (decision 7): hidden in the CurseForge pack, shown with the
# AmazingHubDev addon. Each must fail without it (the gate holds) and pass with it (the tool still works).
DEV_ONLY = {"discipline.lua", "groups-panel.lua", "groups.lua", "guild-bank-panel.lua", "guild-bank.lua",
            "mod-alerts-ui.lua", "mod-alerts.lua", "mod-away.lua", "mod-flood.lua", "newcomer.lua"}


def _luajit():
    return pytest.importorskip("lupa.luajit21")


def _run_lua(lj, path: Path, addon: Path, dev: bool = False) -> str:
    L = lj.LuaRuntime(unpack_returned_tuples=True)
    if dev:
        L.execute("AmazingHubDevFeatures = true")  # what addon/AmazingHubDev sets
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
    assert toc.rstrip().endswith(
        "UI\\PackMigrate.lua\nUI\\PackTweaks.lua\nUI\\TableSort.lua\nUI\\ChatTag.lua\nUI\\WishImport.lua\nUI\\LedgerPanel.lua\nUI\\SettingsPlus.lua\nData\\ItemCatalog.lua\nUI\\ItemCatalog.lua")
    for name in ("PackMigrate.lua", "PackTweaks.lua", "TableSort.lua", "ChatTag.lua", "WishImport.lua", "LedgerPanel.lua", "SettingsPlus.lua",
                 "ItemCatalog.lua"):
        assert (HUB / "UI" / name).read_bytes() == (ROOT / "addon" / "hub-extra" / name).read_bytes()


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
        name = os.path.basename(f)
        res = _run_lua(lj, Path(f), Path("."))
        if name in DEV_ONLY:
            assert res != "ok", f"{name} passes without the developer addon: its gate is gone"
            res = _run_lua(lj, Path(f), Path("."), dev=True)
        if res == "ok":
            passed += 1
        else:
            failed[name] = res
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
    assert "## OptionalDeps: GuildLedger, AmazingHubDev\n" in toc
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
    # line endings do not count: a Windows checkout may turn LF into CRLF in either copy
    norm = lambda b: b.replace(b"\r\n", b"\n")  # noqa: E731
    built = {p.relative_to(out).as_posix(): norm(p.read_bytes()) for p in out.rglob("*") if p.is_file()}
    have = {p.relative_to(HUB).as_posix(): norm(p.read_bytes()) for p in HUB.rglob("*") if p.is_file()}
    assert built.keys() == have.keys()
    assert [k for k in built if built[k] != have[k]] == []


def test_classic_style_is_the_default():
    style = (HUB / "Core" / "Style.lua").read_text("utf-8")
    assert 'Style.DEFAULT = "forever"' in style and 'Style.ORDER = { "forever", "amazinghub" }' in style
    assert 'name = "Classic"' in style and 'name = "Modern"' in style
    assert 'Style.ALIASES = { classic = "forever", modern = "amazinghub" }' in style


def test_table_sort_flips_and_keeps_the_table_order_until_a_heading_is_clicked():
    lj = _luajit()
    lua = lj.LuaRuntime()
    lua.execute("""
        local settings = {}
        AmazingHub = { GetSetting = function(_, k) return settings[k] end, SetSetting = function(_, k, v) settings[k] = v end }
        function CreateFrame()
            return { SetAllPoints = function() end, SetScript = function(self, _, fn) self.click = fn end }
        end
    """)
    lua.execute((HUB / "UI" / "TableSort.lua").read_text("utf-8"))
    out = lua.eval("""(function()
        local T = AmazingHub.TableSort
        local function names(l) local o = {} for i, r in ipairs(l) do o[i] = r.name end return table.concat(o, ",") end
        local function rows() return { { name = "Cora", current = 5 }, { name = "alia", current = 50 },
            { name = "Bram" }, { name = "Dax", current = 50 } } end
        local res = {}
        res[#res + 1] = names(T.Apply("dkp", rows(), T.POINTS))           -- nothing chosen: as given
        local fs = { text = "", GetParent = function() return {} end, SetText = function(self, t) self.text = t end }
        local redraws = 0
        T.Header(fs, "dkp", "current", "CURRENT", function() redraws = redraws + 1 end, true)
        fs.amzSortButton.click()
        res[#res + 1] = names(T.Apply("dkp", rows(), T.POINTS))           -- largest first, empty last, ties stable
        fs.amzSortButton.click()
        res[#res + 1] = names(T.Apply("dkp", rows(), T.POINTS))           -- flipped
        T.Toggle("dkp", "name")
        res[#res + 1] = names(T.Apply("dkp", rows(), T.POINTS))           -- text, case-insensitive
        T.Header(fs, "dkp", "name", "MEMBER", function() end)
        res[#res + 1] = tostring(redraws) .. "|" .. fs.text
        return table.concat(res, " ; ")
    end)()""")
    assert out.split(" ; ") == [
        "Cora,alia,Bram,Dax",
        "alia,Dax,Cora,Bram",
        "Cora,alia,Dax,Bram",
        "alia,Bram,Cora,Dax",
        "2|MEMBER |TInterface\\BUTTONS\\Arrow-Up-Up:12:12|t",
    ]


def test_wishlist_import_takes_the_bots_export_line():
    sys.path[:0] = [str(ROOT / "bot"), str(ROOT / "companion")]
    import sqlite3

    from guildledger_bot.collection.loot import wish_export
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE wishes (guild TEXT, member TEXT, name TEXT, item_id INT, offspec INT, added_at INT)")
    for i, (item, os_) in enumerate([(19019, 0), (17076, 1), (19019, 0)]):
        db.execute("INSERT INTO wishes VALUES ('G', 'testa collector', 'Testa Collector', ?, ?, ?)", (item, os_, i))
    line = wish_export(db, "G", "Testa Collector")
    assert line == "GLW1:Testa Collector:19019,17076o,19019"

    lua = _luajit().LuaRuntime()
    lua.execute("""
        added, prints, later = {}, {}, {}
        local mine = { { itemId = 18832 } }
        AmazingHub = { UI = {}, Colors = {}, Print = function(_, m) prints[#prints + 1] = m end,
            Compat = { PlayerName = function() return "Testa Collector" end },
            Wishlist = {
                GetMyList = function() return mine end,
                ItemFacts = function(_, id) if id ~= 17076 or #later > 0 then return "Item " .. id, "|Hitem:" .. id .. "|h" end end,
                AddToWishlist = function(_, id, link, os) added[#added + 1] = id .. (os and "o" or "") .. "=" .. link
                    mine[#mine + 1] = { itemId = id } end } }
        C_Timer = { After = function(_, fn) later[#later + 1] = fn end }
    """)
    lua.execute((HUB / "UI" / "WishImport.lua").read_text("utf-8"))
    g = lua.globals()
    ok, msg = g.AmazingHub.WishImport.Import(line)
    assert ok is True and "1 new, 0 already" in msg and "rest follows" in msg  # 17076 not cached yet
    lua.execute("later[1]()")  # the game knows it now
    assert list(g.added.values()) == ["19019=|Hitem:19019|h", "17076o=|Hitem:17076|h"]
    ok, msg = g.AmazingHub.WishImport.Import("GLW1:Someone Else:19019")
    assert ok is False and "Someone Else" in msg
    ok, msg = g.AmazingHub.WishImport.Import("GLW1:Testa Collector:12x")
    assert ok is False and "damaged" in msg
    ok, msg = g.AmazingHub.WishImport.Import("GLW1:Testa-Collector:18832, 19019")  # hyphenated name, spaces
    assert ok is True and "0 new, 2 already" in msg


def test_own_chat_tag_replaces_the_alt_tag_for_everyone_who_reads_it():
    lua = _luajit().LuaRuntime()
    lua.execute("""
        local settings = {}
        sent = 0
        AmazingHub = { UI = {}, Colors = {},
            GetSetting = function(_, k) return settings[k] end, SetSetting = function(_, k, v) settings[k] = v end,
            GetPlayerKey = function(_, n) return n end,
            Compat = { PlayerName = function() return "Testa Collector" end },
            CommSystem = { BroadcastMyData = function(_, force) if force then sent = sent + 1 end end },
            db = { members = { ["Sha Rer"] = { chatTag = "|cffff0000Da|Hitem:1|h(mti)|h", chatTagOff = false },
                               ["Old Hub"] = { name = "Old Hub" },
                               ["Quiet One"] = { chatTag = "Q", chatTagOff = true } } } }
    """)
    lua.execute((HUB / "UI" / "ChatTag.lua").read_text("utf-8"))
    lua.execute((HUB / "Modules" / "ChatTweaks.lua").read_text("utf-8"))
    T = lua.globals().AmazingHub.ChatTag
    assert T.Clean("  [Floy]  ") == "Floy"
    assert T.Clean("ÄÖÜäöüßéèàçñ€abcdef") == "ÄÖÜäöüßéèàçñ€abc"  # 16 characters, no cut inside a letter
    assert T.Clean("|cffff0000Da|Hitem:1|h(mti)|h") == "cffff0000Da Hite"  # 16 characters
    assert T.For("Testa Collector") is None  # nothing chosen: the usual alt tag
    assert T.Set("Floy", False) is True and lua.eval("sent") == 1
    assert T.Set("Floy", False) is False and lua.eval("sent") == 1  # unchanged: nothing sent
    assert T.For("Testa Collector") == "Floy"
    assert "|" not in T.For("Sha Rer")
    assert T.For("Old Hub") is None and T.For("Quiet One") is False and T.For("Nobody") is None
    out = lua.eval("""(function()
        local CT = AmazingHub.ChatTweaks
        local long = { level = true, altTag = true }
        local short = { level = true, altTag = true, altShort = true }
        local alt = { level = 11, altTag = "alt of Floyd Mainchar", shortTag = "[Floyd Mainchar]" }
        local function with(own) local i = {} for k, v in pairs(alt) do i[k] = v end i.own = own return i end
        return table.concat({ CT:_BuildPrefix(with("Floy"), long), CT:_BuildPrefix(with("Floy"), short),
            CT:_BuildPrefix(with(false), long), CT:_BuildPrefix(with(nil), long),
            CT:_BuildPrefix(with("Floy"), { level = true, altTag = false }) }, " ; ")
    end)()""")
    assert out.split(" ; ") == [
        "[11] |cff888888(Floy)|r", "[11] |cff888888[Floy]|r", "[11]",
        "[11] |cff888888(alt of Floyd Mainchar)|r", "[11]",
    ]


def test_rank_arrows_only_below_your_own_rank():
    lua = _luajit().LuaRuntime()
    lua.execute("""
        AmazingHub = { db = {}, L = setmetatable({}, { __index = function(_, k) return k end }) }
        myRank = 2
        function GetGuildInfo() return "G", "Officer", myRank end
        function GuildControlGetNumRanks() return 6 end
    """)
    lua.execute((HUB / "Modules" / "GuildManager.lua").read_text("utf-8"))
    out = lua.eval("""(function()
        local GM, o = AmazingHub.GuildManager, {}
        for r = 0, 5 do o[#o + 1] = r .. (GM:MayPromote(r) and "P" or "") .. (GM:MayDemote(r) and "D" or "") end
        myRank = nil
        o[#o + 1] = tostring(GM:MayPromote(4)) .. tostring(GM:MayDemote(4))
        return table.concat(o, " ")
    end)()""")
    # rank 2 (you) may move 3 down, 4 and 5 up; 3 cannot go up to your rank; 5 is the lowest: no demote
    assert out == "0 1 2 3D 4PD 5P falsefalse"


def test_saved_data_without_realm_is_copied_to_the_realm_key_once():
    """0.6 saved under "<guild>-" since Forever's 21/11 patch; 0.7 opens "<guild>-<realm>" (HUB_AUDIT 10.5)."""
    lua = _luajit().LuaRuntime()
    lua.execute("""
        AmazingHub = {}
        function time() return 1790000000 end
        AmazingHubDB = {
          ["Amazing-"] = { settings = { uiScale = 1.1, newOnly = true },
            members = { ["Testa Wanderer"] = { level = 25, note = "new" }, ["Neu Ling"] = { level = 3 } },
            lootHistory = { { item = 1, who = "Testa Wanderer", t = 5 }, { item = 2, who = "Neu Ling", t = 9 } } },
          ["Amazing-Realm"] = { settings = { uiScale = 1.0, oldOnly = true },
            members = { ["Testa Wanderer-Realm"] = { level = 20, class = "MAGE" } },
            lootHistory = { { t = 5, who = "Testa Wanderer", item = 1 } } },
          ["Other-"] = { settings = { uiScale = 0.9 } },
        }
    """)
    lua.execute((HUB / "UI" / "PackMigrate.lua").read_text("utf-8"))
    out = lua.eval("""(function()
        local M, db = AmazingHub.PackMigrate, AmazingHubDB
        local r = { M:MergeRealmless("Amazing-Realm", "Realm") }
        local g = db["Amazing-Realm"]
        local w = g.members["Testa Wanderer-Realm"]
        r[#r + 1] = table.concat({ g.settings.uiScale, tostring(g.settings.oldOnly), tostring(g.settings.newOnly) }, ",")
        r[#r + 1] = table.concat({ w.level, w.class, w.note, tostring(g.members["Neu Ling-Realm"] ~= nil),
            tostring(g.members["Testa Wanderer"] == nil) }, ",")
        r[#r + 1] = tostring(#g.lootHistory) .. "," .. g.lootHistory[2].item
        r[#r + 1] = tostring(db["Amazing-"] ~= nil) .. "," .. tostring(db._packRealmMerged["Amazing-"])
        g.settings.uiScale = 1.2
        r[#r + 1] = M:MergeRealmless("Amazing-Realm", "Realm") .. "," .. g.settings.uiScale
        r[#r + 1] = M:MergeRealmless("Other-Realm", "Realm") .. "," .. db["Other-Realm"].settings.uiScale
        r[#r + 1] = M:MergeRealmless("Amazing-", "") .. "," .. M:MergeRealmless("Nobody-Realm", "Realm")
        return table.concat(r, " ; ")
    end)()""")
    assert out.split(" ; ") == [
        "merged",
        "1.1,true,true",            # both have it: the realmless (newer) value wins; nothing is lost
        "25,MAGE,new,true,true",    # member keys get the realm; fields merge
        "2,2",                      # the list gets only the entry it lacked (same entry, other key order)
        "true,1790000000",          # nothing deleted; done once
        "done before,1.2",          # a second login changes nothing
        "copied,0.9",               # no realm key yet: a copy
        "none,none",                # no realm known; nothing saved without the realm
    ]


def test_developer_addon_is_linked_locally_but_never_packed():
    dev = ROOT / "addon" / "AmazingHubDev"
    assert (dev / "AmazingHubDev.toc").is_file() and "AmazingHubDevFeatures = true" in (dev / "Dev.lua").read_text("utf-8")
    pack = (ROOT / "tools" / "package-collector.ps1").read_text("utf-8")
    assert "AmazingHubDev" not in pack and 'Join-Path $root "addon\\AmazingHub")' in pack
    assert "Get-ChildItem -Path $repoAddons -Directory" in (ROOT / "tools" / "install.ps1").read_text("utf-8")
    gated = [f for f in HUB.rglob("*.lua") if not f.relative_to(HUB).as_posix().startswith("tools/")
             and "AmazingHubDevFeatures" in f.read_text("utf-8")]
    assert len(gated) >= 12, [g.name for g in gated]


def test_item_catalogue_reaches_the_wishlist_on_forever_only():
    data = (ROOT / "addon" / "hub-extra" / "Data" / "ItemCatalog.lua").read_text("utf-8")
    assert (HUB / "Data" / "ItemCatalog.lua").read_text("utf-8") == data
    for game, want in (("FOREVER", True), ("RETAIL", False)):
        lua = _luajit().LuaRuntime()
        lua.execute(f'AmazingHub = {{ Wishlist = {{ catalog = {{ [19019] = {{ name = "from the journal" }} }} }},'
                    f' Client = {{ game = "{game}" }} }}')
        lua.execute(data)
        lua.execute((HUB / "UI" / "ItemCatalog.lua").read_text("utf-8"))
        g = lua.globals()
        assert g.AmazingHubItemCatalog is None
        n = g.AmazingHub.Wishlist.catalogCount
        assert (n is not None and n > 4000) is want, (game, n)
        assert g.AmazingHub.Wishlist.catalog[19019].name == "from the journal"  # never overwritten

