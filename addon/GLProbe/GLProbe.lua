-- GLProbe: GuildLedger Phase 0 probe. Measures the API questions CLAUDE.md section 8 leaves open.
-- Every API used here is listed in the 1.60.1 API docs or Blizzard_Communities (vendor-ref).
-- Reads only. Never sends chat, never performs guild actions.
--
--   /glprobe          items 1, 2, 5, 6, 7 (event log arrives a moment later)
--   /glprobe depth    item 3: page back through guild chat history (up to 30 pages)
--   /glprobe focus    item 4: switch the live counters to the "focused" phase (calls C_Club.FocusStream)
--   /glprobe live     item 4: print the live counters
--   /glprobe pair     item 4c: live /g text vs club message ID (recorded automatically, 60 max)
--   /glprobe reset    wipe GLProbeDB
-- Results go to chat and to GLProbeDB (written to disk on /reload).

local ADDON = ...
local PREFIX = "|cff33ff99GLProbe|r: "
local MAX_PAGES = 30

local function say(msg) DEFAULT_CHAT_FRAME:AddMessage(PREFIX .. msg) end

---------------------------------------------------------------------------------------------------
-- Secret-safe helpers
---------------------------------------------------------------------------------------------------

local function IsSecret(...)
    if not issecretvalue then return false end
    for i = 1, select("#", ...) do
        if issecretvalue((select(i, ...))) then return true end
    end
    return false
end

local function InLockdown()
    if C_ChatInfo and C_ChatInfo.InChatMessagingLockdown then
        local v = C_ChatInfo.InChatMessagingLockdown()
        if IsSecret(v) then return true end
        return v and true or false
    end
    return false
end

-- A plain, storable copy of a value: secrets become "<secret>", tables are copied (depth-limited).
local function plain(v, depth)
    if IsSecret(v) then return "<secret>" end
    local t = type(v)
    if t == "string" or t == "boolean" then return v end
    if t == "number" then
        if v ~= v then return "<nan>" end
        if v >= 1e12 or v <= -1e12 then return string.format("%.0f", v) end -- avoid 1.7e+15 in the file
        return v
    end
    if t == "nil" then return "<nil>" end
    if t == "table" then
        depth = depth or 0
        if depth >= 3 then return "<table>" end
        local out = {}
        for k, val in pairs(v) do
            if not IsSecret(k) and (type(k) == "string" or type(k) == "number") then
                out[k] = plain(val, depth + 1)
            end
        end
        return out
    end
    return "<" .. t .. ">"
end

-- Every return value of f(...) as a plain list, with the count, so nils in the middle are visible.
local function capture(f, ...)
    local function pack(...)
        local out = { n = select("#", ...) }
        for i = 1, out.n do out[i] = plain((select(i, ...))) end
        return out
    end
    return pack(pcall(f, ...))
end

local function msgIdString(id)
    if type(id) ~= "table" or IsSecret(id.epoch, id.position) then return "<secret-or-missing>" end
    if type(id.epoch) ~= "number" or type(id.position) ~= "number" then return "<bad>" end
    return string.format("%.0f:%.0f", id.epoch, id.position)
end

local function idDate(id)
    if type(id) ~= "table" or IsSecret(id.epoch) or type(id.epoch) ~= "number" then return "?" end
    return date("!%Y-%m-%d %H:%M:%S UTC", math.floor(id.epoch / 1e6))
end

local function idNewer(a, b) -- a strictly newer than b
    if a.epoch ~= b.epoch then return a.epoch > b.epoch end
    return a.position > b.position
end

---------------------------------------------------------------------------------------------------
-- Guild club / stream lookup
---------------------------------------------------------------------------------------------------

local function guildClub()
    if not (C_Club and C_Club.GetGuildClubId) then return nil end
    local id = C_Club.GetGuildClubId()
    if id == nil or IsSecret(id) then return nil end
    return id
end

local function guildStream(clubId)
    if not (C_Club and C_Club.GetStreams) then return nil end
    local guildType = (Enum and Enum.ClubStreamType and Enum.ClubStreamType.Guild) or 1
    for _, s in ipairs(C_Club.GetStreams(clubId) or {}) do
        if s.streamType == guildType and not IsSecret(s.streamId) then return s.streamId end
    end
    return nil
end

