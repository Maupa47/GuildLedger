----------------------------------------------------------------------
-- Amazing Hub - Slash Commands
-- /amazing and /amazing dispatch table.
----------------------------------------------------------------------

-- Primary slash command: /amazing and /amazing
SLASH_AMAZINGHUB1 = "/amazing"
SLASH_AMAZINGHUB2 = "/amazinghub"


local L = AmazingHub.L

----------------------------------------------------------------------
-- /amazing help listing
--
-- Lives in helpers so the command branch stays a single call. Colour
-- escapes are built here and never stored inside an L[] key, so a
-- translation can never break "|cff......" / "|r".
----------------------------------------------------------------------
local HELP_HEADER_COLOR = "|cff00CCFF"   -- section headers
local HELP_CMD_COLOR    = "|cffFFD700"   -- command verbs (addon gold)

local function helpHeader(text)
    AmazingHub:Print(HELP_HEADER_COLOR .. text .. "|r")
end

local function helpLine(verb, desc)
    AmazingHub:Print("  " .. HELP_CMD_COLOR .. verb .. "|r  " .. desc)
end

local function printHelp()
    AmazingHub:Print(HELP_CMD_COLOR .. L["Amazing Hub commands (/amazing or /amazing):"] .. "|r")

    helpHeader(L["General"])
    helpLine("/amazing",             L["Open Amazing Hub"])
    helpLine("/amazing open <feature>", L["Open a tab (roster, raids, loot, guild...)"])
    helpLine("/amazing find <text>", L["Search members by name, class, level or note"])
    helpLine("/amazing analytics",   L["Guild analytics and activity stats"])
    helpLine("/amazing map",         L["Open the live guild map"])
    helpLine("/amazing style [name]", L["List the interface styles, or switch to one"])
    helpLine("/amazing pug",         L["Check who you're grouped with"])
    helpLine("/amazing calendar",    L["Guild calendar and events"])
    helpLine("/amazing polls",       L["Guild polls"])
    helpLine("/amazing bulletin",    L["Guild bulletin board"])
    helpLine("/amazing bank [sort [all] | stop | sync | need]", L["Guild bank: open, organize the tab, ask for it, what it needs"])
    helpLine("/amazing cta [type] [message]", L["Call to Arms: rally the guild (officers)"])
    helpLine("/amazing ally",        L["Alliance status and allied guilds"])

    helpHeader(L["Raid and loot"])
    if AmazingHub.LootMaster then helpLine("/amazing lm", L["Master Loot helper status"]) end  -- not on retail (ADR-0026)
    if AmazingHub.Points then helpLine("/amazing points", L["Points and DKP window"]) end
    if AmazingHub.TradeCouncil then   -- retail's loot council by trade (issue #185)
        helpLine("/amazing offer [item]", L["Offer a tradeable item to the raid, or open the loot council"])
    end
    if AmazingHub.ConsumableChecker then  -- Anniversary and retail, not Forever (ADR-0014, issue #187)
        helpLine("/amazing cons",      L["Check raid consumables"])
    end
    helpLine("/amazing specs",         L["Scan group talent specs"])
    helpLine("/amazing export <what>", AmazingHub.LootTracker and L["Export roster, attendance or loot"]
        or L["Export roster or attendance"])   -- the loot history is on retail too since issue #183
    if AmazingHub.Companion then helpLine("/amazing web [on|off]", L["Copy your guild into the web companion"]) end
    if AmazingHub.CompanionImport then helpLine("/amazing roster", L["Bring the raid roster in from the website"]) end
    if AmazingHub.RaidStart then   -- issue #400: the Iniciar raide button's next step
        helpLine("/amazing raid start", L["Start the website's raid: invite and arrange, one step a click"])
    end

    helpHeader(L["Personal"])
    helpLine("/amazing avail",         L["List yourself as available for a group"])
    helpLine("/amazing signup <core>", L["Sign up for a raid core"])
    helpLine("/amazing rules",         L["The guild's rules"])
    helpLine("/amazing mentions",      L["Name mention alerts"])
    helpLine("/amazing myalts",        L["Detect and link your own alts"])
    helpLine("/amazing birthday <DD/MM | off>", L["Share your birthday with the guild (day and month only)"])
    if AmazingHub.AttunementTracker then  -- TBC content (ADR-0014)
        helpLine("/amazing attune",    L["Your attunement progress"])
    end
    helpLine("/amazing craft <item>",  L["Who can craft an item"])
    helpLine("/amazing order <item>",  L["Ask the guild's crafters to make an item"])

    helpHeader(L["Diagnostics"])
    helpLine("/amazing sync",     L["Force a full data sync"])
    helpLine("/amazing selftest", L["Run the built-in self test"])
    helpLine("/amazing errors",   L["Show recent errors"])
    helpLine("/amazing perf [reset]", L["Where Amazing Hub spends its time since login, or zero the counters"])
    helpLine("/amazing probe",    L["Record this client's facts for support"])
    helpLine("/amazing probe chat", L["Post two test lines in guild chat to see whether an addon may post on its own"])
    helpLine("/amazing probe channel", L["Join a temporary channel to see whether an addon message may go through one"])
    helpLine("/amazing style preview", L["Show the Forever style's pieces side by side"])
    helpLine("/amazing debug",    L["Toggle debug output"])

    -- These verbs are refused inside their own modules for non-officers, so
    -- showing them to a member would only advertise commands that do nothing.
    if AmazingHub:IsOfficer() then
        helpHeader(L["Officers"])
        helpLine("/amazing ban <name>",            L["Ban a player from invites"])
        helpLine("/amazing tempban <name> <days>", L["Ban a player for a number of days"])
        helpLine("/amazing unban <name>",          L["Lift a ban"])
        helpLine("/amazing banlist",               L["Open the ban list"])
        if AmazingHub.BulkActions then
            helpLine("/amazing bulk [next | skip | stop]", L["Promote, demote or remove by rules, one member per click"])
            helpLine("/amazing altgroup <promote | demote> <name> [rank]",
                L["Promote or demote a member's alts to their main's rank, or to a rank, one per click"])
        end
        helpLine("/amazing altlimit <number>",     L["List the alt groups with more alts than that"])
        helpLine("/amazing birthday <name> <DD/MM | off>", L["Correct or remove a member's birthday"])
        if AmazingHub.NoteDates then
            helpLine("/amazing joindate [<name> | all | import]", L["Write a member's join date into their note, or read the dates already in the notes"])
            helpLine("/amazing safe [<name>]",     L["The safe list: never in a bulk removal or demotion"])
            helpLine("/amazing nick <name> [nickname]", L["The officers' nickname for a member"])
        end
        helpLine("/amazing record <name>",         L["A member's disciplinary record"])
        helpLine("/amazing warn <name> [reason]",  L["Warn a member, with one click"])
        helpLine("/amazing record term <days>",    L["How long a warning counts"])
        helpLine("/amazing autoinvite",            L["Auto-invite settings"])
        helpLine("/amazing note <name> <text>",    L["Add an officer note"])
        if AmazingHub.Wishlist then helpLine("/amazing wish", L["Open the loot wishlist"]) end
        helpLine("/amazing scout",                 L["Scan for unguilded recruits"])
        helpLine("/amazing ally create <tag> <name>", L["Found an alliance with other guilds"])
        helpLine("/amazing ally invite <officer>",    L["Invite a guild into the alliance"])
        helpLine("/amazing ally leave",               L["Leave the alliance"])
    end
end

----------------------------------------------------------------------
-- What a command and a button share (#142): every /amazing command has a way in
-- from the interface too, and both call the one function here, so the button
-- does exactly what the command does.
----------------------------------------------------------------------
function AmazingHub:CollectMyDataNow()
    if not AmazingHub.DataCollector then return end
    AmazingHub.DataCollector:CollectMyData()
    AmazingHub:Print(L["Data collected."])
end

function AmazingHub:MergeRaidSessions()
    if not AmazingHub.RaidTracker then return end
    AmazingHub:Print(L["Merging duplicate raid sessions\226\128\166"])
    if AmazingHub.RaidTracker:MergeDuplicateSessions() == 0 then
        AmazingHub:Print(L["|cffAAAAAA[Amazing Hub] No duplicates found.|r"])
    end
end

-- Start-up problems first: the ring below is capped and shared with runtime
-- errors, so it can already have lost them.
function AmazingHub:ShowErrors()
    local startup = AmazingHub:ListStartupProblems()
    local shown = {}
    if #startup > 0 then
        AmazingHub:Print(string.format(L["%d start-up problem(s):"], #startup))
        for _, line in ipairs(startup) do
            shown[line] = true
            AmazingHub:Print("|cffFF8800" .. line .. "|r")
        end
    end
    -- The ring also holds the start-up problems just listed; skip those.
    local ring, rest = (AmazingHub.State and AmazingHub.State.errors) or {}, {}
    for _, e in ipairs(ring) do
        if not shown[e.msg] then rest[#rest + 1] = e end
    end
    if #rest == 0 then
        if #startup == 0 then AmazingHub:Print(L["No errors recorded this session."]) end
    else
        AmazingHub:Print(string.format(L["%d recent error(s):"], #rest))
        for i = math.max(1, #rest - 9), #rest do
            AmazingHub:Print("|cffFF4444" .. (rest[i].msg or "?") .. "|r")
        end
    end
end

-- Whether this client is the Master Looter, as one line.
function AmazingHub:LootMasterStatus()
    if not AmazingHub.LootMaster then return nil end
    return AmazingHub.LootMaster:IsMasterLooter() and L["Loot Master mode active. Open loot to start."]
        or L["You are not the Master Looter."]
end

-- The string to paste into the web companion, in a popup; or why there is none.
function AmazingHub:ShowWebString()
    local C = AmazingHub.Companion
    if not C then return end
    if not C:IsEnabled() then
        AmazingHub:Print(L["The web companion is off. Turn it on with /amazing web on."])
        return
    end
    local text, countOrErr = C:Build()
    if text then
        AmazingHub:ShowExportPopup(string.format(L["Web Companion (%d members)"], countOrErr), text)
    else
        AmazingHub:Print(L["|cffFF4444Export failed:|r "] .. tostring(countOrErr))
    end
end

-- Every Amazing Hub record of this guild, gone, and the interface reloaded.
function AmazingHub:EraseGuildData()
    if AmazingHub.guildKey and AmazingHubDB then AmazingHubDB[AmazingHub.guildKey] = nil end
    ReloadUI()
end

-- The verbs of what retail does not have (ADR-0026): no Master Loot, and no soft reserves (softres.it
-- runs Classic raids only). Each module is absent, so its verb says so rather than doing nothing or
-- raising. The site's verbs (web, companion, roster) are retail's too since issue #182, equity since
-- issue #183, and points, dkp and wish since issue #185.
local RETAIL_ABSENT = { "^lm$", "^lm%s", "^lootmaster$", "^softres" }

local function absentHere(msg)
    if not AmazingHub.Client.isRetail then return false end
    for _, pat in ipairs(RETAIL_ABSENT) do
        if msg:match(pat) then return true end
    end
    return false
end

local function handleCommand(msg)
    msg = strtrim(msg or "")
    if absentHere(msg) then
        AmazingHub:Print(L["Not available on this client."])
        return
    end
    -- Deliberately the first branch: "help", "?" and "commands" are exact
    -- literals, so this can never swallow another verb, and sitting at the top
    -- means no present or future prefix pattern below can ever swallow them.
    if msg == "help" or msg == "?" or msg == "commands" then
        printHelp()
    elseif msg == "scan" then
        AmazingHub:CollectMyDataNow()
    elseif msg == "selftest" then
        if AmazingHub.SelfTest then AmazingHub.SelfTest:Run() end
    elseif msg == "myalts" then
        if AmazingHub.AltAutoDetect then AmazingHub.AltAutoDetect:PromptNow() end
    elseif msg == "sync" then
        if AmazingHub.CommSystem then
            AmazingHub.CommSystem:FullSync()
        end
    elseif msg == "perf" then
        AmazingHub.Perf:Print()
    elseif msg == "perf reset" then
        AmazingHub.Perf:Reset()
        AmazingHub:Print(L["Performance counters zeroed."])
    elseif msg == "points" or msg == "dkp" then
        if AmazingHub.ShowPointsFrame then
            AmazingHub:ShowPointsFrame()
        end
    elseif msg == "equity" or msg == "lootequity" then
        if AmazingHub.LootEquity then
            AmazingHub.LootEquity:PrintSummary(15)
        end
    elseif msg == "digest" then
        if AmazingHub.Digest then
            AmazingHub.Digest:Show()
        end
    elseif msg == "backup" then
        if AmazingHub.Backup then AmazingHub.Backup:ShowExport() end
    elseif msg == "restore" then
        if AmazingHub.Backup then AmazingHub.Backup:ShowRestore() end
    elseif msg == "bank" or msg:match("^bank%s") then
        -- /amazing bank [sort [all] | stop | sync | need]: the guild bank (issue #380)
        if AmazingHub.GuildBank then
            local a = {}
            for w in msg:gmatch("%S+") do a[#a + 1] = w end
            table.remove(a, 1)
            AmazingHub.GuildBank:HandleCommand(a)
        end
    elseif msg == "rules" then
        -- /amazing rules: the guild's rules, for any member (#407).
        if AmazingHub.GuildRules then AmazingHub.GuildRules:Show() end
    elseif msg == "bulletin" or msg == "board" then
        if AmazingHub.Bulletin then AmazingHub.Bulletin:Show() end
    elseif msg == "cta" or msg:match("^cta%s") then
        -- /amazing cta: the panel. /amazing cta <type> [message]: send it (issue #108).
        local rest = strtrim((msg:gsub("^cta%s*", "")))
        local kind = rest:match("^(%S+)")
        local CTA = AmazingHub.CallToArms
        if not kind then
            AmazingHub.UI:OpenWindow("guild", "cta")
        elseif CTA and CTA:Template(kind:lower()) then
            CTA:Send(kind:lower(), rest:match("^%S+%s+(.+)$"))
        else
            AmazingHub:Print(L["Usage: /amazing cta [worldboss|pvp|defend|event|rally] [message]"])
        end
    elseif msg == "ally" or msg:match("^ally%s") or msg == "alliance" or msg:match("^alliance%s") then
        -- Cross-guild federation. Officer-only verbs refuse inside the module,
        -- so this stays a thin router.
        if AmazingHub.Alliance then
            AmazingHub.Alliance:HandleCommand(msg:match("^%a+%s+(.*)$") or "")
        end
    elseif msg == "analytics" or msg == "stats" then
        if AmazingHub.GuildAnalytics then AmazingHub.GuildAnalytics:Show() end
    elseif msg == "polls" or msg == "poll" then
        if AmazingHub.Polls then AmazingHub.Polls:Show() end
    elseif msg == "calendar" or msg == "cal" or msg == "events" then
        if AmazingHub.ShowCalendar then AmazingHub:ShowCalendar() end
    elseif msg == "search" or msg:match("^find") then
        if AmazingHub.Search then
            local q = strtrim((msg:gsub("^find%s*", "")))
            AmazingHub.Search:Show(q ~= "search" and q or "")
        end
    elseif msg:match("^order") and AmazingHub.ShowCraftOrderDialog then
        -- /amazing order [item link or id] — a craft order (issue #389); no item opens the Orders tab.
        local arg = strtrim((msg:gsub("^order%s*", "")))
        local itemId = tonumber(arg:match("item:(%d+)")) or tonumber(arg:match("^(%d+)$"))
        if itemId then
            AmazingHub:ShowCraftFor(itemId)
        else
            AmazingHub.UI:OpenWindow("recipes", "mine")
        end
    elseif msg:match("^craft") then
        -- /amazing craft <item link or id> — who can craft this, guild + realm.
        local arg = strtrim((msg:gsub("^craft%s*", "")))
        local itemId = tonumber(arg:match("item:(%d+)")) or tonumber(arg:match("^(%d+)$"))
        if not itemId then
            -- No item given: open the Craft Finder popup instead.
            if AmazingHub.ShowCraftFinder then
                AmazingHub:ShowCraftFinder()
            else
                AmazingHub:Print(L["Usage: /amazing craft [item link or id]"])
            end
        else
            local itemName = AmazingHub.Compat.GetItemInfo(itemId) or ("item:" .. itemId)
            local seen = {}
            -- Guild crafters are already known locally (RecipeTracker sync).
            local guild = AmazingHub.RecipeTracker and AmazingHub.RecipeTracker:GetCraftersForItem(itemId)
            if guild and #guild > 0 then
                local names = {}
                for _, c in ipairs(guild) do
                    if not seen[c.playerName] then
                        seen[c.playerName] = true
                        names[#names + 1] = c.playerName
                    end
                end
                AmazingHub:Print(string.format(L["Crafters for %s in guild: %s"], itemName, table.concat(names, ", ")))
            else
                AmazingHub:Print(string.format(L["No guild crafter for %s - asking the realm..."], itemName))
            end
            -- Alliance: straight from the synced directory, offline crafters included.
            if AmazingHub.Alliance and AmazingHub.Alliance:Get() then
                for _, c in ipairs(AmazingHub.Alliance:FindCrafters(itemId)) do
                    if not seen[c.name] then
                        seen[c.name] = true
                        AmazingHub:Print("   " .. string.format(L["%s of %s can craft %s (%s)"],
                            c.name, c.guild, itemName, L[c.prof or "?"])
                            .. (c.online and "" or " " .. L["(offline)"]))
                    end
                end
            end
            -- Realm-wide: answers trickle in over the mesh (out-of-guild reach).
            if AmazingHub.CraftNet then
                AmazingHub.CraftNet:Query(itemId, function(short, label)
                    if seen[short] then return end
                    seen[short] = true
                    AmazingHub:Print("   " .. string.format(L["%s can craft %s (%s)"], short, itemName, L[label or "?"]))
                end)
            end
        end
    elseif msg == "scout" or msg == "recruitscan" then
        -- Officer: /who-scan unguilded candidates, mass-whisper a template.
        if AmazingHub.RecruitScanner then AmazingHub.RecruitScanner:Show() end
    elseif msg == "beacon" or msg == "recruitbeacon" then
        -- Officer: compose/toggle the guild recruitment beacon.
        if AmazingHub.ShowRecruitBeacon then AmazingHub:ShowRecruitBeacon() end
    elseif msg == "lfg" or msg == "recruiting" then
        -- Anyone: browse guilds recruiting nearby. With no guild, on Forever and retail, that is the
        -- guild finder; otherwise the inbox of what was heard over the mesh.
        if IsInGuild() then
            if AmazingHub.ShowRecruitInbox then AmazingHub:ShowRecruitInbox() end
        else
            AmazingHub:OpenGuildFinder()
        end
    elseif msg == "map" or msg == "guildmap" then
        -- Anyone: open the live guild map (world map pins + list overlay).
        if AmazingHub.ToggleGuildMap then AmazingHub:ToggleGuildMap() end
    elseif msg == "pug" then
        -- Anyone: classify the current party/raid against what AmazingHub knows.
        if AmazingHub.TogglePugInspector then AmazingHub:TogglePugInspector() end
    elseif msg == "minimap" then
        if AmazingHub.ToggleMinimapButton then
            local shown = AmazingHub:ToggleMinimapButton()
            AmazingHub:Print(shown and L["Minimap button shown."] or L["Minimap button hidden."])
        end
    elseif msg == "guildbutton" then
        -- Toggle whether the guild micro button / "J" opens Amazing Hub or Blizzard's
        -- guild UI. Lets people keep the modern guild UI and reach Amazing Hub elsewhere.
        local on = not AmazingHub:IsGuildButtonHijacked()
        AmazingHub:SetSetting("hijackGuildButton", on)
        AmazingHub:Print(on and L["Guild button now opens Amazing Hub."]
            or L["Guild button now opens the Blizzard guild UI. Open Amazing Hub from the minimap button."])
    elseif msg == "debug" then
        AmazingHub.Logger.debug = not AmazingHub.Logger.debug
        AmazingHub:Print(AmazingHub.Logger.debug and L["Debug mode ON."] or L["Debug mode OFF."])
    elseif msg == "resscan" then
        -- Diagnostic: run the resistance scan (equipped + bags) and print the max
        -- wearable per school, so the tooltip-based read can be verified in-game.
        local r = AmazingHub.Resistances and AmazingHub.DataCollector and AmazingHub.DataCollector:CollectResistances()
        if not AmazingHub.Resistances then
            AmazingHub:Print(L["Not available on this client."])   -- no resistance gear on retail (#184)
        elseif r then
            AmazingHub:Print(string.format(
                "Resistances (max wearable) - Shadow %d | Nature %d | Frost %d | Fire %d | Arcane %d",
                r.shadow or 0, r.nature or 0, r.frost or 0, r.fire or 0, r.arcane or 0))
        else
            AmazingHub:Print("Resistance scan unavailable.")
        end
    elseif msg == "errors" then
        AmazingHub:ShowErrors()
    elseif msg == "style" or msg:match("^style%s") then
        -- The interface style (#122): list, switch, or show the Forever pieces side by side.
        local arg = strtrim((msg:gsub("^style%s*", ""))):lower()
        if arg == "" then
            AmazingHub.Style:PrintList()
        elseif arg == "preview" then
            AmazingHub.Style:ShowPreview()
        else
            AmazingHub.Style:Apply(arg)
        end
    elseif msg == "probe" then
        -- Client facts for the WoW: Forever beta, into AmazingHubDB.probe (ADR-0015).
        if AmazingHub.Probe then AmazingHub.Probe:Run() end
    elseif msg == "probe chat" then
        -- Whether chat from a timer gets through, measured (issue #75).
        if AmazingHub.Probe then AmazingHub.Probe:RunChat() end
    elseif msg == "probe channel" then
        -- Whether an addon message may go through a created channel, measured (specs/071-o-recrutamento).
        if AmazingHub.Probe then AmazingHub.Probe:RunChannel() end
    elseif msg == "reset" then
        AmazingHub:EraseGuildData()
    elseif msg:match("^recruit") then
        local rest = msg:gsub("^recruit%s*", "")
        local args = {}
        for word in rest:gmatch("%S+") do
            table.insert(args, word)
        end
        if AmazingHub.Recruitment then
            AmazingHub.Recruitment:HandleCommand(args)
        end
    elseif msg == "consumables" or msg == "cons" then
        if AmazingHub.ConsumableChecker then
            local results = AmazingHub.ConsumableChecker:CheckRaid()
            if results then
                local missing = AmazingHub.ConsumableChecker:GetMissingCount(results)
                AmazingHub:Print(string.format(L["Consumable check done. %d players missing buffs."], missing))
                -- Retail: what the client could not read is said apart, never counted as missing (#187).
                local unknown = AmazingHub.ConsumableChecker:GetUnknownCount(results)
                if unknown > 0 then
                    AmazingHub:Print(string.format(L["%d could not be read (out of range, or hidden by the game)."], unknown))
                end
            end
        else
            AmazingHub:Print(L["Not available on this client."])
        end
    elseif msg == "consreport" then
        if AmazingHub.ConsumableChecker then
            AmazingHub.ConsumableChecker:ReportToChat("RAID")
        else
            AmazingHub:Print(L["Not available on this client."])
        end
    elseif msg:match("^trial") then
        -- The roster's key, so a guildmate on a connected realm is found as the roster menu finds
        -- them: the whole rest when it is somebody (two words on Forever), else the first word, as
        -- it always was (issue #177).
        local rest = strtrim((msg:gsub("^trial%s*", "")))
        local key = AmazingHub:RosterKey(rest)
        local name = rest:match("^(%S+)")
        if not key and name then key = AmazingHub:RosterKey(name) or AmazingHub:GetPlayerKey(name) end
        if key and AmazingHub.TrialTracker then
            AmazingHub.TrialTracker:AddTrial(key)
        else
            AmazingHub:Print(L["Usage: /amazing trial <PlayerName>"])
        end
    elseif msg == "note" or msg:match("^note%s") then
        local rest = msg:gsub("^note%s*", "")
        -- A Forever name is two words, and the note lands on the key the roster gives (issue #49).
        local target, noteText = AmazingHub:SplitNameAndText(rest)
        if target and noteText and AmazingHub.OfficerNotes then
            local key = AmazingHub:RosterKey(target)
            -- Somebody off the roster still gets the note (the PUG inspector reads them), but
            -- the officer is told: "Lethaniel" on Forever is nobody's sheet.
            if AmazingHub.OfficerNotes:AddNote(key or AmazingHub:GetPlayerKey(target), noteText) then
                AmazingHub:Print(key and (L["Note added for "] .. target)
                    or string.format(L["Note added for %s, who matches no single guild member: check the full name."], target))
            end
        else
            AmazingHub:Print(L["Usage: /amazing note <PlayerName> <text>"])
        end
    elseif msg == "offer" or msg:match("^offer%s") then
        -- /amazing offer [item link]: retail's loot council by trade (issue #185); the link keeps its case.
        local link = strtrim((msg:gsub("^offer%s*", "")))
        if not AmazingHub.TradeCouncil then
            AmazingHub:Print(L["Not available on this client."])
        elseif link == "" then
            AmazingHub:ShowTradeCouncil()
        else
            AmazingHub.TradeCouncil:Offer(link)
        end
    elseif msg == "lm undo" then
        -- /amazing lm undo - take the last award back (issue #294), as the Master Loot window's button
        if AmazingHub.LootMaster then
            local award, why = AmazingHub.LootMaster:UndoLastAward()
            AmazingHub:Print(award and string.format(L["|cffFFD700Undone:|r %s"], award.link) or why)
        end
    elseif msg == "lm" or msg == "lootmaster" then
        local status = AmazingHub:LootMasterStatus()
        if status then AmazingHub:Print(status) end
    elseif msg:match("^lm announce") then
        -- /amazing lm announce - manually announce item from target tooltip
        AmazingHub:Print(L["Open loot window as Master Looter to announce items."])
    elseif msg:match("^web") or msg:match("^companion") then
        -- /amazing web [on|off] - the string you paste into the web companion.
        local C = AmazingHub.Companion
        local arg = C and msg:match("^%S+%s+(%S+)")
        if C and (arg == "on" or arg == "off") then
            C:SetEnabled(arg == "on")
            AmazingHub:Print(arg == "on" and L["Web companion enabled."] or L["Web companion disabled."])
        else
            AmazingHub:ShowWebString()
        end
    elseif msg:match("^roster") then
        -- /amazing roster [invite|groups|trim] — the roster the website planned: the raid of the window when
        -- there is one (issue #400), as the Web tab's buttons.
        local I = AmazingHub.CompanionImport
        local sub = I and msg:match("^roster%s+(%S+)")
        if not I then
            AmazingHub:Print(L["|cffFF4444Export failed:|r "] .. "CompanionImport")
        elseif sub == "invite" then
            local n, here, err, offline = I:InviteAll()
            if err then AmazingHub:Print(err)
            else AmazingHub:Print(string.format(L["Invited %d, already here %d."], n, here)) end
            local off = I.OfflineLine(offline)
            if off then AmazingHub:Print(off) end
        elseif sub == "groups" then
            local moved, err = I:OrganizeGroups()
            if err then AmazingHub:Print(err)
            else AmazingHub:Print(string.format(L["Moved %d into their groups."], moved)) end
        elseif sub == "trim" then
            -- Out of the group whoever is not in the plan, after asking (issue #292).
            I:AskTrim()
        elseif sub == "plan" and AmazingHub.RaidPlan then
            -- The night's notes, tasks and loot rules from the site (issue #296).
            AmazingHub.RaidPlan:Show()
        else
            AmazingHub:ShowImportPopup()
        end
    elseif msg == "raid start" then
        -- /amazing raid start — one step of the Iniciar raide button, as its click (issue #400): typed, it is a key
        -- press, which WoW: Forever lets an invite out of. On the raid near now (ButtonRaid: the site's, or one pasted
        -- by hand), never a kept raid days away; with none, it says no raid starts around this time. The line it
        -- prints starts with the raid's name.
        local I, RS = AmazingHub.CompanionImport, AmazingHub.RaidStart
        if I and RS then RS:Click(I:ButtonRaid(), true) end
    elseif msg == "exportatt" or msg == "exportattendance" then
        if AmazingHub.RaidTracker then
            local json, err = AmazingHub.RaidTracker:ExportForTMB()
            if json then
                AmazingHub:ShowExportPopup(L["Attendance Export"], json)
            else
                AmazingHub:Print(L["|cffFF4444Export failed:|r "] .. (err or L["unknown error"]))
            end
        end
    elseif msg:match("^export") then
        -- /amazing export <roster|attendance|loot|readiness|standings|equity> [csv|tsv|discord]
        local rest = strtrim((msg:gsub("^export%s*", "")))
        local dataset, fmt = rest:match("^(%S*)%s*(%S*)$")
        dataset = (dataset and dataset ~= "") and dataset or "roster"
        fmt = (fmt and fmt ~= "") and fmt or "csv"
        local text, title = nil, nil
        if AmazingHub.Exporter then
            text, title = AmazingHub.Exporter:Build(dataset, fmt)
        end
        if text then
            AmazingHub:ShowExportPopup(string.format("%s (%s)", title or L["Export"], fmt), text)
        elseif title == "absent" then
            AmazingHub:Print(L["Not available on this client."])
        elseif title == "officer" then
            AmazingHub:Print(L["|cffFF4444Officers only.|r"])
        elseif AmazingHub.Exporter then
            AmazingHub:Print(string.format(L["Usage: /amazing export <%s> [csv|tsv|discord]"], AmazingHub.Exporter:Names()))
        end
    elseif msg:match("^wish") then
        if not AmazingHub:IsOfficer() then
            AmazingHub:Print(L["|cffFF4444Wishlist is currently available to officers only.|r"])
            return
        end
        local rest = strtrim((msg:gsub("^wish%s*", "")))
        if rest == "" or rest == "list" then
            -- Show wishlist frame
            AmazingHub:ShowWishlistFrame()
        elseif rest:match("^remove%s+") then
            local link = rest:match("^remove%s+(.+)$")
            local itemId = link and tonumber(link:match("item:(%d+)"))
            if itemId and AmazingHub.Wishlist then
                AmazingHub.Wishlist:RemoveFromWishlist(itemId)
            else
                AmazingHub:Print(L["Usage: /amazing wish remove [itemlink]"])
            end
        else
            -- Treat remainder as an item link to add
            local itemId = tonumber(rest:match("item:(%d+)"))
            if itemId and AmazingHub.Wishlist then
                AmazingHub.Wishlist:AddToWishlist(itemId, rest, false)
            else
                AmazingHub:Print(L["Usage: /amazing wish [itemlink] | /amazing wish remove [itemlink]"])
            end
        end
    elseif msg == "mergeraids" then
        AmazingHub:MergeRaidSessions()
    elseif msg == "specs" then
        if AmazingHub.SpecChecker then
            AmazingHub.SpecChecker:ScanGroup()
        end
    elseif msg == "attune" or msg == "attunements" then
        -- Print attunement status for the logged-in character to chat.
        if AmazingHub.AttunementTracker then
            local atts = AmazingHub.AttunementTracker:ScanAttunements()
            AmazingHub:Print(L["|cffFFD700Attunements:|r"])
            for _, att in ipairs(atts) do
                if not att.alwaysComplete then
                    local status
                    if att.complete then
                        status = L["|cff00FF00Done|r"]
                    elseif att.progress and att.progress > 0 then
                        status = format("|cffFFD700%d%%|r", math.floor(att.progress * 100))
                    else
                        status = L["|cffFF4444Not started|r"]
                    end
                    AmazingHub:Print(format("  [%s] %s \226\128\148 %s", att.tier, att.name, status))
                end
            end
        else
            AmazingHub:Print(L["Not available on this client."])
        end
    elseif msg == "attune debug" or msg == "attunements debug" then
        -- Debug mode: prints per-quest IsQuestFlaggedCompleted results.
        if AmazingHub.AttunementTracker then
            AmazingHub:Print("|cffFFD700Attunement debug (per quest):|r")
            for _, attDef in ipairs(AmazingHub.AttunementTracker.ATTUNEMENTS) do
                if not attDef.alwaysComplete and attDef.finalQuestId then
                    AmazingHub:Print(format("|cffAAAAAA--- %s (final=%d) ---|r", attDef.name, attDef.finalQuestId))
                    for _, q in ipairs(attDef.quests) do
                        if q.ids then
                            local anyDone = false
                            for _, qid in ipairs(q.ids) do
                                if AmazingHub.AttunementTracker:IsQuestComplete(qid) then anyDone = true end
                            end
                            local col = anyDone and "|cff00FF00" or "|cffFF4444"
                            local ids = table.concat(q.ids, "/")
                            AmazingHub:Print(format("  %s[%s] %s (Aldor|Scryers)|r", col, ids, q.name))
                        else
                            local done = AmazingHub.AttunementTracker:IsQuestComplete(q.id)
                            local col = done and "|cff00FF00" or "|cffFF4444"
                            AmazingHub:Print(format("  %s[%d] %s|r", col, q.id, q.name))
                        end
                    end
                    if attDef.keyItemId then
                        local count = AmazingHub.Compat.GetItemCount(attDef.keyItemId) or 0
                        local col = count > 0 and "|cff00FF00" or "|cffFF4444"
                        AmazingHub:Print(format("  %sKey item %d: %d in bags|r", col, attDef.keyItemId, count))
                    end
                end
            end
        else
            AmazingHub:Print(L["Not available on this client."])
        end
    elseif msg == "attune dumpquests" and not AmazingHub.AttunementTracker then
        AmazingHub:Print(L["Not available on this client."])   -- TBC's attunement quests (issue #184)
    elseif msg == "attune dumpquests" then
        -- Dumps all completed quest IDs in the TBC attunement range.
        -- Covers T4/T5/T6 + some headroom for anniversary-specific hidden flags.
        AmazingHub:Print("|cffFFD700Completed quests in range 9800-11500:|r")
        local found = 0
        for qid = 9800, 11500 do
            -- Compat, not the tracker: the tracker does not exist outside TBC Anniversary.
            if AmazingHub.Compat.IsQuestComplete(qid) then
                -- Try to get the quest title (may be nil for hidden server-side quests)
                local title = nil
                if C_QuestLog and C_QuestLog.GetTitleForQuestID then
                    title = C_QuestLog.GetTitleForQuestID(qid)
                end
                if title and title ~= "" then
                    AmazingHub:Print(format("  |cff00FF00[%d]|r %s", qid, title))
                else
                    AmazingHub:Print(format("  |cff00FF00[%d]|r |cffAAAAAA(no title \226\128\148 hidden/anniversary quest)|r", qid))
                end
                found = found + 1
            end
        end
        if found == 0 then
            AmazingHub:Print("|cffFF4444No completed quests found in that range.|r")
        else
            AmazingHub:Print(format("|cffAAAAAA%d quests found. Run on main to compare IDs.|r", found))
        end
    elseif msg:match("^signup") then
        -- /amazing signup <CoreName> [tank|healer|melee|ranged] [note]
        local rest     = strtrim((msg:gsub("^signup%s*", "")))
        local coreName = rest:match("^(%S+)")
        local note     = rest:match("^%S+%s+(.+)$") or ""
        -- A role word right after the core is the role (issue #94); one the class cannot play
        -- falls back to the class's own in BroadcastSignup.
        local word = note:match("^(%S+)")
        local role = word and AmazingHub.CoreManager and AmazingHub.CoreManager.ROLE_WORDS[word:lower()]
        if role then note = note:match("^%S+%s+(.+)$") or "" end
        if (not coreName or coreName == "") and AmazingHub.ShowCoreSignupFrame then
            -- The window, as the Raids tab's button opens it: the way in at any width, and with the
            -- Raids tab switched off (#377).
            AmazingHub:ShowCoreSignupFrame()
        elseif not coreName or coreName == "" then
            AmazingHub:Print(L["Usage: /amazing signup <CoreName> [tank|healer|melee|ranged] [note]"])
        elseif not AmazingHub.CoreManager then
            AmazingHub:Print(L["Core Manager not loaded."])
        elseif not AmazingHub.CoreManager:Exists(coreName) then
            AmazingHub:Print(string.format(L["Core \"%s\" not found."], coreName))
        else
            AmazingHub.CoreManager:BroadcastSignup(coreName, note, role)
            AmazingHub:Print(string.format(L["Sign-up sent for core: %s"], coreName))
        end
    elseif msg:match("^unsignup") then
        -- /amazing unsignup <CoreName>  — withdraw your own application
        local coreName = strtrim((msg:gsub("^unsignup%s*", "")))
        if coreName == "" then
            AmazingHub:Print(L["Usage: /amazing unsignup <CoreName>"])
        elseif AmazingHub.CoreManager then
            local playerKey = AmazingHub:GetPlayerKey(AmazingHub.Compat.PlayerName(), GetRealmName())
            AmazingHub.CoreManager:DeclineSignup(playerKey, coreName)
            AmazingHub:Print(string.format(L["Sign-up withdrawn from core: %s"], coreName))
        end
    elseif msg:match("^tempban%s") then
        -- /amazing tempban <name> <days> [reason]  — officer-gated inside BanList:Add.
        local rest = strtrim((msg:gsub("^tempban%s+", "")))
        local name, days, reason = rest:match("^(%S+)%s+(%d+)%s*(.*)$")
        local numDays = days and tonumber(days)
        if name and numDays and numDays > 0 then
            if AmazingHub.BanList and AmazingHub.BanList:Add(name, reason, numDays * 86400) then
                AmazingHub:Print(L["Temp-banned "] .. name .. " (" .. days .. L[" days)"])
            end
        else
            AmazingHub:Print(L["Usage: /amazing tempban <name> <days> [reason]"])
        end
    elseif msg:match("^ban%s") then
        -- /amazing ban <name> [reason]  — officer-gated inside BanList:Add.
        local rest = strtrim((msg:gsub("^ban%s+", "")))
        local name, reason = rest:match("^(%S+)%s*(.*)$")
        if name then
            if AmazingHub.BanList and AmazingHub.BanList:Add(name, reason) then
                AmazingHub:Print(L["Banned "] .. name)
            end
        else
            AmazingHub:Print(L["Usage: /amazing ban <name> [reason]"])
        end
    elseif msg:match("^unban%s") then
        -- /amazing unban <name>  — officer-gated inside BanList:Remove.
        local name = strtrim((msg:gsub("^unban%s+", "")))
        if name ~= "" and AmazingHub.BanList and AmazingHub.BanList:Remove(name) then
            AmazingHub:Print(L["Unbanned "] .. name)
        elseif name ~= "" and AmazingHub.BanList and AmazingHub:IsOfficer() then
            AmazingHub:Print(string.format(L["No ban to lift for %s."], name))   -- nothing stood there (#184)
        end
    elseif msg:match("^warn%s") then
        -- /amazing warn <name> [reason]  — the Warn window (#403), officers only.
        local name, rest = AmazingHub:SplitNameAndText(strtrim((msg:gsub("^warn%s+", ""))))
        name = name or strtrim((msg:gsub("^warn%s+", "")))
        local key = AmazingHub:RosterKey(name)
        if not AmazingHub:IsOfficer() then
            AmazingHub:Print(L["|cffFF4444Officers only.|r"])
        elseif not key then
            AmazingHub:Print(string.format(L["%s is not on the guild roster."], name))
        else
            local _, shown = AmazingHub:RosterKey(name)
            AmazingHub:ShowWarnDialog(key, shown, { reason = rest and strtrim(rest):lower() or nil })
        end
    elseif msg:match("^record%s+term%s") then
        -- /amazing record term <days>  — the guild's term for warnings (#402), officers only.
        local days = strtrim((msg:gsub("^record%s+term%s+", "")))
        local ok, why = false, "range"
        if AmazingHub.Discipline then ok, why = AmazingHub.Discipline:SetTerm(days) end
        if ok then
            AmazingHub:Print(string.format(L["Warnings now count for %d days."], AmazingHub.Discipline:GetTerm()))
        elseif why == "officer" then
            AmazingHub:Print(L["|cffFF4444Officers only.|r"])
        else
            AmazingHub:Print(L["Usage: /amazing record term <1-365>"])
        end
    elseif msg:match("^record%s") then
        -- /amazing record <name>  — a member's disciplinary record (#402), officers only.
        local name = strtrim((msg:gsub("^record%s+", "")))
        local D = AmazingHub.Discipline
        if not (D and AmazingHub:IsOfficer()) then
            AmazingHub:Print(L["|cffFF4444Officers only.|r"])
        elseif name == "" then
            AmazingHub:Print(L["Usage: /amazing record <name>"])
        else
            local key = AmazingHub:RosterKey(name) or AmazingHub:GetPlayerKey(name)
            local now, term = GetServerTime(), D:GetTerm()
            local record = D:Record(key)
            AmazingHub:Print(string.format(L["%s: step %d, %d warning(s)."], name, D.Step(record, term, now), #record))
            for i = 1, math.min(5, #record) do
                local w = record[i]
                local state = w.revokedAt and L["revoked"] or (D.Active(w, term, now) and L["standing"] or L["lapsed"])
                AmazingHub:Print(string.format("  %s  %s  %s (%s)", AmazingHub:DateText(w.at or 0), D.ReasonText(w.reason), state, w.by or "?"))
            end
        end
    elseif msg == "bulk" or msg:match("^bulk%s") then
        -- /amazing bulk [next | skip | stop] — Leadership > Bulk actions (#420). A typed command is addon code, which may
        -- not run the game's protected rank commands: `next` says who is next; the Next button or a
        -- /click AmazingHubBulkNext macro acts.
        if AmazingHub.BulkActions and AmazingHubDevFeatures then -- Amazing Hub: developers only
            AmazingHub.BulkActions:Command((msg:gsub("^bulk%s*", "")))
        else
            AmazingHub:Print(L["Not available on this client."])
        end
    elseif msg == "altgroup" or msg:match("^altgroup%s") then
        -- /amazing altgroup <promote | demote> <name> [rank] (#424): a queue in Leadership > Bulk actions, one alt per click.
        if AmazingHub.BulkActions and AmazingHubDevFeatures then -- Amazing Hub: developers only
            AmazingHub.BulkActions:CommandGroup((msg:gsub("^altgroup%s*", "")))
        else
            AmazingHub:Print(L["Not available on this client."])
        end
    elseif msg == "birthday" or msg:match("^birthday%s") or msg == "aniversario" or msg:match("^aniversario%s") then
        -- /amazing birthday [DD/MM | off] (#428), Settings > Profile's Birthday; an officer adds a name first.
        if AmazingHub.Birthdays then AmazingHub.Birthdays:Command((msg:gsub("^%a+%s*", ""))) end
    elseif msg == "joindate" or msg:match("^joindate%s") then
        -- /amazing joindate [<name> | all | import] (#429): Leadership > Notes and marks.
        if AmazingHub.NoteDates then AmazingHub.NoteDates:Command((msg:gsub("^joindate%s*", ""))) end
    elseif msg == "safe" or msg:match("^safe%s") then
        -- /amazing safe [<name>] (#429): the safe list the bulk actions never remove or demote.
        if AmazingHub.MemberMarks then AmazingHub.MemberMarks:CommandSafe((msg:gsub("^safe%s*", ""))) end
    elseif msg == "nick" or msg:match("^nick%s") then
        -- /amazing nick <name> [nickname] (#429): the officers' nickname, on the tooltip and in chat.
        if AmazingHub.MemberMarks then AmazingHub.MemberMarks:CommandNick((msg:gsub("^nick%s*", ""))) end
    elseif msg == "altlimit" or msg:match("^altlimit%s") then
        -- /amazing altlimit N (#424): the groups with more than N alts, in chat.
        if AmazingHub.AltSync then AmazingHub.AltSync:CommandLimit((msg:gsub("^altlimit%s*", ""))) end
    elseif msg == "banlist" then
        AmazingHub.UI:OpenWindow("management", "ban")
    elseif msg == "autoinvite" or msg:match("^autoinvite%s") or msg == "ai" or msg:match("^ai%s") then
        if AmazingHub.Recruitment then
            local rest = strtrim((msg:gsub("^ai%s*", ""):gsub("^autoinvite%s*", "")))
            local a = {}
            for w in rest:gmatch("%S+") do a[#a + 1] = w end
            AmazingHub.Recruitment:HandleAutoInviteCommand(a)
        end
    elseif msg == "mentions" or msg:match("^mentions%s") then
        if AmazingHub.Mentions then
            local rest = strtrim((msg:gsub("^mentions%s*", "")))
            local a = {}
            for w in rest:gmatch("%S+") do a[#a + 1] = w end
            AmazingHub.Mentions:HandleCommand(a)
        end
    elseif msg == "notecmd" or msg:match("^notecmd%s") then
        if AmazingHub.NoteCommand then
            local rest = strtrim((msg:gsub("^notecmd%s*", "")))
            local a = {}; for w in rest:gmatch("%S+") do a[#a+1] = w end
            AmazingHub.NoteCommand:HandleCommand(a)
        end
    elseif msg == "avail" or msg:match("^avail%s") then
        -- /amazing avail [off | notify [on|off] | [tank|healer|dps|any] <text>]
        -- Anchored on "^avail%s" so it can never swallow a sibling verb.
        -- (/amazing lfg is already the recruitment beacon inbox, hence "avail".)
        if AmazingHub.LFGBoard then
            -- gsub returns (string, count); the extra parens drop the count so it
            -- cannot reach strtrim's optional "characters to trim" argument. The
            -- note here is free text, so "avail 10 man" must not lose its "1".
            local rest = strtrim((msg:gsub("^avail%s*", "")))
            local a = {}; for w in rest:gmatch("%S+") do a[#a+1] = w end
            AmazingHub.LFGBoard:HandleCommand(a, rest)
        end
    elseif msg == "open" or msg:match("^open%s") then
        -- /amazing open <feature> [sub] — one uniform way to open any feature
        -- tab. A dedicated verb rather than a bare-id fallback: several
        -- feature ids (roster, trials, dkp, alliance) are already verbs
        -- above, and "^trial" would even prefix-match "trials" and eat the
        -- "s" as a player name. "open" itself is not a prefix of, nor
        -- prefixed by, any other verb in this chain.
        local id  = msg:match("^open%s+(%S+)")
        local sub = msg:match("^open%s+%S+%s+(%S+)")
        local def = id and AmazingHub.UI and AmazingHub.UI.GetFeature and AmazingHub.UI:GetFeature(id)
        if def and (def.tab or def.opens) then
            AmazingHub.UI:OpenWindow(id, sub)
        else
            AmazingHub:Print(L["Usage: /amazing open <feature>. Try /amazing open roster."])
        end
    else
        -- Unknown verb: point at the listing, then keep the historic
        -- behaviour of opening the roster. A bare /amazing is the documented way
        -- to open the roster and is not a typo, so it stays silent.
        if msg ~= "" then
            AmazingHub:Print(string.format(L["Unknown command. Type %s for the list."], "|cffFFD700/gos help|r"))
        end
        AmazingHub:ToggleRoster()
    end
end

-- Dispatch: /amazing and /amazing (primary)
SlashCmdList["AMAZINGHUB"] = handleCommand

