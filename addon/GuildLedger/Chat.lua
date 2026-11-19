-- Chat capture (CLAUDE.md 5.3, revised after Phase 0).
--
-- Club message text is a protected kstring, so:
--   * live: CHAT_MSG_GUILD/OFFICER gives the text, CLUB_MESSAGE_ADDED gives the server ID and exact
--     time; the two are paired by stream + author (GUID, else name) within PAIR_WINDOW s, in either
--     order -> src "live". Unpaired after FLUSH_AFTER s: club only -> "meta", chat only -> "event".
--   * history: SyncStream walks the downloaded club history back to the cursor and stores IDs the
--     spool does not have yet as "meta" rows (who wrote when, no text).

local _, ns = ...
local C, S = ns.Compat, ns.Store
local M = ns.Module("Chat")
ns.Chat = M

local PAIR_WINDOW = 3 -- seconds between the two halves of one line (measured: 0-0.6 s)
local FLUSH_AFTER = 5 -- seconds before an unpaired half is stored on its own
local PAGE = 100 -- messages per history request
local INIT_TRIES = 12
local PERIODIC_SYNC = 600 -- seconds; catches anything a missed event would lose
local PAGES_PER_STEP = 5 -- history pages read per frame (500 messages); more waits for the next frame

local clubId -- guild club, plain number
local streams = {} -- [streamId] = letter
local letterStream = {} -- [letter] = streamId
local ready = false
local needSync = false
local pendingChat, pendingClub = {}, {}
local flushScheduled = false
local sync = {} -- [streamId] = { from = messageId?, pages = n, active = bool }
local lastSync, lastSyncNote = nil, "not done yet"
local stats = { live = 0, meta = 0, event = 0 }
local unknownLogged = 0 -- debug: history messages without an author name (Phase 7 open question)

---------------------------------------------------------------------------------------------------
-- Helpers
---------------------------------------------------------------------------------------------------

local function cleanText(text)
    return (text:gsub("%c", " "))
end

-- 32-bit polynomial hash as 8 hex digits (no bit library needed).
local function hash8(text)
    local h = 5381
    for i = 1, #text do
        h = (h * 33 + text:byte(i)) % 4294967296
    end
    return string.format("%08x", h)
end

local function sameAuthor(a, b)
    if a.g and b.g then return a.g == b.g end
    -- Discord-bridged lines: the club side may have no name at all ("?").
    if a.fd and b.fd and (a.a == "?" or b.a == "?") then return true end
    return a.a == b.a
end

local function store(row)
    -- Member role (CLAUDE.md 5.7): only lines with text and a server ID are worth keeping for collectors.
    if not S.IsCollector() and row.src ~= "live" then return nil end
    local r = S.AddChat(clubId, row)
    if r == "new" then stats[row.src] = (stats[row.src] or 0) + 1 end
    return r
end

---------------------------------------------------------------------------------------------------
-- Stream selection
---------------------------------------------------------------------------------------------------

local function wanted(stype)
    local o = S.Opts()
    if stype == 1 or stype == 3 then return true end
    if stype == 2 then return o.officer end
    if stype == 4 then return o.other end
    return false
end

local function selectStreams()
    local list = C.Streams(clubId)
    if not list then return false end
    streams, letterStream = {}, {}
    for sid, stype in pairs(list) do
        local letter = C.STREAM_LETTER[stype]
        if letter and wanted(stype) and not letterStream[letter] then
            streams[sid] = letter
            letterStream[letter] = sid
        end
    end
    return next(streams) ~= nil
end

---------------------------------------------------------------------------------------------------
-- Live pairing
---------------------------------------------------------------------------------------------------

local flushPending

local function scheduleFlush()
    if flushScheduled then return end
    flushScheduled = true
    C.After(FLUSH_AFTER + 0.5, function()
        flushScheduled = false
        ns.Safe("Chat.flush", flushPending)
    end)
end

