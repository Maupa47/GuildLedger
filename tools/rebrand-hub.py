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
PINNED = "80883a096cdf9fa1366fb1a248e99b4462d74a21"  # GuildOS 1.20.1, audited in docs/addon/HUB_AUDIT.md
HUB_VERSION = "0.5.4"

# What is not copied (not part of the addon, or replaced by our own files).
SKIP_DIRS = {".git", ".github", "docs", "__pycache__"}
SKIP_FILES = {"README.md", "CHANGELOG.md", "CURSEFORGE.md", "RELEASE_NOTES.md", "chehulnet.lock", "GuildOSM.png"}
TEXT_SUFFIXES = {".lua", ".toc", ".xml"}

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
    ("UI/FeaturePanels.lua",
     "    if AmazingHub.GuildMap then\n        local dotsCb",
     "    if false and AmazingHub.GuildMap then -- Amazing Hub: the hub's map is off, so are its minimap dots\n"
     "        local dotsCb",
     "no minimap-dots switch for the switched-off hub map"),
    ("UI/FeaturePanels.lua",
     "            \"App:  the guild website\\n\"\n"
     "            .. \"GitHub:  https://github.com/danielcosta42/AmazingHub\\n\"\n"
     "            .. \"CurseForge:  https://www.curseforge.com/projects/1549177\\n\"\n"
     "            .. \"Wago:  https://addons.wago.io/addons/rNkyABKa\")",
     "            \"Amazing Forever Guild Pack, made by Maupa for the Amazing guild.\\n\"\n"
     "            .. \"Updates: search \\\"Amazing Forever Guild Pack\\\" on CurseForge or in your addon manager.\\n\"\n"
     "            .. \"Questions and bugs: ask in the guild Discord.\")",
     "About links: ours, not the upstream project's"),
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
    ("Core/Config.lua",
     "AmazingHub.VERSION           = \"1.20.1\"",
     f"AmazingHub.VERSION           = \"{HUB_VERSION}\"",
     "hub version"),
    # --- 5. Slash command: /amazing and /amazinghub ----------------------------------------------------------------
    ("Core/Commands.lua", "SLASH_AMAZINGHUB2 = \"/amazing\"", "SLASH_AMAZINGHUB2 = \"/amazinghub\"",
     "second slash alias"),
    # --- 6. Small wishes (0.5.4) -------------------------------------------------------------------------------------
    ("Modules/RecipeTracker.lua",
     "        for _, c in ipairs(sorted) do\n"
     "            local cc = c.class and AmazingHub.ClassColors[c.class] or C.white\n",
     "        for i, c in ipairs(sorted) do\n"
     "            -- Amazing Hub: at most 5 names (online first); the rest is counted (full list: Professions tab)\n"
     "            if i > 5 then\n"
     "                tooltip:AddLine(string.format(\"  +%d more (/amazing, Professions)\", #sorted - 5), 0.6, 0.6, 0.6)\n"
     "                break\n"
     "            end\n"
     "            local cc = c.class and AmazingHub.ClassColors[c.class] or C.white\n",
     "crafter lists on item tooltips: 5 names at most"),
    # Wishlist import from Discord (0.5.4, tools/hub-extra/WishImport.lua): a button in the title bar.
    ("UI/FeaturePanels.lua",
     "        AmazingHub:Print(L[\"[Wishlist] Sent to the guild.\"])\n"
     "    end)\n"
     "\n"
     "    AmazingHub.WishlistFrame = f\n",
     "        AmazingHub:Print(L[\"[Wishlist] Sent to the guild.\"])\n"
     "    end)\n"
     "    if AmazingHub.WishImport then -- Amazing Hub: paste the line from the bot's /wish export\n"
     "        local importBtn = UI:CreateButton(f, \"Import from Discord\", 130, 22)\n"
     "        importBtn:SetPoint(\"TOPRIGHT\", f, \"TOPRIGHT\", -130, -9) -- title bar, left of the item counter\n"
     "        importBtn:SetScript(\"OnClick\", function() AmazingHub.WishImport.ShowPopup() end)\n"
     "    end\n"
     "\n"
     "    AmazingHub.WishlistFrame = f\n",
     "wishlist window: Import from Discord"),
    # Sortable columns (0.5.4, tools/hub-extra/TableSort.lua): DKP standings and the two Professions tables.
    ("UI/PointsPanel.lua",
     "    hcol(L[\"MEMBER\"], 4)\n"
     "    hcol(L[\"CURRENT\"], 250)\n"
     "    hcol(L[\"EARNED\"], 330)\n"
     "    hcol(L[\"SPENT\"], 410)\n",
     "    -- Amazing Hub: click a heading to sort, click again to flip (UI/TableSort.lua)\n"
     "    local sortHeads = {\n"
     "        { hcol(L[\"MEMBER\"], 4), \"name\", L[\"MEMBER\"] },\n"
     "        { hcol(L[\"CURRENT\"], 250), \"current\", L[\"CURRENT\"], true },\n"
     "        { hcol(L[\"EARNED\"], 330), \"earned\", L[\"EARNED\"], true },\n"
     "        { hcol(L[\"SPENT\"], 410), \"spent\", L[\"SPENT\"], true },\n"
     "    }\n",
     "DKP standings headings are sort buttons"),
    ("UI/PointsPanel.lua",
     "        local list = AmazingHub.Points:GetStandings()\n",
     "        local list = AmazingHub.Points:GetStandings()\n"
     "        if AmazingHub.TableSort then -- Amazing Hub: the chosen column and direction\n"
     "            AmazingHub.TableSort.Headers(\"dkp\", sortHeads, refresh)\n"
     "            AmazingHub.TableSort.Apply(\"dkp\", list, AmazingHub.TableSort.POINTS)\n"
     "        end\n",
     "DKP standings sorted by the chosen column"),
    ("UI/ProfessionsPanel.lua",
     "            state.results = state.line and D.MemberRows(state.line) or {}\n"
     "        end\n",
     "            state.results = state.line and D.MemberRows(state.line) or {}\n"
     "        end\n"
     "        local TS = AmazingHub.TableSort -- Amazing Hub: the chosen column and direction\n"
     "        if TS then TS.Apply(\"prof-\" .. state.mode, state.results, TS.PROFESSIONS[state.mode]) end\n",
     "Professions tables sorted by the chosen column"),
    ("UI/ProfessionsPanel.lua",
     "                fs:SetText(HEADERS[state.mode][col.key])\n",
     "                fs:SetText(HEADERS[state.mode][col.key])\n"
     "                if AmazingHub.TableSort then -- Amazing Hub: heading = sort button with an arrow\n"
     "                    AmazingHub.TableSort.Header(fs, \"prof-\" .. state.mode, col.key, HEADERS[state.mode][col.key],\n"
     "                        function() panel:Refresh() end, AmazingHub.TableSort.PROFESSIONS_NUMERIC[col.key])\n"
     "                end\n",
     "Professions headings are sort buttons"),
    # Own chat tag (0.5.4, tools/hub-extra/ChatTag.lua): the player picks what others see in the brackets.
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
    ("UI/FeaturePanels.lua",
     "            AmazingHub.db.chatTweaks.altShort = checked and true or false\n"
     "        end\n"
     "    end\n"
     "    yOff = yOff + 26\n",
     "            AmazingHub.db.chatTweaks.altShort = checked and true or false\n"
     "        end\n"
     "    end\n"
     "    yOff = yOff + 26\n"
     "    if AmazingHub.ChatTag then yOff = AmazingHub.ChatTag.BuildSettings(content, yOff) end -- Amazing Hub\n",
     "Settings: what others see in the brackets"),
]

