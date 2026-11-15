-- Comms (docs/dev/PACK_PLAN.md correction 2): the one way GuildLedger talks to other players' GuildLedger.
-- Hidden addon messages on the GUILD channel with the prefix "GuildLedger" (CLAUDE.md 5.6/5.7).
--
-- Modules register a handler per message kind (the first character of the message) and queue messages
-- with a priority: HIGH (small, time-sensitive: map, link), NORMAL (hello, who, need, got), BULK (relayed
-- chat lines). One message per SEND_GAP; the highest priority waiting goes first. The game's send result
-- decides: OK -> next; boss-fight lock -> hold and retry; "too fast" -> wait; anything else -> drop.

local _, ns = ...
local C = ns.Compat
local M = ns.Module("Comms")
ns.Comms = M

M.PREFIX = "GuildLedger"
M.SEP = "\t"
M.HIGH, M.NORMAL, M.BULK = 1, 2, 3

local SEND_GAP = 1.0 -- s between two outgoing messages (all kinds together)
local THROTTLE_WAIT = 4 -- s after the game said "too fast"
local LOCKDOWN_WAIT = 5 -- s between retries during a boss-fight lock
local QUEUE_MAX = 300 -- messages waiting, all priorities; the oldest of the lowest priority goes first

local queues = { {}, {}, {} } -- [priority] = { item, ... }
local nextSendAt = 0
local handlers = {} -- [kind] = function(sender, text, isSelf)
local stats = { sent = 0, received = 0, dropped = 0, lastResult = nil, sentByKind = {}, receivedByKind = {} }
M.stats = stats

---------------------------------------------------------------------------------------------------
-- Helpers shared by the modules
---------------------------------------------------------------------------------------------------

function M.IsSelf(sender)
    local me = C.PlayerName()
    if not me or type(sender) ~= "string" then return false end
    return sender == me or sender:sub(1, #me + 1) == me .. "-"
end

-- Split s into pieces of at most max bytes without cutting a UTF-8 character.
function M.SplitUtf8(s, max)
    local out, i, n = {}, 1, #s
    if n == 0 then return { "" } end
    while i <= n do
        local j = math.min(i + max - 1, n)
        while j < n and j > i do
            local b = s:byte(j + 1)
            if b < 128 or b >= 192 then break end -- next byte starts a character: cut here
            j = j - 1
        end
        out[#out + 1] = s:sub(i, j)
        i = j + 1
    end
    return out
end

function M.Waiting()
    return #queues[1] + #queues[2] + #queues[3]
end

---------------------------------------------------------------------------------------------------
-- Queue
---------------------------------------------------------------------------------------------------

-- item = { msgs = { text, ... }, prio = M.NORMAL,
--          skip = function() -> true: drop it before its first message goes out,
--          onSent = function() after its last message went out, onDrop = function() if dropped }
function M.Queue(item)
    item.idx = 1
    local prio = (item.prio == M.HIGH or item.prio == M.BULK) and item.prio or M.NORMAL
    if M.Waiting() >= QUEUE_MAX then
        for p = M.BULK, M.HIGH, -1 do
            if #queues[p] > 0 then
                local old = table.remove(queues[p], 1)
                stats.dropped = stats.dropped + 1
                if old.onDrop then ns.Safe("Comms.onDrop", old.onDrop) end
                break
            end
        end
    end
    table.insert(queues[prio], item)
end

function M.Send(text, prio)
    M.Queue({ msgs = { text }, prio = prio })
end

local function sendNext()
    if C.Clock() < nextSendAt or C.CommBlocked() then return end
    local q
    for p = M.HIGH, M.BULK do
        if #queues[p] > 0 then q = queues[p] break end
    end
    if not q then return end
    local item = q[1]
    if item.idx == 1 and item.skip and item.skip() then
        table.remove(q, 1)
        if item.onDrop then ns.Safe("Comms.onDrop", item.onDrop) end
        return
    end
    local text = item.msgs[item.idx]
    local r = C.SendGuild(M.PREFIX, text)
    if r ~= stats.lastResult then
        ns.Debug("messages: send result " .. tostring(r) .. " (0 = ok)", true)
        stats.lastResult = r
    end
    if r == C.SEND_OK then
        local kind = text:sub(1, 1)
        stats.sent = stats.sent + 1
        stats.sentByKind[kind] = (stats.sentByKind[kind] or 0) + 1
        item.idx = item.idx + 1
        if item.idx > #item.msgs then
            table.remove(q, 1)
            if item.onSent then ns.Safe("Comms.onSent", item.onSent) end
        end
    elseif r == C.SEND_LOCKDOWN then
        nextSendAt = C.Clock() + LOCKDOWN_WAIT
    elseif r and C.SEND_THROTTLED[r] then
        nextSendAt = C.Clock() + THROTTLE_WAIT
    else
        table.remove(q, 1) -- refused for good (or no API): drop, never retry forever
        stats.dropped = stats.dropped + 1
        if item.onDrop then ns.Safe("Comms.onDrop", item.onDrop) end
        ns.Debug("messages: refused by the game (" .. tostring(r) .. ")")
    end
end

---------------------------------------------------------------------------------------------------
-- Receiving
---------------------------------------------------------------------------------------------------

function M.Handle(kind, fn)
    handlers[kind] = fn
end

ns.On("CHAT_MSG_ADDON", function(prefix, text, channel, sender)
    if C.IsSecret(prefix, text, channel, sender) then return end
    if prefix ~= M.PREFIX or channel ~= "GUILD" or type(text) ~= "string" or type(sender) ~= "string" then return end
    local kind = text:sub(1, 1)
    local me = M.IsSelf(sender)
    if not me then
        stats.received = stats.received + 1
        stats.receivedByKind[kind] = (stats.receivedByKind[kind] or 0) + 1
    end
    local fn = handlers[kind]
    if fn then fn(sender, text, me) end
end)

---------------------------------------------------------------------------------------------------
-- Startup, status
---------------------------------------------------------------------------------------------------

function M.OnInit()
    if not C.HasComm then return end
    C.RegisterPrefix(M.PREFIX)
    C.Ticker(SEND_GAP, function() ns.Safe("Comms.send", sendNext) end)
end

local function sendText(r)
    if r == nil then return "nothing sent yet" end
    if r == C.SEND_OK then return "OK" end
    if C.SEND_THROTTLED[r] then return "the game said 'too fast', waiting a moment" end
    if r == C.SEND_LOCKDOWN then return "held during a boss fight" end
    return "refused by the game (code " .. tostring(r) .. ")"
end

-- Lines for the "Sharing with other players" section of /gl status.
function M.StatusLines()
    ns.Line(string.format("Messages sent: %d. Received from others: %d.", stats.sent, stats.received))
    ns.Line("Last send: " .. sendText(stats.lastResult) .. ".")
    local waiting = M.Waiting()
    if waiting > 0 then
        ns.Line(string.format("Waiting to send: %d message(s)%s.", waiting,
            C.InLockdown() and " (held until the boss-fight lock ends)" or ""))
    end
    if stats.dropped > 0 then
        ns.Line(string.format("Messages dropped (too many waiting or refused): %d.", stats.dropped))
    end
end
