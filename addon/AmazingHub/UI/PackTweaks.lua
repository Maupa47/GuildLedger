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
