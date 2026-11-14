----------------------------------------------------------------------
-- Amazing Hub - Feature entries
-- The list every surface renders from: the window's tabs, the minimap
-- menu, the slash commands and the Settings toggles. Adding a feature
-- means adding one entry here.
--
--   tab = false  -> a background module with a Settings toggle only
----------------------------------------------------------------------
local UI = AmazingHub.UI
local L  = AmazingHub.L

-- Tabs, in window order ----------------------------------------------
-- `retail = false`: not on retail (ADR-0026), which has no Master Loot: the loot master (issue #185).
UI:RegisterFeature({
    id = "home", label = L["Now"], order = 5, core = true,
    build = function(c, win) AmazingHub:CreateNowPanel(c, win) end,
})

UI:RegisterFeature({
    id = "roster", label = L["Roster"], order = 10, core = true,
    build = function(c, win) AmazingHub:CreateRosterPanel(c, win) end,
})

UI:RegisterFeature({
    id = "raids", label = L["Raids"], order = 20,
    subs = { "sessions", "raiders", "cores", "audit", "raidtools" },
    build = function(c, win) AmazingHub:CreateRaidHubPanel(c, win) end,
})

UI:RegisterFeature({
    -- On retail too since issue #183: the history and the equity of personal loot, no soft reserves.
    id = "loot", label = L["Loot"], order = 30, officerOnly = true,
    build = function(c, win) AmazingHub:CreateLootPanel(c, win) end,
})

UI:RegisterFeature({
    id = "dkp", label = L["DKP"], order = 35,   -- on retail too since issue #185
    condition = function() return AmazingHub:LootSystemShowsDKP() end,
    build = function(c, win) AmazingHub:CreateDKPPanel(c, win) end,
})

UI:RegisterFeature({
    id = "wishlist", label = L["Wishlist"], order = 38,   -- on retail too since issue #185
    condition = function() return AmazingHub:IsOfficer() and AmazingHub:LootSystemShowsWishlist() end,
    build = function(c, win) AmazingHub:CreateWishlistGuildPanel(c, win) end,
})

-- On WoW: Forever the Professions panel (issue #33) takes the Recipes tab: the whole catalog,
-- who covers it and who does not. Anniversary keeps the recipe search.
UI:RegisterFeature({
    id = "recipes", label = AmazingHub.CreateProfessionsPanel and L["Professions"] or L["Recipes"], order = 40,
    build = function(c, win)
        if AmazingHub.CreateProfessionsPanel then return AmazingHub:CreateProfessionsPanel(c, win) end
        return AmazingHub:CreateRecipesPanel(c, win)
    end,
})

UI:RegisterFeature({
    id = "guild", label = L["Guild"], order = 50,
    subs = { "calendar", "activity", "cta" },
    build = function(c, win) AmazingHub:CreateGuildHub(c, win) end,
})

-- WoW: Forever only (issue #211): the guild's journal, where the module exists.
UI:RegisterFeature({
    id = "journal", label = L["Journal"], order = 55, tbc = false, retail = false, restart = true,
    build = function(c, win) AmazingHub:CreateJournalPanel(c, win) end,
})

-- WoW: Forever only (issue #216): what the guild earned, as the guild website says it.
UI:RegisterFeature({
    id = "achievements", label = L["Achievements"], order = 56, tbc = false, retail = false,
    build = function(c, win) AmazingHub:CreateAchievementsPanel(c, win) end,
})

UI:RegisterFeature({
    id = "alliance", label = L["Alliance"], order = 60,
    condition = function()
        return (AmazingHub.Alliance and AmazingHub.Alliance:Get() ~= nil) or AmazingHub:IsOfficer()
    end,
    build = function(c, win) AmazingHub:CreateAlliancePanel(c, win) end,
})

UI:RegisterFeature({
    id = "recruitment", label = L["Recruitment"], order = 70,
    build = function(c, win) AmazingHub:CreateRecruitmentPanel(c, win) end,
})

UI:RegisterFeature({
    id = "trials", label = L["Trials"], order = 80, officerOnly = true,
    build = function(c, win) AmazingHub:CreateTrialsPanel(c, win) end,
})

UI:RegisterFeature({
    id = "management", label = L["Leadership"], order = 90, officerOnly = true,
    build = function(c, win) AmazingHub:CreateManagementPanel(c, win) end,
})

UI:RegisterFeature({
    id = "web", label = L["Web"], order = 95,   -- on retail too since issue #182
    -- Not officerOnly: publishing is each player's own choice, and the
    -- guild's picture on the site gets better the more members opt in. The
    -- raid actions gate themselves on raid leadership instead.
    build = function(c, win) AmazingHub:CreateWebPanel(c, win) end,
})

UI:RegisterFeature({
    id = "settings", label = L["Settings"], order = 100, core = true,
    build = function(c, win) AmazingHub:CreateSettingsPanel(c, win) end,
})

-- Background modules: a Settings toggle and nothing else ------------
-- `tbc`: TBC content, listed only on TBC Anniversary (ADR-0014). `retail`: false when not on retail.
-- `forever`: false when not on WoW: Forever (issue #187).
local function background(id, label, desc, officerOnly, tbc, retail, forever)
    UI:RegisterFeature({
        id = id, label = label, desc = desc,
        tab = false, officerOnly = officerOnly, tbc = tbc, retail = retail, forever = forever,
        module = id,
    })
end

background("raidTracker",       L["Raid Tracker"],       L["Track raid attendance, penalties, and sessions"], true)
background("lootTracker",       L["Loot Tracker"],       L["Record loot drops from boss kills"])  -- personal loot on retail (#183)
background("lootMaster",        L["Loot Master"],        L["Master Loot with wishlist auto-council"], nil, nil, false)
-- Anniversary's and retail's (Midnight's flask, food and rune; issue #187); WoW: Forever has none.
background("consumableChecker", L["Consumable Checker"], L["Scan raid for missing flasks/food/elixirs"], nil, nil, nil, false)
background("raidHUD",           L["Raid CD Tracker"],    L["Floating tracker for raid cooldowns and consumable check"], nil, true)
background("trialTracker",      L["Trial Tracker"],      L["Track trial member progress (officer)"], true)
background("officerNotes",      L["Officer Notes"],      L["Private notes on guild members (officer)"], true)
background("commSystem",        L["Comm System"],        L["Sync member data between addon users"])
-- WoW: Forever only: on by default since issue #289 (was off until tested, #232).
background("founding",          L["Founding"],           L["The guild's founding and its founding members"], nil, false, false)
