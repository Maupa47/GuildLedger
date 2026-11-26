----------------------------------------------------------------------
-- Amazing Hub - a craft order sent to one crafter also whispers them (Amazing Forever Guild Pack 0.7.0; our own
-- file, not upstream)
--
-- Asked by the admin in round H-b (2026-11-26). An order goes to the guild's crafters through the hub
-- (Modules/CraftOrders.lua, addon messages on GUILD), and a crafter without the hub open never hears of it. So
-- when the player picks one crafter ("To <name> only") and presses Send order, that crafter also gets one
-- whisper saying so. An order to anyone only goes into the orders list, as before. The whisper leaves from the
-- player's own click (Forever drops chat lines an addon sends by itself), through Compat.SendWhisper, which lets
-- whispers reach guild members only.
--
-- Copied in by tools/rebrand-hub.py from addon/hub-extra/; edit it there.
----------------------------------------------------------------------
local OW = {}
AmazingHub.PackOrderWhisper = OW

-- The whisper's text for order `o`.
function OW.Text(o)
    local _, link = AmazingHub.Compat.GetItemInfo(o.item)
    local what = link or ("item " .. tostring(o.item))
    if (o.n or 1) > 1 then what = what .. " x" .. o.n end
    return "[Amazing Hub] I sent you a craft order: " .. what .. ". Open Amazing Hub > Crafts > Orders to accept it."
end

-- Whispers the crafter of order `o` when it went to one. Returns whether a whisper went.
function OW.Tell(o)
    if type(o) ~= "table" or type(o.to) ~= "string" or o.to == "" then return false end
    local O = AmazingHub.CraftOrders
    local name = (O and O.NameOf) and O.NameOf(o.to) or o.to
    -- A member key may carry a realm; Forever names never hold a hyphen (as AmazingHub:OpenWhisper).
    if AmazingHub.Client and AmazingHub.Client.has and AmazingHub.Client.has.surnames then
        name = name:match("^([^-]+)") or name
    end
    local target = AmazingHub.WhisperTarget and AmazingHub:WhisperTarget(name) or name
    local text = OW.Text(o)
    if AmazingHub.NoteWhisper then AmazingHub:NoteWhisper(target) end
    local queue = AmazingHub.WhisperQueue
    if queue and queue.SendNow then return queue:SendNow(target, text) and true or false end
    return AmazingHub.Compat.SendWhisper(text, target) and true or false
end

local O = AmazingHub.CraftOrders
if O and O.Place then
    local place = O.Place
    function O:Place(item, opts, ...)
        local o, why = place(self, item, opts, ...)
        if o and o.to then
            local ok, err = pcall(OW.Tell, o)
            if not ok and AmazingHub.RecordError then AmazingHub:RecordError("OrderWhisper: " .. tostring(err)) end
        end
        return o, why
    end
end