local function tryPair()
    local i = 1
    while i <= #pendingClub do
        local c = pendingClub[i]
        local match
        for j = 1, #pendingChat do
            local e = pendingChat[j]
            if e.s == c.s and math.abs(e.at - c.at) <= PAIR_WINDOW and sameAuthor(e, c) then
                match = j
                break
            end
        end
        if match then
            local e = table.remove(pendingChat, match)
            table.remove(pendingClub, i)
            store({ id = c.id, t = c.t, s = c.s, a = c.a ~= "?" and c.a or e.a, g = c.g or e.g, m = e.m,
                fd = e.fd or c.fd, ed = c.ed, del = c.del, src = "live" })
        else
            i = i + 1
        end
    end
end

flushPending = function()
    local now = C.Clock()
    local i = 1
    while i <= #pendingClub do
        local c = pendingClub[i]
        if now - c.at >= FLUSH_AFTER then
            table.remove(pendingClub, i)
            store({ id = c.id, t = c.t, s = c.s, a = c.a, g = c.g, fd = c.fd, ed = c.ed, del = c.del,
                src = "meta" })
        else
            i = i + 1
        end
    end
    i = 1
    while i <= #pendingChat do
        local e = pendingChat[i]
        if now - e.at >= FLUSH_AFTER then
            table.remove(pendingChat, i)
            store({ id = "ev|" .. e.t .. "|" .. e.a .. "|" .. hash8(e.m), t = e.t, s = e.s, a = e.a, g = e.g,
                m = e.m, fd = e.fd, src = "event" })
        else
            i = i + 1
        end
    end
    if #pendingClub > 0 or #pendingChat > 0 then scheduleFlush() end
end

local function onChatMsg(letter, ...)
    if not ready or not letterStream[letter] then return end
    local text, name = ...
    local guid = select(12, ...)
    local di = select(18, ...)
    if C.IsSecret(text, name, guid) then needSync = true return end
    local fd, dname = C.DiscordInfo(di)
    if fd then
        ns.Debug(string.format("chat %s from Discord: name %s, guid %s, discordInfo {%s}", letter,
            type(name) == "string" and (name == "" and "empty" or "set") or type(name),
            type(guid) == "string" and (guid == "" and "empty" or "set") or type(guid), C.FieldNames(di)))
        if type(name) ~= "string" or name == "" then name = dname or "?" end
    end
    if type(text) ~= "string" or type(name) ~= "string" or name == "" then return end
    fd = fd or nil
    if type(guid) ~= "string" or guid == "" then guid = nil end
    pendingChat[#pendingChat + 1] = { s = letter, a = name, g = guid, m = cleanText(text), fd = fd,
        at = C.Clock(), t = C.Now() }
    tryPair()
    scheduleFlush()
end

ns.On("CHAT_MSG_GUILD", function(...) onChatMsg("g", ...) end)
ns.On("CHAT_MSG_OFFICER", function(...) onChatMsg("o", ...) end)

