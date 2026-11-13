-- Relay (CLAUDE.md 5.7): a collector asks "who has text for these times?" over hidden guild addon
-- messages; members (and other collectors) answer with the lines they captured live; the collector
-- fills its text-less rows after checking stream, time and author, and confirms so everyone drops them.
--   H version role held      hello
--   N stream t1-t2,t3-t4     need (collector)
--   T id k/n chunk           one line, chunk 1 = "s TAB t TAB author TAB guid TAB fd TAB text..."
--   G id,id,...              got it (collector)

local _, ns = ...
local C, S = ns.Compat, ns.Store
local M = ns.Module("Relay")
ns.Relay = M

local PREFIX = "GuildLedger"
local SEP = "\t"
local SEND_GAP = 1.0 -- s between two outgoing messages
local THROTTLE_WAIT = 4 -- s after the game said "too fast"
local QUEUE_MAX = 300
local CHUNK = 200 -- bytes of line data per T message (whole message stays under 255)
local HELLO_DELAY = 20
local ANSWER_MIN, ANSWER_MAX = 2, 8 -- s random wait before answering a need
local ANSWER_CAP = 150 -- lines per need
local NEED_WINDOW = 27 * 3600 -- how far back the server history (and so the gaps) reach
local RANGE_JOIN = 300 -- s: text-less rows closer than this form one range
local NEED_RANGES = 30
local NEED_EVERY = 900
local NEED_MIN_GAP = 120
local ACK_EVERY = 5
local ACK_IDS = 6
local PRUNE_EVERY = 300
local PARTS_TTL = 120
local HEARD_TTL = 3600

local queue = {} -- { msgs = { text, ... }, idx = 1, id = line id or nil }
local nextSendAt = 0
local heard = {} -- [id] = GetTime(): somebody already sent or confirmed this line
local partsBuf = {} -- [sender .. "|" .. id] = { n, chunks = {}, got, at }
local pendingAck = {}
local lastNeed, needScheduled = -1e9, false
local collectors = {} -- [sender] = GetTime() of their last hello
local stats = { sent = 0, received = 0, answered = 0, relayed = 0, rejected = 0, dropped = 0, lastNeed = nil,
    lastResult = nil }
local registered, helloSent = false, false
local lastForeignText = -1e9 -- GetTime() of the last line another player sent
local FOREIGN_QUIET = 5 -- s: someone else is answering while their lines keep coming

---------------------------------------------------------------------------------------------------
-- Helpers
---------------------------------------------------------------------------------------------------

local function club()
    if ns.Chat and ns.Chat.Club then return ns.Chat.Club() end
end

