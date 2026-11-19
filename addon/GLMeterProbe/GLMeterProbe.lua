-- GLMeterProbe: a temporary test (docs/dev/INGAME_TESTS.md, "Damage meter probe"). It records what the game's own
-- damage meter (C_DamageMeter; DamageMeterDocumentation.lua in the forever branch) gives an
-- addon: once during each fight (are the values secret then?), after each fight, and after each boss
-- (ENCOUNTER_END). Everything goes into GLMeterProbeDB (written on /reload or logout); it sends nothing.
-- Delete the folder after the test.

local P = "|cff33ff99GLMeterProbe|r: "
local DB
local fightSeen = false
local events = {}

local function say(msg) if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage(P .. msg) end end
local function secret(v) return issecretvalue ~= nil and issecretvalue(v) == true end

-- A copy that is safe to keep: secret values become "<secret>"; tables are walked with depth and size caps.
local function copy(v, depth)
    depth = depth or 0
    if secret(v) then return "<secret>" end
    local t = type(v)
    if t == "table" then
        if depth >= 5 then return "<table>" end
        local out, n = {}, 0
        for k, x in pairs(v) do
            n = n + 1
            if n > 50 then out["<more>"] = true break end
            if secret(k) then out["<secret key " .. n .. ">"] = copy(x, depth + 1) else out[k] = copy(x, depth + 1) end
        end
        return out
    elseif t == "string" or t == "number" or t == "boolean" then
        return v
    end
    return "<" .. t .. ">"
end

local function call(fn, ...)
    if type(fn) ~= "function" then return false, "function missing" end
    return pcall(fn, ...)
end

local function enum(group, name)
    local e = Enum and Enum[group]
    return e and e[name]
end

local TYPES = { "DamageDone", "HealingDone", "Deaths", "Interrupts" }

-- Read everything once; reason = "during fight" | "after fight" | "boss end" | "by command".
local function capture(reason, extra)
    if not DB then return end
    local M = C_DamageMeter
    local rec = { reason = reason, at = time(), inCombat = InCombatLockdown and InCombatLockdown() or nil,
        extra = extra, byType = {} }
    if type(M) ~= "table" then
        rec.error = "C_DamageMeter missing"
    else
        local ok, list = call(M.GetAvailableCombatSessions)
        rec.sessions = ok and copy(list) or ("error: " .. tostring(list))
        local newest
        if ok and type(list) == "table" and not secret(list) then
            for _, s in ipairs(list) do
                if type(s) == "table" and not secret(s) and type(s.sessionID) == "number" and not secret(s.sessionID) then
                    if not newest or s.sessionID > newest then newest = s.sessionID end
                end
            end
        end
        rec.newest = newest
        local current = enum("DamageMeterSessionType", "Current")
        for _, name in ipairs(TYPES) do
            local tv = enum("DamageMeterType", name)
            local r = {}
            if tv == nil then
                r.missing = "Enum.DamageMeterType." .. name
            else
                if newest then
                    local ok2, s = call(M.GetCombatSessionFromID, newest, tv)
                    r.fromID = ok2 and copy(s) or ("error: " .. tostring(s))
                end
                if current then
                    local ok3, s = call(M.GetCombatSessionFromType, current, tv)
                    r.current = ok3 and copy(s) or ("error: " .. tostring(s))
                end
            end
            rec.byType[name] = r
        end
        -- My own spells in the newest session (damage): does the per-source call work?
        local dmg = enum("DamageMeterType", "DamageDone")
        local ok4, s = call(M.GetCombatSessionFromType, current, dmg)
        if newest and dmg and ok4 and type(s) == "table" and not secret(s) and type(s.combatSources) == "table"
            and not secret(s.combatSources) then
            for _, src in ipairs(s.combatSources) do
                if type(src) == "table" and not secret(src) and src.isLocalPlayer == true and not secret(src.sourceGUID) then
                    local ok5, d = call(M.GetCombatSessionSourceFromID, newest, dmg, src.sourceGUID, nil)
                    rec.mySpells = ok5 and copy(d) or ("error: " .. tostring(d))
                end
            end
        end
        if current then
            local ok6, dur = call(M.GetSessionDurationSeconds, current)
            rec.duration = ok6 and copy(dur) or ("error: " .. tostring(dur))
        end
    end
    rec.events = copy(events)
    table.insert(DB.captures, rec)
    while #DB.captures > 12 do table.remove(DB.captures, 1) end
    return rec
