-- Minimal stub of the WoW: Forever client for running the addon under plain LuaJIT (Lua 5.1).
-- Synthetic data only. Models what Phase 0 measured: club content is a kstring, CHAT_MSG_GUILD has
-- the text, both events arrive for every line, history is downloaded in pages on request.

local W = { now = 1000, server = 1794420000, timers = {}, frames = {}, printed = {}, lockdown = false }
_G.W = W

-- Secret value: any use other than passing it along raises, like the real client.
local function boom() error("attempt to use a secret value", 2) end
local secretMeta
W.SECRET = newproxy(true)
secretMeta = getmetatable(W.SECRET)
for _, k in ipairs({ "__index", "__newindex", "__concat", "__add", "__sub", "__mul", "__div", "__mod",
    "__unm", "__pow", "__lt", "__le", "__len", "__call", "__tostring" }) do
    secretMeta[k] = boom
end
function issecretvalue(v) return v == W.SECRET end
function canaccessvalue(v) return v ~= W.SECRET end

date = os.date
time = os.time
function GetTime() return W.now end
function debugprofilestop() return os.clock() * 1000 end -- real CPU time, for the Phase 6 timing test
function GetServerTime() return W.server end
function UnitName(unit) if unit == "player" then return W.lockdown and W.SECRET or "Testa Collector" end end
function ReloadUI() W.reloaded = (W.reloaded or 0) + 1 end

