-- API: the bridge for other addons, the global GuildLedgerAPI (docs/dev/archive/PACK_PLAN.md section 8; Amazing Hub's Ledger tab).
-- Everything returned is a fresh plain table (strings, numbers, booleans): callers cannot reach our data.
-- The only calls that change anything are the settings switches (map, messages, collector role) and RequestLink (the same as the /gl map commands
-- and /gl link CODE, but without a chat line).
-- Every function is safe to call at any time, also before ADDON_LOADED or when GuildLedger switched itself off.

local _, ns = ...
local S = ns.Store

local API = { apiVersion = 1 }

local function ready() return not ns.disabled and S.DB() ~= nil end

function API.Version() return S.VERSION end

function API.IsCollector() return ready() and S.IsCollector() or false end

function API.GetModules()
    local out = {}
    for i, m in ipairs(ns.modules) do out[i] = m.name end
    return out
end

-- { version, role = "collector"|"member", disabled = text|nil, errors, lockdown, unsaved,
--   lines = { { kind = "print"|"head"|"line", text }, ... } }: the lines are exactly what /gl status prints.
function API.GetStatus()
    local lockdown = false
    pcall(function() lockdown = ns.Compat.InLockdown() and true or false end)
    return {
        version = S.VERSION,
        role = API.IsCollector() and "collector" or "member",
        disabled = ns.disabled,
        errors = ns.errors,
        lockdown = lockdown,
        unsaved = S.unsaved,
        lines = ns.Capture(ns.StatusReport),
    }
end

-- { available, share, pins, shown, shape = "round"|"square", size, sizeMin, sizeMax, outline,
--   colors = { { class = "MAGE", r, g, b, custom = true|false }, ... } (classes in the guild) }
function API.GetMap()
    if not ready() or not ns.Map then
        return { available = false, share = false, pins = false, shown = 0, colors = {} }
    end
    return ns.Map.Settings()
end

function API.SetMapShare(on) if ready() and ns.Map then ns.Map.Set("share", on and true or false) end end
function API.SetMapPins(on) if ready() and ns.Map then ns.Map.Set("pins", on and true or false) end end

-- Look of the dots (same as /gl map shape|size|outline|reset): what = "shape" ("round"|"square"), "size" (number),
-- "outline" (boolean), "color" (class file, r, g, b 0..1; no r = the game's class colour), "reset". true if accepted.
function API.SetMapLook(what, a, r, g, b)
    if not ready() or not ns.Map then return false end
    return ns.Map.SetLook(what, a, r, g, b) and true or false
end

-- Chat messages nobody asked for right now (same as /gl messages on|off). Default off.
function API.GetMessages() return ready() and ns.Store.Opts().messages == true or false end
function API.SetMessages(on) if ready() then ns.Store.Opts().messages = on and true or false end end

-- Login greeting and the guild's message of the day (same as /gl welcome on|off). Default on.
function API.GetWelcome() return ready() and ns.Store.Opts().welcome ~= false or false end
function API.SetWelcome(on) if ready() then ns.Store.Opts().welcome = on and true or false end end

-- Developer mode: readable reports of what is sent and received (same as /gl dev on|off). Default off.
function API.GetDevMode() return ready() and ns.Store.Opts().dev == true or false end
function API.SetDevMode(on) if ready() then ns.Store.Opts().dev = on and true or false end end

-- Collector role (same as /gl collector on|off; officers who run the companion). The role is saved for the
-- whole WoW account, so it covers every character on it. A change takes effect after /reload:
-- GetCollector() -> wanted (the saved switch), active (the role this session is running with).
function API.GetCollector()
    if not ready() then return false, false end
    local want = S.Opts().collector == true
    if ns.startedAsCollector == nil then return want, want end
    return want, ns.startedAsCollector
end
function API.SetCollector(on) if ready() then S.Opts().collector = on and true or false end end

-- { requested, code?, sentAt?, acked?, expired? }
function API.GetLink()
    if not ready() or not ns.Link then return { requested = false } end
    return ns.Link.Info()
end

-- G4 (0.7.0): when a member's current stay in the guild began, as far as this client knows:
-- { t = unix s, estimated = bool, src = "join"|"chat"|"seen" } or nil. The newest join event, else the earliest
-- of the first guild chat line since the last leave and the member list's first-seen time.
function API.GetJoined(who)
    if not ready() or type(who) ~= "string" then return nil end
    local cid = ns.Chat and ns.Chat.Club and ns.Chat.Club()
    if not cid then return nil end
    local g = S.Guild(cid)
    local roster = g.roster or {}
    local guid, name = nil, nil
    if roster[who] then
        guid, name = who, roster[who].n
    else
        for id, m in pairs(roster) do
            if m.n == who then guid, name = id, m.n break end
        end
        name = name or who
    end
    local join, left
    for _, ev in ipairs(g.ev or {}) do
        if (guid and ev.g == guid) or ev.n == name then
            if ev.k == "join" and (not join or ev.t > join.t) then join = ev end
            if (ev.k == "leave" or ev.k == "kick") and (not left or ev.t > left) then left = ev.t end
        end
    end
    local first = guid and g.first and g.first[guid]
    if first and left and first < left then first = nil end -- a line from an earlier stay
    if join and not (first and first < join.t and not join.p) then
        return { t = join.t, estimated = not join.p, src = "join" }
    end
    local fs = guid and roster[guid] and roster[guid].fs
    if first and (not fs or first <= fs) then return { t = first, estimated = true, src = "chat" } end
    if fs then return { t = fs, estimated = true, src = "seen" } end
    return nil
end

-- Collectors: link requests recorded since the data file was last saved, { { name, kind, t }, ... } (G3).
function API.GetLinkQueue()
    if not ready() or not ns.Link or not S.IsCollector() then return {} end
    return ns.Link.Queue()
end

-- Save the data file now (= /gl flush): the game reloads the interface. Only from a click or a command.
function API.Flush()
    if not ready() then return end
    S.MarkSaved()
    ns.Compat.Reload()
end

-- Send a code from Discord's /link (same as /gl link CODE, without the chat line): ok, message.
function API.RequestLink(code)
    if not ready() or not ns.Link then return false, "GuildLedger is not running" end
    return ns.Link.Submit(code)
end

-- The newest GuildLedger version a guild member announced in the last 4 hours, if it is newer than ours:
-- version, one player who runs it. nil when we are up to date (or nobody was heard).
function API.NewerVersion()
    if not ns.Relay or not ns.Relay.VersionsSeen then return nil end
    local best, who
    for name, ver in pairs(ns.Relay.VersionsSeen()) do
        if ns.Relay.older(best or S.VERSION, ver) then best, who = ver, name end
    end
    return best, who
end

GuildLedgerAPI = API
