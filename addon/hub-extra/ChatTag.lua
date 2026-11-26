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

-- Settings > Chat > Guild chat, under the alt tag switches (patched into UI/SettingsPanel.lua's chat page).
-- F is upstream's Form; indent = its sub-option indent; enabled() = whether annotations are on.
function T.BuildForm(F, indent, enabled)
    local ok, err = pcall(function()
        -- Short label and no hint beside the box: the label column is at most 40 % of the page and cuts the rest
        -- (U3, 2026-11-24); the explanation is a note of its own that wraps.
        F:Field("My own tag", {
            w = 150, max = 40, indent = indent,
            get = function() return (T.Mine()) end,
            save = function(box)
                local _, off = T.Mine()
                T.Set(box:GetText(), off)
                box:SetText((T.Mine()))
            end,
        })
        F:Note("What others see in the brackets in front of your guild chat messages, e.g. Floy. Leave it empty for the usual tag"
            .. " (\"alt of\" and the main's name).", { indent = indent })
        F:Check("No tag at all in front of my guild chat messages",
            "Others see your choice when they use Amazing Hub 0.5.4 or newer with \"Annotate guild chat\" on.",
            function() local _, off = T.Mine(); return off end,
            function(on) T.Set((T.Mine()), on and true or false) end,
            { indent = indent, enabled = enabled })
    end)
    if not ok and AmazingHub.Debug then AmazingHub:Debug("Chat tag setting: " .. tostring(err)) end
end
