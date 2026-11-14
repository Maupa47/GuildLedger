-- Map (docs/PACK_PLAN.md section 9): guild members who share their position, as dots on the world map.
-- Demand-driven, so an idle guild sends nothing (budget in shared/schema.md 5):
--   V mapID        a viewer: "my world map shows this map" (while it is open, at most every 30 s)
--   P mapID x y    a sharer: "I am here" (x, y 0..9999) - only while a V for their map or a parent map was
--                  heard in the last 45 s, at most every 10 s, and only if moved or 30 s passed.
-- Sharing is ON by default (decision 6, 2026-11-14); /gl map share off is remembered (opts.mapOptOut).
-- Never in instances, during a boss-fight lock or outside the guild. Positions live in memory only.

local _, ns = ...
local C, S = ns.Compat, ns.Store
local Comms = ns.Comms
local M = ns.Module("Map")
ns.Map = M

local SEP = Comms.SEP
local TICK = 1
local WATCH_EVERY = 30 -- s: a viewer repeats its V while the map stays open on the same map
local WATCH_TTL = 45 -- s: a sharer answers V messages heard within this
local POS_GAP = 10 -- s: at most one P per sharer this often
local POS_REFRESH = 30 -- s: P again even without moving, so dots do not fade
local MOVE_MIN = 30 -- in 0..9999 units: smaller moves are not worth a message
local FADE_AFTER, DROP_AFTER = 60, 120 -- s: dots fade, then disappear
local PARENT_DEPTH = 8
local ROSTER_REFRESH = 600 -- s: viewers ask the game for the member list (for class colours) this often
local DOT_SIZE = 10

local watches = {} -- [mapID] = GetTime() of the last V heard
local positions = {} -- [sender] = { map, x, y, at }
local lastWatch = { map = nil, at = -1e9 }
local lastPos = { map = nil, x = -1e9, y = -1e9, at = -1e9 }
local stats = { sentP = 0, sentV = 0, shown = 0 }
local rosterInfo, rosterAt = {}, -1e9 -- [name] = { level, class }
local pins = {} -- frames on the map canvas, reused
local canvasOf -- canvas the pins belong to

local function opts() return S.Opts() end
local function sharing() return opts().mapOptOut ~= true end

local function club()
    if ns.Chat and ns.Chat.Club then return ns.Chat.Club() end
end

