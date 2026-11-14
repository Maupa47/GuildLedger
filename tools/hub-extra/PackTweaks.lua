----------------------------------------------------------------------
-- Amazing Hub - pack settings (Amazing Forever Guild Pack; our own file, not upstream)
-- Hides tabs the pack does not use, from the window, the minimap menu and the Settings list:
--   achievements  - comes only from the upstream project's website
--   alliance      - cross-guild federation (talks beyond our guild)
--   recruitment   - realm-wide recruiting network
--   web           - the upstream project's web companion
-- Copied in by tools/rebrand-hub.py from tools/hub-extra/; edit it there.
----------------------------------------------------------------------
local UI = AmazingHub.UI

AmazingHub.HIDDEN_FEATURES = { "achievements", "alliance", "recruitment", "web" }

local function never() return false end
for _, id in ipairs(AmazingHub.HIDDEN_FEATURES) do
    local def = UI:GetFeature(id)
    if def then def.condition = never end
end