Enum = { ClubStreamType = { General = 0, Guild = 1, Officer = 2, Discord = 3, Other = 4 } }
DEFAULT_CHAT_FRAME = { AddMessage = function(_, msg) W.printed[#W.printed + 1] = msg end }
SlashCmdList = {}

---------------------------------------------------------------------------------------------------
-- Timers and frames
---------------------------------------------------------------------------------------------------

C_Timer = {}
function C_Timer.After(sec, fn) W.timers[#W.timers + 1] = { at = W.now + sec, fn = fn } end
function C_Timer.NewTicker(sec, fn)
    local t = { every = sec, at = W.now + sec, fn = fn }
    function t:Cancel() self.cancelled = true end
    W.timers[#W.timers + 1] = t
    return t
end

-- Advance the clocks, running due timers in time order.
function W.advance(dt)
    local target = W.now + dt
    while true do
        local best
        for i, t in ipairs(W.timers) do
            if not t.cancelled and t.at <= target and (not best or t.at < W.timers[best].at) then best = i end
        end
        if not best then break end
        local t = W.timers[best]
        W.server = W.server + (t.at - W.now)
        W.now = t.at
        if t.every then t.at = t.at + t.every else table.remove(W.timers, best) end
        t.fn()
    end
    W.server = W.server + (target - W.now)
    W.now = target
    for i = #W.timers, 1, -1 do if W.timers[i].cancelled then table.remove(W.timers, i) end end
end

-- Frames: events for the addon's event frame; everything else (map dots) is a recording no-op object.
local function widget(parent)
    local o = { parent = parent, shown = true, points = {}, scripts = {} }
    return setmetatable(o, { __index = function(_, k)
        if k == "GetParent" then return function(self) return self.parent end end
        if k == "Show" then return function(self) self.shown = true end end
        if k == "Hide" then return function(self) self.shown = false end end
        if k == "IsShown" then return function(self) return self.shown end end
        if k == "CreateTexture" then return function(self) return widget(self) end end
        if k == "SetPoint" then return function(self, ...) self.points = { ... } end end
        if k == "SetScript" then return function(self, what, fn) self.scripts[what] = fn end end
        if k == "SetColorTexture" then
            return function(self, r, g, b, a) self.color = { r, g, b, a }; self.texture = false end
        end
        if k == "SetTexture" then return function(self, path) self.texture = path; self.color = false end end
        if k == "SetVertexColor" then return function(self, r, g, b, a) self.vertex = { r, g, b, a } end end
        if k == "SetSize" then return function(self, w, h) self.size = { w, h } end end
        if k == "SetAlpha" then return function(self, a) self.alpha = a end end
        return function() end
    end })
end
W.widget = widget

function CreateFrame(_, _, parent)
    if parent then return widget(parent) end
    local f = { events = {} }
    function f:RegisterEvent(e) self.events[e] = true end
    function f:UnregisterEvent(e) self.events[e] = nil end
    function f:SetScript(_, fn) self.onEvent = fn end
    W.frames[#W.frames + 1] = f
    return f
end

-- World map: zone 1429 inside continent 1415; W.where = { map, x, y } is the player's position.
W.mapParents = { [1429] = 1415, [1411] = 1414, [1415] = 947, [1414] = 947 }
W.mapRects = { ["1429>1415"] = { 0.4, 0.6, 0.6, 0.8 } }
W.where = { map = 1429, x = 0.5, y = 0.25 }
W.instance = false
C_Map = {}
function C_Map.GetBestMapForUnit() return W.where and W.where.map end
function C_Map.GetPlayerMapPosition(map)
    if not W.where or W.where.map ~= map then return nil end
    return { GetXY = function() return W.where.x, W.where.y end }
end
function C_Map.GetMapInfo(id) return { mapID = id, name = "Map " .. id, parentMapID = W.mapParents[id] or 0 } end
function C_Map.GetMapRectOnMap(id, top)
    local r = W.mapRects[id .. ">" .. top]
    if r then return r[1], r[2], r[3], r[4] end
end
function IsInInstance() return W.instance, W.instance and "party" or "none" end
function UnitInParty() return false end
function UnitInRaid() return nil end
RAID_CLASS_COLORS = { MAGE = { r = 0.25, g = 0.78, b = 0.92 } }
W.canvas = widget(nil)
function W.canvas:GetWidth() return 1000 end
function W.canvas:GetHeight() return 700 end
WorldMapFrame = { open = false, map = 1429 }
function WorldMapFrame:IsShown() return self.open end
function WorldMapFrame:GetMapID() return self.map end
function WorldMapFrame:GetCanvas() return W.canvas end
function WorldMapFrame:GetCanvasScale() return 1 end

function W.fire(event, ...)
    for _, f in ipairs(W.frames) do
        if f.events[event] and f.onEvent then f.onEvent(f, event, ...) end
    end
end

---------------------------------------------------------------------------------------------------
-- Chat lockdown
---------------------------------------------------------------------------------------------------

C_ChatInfo = { InChatMessagingLockdown = function() return W.lockdown end }

-- Addon messages: what this client sends goes to W.addonOut; the test harness delivers it to the guild.
W.addonOut, W.prefixes = {}, {}
W.sendResult = nil -- force a SendAddonMessageResult (e.g. 3 throttle, 11 lockdown); nil = real behaviour
function C_ChatInfo.RegisterAddonMessagePrefix(p) W.prefixes[p] = true return 0 end
function C_ChatInfo.AreOutgoingAddonChatMessagesRestricted() return true end -- like a normal realm may answer
function C_ChatInfo.SendAddonMessage(prefix, msg, chatType)
    if prefix == W.SECRET or msg == W.SECRET then error("secret argument") end
    assert(#prefix <= 16, "prefix too long")
    assert(#msg <= 255, "addon message too long: " .. #msg)
    if W.sendResult then return W.sendResult end
    if W.lockdown then return 11 end
    W.addonOut[#W.addonOut + 1] = { prefix = prefix, msg = msg, chatType = chatType }
    return 0
end

function W.setLockdown(on)
    W.lockdown = on
    W.fire("ADDON_RESTRICTION_STATE_CHANGED", 5, on and 2 or 0)
end

---------------------------------------------------------------------------------------------------
-- Clubs
---------------------------------------------------------------------------------------------------

W.clubId = 42 -- set to nil for "not in a guild"
W.streams = { { streamId = 1, streamType = 1, name = "Guild" }, { streamId = 2, streamType = 2, name = "Officer" } }
W.msgs = { [1] = {}, [2] = {} } -- ascending by (epoch, position)
W.downloaded = { [1] = 0, [2] = 0 } -- how many of the newest messages the client holds
W.kcounter = 0

local function idLess(a, b)
    if a.epoch ~= b.epoch then return a.epoch < b.epoch end
    return a.position < b.position
end
local function idEq(a, b) return a.epoch == b.epoch and a.position == b.position end

local function held(sid)
    local all, n = W.msgs[sid], W.downloaded[sid]
    local out = {}
    for i = math.max(1, #all - n + 1), #all do out[#out + 1] = all[i] end
    return out
end

local function copyMsg(m)
    W.kcounter = W.kcounter + 1
    return {
        messageId = { epoch = m.messageId.epoch, position = m.messageId.position },
        content = "|Kw" .. W.kcounter .. "|k",
        author = m.author.discordInfo
            and { discordInfo = m.author.discordInfo, isSelf = false } -- Discord-bridged: no name, no GUID
            or { name = m.author.name, guid = m.author.guid, classID = 8, isSelf = false },
        destroyed = m.destroyed, edited = m.edited,
    }
end

local function guard(v) if W.lockdown then return W.SECRET end return v end

C_Club = {}
function C_Club.GetGuildClubId() return W.clubId end
function C_Club.GetClubInfo(cid) if cid == W.clubId then return { clubId = cid, name = guard("Synthetic Guild") } end end
function C_Club.GetStreams(cid)
    if W.lockdown then return { { streamId = W.SECRET, streamType = 1, name = W.SECRET } } end
    if cid ~= W.clubId then return {} end
    return W.streams
end
function C_Club.GetMessageRanges(cid, sid)
    if W.lockdown then return W.SECRET end
    local h = held(sid)
    if #h == 0 then return {} end
    return { { oldestMessageId = h[1].messageId, newestMessageId = h[#h].messageId } }
end
function C_Club.GetMessagesBefore(cid, sid, newest, count)
    if W.lockdown then return W.SECRET end
    local out = {}
    local h = held(sid)
    for i = #h, 1, -1 do
        if not idLess(newest, h[i].messageId) then
            table.insert(out, 1, copyMsg(h[i]))
            if #out >= count then break end
        end
    end
    return out
end
function C_Club.GetMessageInfo(cid, sid, id)
    if W.lockdown then return W.SECRET end
    for _, m in ipairs(held(sid)) do if idEq(m.messageId, id) then return copyMsg(m) end end
end
function C_Club.GetMessagesInRange() error("not used by the addon") end
-- W.retain: how many messages the server keeps (Phase 2: ~20 h); asking for older ones gets NO answer.
-- W.dropUntil: requests before this GetTime() are silently dropped (early-login behaviour).
W.retain = 1e9
function C_Club.RequestMoreMessagesBefore(cid, sid, id, count)
    if W.lockdown then error("stub: request during lockdown") end
    W.requests = (W.requests or 0) + 1
    if W.dropUntil and W.now < W.dropUntil then return false end
    local limit = math.min(#W.msgs[sid], W.retain)
    if W.downloaded[sid] >= limit then return false end -- silence, like the real server
    C_Timer.After(0.3, function()
        W.downloaded[sid] = math.min(limit, W.downloaded[sid] + (count or 100))
        W.fire("CLUB_MESSAGE_HISTORY_RECEIVED", cid, sid, {}, {})
    end)
    return false
end
function C_Club.IsBeginningOfStream(cid, sid, id)
    local first = W.msgs[sid][1]
    return first ~= nil and idEq(first.messageId, id)
end

-- Server-side message (not delivered live): history written while nobody was online.
-- discord: a Discord display name -> the message came over Blizzard's Discord link (author has only
-- discordInfo; Phase 2 measured no name and no GUID on such club messages).
function W.addHistory(sid, author, guid, at, discord, pos)
    local a = { name = author, guid = guid }
    if discord then
        a = { discordInfo = { fromDiscord = true, globalName = discord, lastOnlineName = "",
            userID = "d1", hasEmoji = false } }
    end
    local m = { messageId = { epoch = at * 1e6 + 123, position = pos or (#W.msgs[sid] + 1) },
        author = a, destroyed = false, edited = false }
    table.insert(W.msgs[sid], m)
    return m
end

-- A live line: the server stores it, then both events fire (order and gap configurable).
-- opts: clubFirst (bool), gap (s), noChat, noClub, discord (bool), event ("CHAT_MSG_GUILD"),
--       bridged (Discord display name: club author has only discordInfo; chat name = opts.chatName or "")
function W.say(sid, author, guid, text, opts)
    opts = opts or {}
    local m = W.addHistory(sid, author, guid, W.server, opts.bridged, opts.pos)
    if opts.bridged then
        opts.discord, author, guid = true, opts.chatName or "", ""
    end
    W.downloaded[sid] = W.downloaded[sid] + 1
    local event = opts.event or (sid == 2 and "CHAT_MSG_OFFICER" or "CHAT_MSG_GUILD")
    local function chat()
        if opts.noChat then return end
        local di = { fromDiscord = opts.discord or false, globalName = opts.bridged or "", lastOnlineName = "" }
        if W.lockdown then
            W.fire(event, W.SECRET, W.SECRET, "Common", "", W.SECRET, "", 0, 0, "", 7, 99, W.SECRET, 0,
                false, false, false, false, W.SECRET)
        else
            W.fire(event, text, author, "Common", "", author, "", 0, 0, "", 7, 99, guid or "", 0,
                false, false, false, false, di)
        end
    end
    local function club()
        if opts.noClub then return end
        W.fire("CLUB_MESSAGE_ADDED", W.lockdown and W.SECRET or W.clubId, W.lockdown and W.SECRET or sid,
            W.lockdown and W.SECRET or m.messageId)
    end
    local first, second = chat, club
    if opts.clubFirst then first, second = club, chat end
    first()
    if opts.gap and opts.gap > 0 then C_Timer.After(opts.gap, second) else second() end
    return m
end


---------------------------------------------------------------------------------------------------
-- Guild roster, event log, system messages (Phase 0: positions 1-4, 9, 11, 17; log index 1 = oldest)
---------------------------------------------------------------------------------------------------

ERR_GUILD_JOIN_S = "%s has joined the guild."
ERR_GUILD_LEAVE_S = "%s has left the guild."
ERR_GUILD_REMOVE_SS = "%s has been kicked out of the guild by %s."
ERR_GUILD_PROMOTE_SSS = "%s has promoted %s to %s."
ERR_GUILD_DEMOTE_SSS = "%s has demoted %s to %s."

W.roster = {} -- { name, guid, rank, rankIndex, level, class, online }
W.rosterLoaded = false -- the client knows the roster only after the first GuildRoster() answer
W.rosterHole = nil -- index of a row that reads as nil (still loading)
W.glog = {} -- { kind, p1, p2, rank, at }
W.rosterRequests = 0

C_GuildInfo = {}
function C_GuildInfo.GuildRoster()
    W.rosterRequests = W.rosterRequests + 1
    C_Timer.After(0.5, function()
        W.rosterLoaded = true
        W.fire("GUILD_ROSTER_UPDATE", true)
    end)
end
function GetNumGuildMembers()
    if not W.rosterLoaded or not W.clubId then return 0 end
    return #W.roster
end
function GetGuildRosterInfo(i)
    local m = W.roster[i]
    if not m or i == W.rosterHole then return nil end
    if W.lockdown and W.secretRoster then return W.SECRET end
    return m.name, m.rank or "Member", m.rankIndex or 3, m.level or 10, "Mage", "Zone", "", "", m.online or false,
        0, m.class or "MAGE", -1, 0, false, false, 3, m.guid
end

function QueryGuildEventLog()
    C_Timer.After(0.3, function() W.fire("GUILD_EVENT_LOG_UPDATE") end)
end
-- W.glogEnd: how many log entries the client has received so far (nil = all); it shows the last 100.
local function lastLog()
    local n = W.glogEnd or #W.glog
    local first = math.max(1, n - 99)
    return first, n - first + 1
end
function GetNumGuildEvents()
    local _, n = lastLog()
    return n
end
function GetGuildEventInfo(i)
    local first = lastLog()
    local e = W.glog[first + i - 1]
    if not e then return nil end
    local el = math.max(0, W.server - e.at)
    local days = math.floor(el / 86400)
    return e.kind, e.p1, e.p2, e.rank or "", 0, 0, days, math.floor((el % 86400) / 3600)
end

local function sys(fmt, ...)
    if W.lockdown then W.fire("CHAT_MSG_SYSTEM", W.SECRET) return end
    W.fire("CHAT_MSG_SYSTEM", string.format(fmt, ...), "", "", "", "", "", 0, 0, "", 0, 0, "")
end

local function find(name)
    for i, m in ipairs(W.roster) do if m.name == name then return i, m end end
end

-- Roster changes. Each adds the guild event log entry; system messages only reach a client that
-- is logged in (the tests unload the addon to model "offline").
function W.addMember(name, guid, opts)
    opts = opts or {}
    table.insert(W.roster, { name = name, guid = guid, online = opts.online, rankIndex = 4, rank = "Initiate" })
end
function W.join(name, guid, opts)
    W.addMember(name, guid, opts)
    table.insert(W.glog, { kind = "join", p1 = name, at = W.server })
    sys(ERR_GUILD_JOIN_S, name)
end
function W.leave(name)
    table.remove(W.roster, (find(name)))
    table.insert(W.glog, { kind = "quit", p1 = name, at = W.server })
    sys(ERR_GUILD_LEAVE_S, name)
end
function W.kick(name, actor)
    table.remove(W.roster, (find(name)))
    table.insert(W.glog, { kind = "remove", p1 = actor, p2 = name, at = W.server })
    sys(ERR_GUILD_REMOVE_SS, name, actor)
end
function W.promote(actor, name, rank)
    local _, m = find(name)
    m.rank, m.rankIndex = rank, m.rankIndex - 1
    table.insert(W.glog, { kind = "promote", p1 = actor, p2 = name, rank = rank, at = W.server })
    sys(ERR_GUILD_PROMOTE_SSS, actor, name, rank)
end
function W.sysRaw(msg) W.fire("CHAT_MSG_SYSTEM", msg) end

---------------------------------------------------------------------------------------------------
-- Loading the addon and saving SavedVariables
---------------------------------------------------------------------------------------------------

function W.loadAddon(dir, files, name)
    W.ns = {}
    for _, f in ipairs(files) do
        local chunk = assert(loadfile(dir .. "/" .. f))
        chunk(name, W.ns)
    end
    W.fire("ADDON_LOADED", name, false)
end

-- Simulate /reload: frames and timers go away, SavedVariables survive.
function W.unload()
    W.frames, W.timers = {}, {}
end

-- Logout: like unload, and the client forgets the roster.
function W.logout()
    W.unload()
    W.rosterLoaded = false
end

function W.login()
    W.fire("PLAYER_ENTERING_WORLD", true, false)
    W.fire("INITIAL_CLUBS_LOADED")
end

function W.slash(cmd)
    W.printed = {}
    SlashCmdList.GUILDLEDGER(cmd)
    return table.concat(W.printed, "\n")
end

-- Serialize a value the way WoW writes SavedVariables.
local function ser(v, out, indent)
    local t = type(v)
    if t == "string" then
        out[#out + 1] = string.format("%q", v):gsub("\\\n", "\\n")
    elseif t == "number" then
        if v == math.floor(v) and math.abs(v) < 1e15 then out[#out + 1] = string.format("%d", v)
        else out[#out + 1] = string.format("%.14g", v) end
    elseif t == "boolean" then
        out[#out + 1] = tostring(v)
    elseif t == "table" then
        out[#out + 1] = "{\n"
        local n = #v
        for i = 1, n do
            ser(v[i], out, indent)
            out[#out + 1] = ", -- [" .. i .. "]\n"
        end
        local keys = {}
        for k in pairs(v) do
            if not (type(k) == "number" and k >= 1 and k <= n and k == math.floor(k)) then keys[#keys + 1] = k end
        end
        table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
        for _, k in ipairs(keys) do
            out[#out + 1] = type(k) == "string" and string.format("[%q] = ", k) or ("[" .. k .. "] = ")
            ser(v[k], out, indent)
            out[#out + 1] = ",\n"
        end
        out[#out + 1] = "}"
    else
        error("cannot serialize " .. t)
    end
end

function W.savedVariables(name)
    local out = { "\n", name, " = " }
    ser(_G[name], out, "")
    out[#out + 1] = "\n"
    return table.concat(out)
end

return W
