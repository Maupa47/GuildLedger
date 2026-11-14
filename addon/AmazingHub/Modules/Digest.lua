----------------------------------------------------------------------
-- Amazing Hub - Login Digest
-- "Since your last login: N new members, X items looted, ..." — a quick
-- catch-up shown once on login (and on demand via /amazing digest).
-- Build() is pure data; the popup uses the UI factories at runtime.
----------------------------------------------------------------------
local Digest = {}
AmazingHub.Digest = Digest
local L = AmazingHub.L

local FEED_LINES = 5             -- lines from the guild website in one digest
local FEED_SEEN_S = 14 * 86400   -- how long a line shown is remembered: the site sends a week of them

function Digest:Initialize()
    AmazingHub.db.digest = AmazingHub.db.digest or {}
    if AmazingHub.db.digest.enabled == nil then AmazingHub.db.digest.enabled = true end
    if AmazingHub.db.digest.lastSeen == nil then AmazingHub.db.digest.lastSeen = 0 end
    AmazingHub.db.digest.feedSeen = AmazingHub.db.digest.feedSeen or {}
end

-- What the guild website said that this client has not shown yet (amazinghub-web #259), the newest first, and
-- what the block as a whole tells: an event the site says is not said again by this client's own lines.
local function fromSite()
    local seen = AmazingHub.db.digest and AmazingHub.db.digest.feedSeen or {}
    local unseen, told = {}, {}
    for _, item in ipairs(AmazingHub.CompanionImport and AmazingHub.CompanionImport:FeedLines() or {}) do
        told[item.type] = true
        told[item.type .. "|" .. item.at] = true
        if item.key then told[item.type .. "|" .. item.key] = true end
        if not seen[item.id] and #unseen < FEED_LINES then unseen[#unseen + 1] = item end
    end
    return unseen, told
end

local function myKey()
    return AmazingHub:GetPlayerKey(AmazingHub.Compat.PlayerName(), GetRealmName())
end

----------------------------------------------------------------------
-- Build the digest lines for everything that changed since `since`
-- (a server timestamp). Returns an array of strings.
----------------------------------------------------------------------
function Digest:Build(since)
    since = since or AmazingHub.db.digest.lastSeen or 0
    local lines = {}
    local feed, told = fromSite()

    -- New members (first observed by Amazing Hub since last login, after its first look at the guild)
    local newCount, newNames = 0, {}
    local newSince = math.max(since, AmazingHub.db.firstSeenSince or 0)
    for key, ts in pairs(AmazingHub.db.firstSeen or {}) do
        if ts and ts > newSince then
            newCount = newCount + 1
            if #newNames < 3 then newNames[#newNames + 1] = key:match("^([^-]+)") or key end
        end
    end
    if newCount > 0 then
        local names = table.concat(newNames, ", ")
        if newCount > #newNames then names = names .. " +" .. (newCount - #newNames) end
        lines[#lines + 1] = string.format(L["%d new member(s): %s"], newCount, names)
    end

    -- Roster changes since last login (from the audit log)
    if AmazingHub.RosterLog then
        local c = AmazingHub.RosterLog:CountsSince(since)
        if c.kick > 0 then lines[#lines + 1] = string.format(L["%d member(s) removed"], c.kick) end
        if c.leave > 0 then lines[#lines + 1] = string.format(L["%d member(s) left"], c.leave) end
    end

    -- Raid sessions tracked since last login
    local raidCount = 0
    if AmazingHub.db.raidTracker and AmazingHub.db.raidTracker.sessions then
        for _, s in pairs(AmazingHub.db.raidTracker.sessions) do
            if s.startTime and s.startTime > since then raidCount = raidCount + 1 end
        end
    end
    if raidCount > 0 then
        lines[#lines + 1] = string.format(L["%d raid session(s) tracked"], raidCount)
    end

    -- Loot recorded since last login
    local lootCount = 0
    for _, e in ipairs(AmazingHub.db.lootHistory or {}) do
        if (e.timestamp or 0) > since then lootCount = lootCount + 1 end
    end
    if lootCount > 0 then
        lines[#lines + 1] = string.format(L["%d item(s) looted"], lootCount)
    end

    -- Your own points change since last login
    if AmazingHub.Points and AmazingHub.db.points and AmazingHub.db.points.log then
        local mk = myKey()
        local delta = 0
        for _, e in ipairs(AmazingHub.db.points.log) do
            if e.key == mk and (e.ts or 0) > since then delta = delta + (e.delta or 0) end
        end
        if delta ~= 0 then
            lines[#lines + 1] = string.format(L["Your points changed by %+d (now %d)"], delta, AmazingHub.Points:Get(mk))
        end
    end

    -- Milestones & guild anniversaries
    if AmazingHub.Milestones then
        for _, line in ipairs(AmazingHub.Milestones:GetDigestLines(since, told)) do
            lines[#lines + 1] = line
        end
    end
    -- WoW: Forever's founding: who joined as a founder, the window, the guild's anniversaries (#209)
    if AmazingHub.Founding then
        for _, line in ipairs(AmazingHub.Founding:GetDigestLines(since, GetServerTime(), told)) do
            lines[#lines + 1] = line
        end
    end

    -- Upcoming raid reminder (event within the next 24h)
    if AmazingHub.Calendar and AmazingHub.Calendar.GetDigestLines then
        local calLines = AmazingHub.Calendar:GetDigestLines()
        if calLines then
            for _, line in ipairs(calLines) do
                lines[#lines + 1] = "|cff4CB8FF" .. line .. "|r"
            end
        end
    end

    -- Alliance: how many allied raids are coming up in the next week. One line,
    -- and only when this guild is federated and something is actually scheduled.
    if AmazingHub.Alliance and AmazingHub.Alliance:Get() and AmazingHub.Calendar
        and AmazingHub.Calendar.AllianceEvents then
        local horizon = GetServerTime() + (7 * 86400)
        local count = 0
        for _, e in ipairs(AmazingHub.Calendar:AllianceEvents()) do
            if (tonumber(e.when) or 0) <= horizon then
                count = count + 1
            end
        end
        if count > 0 then
            local gold = AmazingHub.Colors.gold
            lines[#lines + 1] = string.format("|cff%02x%02x%02x", gold.r * 255, gold.g * 255, gold.b * 255) ..
                string.format(L["%d allied event(s) this week"], count) .. "|r"
        end
    end

    -- New bulletin notices (most recent few)
    if AmazingHub.Bulletin then
        local shown = 0
        for _, m in ipairs(AmazingHub.Bulletin:GetMessages()) do
            if (m.ts or 0) > since and shown < 3 then
                lines[#lines + 1] = "|cffEDCC7B" .. L["Notice:"] .. "|r " .. (m.text or "")
                shown = shown + 1
            end
        end
    end

    -- New polls opened since last login
    if AmazingHub.Polls then
        local newPolls = 0
        for _, p in pairs(AmazingHub.Polls:GetList()) do
            if not p.closed and (p.ts or 0) > since then newPolls = newPolls + 1 end
        end
        if newPolls > 0 then
            lines[#lines + 1] = string.format(L["%d new poll(s) — cast your vote"], newPolls)
        end
    end

    -- Officer-only catch-up
    if AmazingHub:IsOfficer() then
        if AmazingHub.TrialTracker then
            -- Ready to review: their end, from the guild's length, has passed with no decision (#249).
            local due = AmazingHub.TrialTracker:CountReady()
            if due > 0 then
                lines[#lines + 1] = string.format(L["%d trial(s) ready for decision"], due)
            end
        end
        if AmazingHub.GuildManager and AmazingHub.GuildManager.GetInactiveMembers then
            local inactive = AmazingHub.GuildManager:GetInactiveMembers(AmazingHub.GuildManager.DEFAULT_INACTIVE_DAYS)
            if inactive and #inactive > 0 then
                lines[#lines + 1] = string.format(L["%d inactive member(s)"], #inactive)
            end
        end
    end

    -- WoW: Forever: what the guild earned (#216), and the officers' reminder of its setup (#217)
    if AmazingHub.Achievements then
        for _, line in ipairs(AmazingHub.Achievements:GetDigestLines(told)) do
            lines[#lines + 1] = line
        end
    end
    local setup = AmazingHub.Activation and AmazingHub.Activation:GetDigestLine(GetServerTime())
    if setup then lines[#lines + 1] = setup end
    -- Beside other news, never a reason to open the digest on its own at every login.
    local nearest = AmazingHub.Achievements and AmazingHub.Achievements:NextLine()
    if nearest and (#lines > 0 or #feed > 0) then lines[#lines + 1] = nearest end

    if #feed > 0 then
        lines[#lines + 1] = "|cffEDCC7B" .. L["From the guild website"] .. "|r"
        for _, item in ipairs(feed) do lines[#lines + 1] = item.text end
    end

    return lines
end

-- The login digest showed these: they are not shown again, and what is too old to come back is forgotten.
function Digest:MarkFeedSeen(now)
    local seen = AmazingHub.db.digest.feedSeen
    for _, item in ipairs((fromSite())) do seen[item.id] = now end
    for id, at in pairs(seen) do
        if now - at > FEED_SEEN_S then seen[id] = nil end
    end
end

----------------------------------------------------------------------
-- The popup window.
----------------------------------------------------------------------
function Digest:Show(lines)
    local UI = AmazingHub.UI
    local C = AmazingHub.Colors
    lines = lines or self:Build()

    local f = self.frame
    if not f then
        f = CreateFrame("Frame", "AmazingHubDigestFrame", UIParent, "BackdropTemplate")
        f:SetSize(360, 280)
        f:SetPoint("TOP", UIParent, "TOP", 0, -140)
        f:SetBackdrop({ bgFile = "Interface\\Buttons\\WHITE8x8", edgeFile = "Interface\\Buttons\\WHITE8x8", edgeSize = 1 })
        f:SetBackdropColor(0.058, 0.058, 0.075, 0.98)
        f:SetBackdropBorderColor(C.border.r, C.border.g, C.border.b, C.border.a)
        UI:StylePopup(f, { shadowSize = 16 })
        f:SetFrameStrata("HIGH")
        f:SetMovable(true)
        f:EnableMouse(true)
        f:RegisterForDrag("LeftButton")
        f:SetScript("OnDragStart", function(self2) self2:StartMoving() end)
        f:SetScript("OnDragStop", function(self2) self2:StopMovingOrSizing() end)

        f.title = UI:CreateTitle(f, L["Since your last login"], 15)
        f.title:SetPoint("TOPLEFT", 16, -14)

        f.close = UI:CreateCloseButton(f)
        f.close:SetPoint("TOPRIGHT", -8, -8)
        f.close:SetScript("OnClick", function() f:Hide() end)

        f.body = CreateFrame("Frame", nil, f)
        f.body:SetPoint("TOPLEFT", 16, -44)
        f.body:SetPoint("BOTTOMRIGHT", -16, 48)

        f.openBtn = UI:CreateButton(f, L["Open Amazing Hub"], 140, 26)
        f.openBtn:SetPoint("BOTTOM", 0, 14)
        f.openBtn:SetScript("OnClick", function()
            f:Hide()
            AmazingHub:ToggleRoster()
        end)
        self.frame = f
    end

    -- (Re)populate the body
    for _, c in pairs({ f.body:GetChildren() }) do c:Hide() end
    for _, r in pairs({ f.body:GetRegions() }) do r:Hide() end

    local y = 0
    if #lines == 0 then
        local empty = UI:CreateText(f.body, L["Nothing new since your last login."], 11, C.silver.r, C.silver.g, C.silver.b)
        empty:SetPoint("TOPLEFT", 2, -y)
        empty:SetWidth(f.body:GetWidth() - 4)
    else
        for _, line in ipairs(lines) do
            local dot = UI:CreateText(f.body, "|cffEDCC7B*|r", 12, C.gold.r, C.gold.g, C.gold.b)
            dot:SetPoint("TOPLEFT", 2, -y)
            local fs = UI:CreateText(f.body, line, 11, C.text.r, C.text.g, C.text.b)
            fs:SetPoint("TOPLEFT", 18, -y)
            fs:SetWidth(f.body:GetWidth() - 22)
            fs:SetJustifyH("LEFT")
            y = y + math.max(20, (fs:GetStringHeight() or 14) + 8)
        end
    end
    -- The title above and the button below: a long digest grows, never runs under the button.
    f:SetHeight(math.max(280, 44 + y + 48))

    f:Show()
    return f
end

----------------------------------------------------------------------
-- Auto-show once on login (skipped on first run and when disabled).
----------------------------------------------------------------------
function Digest:ShowOnLogin()
    if not AmazingHub.db.digest or not AmazingHub.db.digest.enabled then return end
    if self.shownThisSession then return end

    local since = AmazingHub.db.digest.lastSeen or 0
    -- First ever run: nothing to compare against — just start the clock.
    if since == 0 then
        AmazingHub.db.digest.lastSeen = GetServerTime()
        return
    end

    local lines = self:Build(since)
    self:MarkFeedSeen(GetServerTime())
    if AmazingHub.Achievements then AmazingHub.Achievements:MarkSeen() end
    if AmazingHub.Activation then
        if AmazingHub.Activation:GetDigestLine(GetServerTime()) then AmazingHub.Activation:Reminded(GetServerTime()) end
    end
    AmazingHub.db.digest.lastSeen = GetServerTime()
    self.shownThisSession = true
    if #lines > 0 then
        self:Show(lines)
    end
end
