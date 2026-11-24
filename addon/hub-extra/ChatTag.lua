----------------------------------------------------------------------
-- Amazing Hub - your own tag in guild chat (Amazing Forever Guild Pack 0.5.4; our own file, not upstream)
-- With "Annotate guild chat" on, the hub writes a tag in front of each guild line, e.g. "[11] (alt of Floyd
-- Mainchar)". Here a player picks what the others see in the brackets for their own lines: their own short text
-- ("Floy"), nothing at all, or the usual alt tag (the default).
-- The choice travels with the player's data that the hub already sends to the guild (DataCollector
-- GetBroadcastData: fields chatTag and chatTagOff; tools/rebrand-hub.py adds them), and each reader's
-- ChatTweaks uses it in place of the alt tag. A reader with an older hub keeps seeing the alt tag.
-- Text off the network is cleaned again before it reaches a chat line: no "|" codes, no brackets, at most
-- 16 characters.
--
-- Copied in by tools/rebrand-hub.py from addon/hub-extra/; edit it there.
----------------------------------------------------------------------
local UI = AmazingHub.UI
local C = AmazingHub.Colors

local T = {}
AmazingHub.ChatTag = T

T.MAX = 16 -- characters

-- Safe tag text, or "" when nothing usable is left.
function T.Clean(s)
    if type(s) ~= "string" then return "" end
    s = s:gsub("[%c|%(%)%[%]]", " "):gsub("%s+", " "):gsub("^ ", ""):gsub(" $", "")
    -- cut after MAX characters, never inside a UTF-8 sequence
    local n, cut = 0, #s
    for pos in s:gmatch("()[^\128-\191]") do
        n = n + 1
        if n > T.MAX then cut = pos - 1 break end
    end
    return (s:sub(1, cut):gsub(" $", ""))
end

-- true when this player wants no tag at all (sent as a boolean, so switching it off reaches the guild too)
function T.Off() return AmazingHub:GetSetting("chatTagOff") == true end

-- What this player chose: text ("" = the usual alt tag), off (true = no tag at all).
function T.Mine()
    local off = AmazingHub:GetSetting("chatTagOff") == true
    return T.Clean(AmazingHub:GetSetting("chatTag")), off
end

local function myKey()
    local name = AmazingHub.Compat and AmazingHub.Compat.PlayerName and AmazingHub.Compat.PlayerName()
    return type(name) == "string" and AmazingHub:GetPlayerKey(name:match("^([^-]+)") or name) or nil
end

-- The tag the member `key` chose for their lines: text, false (no tag), or nil (the usual alt tag).
function T.For(key)
    if type(key) ~= "string" then return nil end
    local tag, off
    if key == myKey() then
        tag, off = T.Mine()
    else
        local m = AmazingHub.db and AmazingHub.db.members and AmazingHub.db.members[key]
        if type(m) ~= "table" then return nil end
        tag, off = T.Clean(m.chatTag), m.chatTagOff == true
    end
    if off then return false end
    if tag ~= "" then return tag end
    return nil
end

-- Save a new choice and tell the guild at once (the normal broadcast would follow only later).
function T.Set(tag, off)
    local oldTag, oldOff = T.Mine()
    tag, off = T.Clean(tag), off == true
    if tag == oldTag and off == oldOff then return false end
    AmazingHub:SetSetting("chatTag", tag)
    AmazingHub:SetSetting("chatTagOff", off)
    local cs = AmazingHub.CommSystem
    if cs and cs.BroadcastMyData then pcall(cs.BroadcastMyData, cs, true) end
    return true
end

-- Settings > General > CHAT, under the alt tag switches. Returns the new y.
function T.BuildSettings(content, y)
    local ok, newY = pcall(function()
        local label = UI:CreateText(content, "What others see in the brackets for my lines:", 11,
            C.text.r, C.text.g, C.text.b)
        label:SetPoint("TOPLEFT", 28, -(y + 4))
        y = y + 22

        local box = CreateFrame("EditBox", nil, content, "InputBoxTemplate")
        box:SetSize(150, 20)
        box:SetPoint("TOPLEFT", 36, -y)
        box:SetAutoFocus(false)
        box:SetMaxLetters(40)
        local tag, off = T.Mine()
        box:SetText(tag)
        local function save()
            local _, nowOff = T.Mine()
            T.Set(box:GetText(), nowOff)
            box:SetText((T.Mine()))
        end
        box:SetScript("OnEnterPressed", function(self) save() self:ClearFocus() end)
        box:SetScript("OnEditFocusLost", save)
        box:SetScript("OnEscapePressed", function(self) self:SetText((T.Mine())) self:ClearFocus() end)

        local hint = UI:CreateText(content, "e.g. Floy. Empty: the usual (alt of ...). Press Enter to save.", 10,
            C.silver.r, C.silver.g, C.silver.b)
        hint:SetPoint("LEFT", box, "RIGHT", 10, 0)
        y = y + 26

        local none = UI:CreateCheckbox(content, "Show no tag at all for my lines", 16)
        none:SetPoint("TOPLEFT", 28, -y)
        none.checkbox:SetChecked(off)
        none.checkbox.onChanged = function(_, on) T.Set(box:GetText(), on and true or false) end
        y = y + 22

        local note = UI:CreateText(content, "Others see it when they use Amazing Hub 0.5.4 or newer with"
            .. " \"Annotate guild chat\" on.", 10, C.silver.r, C.silver.g, C.silver.b)
        note:SetPoint("TOPLEFT", 48, -y)
        y = y + 22
        return y
    end)
    if ok then return newY end
    if AmazingHub.Debug then AmazingHub:Debug("Chat tag setting: " .. tostring(newY)) end
    return y
end