end

-- One line about a capture: how many players, how many names and amounts an addon can read.
local function summary(rec)
    if not rec then return "nothing captured yet" end
    if rec.error then return rec.reason .. ": " .. rec.error end
    local d = rec.byType.DamageDone or {}
    local s = d.fromID or d.current
    if type(s) ~= "table" then return rec.reason .. ": damage session " .. tostring(s) end
    local list = type(s.combatSources) == "table" and s.combatSources or {}
    local n, names, amounts, best = 0, 0, 0, {}
    for _, src in pairs(list) do
        if type(src) == "table" then
            n = n + 1
            if type(src.name) == "string" and src.name ~= "<secret>" then names = names + 1 end
            if type(src.totalAmount) == "number" then
                amounts = amounts + 1
                best[#best + 1] = string.format("%s %d", tostring(src.name), src.totalAmount)
            end
        end
    end
    return string.format("%s: %d source(s), names readable %d, amounts readable %d%s", rec.reason, n, names, amounts,
        #best > 0 and (" - " .. table.concat(best, ", ", 1, math.min(#best, 5))) or "")
end

local frame = CreateFrame("Frame")
for _, e in ipairs({ "ADDON_LOADED", "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED", "ENCOUNTER_END",
    "DAMAGE_METER_CURRENT_SESSION_UPDATED", "DAMAGE_METER_COMBAT_SESSION_UPDATED", "DAMAGE_METER_RESET" }) do
    pcall(frame.RegisterEvent, frame, e)
end

frame:SetScript("OnEvent", function(_, event, ...)
    local ok, err = pcall(function(...)
        if event == "ADDON_LOADED" then
            if ... ~= "GLMeterProbe" then return end
            GLMeterProbeDB = GLMeterProbeDB or {}
            DB = GLMeterProbeDB
            DB.captures = DB.captures or {}
            local fns = {}
            if type(C_DamageMeter) == "table" then for k in pairs(C_DamageMeter) do fns[#fns + 1] = tostring(k) end end
            table.sort(fns)
            local okA, avail, why = call(C_DamageMeter and C_DamageMeter.IsDamageMeterAvailable)
            DB.info = { build = { GetBuildInfo() }, functions = fns, available = okA and copy(avail) or "error",
                reason = okA and copy(why) or tostring(avail), types = copy(Enum and Enum.DamageMeterType),
                sessionTypes = copy(Enum and Enum.DamageMeterSessionType) }
            return
        end
        events[event] = (events[event] or 0) + 1
        if event == "PLAYER_REGEN_DISABLED" then
            fightSeen = false
        elseif event == "DAMAGE_METER_CURRENT_SESSION_UPDATED" then
            if InCombatLockdown and InCombatLockdown() and not fightSeen then
                fightSeen = true
                capture("during fight")
            end
        elseif event == "PLAYER_REGEN_ENABLED" then
            C_Timer.After(2, function()
                local rec = capture("after fight")
                say(summary(rec))
            end)
        elseif event == "ENCOUNTER_END" then
            local extra = copy({ ... })
            C_Timer.After(3, function()
                local rec = capture("boss end", extra)
                say(summary(rec))
            end)
        end
    end, ...)
    if not ok and DB then
        DB.errors = DB.errors or {}
        table.insert(DB.errors, event .. ": " .. tostring(err))
    end
end)

SLASH_GLMETERPROBE1 = "/glmeter"
SlashCmdList.GLMETERPROBE = function(msg)
    msg = (msg or ""):lower()
    if not DB then say("not loaded") return end
    if msg == "now" then
        say(summary(capture("by command")))
    elseif msg == "reset" then
        DB.captures, DB.errors = {}, nil
        say("cleared")
    else
        local info = DB.info or {}
        say(string.format("meter available: %s %s; functions: %d; captures: %d; errors: %d", tostring(info.available),
            tostring(info.reason or ""), #(info.functions or {}), #DB.captures, #(DB.errors or {})))
        say("last: " .. summary(DB.captures[#DB.captures]))
        say("/glmeter now = read now, /glmeter reset = clear. Saved to the file on /reload.")
    end
end
