----------------------------------------------------------------------
-- Amazing Hub - Ledger tab (Amazing Forever Guild Pack, Phase 10; our own file, not upstream)
-- Shows GuildLedger's status (the same lines as /gl status), its map switches and a newer version
-- seen in the guild, through the global GuildLedgerAPI. Without GuildLedger the tab says so and
-- nothing errors. Copied in by tools/rebrand-hub.py from tools/hub-extra/; edit it there.
----------------------------------------------------------------------
local UI = AmazingHub.UI
local C = AmazingHub.Colors

local REFRESH = 5 -- seconds, while the tab is shown
local WHITE = "Interface\\Buttons\\WHITE8x8"

-- A text box in the hub's look (as UI/CorePanel.lua draws its inputs).
local function makeInput(parent, w, placeholder)
    local b = CreateFrame("EditBox", nil, parent, "BackdropTemplate")
    b:SetSize(w, 22)
    b:SetBackdrop({ bgFile = WHITE, edgeFile = WHITE, edgeSize = 1 })
    b:SetBackdropColor(0.05, 0.05, 0.066, 1)
    b:SetBackdropBorderColor(C.border.r, C.border.g, C.border.b, 0.4)
    AmazingHub:ApplyFont(b, 11)
    b:SetTextColor(C.white.r, C.white.g, C.white.b)
    b:SetTextInsets(6, 6, 0, 0)
    b:SetAutoFocus(false)
    b:SetMaxLetters(12)
    b:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
    local ph = b:CreateFontString(nil, "OVERLAY")
    AmazingHub:ApplyFont(ph, 10)
    ph:SetPoint("LEFT", 6, 0)
    ph:SetTextColor(0.4, 0.4, 0.4)
    ph:SetText(placeholder)
    b:SetScript("OnTextChanged", function(self)
        if self:GetText() ~= "" then ph:Hide() else ph:Show() end
    end)
    return b
end

-- The bridge, or nil when GuildLedger is missing, disabled, or speaks another API version.
local function api()
    local a = GuildLedgerAPI -- nil when GuildLedger is not loaded
    if type(a) == "table" and a.apiVersion == 1 then return a end
end

local function call(fn, ...)
    if type(fn) ~= "function" then return nil end
    local ok, a, b = pcall(fn, ...)
    if ok then return a, b end
end

AmazingHub.Ledger = { API = api }

-- The hub's own guild map is off (GuildLedger shares positions): its map command opens the world map,
-- where GuildLedger draws the guild members.
function AmazingHub:ToggleGuildMap()
    if AmazingHub.Compat and AmazingHub.Compat.OpenWorldMap then AmazingHub.Compat.OpenWorldMap() end
end

