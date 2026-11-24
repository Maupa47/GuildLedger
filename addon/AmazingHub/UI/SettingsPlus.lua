----------------------------------------------------------------------
-- Amazing Hub - Settings: fold-out sections and the World map section
-- (Amazing Forever Guild Pack, 0.5.2; our own file, not upstream)
--
-- Fold-out: every section heading on a Settings page (MODULES, CHAT, ...) becomes a "+"/"-" heading that
-- opens or closes its section. Closed by default (on pages other than General the first one starts open); what a
-- player opens or closes is remembered
-- (settings.openSections). Done after upstream's RefreshSettingsPanel has laid the page out: the controls of
-- a closed section are hidden and everything below moves up. Pages with a single section stay as they are.
--
-- Chat messages (Settings -> General): one switch, off by default, for both addons' unprompted chat lines.
--
-- World map (Settings -> General): GuildLedger's map switches (moved here from the Ledger tab), who sees me
-- (zone/continent/world viewers or my zone only), which members I see (anywhere / my continent / my zone), on
-- which kinds of map, names next to the dots, and the look of the dots: shape, size, outline, colour per class. Read and written through GuildLedgerAPI.
--
-- Copied in by tools/rebrand-hub.py from addon/hub-extra/; edit it there.
----------------------------------------------------------------------
local UI = AmazingHub.UI
local C = AmazingHub.Colors

local HEADER_H = 24 -- the heading line that stays visible when its section is closed
local ROUND = "Interface\\CharacterFrame\\TempPortraitAlphaMask" -- white disc, as GuildLedger draws round dots

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

-- Rebuild the page, keeping the scroll position (upstream snaps to the top).
local function rebuild(content)
    local sf = content:GetParent()
    local at = sf and sf.GetVerticalScroll and sf:GetVerticalScroll() or 0
    AmazingHub:RefreshSettingsPanel(content)
    if sf and sf.SetVerticalScroll then
        local max = sf.GetVerticalScrollRange and sf:GetVerticalScrollRange() or at
        sf:SetVerticalScroll(math.min(at, max or at))
    end
end

----------------------------------------------------------------------
-- Fold-out sections
----------------------------------------------------------------------

-- Distance from the top of `content` of an element, through the element it is anchored to; nil when it is
-- not laid out from the top of the page.
local function topOf(content, obj, depth)
    depth = depth or 0
    if depth > 10 or not obj or not obj.GetPoint then return nil end
    local _, rel, _, _, y = obj:GetPoint(1)
    if rel == nil or rel == content then return type(y) == "number" and -y or nil end
    while rel and rel.GetParent and rel:GetParent() ~= content and rel ~= content do rel = rel:GetParent() end
    if rel == content or not rel then return nil end
    return topOf(content, rel, depth + 1)
end

local function moveUp(content, obj, by)
    local n = obj.GetNumPoints and obj:GetNumPoints() or 1
    local pts = {}
    for i = 1, n do pts[i] = { obj:GetPoint(i) } end
    obj:ClearAllPoints()
    for _, p in ipairs(pts) do
        local point, rel, relPoint, x, y = p[1], p[2], p[3], p[4], p[5]
        if (rel == nil or rel == content) and type(y) == "number" then y = y + by end
        obj:SetPoint(point, rel or content, relPoint or point, x or 0, y or 0)
    end
end

