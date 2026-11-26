----------------------------------------------------------------------
-- Amazing Hub - Shift + click links an item into chat everywhere in the hub (Amazing Forever Guild Pack 0.8.0;
-- our own file, not upstream)
--
-- H7 (PLAN_COMMUNITY W17). Upstream already links on Shift + click in the bank, Professions, Recipes and craft
-- orders (HandleModifiedItemClick, the game's own handler, which puts the link into an open chat box). Every
-- other hub row that shows an item's tooltip (materials, wishlists, loot, search results) gets the same here:
-- after a Shift + click over a hub window (frame:IsMouseOver, SimpleScriptRegionAPI), when nothing linked
-- anything during that click, the item the game's tooltip shows (Compat.TooltipItem) goes the same way.
-- Recipes: Shift + click in Crafts and in the title bar's search links the recipe itself (Links.RecipeLink).
--
-- Copied in by tools/rebrand-hub.py from addon/hub-extra/; edit it there.
----------------------------------------------------------------------
local Links = {}
AmazingHub.PackLinks = Links

local Compat = AmazingHub.Compat
local linkedAt = -1  -- GetTime() of the last link the game handled

local function now() return (GetTime and GetTime()) or 0 end

-- Is the mouse over a shown hub window?
function Links.OverHub()
    local W = AmazingHub.PackWindows
    local f = AmazingHub.RosterFrame
    if f and f:IsShown() and f.IsMouseOver and f:IsMouseOver() then return true end
    for _, name in ipairs(W and W.NAMES or {}) do
        f = _G[name]
        if type(f) == "table" and f.IsShown and f:IsShown() and f.IsMouseOver and f:IsMouseOver() then return true end
    end
    return false
end

-- The link the tooltip shows, when it shows an item.
function Links.TooltipLink()
    if not (GameTooltip and GameTooltip.IsShown and GameTooltip:IsShown() and Compat.TooltipItem) then return nil end
    local ok, _, link = pcall(Compat.TooltipItem, GameTooltip)
    if ok and type(link) == "string" and link:find("|Hitem:", 1, true) then return link end
    return nil
end

-- A recipe's own link from its spell id (Compat.SpellLink: C_Spell.GetSpellLink, SpellDocumentation 1.60.1), or nil.
function Links.RecipeLink(spellID)
    return Compat.SpellLink and Compat.SpellLink(spellID) or nil
end

-- After a click: link what the tooltip shows unless something already linked during the click (`since`).
function Links.AfterClick(since)
    if linkedAt >= since then return false end
    if not Links.OverHub() then return false end
    local link = Links.TooltipLink()
    if not (link and HandleModifiedItemClick) then return false end
    HandleModifiedItemClick(link)
    return true
end

if type(hooksecurefunc) == "function" then
    if HandleModifiedItemClick then hooksecurefunc("HandleModifiedItemClick", function() linkedAt = now() end) end
    if ChatEdit_InsertLink then hooksecurefunc("ChatEdit_InsertLink", function() linkedAt = now() end) end
end

if type(CreateFrame) == "function" and Compat and Compat.RegisterEvent then
    local f = CreateFrame("Frame")
    Compat.RegisterEvent(f, "GLOBAL_MOUSE_UP")
    f:SetScript("OnEvent", function(_, _, button)
        if button ~= "LeftButton" or not (IsShiftKeyDown and IsShiftKeyDown()) then return end
        local since = now()
        -- The row's own OnClick runs on the same mouse-up; look a moment later whether it linked.
        if Compat.After then
            Compat.After(0.05, function()
                local ok, err = pcall(Links.AfterClick, since)
                if not ok and AmazingHub.RecordError then AmazingHub:RecordError("Links: " .. tostring(err)) end
            end)
        end
    end)
end
