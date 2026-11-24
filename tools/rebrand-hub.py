"""Build addon/AmazingHub from a GuildOS checkout (docs/addon/HUB_AUDIT.md section 7, docs/dev/PACK_PLAN.md Phase 9).

    python tools/rebrand-hub.py [--src vendor-ref/GuildOS] [--out addon/AmazingHub] [--any-commit]

Never edit addon/AmazingHub by hand: change a rule here and run it again. That keeps pulling a newer GuildOS to
"update vendor-ref/GuildOS, run this script, run the tests". Every patch must apply exactly once; if GuildOS
changed the code a patch expects, the script stops and names the patch, so nothing is silently skipped.

GuildOS is MIT (c) 2026 danielcosta42; its LICENSE is kept in the output and credited in THIRD_PARTY.md.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINNED = "1f9fa9d"  # GuildOS 1.40.0, audited in docs/addon/HUB_AUDIT.md section 10
PINNED_VERSION = "1.40.0"
HUB_VERSION = "0.7.0"

# What is not copied (not part of the addon, or replaced by our own files).
SKIP_DIRS = {".git", ".github", "docs", "specs", "__pycache__"}  # specs: upstream's design notes (1.40)
SKIP_FILES = {"README.md", "CHANGELOG.md", "CURSEFORGE.md", "RELEASE_NOTES.md", "chehulnet.lock", "GuildOSM.png"}
TEXT_SUFFIXES = {".lua", ".toc", ".xml", ".json"}  # json: upstream test data (1.40)

# Strings that keep their original spelling. (The original author's credit stays where the MIT licence needs it:
# LICENSE, THIRD_PARTY.md, and the TOC's X-Upstream line, none of which a player sees in game.)
PROTECT: list[str] = []

# Renames, applied in order to file contents and to file paths. In game nothing says GuildOS or Chehul (admin's
# decision 2026-11-14): the hub is "Amazing Hub", its maker "Maupa".
RENAMES = [
    (re.compile(r"(?:https?://)?guildos\.me(?:/[\w./#?=&-]*)?"), "the guild website"),  # GuildOS's web companion
    (re.compile(r"Chehul \(danielcosta42\)"), "Maupa"),
    (re.compile(r"GuildOS"), "AmazingHub"),          # global table, GuildOSDB, GuildOSInbox, media paths
    (re.compile(r"GUILDOS"), "AMAZINGHUB"),          # comms prefix, SlashCmdList key, bindings
    (re.compile(r"\|cffFFD700Guild\|r \|cffD4AC0DOS\|r"), "|cffFFD700Amazing|r |cffD4AC0DHub|r"),  # two-colour logo
    (re.compile(r"Guild OS"), "Amazing Hub"),        # what players read
    (re.compile(r"GUILD OS"), "AMAZING HUB"),
    (re.compile(r"Guild-OS"), "Amazing Hub"),
    (re.compile(r"Chehul(?=[A-Z])"), "AmzHub"),      # ChehulNet, ChehulMesh, ChehulPing…: never shared with GuildOS
    (re.compile(r"(?<![\w/])/guildos\b"), "/amazing"),  # slash command only (not inside URLs)
    (re.compile(r"(?<![\w/])/gos\b"), "/amazing"),
    (re.compile(r"guildos", re.I), "amazinghub"),    # remaining ids: style "guildos", calendar mark "guildos:"
    (re.compile(r"CHEHUL"), "MAUPA"),                # the maker's name, in texts, comments and test characters
    (re.compile(r"Chehul"), "Maupa"),
    (re.compile(r"chehul"), "maupa"),
]
OLD_NAMES = re.compile(r"guild[ -]?os|guild\|r \|c[0-9a-f]{8}os\|r|chehul|danielcosta", re.I)  # must not survive outside the credit spots

# Patches on the renamed text: (file, old, new, why). Each old string must occur exactly once.
PATCHES: list[tuple[str, str, str, str]] = [
    # --- 1. Nothing leaves our guild: one guard at every outbound choke point -----------------------------------
    ("Core/Compat.lua",
     "-- Send an addon message through ChatThrottleLib; prio is its \"BULK\" (default), \"NORMAL\" or \"ALERT\".\n"
     "function Compat.SendAddonMessage(prefix, text, channel, target, prio, queueName)\n",
     "-- Amazing Hub: addon messages and chat lines only to our own guild, officers, party and raid, or a whisper to a\n"
     "-- guild member. Public channels, SAY, YELL and whispers to strangers are dropped here, at the choke point.\n"
     "local GUILD_ONLY = { GUILD = true, OFFICER = true, PARTY = true, RAID = true, RAID_WARNING = true,\n"
     "    INSTANCE_CHAT = true }\n"
     "function Compat.InOurGuild(name)\n"
     "    if type(name) ~= \"string\" or name == \"\" or Compat.IsSecret(name) then return false end\n"
     "    if C_GuildInfo and C_GuildInfo.MemberExistsByName then\n"
     "        local ok, yes = pcall(C_GuildInfo.MemberExistsByName, name)\n"
     "        if ok and not Compat.IsSecret(yes) and yes then return true end\n"
     "    end\n"
     "    local ok, yes = pcall(AmazingHub.IsGuildmate, AmazingHub, name)\n"
     "    return ok and yes == true\n"
     "end\n"
     "function Compat.AllowedOutbound(channel, target)\n"
     "    if GUILD_ONLY[channel] then return true end\n"
     "    return channel == \"WHISPER\" and Compat.InOurGuild(target)\n"
     "end\n"
     "-- Stands in for the global SendChatMessage in every file that called it directly (rebrand-hub.py SHADOW).\n"
     "function Compat.GuardedChat(text, chatType, language, target)\n"
     "    if not Compat.AllowedOutbound(chatType, target) then return end\n"
     "    local send = (C_ChatInfo and C_ChatInfo.SendChatMessage) or SendChatMessage\n"
     "    if send then return send(text, chatType, language, target) end\n"
     "end\n\n"
     "-- Send an addon message through ChatThrottleLib; prio is its \"BULK\" (default), \"NORMAL\" or \"ALERT\".\n"
     "function Compat.SendAddonMessage(prefix, text, channel, target, prio, queueName)\n"
     "    if not Compat.AllowedOutbound(channel, target) then return end\n",
     "outbound guard for queued addon messages"),
    ("Core/Compat.lua",
     "function Compat.SendAddonMessageNow(prefix, text, channel, target, onSent)\n",
     "function Compat.SendAddonMessageNow(prefix, text, channel, target, onSent)\n"
     "    if not Compat.AllowedOutbound(channel, target) then return end\n",
     "outbound guard for immediate addon messages"),
    ("Core/Compat.lua",
     "function Compat.SendChatMessage(text, chatType)\n",
     "function Compat.SendChatMessage(text, chatType)\n"
     "    if not Compat.AllowedOutbound(chatType) then return false end -- Amazing Hub: no SAY, YELL, channels\n",
     "outbound guard for chat lines"),
    ("Core/Compat.lua",
     "function Compat.JoinChannel(name)\n    if not JoinChannelByName then return false end\n",
     "function Compat.JoinChannel(name)\n    do return false end -- Amazing Hub: never joins a public channel\n"
     "    if not JoinChannelByName then return false end\n",
     "never join channels"),
    ("Libs/LibAmzHubMesh.lua",
     "local function Send(prefix, payload, dist, target)\n",
     "local function Send(prefix, payload, dist, target)\n"
     "    -- Amazing Hub: the mesh may only reach our guild, our group or a guild member.\n"
     "    local guildOnly = dist == \"GUILD\" or dist == \"PARTY\" or dist == \"RAID\" or dist == \"INSTANCE_CHAT\"\n"
     "    if not guildOnly and not (dist == \"WHISPER\" and AmazingHub and AmazingHub.Compat\n"
     "        and AmazingHub.Compat.InOurGuild(target)) then\n"
     "        M.stats.refused = (M.stats.refused or 0) + 1\n"
     "        return false\n"
     "    end\n",
     "mesh guard: guild, group or guild member only"),
    ("Libs/LibAmzHubMesh.lua",
     "M.PREFIX_ROOT = \"Maupa\"",
     "M.PREFIX_ROOT = \"AmzHub\" -- Amazing Hub: never on the original addon's prefixes",
     "mesh prefix root renamed"),
    ("Modules/AmzHubNet.lua",
     "for _, name in ipairs({ \"maupa\", \"maupa costa\", \"maupa druida\", \"maupa shammy\", \"maupa lightdrizzle\" }) do",
     "for _, name in ipairs({}) do -- Amazing Hub: nobody may push alert popups (the upstream list named its author)",
     "no alert senders"),
    # --- 2. Off until an officer turns it on (decision 7) and features that leave the guild ----------------------
    ("Core/Core.lua",
     "local OFF_UNTIL_TESTED = {}\n",
     "-- Amazing Hub: off until an officer switches them on (docs/addon/HUB_AUDIT.md sections 2-3).\n"
     "local OFF_UNTIL_TESTED = { alliance = true, recruitment = true, web = true, founding = true }\n",
     "network and chat-posting features start off"),
    ("Core/Core.lua",
     "            lootMaster = true,\n            consumableChecker = true,\n            recruitment = true,\n",
     "            lootMaster = false,        -- Amazing Hub: announces in raid chat; officers switch it on\n"
     "            consumableChecker = false, -- Amazing Hub: posts results in chat; officers switch it on\n"
     "            recruitment = false,       -- Amazing Hub: welcome lines / auto-invite; officers switch it on\n",
     "chat-posting modules start off"),
    ("Core/Core.lua",
     "    if OFF_UNTIL_TESTED[id] and (not mods or mods[id] == nil) then return false end\n",
     "    if OFF_UNTIL_TESTED[id] and (not mods or mods[id] == nil) then return false end\n"
     "    -- Amazing Hub: tabs hidden until a player ticks them in Settings (also on installs that predate this)\n"
     "    if AmazingHub.OFF_BY_DEFAULT and AmazingHub.OFF_BY_DEFAULT[id] and (not mods or mods[id] == nil) then\n"
     "        return false\n"
     "    end\n",
     "Raids, Loot, Trials tabs off until switched on"),
    ("Modules/NoteCommand.lua",
     "    if AmazingHub.db.noteCommand.enabled == nil then AmazingHub.db.noteCommand.enabled = true end\n",
     "    if AmazingHub.db.noteCommand.enabled == nil then AmazingHub.db.noteCommand.enabled = false end -- Amazing Hub\n",
     "!note replies start off"),
    # --- 3. GuildLedger does these (docs/addon/HUB_AUDIT.md section 4) --------------------------------------------------
    ("Modules/GuildChat.lua",
     "function GuildChat:Initialize()\n",
     "function GuildChat:Initialize()\n"
     "    do return end -- Amazing Hub: GuildLedger keeps the guild chat (no second reader of the club history)\n",
     "guild chat capture off"),
    # RosterLog stays on: it only reads the join/leave line, shares within the guild, and TrialTracker needs it.
    ("Modules/GuildMap.lua",
     "    local f = CreateFrame(\"Frame\")\n    AmazingHub.Compat.RegisterEvent(f, \"ZONE_CHANGED_NEW_AREA\")\n",
     "    do return end -- Amazing Hub: GuildLedger's map shares positions (decision 6)\n"
     "    local f = CreateFrame(\"Frame\")\n    AmazingHub.Compat.RegisterEvent(f, \"ZONE_CHANGED_NEW_AREA\")\n",
     "guild map off"),
    ("Modules/GuildMap.lua",
     "function GuildMap:Broadcast(force)\n",
     "function GuildMap:Broadcast(force)\n    do return false end -- Amazing Hub: GuildLedger's map shares positions\n",
     "guild map never sends"),
    ("Modules/GuildMap.lua",
     "function GuildMap:HandlePosition(sender, data, channel)\n",
     "function GuildMap:HandlePosition(sender, data, channel)\n    do return end -- Amazing Hub: see Broadcast\n",
     "guild map ignores positions"),
    ("UI/SettingsPanel.lua",
     "            \"App:  the guild website\\n\"\n"
     "            .. \"GitHub:  https://github.com/danielcosta42/AmazingHub\\n\"\n"
     "            .. \"CurseForge:  https://www.curseforge.com/projects/1549177\\n\"\n"
     "            .. \"Wago:  https://addons.wago.io/addons/rNkyABKa\")",
     "            \"Amazing Forever Guild Pack, made by Maupa for the Amazing guild.\\n\"\n"
     "            .. \"Updates: search \\\"Amazing Forever Guild Pack\\\" on CurseForge or in your addon manager.\\n\"\n"
     "            .. \"Questions and bugs: ask in the guild Discord.\")",
     "About links: ours, not the upstream project's"),
    ("tools/site-loot.lua",
     "function UnitClass() return \"Chaupa\", \"WARRIOR\" end\n",
     "function UnitClass() return \"Chaupa\", \"WARRIOR\" end\n"
     "local OWN = string.char(67, 104, 101, 104, 117, 108) .. \" Costa\" -- Amazing Hub: as in the compressed fixture\n",
     "test fixture (compressed, cannot be renamed) still holds the original test character"),
    ("tools/style.lua",
     "popups[#popups].text:find(\"WoW: Forever\", 1, true),\n  \"when combat ends",
     "popups[#popups].text:find(\"Classic\", 1, true),\n  \"when combat ends",
     "style test: the reload names the style Classic"),
    ("tools/style.lua",
     "  S = load(opts); S:Resolve()\n  function InCombatLockdown()",
     "  S = load(opts)\n"
     "  -- Amazing Hub: upstream's wizard check, with upstream's order and default (ours: Classic first and default)\n"
     "  S.ORDER = { \"amazinghub\", \"forever\" }\n"
     "  S.DEFAULT = \"amazinghub\"\n"
     "  S:Resolve()\n  function InCombatLockdown()",
     "style test: the wizard check with upstream's order"),
    ("tools/guild-block.lua",
     "table.concat(own.ct, \"+\") == \"Chaupa Costa+Mira Thornwood\"",
     "table.concat(own.ct, \"+\") == string.char(67, 104, 101, 104, 117, 108) .. \" Costa+Mira Thornwood\"",
     "test fixture (compressed, cannot be renamed) still holds the original test character"),
    # --- Classic look by default (admin's wish 2026-11-14): the game's own frames, buttons, tabs and font;
    #     "Modern" (the flat dark look with its own fonts) is chosen in Settings or with /amazing style modern.
    ("Core/Style.lua",
     "Style.DEFAULT = \"amazinghub\"\nStyle.ORDER = { \"amazinghub\", \"forever\" }\n",
     "Style.DEFAULT = \"forever\" -- Amazing Hub: the classic look unless the player picks Modern\n"
     "Style.ORDER = { \"forever\", \"amazinghub\" }\n"
     "Style.ALIASES = { classic = \"forever\", modern = \"amazinghub\" }\n",
     "classic style by default"),
    ("Core/Style.lua",
     "Style.current = Style.DEFAULT\n",
     "Style.current = \"amazinghub\" -- until Resolve at load picks the account's style (Classic by default)\n",
     "flat until resolved"),
    # upstream's style check, told about Classic/Modern (so all its other checks keep running)
    ("tools/style.lua",
     "S:Available()[2] == \"forever\", \"the Forever client offers both\")",
     "S:Available()[1] == \"forever\", \"the Forever client offers both, Classic first\")",
     "style test: order"),
    ("tools/style.lua",
     "S:Name(\"amazinghub\") == \"AmazingHub\" and S:Name(\"forever\") == \"WoW: Forever\"",
     "S:Name(\"amazinghub\") == \"Modern\" and S:Name(\"forever\") == \"Classic\"",
     "style test: names"),
    ("tools/style.lua",
     "check(ok and AmazingHubDB.style == \"forever\", \"a style the client draws is saved for the account\")\n",
     "check(ok and AmazingHubDB.style == \"forever\", \"a style the client draws is saved for the account\")\n"
     "check(S:Choose(\"modern\") and AmazingHubDB.style == \"amazinghub\" and S:Choose(\"classic\")\n"
     "  and AmazingHubDB.style == \"forever\", \"classic and modern are names for the two styles\")\n",
     "style test: aliases"),
    ("tools/style.lua",
     "check(said(\"WoW: Forever\") and said(\"AmazingHub\"), ",
     "check(said(\"Classic\") and said(\"Modern\"), ",
     "style test: fallback message"),
    ("tools/style.lua",
     "check(S:Resolve() == \"amazinghub\" and #printed == 0, \"nothing saved: amazinghub, silently\")\n",
     "check(S:Resolve() == \"forever\" and #printed == 0, \"nothing saved: Classic, silently\")\n"
     "S = load({ db = {}, noArt = true })\n"
     "check(S:Resolve() == \"amazinghub\" and #printed == 0, \"nothing saved and no art: Modern, silently\")\n",
     "style test: classic default"),
    ("tools/style.lua",
     "S = load({ db = {} })\nlocal C = AmazingHub.Colors\n",
     "S = load({ db = { style = \"amazinghub\" } })\nlocal C = AmazingHub.Colors\n",
     "style test: modern palette check picks modern"),
    ("tools/style.lua",
     "check(applies[1].label.text == \"Apply\" and applies[2].label.text == \"In use\" and applies[2].enabled == false,",
     "check(applies[2].label.text == \"Apply\" and applies[1].label.text == \"In use\" and applies[1].enabled == false,",
     "style test: Classic (in use) is listed first"),
    ("tools/style.lua",
     "applies[1].scripts.OnClick(applies[1])\n",
     "applies[2].scripts.OnClick(applies[2])\n",
     "style test: press Modern's Apply (the second button)"),
    ("Core/Style.lua",
     "        AmazingHub:Print(\"  \" .. id .. \" - \" .. self:Name(id)",
     "        AmazingHub:Print(\"  \" .. self:Name(id):lower() .. \" - \" .. self:Name(id)",
     "/amazing style lists classic and modern"),
    ("Core/Style.lua",
     "tostring(id), table.concat(self.ORDER, \", \")))",
     "tostring(id), \"classic, modern\"))",
     "unknown style names classic and modern"),
    ("tools/style.lua",
     "check(said(\"amazinghub - AmazingHub (in use)\") and said(\"forever - WoW: Forever\"), ",
     "check(said(\"modern - Modern (in use)\") and said(\"classic - Classic\"), ",
     "style test: list wording"),
    ("Core/Style.lua",
     "    amazinghub = { name = \"AmazingHub\", desc = L[\"Flat and dark: the look Amazing Hub was made with.\"] },\n"
     "    forever = { name = \"WoW: Forever\",\n"
     "                desc = L[\"The game's own bronze frames, tabs and buttons. A beta: tell us what looks off.\"] },\n",
     "    amazinghub = { name = \"Modern\", desc = \"Flat and dark, with its own clean fonts.\" },\n"
     "    forever = { name = \"Classic\",\n"
     "                desc = \"Like the game's own windows: bronze frames, tabs and buttons, and the game's font.\" },\n",
     "style names Classic and Modern"),
    ("Core/Style.lua",
     "    local id = (want and self:Has(want)) and want or self.DEFAULT\n",
     "    -- Amazing Hub: the default is Classic, which needs the client's art; without it, Modern.\n"
     "    local fallback = self:Has(self.DEFAULT) and self.DEFAULT or \"amazinghub\"\n"
     "    local id = (want and self:Has(want)) and want or fallback\n",
     "classic default falls back to modern"),
    ("Core/Style.lua",
     "function Style:Choose(id)\n",
     "function Style:Choose(id)\n    id = self.ALIASES[id] or id -- /amazing style classic | modern\n",
     "style aliases"),
    ("Core/Style.lua",
     "function Style:Apply(id)\n",
     "function Style:Apply(id)\n    id = self.ALIASES[id] or id\n",
     "style aliases in apply"),
    # --- 4. Version shown and synced --------------------------------------------------------------------------------
    # --- 5. Slash command: /amazing and /amazinghub ----------------------------------------------------------------
    ("Core/Commands.lua", "SLASH_AMAZINGHUB2 = \"/amazing\"", "SLASH_AMAZINGHUB2 = \"/amazinghub\"",
     "second slash alias"),
    # --- 6. Small wishes (0.5.4) -------------------------------------------------------------------------------------
    # Wishlist import from Discord (0.5.4, addon/hub-extra/WishImport.lua): a button in the title bar.
    # Sortable columns (0.5.4, addon/hub-extra/TableSort.lua): DKP standings and the two Professions tables.
    ("UI/ProfessionsPanel.lua",
     "                fs:SetText(HEADERS[state.mode][col.key])\n",
     "                fs:SetText(HEADERS[state.mode][col.key])\n"
     "                if AmazingHub.TableSort then -- Amazing Hub: heading = sort button with an arrow\n"
     "                    AmazingHub.TableSort.Header(fs, \"prof-\" .. state.mode, col.key, HEADERS[state.mode][col.key],\n"
     "                        function() panel:Refresh() end, AmazingHub.TableSort.PROFESSIONS_NUMERIC[col.key])\n"
     "                end\n",
     "Professions headings are sort buttons"),
    # Own chat tag (0.5.4, addon/hub-extra/ChatTag.lua): the player picks what others see in the brackets.
    ("Modules/DataCollector.lua",
     "        addonVersion = AmazingHub.VERSION,\n",
     "        addonVersion = AmazingHub.VERSION,\n"
     "        -- Amazing Hub: the tag others show in front of my guild lines (UI/ChatTag.lua); always sent, so\n"
     "        -- clearing it reaches the receivers' key-by-key merge too\n"
     "        chatTag = AmazingHub.ChatTag and (AmazingHub.ChatTag.Mine()) or nil,\n"
     "        chatTagOff = AmazingHub.ChatTag and AmazingHub.ChatTag.Off(),\n",
     "own chat tag travels with the player's data"),
    ("Modules/ChatTweaks.lua",
     "            shortTag  = (cfg.altShort",
     "            own       = AmazingHub.ChatTag and cached.fullKey and AmazingHub.ChatTag.For(cached.fullKey), -- Amazing Hub\n"
     "            shortTag  = (cfg.altShort",
     "chat lines: the author's own tag"),
    ("Modules/ChatTweaks.lua",
     "    if cfg.altTag and cfg.altShort then\n",
     "    if cfg.altTag and info.own ~= nil then -- Amazing Hub: the author's own tag (text) or none (false)\n"
     "        if info.own then\n"
     "            parts[#parts + 1] = \"|cff888888\" .. (cfg.altShort and \"[\" .. info.own .. \"]\" or \"(\" .. info.own .. \")\") .. \"|r\"\n"
     "        end\n"
     "    elseif cfg.altTag and cfg.altShort then\n",
     "chat prefix: the author's own tag replaces the alt tag"),
    # --- 7. Officer and window fixes (0.6.1) -------------------------------------------------------------------------
    # Rank arrows only where the game would allow the change: below your own rank (rank changes themselves are
    # Blizzard-protected; the hub hands them to the game's guild window).
    ("Modules/GuildManager.lua",
     "function GuildManager:CanKick()\n",
     "-- Amazing Hub: the game lets you move only members below your own rank, and never past it\n"
     "local function myRank()\n"
     "    local _, _, r = GetGuildInfo(\"player\")\n"
     "    return type(r) == \"number\" and r or nil\n"
     "end\n"
     "function GuildManager:MayPromote(rankIndex)\n"
     "    local me = myRank()\n"
     "    return me ~= nil and type(rankIndex) == \"number\" and rankIndex > me + 1\n"
     "end\n"
     "function GuildManager:MayDemote(rankIndex)\n"
     "    local me = myRank()\n"
     "    local n = (GuildControlGetNumRanks and GuildControlGetNumRanks()) or 0\n"
     "    return me ~= nil and type(rankIndex) == \"number\" and rankIndex > me and (n == 0 or rankIndex < n - 1)\n"
     "end\n"
     "-- Amazing Hub: the game's last login of an offline member as a time (nil when online or unknown)\n"
     "function GuildManager:LastOnlineTime(rosterIndex)\n"
     "    local d = self:GetDaysOffline(rosterIndex)\n"
     "    if type(d) ~= \"number\" or d ~= d then return nil end\n"
     "    return time() - math.floor(d * 86400)\n"
     "end\n"
     "\n"
     "function GuildManager:CanKick()\n",
     "rank changes allowed only below your own rank; last login as a time"),
    ("UI/ManagementPanel.lua",
     "                if canPromote then\n",
     "                if canPromote and AmazingHub.GuildManager:MayPromote(m.rankIndex) then -- Amazing Hub\n",
     "Suggestions: Promote only where allowed"),
    # Engagement counts recruiting posts and the player's own invites: both impossible in this pack on Forever.
    ("UI/ManagementPanel.lua",
     "    { key = \"engage\",   label = L[\"Engagement\"] },\n",
     "    -- Amazing Hub: no Engagement (recruiting posts and addon invites are blocked on WoW: Forever)\n",
     "Leadership: Engagement sub-tab removed"),
    # Last seen: the game's last login too, so members without the addon show a time.
    ("UI/RosterFrame.lua",
     "lastSync = addonData.lastSync or 0,\n",
     "lastSync = addonData.lastSync or 0,\n"
     "                        lastOnline = (not isOnline and AmazingHub.GuildManager and AmazingHub.GuildManager.LastOnlineTime\n"
     "                            and AmazingHub.GuildManager:LastOnlineTime(i)) or 0, -- Amazing Hub\n",
     "roster rows: the game's last login"),
    ("UI/RosterFrame.lua",
     "value = function(d) return d.lastUpdate > 0 and d.lastUpdate or nil end },\n",
     "value = function(d) -- Amazing Hub: the later of the addon's data and the game's last login\n"
     "          local t = math.max(d.lastUpdate, d.lastOnline or 0)\n"
     "          return t > 0 and t or nil\n"
     "      end },\n",
     "Last seen sorts by the game's last login too"),
    ("UI/RosterFrame.lua",
     "    elseif data.lastUpdate > 0 then\n        row.lastSeenText:SetText(AmazingHub:TimeAgo(data.lastUpdate))\n",
     "    elseif math.max(data.lastUpdate, data.lastOnline or 0) > 0 then -- Amazing Hub: or the game's last login\n"
     "        row.lastSeenText:SetText(AmazingHub:TimeAgo(math.max(data.lastUpdate, data.lastOnline or 0)))\n",
     "Last seen shows the game's last login too"),
    # The way back to the game's own guild window: always in the bottom bar, with a clear name.
    ("UI/Window.lua",
     "    { key = \"blizzard\", label = L[\"Blizzard\"], priority = 50,\n",
     "    { key = \"blizzard\", label = \"Game guild window\", priority = 95, -- Amazing Hub: always shown\n",
     "bottom bar: Game guild window button stays"),
    # Loot equity: plain words.
    ("UI/LootWindow.lua",
     "countText:SetText(string.format(L[\"%d members with loot/raid history\"], #rows))",
     "countText:SetText(string.format(\"%d members: items received compared with raid attendance\", #rows))",
     "Loot equity: what the table compares"),
    ("UI/LootWindow.lua", "L[\"dry\"]", "\"due loot\"", "Loot equity: 'dry' in plain words"),
    ("UI/LootWindow.lua", "L[\"well-fed\"]", "\"lots of loot\"", "Loot equity: 'well-fed' in plain words"),
    # UI scale: five buttons. The slider sat inside the window it scaled, so every step moved it under the mouse.
    # --- 8. Re-pin to GuildOS 1.40.0 (docs/addon/HUB_AUDIT.md section 10, 2026-11-24) ------------------------
    # Developer features: what acts for the player is hidden unless the AmazingHubDev addon is installed (the
    # admin's own install; tools/install.ps1 links addon/AmazingHubDev, the CurseForge pack never has it). It sets
    # the global AmazingHubDevFeatures = true before the hub loads (OptionalDeps); the patches read that global, so
    # upstream's own checks can switch it on too.
    ("Core/Config.lua",
     "AmazingHub.VERSION           = \"1.40.0\"",
     "-- Amazing Hub: true only with the AmazingHubDev addon (never in the CurseForge pack): group posts and\n"
     "-- auto-invite, reminder whispers, bulk rank changes, bank cleanup, warning whispers and chat alerts.\n"
     "AmazingHub.DEV = AmazingHubDevFeatures == true\n"
     f"AmazingHub.VERSION           = \"{HUB_VERSION}\"",
     "hub version; developer features flag"),
    ("Modules/AllianceLink.lua",
     "function Link:Initialize()\n",
     "function Link:Initialize()\n"
     "    do return end -- Amazing Hub: no alliance: never joins its channel, never copies guild chat (HUB_AUDIT 10.2 A1)\n",
     "alliance link never starts"),
    ("Core/Compat.lua",
     "function Compat.SendWhisper(text, target)\n",
     "function Compat.SendWhisper(text, target)\n"
     "    if not Compat.AllowedOutbound(\"WHISPER\", target) then return false end -- Amazing Hub: guild members only\n",
     "whispers only to guild members"),
    ("Core/Compat.lua",
     "function Compat.SendChannelMessage(text, index)\n",
     "function Compat.SendChannelMessage(text, index)\n"
     "    do return false end -- Amazing Hub: never into a channel\n",
     "never a line into a channel"),
    ("Core/Compat.lua",
     "function Compat.JoinPrivateChannel(name, password)\n",
     "function Compat.JoinPrivateChannel(name, password)\n"
     "    do return false end -- Amazing Hub: never joins a channel\n",
     "never join a private channel"),
    ("Modules/CommSystem.lua",
     "CommSystem.LEGACY_ALT_MAX = \"1.38.0\"",
     "CommSystem.LEGACY_ALT_MAX = \"0.6.99\" -- Amazing Hub: our last version before AltSync (pack 0.7.0 has it)",
     "alt links: our own versions decide who is legacy"),
    ("tools/whisper-not-found.lua",
     "shipped verbatim from danielcosta42/maupanet",
     "shipped verbatim from the upstream project",
     "test comment without the upstream author's name"),
    ("UI/SettingsPanel.lua",
     "    if AmazingHub.GuildMap then\n"
     "        F:Check(L[\"Show guildmates in your zone on the minimap\"]",
     "    if false and AmazingHub.GuildMap then -- Amazing Hub: the hub's map is off, so are its minimap dots\n"
     "        F:Check(L[\"Show guildmates in your zone on the minimap\"]",
     "no minimap-dots switch for the switched-off hub map"),
    ("UI/SettingsPanel.lua",
     "setCt(\"altShort\"),\n"
     "        { indent = 2 * SUB_INDENT, enabled = function() return annotating() and ct().altTag ~= false end })\n",
     "setCt(\"altShort\"),\n"
     "        { indent = 2 * SUB_INDENT, enabled = function() return annotating() and ct().altTag ~= false end })\n"
     "    if AmazingHub.ChatTag then AmazingHub.ChatTag.BuildForm(F, SUB_INDENT, annotating) end -- Amazing Hub: own tag\n",
     "Settings: what others see in the brackets"),
    ("UI/SettingsPanel.lua",
     "    local scale = CreateFrame(\"Slider\", \"AmazingHubScaleSlider\", scaleRow, \"OptionsSliderTemplate\")\n"
     "    scale:SetMinMaxValues(0.8, 1.2)\n"
     "    scale:SetValueStep(0.05)\n"
     "    scale:SetObeyStepOnDrag(true)\n"
     "    -- The template's three texts, by the names it gives them.\n"
     "    local function say(suffix, text)\n"
     "        local fs = _G[(scale:GetName() or \"\") .. suffix]\n"
     "        if fs then fs:SetText(text) end\n"
     "    end\n"
     "    say(\"Low\", \"80%\")\n"
     "    say(\"High\", \"120%\")\n"
     "    scale:SetScript(\"OnValueChanged\", function(_, value)\n"
     "        value = math.floor(value * 20 + 0.5) / 20   -- snap to the 0.05 step\n"
     "        AmazingHub:SetSetting(\"uiScale\", value)\n"
     "        say(\"Text\", string.format(\"%d%%\", value * 100))\n"
     "        UI:ApplyScale()\n"
     "    end)\n"
     "    F:Sync(function()\n"
     "        local v = AmazingHub:GetSetting(\"uiScale\") or 1\n"
     "        scale:SetValue(v)\n"
     "        say(\"Text\", string.format(\"%d%%\", v * 100))\n"
     "    end)\n"
     "    F:Row(scaleRow, { wide = true, place = function(_, w)\n"
     "        local lw = labelColumn(w)\n"
     "        scale:ClearAllPoints()\n"
     "        scale:SetPoint(\"LEFT\", scaleRow, \"LEFT\", lw + 8, 2)\n"
     "        scale:SetWidth(math.max(100, math.min(200, w - lw - 8 - 40)))\n"
     "        return 34\n"
     "    end })\n",
     "    -- Amazing Hub: five buttons instead of the slider (the slider moved with the window it scaled)\n"
     "    local scaleBtns = {}\n"
     "    for i, v in ipairs({ 0.8, 0.9, 1.0, 1.1, 1.2 }) do\n"
     "        local b = UI:CreateButton(scaleRow, \"\", 50, 20)\n"
     "        b:SetScript(\"OnClick\", function()\n"
     "            AmazingHub:SetSetting(\"uiScale\", v)\n"
     "            UI:ApplyScale()\n"
     "            F:Refresh()\n"
     "        end)\n"
     "        scaleBtns[i] = { b = b, v = v }\n"
     "    end\n"
     "    F:Sync(function()\n"
     "        local cur = AmazingHub:GetSetting(\"uiScale\") or 1\n"
     "        for _, e in ipairs(scaleBtns) do\n"
     "            local pct = string.format(\"%d%%\", e.v * 100 + 0.5)\n"
     "            e.b.label:SetText(math.abs(cur - e.v) < 0.01 and (\"|cffFFD700\" .. pct .. \"|r\") or pct)\n"
     "        end\n"
     "    end)\n"
     "    F:Row(scaleRow, { wide = true, place = function(_, w)\n"
     "        local lw = labelColumn(w)\n"
     "        for i, e in ipairs(scaleBtns) do\n"
     "            e.b:ClearAllPoints()\n"
     "            e.b:SetPoint(\"LEFT\", scaleRow, \"LEFT\", lw + 8 + (i - 1) * 54, 2)\n"
     "        end\n"
     "        return 34\n"
     "    end })\n",
     "UI scale: five buttons instead of the slider"),
    ("UI/FeaturePanels.lua",
     "    f.syncBtn = syncBtn\n",
     "    f.syncBtn = syncBtn\n"
     "    if AmazingHub.WishImport then -- Amazing Hub: paste the line from the bot's /wish export\n"
     "        local importBtn = UI:CreateButton(f, \"Import from Discord\", 130, 22)\n"
     "        importBtn:SetPoint(\"TOPRIGHT\", f, \"TOPRIGHT\", -130, -9) -- title bar, left of the item counter\n"
     "        importBtn:SetScript(\"OnClick\", function() AmazingHub.WishImport.ShowPopup() end)\n"
     "    end\n",
     "wishlist window: Import from Discord"),
    ("UI/PointsPanel.lua",
     "            fs:SetShown(at.shown)\n"
     "        end\n"
     "\n"
     "        local list\n"
     "        if account then\n",
     "            fs:SetShown(at.shown)\n"
     "        end\n"
     "        if AmazingHub.TableSort and not account then -- Amazing Hub: click a heading to sort (UI/TableSort.lua)\n"
     "            AmazingHub.TableSort.Headers(\"dkp\", { { heads.name, \"name\", TITLES.name },\n"
     "                { heads.cur, \"current\", TITLES.cur, true }, { heads.earned, \"earned\", TITLES.earned, true },\n"
     "                { heads.spent, \"spent\", TITLES.spent, true } }, refresh)\n"
     "        end\n"
     "\n"
     "        local list\n"
     "        if account then\n",
     "DKP standings headings are sort buttons"),
    ("UI/PointsPanel.lua",
     "            list = inScope(P.GetStandings, P)\n",
     "            list = inScope(P.GetStandings, P)\n"
     "            if AmazingHub.TableSort then -- Amazing Hub: the chosen column and direction\n"
     "                AmazingHub.TableSort.Apply(\"dkp\", list, AmazingHub.TableSort.POINTS)\n"
     "            end\n",
     "DKP standings sorted by the chosen column"),
    ("UI/ProfessionsPanel.lua",
     "            local at, n\n"
     "            if UI.WithDetail then\n",
     "            local TS = AmazingHub.TableSort -- Amazing Hub: the chosen column, before the detail row goes in\n"
     "            if TS then TS.Apply(\"prof-recipes\", out, TS.PROFESSIONS.recipes) end\n"
     "            local at, n\n"
     "            if UI.WithDetail then\n",
     "Professions recipes sorted by the chosen column"),
    ("UI/ProfessionsPanel.lua",
     "            state.results = state.line and D.MemberRows(state.line) or {}\n"
     "            state.detailAt, state.detailRows = nil, nil\n",
     "            state.results = state.line and D.MemberRows(state.line) or {}\n"
     "            state.detailAt, state.detailRows = nil, nil\n"
     "            local TS = AmazingHub.TableSort -- Amazing Hub: the chosen column and direction\n"
     "            if TS then TS.Apply(\"prof-crafters\", state.results, TS.PROFESSIONS.crafters) end\n",
     "Professions crafters sorted by the chosen column"),
    ("UI/ManagementPanel.lua",
     "        row.downBtn:SetShown(canDemote)\n"
     "        row.upBtn:SetShown(canPromote)\n",
     "        -- Amazing Hub: only below your own rank\n"
     "        row.downBtn:SetShown(canDemote and AmazingHub.GuildManager:MayDemote(m.rankIndex))\n"
     "        row.upBtn:SetShown(canPromote and AmazingHub.GuildManager:MayPromote(m.rankIndex))\n",
     "Ranks: arrows only where allowed"),
    ("Modules/LFGBoard.lua",
     "LFGBoard.DEFAULTS = { notify = true, postToGuild = true, lastRole = \"ANY\", lastNote = \"\",\n",
     "LFGBoard.DEFAULTS = { notify = true, postToGuild = false, lastRole = \"ANY\", lastNote = \"\", -- Amazing Hub: off\n",
     "group lines in guild chat start off"),
    ("Modules/LFGBoard.lua",
     "                      autoInvite = true, toast = true, filterCat = \"all\", filterLevel = false }\n",
     "                      autoInvite = false, toast = true, filterCat = \"all\", filterLevel = false } -- Amazing Hub\n"
     "-- Amazing Hub: posting in guild chat and inviting whoever whispers only with the developer addon (decision 7)\n"
     "local DEV_PREFS = { postToGuild = true, autoInvite = true }\n",
     "auto-invite starts off; developer-only prefs"),
    ("Modules/LFGBoard.lua",
     "function LFGBoard:Pref(key)\n",
     "function LFGBoard:Pref(key)\n"
     "    if DEV_PREFS[key] and not AmazingHubDevFeatures then return false end\n",
     "group prefs: guild posts and auto-invite read off without the developer addon"),
    ("Modules/LFGBoard.lua",
     "function LFGBoard:_SayInGuild(role, note, acts, line)\n",
     "function LFGBoard:_SayInGuild(role, note, acts, line)\n"
     "    if not AmazingHubDevFeatures then return false end -- Amazing Hub: no group lines in guild chat (decision 7)\n",
     "no group lines in guild chat"),
    ("Modules/Groups.lua",
     "local function pref(key)\n",
     "local function pref(key)\n"
     "    if (key == \"autoInvite\" or key == \"postToGuild\") and not AmazingHubDevFeatures then return false end -- Amazing Hub\n",
     "groups: no auto-invite without the developer addon"),
    ("UI/GroupsPanel.lua",
     "    auto.checkbox.onChanged = function(_, checked) B:SetPref(\"autoInvite\", checked and true or false) end\n"
     "    y = y - 26\n",
     "    auto.checkbox.onChanged = function(_, checked) B:SetPref(\"autoInvite\", checked and true or false) end\n"
     "    y = y - 26\n"
     "    if not AmazingHubDevFeatures then -- Amazing Hub: neither option in the CurseForge pack (decision 7)\n"
     "        chat:Hide()\n"
     "        auto:Hide()\n"
     "        y = y + 52\n"
     "    end\n",
     "groups: guild-post and auto-invite switches hidden"),
    ("UI/ManagementPanel.lua",
     "    { key = \"alertrules\", label = L[\"Alert rules\"] },\n"
     "}\n",
     "    { key = \"alertrules\", label = L[\"Alert rules\"] },\n"
     "}\n"
     "-- Amazing Hub: officer tools that act for the player only with the developer addon (decision 7)\n"
     "if not AmazingHubDevFeatures then\n"
     "    local DEV_ONLY = { bulk = true, remind = true, alerts = true, alertrules = true }\n"
     "    for i = #SUBTABS, 1, -1 do\n"
     "        if DEV_ONLY[SUBTABS[i].key] then table.remove(SUBTABS, i) end\n"
     "    end\n"
     "end\n",
     "Leadership: bulk actions, reminders and chat alerts only for developers"),
    ("Modules/AddonReminder.lua",
     "function Reminder:Remind(key)\n",
     "function Reminder:Remind(key)\n"
     "    if not AmazingHubDevFeatures then return false, \"officer\" end -- Amazing Hub: no reminder whispers (decision 7)\n",
     "no addon reminder whispers"),
    ("Core/Commands.lua",
     "        if AmazingHub.BulkActions then\n"
     "            AmazingHub.BulkActions:Command(",
     "        if AmazingHub.BulkActions and AmazingHubDevFeatures then -- Amazing Hub: developers only\n"
     "            AmazingHub.BulkActions:Command(",
     "/amazing bulk only for developers"),
    ("Core/Commands.lua",
     "        if AmazingHub.BulkActions then\n"
     "            AmazingHub.BulkActions:CommandGroup(",
     "        if AmazingHub.BulkActions and AmazingHubDevFeatures then -- Amazing Hub: developers only\n"
     "            AmazingHub.BulkActions:CommandGroup(",
     "/amazing altgroup only for developers"),
    ("UI/MemberDetail.lua",
     "        if AmazingHub:IsOfficer() and AmazingHub.BulkActions and #linkedKeys > 1 then\n",
     "        if AmazingHub:IsOfficer() and AmazingHub.BulkActions and AmazingHubDevFeatures and #linkedKeys > 1 then -- Amazing Hub\n",
     "member window: alt group promote/demote only for developers"),
    ("Modules/GuildBankCleanup.lua",
     "AmazingHub.GuildBankCleanup = Cleanup\n",
     "if AmazingHubDevFeatures then AmazingHub.GuildBankCleanup = Cleanup end -- Amazing Hub: bank cleanup for developers only\n",
     "bank cleanup only for developers"),
    ("Modules/Discipline.lua",
     "    if opts.silent then return w, \"silent\" end\n",
     "    if opts.silent or not AmazingHubDevFeatures then return w, \"silent\" end -- Amazing Hub: recorded, never whispered\n",
     "warnings are recorded, not whispered"),
    ("UI/WarnDialog.lua",
     "    local silent = UI:CreateCheckbox(f, L[\"Only record it, without a whisper\"])\n"
     "    silent:SetPoint(\"TOPLEFT\", 14, -228)\n",
     "    local silent = UI:CreateCheckbox(f, L[\"Only record it, without a whisper\"])\n"
     "    silent:SetPoint(\"TOPLEFT\", 14, -228)\n"
     "    if not AmazingHubDevFeatures then -- Amazing Hub: a warning is recorded only (decision 7)\n"
     "        silent:Hide()\n"
     "        msgLabel:SetText(\"The text, kept with the warning (this pack never whispers it)\")\n"
     "    end\n",
     "warn window: no whisper option"),
    ("Modules/ModAlerts.lua",
     "AmazingHub.ModAlerts = ModAlerts\n",
     "if AmazingHubDevFeatures then AmazingHub.ModAlerts = ModAlerts end -- Amazing Hub: chat alerts for developers only\n",
     "ModAlerts: chat alerts only for developers"),
    ("Modules/ModFlood.lua",
     "AmazingHub.ModFlood = ModFlood\n",
     "if AmazingHubDevFeatures then AmazingHub.ModFlood = ModFlood end -- Amazing Hub: chat alerts for developers only\n",
     "ModFlood: chat alerts only for developers"),
    ("Modules/Newcomer.lua",
     "AmazingHub.Newcomer = Newcomer\n",
     "if AmazingHubDevFeatures then AmazingHub.Newcomer = Newcomer end -- Amazing Hub: chat alerts for developers only\n",
     "Newcomer: chat alerts only for developers"),
    ("Modules/RecruitmentSystem.lua",
     "    welcomeEnabled = true,\n",
     "    welcomeEnabled = false, -- Amazing Hub: no welcome lines in guild chat, even with recruitment on\n",
     "welcome lines start off"),
    ("Core/Core.lua",
     "    if not AmazingHubDB[dbKey] then\n"
     "        AmazingHubDB[dbKey] = {}\n"
     "    end\n",
     "    -- Amazing Hub: data the 0.6 hub saved under \"<guild>-\" (no realm) is copied over once (UI/PackMigrate.lua)\n"
     "    if guilded and AmazingHub.PackMigrate then\n"
     "        AmazingHub:SafeCall(AmazingHub.PackMigrate.MergeRealmless, AmazingHub.PackMigrate, dbKey, realmName)\n"
     "    end\n"
     "    if not AmazingHubDB[dbKey] then\n"
     "        AmazingHubDB[dbKey] = {}\n"
     "    end\n",
     "saved data without the realm is copied to the realm's key"),
]

# Patches whose anchor occurs a known number of times: (file, old, new, why, times).
PATCHES_ALL: list[tuple[str, str, str, str, int]] = [
    ("tools/site-loot.lua", "== \"Chaupa Costa\"", "== OWN",
     "test fixture: the original test character's name", 4),
    ("tools/site-loot.lua", "wl[\"chaupa costa\"]", "wl[OWN:lower()]", "test fixture: the same name as a key", 4),
    ("tools/style.lua", "S = load({ db = {} }); S:Resolve()",
     "S = load({ db = { style = \"amazinghub\" } }); S:Resolve()",
     "style test: blocks that check the flat look pick Modern (nothing saved is Classic now)", 5),
]

# Our own hub files: (file in addon/hub-extra, folder in the hub). Appended to the TOC in this order. The item
# catalogue's data (tools/build-catalog.py) comes before the file that hands it to the wishlist.
EXTRAS = [("PackMigrate.lua", "UI"), ("PackTweaks.lua", "UI"), ("TableSort.lua", "UI"), ("ChatTag.lua", "UI"), ("WishImport.lua", "UI"), ("LedgerPanel.lua", "UI"), ("SettingsPlus.lua", "UI"),
          ("Data/ItemCatalog.lua", "Data"), ("ItemCatalog.lua", "UI")]

# Files that call the chat globals directly get guarded file-locals in front, so no code path sends past the guard.
# (Replacing the globals themselves would taint Blizzard's chat frame; file-locals touch only this addon.)
SHADOW_RX = re.compile(r"(?<![.\w:])(SendChatMessage|JoinChannelByName|JoinTemporaryChannel)(?!\w)")
SHADOW_HEAD = {
    "SendChatMessage": "local SendChatMessage = function(...) return AmazingHub.Compat.GuardedChat(...) end",
    "JoinChannelByName": "local JoinChannelByName = nil",
    "JoinTemporaryChannel": "local JoinTemporaryChannel = nil",
}
SHADOW_SKIP = {"Core/Compat.lua"}  # Compat holds the guard itself


def shadow(rel: str, text: str) -> str:
    if rel in SHADOW_SKIP or not rel.endswith(".lua"):
        return text
    code = "\n".join(l for l in text.split("\n") if not l.lstrip().startswith("--"))
    names = sorted({m.group(1) for m in SHADOW_RX.finditer(code)
                    if not code[max(0, m.start() - 1):m.start()] == '"'})
    if not names:
        return text
    head = "-- Amazing Hub guard (tools/rebrand-hub.py): chat leaves only to the guild, group or a guild member.\n"
    return head + "\n".join(SHADOW_HEAD[n] for n in names) + "\n" + text


TOC_HEADER =f"""## Interface: 16001
## Title: |cffFFD700Amazing Hub|r |cff888888(Amazing Forever Guild Pack)|r
## Notes: Guild window for the Amazing guild: roster, professions and recipes, calendar, guild members on the map.
## Author: Maupa
## Version: {HUB_VERSION}
## SavedVariables: AmazingHubDB
## DefaultState: enabled
## IconTexture: Interface\\AddOns\\AmazingHub\\Media\\minimap-logo
## OptionalDeps: GuildLedger, AmazingHubDev
## X-License: MIT
## X-Category: Guild
## X-Upstream: GuildOS {PINNED_VERSION} ({PINNED[:7]}) https://github.com/danielcosta42/GuildOS
"""


# In upstream's test scripts the maker's name is a test character whose length and sort position the checks rely on
# (fixed serialized bytes, sorted lists): there it becomes a same-length name with the same start.
TEST_NAMES = [(re.compile(r"CHEHUL(?![A-Z])"), "CHAUPA"), (re.compile(r"Chehul(?![A-Z])"), "Chaupa"),
              (re.compile(r"chehul(?![a-z])"), "chaupa"),
              (re.compile(r"43686568756c"), "436861757061")]  # the same name inside a hex fixture


def rename(text: str, test: bool = False) -> str:
    keep = {}
    for i, p in enumerate(PROTECT):
        token = f"\x00{i}\x00"
        keep[token] = p
        text = text.replace(p, token)
    for rx, new in (TEST_NAMES if test else []) + RENAMES:
        text = rx.sub(new, text)
    for token, p in keep.items():
        text = text.replace(token, p)
    return text


def rewrite_toc(text: str) -> str:
    body = text.split("\n\n", 1)[1] if "\n\n" in text else text  # everything after the header block
    return TOC_HEADER + "\n" + body


def build(src: Path, out: Path, any_commit: bool) -> int:
    head = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if not head.startswith(PINNED) and not any_commit:
        sys.exit(f"{src} is at {head or '?'}, not the audited {PINNED[:7]}. Audit the difference, update PINNED,"
                 " or pass --any-commit.")
    out.mkdir(parents=True, exist_ok=True)
    for child in out.iterdir():  # empty it, but keep the folder (an editor or the game may hold it open)
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    count = 0
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if (any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts) or path.name in SKIP_FILES
                or path.is_dir()):  # dotfiles (.gitignore, .pkgmeta, .luacheckrc) are GuildOS's repo, not the addon
            continue
        if rel.parts[0] == "tools" and path.suffix in {".py", ".sh", ".ps1", ".yml", ".yaml", ".md", ".cmd"}:
            continue  # upstream's release/CI scripts; its Lua checks and their data stay (addon/tests/test_hub.py)
        dest = out / rename(rel.as_posix())
        dest.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")  # git may check out CRLF
            text = rename(text, test=rel.parts[0] == "tools")
            if path.name == "GuildOS.toc":
                text = rewrite_toc(text)
            dest.write_bytes(text.encode("utf-8"))
        else:
            shutil.copy2(path, dest)
        count += 1
    for rel, old, new, why in PATCHES:
        f = out / rel
        text = f.read_bytes().decode("utf-8")
        n = text.count(old)
        if n != 1:
            sys.exit(f"patch '{why}' expected its anchor once in {rel}, found {n}: GuildOS changed; update the patch.")
        f.write_bytes(text.replace(old, new).encode("utf-8"))
    for rel, old, new, why, times in PATCHES_ALL:
        f = out / rel
        text = f.read_bytes().decode("utf-8")
        n = text.count(old)
        if n != times:
            sys.exit(f"patch '{why}' expected its anchor {times}x in {rel}, found {n}: GuildOS changed; update it.")
        f.write_bytes(text.replace(old, new).encode("utf-8"))
    # Our own files (addon/hub-extra), loaded last so they can register tabs and replace hub functions.
    toc = out / "AmazingHub.toc"
    toc_text = toc.read_bytes().decode("utf-8").rstrip("\n") + "\n\n# Amazing Forever Guild Pack (addon/hub-extra)\n"
    for name, folder in EXTRAS:
        base = Path(name).name
        shutil.copy2(ROOT / "addon" / "hub-extra" / name, out / folder / base)
        toc_text += f"{folder}\\{base}\n"
        count += 1
    toc.write_bytes(toc_text.encode("utf-8"))
    for f in sorted(out.rglob("*.lua")):
        rel = f.relative_to(out).as_posix()
        if rel.startswith("tools/"):
            continue
        text = f.read_bytes().decode("utf-8")
        guarded = shadow(rel, text)
        if guarded != text:
            f.write_bytes(guarded.encode("utf-8"))
            print(f"  guard: {rel}")
    leftovers = [f"{p.relative_to(out)}: {m.group(0)}" for p in out.rglob("*") if p.suffix in TEXT_SUFFIXES
                 for m in [OLD_NAMES.search(rename_safe(p.read_text("utf-8")))] if m]
    if leftovers:
        sys.exit(f"old names left in: {leftovers[:8]}")
    return count


def rename_safe(text: str) -> str:
    """Text to search for old names: without the protected strings and the TOC's X-Upstream credit line."""
    for p in PROTECT:
        text = text.replace(p, "")
    return "\n".join(line for line in text.split("\n") if not line.startswith("## X-Upstream:"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--src", default=str(ROOT / "vendor-ref" / "GuildOS"))
    ap.add_argument("--out", default=str(ROOT / "addon" / "AmazingHub"))
    ap.add_argument("--any-commit", action="store_true")
    a = ap.parse_args()
    n = build(Path(a.src), Path(a.out), a.any_commit)
    print(f"built {a.out}: {n} files, {len(PATCHES)} patches applied")


if __name__ == "__main__":
    main()
