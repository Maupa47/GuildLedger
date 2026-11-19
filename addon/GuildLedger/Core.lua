-- Core: event dispatch (errors caught and rate-limited), output, slash commands.

local ADDON, ns = ...
local C = ns.Compat
local PREFIX = "|cff33ff99GuildLedger|r: "

ns.errors = 0
local lastErrorPrint = -100

-- While ns.Capture runs, output goes into a list instead of the chat frame (GuildLedgerAPI.GetStatus).
local capture

function ns.Capture(fn)
    local out = {}
    capture = out
    local ok, err = pcall(fn)
    capture = nil
    if not ok then out[#out + 1] = { kind = "line", text = "(could not read: " .. tostring(err) .. ")" } end
    return out
end

function ns.Print(msg)
    if capture then capture[#capture + 1] = { kind = "print", text = msg } return end
    if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage(PREFIX .. msg) end
end

-- A message nobody asked for right now (e.g. a collector confirming a link code later): shown only with
-- /gl messages on (opts.messages, default off; also Amazing Hub's Settings -> CHAT MESSAGES).
function ns.Notice(msg)
    if ns.Store.Opts().messages or ns.Store.Opts().debug then ns.Print(msg) end
end

-- Developer mode (/gl dev on, opts.dev; also Amazing Hub's Settings -> CHAT MESSAGES): readable reports of what
-- GuildLedger sends and receives (history found, missing text asked for, lines received from whom, what is still
-- missing). Also shown while /gl debug is on. Off by default.
function ns.Info(msg)
    local o = ns.Store.Opts()
    if o.dev or o.debug then ns.Print("|cff7fbfff" .. msg .. "|r") end
end

-- "Mon 13:05": a time in the last few days.
function ns.When(ts) return ts and date("%a %H:%M", ts) or "?" end

-- /gl status layout: a gold heading per section, then indented lines, one fact per line.
function ns.Head(text)
    if capture then capture[#capture + 1] = { kind = "head", text = text } return end
    if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage("|cffffd100" .. text .. "|r") end
end

function ns.Line(text)
    if capture then capture[#capture + 1] = { kind = "line", text = text } return end
    if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage("   " .. text) end
end

-- 12345 -> "12,345"
function ns.Num(n)
    local s = tostring(math.floor(tonumber(n) or 0))
    local out = s:reverse():gsub("(%d%d%d)", "%1,"):reverse()
    return (out:gsub("^,", ""))
end

function ns.Clock(ts) return ts and date("%H:%M", ts) or "never" end

-- With /gl debug on: print, and keep the last 400 lines in GuildLedgerDB.diag for later reading.
-- quiet = true: only into diag (for things that happen too often to print).
function ns.Debug(msg, quiet)
    if not ns.Store.Opts().debug then return end
    if not quiet then ns.Print("|cff888888" .. msg .. "|r") end
    local db = ns.Store.DB()
    if not db then return end
    db.diag = db.diag or {}
    table.insert(db.diag, date("%H:%M:%S ") .. msg)
    while #db.diag > 400 do table.remove(db.diag, 1) end
end

local function reportError(where, err)
    ns.errors = ns.errors + 1
    ns.lastError = where .. ": " .. tostring(err)
    -- Silent by default (players see nothing in chat); /gl status shows the count, debug prints it.
    local now = C.Clock()
    if ns.Store.Opts().debug and now - lastErrorPrint > 10 then
        lastErrorPrint = now
        ns.Print("|cffff5555error|r in " .. ns.lastError .. " (/gl status shows the count)")
    end
end

-- Run fn(...) and swallow errors (no Lua error popups on login, ever).
function ns.Safe(where, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok then reportError(where, err) end
end

---------------------------------------------------------------------------------------------------
-- Events
---------------------------------------------------------------------------------------------------

local frame = CreateFrame("Frame")
local handlers = {} -- event -> { fn, ... }

function ns.On(event, fn)
    if not handlers[event] then
        handlers[event] = {}
        frame:RegisterEvent(event)
    end
    table.insert(handlers[event], fn)
end

frame:SetScript("OnEvent", function(_, event, ...)
    local list = handlers[event]
    if not list then return end
    for i = 1, #list do ns.Safe(event, list[i], ...) end
end)

---------------------------------------------------------------------------------------------------
-- Timing (Phase 6): last and worst duration of the heavy steps, shown by /gl status
---------------------------------------------------------------------------------------------------

ns.perf = {} -- name -> { last = ms, max = ms, n = count }
ns.perfOrder = {}

function ns.Timed(name, fn, ...)
    local t0 = C.ProfileMs()
    fn(...)
    local t1 = t0 and C.ProfileMs()
    if not t1 then return end
    local p = ns.perf[name]
    if not p then
        p = { max = 0, n = 0 }
        ns.perf[name] = p
        ns.perfOrder[#ns.perfOrder + 1] = name
    end
    p.last, p.n = t1 - t0, p.n + 1
    if p.last > p.max then p.max = p.last end
end

ns.modules = {}
function ns.Module(name)
    local m = { name = name }
    ns.modules[#ns.modules + 1] = m
    return m
end

ns.On("ADDON_LOADED", function(name)
    if name ~= ADDON then return end
    if not ns.Store.Init() then
        ns.disabled = "its saved data comes from a newer GuildLedger version; please update the addon"
        return -- silent; /gl status explains it
    end
    for _, m in ipairs(ns.modules) do
        if m.OnInit then ns.Safe(m.name .. ".OnInit", m.OnInit) end
    end
end)

ns.On("PLAYER_LOGOUT", function()
    ns.Store.MarkSaved()
end)

---------------------------------------------------------------------------------------------------
-- Slash commands
---------------------------------------------------------------------------------------------------

local function onOff(v) return v and "|cff33ff33on|r" or "|cff888888off|r" end

local MISSING_NAMES = { club = "guild chat", roster = "member list", eventlog = "guild log",
    comm = "sharing with other players", sysformats = "join/leave messages", timer = "timers",
    servertime = "server time", secrets = "secret-value checks" }

local function status()
    if ns.disabled then ns.Print("switched off: " .. ns.disabled) return end
    local o = ns.Store.Opts()
    ns.Print("status, version " .. ns.Store.VERSION)
    if o.collector then
        ns.Line("Role: |cff33ff33Collector|r - saves guild chat and roster changes for the Discord log"
            .. " (the companion program on this PC sends them).")
    else
        ns.Line("Role: Member - keeps recent guild chat and gives it to the officers' collectors.")
    end
    local missing = {}
    for k in pairs(C.missing) do missing[#missing + 1] = MISSING_NAMES[k] or k end
    table.sort(missing)
    if ns.errors == 0 and #missing == 0 then
        ns.Line("Problems: none.")
    else
        if ns.errors > 0 then
            ns.Line(string.format("|cffff5555Problems: %d error(s).|r Last one: %s", ns.errors, tostring(ns.lastError)))
        end
        if #missing > 0 then
            ns.Line("Not available in this game version: " .. table.concat(missing, ", ") .. ".")
        end
    end
    if C.InLockdown() then
        ns.Line("Boss-fight chat lock: |cffffaa00ON|r - the game hides chat from addons right now;"
            .. " GuildLedger catches up afterwards.")
    else
        ns.Line("Boss-fight chat lock: off.")
    end
    for _, m in ipairs(ns.modules) do
        if m.Status then ns.Safe(m.name .. ".Status", m.Status) end
    end
    ns.Head("Saving")
    if ns.Store.unsaved > 0 then
        ns.Line(string.format("%s change(s) not saved to disk yet. They are saved on /reload or logout"
            .. " (/gl flush saves now).", ns.Num(ns.Store.unsaved)))
    else
        ns.Line("Nothing new to save.")
    end
    if o.debug and #ns.perfOrder > 0 then
        ns.Head("Timing (debug)")
        for _, name in ipairs(ns.perfOrder) do
            local p = ns.perf[name]
            ns.Line(string.format("%s: %.1f ms last time, %.1f ms at most (%d times)", name, p.last, p.max, p.n))
        end
    end
    ns.Head("Settings")
    ns.Line(string.format("Collector: %s - Officer chat: %s - Chat messages: %s - Login greeting: %s"
        .. " - Developer mode: %s - Debug messages: %s", onOff(o.collector), onOff(o.officer), onOff(o.messages),
        onOff(o.welcome ~= false), onOff(o.dev), onOff(o.debug)))
end

ns.StatusReport = status -- GuildLedgerAPI.GetStatus captures exactly these lines

local function usage()
    ns.Print("commands: /gl status, /gl who, /gl link CODE, /gl map (world-map dots), /gl sync, /gl flush,"
        .. " /gl collector on|off, /gl officer on|off, /gl messages on|off, /gl welcome on|off (login greeting),"
        .. " /gl dev on|off (what is sent and"
        .. " received), /gl debug on|off")
end

SLASH_GUILDLEDGER1 = "/gl"
SLASH_GUILDLEDGER2 = "/guildledger"
SlashCmdList.GUILDLEDGER = function(msg)
    local msg0 = msg
    msg = (msg or ""):lower()
    local cmd, arg, arg2 = msg:match("^%s*(%S*)%s*(%S*)%s*(%S*)")
    local o = ns.Store.Opts()
    if cmd == "" or cmd == "status" then
        status()
    elseif cmd == "link" then
        if ns.Link and ns.Link.Request then
            local raw = (msg0 or ""):match("^%s*%S+%s+(%S+)")
            ns.Safe("Link.request", ns.Link.Request, raw)
        end
    elseif cmd == "map" then
        if ns.Map and ns.Map.Command then ns.Safe("Map.command", ns.Map.Command, arg, arg2) end
    elseif cmd == "who" then
        if ns.Relay and ns.Relay.Who then ns.Safe("Relay.who", ns.Relay.Who) end
    elseif cmd == "sync" then
        for _, m in ipairs(ns.modules) do
            if m.Sync then ns.Safe(m.name .. ".Sync", m.Sync, true) end
        end
        ns.Print("sync started")
    elseif cmd == "flush" then
        ns.Store.MarkSaved()
        C.Reload()
    elseif (cmd == "officer" or cmd == "debug" or cmd == "collector" or cmd == "messages" or cmd == "dev"
        or cmd == "welcome")
        and (arg == "on" or arg == "off") then
        o[cmd] = arg == "on"
        ns.Print(cmd .. " " .. onOff(o[cmd]))
        if cmd == "collector" then
            ns.Print("role " .. (o.collector and "collector (run the companion)" or "member")
                .. ": takes effect after /reload")
        end
        for _, m in ipairs(ns.modules) do
            if m.OnOption then ns.Safe(m.name .. ".OnOption", m.OnOption, cmd) end
        end
    else
        usage()
    end
end
