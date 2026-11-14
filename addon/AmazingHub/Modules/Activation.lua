----------------------------------------------------------------------
-- Amazing Hub - Activation (issue #217, the guild website #244)
--
-- The five steps that take a guild to where Amazing Hub holds, for its GM and officers while it is not
-- there yet. Two the client knows by itself: whether it publishes, and who runs the addon. The rest
-- only the guild website knows, and it says so through the inbox (GOSGILD1). Nothing here is ever stored
-- about a step: only who hid the card, when the reminder last went and that it was celebrated.
--
-- WoW: Forever only.
----------------------------------------------------------------------
if AmazingHub.Client.isAnniversary or AmazingHub.Client.isRetail then return end

local Activation = {}
AmazingHub.Activation = Activation
local L = AmazingHub.L

local DAY = 86400
local HIDE_S = 30 * DAY
local REMIND_S = 3 * DAY
local STALE_S = 3 * DAY
local ACTIVE_S = 30 * DAY
local MEMBERS_NEEDED = 5
local CELEBRATE_DELAY = 15   -- seconds after login: the chat is up by then

Activation.STEPS = { "publish", "bot", "account", "members", "run" }

function Activation:Initialize()
    AmazingHub.db.activation = AmazingHub.db.activation or {}
    AmazingHub.Compat.After(CELEBRATE_DELAY, function() Activation:Celebrate() end)
end

local function fromSite()
    local block = AmazingHub.CompanionImport and AmazingHub.CompanionImport:GuildBlock()
    local a = block and block.activation
    return type(a) == "table" and a or nil
end

local function addonMembers(now)
    local n = 0
    for _, m in pairs(AmazingHub.db.members or {}) do
        if type(m) == "table" and (tonumber(m.lastUpdate) or 0) > now - ACTIVE_S then n = n + 1 end
    end
    return n
end

-- Where the guild stands: { steps, done, activated, staleDays }. `staleDays` when what the site said
-- is over three days old, for the card to say so.
function Activation:Read(now)
    local a = fromSite()
    local site = a and type(a.steps) == "table" and a.steps or {}
    local steps = {
        publish = site.publish == true or (AmazingHubDB and AmazingHubDB.__companionAt) ~= nil,
        bot = site.bot == true,
        account = site.account == true,
        members = site.members == true or addonMembers(now) >= MEMBERS_NEEDED,
        run = site.run == true,
    }
    local done = 0
    for _, id in ipairs(self.STEPS) do
        if steps[id] then done = done + 1 end
    end
    local at = AmazingHub.CompanionImport:Ack()
    local stale = at and now - at > STALE_S and math.floor((now - at) / DAY) or nil
    -- Once said it stays: a block gone old, or the companion off, does not un-activate a guild.
    local activated = (a and tonumber(a.activatedAt) ~= nil) or (AmazingHub.db.activation and AmazingHub.db.activation.celebrated == true) or false
    return { steps = steps, done = done, activated = activated, staleDays = stale }
end

-- For the GM and the officers, while the guild is not there and they did not put it away.
function Activation:ShouldShow(now)
    if not AmazingHub:IsOfficer() or not AmazingHub.db.activation then return false end
    return not self:Read(now).activated and now >= (AmazingHub.db.activation.hiddenUntil or 0)
end

function Activation:Hide(now)
    AmazingHub.db.activation.hiddenUntil = now + HIDE_S
end

-- One line in the login digest, every three days at most.
function Activation:GetDigestLine(now)
    if not self:ShouldShow(now) or now - (AmazingHub.db.activation.remindedAt or 0) < REMIND_S then return nil end
    return string.format(L["Set up Amazing Hub for your guild: %d of %d steps done"], self:Read(now).done, #self.STEPS)
end

function Activation:Reminded(now)
    if AmazingHub.db.activation then AmazingHub.db.activation.remindedAt = now end
end

-- Once, when the site says the guild got there.
function Activation:Celebrate()
    local db = AmazingHub.db.activation
    if not db or db.celebrated or not AmazingHub:IsOfficer() then return end
    local a = fromSite()
    if a and tonumber(a.activatedAt) then
        db.celebrated = true
        AmazingHub:Print(L["Amazing Hub is set up for your guild. Well done!"])
    end
end
