-- Welcome (admin's wish, 2026-11-18): at login (not on /reload) a greeting from Maupa's sprite and the guild's
-- message of the day, in the player's own chat window. Nothing is sent. On by default; off with /gl welcome off
-- or Amazing Hub's Settings -> CHAT MESSAGES.
-- The message of the day comes from the GUILD_MOTD event (GuildInfoDocumentation.lua; secret only in a chat
-- lockdown). C_GuildInfo.GetMOTD is not used: it is marked HasRestrictions there.

local _, ns = ...
local C = ns.Compat
local M = ns.Module("Welcome")
ns.Welcome = M

local DELAY = 8 -- s after login: after the game's own login lines
local WAIT_MOTD = 20 -- s: how much longer to wait for the message of the day
local GREETING = "Maupa's sprite wishes you a wonderful journey and blows a kiss your way!"

local motd -- the latest message of the day, plain string
local said = false

function M.On() return ns.Store.Opts().welcome ~= false end

-- The message of the day as one plain line: control characters become spaces, "|" shows as itself.
function M.Clean(text)
    return (text:gsub("%c", " "):gsub("|", "||"))
end

function M.Say()
    if said or not M.On() or not DEFAULT_CHAT_FRAME then return end
    said = true
    DEFAULT_CHAT_FRAME:AddMessage("|cffff77cc" .. GREETING .. "|r")
    if motd and motd:match("%S") then
        DEFAULT_CHAT_FRAME:AddMessage("|cff33ff99The guild message of the day is:|r " .. M.Clean(motd))
    end
end

ns.On("GUILD_MOTD", function(text)
    if C.IsSecret(text) or type(text) ~= "string" then return end
    motd = text
end)

ns.On("PLAYER_ENTERING_WORLD", function(isInitialLogin)
    if C.IsSecret(isInitialLogin) or isInitialLogin ~= true or said then return end
    local waited = 0
    local function try()
        if motd ~= nil or waited >= WAIT_MOTD then
            M.Say()
            return
        end
        waited = waited + 2
        C.After(2, function() ns.Safe("Welcome.try", try) end)
    end
    C.After(DELAY, function() ns.Safe("Welcome.try", try) end)
end)
