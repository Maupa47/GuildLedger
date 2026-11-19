-- API: the bridge for other addons, the global GuildLedgerAPI (docs/dev/PACK_PLAN.md section 8; Amazing Hub's Ledger tab).
-- Everything returned is a fresh plain table (strings, numbers, booleans): callers cannot reach our data.
-- The only calls that change anything are the map settings and RequestLink (the same as the /gl map commands
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

-- { requested, code?, sentAt?, acked?, expired? }
function API.GetLink()
    if not ready() or not ns.Link then return { requested = false } end
    return ns.Link.Info()
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