function AmazingHub:CreateLedgerPanel(parent)
    local scroll, content = UI:CreateScrollFrame(parent, "AmazingHubLedgerScroll")
    scroll:SetPoint("TOPLEFT", 4, -4)
    scroll:SetPoint("BOTTOMRIGHT", -26, 4)
    local pool, used, y = {}, 0, 0
    local function width()
        local w = scroll:GetWidth() or 0
        return w > 1 and w or 400
    end

    local function line(text, size, col, indent, gap)
        used = used + 1
        local fs = pool[used]
        if not fs then
            fs = UI:CreateText(content, "", size, col.r, col.g, col.b)
            fs:SetJustifyH("LEFT")
            pool[used] = fs
        end
        AmazingHub:ApplyFont(fs, size)
        fs:SetTextColor(col.r, col.g, col.b)
        fs:ClearAllPoints()
        fs:SetPoint("TOPLEFT", indent or 4, -y)
        fs:SetWidth(math.max(1, width() - (indent or 4) - 8))
        fs:SetText(text)
        fs:Show()
        y = y + (fs:GetStringHeight() or size) + (gap or 6)
    end

    local share = UI:CreateCheckbox(content, "Show my position to guild members on the world map", 18)
    local pins = UI:CreateCheckbox(content, "Show guild members on my world map", 18)
    local open = UI:CreateButton(content, "Open world map", 140)
    open:SetScript("OnClick", function() AmazingHub:ToggleGuildMap() end)
    share.checkbox.onChanged = function(_, checked) local a = api(); if a then call(a.SetMapShare, checked) end end
    pins.checkbox.onChanged = function(_, checked) local a = api(); if a then call(a.SetMapPins, checked) end end

    -- Discord link: the code from /link in the guild Discord, same as /gl link CODE.
    local refresh
    local codeBox = makeInput(content, 150, "code from Discord")
    local linkBtn = UI:CreateButton(content, "Link", 80)
    linkBtn:SetPoint("LEFT", codeBox, "RIGHT", 8, 0)
    local linkMsg
    local function submit()
        local a = api()
        if not a then return end
        local ok, msg = call(a.RequestLink, codeBox:GetText())
        linkMsg = { ok = ok, text = msg or "The code could not be sent." }
        if ok then codeBox:SetText("") end
        codeBox:ClearFocus()
        if refresh then AmazingHub:SafeCall(refresh) end
    end
    codeBox:SetScript("OnEnterPressed", submit)
    linkBtn:SetScript("OnClick", submit)

    local function place(widget, h)
        widget:ClearAllPoints()
        widget:SetPoint("TOPLEFT", 8, -y)
        widget:Show()
        y = y + h
    end

    function refresh()
        for _, fs in ipairs(pool) do fs:Hide() end
        used, y = 0, 4
        content:SetWidth(width())
        local a = api()
        if not a then
            share:Hide(); pins:Hide(); open:Hide(); codeBox:Hide(); linkBtn:Hide()
            line("GuildLedger is not running.", 13, C.gold)
            line("It comes in the same pack (Amazing Forever Guild Pack). On the character screen, open AddOns,"
                .. " tick \"GuildLedger (Amazing Forever Guild Pack)\" and log in again.", 11, C.textDim, 8)
            content:SetHeight(math.max(1, y))
            return
        end

        line("GUILDLEDGER " .. tostring(call(a.Version) or "?"), 13, C.gold, 4, 4)
        line("Keeps the guild chat and roster log for Discord, and shows guild members on the world map.",
            11, C.textDim, 8, 10)
        local newer, who = call(a.NewerVersion)
        if newer then
            line(string.format("Update available: version %s (seen from %s). Update the Amazing Forever Guild Pack"
                .. " in your addon manager.", tostring(newer), tostring(who)), 11, C.red, 8, 10)
        end

        line("WORLD MAP", 12, C.gold)
        local m = call(a.GetMap) or {}
        share.checkbox:SetChecked(m.share and true or false)
        pins.checkbox:SetChecked(m.pins and true or false)
        if m.available then
            share.checkbox:Enable(); pins.checkbox:Enable()
        else
            share.checkbox:Disable(); pins.checkbox:Disable()
        end
        place(share, 26)
        place(pins, 30)
        place(open, 34)

        line("DISCORD LINK", 12, C.gold)
        line("Links your characters to your Discord account. In the guild Discord type /link, then enter the code"
            .. " here and confirm in Discord.", 11, C.textDim, 8, 6)
        local link = call(a.GetLink) or {}
        if link.code and link.acked then
            line("Your code " .. tostring(link.code) .. " reached a collector: confirm it in Discord.", 11, C.green, 8)
        elseif link.code and not link.expired then
            line("Your code " .. tostring(link.code) .. " is waiting for a collector to be online.", 11, C.text, 8)
        end
        place(codeBox, 30)
        linkBtn:Show()
        if linkMsg then line(linkMsg.text, 11, linkMsg.ok and C.green or C.red, 8, 10) end
        y = y + 6

        line("STATUS (same as /gl status)", 12, C.gold)
        local st = call(a.GetStatus)
        for _, l in ipairs(st and st.lines or {}) do
            if l.kind == "head" then
                y = y + 4
                line(tostring(l.text), 12, C.gold, 4, 4)
            elseif l.kind == "line" then
                line(tostring(l.text), 11, C.text, 12, 3)
            else -- "print": the opening line, or why GuildLedger switched itself off
                line(tostring(l.text), 11, C.textDim, 4, 3)
            end
        end
        content:SetHeight(math.max(1, y))
    end

    local ticker
    parent:HookScript("OnShow", function()
        AmazingHub:SafeCall(refresh)
        if not ticker and C_Timer and C_Timer.NewTicker then
            ticker = C_Timer.NewTicker(REFRESH, function()
                if parent:IsShown() then AmazingHub:SafeCall(refresh) end
            end)
        end
    end)
    parent:HookScript("OnHide", function()
        if ticker then ticker:Cancel(); ticker = nil end
    end)
    scroll:HookScript("OnSizeChanged", function() if parent:IsShown() then AmazingHub:SafeCall(refresh) end end)
    AmazingHub:SafeCall(refresh)
    return refresh
end

UI:RegisterFeature({
    id = "ledger", label = "Ledger", order = 96,
    build = function(c, win) return AmazingHub:CreateLedgerPanel(c, win) end,
})
