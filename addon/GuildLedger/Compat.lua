-- Compat: every Blizzard API call goes through here, behind an existence check (CLAUDE.md 5.6).
-- All functions are documented for 1.60.1 (vendor-ref) or measured in Phase 0 (docs/dev/API_FINDINGS.md).
-- Rule: check secrets first, then bail out. Never compare, concatenate or index with a secret.

local _, ns = ...
local C = {}
ns.Compat = C

C.missing = {} -- feature name -> true when the client lacks the API

local Club = C_Club
local hasClub = Club and Club.GetGuildClubId and Club.GetStreams and Club.GetMessageRanges
    and Club.GetMessagesBefore and Club.GetMessageInfo and Club.RequestMoreMessagesBefore
    and Club.IsBeginningOfStream
if not hasClub then C.missing.club = true end
if not (C_Timer and C_Timer.After and C_Timer.NewTicker) then C.missing.timer = true end
if not GetServerTime then C.missing.servertime = true end
if not issecretvalue then C.missing.secrets = true end -- fine: then nothing is ever secret

C.STREAM_LETTER = { [1] = "g", [2] = "o", [3] = "d", [4] = "x" } -- Enum.ClubStreamType values

function C.IsSecret(...)
    if not issecretvalue then return false end
    for i = 1, select("#", ...) do
        if issecretvalue((select(i, ...))) then return true end
    end
    return false
end
local IsSecret = C.IsSecret

function C.InLockdown()
    if not (C_ChatInfo and C_ChatInfo.InChatMessagingLockdown) then return false end
    local v = C_ChatInfo.InChatMessagingLockdown()
    if IsSecret(v) then return true end
    return v and true or false
end

function C.Now()
    return GetServerTime and GetServerTime() or time()
end

-- Milliseconds for timing (debugprofilestop, CLAUDE.md 8 Phase 6); nil when the client lacks it.
function C.ProfileMs()
    if debugprofilestop then return debugprofilestop() end
end

function C.Clock()
    return GetTime and GetTime() or 0
end

function C.After(seconds, fn)
    if C_Timer and C_Timer.After then C_Timer.After(seconds, fn) end
end

function C.Ticker(seconds, fn)
    if C_Timer and C_Timer.NewTicker then return C_Timer.NewTicker(seconds, fn) end
end

function C.PlayerName()
    if not UnitName then return nil end
    local name = UnitName("player")
    if IsSecret(name) or type(name) ~= "string" then return nil end
    return name
end

function C.Reload()
    if ReloadUI then ReloadUI() end
end

---------------------------------------------------------------------------------------------------
-- Clubs
---------------------------------------------------------------------------------------------------

function C.GuildClubId()
    if not hasClub then return nil end
    local id = Club.GetGuildClubId()
    if id == nil or IsSecret(id) then return nil end
    return id
end

function C.ClubName(clubId)
    if not (Club and Club.GetClubInfo) or C.InLockdown() then return nil end
    local info = Club.GetClubInfo(clubId)
    if type(info) ~= "table" or IsSecret(info.name) or type(info.name) ~= "string" then return nil end
    return info.name
end

-- { [streamId] = streamType } for streams whose fields are readable; nil in a lockdown.
function C.Streams(clubId)
    if not hasClub or C.InLockdown() then return nil end
    local out = {}
    for _, s in ipairs(Club.GetStreams(clubId) or {}) do
        if not IsSecret(s.streamId, s.streamType) and type(s.streamType) == "number" then
            out[s.streamId] = s.streamType
        end
    end
    return out
end

-- A message ID as plain numbers, or nil when unreadable.
function C.ReadId(id)
    if type(id) ~= "table" or IsSecret(id) or IsSecret(id.epoch, id.position) then return nil end
    if type(id.epoch) ~= "number" or type(id.position) ~= "number" then return nil end
    return id.epoch, id.position
end

