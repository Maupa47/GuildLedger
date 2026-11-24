----------------------------------------------------------------------
-- Amazing Hub - Settings: fold-out sections, and the pack's own sections
-- (Amazing Forever Guild Pack; our own file, not upstream. Rebuilt for upstream's Form pages in 0.7.0.)
--
-- Upstream builds each Settings page (Profile, Interface, Chat, Modules, Rules, Data) with a Form: rows top to
-- bottom, re-anchored by Form:Layout. AmazingHub:RefreshSettingsPanel(content, key) returns that Form; a fresh one
-- is made when the page changes shape. Each time a fresh Form appears, this file appends:
--   Chat page       "Chat messages": one switch for both addons' unprompted chat lines (off), the login
--                   greeting (on), GuildLedger's developer mode (off)
--   Interface page  "World map": GuildLedger's map switches and the look of the dots (through GuildLedgerAPI)
--   Profile page    "Collector (officers)": the officer's role switch (/gl collector on|off)
-- Fold-out: on a page with two sections or more every heading becomes "+"/"-"; a click opens or closes its
-- section. The first section of a page starts open, the others closed; what the player chose is remembered
-- (settings.openSections, by title). Rows of a closed section are hidden through the rows' own `shown`, so
-- upstream's Layout moves everything below up.
--
-- Copied in by tools/rebrand-hub.py from addon/hub-extra/; edit it there.
----------------------------------------------------------------------
local UI = AmazingHub.UI
local C = AmazingHub.Colors

local ROUND = "Interface\\CharacterFrame\\TempPortraitAlphaMask" -- white disc, as GuildLedger draws round dots
local LABEL_X = 150 -- where the choice buttons start, after their label

local Plus = {}
AmazingHub.SettingsPlus = Plus

local function api()
    local a = GuildLedgerAPI
    if type(a) == "table" and a.apiVersion == 1 then return a end
end

local function call(fn, ...)
    if type(fn) ~= "function" then return nil end
    local ok, a, b = pcall(fn, ...)
    if ok then return a, b end
end

local function openSections()
    local s = AmazingHub:GetSetting("openSections")
    if type(s) ~= "table" then
        s = {}
        AmazingHub:SetSetting("openSections", s)
    end
    return s
end

local function both(a, b)
    if not a then return b end
    return function() return a() and b() end
end

local function frame(F, h)
    local f = CreateFrame("Frame", nil, F.content)
    f:SetSize(1, h)
    return f
end

local function mark(b, on)
    if not (b.SetBaseColor and b.label) then return end -- a style whose buttons the game draws
    if on then
        b:SetBaseColor(C.accent.r * 0.34, C.accent.g * 0.34, C.accent.b * 0.34, 0.95)
        b.label:SetTextColor(C.gold.r, C.gold.g, C.gold.b)
    else
        b:SetBaseColor(C.bg2.r, C.bg2.g, C.bg2.b, 0.92)
        b.label:SetTextColor(C.text.r, C.text.g, C.text.b)
    end
end

----------------------------------------------------------------------
-- Fold-out sections
----------------------------------------------------------------------

-- Remember where each section starts: wraps the Form's Section once (all pages share one Form class).
local function recordSections(F)
    local Form = getmetatable(F)
    Form = Form and (Form.__index or Form)
    if type(Form) ~= "table" or type(Form.Section) ~= "function" or Form.__amzSections then return false end
    local section = Form.Section
    Form.Section = function(self, title, shown)
        local first = #self.rows + 1
        local fs = section(self, title, shown)
        self.__amzHeads = self.__amzHeads or {}
        self.__amzHeads[#self.__amzHeads + 1] = { title = title, first = first, row = #self.rows, fs = fs }
        return fs
    end
    Form.__amzSections = true
    return true
end

function Plus.Fold(F)
    local heads = F.__amzHeads
    if type(heads) ~= "table" or #heads < 2 then return end
    local open = openSections()
    for i, h in ipairs(heads) do
        if open[h.title] == nil then open[h.title] = i == 1 end
        local isOpen = function() return open[h.title] == true end
        local last = heads[i + 1] and (heads[i + 1].first - 1) or #F.rows
        for r = h.row + 1, last do
            local row = F.rows[r]
            if row then row.shown = both(row.shown, isOpen) end
        end
        local headRow = F.rows[h.row]
        local btn = CreateFrame("Button", nil, F.content)
        btn:SetAllPoints(h.fs)
        local function label() h.fs:SetText((open[h.title] and "-  " or "+  ") .. h.title) end
        label()
        btn:SetScript("OnEnter", function() h.fs:SetTextColor(C.gold.r, C.gold.g, C.gold.b) end)
        btn:SetScript("OnLeave", function() h.fs:SetTextColor(C.text.r, C.text.g, C.text.b) end)
        btn:SetScript("OnClick", function()
            open[h.title] = not open[h.title]
            label()
            F:Refresh()
        end)
        h.btn, h.headShown = btn, headRow and headRow.shown
    end
    -- the click areas follow their headings (a heading may itself be hidden by upstream)
    local layout = F.Layout
    F.Layout = function(self, ...)
        local y = layout(self, ...)
        for _, h in ipairs(heads) do h.btn:SetShown(h.fs:IsShown()) end
        return y
    end
end

----------------------------------------------------------------------
-- Chat messages (0.5.3): one switch for both addons (PackTweaks.lua gates the hub's chat lines,
-- GuildLedgerAPI.SetMessages GuildLedger's). Off by default. Plus the greeting and developer mode.
----------------------------------------------------------------------
function Plus.BuildMessages(F)
    F:Section("Chat messages")
    F:Check("Show chat messages from the Amazing Forever Guild Pack",
        "Off: nothing appears in chat by itself (the login line, sync notices, link confirmations)."
        .. " The answers to commands you type and to your clicks always show.",
        function() return AmazingHub.ChatMessagesOn and AmazingHub:ChatMessagesOn() or false end,
        function(on)
            AmazingHub:SetSetting("chatMessages", on)
            local a = api()
            if a then call(a.SetMessages, on) end
        end)
    local a = api()
    if a and a.GetWelcome then -- login greeting (0.5.4): /gl welcome on|off
        F:Check("Greeting and the guild's message of the day when I log in",
            "On by default. Only in your own chat window, once per login (not after /reload).",
            function() return call(a.GetWelcome) and true or false end,
            function(on) call(a.SetWelcome, on) end)
    end
    if a and a.GetDevMode then -- developer mode (0.5.4): /gl dev on|off
        F:Check("Developer mode: show what GuildLedger sends and receives",
            "Chat history found after login, which collector asked for missing chat text, how many lines came"
            .. " from which player, and how many are still missing. For testing; off by default.",
            function() return call(a.GetDevMode) and true or false end,
            function(on) call(a.SetDevMode, on) end)
    end
end

----------------------------------------------------------------------
-- Collector (0.6.0): the officer's role switch, saved for the whole WoW account; applies after /reload.
----------------------------------------------------------------------
function Plus.BuildCollector(F)
    local a = api()
    if not (a and a.GetCollector and a.SetCollector) then return end
    local _, active = call(a.GetCollector)
    local function want() return (call(a.GetCollector)) and true or false end
    local function pending() return want() ~= (active and true or false) end
    F:Section("Collector (officers)")
    F:Check("I am a collector (I run the GuildLedger companion on this PC)",
        "Only for officers the guild's GuildLedger admin has set up. On: also reads the guild chat history,"
        .. " tracks joins, leaves and kicks, and asks members for lines it missed. Counts for every character"
        .. " on this WoW account.",
        want, function(on) call(a.SetCollector, on) end)
    F:Buttons({ { "Reload now", function() if ReloadUI then ReloadUI() end end, w = 110 } },
        { indent = 34, shown = pending })
    F:Note("The change takes effect after a reload.", { indent = 34, shown = pending })
end

----------------------------------------------------------------------
-- World map
----------------------------------------------------------------------

local function classLabel(class)
    local names = LOCALIZED_CLASS_NAMES_MALE
    if type(names) == "table" and type(names[class]) == "string" then return names[class] end
    return class:sub(1, 1) .. class:sub(2):lower()
end

local function paint(tex, shape, r, g, b, a)
    if shape == "round" then
        tex:SetTexture(ROUND)
        tex:SetVertexColor(r, g, b, a)
    else
        tex:SetColorTexture(r, g, b, a)
        tex:SetVertexColor(1, 1, 1, 1)
    end
end

-- The game's colour picker (Blizzard_ColorPickerFrame, Mainline and Classic): false when it is missing.
function Plus.PickColor(r, g, b, onChange)
    local P = ColorPickerFrame
    if type(P) ~= "table" or type(P.SetupColorPickerAndShow) ~= "function" then return false end
    P:SetupColorPickerAndShow({
        r = r, g = g, b = b, hasOpacity = false,
        swatchFunc = function() onChange(P:GetColorRGB()) end,
        cancelFunc = function() onChange(P:GetPreviousValues()) end,
    })
    return true
end

-- A label and a row of choice buttons; the current one is highlighted. list = { { id, text, w }, ... }.
local function choices(F, label, list, get, pick, shown)
    local f = frame(F, 24)
    local lbl = UI:CreateText(f, label, 11, C.text.r, C.text.g, C.text.b)
    lbl:SetPoint("LEFT", 4, 0)
    local btns = {}
    for _, c in ipairs(list) do
        local b = UI:CreateButton(f, c.text, c.w or 110, 22)
        b:SetScript("OnClick", function() pick(c.id); F:Refresh() end)
        btns[#btns + 1] = { b = b, id = c.id, w = c.w or 110 }
    end
    F:Sync(function()
        local cur = get()
        for _, e in ipairs(btns) do mark(e.b, cur == e.id) end
    end)
    F:Row(f, { wide = true, shown = shown, place = function(_, w)
        local x, y = LABEL_X, 0
        for _, e in ipairs(btns) do
            if x > LABEL_X and x + e.w > w then x, y = LABEL_X, y + 26 end
            e.b:ClearAllPoints()
            e.b:SetPoint("TOPLEFT", f, "TOPLEFT", x, -y)
            x = x + e.w + 4
        end
        f:SetHeight(y + 24)
        return y + 24
    end })
end

function Plus.BuildMap(F)
    local a = api()
    F:Section("World map")
    local m = a and call(a.GetMap)
    if not m then
        F:Note("Needs GuildLedger, which comes in the same pack: tick it in the AddOns list on the character screen.")
        return
    end
    if not m.available then
        F:Note("The world map is not available in this game version.")
        return
    end
    F:Sync(function() m = call(a.GetMap) or m end) -- runs first on every refresh: the rows below read `m`
    local set = function(...) call(a.SetMapLook, ...) end
    local sharing = function() return m.share and m.shareScope ~= nil end

    F:Check("Show my position to guild members on the world map",
        "Only while a guild member looks at the map of your zone; never in instances or boss fights; never saved.",
        function() return m.share end, function(on) call(a.SetMapShare, on) end)
    F:Check("Show guild members on my world map", nil, function() return m.pins end,
        function(on) call(a.SetMapPins, on) end)

    if m.shareScope then
        choices(F, "Who sees me", {
            { id = "all", text = "Zone, continent, world", w = 160 },
            { id = "zone", text = "Only my zone's map", w = 140 },
        }, function() return m.shareScope end, function(id) set("shareScope", id) end, sharing)
        F:Note("\"Only my zone's map\": guild members see you only when they open the map of the zone you are in.",
            { indent = 34, shown = sharing })
    end
    if m.near then
        choices(F, "Show members", {
            { id = "any", text = "Anywhere", w = 100 },
            { id = "continent", text = "On my continent", w = 130 },
            { id = "zone", text = "In my zone", w = 100 },
        }, function() return m.near end, function(id) set("near", id) end)
        F:Note("For example \"In my zone\": in Elwynn Forest you see only the guild members in Elwynn Forest,"
            .. " whichever map you open.", { indent = 34 })
    end
    if m.views then
        local f = frame(F, 22)
        local lbl = UI:CreateText(f, "Show dots on", 11, C.text.r, C.text.g, C.text.b)
        lbl:SetPoint("LEFT", 4, 0)
        local boxes = {}
        for i, v in ipairs({ { id = "zone", text = "Zone maps" }, { id = "continent", text = "Continent maps" },
                             { id = "world", text = "World map" } }) do
            local cb = UI:CreateCheckbox(f, v.text, 18)
            cb:SetPoint("LEFT", f, "LEFT", LABEL_X + (i - 1) * 140, 0)
            cb.checkbox.onChanged = function(_, on) set("view", v.id, on and true or false) end
            boxes[v.id] = cb
        end
        F:Sync(function() for id, cb in pairs(boxes) do cb.checkbox:SetChecked(m.views[id] and true or false) end end)
        F:Row(f, { wide = true, h = 22 })
        F:Check("Names next to the dots (otherwise when you point at a dot)", nil, function() return m.names end,
            function(on) set("names", on) end)
        if m.self ~= nil then
            F:Check("Show my own dot (off: only the game's arrow shows you)", nil, function() return m.self end,
                function(on) set("self", on) end)
        end
    end

    -- Marker shape, with a preview of one dot as it looks on the map
    local look = { shape = m.shape, size = m.size, outline = m.outline }
    local shapeRow = frame(F, 28)
    local shapeLbl = UI:CreateText(shapeRow, "Marker", 11, C.text.r, C.text.g, C.text.b)
    shapeLbl:SetPoint("LEFT", 4, 0)
    local shapeBtns = {}
    for i, shape in ipairs({ "round", "square" }) do
        local b = UI:CreateButton(shapeRow, shape == "round" and "Round" or "Square", 80, 22)
        b:SetPoint("LEFT", shapeRow, "LEFT", LABEL_X + (i - 1) * 84, 0)
        b:SetScript("OnClick", function() set("shape", shape); F:Refresh() end)
        shapeBtns[shape] = b
    end
    local preview = CreateFrame("Frame", nil, shapeRow)
    preview:SetPoint("LEFT", shapeRow, "LEFT", LABEL_X + 2 * 84 + 24, 0)
    preview:SetSize(40, 28)
    local rim = preview:CreateTexture(nil, "ARTWORK")
    rim:SetPoint("CENTER")
    local dot = preview:CreateTexture(nil, "OVERLAY")
    dot:SetPoint("CENTER")
    local sample
    local function drawPreview()
        local r, g, b = 0.25, 0.78, 0.92
        if sample then r, g, b = sample.r, sample.g, sample.b end
        paint(dot, look.shape, r, g, b, 1)
        dot:SetSize(look.size or 12, look.size or 12)
        if look.outline then
            paint(rim, look.shape, 0, 0, 0, 0.85)
            rim:SetSize((look.size or 12) + 4, (look.size or 12) + 4)
            rim:Show()
        else
            rim:Hide()
        end
    end
    F:Sync(function()
        look.shape, look.size, look.outline = m.shape, m.size, m.outline
        sample = m.colors and m.colors[1] or sample
        for shape, b in pairs(shapeBtns) do mark(b, m.shape == shape) end
        drawPreview()
    end)
    F:Row(shapeRow, { wide = true, h = 28, gap = 12 })

    -- Size (the slider shows its value above itself and min/max below: room on both sides)
    local sizeRow = frame(F, 40)
    local sizeLbl = UI:CreateText(sizeRow, "Size", 11, C.text.r, C.text.g, C.text.b)
    sizeLbl:SetPoint("LEFT", 4, 0)
    local slider = CreateFrame("Slider", "AmazingHubMapDotSlider", sizeRow, "OptionsSliderTemplate")
    slider:SetPoint("LEFT", sizeRow, "LEFT", LABEL_X, 0)
    slider:SetWidth(180)
    slider:SetMinMaxValues(m.sizeMin or 6, m.sizeMax or 24)
    slider:SetValueStep(1)
    slider:SetObeyStepOnDrag(true)
    local name = slider:GetName()
    if _G[name .. "Low"] then _G[name .. "Low"]:SetText(tostring(m.sizeMin or 6)) end
    if _G[name .. "High"] then _G[name .. "High"]:SetText(tostring(m.sizeMax or 24)) end
    local syncing = false
    F:Sync(function()
        syncing = true
        slider:SetValue(m.size or 12)
        syncing = false
        if _G[name .. "Text"] then _G[name .. "Text"]:SetText((m.size or 12) .. " px") end
    end)
    slider:SetScript("OnValueChanged", function(_, v)
        if syncing then return end
        v = math.floor(v + 0.5)
        set("size", v)
        look.size = v
        if _G[name .. "Text"] then _G[name .. "Text"]:SetText(v .. " px") end
        drawPreview()
    end)
    F:Row(sizeRow, { wide = true, h = 40, gap = 16 })

    F:Check("Dark outline (easier to see on bright maps)", nil, function() return m.outline end,
        function(on)
            set("outline", on)
            look.outline = on
            drawPreview()
        end)

    -- Colours per class: one button per class of the guild, three to a row
    local hasColors = function() return type(m.colors) == "table" and #m.colors > 0 end
    local canPick = type(ColorPickerFrame) == "table" and type(ColorPickerFrame.SetupColorPickerAndShow) == "function"
    F:Note("Colour per class", { gap = 12 })
    F:Note("The classes appear once the guild member list has loaded; open this page again in a moment.",
        { indent = 12, shown = function() return not hasColors() end })
    F:Note(canPick and "Click a class to choose its colour. Right-click: back to the game's colour."
        or "Right-click a class: back to the game's colour. (The game's colour picker is not available.)",
        { indent = 12, shown = hasColors })
    local grid = frame(F, 24)
    local cells = {}
    local function cell(i)
        local e = cells[i]
        if e then return e end
        local b = CreateFrame("Button", nil, grid)
        b:SetSize(144, 20)
        b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
        local sw = b:CreateTexture(nil, "ARTWORK")
        sw:SetSize(14, 14)
        sw:SetPoint("LEFT", 2, 0)
        local lbl = UI:CreateText(b, "", 10, 1, 1, 1)
        lbl:SetPoint("LEFT", sw, "RIGHT", 6, 0)
        e = { b = b, sw = sw, lbl = lbl }
        b:SetScript("OnClick", function(_, button)
            local c = e.c
            if not c then return end
            if button == "RightButton" then
                set("color", c.class)
                F:Refresh()
                return
            end
            Plus.PickColor(c.r, c.g, c.b, function(r, g, bl)
                if type(r) ~= "number" then return end
                set("color", c.class, r, g, bl)
                e.sw:SetColorTexture(r, g, bl, 1)
                e.lbl:SetTextColor(r, g, bl)
                if sample and sample.class == c.class then
                    sample = { class = c.class, r = r, g = g, b = bl }
                    drawPreview()
                end
            end)
        end)
        cells[i] = e
        return e
    end
    F:Sync(function()
        local list = hasColors() and m.colors or {}
        for i, c in ipairs(list) do
            local e = cell(i)
            e.c = c
            e.sw:SetColorTexture(c.r, c.g, c.b, 1)
            e.lbl:SetText(classLabel(c.class) .. (c.custom and "  *" or ""))
            e.lbl:SetTextColor(c.r, c.g, c.b)
            e.b:Show()
        end
        for i = #list + 1, #cells do cells[i].b:Hide(); cells[i].c = nil end
    end)
    F:Row(grid, { wide = true, indent = 12, shown = hasColors, place = function(_, w)
        local per = math.max(1, math.min(3, math.floor(w / 150)))
        local n = 0
        for i, e in ipairs(cells) do
            if e.c then
                e.b:ClearAllPoints()
                e.b:SetPoint("TOPLEFT", grid, "TOPLEFT", ((i - 1) % per) * 150, -math.floor((i - 1) / per) * 24)
                n = i
            end
        end
        local h = math.max(24, math.ceil(n / per) * 24)
        grid:SetHeight(h)
        return h
    end })

    F:Buttons({
        { "Reset map options", function() set("reset"); F:Refresh() end, w = 150 },
        { "Open world map", function() AmazingHub:ToggleGuildMap() end, w = 140 },
    }, { gap = 12 })
end

----------------------------------------------------------------------
-- Hook into upstream's Settings pages
----------------------------------------------------------------------

local EXTRA = { chat = Plus.BuildMessages, interface = Plus.BuildMap, profile = Plus.BuildCollector }
-- upstream's page keys, and the old ones it still accepts (UI/SettingsPanel.lua OLD_KEYS); anything else is "profile"
local KNOWN = { profile = true, interface = true, chat = true, modules = true, rules = true, data = true }
local OLD_KEYS = { general = "profile", raid = "rules", officer = "rules", about = "data" }

local original = AmazingHub.RefreshSettingsPanel
function AmazingHub:RefreshSettingsPanel(content, key, ...)
    local F = original(self, content, key, ...)
    if type(F) ~= "table" or type(F.rows) ~= "table" then return F end
    if recordSections(F) then -- first page ever: build it again so its headings are recorded too
        content.__settingsShape = nil
        F = original(self, content, key, ...)
    end
    if content.__amzForm ~= F then -- a fresh Form: add ours, then fold
        content.__amzForm = F
        local page = OLD_KEYS[key] or key
        local build = EXTRA[page] or (EXTRA[page] == nil and not KNOWN[page] and EXTRA.profile) -- upstream's fallback
        if build then
            local ok, err = pcall(build, F)
            if not ok and AmazingHub.Debug then AmazingHub:Debug("Settings " .. tostring(page) .. ": " .. tostring(err)) end
        end
        local ok, err = pcall(Plus.Fold, F)
        if not ok and AmazingHub.Debug then AmazingHub:Debug("Settings sections: " .. tostring(err)) end
        F:Refresh()
    end
    return F
end
