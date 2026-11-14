-- Relay (CLAUDE.md 5.7): a collector asks "who has text for these times?"; members (and other collectors)
-- answer with the lines they captured live; the collector fills its text-less rows after checking
-- stream, time and author, and confirms so everyone drops them. Sends and receives through Comms.lua.
--   H version role held given filled   hello (20 s after login, then every 15 min)
--   W                                  who is online? (everyone answers with H, spread over WHO_SPREAD s)
--   N stream t1-t2,t3-t4               need (collector)
--   T id k/n chunk                     one line, chunk 1 = "s TAB t TAB author TAB guid TAB fd TAB text..."
--   G id,id,...                        got it (collector)
-- Older versions (0.2.x) send H with only "held" after the role.

local _, ns = ...
local C, S = ns.Compat, ns.Store
local Comms = ns.Comms
local M = ns.Module("Relay")
ns.Relay = M

local SEP = Comms.SEP
local CHUNK = 200 -- bytes of line data per T message (whole message stays under 255)
local HELLO_DELAY = 20
local HELLO_EVERY = 900 -- s: everybody repeats hello, so /gl who knows who is online
local WHO_SPREAD = 30 -- s: answers to a who request are spread over this
local WHO_ANSWER_GAP = 300 -- s: answer a who request at most this often
local WHO_ASK_GAP = 60 -- s: /gl who asks again at most this often
local WHO_FRESH = 1800 -- s: /gl who lists players heard within this
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
local PARTS_MAX, PARTS_PER_SENDER = 200, 40 -- unfinished multi-part lines a collector keeps
local NEED_ROUND = 10 -- s: needs from one asker this close together are one round (a long list comes in pieces)
local NEED_ANSWER_GAP = 60 -- s: a new round from the same asker is answered at most this often
local HEARD_TTL = 3600
local FOREIGN_QUIET = 5 -- s: someone else is answering while their lines keep coming

local heard = {} -- [id] = GetTime(): somebody already sent or confirmed this line
local queued = {} -- [id] = GetTime(): one of our own answers is waiting in the queue
local partsBuf = {} -- [sender .. "|" .. id] = { n, chunks = {}, got, at, sender }
local pendingAck = {}
local lastNeed, needScheduled = -1e9, false
local collectors = {} -- [sender] = GetTime() of their last hello
local seen = {} -- [sender] = { ver, role, at, held, given, filled }: everyone who said hello
local roundAt = {} -- [asker] = GetTime() when their current need round started
local whoAnsweredAt, whoAskedAt = -1e9, -1e9
local lastForeignText = -1e9 -- GetTime() of the last line another player sent
local helloSent = false
local stats = { answered = 0, relayed = 0, rejected = 0, lastNeed = nil }

---------------------------------------------------------------------------------------------------
-- Helpers
---------------------------------------------------------------------------------------------------

local function club()
    if ns.Chat and ns.Chat.Club then return ns.Chat.Club() end
end

M.splitUtf8 = Comms.SplitUtf8

