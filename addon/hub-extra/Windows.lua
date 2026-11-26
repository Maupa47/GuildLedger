----------------------------------------------------------------------
-- Amazing Hub - windows in front, folded window reopens whole (Amazing Forever Guild Pack 0.7.0; our own file)
--
-- H1 (PLAN_COMMUNITY W11): the main window and every hub popup are top-level: a click on one brings it to the
-- front of the others in its layer, and each comes to the front when it is shown. Popups styled through
-- UI:StylePopup get this when they are made; the named windows below, which some modules make without it,
-- when they first exist (looked for when the main window shows and just after a mouse click, since a popup is
-- made by a click). The game's own dialogs keep their higher layer and still open above.
-- H5 (W15): a main window closed while folded to the bar opens full size again from /amazing, the minimap
-- button or the key binding (all go through UI:ToggleMain; UI:OpenWindow did this already).
--
-- Copied in by tools/rebrand-hub.py from addon/hub-extra/; edit it there.
----------------------------------------------------------------------
local UI = AmazingHub.UI
local W = {}
AmazingHub.PackWindows = W

-- Hub windows made with CreateFrame and a global name (the 1.40.0 source, 2026-11-25).
W.NAMES = {
    "AmazingHubAnalyticsFrame", "AmazingHubBanShareDialog", "AmazingHubBulletinFrame", "AmazingHubCallToArms",
    "AmazingHubColumnsPanel", "AmazingHubCompanionImportPopup", "AmazingHubConsPopup", "AmazingHubCoreSignupFrame",
    "AmazingHubCouncilFrame", "AmazingHubCraftFinder", "AmazingHubCraftOrderDialog", "AmazingHubDetailFrame", "AmazingHubDigestFrame", "AmazingHubEventEditor",
    "AmazingHubExportChooser", "AmazingHubExportPopup", "AmazingHubGroupComposer", "AmazingHubGuildBankCleanup",
    "AmazingHubGuildFinder", "AmazingHubJoinForm", "AmazingHubJoinRequests", "AmazingHubLootCouncilFrame",
    "AmazingHubOfficerSheet", "AmazingHubPollsFrame", "AmazingHubPrioModal", "AmazingHubPugInspector",
    "AmazingHubRaidPromptFrame", "AmazingHubRecruitPopup", "AmazingHubRecruitScannerFrame", "AmazingHubRestoreFrame",
    "AmazingHubSRImportPopup", "AmazingHubSearchFrame", "AmazingHubWarnDialog", "AmazingHubWishImportPopup",
    "AmazingHubWishlistFrame",
}

local done = setmetatable({}, { __mode = "k" })

local function raise(self)
    if self.Raise then self:Raise() end
end

-- Makes `f` top-level and brings it to the front whenever it is shown. Once per frame.
function W.Front(f)
    if type(f) ~= "table" or done[f] or type(f.SetToplevel) ~= "function" then return false end
    done[f] = true
    pcall(f.SetToplevel, f, true)
    if f.HookScript then f:HookScript("OnShow", raise) end
    if f.IsShown and f:IsShown() then raise(f) end
    return true
end

function W.Scan()
    if AmazingHub.RosterFrame then W.Front(AmazingHub.RosterFrame) end
    for _, name in ipairs(W.NAMES) do
        local f = _G[name]
        if f then W.Front(f) end
    end
end

local style = UI.StylePopup
if style then
    function UI:StylePopup(frame, ...)
        local out = style(self, frame, ...)
        W.Front(frame)
        return out
    end
end

local toggle = UI.ToggleMain
if toggle then
    function UI:ToggleMain(...)
        local f = self.GetMainWindow and self:GetMainWindow()
        local opening = f and not f:IsShown()
        local out = toggle(self, ...)
        if opening and f:IsShown() then
            W.Front(f)
            local g = AmazingHub.db and AmazingHub.db.settings and AmazingHub.db.settings.window
            if ((g and g.collapsed) or f.band == "bar") and f.ToggleCollapsed then f:ToggleCollapsed() end
        end
        W.Scan()
        return out
    end
end

if type(CreateFrame) == "function" and AmazingHub.Compat and AmazingHub.Compat.RegisterEvent then
    local clicks = CreateFrame("Frame")
    AmazingHub.Compat.RegisterEvent(clicks, "GLOBAL_MOUSE_DOWN")
    clicks:SetScript("OnEvent", function()
        if AmazingHub.Compat.After then AmazingHub.Compat.After(0.2, W.Scan) end
    end)
end
