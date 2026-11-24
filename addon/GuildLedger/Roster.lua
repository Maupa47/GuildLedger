-- Roster capture (CLAUDE.md 5.4): three layers.
--   1. sys:  live system messages ("X has joined the guild."), exact time.
--   2. diff: roster snapshot compared by GUID with the stored one; covers time spent offline.
--            The true time lies between the previous snapshot (w) and this one (t).
--   3. log:  the guild event log (last 100 entries, elapsed hours) for actor + approximate time.

local _, ns = ...
local C, S = ns.Compat, ns.Store
local M = ns.Module("Roster")

local LOGIN_QUIET = 8 -- s after login/reload: system messages are ignored
local DEBOUNCE = 1 -- s after GUILD_ROSTER_UPDATE
local MIN_SNAPSHOT_GAP = 30 -- s between two full roster reads (GUILD_ROSTER_UPDATE fires on every logon)
local REQUEST_GAP = 60 -- s between two roster requests
local PERIODIC = 300 -- s, periodic roster request
local SYS_SHADOW = 600 -- s: a diff event is skipped when a sys event of the family is this recent
local LOG_DUP = 2 * 3600 -- s: a log entry within this of a stored one (same kind/name/actor) is the same
local MAX_GONE = 0.2 -- refuse a snapshot that would drop more than this share of the stored roster
local CONFIRM_READS = 3 -- ... unless that many reads in a row, over CONFIRM_SPAN s, agree on it
local CONFIRM_SPAN = 120
local INIT_TRIES = 12

local clubId
local ready = false
local loginAt = 0
local lastRequest = -1e9
local lastSnapshot = -1e9
local snapshotScheduled = false
local wantLog = false
local refused = { count = 0, n = nil, since = nil }
local stats = { sys = 0, diff = 0, log = 0, snapshots = 0, untrusted = 0, refused = 0 }
local lastSnapshotNote = "not done yet"
local lastLogRead
local patterns = {} -- { { kind, pattern, order } }

---------------------------------------------------------------------------------------------------
-- System message patterns from the client's own format strings
---------------------------------------------------------------------------------------------------

-- "%s has been kicked out of the guild by %s." -> "^(.+) has been kicked out of the guild by (.+)%.$",
-- order {1, 2}. Numbered placeholders ("%2$s") map captures back to argument numbers.
local function toPattern(fmt)
    fmt = fmt:gsub("|3%-%d+%((.-)%)", "%1") -- grammar wrapper (some locales) -> its content
    local order, n = {}, 0
    local marked = fmt:gsub("%%(%d*)%$?[sd]", function(num)
        n = n + 1
        order[n] = tonumber(num) or n
        return "\001"
    end)
    local pat = marked:gsub("([%^%$%(%)%%%.%[%]%*%+%-%?])", "%%%1"):gsub("\001", "(.+)")
    return "^" .. pat .. "$", order
end
M.toPattern = toPattern

