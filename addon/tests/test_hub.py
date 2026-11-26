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
        "UI\\PackMigrate.lua\nUI\\PackTweaks.lua\nUI\\TableSort.lua\nUI\\ChatTag.lua\nUI\\WishImport.lua\nUI\\LedgerPanel.lua\nUI\\SettingsPlus.lua\nUI\\Windows.lua\nUI\\Links.lua\nUI\\ClearBox.lua\nUI\\Materials.lua\nUI\\Joined.lua\nUI\\SearchBox.lua\nUI\\OrderWhisper.lua\nData\\ItemCatalog.lua\nUI\\ItemCatalog.lua")
    for name in ("PackMigrate.lua", "PackTweaks.lua", "TableSort.lua", "ChatTag.lua", "WishImport.lua", "LedgerPanel.lua", "SettingsPlus.lua", "Windows.lua", "Links.lua", "ClearBox.lua", "Materials.lua", "Joined.lua", "SearchBox.lua", "OrderWhisper.lua",
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


def test_whispers_reach_guild_members_by_their_whisper_name_only():
    """U3 (2026-11-24): every whisper was dropped, because Forever whispers "First-Surname" for "First Surname"."""
    src = (HUB / "Core" / "Compat.lua").read_text("utf-8")
    start = src.index("local GUILD_ONLY")
    end = src.index("-- Stands in for the global SendChatMessage")
    lua = _luajit().LuaRuntime()
    lua.execute("""
        Compat = { IsSecret = function() return false end }
        AmazingHub = { IsGuildmate = function() return false end,
                       GetPlayerKey = function(_, n) return n .. "-Realm" end }
        ROSTER = { "Floyd Mainchar", "Neu", "Other-Elsewhere" }
        function GetTime() return 100 end
        function GetRealmName() return "Realm" end
        function GetNumGuildMembers() return #ROSTER end
        function GetGuildRosterInfo(i) return ROSTER[i] end
    """)
    lua.execute(src[start:end])
    ok = lua.eval("function(n) return Compat.AllowedOutbound('WHISPER', n) end")
    for name in ("Floyd-Mainchar", "Floyd Mainchar", "floyd-mainchar", "Neu", "Neu-Realm", "Other-Elsewhere",
                 "Floyd Mainchar-Realm"):
        assert ok(name) is True, name
    for name in ("Floyd", "Mainchar", "Stranger", "Neu-Elsewhere", "", None):
        assert ok(name) is False, name
    assert lua.eval("Compat.AllowedOutbound('SAY', 'Neu')") is False
    assert lua.eval("Compat.AllowedOutbound('GUILD')") is True



def test_alt_question_is_asked_once_and_remembered():
    """H8 (PLAN_COMMUNITY W18): upstream's fix, checked across logins: Not now and Link both stop the question."""
    lj = _luajit()
    assert _run_lua(lj, Path(__file__).with_name("hub_alts.lua"), HUB) == "ok"


def _frame_lua():
    return """
        local function frame(shown)
            local f = { shown = shown, raised = 0, top = false, hooks = {} }
            function f:SetToplevel(v) self.top = v end
            function f:Raise() self.raised = self.raised + 1 end
            function f:IsShown() return self.shown end
            function f:Show() self.shown = true; for _, h in ipairs(self.hooks) do h(self) end end
            function f:Hide() self.shown = false end
            function f:SetShown(v) if v then self:Show() else self:Hide() end end
            function f:HookScript(_, h) self.hooks[#self.hooks + 1] = h end
            return f
        end
        NEW_FRAME = frame
    """


def test_hub_windows_come_to_the_front_and_reopen_whole():
    """H1 (W11) and H5 (W15): hub-extra/Windows.lua."""
    lua = _luajit().LuaRuntime()
    lua.execute(_frame_lua())
    lua.execute("""
        clicks, timers = nil, {}
        function CreateFrame() return { SetScript = function(_, _, fn) clicks = fn end } end
        AmazingHub = { db = { settings = { window = { collapsed = true } } },
            Compat = { RegisterEvent = function() end, After = function(_, fn) timers[#timers + 1] = fn end } }
        main = NEW_FRAME(false); main.band = "bar"; main.folds = 0
        function main:ToggleCollapsed() self.folds = self.folds + 1; AmazingHub.db.settings.window.collapsed = nil end
        AmazingHub.UI = {
            StylePopup = function(_, f) f.styled = true; return f end,
            GetMainWindow = function() AmazingHub.RosterFrame = main; return main end,
            ToggleMain = function(self) local f = self:GetMainWindow(); f:SetShown(not f:IsShown()) end,
        }
    """)
    lua.execute((HUB / "UI" / "Windows.lua").read_text("utf-8"))
    out = lua.eval("""(function()
        local UI, r = AmazingHub.UI, {}
        local p = NEW_FRAME(true)
        UI:StylePopup(p)
        r[#r + 1] = tostring(p.styled and p.top and p.raised == 1)      -- a styled popup: top-level, in front
        p:Hide(); p:Show()
        r[#r + 1] = tostring(p.raised == 2)                              -- in front again when shown
        UI:ToggleMain()
        r[#r + 1] = tostring(main.shown and main.folds == 1 and main.top) -- closed folded: opens whole
        UI:ToggleMain(); main.band = "full"; UI:ToggleMain()
        r[#r + 1] = tostring(main.folds == 1)                            -- not folded: left as it is
        AmazingHubWishlistFrame = NEW_FRAME(true)                        -- made later by a click
        clicks(); for _, fn in ipairs(timers) do fn() end
        r[#r + 1] = tostring(AmazingHubWishlistFrame.top and AmazingHubWishlistFrame.raised == 1)
        clicks(); for _, fn in ipairs(timers) do fn() end
        r[#r + 1] = tostring(AmazingHubWishlistFrame.raised == 1)        -- hooked once only
        return table.concat(r, ",")
    end)()""")
    assert out == "true,true,true,true,true,true"


def test_chat_annotation_defaults_apply_once():
    """H6 (W16): annotate on, class icon off, level on, alt tag on, once; the player's later choice stays."""
    lua = _luajit().LuaRuntime()
    lua.execute("""
        AmazingHub = { UI = { GetFeature = function() end }, db = { settings = {}, chatTweaks = { classIcon = true } } }
        started = 0
        AmazingHub.ChatTweaks = { Initialize = function() started = started + 1 end }
    """)
    lua.execute((HUB / "UI" / "PackTweaks.lua").read_text("utf-8"))
    out = lua.eval("""(function()
        local db, r = AmazingHub.db, {}
        AmazingHub.ChatTweaks:Initialize()
        local c = db.chatTweaks
        r[#r + 1] = table.concat({ tostring(c.enabled), tostring(c.classIcon), tostring(c.level), tostring(c.altTag),
            tostring(db.settings.packChatDefaults), started }, " ")
        c.enabled, c.level = false, false
        AmazingHub.ChatTweaks:Initialize()
        r[#r + 1] = tostring(c.enabled) .. " " .. tostring(c.level) .. " " .. started
        return table.concat(r, ";")
    end)()""")
    assert out == "true false true true 1 1;false false 2"


def test_shift_click_links_the_tooltip_item_once():
    """H7 (W17): hub-extra/Links.lua links what the tooltip shows unless the row linked it itself."""
    lua = _luajit().LuaRuntime()
    lua.execute("""
        T, linked, mouse = 10, {}, true
        function GetTime() return T end
        hooks = {}
        function hooksecurefunc(name, fn) hooks[name] = fn end
        function HandleModifiedItemClick(l) linked[#linked + 1] = l; if hooks.HandleModifiedItemClick then hooks.HandleModifiedItemClick(l) end end
        tip = "|cff1eff00|Hitem:2589::::::::|h[Linen Cloth]|h|r"
        GameTooltip = { IsShown = function() return tip ~= nil end }
        AmazingHub = { Compat = { TooltipItem = function() return "Linen Cloth", tip end } }
        AmazingHub.RosterFrame = { IsShown = function() return true end, IsMouseOver = function() return mouse end }
    """)
    lua.execute((HUB / "UI" / "Links.lua").read_text("utf-8"))
    out = lua.eval("""(function()
        local L, r = AmazingHub.PackLinks, {}
        r[#r + 1] = tostring(L.AfterClick(10))                -- a row with only a tooltip: linked
        HandleModifiedItemClick("row's own")                  -- a row that links itself, same click
        r[#r + 1] = tostring(L.AfterClick(10))                -- not linked twice
        T = 11; mouse = false
        r[#r + 1] = tostring(L.AfterClick(11))                -- not over a hub window
        mouse = true; tip = "|Hspell:123|h[Enchant]|h"
        r[#r + 1] = tostring(L.AfterClick(11))                -- a spell is not an item
        return table.concat(r, ",") .. ";" .. #linked
    end)()""")
    assert out == "true,false,false,false;2"


def test_search_fields_get_a_clear_button():
    """H3 (W13): hub-extra/ClearBox.lua."""
    lua = _luajit().LuaRuntime()
    lua.execute("""
        local function widget()
            local w = { shown = true, hooks = {}, scripts = {} }
            function w:SetSize() end
            function w:SetPoint() end
            function w:SetShown(v) self.shown = v end
            function w:SetScript(k, fn) self.scripts[k] = fn end
            function w:HookScript(k, fn) self.hooks[k] = self.hooks[k] or {}; table.insert(self.hooks[k], fn) end
            return w
        end
        function CreateFrame() return widget() end
        local function input()
            local b = widget()
            b.text = ""
            function b:GetText() return self.text end
            function b:SetText(t) self.text = t; for _, fn in ipairs(self.hooks.OnTextChanged or {}) do fn(self) end end
            function b:ClearFocus() end
            function b:SetTextInsets() end
            return b
        end
        AmazingHub = { UI = {
            CreateText = function() return { SetPoint = function() end } end,
            CreateInput = function() return input() end,
        } }
        function AmazingHub:CreateRosterPanel(parent, host)
            host.searchBox = AmazingHub.UI:CreateInput(parent, 160, 22, { placeholder = "Search" })
            host.segment, host.classFilter, host.refreshed = "all", nil, 0
            function host:UpdateRailActive() end
            function host:SetSegment(id) self.segment = id; self:UpdateRailActive() end
            host.searchBox:HookScript("OnTextChanged", function(b) host.searchFilter = b:GetText() end)
        end
    """)
    lua.execute((HUB / "UI" / "ClearBox.lua").read_text("utf-8"))
    out = lua.eval("""(function()
        local UI, r = AmazingHub.UI, {}
        local plain = UI:CreateInput(nil, 100, 22, { placeholder = "Search recipes" })
        local note = UI:CreateInput(nil, 100, 22, { multiline = true, placeholder = "Note" })
        local amount = UI:CreateInput(nil, 100, 22, { numeric = true, placeholder = "0" })
        r[#r + 1] = tostring(plain.packClear ~= nil and note.packClear == nil and amount.packClear == nil)
        r[#r + 1] = tostring(plain.packClear.shown)                 -- empty: no x
        plain:SetText("linen")
        r[#r + 1] = tostring(plain.packClear.shown)                 -- text: x
        plain.packClear.scripts.OnClick()
        r[#r + 1] = tostring(plain:GetText() == "" and not plain.packClear.shown)
        return table.concat(r, ",")
    end)()""")
    assert out == "true,false,true,true"


def test_recipe_materials_show_the_guild_bank_count():
    """H9 (W19): hub-extra/Materials.lua."""
    lua = _luajit().LuaRuntime()
    lua.execute("""
        local function fs() return { t = "", SetText = function(s, t) s.t = t end, GetText = function(s) return s.t end } end
        seen = 0
        AmazingHub = {
            GuildBank = { Newest = function() return seen end,
                          CountOf = function(_, id) return ({ [2589] = 40 })[id] or 0 end },
            CraftOrders = { Reagents = function() return { { itemID = 2589, count = 2 }, { itemID = 2320, count = 1 } } end },
        }
        function AmazingHub:CreateCraftDetail()
            local d = { mats = { { name = fs() }, { name = fs() } } }
            function d:Paint() self.mats[1].name:SetText("Linen Cloth"); self.mats[2].name:SetText("Coarse Thread") end
            return d
        end
    """)
    lua.execute((HUB / "UI" / "Materials.lua").read_text("utf-8"))
    out = lua.eval("""(function()
        local d = AmazingHub:CreateCraftDetail()
        d.recipe = { item = 2580 }
        d:Paint()
        local before = d.mats[1].name.t
        seen = 1790000000
        d:Paint()
        return before .. "#" .. d.mats[1].name.t .. "#" .. d.mats[2].name.t
    end)()""")
    before, linen, thread = out.split("#", 2)
    assert before == "Linen Cloth"                       # never saw the bank: nothing added
    assert linen.startswith("Linen Cloth") and "bank 40" in linen
    assert thread == "Coarse Thread"                     # the bank holds none


def test_join_dates_from_guildledger_fill_the_member_history_read_only():
    """H10 (W21): hub-extra/Joined.lua."""
    lua = _luajit().LuaRuntime()
    lua.execute("""
        H = {
          ["Seen-Realm"]   = { stints = { { joinAt = 5000, joinEst = true } } },
          ["Exact-Realm"]  = { stints = { { joinAt = 5000 } } },
          ["Noted-Realm"]  = { stints = { { joinAt = 5000, joinEst = true, joinSrc = "note" } } },
          ["Gone-Realm"]   = { stints = { { joinAt = 5000, leftAt = 6000 } } },
          ["Back-Realm"]   = { stints = { { joinAt = 1000, leftAt = 3000 }, { joinAt = 5000, joinEst = true } } },
        }
        AmazingHub = { MemberHistory = {}, IsGuildmate = function(_, k) return k == "New-Realm" end }
        local MH = AmazingHub.MemberHistory
        function MH:Stints(key) return H[key] and H[key].stints or {} end
        function MH:JoinedAt(key)
            local s = self:Stints(key); local last = s[#s]
            if last and last.leftAt == nil and last.joinAt then return last.joinAt, last.joinEst == true end
        end
        LEDGER = { Seen = 4000, Exact = 4000, Noted = 4000, Gone = 4000, Back = 2000, New = 4000, Stranger = 4000 }
        GuildLedgerAPI = { GetJoined = function(n) return LEDGER[n] and { t = LEDGER[n], estimated = true } end }
    """)
    lua.execute((HUB / "UI" / "Joined.lua").read_text("utf-8"))
    out = lua.eval("""(function()
        local MH, r = AmazingHub.MemberHistory, {}
        for _, k in ipairs({ "Seen", "Exact", "Noted", "Gone", "Back", "New", "Stranger" }) do
            local t, est = MH:JoinedAt(k .. "-Realm")
            r[#r + 1] = k .. "=" .. tostring(t) .. ":" .. tostring(est)
        end
        LEDGER.Seen = 6000
        local t = MH:JoinedAt("Seen-Realm"); r[#r + 1] = "later=" .. tostring(t)
        return table.concat(r, " ") .. " " .. tostring(H["Seen-Realm"].stints[1].joinAt)
    end)()""")
    assert out.split() == [
        "Seen=4000:true",       # only seen by a hub: GuildLedger's earlier date, estimated
        "Exact=5000:false",     # the game's own line stays
        "Noted=5000:true",      # a day from the note stays
        "Gone=nil:nil",         # not a member now
        "Back=5000:true",       # GuildLedger's date lies in the earlier stay: ignored
        "New=4000:true",        # no history yet, in the roster now
        "Stranger=nil:nil",     # not in the roster
        "later=5000",           # a later date changes nothing
        "5000",                 # nothing written into the history
    ]


def test_title_bar_search_groups_its_results():
    """H2 (W12): hub-extra/SearchBox.lua's query, and the Settings index it reads (SettingsPlus)."""
    lua = _luajit().LuaRuntime()
    lua.execute("""
        opened = {}
        AmazingHub = {
            L = setmetatable({}, { __index = function(_, k) return k end }),
            UI = { featureOrder = { "roster", "bank", "settings", "dkp" },
                   features = { roster = { id = "roster", label = "Roster", tab = true },
                                bank = { id = "bank", label = "Bank", tab = true },
                                settings = { id = "settings", label = "Settings", tab = true },
                                dkp = { id = "dkp", label = "DKP", tab = false } },
                   OpenWindow = function(_, id, sub) opened[#opened + 1] = id .. ":" .. tostring(sub); return true end },
            IsFeatureEnabled = function() return true end,
            Search = { Query = function(_, q) return { members = q:find("^lin") and { { name = "Linnea", class = "MAGE", level = 30, online = true } } or {} } end },
            ProfDirectory = { RecipeRows = function(_, _, q)
                local out = {}
                for _, r in ipairs({ { id = 1, name = "Linen Bandage", out = 1251, crafters = {} },
                                     { id = 2, name = "Linen Cloak", out = 2570, crafters = { "a" } } }) do
                    if r.name:lower():find(q, 1, true) then out[#out + 1] = r end
                end
                return out
            end },
            Wishlist = { catalog = { [2589] = { name = "Linen Cloth" }, [4306] = { name = "Silk Cloth" } } },
            GuildBank = { Index = function() return { list = { { id = 2589, total = 40 } } } end,
                          ItemInfo = function() return {} end, CountOf = function(_, id) return id == 2589 and 40 or 0 end },
            SettingsPlus = { Index = function() return {
                { page = "chat", pageLabel = "Settings", label = "Chat" },
                { page = "interface", pageLabel = "Settings > Interface", label = "Online members first, whatever column is sorted",
                  section = "Member list" } } end, Reveal = function(e) opened[#opened + 1] = "reveal:" .. e.page end },
            Compat = {},
            SafeCall = function(_, fn, ...) return fn(...) end,
        }
        for i = 1, 20 do AmazingHub.Wishlist.catalog[10000 + i] = { name = "Linen Thing " .. i } end
    """)
    lua.execute((HUB / "UI" / "SearchBox.lua").read_text("utf-8"))
    out = lua.eval("""(function()
        local S, r = AmazingHub.PackSearch, {}
        r[#r + 1] = tostring(#S.Query("l"))                    -- one letter: nothing
        local g = S.Query("Lin")
        for _, x in ipairs(g) do r[#r + 1] = x.key .. "=" .. #x.rows end
        r[#r + 1] = g[2].rows[1].text:sub(1, 11)               -- a recipe the guild knows first
        r[#r + 1] = g[3].rows[1].text                          -- an item whose name starts with it first
        g[4].rows[1].go(); g[2].rows[1].go = g[2].rows[1].go
        local t = S.Query("bank")
        r[#r + 1] = t[#t].key .. ":" .. t[#t].rows[1].text     -- a tab
        local s = S.Query("online members")
        s[1].rows[1].go()
        r[#r + 1] = s[1].key
        return table.concat(r, ",") .. ";" .. table.concat(opened, ",")
    end)()""")
    head, opened = out.split(";")
    assert head.split(",") == ["0", "members=1", "recipes=2", "items=8", "bank=1", "settings=1", "Linen Cloak",
                               "Linen Cloth", "tabs:Bank", "settings"]
    assert opened == "bank:nil,reveal:interface"



def test_whisper_box_drops_the_realm_of_a_member_key_on_forever():
    """U3c (2026-11-26): an order's Whisper opened "/w First-Surname-Realm"."""
    src = (HUB / "Core" / "Utils.lua").read_text("utf-8")
    start = src.index("function AmazingHub:WhisperTarget")
    end = src.index("\nend\n", src.index("function AmazingHub:OpenWhisper")) + 5
    lua = _luajit().LuaRuntime()
    lua.execute("opened = {}; function ChatFrame_OpenChat(t) opened[#opened + 1] = t end;"
                " AmazingHub = { Client = { has = { surnames = true } } }")
    lua.execute(src[start:end])
    lua.execute('AmazingHub:OpenWhisper("Floyd Mainchar-OtherRealm"); AmazingHub:OpenWhisper("Neu", "hi");'
                ' AmazingHub.Client.has.surnames = false; AmazingHub:OpenWhisper("Bob-Realm")')
    assert list(lua.eval("opened").values()) == ["/w Floyd-Mainchar ", "/w Neu hi", "/w Bob-Realm "]


def test_order_to_one_crafter_whispers_them_and_to_anyone_does_not():
    """Round H-b (2026-11-26): hub-extra/OrderWhisper.lua."""
    lua = _luajit().LuaRuntime()
    lua.execute("""
        sent = {}
        AmazingHub = {
            Client = { has = { surnames = true } },
            Compat = { GetItemInfo = function(id) return "Cloak", "|Hitem:" .. id .. "|h[Linen Cloak]|h" end,
                       SendWhisper = function(text, target) sent[#sent + 1] = target .. "=" .. text; return true end },
            CraftOrders = { NameOf = function(k) return k end,
                            Place = function(_, item, opts) return { item = item, n = opts.n, to = opts.to } end },
        }
        function AmazingHub:WhisperTarget(n) return (n:gsub(" ", "-")) end
    """)
    lua.execute((HUB / "UI" / "OrderWhisper.lua").read_text("utf-8"))
    lua.execute('AmazingHub.CraftOrders:Place(2570, { n = 2, to = "Floyd Mainchar-Realm" })'
                '; AmazingHub.CraftOrders:Place(2570, { n = 1 })')
    sent = list(lua.eval("sent").values())
    assert len(sent) == 1
    assert sent[0].startswith("Floyd-Mainchar=[Amazing Hub] I sent you a craft order: ")
    assert "[Linen Cloak]" in sent[0] and " x2." in sent[0]


def test_opened_recipe_lists_its_recipe_and_what_teaches_it():
    """Round H-b: hub-extra/Materials.lua's two link lines."""
    lua = _luajit().LuaRuntime()
    lua.execute("""
        AmazingHub = {
            PackLinks = { RecipeLink = function(id) return "|Hspell:" .. id .. "|h[Tailoring: Linen Cloak]|h" end },
            Compat = { GetItemInfo = function(id) if id == 6270 then return "P", "|Hitem:6270|h[Pattern: Linen Cloak]|h" end end },
            Wishlist = { catalog = { [7000] = { name = "Plans: Copper Bracers" } } },
        }
    """)
    lua.execute((HUB / "UI" / "Materials.lua").read_text("utf-8"))
    out = lua.eval("""(function()
        local M, r = AmazingHub.PackMaterials, {}
        for _, rec in ipairs({ { recipeId = 2387, recipeItem = 6270 }, { recipeId = 2662, recipeItem = 7000 }, { recipeId = 7418 } }) do
            local parts = {}
            for _, e in ipairs(M.RecipeLines(rec)) do parts[#parts + 1] = e.label .. (e.text or e.link) .. (e.link and "*" or "") end
            r[#r + 1] = table.concat(parts, " / ")
        end
        return table.concat(r, " # ")
    end)()""")
    a, b, c = out.split(" # ")
    assert "Recipe: " in a and "[Tailoring: Linen Cloak]" in a and "Learned from: |Hitem:6270|h[Pattern: Linen Cloak]|h*" in a
    assert "Learned from: Plans: Copper Bracers" in b and not b.endswith("Bracers*")   # not cached: name, no link yet
    assert "Learned from" not in c                                                       # trainer recipe: nothing to link