local function lineMessages(row)
    local payload = table.concat({ row.s, tostring(row.t), row.a or "", row.g or "", row.fd and "1" or "0",
        row.m }, SEP)
    local chunks = Comms.SplitUtf8(payload, CHUNK)
    local msgs = {}
    for k, chunk in ipairs(chunks) do
        msgs[k] = table.concat({ "T", row.id, k .. "/" .. #chunks, chunk }, SEP)
    end
    return msgs
end
M.lineMessages = lineMessages

local function myCounts()
    local cid = club()
    local held = (cid and not S.IsCollector()) and #S.Guild(cid).chat or 0
    return held, stats.answered, stats.relayed
end

local function hello()
    if not club() then return false end
    local held, given, filled = myCounts()
    Comms.Send(table.concat({ "H", S.VERSION, S.IsCollector() and "c" or "m", tostring(held), tostring(given),
        tostring(filled) }, SEP), Comms.NORMAL)
    helloSent = true
    return true
end

-- "0.2.10" > "0.2.9": compare dotted numbers.
local function older(a, b)
    local x, y = {}, {}
    for n in tostring(a):gmatch("%d+") do x[#x + 1] = tonumber(n) end
    for n in tostring(b):gmatch("%d+") do y[#y + 1] = tonumber(n) end
    for i = 1, math.max(#x, #y) do
        if (x[i] or 0) ~= (y[i] or 0) then return (x[i] or 0) < (y[i] or 0) end
    end
    return false
end
M.older = older

---------------------------------------------------------------------------------------------------
-- Member side: answer a need with own lines
---------------------------------------------------------------------------------------------------

local function queueLine(row)
    local id = row.id
    queued[id] = C.Clock()
    Comms.Queue({
        msgs = M.lineMessages(row), prio = Comms.BULK,
        skip = function() return heard[id] ~= nil end, -- another player sent or confirmed it meanwhile
        onSent = function()
            queued[id] = nil
            heard[id] = C.Clock()
            stats.answered = stats.answered + 1
        end,
        onDrop = function() queued[id] = nil end,
    })
end

local function onNeed(sender, text, me)
    local s, rangesText = text:match("^N\t(%a)\t(.+)$")
    local cid = club()
    if not s or not cid or me then return end
    local now = C.Clock()
    local started = roundAt[sender] or -1e9
    if now - started >= NEED_ANSWER_GAP then
        roundAt[sender] = now -- a new round
    elseif now - started > NEED_ROUND then
        return -- same asker again too soon: ignored (spam protection)
    end
    local ranges = {}
    for a, b in rangesText:gmatch("(%d+)%-(%d+)") do ranges[#ranges + 1] = { tonumber(a), tonumber(b) } end
    if #ranges == 0 then return end
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
            if not heard[row.id] and not queued[row.id] then queueLine(row) end
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
    for _, m in ipairs(msgs) do Comms.Send(m, Comms.NORMAL) end
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
        Comms.Send("G" .. SEP .. table.concat(ids, ","), Comms.NORMAL)
    end
end

---------------------------------------------------------------------------------------------------
-- Receiving
---------------------------------------------------------------------------------------------------

local function onText(sender, text, me)
    local id, k, n, chunk = text:match("^T\t([^\t]+)\t(%d+)/(%d+)\t(.*)$")
    if not id or me then return end
    k, n = tonumber(k), tonumber(n)
    heard[id] = C.Clock() -- members: someone is sending this line, skip it
    lastForeignText = C.Clock()
    if not S.IsCollector() or n < 1 or n > 20 or k < 1 or k > n then return end
    local key = sender .. "|" .. id
    local p = partsBuf[key]
    if not p then
        -- Bounded: one sender cannot make us keep endless half-received lines.
        local total, mine, oldestKey, oldestAt = 0, 0, nil, math.huge
        for kk, q in pairs(partsBuf) do
            total = total + 1
            if q.sender == sender then mine = mine + 1 end
            if q.at < oldestAt then oldestKey, oldestAt = kk, q.at end
        end
        if mine >= PARTS_PER_SENDER then return end
        if total >= PARTS_MAX and oldestKey then partsBuf[oldestKey] = nil end
        p = { n = n, chunks = {}, got = 0, at = C.Clock(), sender = sender }
        partsBuf[key] = p
    end
    if p.n ~= n or p.chunks[k] then return end
    p.chunks[k] = chunk
    p.got = p.got + 1
    if p.got < n then return end
    partsBuf[key] = nil
    accept(sender, id, table.concat(p.chunks))
end

local function onGot(_, text)
    local idsText = text:match("^G\t(.+)$")
    if not idsText then return end
    local ids, any = {}, false
    for id in idsText:gmatch("[^,]+") do
        ids[id] = true
        heard[id] = C.Clock()
        any = true
    end
    local cid = club()
    if any and cid and not S.IsCollector() then S.RemoveChat(cid, ids) end -- members drop confirmed lines
end

local function onHello(sender, text, me)
    local ver, role, rest = text:match("^H\t([^\t]*)\t([cm])(.*)$")
    if not ver or me then return end
    local held, given, filled = rest:match("^\t(%d+)\t?(%d*)\t?(%d*)")
    local before = seen[sender]
    if role == "c" then collectors[sender] = C.Clock() end
    seen[sender] = { ver = ver, role = role, at = C.Clock(), held = tonumber(held), given = tonumber(given),
        filled = tonumber(filled) }
    ns.Debug(string.format("relay: hello from %s (%s, v%s)", sender, role == "c" and "collector" or "member", ver),
        before ~= nil)
    -- A member who just logged in may hold text for our gaps (periodic hellos do not count).
    local fresh = not before or C.Clock() - before.at > WHO_FRESH
    if fresh and role == "m" and S.IsCollector() and C.Clock() - lastNeed >= NEED_MIN_GAP then
        scheduleNeeds(5)
    end
end

local function onWho(_, _, me)
    if me or C.Clock() - whoAnsweredAt < WHO_ANSWER_GAP then return end
    whoAnsweredAt = C.Clock()
    C.After(math.random(1, WHO_SPREAD), function() ns.Safe("Relay.hello", hello) end)
end

Comms.Handle("N", onNeed)
Comms.Handle("T", onText)
Comms.Handle("G", onGot)
Comms.Handle("H", onHello)
Comms.Handle("W", onWho)

---------------------------------------------------------------------------------------------------
-- Startup, housekeeping
---------------------------------------------------------------------------------------------------

local function housekeeping()
    local now = C.Clock()
    for id, at in pairs(heard) do if now - at > HEARD_TTL then heard[id] = nil end end
    for id, at in pairs(queued) do if now - at > HEARD_TTL then queued[id] = nil end end
    for key, p in pairs(partsBuf) do if now - p.at > PARTS_TTL then partsBuf[key] = nil end end
    for who, at in pairs(collectors) do if now - at > 4 * 3600 then collectors[who] = nil end end
    for who, v in pairs(seen) do if now - v.at > 4 * 3600 then seen[who] = nil end end
    local cid = club()
    if cid and not S.IsCollector() then S.PruneMember(cid, C.Now()) end
end

function M.OnInit()
    if not C.HasComm then return end
    C.Ticker(ACK_EVERY, function() ns.Safe("Relay.ack", flushAcks) end)
    C.Ticker(PRUNE_EVERY, function() ns.Safe("Relay.prune", housekeeping) end)
    C.Ticker(NEED_EVERY, function() ns.Safe("Relay.need", sendNeeds) end)
    C.Ticker(HELLO_DELAY, function()
        if not helloSent then ns.Safe("Relay.hello", hello) end
    end)
    C.Ticker(HELLO_EVERY, function()
        if helloSent then ns.Safe("Relay.hello", hello) end
    end)
end

---------------------------------------------------------------------------------------------------
-- /gl who and /gl status
---------------------------------------------------------------------------------------------------

-- Plain copy: { [player] = version } of everyone heard in the last 4 hours (GuildLedgerAPI).
function M.VersionsSeen()
    local out = {}
    for who, v in pairs(seen) do out[who] = v.ver end
    return out
end

local function describe(v)
    local parts = { "version " .. v.ver .. (older(v.ver, S.VERSION) and " |cffffaa00(outdated)|r" or "") }
    if v.role == "c" then
        if v.filled then parts[#parts + 1] = string.format("filled %d line(s) from members", v.filled) end
    else
        if v.held then parts[#parts + 1] = string.format("keeps %d line(s)", v.held) end
        if v.given then parts[#parts + 1] = string.format("gave %d to collectors", v.given) end
    end
    local ago = math.floor((C.Clock() - v.at) / 60)
    parts[#parts + 1] = ago < 1 and "just now" or string.format("%d min ago", ago)
    return table.concat(parts, " - ")
end

local function printWho()
    local now = C.Clock()
    local col, mem = {}, {}
    for who, v in pairs(seen) do
        if now - v.at <= WHO_FRESH then
            table.insert(v.role == "c" and col or mem, { who = who, v = v })
        end
    end
    table.sort(col, function(a, b) return a.who < b.who end)
    table.sort(mem, function(a, b) return a.who < b.who end)
    local held, given, filled = myCounts()
    local me = { ver = S.VERSION, role = S.IsCollector() and "c" or "m", at = now, held = held, given = given,
        filled = filled }
    ns.Print(string.format("players online with GuildLedger: %d (you included)", #col + #mem + 1))
    ns.Head("You")
    ns.Line((S.IsCollector() and "Collector" or "Member") .. " - " .. describe(me))
    ns.Head(string.format("Collectors (%d)", #col))
    if #col == 0 then ns.Line("none online") end
    for _, e in ipairs(col) do ns.Line(e.who .. " - " .. describe(e.v)) end
    ns.Head(string.format("Members (%d)", #mem))
    if #mem == 0 then ns.Line("none heard yet") end
    for _, e in ipairs(mem) do ns.Line(e.who .. " - " .. describe(e.v)) end
end

-- /gl who: ask everyone online, show the list once the answers are in.
function M.Who()
    if not C.HasComm then
        ns.Print("sharing with other players is not available in this game version")
        return
    end
    if C.Clock() - whoAskedAt < WHO_ASK_GAP then
        printWho()
        return
    end
    whoAskedAt = C.Clock()
    Comms.Send("W", Comms.NORMAL)
    ns.Print(string.format("asking everyone online who has GuildLedger; the list follows in about %d seconds.",
        WHO_SPREAD + 5))
    C.After(WHO_SPREAD + 5, function() ns.Safe("Relay.who", printWho) end)
end

function M.Status()
    ns.Head("Sharing with other players")
    if not C.HasComm then
        ns.Line("Not available in this game version.")
        return
    end
    if S.IsCollector() then
        ns.Line(string.format("Lines filled in by members since login: %d%s.", stats.relayed,
            stats.rejected > 0 and (" (" .. stats.rejected .. " refused because they did not match)") or ""))
        ns.Line("Last asked members for missing lines: "
            .. (stats.lastNeed and date("%H:%M", stats.lastNeed) or "not yet") .. ".")
    else
        ns.Line(string.format("Lines given to collectors since login: %d.", stats.answered))
    end
    Comms.StatusLines()
    local names = {}
    for who in pairs(collectors) do names[#names + 1] = who end
    table.sort(names)
    ns.Line("Collectors online: " .. (#names > 0 and table.concat(names, ", ") or "none seen yet") .. ".")
    local versions, outdated = {}, {}
    for who, v in pairs(seen) do
        versions[v.ver] = (versions[v.ver] or 0) + 1
        if older(v.ver, S.VERSION) then outdated[#outdated + 1] = who .. " (" .. v.ver .. ")" end
    end
    local parts = {}
    for ver, n in pairs(versions) do parts[#parts + 1] = string.format("%s by %d player(s)", ver, n) end
    table.sort(parts)
    if #parts > 0 then
        ns.Line("GuildLedger versions seen (last 4 hours): " .. table.concat(parts, ", ") .. ".")
    end
    if #outdated > 0 then
        table.sort(outdated)
        ns.Line("|cffffaa00Outdated, should update:|r " .. table.concat(outdated, ", ") .. ".")
    end
end