local function parents(mapID)
    local chain, id = { mapID }, mapID
    for _ = 1, PARENT_DEPTH do
        local parent = C.MapInfo(id)
        if not parent or parent == 0 or parent == id then break end
        chain[#chain + 1] = parent
        id = parent
    end
    return chain
end

local function watched(mapID, now)
    for _, id in ipairs(parents(mapID)) do
        if watches[id] and now - watches[id] <= WATCH_TTL then return true end
    end
    return false
end
M.watched = watched

---------------------------------------------------------------------------------------------------
-- Receiving
---------------------------------------------------------------------------------------------------

local function int(v, lo, hi)
    v = tonumber(v)
    if not v or v ~= math.floor(v) or v < lo or v > hi then return nil end
    return v
end

Comms.Handle("V", function(_, text, me)
    if me then return end
    local id = int(text:match("^V\t(%d+)$"), 1, 1e9)
    if id then watches[id] = C.Clock() end
end)

Comms.Handle("P", function(sender, text, me)
    if me or not opts().mapPins then return end
    local m, x, y = text:match("^P\t(%d+)\t(%d+)\t(%d+)$")
    m, x, y = int(m, 1, 1e9), int(x, 0, 9999), int(y, 0, 9999)
    if not (m and x and y) then return end
    positions[sender] = { map = m, x = x, y = y, at = C.Clock() }
end)

---------------------------------------------------------------------------------------------------
-- Sharing my position
---------------------------------------------------------------------------------------------------

local function share(now)
    if not sharing() or not club() or C.InLockdown() or C.InInstance() then return end
    if now - lastPos.at < POS_GAP then return end
    local map = C.PlayerMap()
    if not map or not watched(map, now) then return end
    local fx, fy = C.PlayerMapPos(map)
    if not fx then return end
    local x, y = math.floor(fx * 9999 + 0.5), math.floor(fy * 9999 + 0.5)
    local moved = map ~= lastPos.map or math.abs(x - lastPos.x) + math.abs(y - lastPos.y) >= MOVE_MIN
    if not moved and now - lastPos.at < POS_REFRESH then return end
    Comms.Send(table.concat({ "P", map, x, y }, SEP), Comms.HIGH)
    lastPos.map, lastPos.x, lastPos.y, lastPos.at = map, x, y, now
    stats.sentP = stats.sentP + 1
end

---------------------------------------------------------------------------------------------------
-- Showing others
---------------------------------------------------------------------------------------------------

local function memberInfo(sender)
    local wait = next(rosterInfo) and ROSTER_REFRESH or 5 -- empty: the list may still be loading
    if C.Clock() - rosterAt > wait then
        rosterAt = C.Clock()
        rosterInfo = {}
        C.RequestRoster()
        for i = 1, C.RosterCount() do
            local r = C.RosterRow(i)
            if r then rosterInfo[r.n] = { level = r.l, class = r.c } end
        end
    end
    for name, info in pairs(rosterInfo) do -- the sender may carry "-Realm"; never split names, compare whole
        if sender == name or sender:sub(1, #name + 1) == name .. "-" then return info, name end
    end
    return nil
end

local function hideFrom(i)
    for k = i, #pins do pins[k]:Hide() end
end

local function pinFor(i, canvas)
    local pin = pins[i]
    if pin and pin:GetParent() == canvas then return pin end
    pin = CreateFrame("Frame", nil, canvas)
    pin.dot = pin:CreateTexture(nil, "OVERLAY")
    pin.dot:SetAllPoints()
    pin:SetFrameStrata("HIGH")
    pin:EnableMouse(true)
    pin:SetScript("OnEnter", function(self)
        if not GameTooltip or not self.info then return end
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:AddLine(self.info.name)
        if self.info.detail then GameTooltip:AddLine(self.info.detail, 1, 1, 1) end
        GameTooltip:AddLine(self.info.where, 0.8, 0.8, 0.8)
        GameTooltip:Show()
    end)
    pin:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    pins[i] = pin
    return pin
end

-- Position of a sharer's point on the displayed map (0..1), or nil when it is not on that map.
local function project(p, view)
    local fx, fy = p.x / 9999, p.y / 9999
    if p.map == view then return fx, fy end
    local minX, maxX, minY, maxY = C.MapRectOn(p.map, view)
    if not minX then return nil end
    return minX + fx * (maxX - minX), minY + fy * (maxY - minY)
end
M.project = project

local function draw(frame, view, now)
    local canvas = frame:GetCanvas()
    if not canvas then return end
    if canvasOf and canvasOf ~= canvas then hideFrom(1) end
    canvasOf = canvas
    local scale = frame.GetCanvasScale and frame:GetCanvasScale() or 1
    if C.IsSecret(scale) or type(scale) ~= "number" or scale <= 0 then scale = 1 end
    local w, h = canvas:GetWidth(), canvas:GetHeight()
    local n = 0
    for sender, p in pairs(positions) do
        local age = now - p.at
        local nx, ny = project(p, view)
        local info, name = memberInfo(sender)
        local known = info ~= nil or next(rosterInfo) == nil -- with a loaded member list, only guild members
        if nx and known and not C.InGroupWith(sender) then
            n = n + 1
            local pin = pinFor(n, canvas)
            local r, g, b = C.ClassColor(info and info.class)
            pin.dot:SetColorTexture(r, g, b, 1)
            pin:SetSize(DOT_SIZE / scale, DOT_SIZE / scale)
            pin:ClearAllPoints()
            pin:SetPoint("CENTER", canvas, "TOPLEFT", nx * w, -ny * h)
            pin:SetAlpha(age > FADE_AFTER and 0.4 or 1)
            local _, zone = C.MapInfo(p.map)
            pin.info = {
                name = name or sender,
                detail = info and info.level and ("level " .. info.level) or nil,
                where = (zone or "?") .. ", " .. math.floor(age) .. " s ago",
            }
            pin:Show()
        end
    end
    hideFrom(n + 1)
    stats.shown = n
end

local function view(now)
    local frame, map = C.OpenWorldMap()
    if not frame or not opts().mapPins then
        hideFrom(1)
        stats.shown = 0
        return
    end
    if map ~= lastWatch.map or now - lastWatch.at >= WATCH_EVERY then
        Comms.Send("V" .. SEP .. map, Comms.HIGH)
        lastWatch.map, lastWatch.at = map, now
        stats.sentV = stats.sentV + 1
    end
    draw(frame, map, now)
end

local function tick()
    local now = C.Clock()
    for sender, p in pairs(positions) do
        if now - p.at > DROP_AFTER then positions[sender] = nil end
    end
    for id, at in pairs(watches) do
        if now - at > WATCH_TTL then watches[id] = nil end
    end
    if not C.HasMap or not C.HasComm then return end
    ns.Safe("Map.share", share, now)
    ns.Safe("Map.view", view, now)
end

function M.OnInit()
    local o = opts()
    o.mapShare = nil -- 0.4.0 wrote an automatic "off" here; it was never the player's choice (decision 6)
    if o.mapPins == nil then o.mapPins = true end
    C.Ticker(TICK, function() ns.Safe("Map.tick", tick) end)
end

-- For tests and /gl status.
function M.Positions() return positions end

-- Quiet setter (GuildLedgerAPI, the hub's Ledger tab): "share" or "pins", on = true/false.
function M.Set(what, on)
    local o = opts()
    if what == "share" then o.mapOptOut = not on
    elseif what == "pins" then o.mapPins = on and true or false end
end

function M.Settings()
    local o = opts()
    return { available = (C.HasMap and C.HasComm) and true or false, share = sharing(), pins = o.mapPins ~= false,
        shown = stats.shown }
end

function M.Command(what, value)
    local o = opts()
    if (what == "share" or what == "pins") and (value == "on" or value == "off") then
        M.Set(what, value == "on")
        if what == "share" then
            ns.Print(sharing() and "map: your position is now shared with guild members who look at the map of"
                .. " your zone (never in instances or boss fights). /gl map share off stops it."
                or "map: your position is no longer shared.")
        else
            ns.Print(o.mapPins and "map: guild members who share their position are shown on your world map."
                or "map: guild members are no longer shown on your world map.")
        end
        return
    end
    ns.Print("map commands: /gl map share on|off (show your position to guild members), /gl map pins on|off"
        .. " (show theirs on your map)")
end

function M.Status()
    ns.Head("World map")
    if not C.HasMap or not C.HasComm then
        ns.Line("Not available in this game version.")
        return
    end
    local o = opts()
    ns.Line("Your position: " .. (sharing() and "|cff33ff33shared|r - only while a guild member looks at the map"
        .. " of your zone, never in instances or boss fights (/gl map share off stops it)."
        or "not shared (/gl map share on to share it)."))
    ns.Line("Guild members on your map: " .. (o.mapPins and "shown" or "hidden") .. ". Shown right now: "
        .. stats.shown .. ".")
    if sharing() then ns.Line(string.format("Position messages sent since login: %d.", stats.sentP)) end
end
