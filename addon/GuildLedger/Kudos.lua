-- Kudos: a guild in-joke (admin's wish, 2026-11-15). On the PC of the character "Doc Taco" only, a friendly line
-- in their own chat window every 30 minutes. Shown locally; nothing is sent to anyone. On purpose not affected by
-- the chat-messages switch (it is the whole point).

local _, ns = ...
local C = ns.Compat
local M = ns.Module("Kudos")
ns.Kudos = M

local WHO = "doc taco" -- compared without case; the game may write the space as a hyphen
local EVERY = 1800 -- s
local TEXT = "We all think you are really pretty"

-- Is this the character the line is for? (the player's own name, as UnitName("player") gives it: no realm)
function M.IsFor(name)
    if type(name) ~= "string" then return false end
    return (name:lower():gsub("%-", " ")) == WHO
end

function M.Say()
    if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage("|cffff77cc" .. TEXT .. "|r") end
end

function M.OnInit()
    if not M.IsFor(C.PlayerName()) then return end
    C.Ticker(EVERY, function() ns.Safe("Kudos.say", M.Say) end)
end