-- headers = { { fs = fontString, text = "MODULES" }, ... } in the order upstream made them.
function Plus.Fold(content, headers)
    if #headers < 2 then return end
    local open = openSections()
    local height = content:GetHeight() or 0
    local list = {}
    for _, h in ipairs(headers) do
        local y = topOf(content, h.fs)
        if y then list[#list + 1] = { fs = h.fs, text = h.text, top = y } end
    end
    table.sort(list, function(a, b) return a.top < b.top end)
    -- The first section of the other pages (Loot: LOOT SYSTEM, where DKP is chosen) starts open; General's all closed.
    local firstOpen = content.__settingsCat ~= nil and content.__settingsCat ~= "general"
    for i, s in ipairs(list) do
        s.bottom = list[i + 1] and list[i + 1].top or height
        if open[s.text] == nil then
            s.open = firstOpen and i == 1
        else
            s.open = open[s.text] and true or false
        end
        s.hide = s.open and 0 or math.max(0, s.bottom - s.top - HEADER_H)
    end

    local isHeader = {}
    for _, s in ipairs(list) do isHeader[s.fs] = true end
    local items = { content:GetChildren() }
    for _, r in ipairs({ content:GetRegions() }) do items[#items + 1] = r end
    -- Measure everything first: moving an element moves those anchored to it.
    local tops = {}
    for i, obj in ipairs(items) do tops[i] = not isHeader[obj] and topOf(content, obj) end
    for i, obj in ipairs(items) do
        local y = tops[i]
        if y then
            local shift, inClosed = 0, false
            for _, s in ipairs(list) do
                if y >= s.bottom then
                    shift = shift + s.hide
                elseif y >= s.top + HEADER_H - 2 and not s.open then
                    inClosed = true
                end
            end
            if inClosed then
                obj:Hide()
            elseif shift > 0 and obj.GetNumPoints then
                local _, rel = obj:GetPoint(1)
                if rel == nil or rel == content then moveUp(content, obj, shift) end
            end
        end
    end

    local total = 0
    for _, s in ipairs(list) do
        local before = 0
        for _, o in ipairs(list) do if o.bottom <= s.top then before = before + o.hide end end
        if before > 0 then moveUp(content, s.fs, before) end
        total = total + s.hide
        s.fs:SetText((s.open and "-  " or "+  ") .. s.text)
        local btn = CreateFrame("Button", nil, content)
        btn:SetPoint("TOPLEFT", s.fs, "TOPLEFT", -4, 4)
        btn:SetSize(math.max(200, (content:GetWidth() or 400) - 20), 20)
        btn:SetScript("OnEnter", function() s.fs:SetTextColor(C.gold.r, C.gold.g, C.gold.b) end)
        btn:SetScript("OnLeave", function() s.fs:SetTextColor(C.label.r, C.label.g, C.label.b) end)
        btn:SetScript("OnClick", function()
            open[s.text] = not s.open -- false is remembered too (a first section the player closed stays closed)
            rebuild(content)
        end)
    end
    content:SetHeight(math.max(1, height - total))
end

----------------------------------------------------------------------
-- World map section
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

----------------------------------------------------------------------
-- Chat messages section (0.5.3): one switch for both addons (PackTweaks.lua gates the hub's chat lines,
-- GuildLedgerAPI.SetMessages GuildLedger's). Off by default.
----------------------------------------------------------------------
function Plus.BuildMessages(content, y, header)
    local h = header("CHAT MESSAGES")
    h:SetPoint("TOPLEFT", 0, -y)
    y = y + 26
    local box = UI:CreateCheckbox(content, "Show chat messages from the Amazing Forever Guild Pack", 18)
    box:SetPoint("TOPLEFT", 4, -y)
    box.checkbox:SetChecked(AmazingHub.ChatMessagesOn and AmazingHub:ChatMessagesOn() or false)
    box.checkbox.onChanged = function(_, on)
        on = on and true or false
        AmazingHub:SetSetting("chatMessages", on)
        local a = api()
        if a then call(a.SetMessages, on) end
    end
    y = y + 28
    local function hint(text)
        local fs = UI:CreateText(content, text, 10, C.silver.r, C.silver.g, C.silver.b)
        fs:SetPoint("TOPLEFT", 34, -y)
        fs:SetJustifyH("LEFT")
        fs:SetWidth(math.max(100, (content:GetWidth() or 400) - 58))
        local hgt = fs.GetStringHeight and fs:GetStringHeight() or 0
        if type(hgt) ~= "number" or hgt < 10 then hgt = 13 end
        y = y + hgt + 12
    end
    hint("Off: nothing appears in chat by itself (the login line, sync notices, link confirmations)."
        .. " The answers to commands you type and to your clicks always show.")

    local a = api()
    -- Login greeting (0.5.4): Maupa's sprite and the guild's message of the day (/gl welcome on|off).
    if a and a.GetWelcome then
        local hello = UI:CreateCheckbox(content, "Greeting and the guild's message of the day when I log in", 18)
        hello:SetPoint("TOPLEFT", 4, -y)
        hello.checkbox:SetChecked(call(a.GetWelcome) and true or false)
        hello.checkbox.onChanged = function(_, on) call(a.SetWelcome, on and true or false) end
        y = y + 28
        hint("On by default. Only in your own chat window, once per login (not after /reload).")
    end

    -- Developer mode (0.5.4): GuildLedger's reports of what it sends and receives (/gl dev on|off).
    if a and a.GetDevMode then
        local dev = UI:CreateCheckbox(content, "Developer mode: show what GuildLedger sends and receives", 18)
        dev:SetPoint("TOPLEFT", 4, -y)
        dev.checkbox:SetChecked(call(a.GetDevMode) and true or false)
        dev.checkbox.onChanged = function(_, on) call(a.SetDevMode, on and true or false) end
        y = y + 28
        hint("Chat history found after login, which collector asked for missing chat text, how many lines came"
            .. " from which player, and how many are still missing. For testing; off by default.")
    end
    return y
end

----------------------------------------------------------------------
-- Collector section (0.6.0): the officer's role switch (/gl collector on|off), saved for the whole WoW
-- account. Takes effect after /reload; the button does that.
----------------------------------------------------------------------
function Plus.BuildCollector(content, y, header)
    local a = api()
    if not (a and a.GetCollector and a.SetCollector) then return y end
    local h = header("COLLECTOR (OFFICERS)")
    h:SetPoint("TOPLEFT", 0, -y)
    y = y + 26
    local function hint(text)
        local fs = UI:CreateText(content, text, 10, C.silver.r, C.silver.g, C.silver.b)
        fs:SetPoint("TOPLEFT", 34, -y)
        fs:SetJustifyH("LEFT")
        fs:SetWidth(math.max(100, (content:GetWidth() or 400) - 58))
        local hgt = fs.GetStringHeight and fs:GetStringHeight() or 0
        if type(hgt) ~= "number" or hgt < 10 then hgt = 13 end
        y = y + hgt + 12
        return fs
    end
    local want, active = call(a.GetCollector)
    local box = UI:CreateCheckbox(content, "I am a collector (I run the GuildLedger companion on this PC)", 18)
    box:SetPoint("TOPLEFT", 4, -y)
    box.checkbox:SetChecked(want and true or false)
    y = y + 28
    hint("Only for officers the guild's GuildLedger admin has set up. On: also reads the guild chat history,"
        .. " tracks joins, leaves and kicks, and asks members for lines it missed. Counts for every character"
        .. " on this WoW account.")
    local reload = UI:CreateButton(content, "Reload now", 110, 22)
    reload:SetPoint("TOPLEFT", 34, -y)
    reload:SetScript("OnClick", function() if ReloadUI then ReloadUI() end end)
    local note = UI:CreateText(content, "The change takes effect after a reload.", 10, C.silver.r, C.silver.g,
        C.silver.b)
    note:SetPoint("LEFT", reload, "RIGHT", 10, 0)
    y = y + 30
    local function pending(w) -- the button only while the switch differs from the running role
        local show = (w and true or false) ~= (active and true or false)
        if show then reload:Show() note:Show() else reload:Hide() note:Hide() end
    end
    pending(want)
    box.checkbox.onChanged = function(_, on)
        on = on and true or false
        call(a.SetCollector, on)
        pending(on)
    end
    return y
end

-- Builds the section at `y`; returns the new y. `header(text)` makes a recorded section heading.
function Plus.BuildMap(content, y, header)
    local a = api()
    local h = header("WORLD MAP")
    h:SetPoint("TOPLEFT", 0, -y)
    y = y + 26
    -- A text line at y; moves y below it by its real height (a long line wraps) plus `gap`.
    -- `gap` = false: a label beside other controls on the same row (y stays).
    local function text(s, size, col, x, gap)
        local fs = UI:CreateText(content, s, size or 10, col.r, col.g, col.b)
        fs:SetPoint("TOPLEFT", x or 4, -y)
        fs:SetJustifyH("LEFT")
        if gap ~= false then
            fs:SetWidth(math.max(100, (content:GetWidth() or 400) - (x or 4) - 24))
            local hgt = fs.GetStringHeight and fs:GetStringHeight() or 0
            if type(hgt) ~= "number" or hgt < (size or 10) then hgt = (size or 10) + 3 end
            y = y + hgt + (gap or 6)
        end
        return fs
    end
    local m = a and call(a.GetMap)
    if not m then
        text("Needs GuildLedger, which comes in the same pack: tick it in the AddOns list on the character screen.",
            10, C.textDim, 4, 12)
        return y
    end
    if not m.available then
        text("The world map is not available in this game version.", 10, C.textDim, 4, 12)
        return y
    end
    local set = function(...) call(a.SetMapLook, ...) end

    local share = UI:CreateCheckbox(content, "Show my position to guild members on the world map", 18)
    share:SetPoint("TOPLEFT", 4, -y)
    share.checkbox:SetChecked(m.share and true or false)
    share.checkbox.onChanged = function(_, on) call(a.SetMapShare, on and true or false) end
    y = y + 28
    text("Only while a guild member looks at the map of your zone; never in instances or boss fights; never saved.",
        10, C.silver, 34, 12)
    local pins = UI:CreateCheckbox(content, "Show guild members on my world map", 18)
    pins:SetPoint("TOPLEFT", 4, -y)
    pins.checkbox:SetChecked(m.pins and true or false)
    pins.checkbox.onChanged = function(_, on) call(a.SetMapPins, on and true or false) end
    y = y + 38

    -- A row of choice buttons; the current one is highlighted. Returns the new y.
    local function choices(label, list, current, onPick)
        y = y + 4
        text(label, 11, C.text, 4, false)
        y = y - 4
        local x = 150
        for _, c in ipairs(list) do
            local b = UI:CreateButton(content, c.text, c.w or 110, 22)
            b:SetPoint("TOPLEFT", x, -y)
            if current == c.id then
                b:SetBaseColor(C.accent.r * 0.34, C.accent.g * 0.34, C.accent.b * 0.34, 0.95)
                b.label:SetTextColor(C.gold.r, C.gold.g, C.gold.b)
            end
            b:SetScript("OnClick", function() onPick(c.id); rebuild(content) end)
            x = x + (c.w or 110) + 4
        end
        y = y + 32
    end

    -- Who sees me (only matters while sharing is on)
    if m.share and m.shareScope then
        choices("Who sees me", {
            { id = "all", text = "Zone, continent, world", w = 160 },
            { id = "zone", text = "Only my zone's map", w = 140 },
        }, m.shareScope, function(id) set("shareScope", id) end)
        text("\"Only my zone's map\": guild members see you only when they open the map of the zone you are in.",
            10, C.silver, 34, 10)
    end

    -- What I see: which guild members, on which maps, with names or not
    if m.near then
        choices("Show members", {
            { id = "any", text = "Anywhere", w = 100 },
            { id = "continent", text = "On my continent", w = 130 },
            { id = "zone", text = "In my zone", w = 100 },
        }, m.near, function(id) set("near", id) end)
        text("For example \"In my zone\": in Elwynn Forest you see only the guild members in Elwynn Forest,"
            .. " whichever map you open.", 10, C.silver, 34, 10)
    end
    if m.views then
        text("Show dots on", 11, C.text, 4, false)
        local x = 150
        for _, v in ipairs({ { id = "zone", text = "Zone maps" }, { id = "continent", text = "Continent maps" },
                             { id = "world", text = "World map" } }) do
            local cb = UI:CreateCheckbox(content, v.text, 18)
            cb:SetPoint("TOPLEFT", x, -(y - 2))
            cb.checkbox:SetChecked(m.views[v.id] and true or false)
            cb.checkbox.onChanged = function(_, on) set("view", v.id, on and true or false) end
            x = x + 140
        end
        y = y + 30
        local names = UI:CreateCheckbox(content, "Names next to the dots (otherwise when you point at a dot)", 18)
        names:SetPoint("TOPLEFT", 4, -y)
        names.checkbox:SetChecked(m.names and true or false)
        names.checkbox.onChanged = function(_, on) set("names", on and true or false) end
        y = y + 30
        if m.self ~= nil then
            local me = UI:CreateCheckbox(content, "Show my own dot (off: only the game's arrow shows you)", 18)
            me:SetPoint("TOPLEFT", 4, -y)
            me.checkbox:SetChecked(m.self and true or false)
            me.checkbox.onChanged = function(_, on) set("self", on and true or false) end
            y = y + 30
        end
        y = y + 6
    end

    -- Marker shape, with a preview of one dot as it looks on the map
    y = y + 4
    text("Marker", 11, C.text, 4, false)
    y = y - 4
    local x = 120
    for _, shape in ipairs({ "round", "square" }) do
        local b = UI:CreateButton(content, shape == "round" and "Round" or "Square", 80, 22)
        b:SetPoint("TOPLEFT", x, -y)
        if m.shape == shape then
            b:SetBaseColor(C.accent.r * 0.34, C.accent.g * 0.34, C.accent.b * 0.34, 0.95)
            b.label:SetTextColor(C.gold.r, C.gold.g, C.gold.b)
        end
        b:SetScript("OnClick", function() set("shape", shape); rebuild(content) end)
        x = x + 84
    end
    local preview = CreateFrame("Frame", nil, content)
    preview:SetPoint("TOPLEFT", x + 24, -(y - 3))
    preview:SetSize(40, 28)
    local rim = preview:CreateTexture(nil, "ARTWORK")
    rim:SetPoint("CENTER")
    local dot = preview:CreateTexture(nil, "OVERLAY")
    dot:SetPoint("CENTER")
    local sample = m.colors and m.colors[1]
    local look = { shape = m.shape, size = m.size, outline = m.outline }
    local function drawPreview()
        local r, g, b = 0.25, 0.78, 0.92
        if sample then r, g, b = sample.r, sample.g, sample.b end
        paint(dot, look.shape, r, g, b, 1)
        dot:SetSize(look.size, look.size)
        if look.outline then
            paint(rim, look.shape, 0, 0, 0, 0.85)
            rim:SetSize(look.size + 4, look.size + 4)
            rim:Show()
        else
            rim:Hide()
        end
    end
    drawPreview()
    y = y + 40

    -- Size (the slider shows its value above itself and min/max below: room on both sides)
    y = y + 14
    text("Size", 11, C.text, 4, false)
    local slider = CreateFrame("Slider", "AmazingHubMapDotSlider", content, "OptionsSliderTemplate")
    slider:SetPoint("TOPLEFT", 120, -(y + 1))
    slider:SetWidth(180)
    slider:SetMinMaxValues(m.sizeMin or 6, m.sizeMax or 24)
    slider:SetValueStep(1)
    slider:SetObeyStepOnDrag(true)
    slider:SetValue(m.size or 12)
    local name = slider:GetName()
    if _G[name .. "Low"] then _G[name .. "Low"]:SetText(tostring(m.sizeMin or 6)) end
    if _G[name .. "High"] then _G[name .. "High"]:SetText(tostring(m.sizeMax or 24)) end
    if _G[name .. "Text"] then _G[name .. "Text"]:SetText((m.size or 12) .. " px") end
    slider:SetScript("OnValueChanged", function(self, v)
        v = math.floor(v + 0.5)
        set("size", v)
        look.size = v
        if _G[name .. "Text"] then _G[name .. "Text"]:SetText(v .. " px") end
        drawPreview()
    end)
    y = y + 42

    local outline = UI:CreateCheckbox(content, "Dark outline (easier to see on bright maps)", 18)
    outline:SetPoint("TOPLEFT", 4, -y)
    outline.checkbox:SetChecked(m.outline and true or false)
    outline.checkbox.onChanged = function(_, on)
        set("outline", on and true or false)
        look.outline = on and true or false
        drawPreview()
    end
    y = y + 38

    -- Colours per class
    text("Colour per class", 11, C.text, 4, 4)
    local colors = m.colors or {}
    if #colors == 0 then
        text("The classes appear once the guild member list has loaded; open this page again in a moment.",
            10, C.silver, 12, 12)
    else
        local canPick = type(ColorPickerFrame) == "table" and type(ColorPickerFrame.SetupColorPickerAndShow) == "function"
        text(canPick and "Click a class to choose its colour. Right-click: back to the game's colour."
            or "Right-click a class: back to the game's colour. (The game's colour picker is not available.)",
            10, C.silver, 12, 8)
        local col, perRow, w = 0, 3, 150
        for _, c in ipairs(colors) do
            local b = CreateFrame("Button", nil, content)
            b:SetSize(w - 6, 20)
            b:SetPoint("TOPLEFT", 12 + col * w, -y)
            b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
            local sw = b:CreateTexture(nil, "ARTWORK")
            sw:SetSize(14, 14)
            sw:SetPoint("LEFT", 2, 0)
            sw:SetColorTexture(c.r, c.g, c.b, 1)
            local lbl = UI:CreateText(b, classLabel(c.class) .. (c.custom and "  *" or ""), 10, c.r, c.g, c.b)
            lbl:SetPoint("LEFT", sw, "RIGHT", 6, 0)
            b:SetScript("OnClick", function(_, button)
                if button == "RightButton" then
                    set("color", c.class)
                    rebuild(content)
                    return
                end
                Plus.PickColor(c.r, c.g, c.b, function(r, g, bl)
                    if type(r) ~= "number" then return end
                    set("color", c.class, r, g, bl)
                    sw:SetColorTexture(r, g, bl, 1)
                    lbl:SetTextColor(r, g, bl)
                    if sample and sample.class == c.class then
                        sample = { class = c.class, r = r, g = g, b = bl }
                        drawPreview()
                    end
                end)
            end)
            col = col + 1
            if col == perRow then col = 0; y = y + 24 end
        end
        if col > 0 then y = y + 24 end
        y = y + 10
    end

    local reset = UI:CreateButton(content, "Reset map options", 150, 22)
    reset:SetPoint("TOPLEFT", 4, -y)
    reset:SetScript("OnClick", function() set("reset"); rebuild(content) end)
    local openMap = UI:CreateButton(content, "Open world map", 140, 22)
    openMap:SetPoint("LEFT", reset, "RIGHT", 8, 0)
    openMap:SetScript("OnClick", function() AmazingHub:ToggleGuildMap() end)
    y = y + 34
    return y
end

----------------------------------------------------------------------
-- Hook into upstream's Settings page
----------------------------------------------------------------------

local original = AmazingHub.RefreshSettingsPanel
function AmazingHub:RefreshSettingsPanel(content, category)
    local headers = {}
    local made = rawget(UI, "CreateHeaderText")
    local function record(ui, parent, text, size, ...)
        local fs = made(ui, parent, text, size, ...)
        if parent == content and type(text) == "string" then headers[#headers + 1] = { fs = fs, text = text } end
        return fs
    end
    UI.CreateHeaderText = record
    local ok, err = pcall(original, self, content, category)
    UI.CreateHeaderText = made
    if not ok then error(err, 0) end

    if content.__settingsCat == "general" then
        local okMap, errMap = pcall(function()
            local function header(text) return record(UI, content, text, 12) end
            local y = (content:GetHeight() or 0) + 12
            y = Plus.BuildMessages(content, y, header) + 4
            y = Plus.BuildMap(content, y, header) + 4
            y = Plus.BuildCollector(content, y, header)
            content:SetHeight(math.max(1, y))
        end)
        if not okMap and AmazingHub.Debug then AmazingHub:Debug("World map settings: " .. tostring(errMap)) end
    end
    local okFold, errFold = pcall(Plus.Fold, content, headers)
    if not okFold and AmazingHub.Debug then AmazingHub:Debug("Settings sections: " .. tostring(errFold)) end
end
