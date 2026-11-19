----------------------------------------------------------------------
-- Amazing Hub - pack settings (Amazing Forever Guild Pack; our own file, not upstream)
-- Hides tabs the pack does not use, from the window, the minimap menu and the Settings list:
--   achievements  - comes only from the upstream project's website
--   alliance      - cross-guild federation (talks beyond our guild)
--   recruitment   - realm-wide recruiting network
--   web           - the upstream project's web companion
-- Tabs that are off until a player ticks them in Settings -> MODULES (Core.lua's IsFeatureEnabled reads
-- OFF_BY_DEFAULT; a player's own choice is saved and wins):
--   raids, loot, trials
-- Keeps the hub quiet in chat unless the player switches messages on (see "Chat messages" below).
-- Copied in by tools/rebrand-hub.py from tools/hub-extra/; edit it there.
----------------------------------------------------------------------
local UI = AmazingHub.UI

AmazingHub.HIDDEN_FEATURES = { "achievements", "alliance", "recruitment", "web" }
AmazingHub.OFF_BY_DEFAULT = { raids = true, loot = true, trials = true }

local function never() return false end
for _, id in ipairs(AmazingHub.HIDDEN_FEATURES) do
    local def = UI:GetFeature(id)
    if def then def.condition = never end
end

-- A line beside the checkbox in Settings, so players know what the tab is.
local DESC = {
    raids = "Tab: raid sessions, attendance, raid groups. Off by default.",
    loot = "Tab (officers): loot history and who got what. Off by default.",
    trials = "Tab (officers): trial members and their progress. Off by default.",
}
for id, text in pairs(DESC) do
    local def = UI:GetFeature(id)
    if def and not def.desc then def.desc = text end
end

----------------------------------------------------------------------
-- Chat messages (0.5.3): the pack stays quiet in chat unless the player switched messages on
-- (Settings -> General -> CHAT MESSAGES, setting "chatMessages"). The answer to something the player just
-- did is always shown: a /amazing command, or a click on a hub button or checkbox (within ACT_WINDOW seconds),
-- and everything while /amazing debug is on.
----------------------------------------------------------------------
local ACT_WINDOW = 1.5
local actedUntil = 0
local function now() return type(GetTime) == "function" and GetTime() or 0 end
function AmazingHub.UserActed() actedUntil = now() + ACT_WINDOW end

function AmazingHub:ChatMessagesOn()
    return self.GetSetting and self:GetSetting("chatMessages") == true or false
end

local shown = AmazingHub.Print
if shown then
    function AmazingHub:Print(msg)
        if now() <= actedUntil or self:ChatMessagesOn() or (self.Logger and self.Logger.debug) then
            return shown(self, msg)
        end
    end
end

if type(SlashCmdList) == "table" and type(SlashCmdList.AMAZINGHUB) == "function" then
    local command = SlashCmdList.AMAZINGHUB
    SlashCmdList.AMAZINGHUB = function(...)
        AmazingHub.UserActed()
        return command(...)
    end
end

-- Clicks on the hub's own buttons and checkboxes count as "the player just did something".
for _, name in ipairs({ "CreateButton", "CreateCheckbox" }) do
    local make = UI[name]
    if make then
        UI[name] = function(ui, ...)
            local w = make(ui, ...)
            local target = type(w) == "table" and (rawget(w, "checkbox") or w)
            if target and target.HookScript then target:HookScript("OnMouseDown", AmazingHub.UserActed) end
            return w
        end
    end
end