ns.On("CLUB_MESSAGE_ADDED", function(cid, sid, messageId)
    if not ready or C.IsSecret(cid, sid) or cid ~= clubId or not streams[sid] then return end
    if C.InLockdown() or not C.ReadId(messageId) then needSync = true return end
    local row = C.ReadMessage(C.MessageInfo(clubId, sid, messageId))
    if not row then needSync = true return end
    if not row.g then
        local m = C.MessageInfo(clubId, sid, messageId)
        ns.Debug(string.format("club %s message without GUID: author {%s}, discord %s", streams[sid],
            C.FieldNames(type(m) == "table" and not C.IsSecret(m) and m.author or nil),
            row.fd and "yes" or "no"))
    end
    row.s, row.at = streams[sid], C.Clock()
    pendingClub[#pendingClub + 1] = row
    tryPair()
    scheduleFlush()
end)

ns.On("CLUB_MESSAGE_UPDATED", function(cid, sid, messageId)
    if not ready or C.IsSecret(cid, sid) or cid ~= clubId or not streams[sid] then return end
    if not C.ReadId(messageId) then return end
    local row = C.ReadMessage(C.MessageInfo(clubId, sid, messageId))
    if not row then return end
    -- Edited text is unreadable (kstring); only the flags are kept.
    if not S.SetFlags(clubId, streams[sid], row.id, row.ed, row.del) then
        for _, c in ipairs(pendingClub) do
            if c.id == row.id then c.ed, c.del = c.ed or row.ed, c.del or row.del end
        end
    end
end)

---------------------------------------------------------------------------------------------------
-- History sync (meta rows for what was written while nobody collected)
---------------------------------------------------------------------------------------------------

local syncStream
local STREAM_NAMES = { g = "Guild chat", o = "Officer chat", d = "Discord chat", x = "Other chat" }
local REQUEST_TIMEOUT = 15 -- s without CLUB_MESSAGE_HISTORY_RECEIVED
local REQUEST_RETRIES = 2 -- then: the server has nothing older (Phase 2: it just stays silent)
local histEvents = 0

local function finishSync(sid, note)
    local st = sync[sid]
    if st and st.top then
        S.SetCursor(clubId, streams[sid], st.top[1], st.top[2])
    end
    sync[sid] = nil
    lastSync, lastSyncNote = C.Now(), note
    ns.Debug("sync " .. tostring(streams[sid]) .. " done: " .. note)
    local where = STREAM_NAMES[streams[sid]] or "chat"
    if st and st.added > 0 then
        ns.Info(string.format("%s: %d message(s) found in the server history that you had not seen yet"
            .. " (%s to %s). Their text is asked from other players.", where, st.added, ns.When(st.lo),
            ns.When(st.hi)))
    elseif st then
        ns.Info(where .. ": no messages missed, nothing new in the server history.")
    end
    if ns.RelaySynced then ns.Safe("Relay.synced", ns.RelaySynced) end
end

local function idText(id)
    local e, p = C.ReadId(id)
    if not e then return "?" end
    return date("%m-%d %H:%M:%S", math.floor(e / 1e6))
end

-- Ask the server for PAGE messages older than `before` (nil = the newest). The walk resumes on
-- CLUB_MESSAGE_HISTORY_RECEIVED; without an answer it retries, then gives up and saves the cursor.
local function request(sid, st, before)
    st.pages = st.pages + 1
    local token = {}
    st.waiting = token
    local had = C.RequestMore(clubId, sid, before, PAGE)
    ns.Debug(string.format("sync %s: request #%d before %s (retry %d) -> %s", streams[sid], st.pages,
        before and idText(before) or "newest", st.retries or 0, tostring(had)))
    if had then
        st.waiting = nil
        C.After(0.2, function() ns.Safe("Chat.sync", syncStream, sid) end)
        return
    end
    C.After(REQUEST_TIMEOUT, function()
        if sync[sid] ~= st or st.waiting ~= token then return end
        st.waiting = nil
        st.retries = (st.retries or 0) + 1
        if st.retries > REQUEST_RETRIES then
            finishSync(sid, string.format("up to date, back to the oldest messages the server keeps (%d new)",
                st.added))
        else
            st.pages = st.pages - 1 -- a retry is not a new page
            ns.Safe("Chat.sync", syncStream, sid)
        end
    end)
end

-- Walk back from st.from (or the newest message) until the cursor, the beginning of the stream or
-- the page cap. Older messages are requested from the server and the walk resumes on
-- CLUB_MESSAGE_HISTORY_RECEIVED.
local function syncStep(sid)
    if not ready or not streams[sid] then return end
    if C.InLockdown() then needSync = true return end
    local letter = streams[sid]
    local st = sync[sid]
    if not st then
        st = { pages = 0, added = 0 }
        sync[sid] = st
        local ce = S.Cursor(clubId, letter)
        ns.Debug(string.format("sync %s start: cursor %s, floor %s", letter,
            ce and date("%m-%d %H:%M:%S", math.floor(ce / 1e6)) or "none", tostring(S.Floor(clubId))))
    end
    local _, newestR = C.LastRange(clubId, sid)
    if not newestR then
        -- Empty or not yet downloaded: ask a few times, then leave it to the periodic sync.
        if st.pages >= 3 then finishSync(sid, "the server has no guild chat history") return end
        request(sid, st, nil)
        return
    end
    if not st.top then st.top = { C.ReadId(newestR) } end
    local ce, cp = S.Cursor(clubId, letter)
    local floor = S.Floor(clubId) or 0
    local from = st.from or newestR
    for _ = 1, PAGES_PER_STEP do -- local walk through what is already downloaded
        local msgs = C.MessagesBefore(clubId, sid, from, PAGE)
        if not msgs then needSync = true return end
        local oldest, oe, op
        for _, m in ipairs(msgs) do
            local row = C.ReadMessage(m)
            if row and row.a == "?" and unknownLogged < 5 and S.Opts().debug then
                unknownLogged = unknownLogged + 1
                local a = type(m) == "table" and not C.IsSecret(m) and m.author or nil
                ns.Debug(string.format("history message without author name: author {%s}, discordInfo {%s}",
                    C.FieldNames(a), C.FieldNames(type(a) == "table" and not C.IsSecret(a) and a.discordInfo or nil)),
                    true)
            end
            if row then
                if not oe or S.Newer(oe, op, row.epoch, row.pos) then
                    oldest, oe, op = m.messageId, row.epoch, row.pos
                end
                if row.t >= floor and (not ce or S.Newer(row.epoch, row.pos, ce, cp)) then
                    row.s, row.src, row.epoch, row.pos = letter, "meta", nil, nil
                    if store(row) == "new" then
                        st.added = st.added + 1
                        if not st.lo or row.t < st.lo then st.lo = row.t end
                        if not st.hi or row.t > st.hi then st.hi = row.t end
                    end
                end
            end
        end
        if not oldest then finishSync(sid, "could not read the history") return end
        if (ce and not S.Newer(oe, op, ce, cp)) or math.floor(oe / 1e6) < floor then
            finishSync(sid, string.format("up to date (%d new)", st.added))
            return
        end
        local fe, fp = C.ReadId(from)
        if fe and oe == fe and op == fp then
            -- Nothing older is downloaded: ask the server, unless we are at the start or the cap.
            if C.IsBeginning(clubId, sid, oldest) then
                finishSync(sid, string.format("up to date, back to the start of the guild chat (%d new)", st.added))
                return
            end
            if st.pages >= S.Opts().pageCap then
                finishSync(sid, string.format("stopped after %d pages (%d new), the rest follows next time", st.pages,
                    st.added))
                return
            end
            st.from = oldest
            request(sid, st, oldest)
            return
        end
        from = oldest
    end
    st.from = from -- long local walk: continue on the next frame, no stutter
    C.After(0, function() ns.Safe("Chat.sync", syncStream, sid) end)
end

syncStream = function(sid)
    ns.Timed("history step", syncStep, sid)
end

function M.Sync(force)
    if not ready or not S.IsCollector() then return end -- members keep live lines only
    if C.InLockdown() then needSync = true return end
    needSync = false
    for sid in pairs(streams) do
        if force or not sync[sid] then
            sync[sid] = nil
            syncStream(sid)
        end
    end
end

ns.On("CLUB_MESSAGE_HISTORY_RECEIVED", function(cid, sid, downloaded)
    if not ready or C.IsSecret(cid, sid) or cid ~= clubId or not streams[sid] then return end
    histEvents = histEvents + 1
    local st = sync[sid]
    if not st then return end
    if type(downloaded) == "table" and not C.IsSecret(downloaded) then
        ns.Debug(string.format("sync %s: history received %s .. %s", streams[sid],
            idText(downloaded.oldestMessageId), idText(downloaded.newestMessageId)))
    end
    st.waiting, st.retries = nil, 0
    C.After(0.2, function() ns.Safe("Chat.sync", syncStream, sid) end)
end)

ns.On("ADDON_RESTRICTION_STATE_CHANGED", function(rtype, state)
    if C.IsSecret(rtype, state) then return end
    if state == 0 and needSync then -- Enum.AddOnRestrictionState.Inactive
        C.After(1, function() ns.Safe("Chat.sync", M.Sync) end)
    end
end)

---------------------------------------------------------------------------------------------------
-- Startup
---------------------------------------------------------------------------------------------------

local tries = 0

local function tryInit()
    if ns.disabled then return true end
    if not S.DB() then return false end -- SavedVariables not loaded yet
    local id = C.GuildClubId()
    if not id then return false end
    if ready and id == clubId then return true end
    if C.InLockdown() then return false end
    clubId = id
    S.Guild(clubId, C.ClubName(clubId))
    if not selectStreams() then return false end
    ready = true
    ns.Debug("ready, club " .. tostring(clubId))
    -- A history request sent the instant the client logs in can go unanswered; give it a moment.
    C.After(5, function() ns.Safe("Chat.sync", M.Sync, true) end)
    return true
end

local initTicker

local function startInitRetries()
    if initTicker then return end
    tries = 0
    initTicker = C.Ticker(5, function()
        tries = tries + 1
        local ok = false
        ns.Safe("Chat.init", function() ok = tryInit() end)
        if (ok or tries >= INIT_TRIES) and initTicker then
            initTicker:Cancel()
            initTicker = nil
        end
    end)
end

function M.OnInit()
    -- poll while a sync is owed (lockdown) and run a periodic catch-up sync
    C.Ticker(5, function()
        if ready and needSync and not C.InLockdown() then ns.Safe("Chat.sync", M.Sync) end
    end)
    C.Ticker(PERIODIC_SYNC, function() ns.Safe("Chat.sync", M.Sync) end)
end

ns.On("PLAYER_ENTERING_WORLD", function()
    if not tryInit() then startInitRetries() end
end)
ns.On("INITIAL_CLUBS_LOADED", function() tryInit() end)
ns.On("CLUB_STREAMS_LOADED", function(cid)
    if C.IsSecret(cid) then return end
    if not ready then tryInit() elseif cid == clubId then selectStreams() end
end)
ns.On("CLUB_STREAM_ADDED", function(cid)
    if ready and not C.IsSecret(cid) and cid == clubId then selectStreams() end
end)
ns.On("CLUB_STREAM_REMOVED", function(cid)
    if ready and not C.IsSecret(cid) and cid == clubId then selectStreams() end
end)

function M.OnOption(name)
    if name == "officer" and ready then
        selectStreams()
        M.Sync(true)
    end
end

-- For Relay.lua: the guild club and the stream letters in use (nil while not ready).
function M.Club()
    if ready then return clubId, letterStream end
end

function M.Status()
    ns.Head("Guild chat")
    if not ready then
        ns.Line("Waiting for the guild (not in a guild, or the game has not loaded it yet).")
        return
    end
    local g = S.Guild(clubId)
    local channels = {}
    if letterStream.g then channels[#channels + 1] = "guild chat" end
    if letterStream.o then channels[#channels + 1] = "officer chat" end
    if letterStream.d then channels[#channels + 1] = "Discord chat" end
    ns.Line(string.format("Guild: %s. Logging: %s.", tostring(g.name or clubId), table.concat(channels, " and ")))
    local total, text, meta, ev = S.Counts(clubId)
    local newText = (stats.live or 0) + (stats.event or 0)
    if S.IsCollector() then
        ns.Line(string.format("Lines saved: %s (%s with text, %s only as 'someone wrote' without text).",
            ns.Num(total), ns.Num(text + ev), ns.Num(meta)))
        ns.Line(string.format("Since login: %s line(s) seen live with text, %s found in the guild history"
            .. " (without text, members may fill them in).", ns.Num(newText), ns.Num(stats.meta or 0)))
        if next(sync) ~= nil then
            for _, st in pairs(sync) do
                ns.Line(string.format("History check: running (%d page(s) read, %d new line(s))%s.", st.pages,
                    st.added, st.waiting and ", waiting for the server" or ""))
            end
        elseif needSync then
            ns.Line("History check: waits until the boss-fight chat lock ends.")
        else
            ns.Line(string.format("Last history check: %s - %s.", ns.Clock(lastSync), lastSyncNote))
        end
    else
        ns.Line(string.format("Lines kept for collectors: %s (deleted once a collector has them; at most %s"
            .. " lines and 3 days).", ns.Num(total), ns.Num(S.MEMBER_MAX)))
        ns.Line(string.format("Since login: %s new line(s).", ns.Num(newText)))
    end
    local pending = #pendingChat + #pendingClub
    if pending > 0 then ns.Line(string.format("Lines still being matched: %d.", pending)) end
end