# Patches whose anchor occurs a known number of times: (file, old, new, why, times).
PATCHES_ALL: list[tuple[str, str, str, str, int]] = [
    ("tools/style.lua", "S = load({ db = {} }); S:Resolve()",
     "S = load({ db = { style = \"amazinghub\" } }); S:Resolve()",
     "style test: blocks that check the flat look pick Modern (nothing saved is Classic now)", 3),
]

# Our own hub files: (file in tools/hub-extra, folder in the hub). Appended to the TOC in this order.
EXTRAS = [("PackTweaks.lua", "UI"), ("TableSort.lua", "UI"), ("ChatTag.lua", "UI"), ("WishImport.lua", "UI"), ("LedgerPanel.lua", "UI"), ("SettingsPlus.lua", "UI")]

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
## OptionalDeps: GuildLedger
## X-License: MIT
## X-Category: Guild
## X-Upstream: GuildOS 1.20.1 ({PINNED[:7]}) https://github.com/danielcosta42/GuildOS
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
    if head != PINNED and not any_commit:
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
    # Our own files (tools/hub-extra), loaded last so they can register tabs and replace hub functions.
    toc = out / "AmazingHub.toc"
    toc_text = toc.read_bytes().decode("utf-8").rstrip("\n") + "\n\n# Amazing Forever Guild Pack (tools/hub-extra)\n"
    for name, folder in EXTRAS:
        shutil.copy2(ROOT / "tools" / "hub-extra" / name, out / folder / name)
        toc_text += f"{folder}\\{name}\n"
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