-- Oldest and newest message ID of the last downloaded range, or nil.
function C.LastRange(clubId, streamId)
    if not hasClub or C.InLockdown() then return nil end
    local ranges = Club.GetMessageRanges(clubId, streamId) or {}
    local r = ranges[#ranges]
    if not r then return nil end
    local oe, op = C.ReadId(r.oldestMessageId)
    local ne, np = C.ReadId(r.newestMessageId)
    if not (oe and ne) then return nil end
    if ne < oe or (ne == oe and np < op) then return nil end
    return r.oldestMessageId, r.newestMessageId
end

function C.MessagesBefore(clubId, streamId, newestId, count)
    if not hasClub or C.InLockdown() then return nil end
    return Club.GetMessagesBefore(clubId, streamId, newestId, count)
end

function C.MessageInfo(clubId, streamId, messageId)
    if not hasClub or C.InLockdown() then return nil end
    return Club.GetMessageInfo(clubId, streamId, messageId)
end

-- Returns alreadyHasMessages (true/false) or nil when the request could not be made.
function C.RequestMore(clubId, streamId, messageId, count)
    if not hasClub or C.InLockdown() then return nil end
    local had = Club.RequestMoreMessagesBefore(clubId, streamId, messageId, count)
    if IsSecret(had) then return false end
    return had and true or false
end

function C.IsBeginning(clubId, streamId, messageId)
    if not hasClub or C.InLockdown() then return false end
    local v = Club.IsBeginningOfStream(clubId, streamId, messageId)
    if IsSecret(v) then return false end
    return v and true or false
end

-- A ClubMessageInfo as the fields GuildLedger keeps, or nil if anything needed is secret.
-- `content` is never read: it is a protected kstring (Phase 0).
function C.ReadMessage(m)
    if type(m) ~= "table" or IsSecret(m) then return nil end
    local epoch, pos = C.ReadId(m.messageId)
    if not epoch then return nil end
    if IsSecret(m.destroyed, m.edited) then return nil end
    local name, guid, fd
    local a = m.author
    if type(a) == "table" and not IsSecret(a) then
        if not IsSecret(a.name) and type(a.name) == "string" and a.name ~= "" then name = a.name end
        if not IsSecret(a.guid) and type(a.guid) == "string" and a.guid ~= "" then guid = a.guid end
        local dfd, dname = C.DiscordInfo(a.discordInfo)
        if dfd then fd, name = true, name or dname end
    end
    return {
        id = string.format("%.0f:%.0f", epoch, pos), epoch = epoch, pos = pos,
        t = math.floor(epoch / 1e6), a = name or "?", g = guid, fd = fd,
        ed = m.edited == true or nil, del = m.destroyed == true or nil,
    }
end

local function plainString(v)
    if IsSecret(v) or type(v) ~= "string" or v == "" then return nil end
    return v
end

-- DiscordChatInfo (DiscordConstantsDocumentation.lua; ClubMemberInfo.discordInfo, CHAT_MSG_* arg 18).
-- Returns fromDiscord (bool) and the Discord display name (globalName, else lastOnlineName) or nil.
-- Phase 2: Discord-bridged guild messages have no author name/GUID in the club, only this.
function C.DiscordInfo(di)
    if type(di) ~= "table" or IsSecret(di) or IsSecret(di.fromDiscord) or di.fromDiscord ~= true then
        return false, nil
    end
    return true, plainString(di.globalName) or plainString(di.lastOnlineName)
end

-- Debug only: names of the non-nil fields of a plain table (never values; they may be secret).
function C.FieldNames(t)
    if type(t) ~= "table" or IsSecret(t) then return type(t) end
    local keys = {}
    for k in pairs(t) do
        if type(k) == "string" then keys[#keys + 1] = k end
    end
    table.sort(keys)
    return table.concat(keys, ",")
end

---------------------------------------------------------------------------------------------------
-- Guild roster, event log, system message formats (CLAUDE.md 2 "Roster"; Phase 0 items 5-7)
---------------------------------------------------------------------------------------------------

local hasRoster = C_GuildInfo and C_GuildInfo.GuildRoster and GetNumGuildMembers and GetGuildRosterInfo
if not hasRoster then C.missing.roster = true end
local hasLog = QueryGuildEventLog and GetNumGuildEvents and GetGuildEventInfo
if not hasLog then C.missing.eventlog = true end

C.HasRoster = hasRoster and true or false
C.HasEventLog = hasLog and true or false

function C.RequestRoster()
    if hasRoster then C_GuildInfo.GuildRoster() end
end

function C.RosterCount()
    if not hasRoster then return 0 end
    local n = GetNumGuildMembers()
    if IsSecret(n) or type(n) ~= "number" then return 0 end
    return n
end

-- One roster row, or nil when any needed value is missing or secret.
-- Positions (Phase 0, 6): 1 name, 2 rankName, 3 rankIndex, 4 level, 9 online, 11 classFile, 17 GUID.
function C.RosterRow(i)
    if not hasRoster then return nil end
    local name, rankName, rankIndex, level, _, _, _, _, online, _, classFile, _, _, _, _, _, guid =
        GetGuildRosterInfo(i)
    if IsSecret(name, rankName, rankIndex, level, online, classFile, guid) then return nil end
    if type(name) ~= "string" or name == "" or type(guid) ~= "string" or guid == "" then return nil end
    return {
        n = name, g = guid,
        r = type(rankIndex) == "number" and rankIndex or nil,
        rn = type(rankName) == "string" and rankName or nil,
        l = type(level) == "number" and level or nil,
        c = type(classFile) == "string" and classFile or nil,
        on = online == true,
    }
end

function C.QueryEventLog()
    if hasLog then QueryGuildEventLog() end
end

function C.EventLogCount()
    if not hasLog then return 0 end
    local n = GetNumGuildEvents()
    if IsSecret(n) or type(n) ~= "number" then return 0 end
    return n
end

-- type, player1, player2, rank, elapsed hours (y/m/d/h converted approximately), or nil.
-- Phase 0: index 1 = oldest; time values are elapsed time, not a date.
function C.EventLogEntry(i)
    if not hasLog then return nil end
    local kind, p1, p2, rank, y, mo, d, h = GetGuildEventInfo(i)
    if IsSecret(kind, p1, p2, rank, y, mo, d, h) or type(kind) ~= "string" then return nil end
    local hours = (((tonumber(y) or 0) * 365 + (tonumber(mo) or 0) * 30 + (tonumber(d) or 0)) * 24)
        + (tonumber(h) or 0)
    local coarse = (tonumber(y) or 0) + (tonumber(mo) or 0) + (tonumber(d) or 0) > 0
    return kind, plainString(p1), plainString(p2), plainString(rank), hours, coarse
end

-- The client's own format strings (Phase 0, 7). Missing or non-string ones are left out.
function C.GuildFormats()
    local out = {}
    for kind, name in pairs({ join = "ERR_GUILD_JOIN_S", leave = "ERR_GUILD_LEAVE_S",
        kick = "ERR_GUILD_REMOVE_SS", promote = "ERR_GUILD_PROMOTE_SSS", demote = "ERR_GUILD_DEMOTE_SSS" }) do
        local v = _G[name]
        if type(v) == "string" and not IsSecret(v) and v ~= "" then out[kind] = v end
    end
    if not next(out) then C.missing.sysformats = true end
    return out
end

---------------------------------------------------------------------------------------------------
-- Addon messages on the guild channel, for the relay only (CLAUDE.md 5.7; ChatInfoDocumentation.lua)
---------------------------------------------------------------------------------------------------

local Chat = C_ChatInfo
local hasComm = Chat and Chat.RegisterAddonMessagePrefix and Chat.SendAddonMessage
if not hasComm then C.missing.comm = true end
C.HasComm = hasComm and true or false

-- Enum.SendAddonMessageResult (documented values, used when the Enum is absent)
local RESULT = (Enum and Enum.SendAddonMessageResult) or {}
C.SEND_OK = RESULT.Success or 0
C.SEND_THROTTLED = { [RESULT.AddonMessageThrottle or 3] = true, [RESULT.ChannelThrottle or 8] = true }
C.SEND_LOCKDOWN = RESULT.AddOnMessageLockdown or 11

function C.RegisterPrefix(prefix)
    if hasComm then return Chat.RegisterAddonMessagePrefix(prefix) end
end

-- True when sending now would be refused anyway (chat lockdown). Phase 7: the realm flag
-- AreOutgoingAddonChatMessagesRestricted is NOT a reason to hold: the send result decides.
function C.CommBlocked()
    return not hasComm or C.InLockdown()
end

-- Sends on GUILD. Returns the result code (C.SEND_OK on success), or nil when it cannot send at all.
function C.SendGuild(prefix, message)
    if not hasComm or IsSecret(prefix, message) then return nil end
    local r = Chat.SendAddonMessage(prefix, message, "GUILD")
    if IsSecret(r) then return nil end
    if r == nil or r == true then return C.SEND_OK end -- older clients returned a bool
    return r
end

---------------------------------------------------------------------------------------------------
-- World map (Map.lua; MapDocumentation.lua, Blizzard_MapCanvas, InstanceDocumentation.lua, forever branch)
---------------------------------------------------------------------------------------------------

local Map = C_Map
local hasMap = Map and Map.GetBestMapForUnit and Map.GetPlayerMapPosition and Map.GetMapInfo
if not hasMap then C.missing.map = true end
C.HasMap = hasMap and true or false

function C.PlayerMap()
    if not hasMap then return nil end
    local id = Map.GetBestMapForUnit("player")
    if IsSecret(id) or type(id) ~= "number" then return nil end
    return id
end

-- The player's position on that map as 0..1, or nil (instances, secret, unknown).
function C.PlayerMapPos(mapID)
    if not hasMap or not mapID then return nil end
    local pos = Map.GetPlayerMapPosition(mapID, "player")
    if pos == nil or IsSecret(pos) or type(pos) ~= "table" or not pos.GetXY then return nil end
    local x, y = pos:GetXY()
    if IsSecret(x, y) or type(x) ~= "number" or type(y) ~= "number" then return nil end
    if x <= 0 and y <= 0 then return nil end -- the game's "no position"
    if x < 0 or x > 1 or y < 0 or y > 1 then return nil end
    return x, y
end

-- Parent map ID and name of a map, or nil.
function C.MapInfo(mapID)
    if not hasMap or not mapID then return nil end
    local info = Map.GetMapInfo(mapID)
    if type(info) ~= "table" or IsSecret(info) then return nil end
    local parent = not IsSecret(info.parentMapID) and info.parentMapID or nil
    local name = not IsSecret(info.name) and type(info.name) == "string" and info.name or nil
    -- Enum.UIMapType (MapConstantsDocumentation): 0 Cosmic, 1 World, 2 Continent, 3 Zone, 4 Dungeon, 5 Micro, 6 Orphan
    local kind = not IsSecret(info.mapType) and type(info.mapType) == "number" and info.mapType or nil
    return parent, name, kind
end

-- Where mapID lies on topMapID: minX, maxX, minY, maxY (0..1 of the top map), or nil.
function C.MapRectOn(mapID, topMapID)
    if not (Map and Map.GetMapRectOnMap) or not mapID or not topMapID then return nil end
    local ok, a, b, c, d = pcall(Map.GetMapRectOnMap, mapID, topMapID)
    if not ok or IsSecret(a, b, c, d) or type(a) ~= "number" or type(d) ~= "number" then return nil end
    if b <= a or d <= c then return nil end
    return a, b, c, d
end

function C.InInstance()
    if not IsInInstance then return false end
    local inside = IsInInstance()
    if IsSecret(inside) then return true end
    return inside and true or false
end

-- The world map's frame and displayed map, if it is open.
function C.OpenWorldMap()
    local f = WorldMapFrame
    if type(f) ~= "table" or not f.IsShown or not f:IsShown() or not f.GetMapID or not f.GetCanvas then return nil end
    local id = f:GetMapID()
    if IsSecret(id) or type(id) ~= "number" then return nil end
    return f, id
end

-- In the player's party or raid (the game draws those itself).
function C.InGroupWith(name)
    if type(name) ~= "string" then return false end
    local p = UnitInParty and UnitInParty(name)
    local r = UnitInRaid and UnitInRaid(name)
    if IsSecret(p, r) then return false end
    return (p or r) and true or false
end

function C.ClassColor(classFile)
    local c = type(classFile) == "string" and RAID_CLASS_COLORS and RAID_CLASS_COLORS[classFile]
    if type(c) ~= "table" then return 1, 1, 1 end
    return c.r or 1, c.g or 1, c.b or 1
end