-- Last range as CLAUDE.md 2 describes; nil if none or empty.
local function lastRange(clubId, sid)
    local ranges = C_Club.GetMessageRanges(clubId, sid) or {}
    local r = ranges[#ranges]
    if not r then return nil, #ranges end
    local o, n = r.oldestMessageId, r.newestMessageId
    if IsSecret(o.epoch, o.position, n.epoch, n.position) then return nil, #ranges end
    if idNewer(o, n) then return nil, #ranges end
    return r, #ranges
end

---------------------------------------------------------------------------------------------------
-- State
---------------------------------------------------------------------------------------------------

local db
local frame = CreateFrame("Frame")
local live = { phase = "unfocused", unfocused = {}, focused = {} }
local depth -- active paging state or nil
local lastNewest -- newest guild message ID seen by the live checker

local function bump(name)
    local t = live[live.phase]
    t[name] = (t[name] or 0) + 1
end

---------------------------------------------------------------------------------------------------
-- Items 1, 2, 5, 6, 7
---------------------------------------------------------------------------------------------------

local function probeBuild()
    local version, build, dateStr, iface = GetBuildInfo()
    db.build = {
        version = plain(version), build = plain(build), date = plain(dateStr), interface = plain(iface),
        projectId = plain(_G.WOW_PROJECT_ID), locale = GetLocale and plain(GetLocale()) or "<no GetLocale>",
        hasIsSecretValue = issecretvalue ~= nil, hasCanAccessValue = canaccessvalue ~= nil,
        serverTime = GetServerTime and GetServerTime() or "<no GetServerTime>",
    }
    say(string.format("1) build %s (%s), interface %s, WOW_PROJECT_ID %s, locale %s",
        tostring(db.build.version), tostring(db.build.build), tostring(db.build.interface),
        tostring(db.build.projectId), tostring(db.build.locale)))
end

local function probeChat()
    local out = { lockdown = InLockdown() }
    db.chat = out
    local clubId = guildClub()
    if not clubId then say("2) no guild club (not in a guild, or clubs not loaded yet)") return end
    out.clubId = plain(clubId)
    if out.lockdown then say("2) chat messaging lockdown active - try again out of combat") return end
    if C_GuildInfo and C_GuildInfo.IsDiscordStreamSeparate then
        out.discordSeparate = plain(C_GuildInfo.IsDiscordStreamSeparate())
    end
    out.streams = {}
    for _, s in ipairs(C_Club.GetStreams(clubId) or {}) do
        out.streams[#out.streams + 1] = {
            streamId = plain(s.streamId), name = plain(s.name), streamType = plain(s.streamType),
            leadersAndModeratorsOnly = plain(s.leadersAndModeratorsOnly),
        }
        say(string.format("2) stream id=%s type=%s name=%s", tostring(plain(s.streamId)),
            tostring(plain(s.streamType)), tostring(plain(s.name))))
    end
    local sid = guildStream(clubId)
    if not sid then say("2) no Guild stream (type 1) found") return end
    out.guildStreamId = plain(sid)
    out.ranges = {}
    for i, r in ipairs(C_Club.GetMessageRanges(clubId, sid) or {}) do
        out.ranges[i] = { oldest = msgIdString(r.oldestMessageId), newest = msgIdString(r.newestMessageId) }
    end
    say(string.format("2) guild stream %s: %d message range(s)", tostring(plain(sid)), #out.ranges))
    local r = lastRange(clubId, sid)
    if not r then
        say("2) no usable range yet - requesting history; run /glprobe again in a few seconds")
        C_Club.RequestMoreMessagesBefore(clubId, sid, nil)
        return
    end
    out.messages = {}
    local authorKeys = {}
    local msgs = C_Club.GetMessagesBefore(clubId, sid, r.newestMessageId, 20) or {}
    for _, m in ipairs(msgs) do
        local row = {
            id = msgIdString(m.messageId), when = idDate(m.messageId),
            content = plain(m.content), destroyed = plain(m.destroyed), edited = plain(m.edited),
            destroyer = m.destroyer and plain(m.destroyer) or nil,
            author = {},
            epochType = type(m.messageId) ~= "table" and "<no messageId>"
                or IsSecret(m.messageId.epoch) and "<secret>" or type(m.messageId.epoch),
        }
        if type(m.author) == "table" then
            for k, v in pairs(m.author) do
                if not IsSecret(k) and type(k) == "string" and v ~= nil then
                    row.author[k] = plain(v)
                    authorKeys[k] = (authorKeys[k] or 0) + 1
                end
            end
        end
        out.messages[#out.messages + 1] = row
    end
    out.authorFieldCounts = authorKeys
    local keys = {}
    for k, n in pairs(authorKeys) do keys[#keys + 1] = k .. "=" .. n end
    table.sort(keys)
    say(string.format("2) read %d messages; non-nil author fields: %s", #out.messages, table.concat(keys, ", ")))
    local first = out.messages[#out.messages]
    if first then
        say(string.format("2) newest: [%s] %s (guid %s)", first.when, tostring(first.author.name),
            tostring(first.author.guid or "absent")))
    end
end

local function probeRoster()
    local out = {}
    db.roster = out
    if not (GetNumGuildMembers and GetGuildRosterInfo) then say("6) roster API missing") return end
    out.count = plain(GetNumGuildMembers())
    out.row1 = capture(GetGuildRosterInfo, 1)
    -- capture() puts pcall's status first, so return value k is at index k + 1.
    local guid = out.row1[18]
    say(string.format("6) %s members; row 1 has %d values (incl. pcall ok); value 1=%s, 17=%s",
        tostring(out.count), out.row1.n - 1, tostring(out.row1[2]), tostring(guid)))
    if out.count == 0 or out.count == "<secret>" then
        say("6) roster empty - requested a refresh, run /glprobe again shortly")
        if C_GuildInfo and C_GuildInfo.GuildRoster then C_GuildInfo.GuildRoster() end
    end
end

local function probeFormats()
    local names = {
        "ERR_GUILD_JOIN_S", "ERR_GUILD_LEAVE_S", "ERR_GUILD_REMOVE_SS", "ERR_GUILD_PROMOTE_SSS",
        "ERR_GUILD_DEMOTE_SSS", "GUILDEVENT_TYPE_INVITE", "GUILDEVENT_TYPE_JOIN", "GUILDEVENT_TYPE_REMOVE",
        "GUILDEVENT_TYPE_QUIT", "GUILDEVENT_TYPE_PROMOTE", "GUILDEVENT_TYPE_DEMOTE",
    }
    db.formats = {}
    for _, n in ipairs(names) do
        db.formats[n] = plain(_G[n])
        if n:find("^ERR_") then say(string.format("7) %s = %s", n, tostring(db.formats[n]))) end
    end
end

local function probeEventLogRequest()
    if not (QueryGuildEventLog and GetNumGuildEvents and GetGuildEventInfo) then
        db.eventLog = { missing = true }
        say("5) guild event log API missing")
        return
    end
    db.eventLog = { requested = GetServerTime and GetServerTime() }
    frame:RegisterEvent("GUILD_EVENT_LOG_UPDATE")
    QueryGuildEventLog()
    say("5) guild event log requested...")
end

local function onEventLog()
    frame:UnregisterEvent("GUILD_EVENT_LOG_UPDATE")
    local n = GetNumGuildEvents()
    local out = db.eventLog or {}
    db.eventLog = out
    out.count = plain(n)
    out.first, out.last = {}, {}
    if type(n) ~= "number" then say("5) event count unreadable") return end
    for i = 1, math.min(10, n) do out.first[#out.first + 1] = capture(GetGuildEventInfo, i) end
    for i = math.max(1, n - 9), n do out.last[#out.last + 1] = capture(GetGuildEventInfo, i) end
    say(string.format("5) guild event log: %d entries (first 10 and last 10 saved)", n))
    for i = 1, math.min(3, #out.first) do
        local e = out.first[i]
        say(string.format("5) #%d %s p1=%s p2=%s rank=%s y/m/d/h=%s/%s/%s/%s", i, tostring(e[2]),
            tostring(e[3]), tostring(e[4]), tostring(e[5]), tostring(e[6]), tostring(e[7]), tostring(e[8]),
            tostring(e[9])))
    end
end

---------------------------------------------------------------------------------------------------
-- Item 3: history depth
---------------------------------------------------------------------------------------------------

local function depthFinish(reason)
    if not depth then return end
    local clubId, sid = depth.clubId, depth.sid
    local r, nRanges = lastRange(clubId, sid)
    local total
    if r and C_Club.GetMessagesInRange then
        total = #(C_Club.GetMessagesInRange(clubId, sid, r.oldestMessageId, r.newestMessageId) or {})
    end
    db.depth = {
        reason = reason, pages = depth.pages, ranges = nRanges, total = total,
        oldestId = r and msgIdString(r.oldestMessageId), oldest = r and idDate(r.oldestMessageId),
        newest = r and idDate(r.newestMessageId), seconds = GetTime() - depth.started,
        alreadyHad = depth.alreadyHad,
    }
    say(string.format("3) depth done (%s): %d pages, %s messages, oldest %s, %s range(s)", reason,
        depth.pages, tostring(total), tostring(db.depth.oldest), tostring(nRanges)))
    depth = nil
end

local function depthStep()
    if not depth then return end
    if InLockdown() then depthFinish("lockdown") return end
    local clubId, sid = depth.clubId, depth.sid
    local r = lastRange(clubId, sid)
    local token = {}
    depth.token = token
    if r and C_Club.IsBeginningOfStream(clubId, sid, r.oldestMessageId) then depthFinish("beginning") return end
    if depth.pages >= MAX_PAGES then depthFinish("page cap") return end
    local had
    if r then
        had = C_Club.RequestMoreMessagesBefore(clubId, sid, r.oldestMessageId, 100)
    else
        had = C_Club.RequestMoreMessagesBefore(clubId, sid, nil)
    end
    if had and not IsSecret(had) then depth.alreadyHad = depth.alreadyHad + 1 end
    -- No answer within 15 s means the server has nothing older (or ignores us).
    C_Timer.After(15, function()
        if depth and depth.token == token then depthFinish("timeout (no history event in 15 s)") end
    end)
    if had and not IsSecret(had) then
        -- Client says it already has the messages; it may not fire the event. Advance shortly.
        C_Timer.After(1, function()
            if depth and depth.token == token then depth.pages = depth.pages + 1 depthStep() end
        end)
    end
end

local function depthStart()
    if depth then say("3) already running") return end
    local clubId = guildClub()
    local sid = clubId and guildStream(clubId)
    if not sid then say("3) no guild stream") return end
    if InLockdown() then say("3) lockdown - try later") return end
    depth = { clubId = clubId, sid = sid, pages = 0, started = GetTime(), alreadyHad = 0 }
    frame:RegisterEvent("CLUB_MESSAGE_HISTORY_RECEIVED")
    say("3) paging back through guild history (max " .. MAX_PAGES .. " pages)...")
    depthStep()
end

---------------------------------------------------------------------------------------------------
-- Item 4: live behaviour (counts only, no content)
---------------------------------------------------------------------------------------------------

local function checkRangeGrew()
    if InLockdown() then bump("check_lockdown") return end
    local clubId = guildClub()
    local sid = clubId and guildStream(clubId)
    if not sid then return end
    local r = lastRange(clubId, sid)
    if not r then bump("check_norange") return end
    local n = r.newestMessageId
    if lastNewest and idNewer(n, lastNewest) then bump("range_grew") else bump("range_same") end
    lastNewest = { epoch = n.epoch, position = n.position }
end

local function liveReport()
    for _, phase in ipairs({ "unfocused", "focused" }) do
        local keys = {}
        for k, n in pairs(live[phase]) do keys[#keys + 1] = k .. "=" .. n end
        table.sort(keys)
        say(string.format("4) %s: %s", phase, #keys > 0 and table.concat(keys, ", ") or "(nothing yet)"))
    end
    say("4) current phase: " .. live.phase)
    db.live = plain(live)
end

local function focus()
    local clubId = guildClub()
    local sid = clubId and guildStream(clubId)
    if not sid then say("4) no guild stream") return end
    local ok = C_Club.FocusStream(clubId, sid)
    live.phase = "focused"
    say("4) FocusStream returned " .. tostring(plain(ok)) .. "; counting into 'focused' now")
    db.live = plain(live)
end

---------------------------------------------------------------------------------------------------
-- Events and slash command
---------------------------------------------------------------------------------------------------

local handlers = {}

function handlers.ADDON_LOADED(name)
    if name ~= ADDON then return end
    GLProbeDB = GLProbeDB or {}
    db = GLProbeDB
    frame:UnregisterEvent("ADDON_LOADED")
end

-- Item 4c (added after the first run showed club `content` is a protected kstring "|Kw1|k"):
-- record CHAT_MSG_GUILD and CLUB_MESSAGE_ADDED side by side to see whether the live text is plain
-- and whether each line can be paired with its club message ID (order, timing, same author GUID).
local PAIR_MAX = 60

local function pairLog(row)
    db.pair = db.pair or {}
    if #db.pair >= PAIR_MAX then return end
    row.t = GetTime()
    row.st = GetServerTime and GetServerTime()
    db.pair[#db.pair + 1] = row
end

local function describeText(text)
    if IsSecret(text) then return "<secret>", nil end
    if type(text) ~= "string" then return plain(text), nil end
    return text, text:find("^|K") ~= nil
end

function handlers.CHAT_MSG_GUILD(...)
    bump("CHAT_MSG_GUILD")
    C_Timer.After(1, checkRangeGrew)
    local text, name = ...
    local lineID, guid = select(11, ...)
    local shown, isK = describeText(text)
    pairLog({ ev = "chat", text = shown, isK = isK, name = plain(name), lineID = plain(lineID),
        guid = plain(guid), discord = plain(select(18, ...)) })
end

local function pairClub(clubId, streamId, messageId)
    if InLockdown() then pairLog({ ev = "club", lockdown = true }) return end
    local row = { ev = "club", sid = plain(streamId), id = msgIdString(messageId) }
    local m = C_Club.GetMessageInfo and C_Club.GetMessageInfo(clubId, streamId, messageId)
    if type(m) == "table" then
        local shown, isK = describeText(m.content)
        row.content, row.isK = shown, isK
        if type(m.author) == "table" then
            row.name, row.guid = plain(m.author.name), plain(m.author.guid)
        end
    else
        row.noInfo = true
    end
    pairLog(row)
end

function handlers.CLUB_MESSAGE_ADDED(clubId, streamId, messageId)
    if IsSecret(clubId, streamId) then bump("club_added_secretargs") return end
    if clubId == guildClub() then
        bump("CLUB_MESSAGE_ADDED")
        pairClub(clubId, streamId, messageId)
    else
        bump("CLUB_MESSAGE_ADDED_otherclub")
    end
end

local function pairReport()
    local list = db.pair or {}
    local chat, club, chatK, clubK = 0, 0, 0, 0
    for _, r in ipairs(list) do
        if r.ev == "chat" then chat = chat + 1 if r.isK then chatK = chatK + 1 end end
        if r.ev == "club" then club = club + 1 if r.isK then clubK = clubK + 1 end end
    end
    say(string.format("4c) %d entries: CHAT_MSG_GUILD %d (%d are |K tokens), CLUB_MESSAGE_ADDED %d (%d |K)",
        #list, chat, chatK, club, clubK))
    for i = math.max(1, #list - 5), #list do
        local r = list[i]
        say(string.format("4c) %s %.2f %s guid=%s %s", r.ev, r.t or 0, tostring(r.name),
            tostring(r.guid), r.ev == "chat" and ("text=" .. tostring(r.text)) or ("id=" .. tostring(r.id))))
    end
end

function handlers.CLUB_MESSAGE_HISTORY_RECEIVED(clubId, streamId)
    bump("CLUB_MESSAGE_HISTORY_RECEIVED")
    if not depth or IsSecret(clubId, streamId) then return end
    if clubId ~= depth.clubId or streamId ~= depth.sid then return end
    depth.pages = depth.pages + 1
    depth.token = nil
    C_Timer.After(0.2, depthStep)
end

function handlers.GUILD_EVENT_LOG_UPDATE() onEventLog() end

function handlers.ADDON_RESTRICTION_STATE_CHANGED(rtype, state)
    bump("ADDON_RESTRICTION_STATE_CHANGED")
    db.restrictionChanges = db.restrictionChanges or {}
    local list = db.restrictionChanges
    if #list < 50 then list[#list + 1] = { type = plain(rtype), state = plain(state) } end
end

frame:SetScript("OnEvent", function(_, event, ...)
    local h = handlers[event]
    if not h then return end
    local ok, err = pcall(h, ...)
    if not ok then say("error in " .. event .. ": " .. tostring(err)) end
end)
frame:RegisterEvent("ADDON_LOADED")
frame:RegisterEvent("CLUB_MESSAGE_ADDED")
frame:RegisterEvent("CHAT_MSG_GUILD")
frame:RegisterEvent("CLUB_MESSAGE_HISTORY_RECEIVED")
frame:RegisterEvent("ADDON_RESTRICTION_STATE_CHANGED")

local function run(fn, label)
    local ok, err = pcall(fn)
    if not ok then say(label .. " failed: " .. tostring(err)) end
end

SLASH_GLPROBE1 = "/glprobe"
SlashCmdList.GLPROBE = function(arg)
    arg = (arg or ""):lower():gsub("^%s+", ""):gsub("%s+$", "")
    if not db then say("not loaded yet") return end
    if arg == "" then
        db.ranAt = GetServerTime and GetServerTime()
        run(probeBuild, "1")
        run(probeChat, "2")
        run(probeRoster, "6")
        run(probeFormats, "7")
        run(probeEventLogRequest, "5")
        say("done. /reload to write GLProbeDB to disk.")
    elseif arg == "depth" then run(depthStart, "3")
    elseif arg == "focus" then run(focus, "4")
    elseif arg == "live" then run(liveReport, "4")
    elseif arg == "pair" then run(pairReport, "4c")
    elseif arg == "reset" then
        for k in pairs(db) do db[k] = nil end
        say("GLProbeDB cleared")
    else say("usage: /glprobe [depth|focus|live|reset]") end
end