local function buildPatterns()
    patterns = {}
    local formats = C.GuildFormats()
    -- most specific first (kick contains more fixed text than leave)
    for _, kind in ipairs({ "kick", "promote", "demote", "join", "leave" }) do
        if formats[kind] then
            local pat, order = toPattern(formats[kind])
            patterns[#patterns + 1] = { kind = kind, pat = pat, order = order }
        end
    end
end

-- Argument roles per kind (Phase 0, 7): kick (target, actor); promote/demote (actor, target, rank).
local ROLES = {
    join = { n = 1 }, leave = { n = 1 }, kick = { n = 1, by = 2 },
    promote = { by = 1, n = 2, d = 3 }, demote = { by = 1, n = 2, d = 3 },
}

local function stripLinks(msg)
    msg = msg:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")
    msg = msg:gsub("|Hplayer:[^|]*|h%[(.-)%]|h", "%1"):gsub("|H[^|]*|h(.-)|h", "%1")
    return msg
end

-- kind, { n, by, d } or nil
local function parseSystem(msg)
    msg = stripLinks(msg)
    for _, p in ipairs(patterns) do
        local caps = { msg:match(p.pat) }
        if caps[1] then
            local args = {}
            for i, num in ipairs(p.order) do args[num] = caps[i] end
            local roles, out = ROLES[p.kind], {}
            for field, num in pairs(roles) do out[field] = args[num] end
            if out.n and out.n ~= "" then return p.kind, out end
        end
    end
end
M.parseSystem = parseSystem

---------------------------------------------------------------------------------------------------
-- Helpers
---------------------------------------------------------------------------------------------------

local function guidByName(name, map)
    if map then return map[name] end
    for guid, m in pairs(S.Guild(clubId).roster) do
        if m.n == name then return guid end
    end
end

local function nameMap()
    local map = {}
    for guid, m in pairs(S.Guild(clubId).roster) do map[m.n] = guid end
    return map
end

local function sysId(kind, name, by, t)
    return string.format("%s|%s|%s|%d", kind, name, by or "", math.floor(t / 5))
end

local function approxId(kind, name, by, src, t)
    return string.format("%s|%s|%s|%s:%d", kind, name, by or "", src, math.floor(t / 3600))
end

local function requestRoster(force)
    local now = C.Clock()
    if not force and now - lastRequest < REQUEST_GAP then return end
    lastRequest = now
    C.RequestRoster()
end

---------------------------------------------------------------------------------------------------
-- Layer 1: live system messages
---------------------------------------------------------------------------------------------------

ns.On("CHAT_MSG_SYSTEM", function(msg)
    if not ready or C.IsSecret(msg) or type(msg) ~= "string" then return end
    if C.Clock() - loginAt < LOGIN_QUIET then return end
    local kind, a = parseSystem(msg)
    if not kind then return end
    local t = C.Now()
    local ev = { id = sysId(kind, a.n, a.by, t), t = t, p = true, k = kind, n = a.n, g = guidByName(a.n),
        by = a.by, d = a.d, src = "sys" }
    if S.AddEvent(clubId, ev) then
        stats.sys = stats.sys + 1
        ns.Debug(string.format("roster sys %s: %s%s", kind, a.n, a.by and (" by " .. a.by) or ""))
    end
    if kind == "join" or kind == "leave" or kind == "kick" then requestRoster(true) end
end)

---------------------------------------------------------------------------------------------------
-- Layer 2: roster snapshot and diff
---------------------------------------------------------------------------------------------------

-- All rows, or nil + reason when the roster is not trustworthy yet.
local function readRoster()
    local n = C.RosterCount()
    if n == 0 then return nil, "empty" end
    local rows = {}
    for i = 1, n do
        local r = C.RosterRow(i)
        if not r then return nil, "row " .. i .. " of " .. n .. " unreadable" end
        rows[r.g] = r
    end
    return rows, n
end

local function recentSys(kind, name, now)
    return S.FindEvent(clubId, kind, name, function(ev)
        return ev.src == "sys" and now - ev.t <= SYS_SHADOW and ev.t <= now + 5
    end)
end

local function snapshot()
    lastSnapshot = C.Clock()
    local rows, n = readRoster()
    if not rows then
        stats.untrusted = stats.untrusted + 1
        lastSnapshotNote = "member list not loaded by the game yet (" .. n .. ")"
        ns.Debug("roster snapshot skipped: " .. n)
        return
    end
    local g = S.Guild(clubId)
    local stored, now = g.roster, C.Now()

    if g.rosterAt then
        local storedN, gone = 0, 0
        for guid in pairs(stored) do
            storedN = storedN + 1
            if not rows[guid] then gone = gone + 1 end
        end
        if storedN > 0 and gone > storedN * MAX_GONE then
            -- A real mass removal shows the same count on several reads; a glitch does not.
            if refused.n ~= n then refused.count, refused.n, refused.since = 0, n, now end
            refused.count = refused.count + 1
            if refused.count < CONFIRM_READS or now - refused.since < CONFIRM_SPAN then
                stats.refused = stats.refused + 1
                lastSnapshotNote = string.format("%d of %d members would be missing - refused for now,"
                    .. " waiting for confirmation (check %d of %d)", gone, storedN, refused.count, CONFIRM_READS)
                ns.Debug("roster snapshot " .. lastSnapshotNote)
                requestRoster(false)
                return
            end
            ns.Debug(string.format("roster: %d of %d gone, confirmed by %d reads", gone, storedN, refused.count))
        end
    end
    refused.count, refused.n = 0, nil

    local first = g.rosterAt == nil
    local joins, leaves = 0, 0
    for guid, r in pairs(rows) do
        local m = stored[guid]
        if not m then
            m = { fs = now }
            stored[guid] = m
            if not first then
                local sys = recentSys("join", r.n, now)
                if sys then
                    if not sys.g then sys.g = guid end
                else
                    local ev = { id = approxId("join", r.n, nil, "diff", now), t = now, w = g.rosterAt, p = false,
                        k = "join", n = r.n, g = guid, src = "diff" }
                    if S.AddEvent(clubId, ev) then joins = joins + 1 end
                end
            end
        end
        m.n, m.r, m.rn, m.l, m.c = r.n, r.r, r.rn, r.l, r.c
        if r.on then m.ls = now end -- last seen online (nil until seen online)
    end
    for guid, m in pairs(stored) do
        if not rows[guid] then
            stored[guid] = nil
            if not recentSys("leave", m.n, now) then
                local ev = { id = approxId("leave", m.n, nil, "diff", now), t = now, w = g.rosterAt, p = false,
                    k = "leave", n = m.n, g = guid, src = "diff" }
                if S.AddEvent(clubId, ev) then leaves = leaves + 1 end
            end
        end
    end
    g.rosterAt = now
    S.PruneFirst(clubId, now)
    S.unsaved = S.unsaved + ((joins + leaves > 0 or first) and 1 or 0)
    stats.snapshots = stats.snapshots + 1
    stats.diff = stats.diff + joins + leaves
    if first then
        lastSnapshotNote = string.format("first check, %d members saved", n)
    elseif joins + leaves == 0 then
        lastSnapshotNote = string.format("%d members, no changes", n)
    else
        lastSnapshotNote = string.format("%d members, %d joined, %d left", n, joins, leaves)
    end
    ns.Debug("roster snapshot: " .. lastSnapshotNote, joins + leaves == 0 and not first)
    if joins + leaves > 0 or wantLog then
        wantLog = false
        C.QueryEventLog()
    end
end

local function scheduleSnapshot()
    if snapshotScheduled then return end
    snapshotScheduled = true
    local wait = math.max(DEBOUNCE, lastSnapshot + MIN_SNAPSHOT_GAP - C.Clock())
    C.After(wait, function()
        snapshotScheduled = false
        ns.Safe("Roster.snapshot", ns.Timed, "roster snapshot", snapshot)
    end)
end

ns.On("GUILD_ROSTER_UPDATE", function()
    if ready then scheduleSnapshot() end
end)

---------------------------------------------------------------------------------------------------
-- Layer 3: guild event log
---------------------------------------------------------------------------------------------------

local LOG_KIND = { join = "join", quit = "leave", remove = "kick", promote = "promote", demote = "demote" }

-- Phase 3: after one query the event fires ~50 times within a minute, each read showing 100 entries
-- and usually one entry more than the read before (the client seems to receive a longer log in
-- pieces). Every read is processed (cheaply); one summary line is printed when the reads stop.
local logBurst = { reads = 0, added = 0, scheduled = false }

local function logSummary()
    logBurst.scheduled = false
    lastLogRead = string.format("%s - %d new entr%s", date("%H:%M"), logBurst.added,
        logBurst.added == 1 and "y" or "ies")
    ns.Debug("roster event log " .. lastLogRead)
    logBurst.reads, logBurst.added = 0, 0
end

local readLog

ns.On("GUILD_EVENT_LOG_UPDATE", function()
    if ready then ns.Timed("event log read", readLog) end
end)

readLog = function()
    local now, added = C.Now(), 0
    local count = C.EventLogCount()
    local map = nameMap()
    local firstH, lastH
    for i = 1, count do
        local kind, p1, p2, rank, hours, coarse = C.EventLogEntry(i)
        local k = kind and LOG_KIND[kind]
        if kind then
            firstH = firstH or hours
            lastH = hours
        end
        if k then
            -- join/quit: player1 = member. remove/promote/demote: player1 = actor, player2 = target
            -- (confirmed in game, Phase 3: the remove entry for a kick by X has player1 = X).
            local name, by = p1, nil
            if k == "kick" or k == "promote" or k == "demote" then name, by = p2, p1 end
            if name then
                local t = now - hours * 3600
                -- Phase 3: while the log arrives in pieces an entry can show up first without its actor
                -- (player1 nil) and again with it: a missing actor matches any actor and is filled in.
                local dup = S.FindEvent(clubId, k, name, function(ev)
                    return ev.src == "log" and ev.k == k and (ev.by == by or ev.by == nil or by == nil)
                        and math.abs(ev.t - t) <= LOG_DUP
                end)
                if dup and by and not dup.by then
                    dup.by = by
                    S.unsaved = S.unsaved + 1
                elseif not dup then
                    local ev = { id = approxId(k, name, by, "log", t), t = t, w = t - (coarse and 86400 or 3600),
                        p = false, k = k, n = name, g = guidByName(name, map), by = by,
                        d = (k == "promote" or k == "demote") and rank or nil, src = "log" }
                    if S.AddEvent(clubId, ev) then added = added + 1 end
                end
            end
        end
    end
    stats.log = stats.log + added
    logBurst.reads, logBurst.added = logBurst.reads + 1, logBurst.added + added
    ns.Debug(string.format("event log read: %d entries (index 1: %sh ago, last: %sh ago), +%d new", count,
        tostring(firstH), tostring(lastH), added), true)
    if not logBurst.scheduled then
        logBurst.scheduled = true
        C.After(5, function() ns.Safe("Roster.logSummary", logSummary) end)
    end
end

---------------------------------------------------------------------------------------------------
-- Startup, status
---------------------------------------------------------------------------------------------------

local function tryInit()
    if ns.disabled then return true end
    if not S.DB() then return false end
    if ready then return true end
    if not C.HasRoster then return true end -- nothing to do; /gl status shows "missing API: roster"
    if not S.IsCollector() then return true end -- member role: collectors track the roster (CLAUDE.md 5.7)
    local id = C.GuildClubId()
    if not id then return false end
    clubId, ready = id, true
    S.Guild(clubId)
    buildPatterns()
    wantLog = C.HasEventLog
    ns.Debug("roster ready, " .. #patterns .. " system message patterns")
    requestRoster(true)
    return true
end

local initTicker
ns.On("PLAYER_ENTERING_WORLD", function()
    loginAt = C.Clock()
    if tryInit() or initTicker then return end
    local tries = 0
    initTicker = C.Ticker(5, function()
        tries = tries + 1
        local ok = false
        ns.Safe("Roster.init", function() ok = tryInit() end)
        if (ok or tries >= INIT_TRIES) and initTicker then
            initTicker:Cancel()
            initTicker = nil
        end
    end)
end)
ns.On("INITIAL_CLUBS_LOADED", function() tryInit() end)

function M.OnInit()
    C.Ticker(PERIODIC, function()
        if ready then ns.Safe("Roster.request", requestRoster, false) end
    end)
end

function M.Sync()
    if not ready then return end
    wantLog = C.HasEventLog
    requestRoster(true)
end

function M.Status()
    ns.Head("Member list (joins, leaves, kicks, rank changes)")
    if not ready then
        if not S.IsCollector() then
            ns.Line("Not tracked by members - the collectors do this.")
        elseif not C.HasRoster then
            ns.Line("Not available in this game version.")
        else
            ns.Line("Waiting for the guild.")
        end
        return
    end
    local g = S.Guild(clubId)
    local members = 0
    for _ in pairs(g.roster) do members = members + 1 end
    ns.Line(string.format("Members saved: %s.", ns.Num(members)))
    ns.Line(string.format("Last check: %s - %s.", g.rosterAt and date("%H:%M", g.rosterAt) or "never",
        lastSnapshotNote))
    ns.Line(string.format("Changes seen since login: %d live, %d by comparing the member list, %d from the guild log.",
        stats.sys, stats.diff, stats.log))
    ns.Line("Guild log last read: " .. (lastLogRead or (C.HasEventLog and "not yet" or "not available")) .. ".")
    ns.Line(string.format("Changes saved in total: %s.", ns.Num(#g.ev)))
end
