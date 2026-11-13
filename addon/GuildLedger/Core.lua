-- Core: event dispatch (errors caught and rate-limited), output, slash commands.

local ADDON, ns = ...
local C = ns.Compat
local PREFIX = "|cff33ff99GuildLedger|r: "

ns.errors = 0
local lastErrorPrint = -100

function ns.Print(msg)
    if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage(PREFIX .. msg) end
end

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
    local now = C.Clock()
    if now - lastErrorPrint > 10 then
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
        ns.disabled = "SavedVariables schema " .. tostring(GuildLedgerDB.schema) .. " is newer than this addon"
        ns.Print("|cffff5555disabled|r: " .. ns.disabled)
        return
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

local function status()
    if ns.disabled then ns.Print("disabled: " .. ns.disabled) return end
    local missing = {}
    for k in pairs(C.missing) do missing[#missing + 1] = k end
    table.sort(missing)
    ns.Print(string.format("v%s, lockdown %s, missing API: %s, errors: %d", ns.Store.VERSION,
        onOff(C.InLockdown()), #missing > 0 and table.concat(missing, ", ") or "none", ns.errors))
    for _, m in ipairs(ns.modules) do
        if m.Status then ns.Safe(m.name .. ".Status", m.Status) end
    end
    if #ns.perfOrder > 0 then
        local parts = {}
        for _, name in ipairs(ns.perfOrder) do
            local p = ns.perf[name]
            parts[#parts + 1] = string.format("%s %.1f/%.1f (%dx)", name, p.last, p.max, p.n)
        end
        ns.Print("timing ms last/max: " .. table.concat(parts, ", "))
    end
    ns.Print(string.format("unsaved rows this session: %d (saved on /reload or logout; /gl flush)", ns.Store.unsaved))
    local o = ns.Store.Opts()
    ns.Print(string.format("collector %s, officer %s, debug %s", onOff(o.collector), onOff(o.officer),
        onOff(o.debug)))
    if ns.lastError then ns.Print("last error: " .. ns.lastError) end
end

local function usage()
    ns.Print("/gl status | sync | flush | collector on|off | officer on|off | debug on|off")
end

SLASH_GUILDLEDGER1 = "/gl"
SLASH_GUILDLEDGER2 = "/guildledger"
SlashCmdList.GUILDLEDGER = function(msg)
    msg = (msg or ""):lower()
    local cmd, arg = msg:match("^%s*(%S*)%s*(%S*)")
    local o = ns.Store.Opts()
    if cmd == "" or cmd == "status" then
        status()
    elseif cmd == "sync" then
        for _, m in ipairs(ns.modules) do
            if m.Sync then ns.Safe(m.name .. ".Sync", m.Sync, true) end
        end
        ns.Print("sync started")
    elseif cmd == "flush" then
        ns.Store.MarkSaved()
        C.Reload()
    elseif (cmd == "officer" or cmd == "debug" or cmd == "collector") and (arg == "on" or arg == "off") then
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