local function isSelf(sender)
    local me = C.PlayerName()
    if not me or type(sender) ~= "string" then return false end
    return sender == me or sender:sub(1, #me + 1) == me .. "-"
end

-- Split s into pieces of at most max bytes without cutting a UTF-8 character.
local function splitUtf8(s, max)
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
M.splitUtf8 = splitUtf8

local function enqueue(item)
    if #queue >= QUEUE_MAX then
        table.remove(queue, 1)
        stats.dropped = stats.dropped + 1
    end
    item.idx = 1
    queue[#queue + 1] = item
end

local function enqueueText(text) enqueue({ msgs = { text } }) end

---------------------------------------------------------------------------------------------------
-- Sending: one message per SEND_GAP, held while the game would refuse it
---------------------------------------------------------------------------------------------------

local function sendNext()
    local item = queue[1]
    if not item or C.Clock() < nextSendAt or C.CommBlocked() then return end
    if item.id and item.idx == 1 and heard[item.id] then -- another player sent or confirmed it meanwhile
        table.remove(queue, 1)
        return
    end
    local r = C.SendGuild(PREFIX, item.msgs[item.idx])
    if r ~= stats.lastResult then
        ns.Debug("relay: send result " .. tostring(r) .. " (0 = ok)")
        stats.lastResult = r
    end
    if r == C.SEND_OK then
        stats.sent = stats.sent + 1
        item.idx = item.idx + 1
        if item.idx > #item.msgs then
            table.remove(queue, 1)
            if item.id then
                heard[item.id] = C.Clock()
                stats.answered = stats.answered + 1
            end
        end
    elseif r == C.SEND_LOCKDOWN then
        nextSendAt = C.Clock() + 5 -- boss fight: keep it, try again later
    elseif r and C.SEND_THROTTLED[r] then
        nextSendAt = C.Clock() + THROTTLE_WAIT
    else
        table.remove(queue, 1) -- refused for good (or no API): drop, never retry forever
        stats.dropped = stats.dropped + 1
        ns.Debug("relay: message refused (" .. tostring(r) .. ")")
    end
end

---------------------------------------------------------------------------------------------------
-- Member side: answer a need with own lines
---------------------------------------------------------------------------------------------------

local function lineMessages(row)
    local payload = table.concat({ row.s, tostring(row.t), row.a or "", row.g or "", row.fd and "1" or "0",
        row.m }, SEP)
    local chunks = splitUtf8(payload, CHUNK)
    local msgs = {}
    for k, chunk in ipairs(chunks) do
        msgs[k] = table.concat({ "T", row.id, k .. "/" .. #chunks, chunk }, SEP)
    end
    return msgs
end
M.lineMessages = lineMessages

local function onNeed(sender, s, rangesText)
    local cid = club()
    if not cid or isSelf(sender) then return end
    local ranges = {}
    for a, b in rangesText:gmatch("(%d+)%-(%d+)") do ranges[#ranges + 1] = { tonumber(a), tonumber(b) } end
    if #ranges == 0 then return end
    local queued = {}
    for _, item in ipairs(queue) do if item.id then queued[item.id] = true end end
    local rows = {}
    for _, row in ipairs(S.Guild(cid).chat) do
        if row.s == s and row.m and row.src == "live" and not heard[row.id] and not queued[row.id] then
            for _, r in ipairs(ranges) do
                if row.t >= r[1] and row.t <= r[2] then rows[#rows + 1] = row break end
            end
        end
    end
    if #rows == 0 then return end
    table.sort(rows, function(x, y) return x.t < y.t end)
    while #rows > ANSWER_CAP do table.remove(rows) end
    ns.Debug(string.format("relay: %s needs %d range(s); I have %d line(s)", sender, #ranges, #rows))
    -- A random wait spreads the answers. Whoever starts first answers; the others wait until that player's
    -- lines stop coming and then send only what is still missing (they heard every line sent).
    local tries = 0
    local function answer()
        tries = tries + 1
        if C.Clock() - lastForeignText < FOREIGN_QUIET and tries < 60 then
            C.After(FOREIGN_QUIET, function() ns.Safe("Relay.answer", answer) end)
            return
        end
        for _, row in ipairs(rows) do
            if not heard[row.id] then enqueue({ msgs = lineMessages(row), id = row.id }) end
        end
    end
    C.After(math.random(ANSWER_MIN, ANSWER_MAX), function() ns.Safe("Relay.answer", answer) end)
end

---------------------------------------------------------------------------------------------------
-- Collector side: ask for gaps, accept checked lines, confirm
---------------------------------------------------------------------------------------------------

-- "N" messages for this collector's text-less rows of the last NEED_WINDOW, newest ranges first.
local function buildNeeds(now)
    local cid, letters = club()
    if not cid then return {} end
    local byStream = {}
    for _, row in ipairs(S.Guild(cid).chat) do
        if not row.m and row.src == "meta" and row.a ~= "?" and row.t >= now - NEED_WINDOW and letters[row.s] then
            byStream[row.s] = byStream[row.s] or {}
            table.insert(byStream[row.s], row.t)
        end
    end
    local ranges = {}
    for s, ts in pairs(byStream) do
        table.sort(ts)
        local lo, hi = ts[1], ts[1]
        for i = 2, #ts do
            if ts[i] - hi > RANGE_JOIN then
                ranges[#ranges + 1] = { s = s, lo = lo, hi = hi }
                lo = ts[i]
            end
            hi = ts[i]
        end
        ranges[#ranges + 1] = { s = s, lo = lo, hi = hi }
    end
    table.sort(ranges, function(a, b) return a.hi > b.hi end)
    local msgs, cur, curS = {}, nil, nil
    for i = 1, math.min(#ranges, NEED_RANGES) do
        local r = ranges[i]
        local piece = (r.lo - 1) .. "-" .. (r.hi + 1)
        if cur and curS == r.s and #cur + #piece + 1 <= 240 then
            cur = cur .. "," .. piece
        else
            if cur then msgs[#msgs + 1] = cur end
            cur, curS = "N" .. SEP .. r.s .. SEP .. piece, r.s
        end
    end
    if cur then msgs[#msgs + 1] = cur end
    return msgs
end
M.buildNeeds = buildNeeds

local function sendNeeds()
    needScheduled = false
    if not S.IsCollector() or not club() then return end
    local msgs = buildNeeds(C.Now())
    lastNeed = C.Clock()
    if #msgs == 0 then return end
    stats.lastNeed = C.Now()
    ns.Debug(string.format("relay: asking for text gaps (%d message(s))", #msgs))
    for _, m in ipairs(msgs) do enqueueText(m) end
end

local function scheduleNeeds(delay)
    if needScheduled or not S.IsCollector() then return end
    needScheduled = true
    C.After(delay, function() ns.Safe("Relay.need", sendNeeds) end)
end

-- History sync finished (Chat.lua): the gaps are known now.
function ns.RelaySynced() scheduleNeeds(30) end

local function accept(sender, id, payload)
    local cid = club()
    if not cid then return end
    local s, t, a, g, fd, text = payload:match("^(%a)\t(%d+)\t([^\t]*)\t([^\t]*)\t([01])\t(.*)$")
    if not s then stats.rejected = stats.rejected + 1 return end
    local row = S.HasChat(cid, s, id)
    if not row then return end -- not in this collector's history: nothing to check it against
    if row.m then pendingAck[#pendingAck + 1] = id return end -- already has text: just confirm
    local sameAuthor = (row.g and g ~= "" and row.g == g) or (not row.g and (row.a == a or row.a == "?"))
    if not sameAuthor or math.abs(tonumber(t) - row.t) > 1 or text == "" then
        stats.rejected = stats.rejected + 1
        ns.Debug("relay: rejected line " .. id .. " from " .. sender)
        return
    end
    row.m = text
    row.src = "live"
    row.rb = sender
    if fd == "1" then row.fd = true end
    if row.a == "?" and a ~= "" then row.a = a end
    S.unsaved = S.unsaved + 1
    stats.relayed = stats.relayed + 1
    pendingAck[#pendingAck + 1] = id
end

local function flushAcks()
    while #pendingAck > 0 do
        local ids = {}
        while #pendingAck > 0 and #ids < ACK_IDS do ids[#ids + 1] = table.remove(pendingAck, 1) end
        enqueueText("G" .. SEP .. table.concat(ids, ","))
    end
end

---------------------------------------------------------------------------------------------------
-- Receiving
---------------------------------------------------------------------------------------------------

local function onText(sender, id, k, n, chunk)
    heard[id] = C.Clock() -- members: someone is sending this line, skip it
    lastForeignText = C.Clock()
    if not S.IsCollector() or n < 1 or n > 20 or k < 1 or k > n then return end
    local key = sender .. "|" .. id
    local p = partsBuf[key]
    if not p then
        p = { n = n, chunks = {}, got = 0, at = C.Clock() }
        partsBuf[key] = p
    end
    if p.n ~= n or p.chunks[k] then return end
    p.chunks[k] = chunk
    p.got = p.got + 1
    if p.got < n then return end
    partsBuf[key] = nil
    accept(sender, id, table.concat(p.chunks))
end

local function onGot(idsText)
    local ids, any = {}, false
    for id in idsText:gmatch("[^,]+") do
        ids[id] = true
        heard[id] = C.Clock()
        any = true
    end
    local cid = club()
    if any and cid and not S.IsCollector() then S.RemoveChat(cid, ids) end -- members drop confirmed lines
end

ns.On("CHAT_MSG_ADDON", function(prefix, text, channel, sender)
    if C.IsSecret(prefix, text, channel, sender) then return end
    if prefix ~= PREFIX or channel ~= "GUILD" or type(text) ~= "string" or type(sender) ~= "string" then return end
    if not isSelf(sender) then stats.received = stats.received + 1 end
    local kind = text:sub(1, 1)
    if kind == "T" then
        local id, k, n, chunk = text:match("^T\t([^\t]+)\t(%d+)/(%d+)\t(.*)$")
        if id and not isSelf(sender) then onText(sender, id, tonumber(k), tonumber(n), chunk) end
    elseif kind == "N" then
        local s, ranges = text:match("^N\t(%a)\t(.+)$")
        if s then onNeed(sender, s, ranges) end
    elseif kind == "G" then
        local ids = text:match("^G\t(.+)$")
        if ids then onGot(ids) end
    elseif kind == "H" then
        local ver, role = text:match("^H\t([^\t]*)\t([cm])")
        if not ver or isSelf(sender) then return end
        if role == "c" then collectors[sender] = C.Clock() end
        ns.Debug(string.format("relay: hello from %s (%s, v%s)", sender, role == "c" and "collector" or "member", ver))
        -- A member who just logged in may hold text for our gaps.
        if role == "m" and S.IsCollector() and C.Clock() - lastNeed >= NEED_MIN_GAP then scheduleNeeds(5) end
    end
end)

---------------------------------------------------------------------------------------------------
-- Startup, housekeeping, status
---------------------------------------------------------------------------------------------------

local function hello()
    local cid = club()
    if not cid then return false end
    local held = S.IsCollector() and 0 or #S.Guild(cid).chat
    enqueueText(table.concat({ "H", S.VERSION, S.IsCollector() and "c" or "m", tostring(held) }, SEP))
    helloSent = true
    return true
end

local function housekeeping()
    local now = C.Clock()
    for id, at in pairs(heard) do if now - at > HEARD_TTL then heard[id] = nil end end
    for key, p in pairs(partsBuf) do if now - p.at > PARTS_TTL then partsBuf[key] = nil end end
    for who, at in pairs(collectors) do if now - at > 4 * 3600 then collectors[who] = nil end end
    local cid = club()
    if cid and not S.IsCollector() then S.PruneMember(cid, C.Now()) end
end

function M.OnInit()
    if not C.HasComm then return end
    if not registered then
        C.RegisterPrefix(PREFIX)
        registered = true
    end
    C.Ticker(SEND_GAP, function() ns.Safe("Relay.send", sendNext) end)
    C.Ticker(ACK_EVERY, function() ns.Safe("Relay.ack", flushAcks) end)
    C.Ticker(PRUNE_EVERY, function() ns.Safe("Relay.prune", housekeeping) end)
    C.Ticker(NEED_EVERY, function() ns.Safe("Relay.need", sendNeeds) end)
    C.Ticker(HELLO_DELAY, function()
        if not helloSent then ns.Safe("Relay.hello", hello) end
    end)
end

function M.Status()
    if not C.HasComm then
        ns.Print("relay: |cffffaa00off|r (addon messages not available)")
        return
    end
    local cid = club()
    local names = {}
    for who in pairs(collectors) do names[#names + 1] = who end
    table.sort(names)
    if S.IsCollector() then
        ns.Print(string.format("relay: role |cff33ff33collector|r; filled %d line(s) from members, rejected %d;"
            .. " last ask %s; queue %d", stats.relayed, stats.rejected,
            stats.lastNeed and date("%H:%M", stats.lastNeed) or "never", #queue))
    else
        ns.Print(string.format("relay: role member; holding %d line(s) for collectors, sent %d;"
            .. " queue %d", cid and #S.Guild(cid).chat or 0, stats.answered, #queue))
    end
    ns.Print(string.format("relay: messages sent %d, received %d (from others), last send result %s;"
        .. " collectors seen: %s%s", stats.sent, stats.received, tostring(stats.lastResult),
        #names > 0 and table.concat(names, ", ") or "none",
        stats.dropped > 0 and (", dropped " .. stats.dropped) or ""))
end
