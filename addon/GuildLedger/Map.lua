-- Map (docs/dev/PACK_PLAN.md section 9): guild members who share their position, as dots on the world map.
-- Demand-driven, so an idle guild sends nothing (budget in shared/schema.md 5):
--   V mapID        a viewer: "my world map shows this map" (while it is open, at most every 30 s)
--   P mapID x y    a sharer: "I am here" (x, y 0..9999) - only while a V for their map or a parent map was
--                  heard in the last 45 s, at most every 10 s, and only if moved or 30 s passed.
-- Sharing is ON by default (decision 6, 2026-11-14); /gl map share off is remembered (opts.mapOptOut).
-- Never in instances, during a boss-fight lock or outside the guild. Positions live in memory only.
-- Look of the dots (0.5.2; /gl map shape|size|outline|colors, or the hub's Settings): opts.mapShape
-- ("round" | "square"), opts.mapSize (pixels), opts.mapOutline (dark rim), opts.mapColors[CLASS] = "rrggbb".
-- When and where (0.5.3; /gl map views|near|names|share zone, or the hub's Settings), all on the player's own PC,
-- the messages stay the same:
--   opts.mapViews[kind] = false   no dots (and no V sent) while the world map shows a "zone", "continent" or "world"
--   opts.mapNear = "zone"|"continent"   only guild members in my zone / on my continent (nil: anywhere)
--   opts.mapNames = true          names next to the dots (otherwise only in the tooltip)
--   opts.mapShareScope = "zone"   I answer only viewers looking at my zone's map, not at continent or world maps

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
local SIZE_MIN, SIZE_MAX, SIZE_DEFAULT = 6, 24, 12
local RIM = 2 -- px: the dark outline on each side
-- A white disc. Blizzard's own guild window (Blizzard_Communities/ClubFinder.xml) shows this file as an icon.
local ROUND = "Interface\\CharacterFrame\\TempPortraitAlphaMask"

local watches = {} -- [mapID] = GetTime() of the last V heard
local positions = {} -- [sender] = { map, x, y, at }
local lastWatch = { map = nil, at = -1e9 }
local lastPos = { map = nil, x = -1e9, y = -1e9, at = -1e9 }
local stats = { sentP = 0, sentV = 0, shown = 0 }
local rosterInfo, rosterAt = {}, -1e9 -- [name] = { level, class }
local pins = {} -- frames on the map canvas, reused
local canvasOf -- canvas the pins belong to
local levels = {} -- [mapID] = { zone = id, continent = id, kind = "zone"|"continent"|"world" } (maps never change)

local function opts() return S.Opts() end
M.SIZE_MIN, M.SIZE_MAX, M.SIZE_DEFAULT = SIZE_MIN, SIZE_MAX, SIZE_DEFAULT
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

-- Map type -> "world" | "continent" | "zone" (dungeons, cities and other small maps count as zone level).
local function kindOf(mapType)
    if mapType == 0 or mapType == 1 then return "world" end
    if mapType == 2 then return "continent" end
    return "zone"
end

-- The zone and continent a map belongs to, and what kind of map it is itself.
local function level(mapID)
    if not mapID then return nil end
    local l = levels[mapID]
    if l then return l end
    l = {}
    local id = mapID
    for _ = 1, PARENT_DEPTH + 1 do
        local parent, _, t = C.MapInfo(id)
        if id == mapID then l.kind = kindOf(t) end
        if t == 3 and not l.zone then l.zone = id end
        if t == 2 and not l.continent then l.continent = id end
        if not parent or parent == 0 or parent == id then break end
        id = parent
    end
    l.zone = l.zone or mapID
    levels[mapID] = l
    return l
end
M.level = level

-- A V for my map or a map above it; with mapShareScope "zone" only up to my zone's map, so viewers of a
-- continent or the whole world do not see me.
local function watched(mapID, now)
    local zoneOnly = opts().mapShareScope == "zone"
    local top = zoneOnly and level(mapID).zone
    for _, id in ipairs(parents(mapID)) do
        if watches[id] and now - watches[id] <= WATCH_TTL then return true end
        if zoneOnly and id == top then break end
    end
    return false
end
M.watched = watched

local function viewOn(kind)
    local v = opts().mapViews
    return not (type(v) == "table" and v[kind] == false)
end

-- Is a sharer on this map near enough for the player's mapNear choice?
local function near(map)
    local want = opts().mapNear
    if want ~= "zone" and want ~= "continent" then return true end
    local mine = C.PlayerMap()
    if not mine then return false end -- where am I? unknown (an instance): show nobody
    local a, b = level(map), level(mine)
    if want == "zone" then return a.zone == b.zone end
    return a.continent ~= nil and a.continent == b.continent
end

---------------------------------------------------------------------------------------------------
-- Receiving
---------------------------------------------------------------------------------------------------

local function int(v, lo, hi)
    v = tonumber(v)
    if not v or v ~= math.floor(v) or v < lo or v > hi then return nil end
    return v
end

---------------------------------------------------------------------------------------------------
-- Look of the dots
---------------------------------------------------------------------------------------------------

local function look()
    local o = opts()
    local size = tonumber(o.mapSize)
    size = size and math.floor(size) or SIZE_DEFAULT
    if size < SIZE_MIN or size > SIZE_MAX then size = SIZE_DEFAULT end
    return o.mapShape == "square" and "square" or "round", size, o.mapOutline ~= false
end

local function hexColor(hex)
    if type(hex) ~= "string" or not hex:match("^%x%x%x%x%x%x$") then return nil end
    return tonumber(hex:sub(1, 2), 16) / 255, tonumber(hex:sub(3, 4), 16) / 255, tonumber(hex:sub(5, 6), 16) / 255
end

-- The player's colour for a class, else the game's class colour.
local function colorOf(class)
    local own = type(class) == "string" and type(opts().mapColors) == "table" and opts().mapColors[class]
    local r, g, b = hexColor(own)
    if r then return r, g, b end
    return C.ClassColor(class)
end
M.colorOf = colorOf

local function paint(tex, shape, r, g, b, a)
    if shape == "round" then
        tex:SetTexture(ROUND)
        tex:SetVertexColor(r, g, b, a)
    else
        tex:SetColorTexture(r, g, b, a)
        tex:SetVertexColor(1, 1, 1, 1)
    end
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
        if Comms.SameName(sender, name) then return info, name end
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
    pin.rim = pin:CreateTexture(nil, "ARTWORK")
    pin.rim:SetAllPoints()
    pin.dot = pin:CreateTexture(nil, "OVERLAY")
    pin.dot:SetPoint("CENTER")
    pin.tag = false -- the name label, made on first use
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

-- The name next to a dot: a child frame at scale 1/canvas scale, so the text keeps its normal size when the
-- map is zoomed. Needs the game's small font (Blizzard's guild window uses GameFontHighlightSmall).
local function label(pin, text, scale)
    if not text then
        if pin.tag then pin.tag:Hide() end
        return
    end
    local font = GameFontHighlightSmall
    if not font then return end
    if not pin.tag then
        pin.tag = CreateFrame("Frame", nil, pin)
        pin.tag:SetSize(1, 1)
        pin.tag:SetPoint("LEFT", pin, "RIGHT")
        pin.tag.text = pin.tag:CreateFontString(nil, "OVERLAY")
        pin.tag.text:SetFontObject(font)
        pin.tag.text:SetPoint("LEFT", pin.tag, "LEFT", 2, 0)
        pin.tag.text:SetShadowColor(0, 0, 0, 1)
        pin.tag.text:SetShadowOffset(1, -1)
    end
    pin.tag:SetScale(1 / scale)
    pin.tag.text:SetText(text)
    pin.tag:Show()
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
    local shape, size, outline = look()
    local dot = size / scale
    local full = outline and (size + 2 * RIM) / scale or dot
    local n = 0
    local function put(nx, ny, info, title, age, where)
        n = n + 1
        local pin = pinFor(n, canvas)
        local r, g, b = colorOf(info and info.class)
        paint(pin.dot, shape, r, g, b, 1)
        pin.dot:SetSize(dot, dot)
        pin:SetSize(full, full)
        if outline then
            paint(pin.rim, shape, 0, 0, 0, 0.85)
            pin.rim:Show()
        else
            pin.rim:Hide()
        end
        pin:ClearAllPoints()
        pin:SetPoint("CENTER", canvas, "TOPLEFT", nx * w, -ny * h)
        pin:SetAlpha(age > FADE_AFTER and 0.4 or 1)
        label(pin, opts().mapNames and title or nil, scale)
        pin.info = { name = title, detail = info and info.level and ("level " .. info.level) or nil, where = where }
        pin:Show()
    end
    for sender, p in pairs(positions) do
        local age = now - p.at
        local nx, ny = project(p, view)
        local info, name = memberInfo(sender)
        local known = info ~= nil or next(rosterInfo) == nil -- with a loaded member list, only guild members
        if nx and known and not Comms.IsSelf(sender) and not C.InGroupWith(sender) and near(p.map) then
            local _, zone = C.MapInfo(p.map)
            put(nx, ny, info, name or sender, age, (zone or "?") .. ", " .. math.floor(age) .. " s ago")
        end
    end
    -- My own dot: off by default (the game's arrow already shows me); drawn from my own position, not a message.
    if opts().mapSelf then
        local map = C.PlayerMap()
        local fx, fy
        if map then fx, fy = C.PlayerMapPos(map) end
        if fx then
            local nx, ny = project({ map = map, x = math.floor(fx * 9999 + 0.5), y = math.floor(fy * 9999 + 0.5) },
                view)
            local me = C.PlayerName()
            if nx and me then put(nx, ny, (memberInfo(me)), me, 0, "you") end
        end
    end
    hideFrom(n + 1)
    stats.shown = n
end

local function view(now)
    local frame, map = C.OpenWorldMap()
    if not frame or not opts().mapPins or not viewOn(level(map).kind) then
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

-- For tests.
function M.Positions() return positions end
function M.Pins() return pins end

-- Quiet setter (GuildLedgerAPI, the hub's Ledger tab): "share" or "pins", on = true/false.
function M.Set(what, on)
    local o = opts()
    if what == "share" then o.mapOptOut = not on
    elseif what == "pins" then o.mapPins = on and true or false end
end

-- Change the look of the dots: "shape" ("round"|"square"), "size" (number), "outline" (boolean),
-- "color" (class file, then r, g, b 0..1; no r = the game's colour again), "reset" (everything back).
-- When and where: "view" (kind "zone"|"continent"|"world", then true/false), "near" ("any"|"zone"|"continent"),
-- "names" (boolean), "shareScope" ("all"|"zone").
-- Returns true when the value was accepted.
function M.SetLook(what, a, r, g, b)
    local o = opts()
    if what == "shape" and (a == "round" or a == "square") then
        o.mapShape = a
    elseif what == "size" and tonumber(a) then
        o.mapSize = math.max(SIZE_MIN, math.min(SIZE_MAX, math.floor(tonumber(a) + 0.5)))
    elseif what == "outline" and type(a) == "boolean" then
        o.mapOutline = a
    elseif what == "color" and type(a) == "string" and a:match("^[A-Z]+$") then
        if type(o.mapColors) ~= "table" then o.mapColors = {} end
        local function byte(v) return math.max(0, math.min(255, math.floor((tonumber(v) or 0) * 255 + 0.5))) end
        o.mapColors[a] = r and string.format("%02x%02x%02x", byte(r), byte(g), byte(b)) or nil
        if next(o.mapColors) == nil then o.mapColors = nil end
    elseif what == "view" and (a == "zone" or a == "continent" or a == "world") and type(r) == "boolean" then
        if type(o.mapViews) ~= "table" then o.mapViews = {} end
        if r then o.mapViews[a] = nil else o.mapViews[a] = false end
        if next(o.mapViews) == nil then o.mapViews = nil end
    elseif what == "near" and (a == "any" or a == "zone" or a == "continent") then
        o.mapNear = a ~= "any" and a or nil
    elseif what == "names" and type(a) == "boolean" then
        o.mapNames = a or nil
    elseif what == "shareScope" and (a == "all" or a == "zone") then
        o.mapShareScope = a == "zone" and "zone" or nil
    elseif what == "self" and type(a) == "boolean" then
        o.mapSelf = a or nil
    elseif what == "reset" then
        o.mapShape, o.mapSize, o.mapOutline, o.mapColors = nil, nil, nil, nil
        o.mapViews, o.mapNear, o.mapNames, o.mapShareScope, o.mapSelf = nil, nil, nil, nil, nil
    else
        return false
    end
    return true
end

-- Classes worth a colour choice: those in the guild, plus any the player already coloured.
local function classes()
    local seen, out = {}, {}
    local function add(c)
        if type(c) == "string" and c:match("^[A-Z]+$") and not seen[c] then seen[c] = true; out[#out + 1] = c end
    end
    for i = 1, C.RosterCount() do
        local r = C.RosterRow(i)
        if r then add(r.c) end
    end
    for c in pairs(type(opts().mapColors) == "table" and opts().mapColors or {}) do add(c) end
    table.sort(out)
    return out
end

function M.Settings()
    local o = opts()
    local shape, size, outline = look()
    local colors = {}
    for _, class in ipairs(classes()) do
        local r, g, b = colorOf(class)
        local own = type(o.mapColors) == "table" and o.mapColors[class] ~= nil
        colors[#colors + 1] = { class = class, r = r, g = g, b = b, custom = own }
    end
    return { available = (C.HasMap and C.HasComm) and true or false, share = sharing(), pins = o.mapPins ~= false,
        shown = stats.shown, shape = shape, size = size, outline = outline, sizeMin = SIZE_MIN, sizeMax = SIZE_MAX,
        colors = colors,
        views = { zone = viewOn("zone"), continent = viewOn("continent"), world = viewOn("world") },
        near = o.mapNear or "any", names = o.mapNames == true, shareScope = o.mapShareScope or "all",
        self = o.mapSelf == true }
end

function M.Command(what, value)
    local o = opts()
    if what == "share" and value == "zone" then
        M.Set("share", true)
        M.SetLook("shareScope", "zone")
        ns.Print("map: your position is shared only with guild members who look at the map of your zone (not"
            .. " continent or world maps). /gl map share on: also continent and world maps.")
        return
    end
    if what == "share" and value == "on" then M.SetLook("shareScope", "all") end
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
    local done
    if what == "shape" then
        done = M.SetLook("shape", value)
    elseif what == "size" then
        done = M.SetLook("size", value)
    elseif what == "outline" and (value == "on" or value == "off") then
        done = M.SetLook("outline", value == "on")
    elseif what == "colors" and value == "reset" then
        o.mapColors = nil
        done = true
    elseif what == "reset" then
        done = M.SetLook("reset")
    elseif what == "near" then
        if M.SetLook("near", value) then
            ns.Print(value == "any" and "map: guild members are shown wherever they are."
                or ("map: only guild members in your " .. value .. " are shown."))
            return
        end
    elseif what == "names" and (value == "on" or value == "off") then
        M.SetLook("names", value == "on")
        ns.Print("map: names next to the dots " .. value .. ".")
        return
    elseif what == "me" and (value == "on" or value == "off") then
        M.SetLook("self", value == "on")
        ns.Print("map: your own dot " .. (value == "on" and "shown." or "hidden (the game's arrow shows you)."))
        return
    elseif what == "zone" or what == "continent" or what == "world" then
        if value == "on" or value == "off" then
            M.SetLook("view", what, value == "on")
            ns.Print("map: dots on " .. what .. " maps " .. value .. ".")
            return
        end
    end
    if done then
        local shape, size, outline = look()
        ns.Print(string.format("map dots: %s, %d px, %s.", shape, size, outline and "with outline" or "no outline"))
        return
    end
    ns.Print("map commands: /gl map share on|zone|off (show your position: to everyone looking at your zone,"
        .. " continent or world map | only to those looking at your zone | nobody), /gl map pins on|off (show"
        .. " theirs on your map), /gl map near any|continent|zone (only those near you), /gl map zone|continent|"
        .. "world on|off (dots on that kind of map), /gl map names on|off, /gl map me on|off (your own dot),"
        .. " /gl map shape round|square,"
        .. " /gl map size " .. SIZE_MIN .. "-" .. SIZE_MAX .. ", /gl map outline on|off, /gl map colors reset,"
        .. " /gl map reset. Colours per class: Amazing Hub, Settings, World map.")
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
    if sharing() and o.mapShareScope == "zone" then
        ns.Line("Who sees you: only guild members who open the map of your zone.")
    end
    ns.Line("Guild members on your map: " .. (o.mapPins and "shown" or "hidden") .. ". Shown right now: "
        .. stats.shown .. ".")
    if o.mapPins then
        local kinds = {}
        for _, k in ipairs({ "zone", "continent", "world" }) do
            if viewOn(k) then kinds[#kinds + 1] = k end
        end
        local where = ({ zone = "in your zone", continent = "on your continent" })[o.mapNear] or "anywhere"
        ns.Line(string.format("Showing members %s, on %s maps%s.", where,
            #kinds > 0 and table.concat(kinds, ", ") or "no", o.mapNames and ", with names" or ""))
    end
    if sharing() then ns.Line(string.format("Position messages sent since login: %d.", stats.sentP)) end
end
