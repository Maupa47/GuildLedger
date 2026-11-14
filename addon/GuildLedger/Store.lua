-- Store: GuildLedgerDB layout (shared/schema.md), duplicate index, ring buffer, cursors.
-- The addon is a spool, not the archive: the companion reads the file after each save.

local _, ns = ...
local S = {}
ns.Store = S

S.VERSION = "0.5.0"
S.SCHEMA = 3
S.MAX_LINKS = 500 -- collector: link requests kept until the companion uploads them (ring buffer)
S.MEMBER_MAX = 2000 -- member role: lines kept for collectors (CLAUDE.md 5.7)
S.MEMBER_AGE = 3 * 86400
S.MAX_CHAT = 20000
S.MAX_EV = 5000
local TRIM_SLACK = 500

local db
local index = {} -- [guildKey] = { ["<s>|<id>"] = row }
local evIndex = {} -- [guildKey] = { byId = { [id] = ev }, byName = { ["<family>|<name>"] = { ev, ... } } }
S.unsaved = 0 -- rows added or changed since this session's load

local DEFAULT_OPTS = { officer = false, other = false, debug = false, pageCap = 50, collector = false }

function S.Init()
    GuildLedgerDB = GuildLedgerDB or {}
    db = GuildLedgerDB
    if db.schema == 1 then
        -- 1 -> 2: only collectors ran schema 1, so they stay collectors; rows need no change.
        db.opts = db.opts or {}
        db.opts.collector = true
        db.schema = 2
    end
    if db.schema == 2 then
        db.schema = 3 -- 2 -> 3: adds guilds[..].links (collectors) and db.link (account); nothing to convert
    end
    db.schema = db.schema or S.SCHEMA
    db.meta = db.meta or {}
    db.meta.addon = S.VERSION
    db.meta.writer = ns.Compat.PlayerName() or db.meta.writer
    db.guilds = db.guilds or {}
    db.opts = db.opts or {}
    for k, v in pairs(DEFAULT_OPTS) do
        if db.opts[k] == nil then db.opts[k] = v end
    end
    return db.schema == S.SCHEMA
end

function S.Opts() return db and db.opts or DEFAULT_OPTS end
function S.IsCollector() return S.Opts().collector == true end
function S.DB() return db end

function S.MarkSaved()
    if db then db.meta.saved = ns.Compat.Now() end
end

local function buildIndex(key, g)
    local idx = {}
    for _, row in ipairs(g.chat) do
        idx[row.s .. "|" .. row.id] = row
    end
    index[key] = idx
    return idx
end

-- The guild's table, created on first use. clubId must be a plain (non-secret) number.
function S.Guild(clubId, name)
    local key = tostring(clubId)
    local g = db.guilds[key]
    if not g then
        g = { chat = {}, cursor = {}, ev = {}, roster = {} }
        db.guilds[key] = g
    end
    g.chat = g.chat or {}
    g.cursor = g.cursor or {}
    g.ev = g.ev or {}
    g.roster = g.roster or {}
    if name then g.name = name end
    if not index[key] then buildIndex(key, g) end
    if not evIndex[key] then S.BuildEventIndex(key, g) end
    return g, key
end

---------------------------------------------------------------------------------------------------
-- Message IDs "<epoch>:<position>"
---------------------------------------------------------------------------------------------------

function S.ParseId(id)
    if type(id) ~= "string" then return nil end
    local e, p = id:match("^(%d+):(%d+)$")
    if not e then return nil end
    return tonumber(e), tonumber(p)
end

-- true when (e1, p1) is strictly newer than (e2, p2)
function S.Newer(e1, p1, e2, p2)
    if e1 ~= e2 then return e1 > e2 end
    return p1 > p2
end

---------------------------------------------------------------------------------------------------
-- Chat rows
---------------------------------------------------------------------------------------------------

local function trimChat(key, g)
    local chat = g.chat
    if #chat <= S.MAX_CHAT + TRIM_SLACK then return end
    table.sort(chat, function(a, b)
        if a.t ~= b.t then return a.t < b.t end
        return a.id < b.id
    end)
    local keep, first = {}, #chat - S.MAX_CHAT + 1
    for i = first, #chat do keep[#keep + 1] = chat[i] end
    g.chat = keep
    g.floor = keep[1].t -- history sync must not re-add what was trimmed
    buildIndex(key, g)
end

-- Rows older than this (unix s) were trimmed from the spool; nil = nothing trimmed yet.
function S.Floor(clubId)
    return S.Guild(clubId).floor
end

-- Insert a row, or merge it into the stored copy. Returns "new", "updated" or nil (no change).
-- A later copy may add text where there was none and set ed/del/fd; it never replaces text.
function S.AddChat(clubId, row)
    local g, key = S.Guild(clubId)
    local idx = index[key]
    local k = row.s .. "|" .. row.id
    local old = idx[k]
    if old then
        local changed = false
        if row.m and not old.m then old.m = row.m; old.src = "live"; changed = true end
        if row.ed and not old.ed then old.ed = true; changed = true end
        if row.del and not old.del then old.del = true; changed = true end
        if row.fd and not old.fd then old.fd = true; changed = true end
        if old.a == "?" and row.a and row.a ~= "?" then old.a = row.a; changed = true end
        if changed then S.unsaved = S.unsaved + 1 return "updated" end
        return nil
    end
    g.chat[#g.chat + 1] = row
    idx[k] = row
    S.unsaved = S.unsaved + 1
    trimChat(key, g)
    return "new"
end

function S.HasChat(clubId, s, id)
    local _, key = S.Guild(clubId)
    return index[key][s .. "|" .. id]
end

function S.SetFlags(clubId, s, id, ed, del)
    local row = S.HasChat(clubId, s, id)
    if not row then return false end
    local changed = false
    if ed and not row.ed then row.ed = true; changed = true end
    if del and not row.del then row.del = true; changed = true end
    if changed then S.unsaved = S.unsaved + 1 end
    return changed
end

-- Cursor: newest club ID up to which a history sync has completed for stream s (contiguous).
function S.Cursor(clubId, s)
    local g = S.Guild(clubId)
    return S.ParseId(g.cursor[s])
end

function S.SetCursor(clubId, s, epoch, pos)
    local g = S.Guild(clubId)
    local ce, cp = S.ParseId(g.cursor[s])
    if not ce or S.Newer(epoch, pos, ce, cp) then
        g.cursor[s] = string.format("%.0f:%.0f", epoch, pos)
    end
end

function S.Counts(clubId)
    local g = S.Guild(clubId)
    local text, meta, ev = 0, 0, 0
    for _, row in ipairs(g.chat) do
        if row.src == "event" then ev = ev + 1
        elseif row.m then text = text + 1
        else meta = meta + 1 end
    end
    return #g.chat, text, meta, ev
end

---------------------------------------------------------------------------------------------------
-- Roster events (k: join, leave, kick, promote, demote; src: sys, diff, log)
---------------------------------------------------------------------------------------------------

-- leave and kick are the same thing seen from the roster ("gone"); used for duplicate checks.
local FAMILY = { join = "in", leave = "out", kick = "out", promote = "rank", demote = "rank" }
S.FAMILY = FAMILY

local function evKey(ev) return (FAMILY[ev.k] or ev.k) .. "|" .. ev.n end

function S.BuildEventIndex(key, g)
    local byId, byName = {}, {}
    for _, ev in ipairs(g.ev) do
        byId[ev.id] = ev
        local k = evKey(ev)
        byName[k] = byName[k] or {}
        table.insert(byName[k], ev)
    end
    evIndex[key] = { byId = byId, byName = byName }
end

-- Events of the same family for this name; filter(ev) -> bool. Returns the first match or nil.
function S.FindEvent(clubId, kind, name, filter)
    local _, key = S.Guild(clubId)
    local list = evIndex[key].byName[(FAMILY[kind] or kind) .. "|" .. name]
    if not list then return nil end
    for i = #list, 1, -1 do
        if filter(list[i]) then return list[i] end
    end
end

-- Insert an event unless its ID exists. Returns true when stored.
function S.AddEvent(clubId, ev)
    local g, key = S.Guild(clubId)
    local idx = evIndex[key]
    if idx.byId[ev.id] then return false end
    g.ev[#g.ev + 1] = ev
    idx.byId[ev.id] = ev
    local k = evKey(ev)
    idx.byName[k] = idx.byName[k] or {}
    table.insert(idx.byName[k], ev)
    S.unsaved = S.unsaved + 1
    if #g.ev > S.MAX_EV + TRIM_SLACK then
        table.sort(g.ev, function(a, b)
            if a.t ~= b.t then return a.t < b.t end
            return a.id < b.id
        end)
        local keep = {}
        for i = #g.ev - S.MAX_EV + 1, #g.ev do keep[#keep + 1] = g.ev[i] end
        g.ev = keep
        S.BuildEventIndex(key, g)
    end
    return true
end

---------------------------------------------------------------------------------------------------
-- Member role (CLAUDE.md 5.7): a small buffer of lines with text, for collectors
---------------------------------------------------------------------------------------------------

local function keepRows(clubId, keep)
    local g, key = S.Guild(clubId)
    local out = {}
    for _, row in ipairs(g.chat) do
        if keep(row) then out[#out + 1] = row end
    end
    local removed = #g.chat - #out
    if removed > 0 then
        g.chat = out
        buildIndex(key, g)
        S.unsaved = S.unsaved + 1
    end
    return removed
end

-- Drop the lines a collector confirmed (ids = { [id] = true }). Returns how many were removed.
function S.RemoveChat(clubId, ids)
    return keepRows(clubId, function(row) return not ids[row.id] end)
end

-- Member buffer limits: nothing older than MEMBER_AGE, at most MEMBER_MAX lines (oldest go first).
function S.PruneMember(clubId, now)
    local g = S.Guild(clubId)
    local cutoff = now - S.MEMBER_AGE
    local removed = keepRows(clubId, function(row) return row.t >= cutoff and row.m ~= nil end)
    local extra = #g.chat - S.MEMBER_MAX
    if extra > 0 then
        table.sort(g.chat, function(a, b)
            if a.t ~= b.t then return a.t < b.t end
            return a.id < b.id
        end)
        local i = 0
        removed = removed + keepRows(clubId, function() i = i + 1 return i > extra end)
    end
    return removed
end

---------------------------------------------------------------------------------------------------
-- Discord link requests heard by a collector (schema 3; docs/PACK_PLAN.md section 10)
---------------------------------------------------------------------------------------------------

-- row = { id, t, k = "link"|"alt", code?, tag, n = sender, g = GUID if known }. Returns true when new.
function S.AddLink(clubId, row)
    local g = S.Guild(clubId)
    g.links = g.links or {}
    for _, r in ipairs(g.links) do
        if r.id == row.id then return false end
    end
    g.links[#g.links + 1] = row
    while #g.links > S.MAX_LINKS do table.remove(g.links, 1) end
    S.unsaved = S.unsaved + 1
    return true
end

-- Account-wide link state: { tag = "...", pending = { code, at, acked }, requested = true once acked }.
function S.LinkState()
    db.link = db.link or {}
    return db.link
end
