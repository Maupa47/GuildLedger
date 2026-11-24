----------------------------------------------------------------------
-- Amazing Hub - saved data from before the re-pin (Amazing Forever Guild Pack 0.7.0; our own file, not upstream)
--
-- Since WoW: Forever's patch of 2026-11-21 the client answers no realm name. The pack's 0.6 hub then saved the
-- guild's data under "<guild>-" (no realm). From 0.7 the hub finds the realm again (from the account's characters)
-- and opens "<guild>-<realm>", where the data from before 21/11 is. MergeRealmless copies what was saved under
-- "<guild>-" over, once per guild (admin's decision 2026-11-24, docs/addon/HUB_AUDIT.md 10.5):
--   - no "<guild>-<realm>" yet: a copy of the whole table;
--   - both: what the target lacks is copied; a value both have takes the "<guild>-" one (it is the newer);
--     lists (1..n) get the entries the target does not have yet, appended at the end;
--   - tables keyed by member ("Name-<realm>" in the target): "Name" becomes "Name-<realm>" before merging.
-- Nothing is deleted: "<guild>-" stays in the file, so the copy can be checked. Done once
-- (AmazingHubDB._packRealmMerged[<guild>-] = time).
--
-- Called by Core.lua's ResolveGuildDB (tools/rebrand-hub.py patch). Copied in from addon/hub-extra/; edit it there.
----------------------------------------------------------------------
local M = {}
AmazingHub.PackMigrate = M

local function isList(t)
    local n = #t
    if n == 0 then return false end
    local count = 0
    for _ in pairs(t) do count = count + 1 end
    return count == n
end

local function copy(v)
    if type(v) ~= "table" then return v end
    local out = {}
    for k, x in pairs(v) do out[k] = copy(x) end
    return out
end

-- The same text for equal values, whatever the order of their keys (to find list entries already there).
local function sig(v, depth)
    local t = type(v)
    if t == "string" then return string.format("%q", v) end
    if t ~= "table" then return tostring(v) end
    if depth > 6 then return "{...}" end
    local keys = {}
    for k in pairs(v) do keys[#keys + 1] = k end
    table.sort(keys, function(a, b)
        local ta, tb = type(a), type(b)
        if ta ~= tb then return ta < tb end
        if ta == "number" or ta == "string" then return a < b end
        return tostring(a) < tostring(b)
    end)
    local parts = {}
    for _, k in ipairs(keys) do parts[#parts + 1] = sig(k, depth + 1) .. "=" .. sig(v[k], depth + 1) end
    return "{" .. table.concat(parts, ",") .. "}"
end

local function endsWith(s, tail) return #s >= #tail and s:sub(-#tail) == tail end

-- A table keyed by member: some of the target's keys carry the realm and none of the source's do.
local function memberKeyed(dst, src, suffix)
    local dstHas, srcHas = false, false
    for k in pairs(dst) do if type(k) == "string" and endsWith(k, suffix) then dstHas = true break end end
    if not dstHas then return false end
    for k in pairs(src) do if type(k) == "string" and endsWith(k, suffix) then srcHas = true break end end
    return not srcHas
end

local merge
merge = function(dst, src, suffix)
    if isList(dst) and isList(src) then
        local have = {}
        for _, v in ipairs(dst) do have[sig(v, 0)] = true end
        for _, v in ipairs(src) do
            local s = sig(v, 0)
            if not have[s] then
                dst[#dst + 1] = copy(v)
                have[s] = true
            end
        end
        return
    end
    local rekey = memberKeyed(dst, src, suffix)
    for k, v in pairs(src) do
        local key = k
        if rekey and type(k) == "string" and k ~= "" and not endsWith(k, suffix) then key = k .. suffix end
        local cur = dst[key]
        if type(cur) == "table" and type(v) == "table" then
            merge(cur, v, suffix)
        else
            dst[key] = copy(v) -- missing, or both have it: the realmless one is the newer
        end
    end
end
M.Merge = merge -- for the tests

-- dbKey = "<guild>-<realm>" as the hub resolved it; realm = the realm in it. Returns what it did.
function M:MergeRealmless(dbKey, realm)
    local db = AmazingHubDB
    if type(db) ~= "table" or type(dbKey) ~= "string" or type(realm) ~= "string" then return "none" end
    if realm == "" or realm == "Unknown" or not endsWith(dbKey, "-" .. realm) then return "none" end
    local old = dbKey:sub(1, #dbKey - #realm) -- "<guild>-"
    local src = db[old]
    if type(src) ~= "table" or old == dbKey then return "none" end
    db._packRealmMerged = type(db._packRealmMerged) == "table" and db._packRealmMerged or {}
    if db._packRealmMerged[old] then return "done before" end
    local dst = db[dbKey]
    local what
    if type(dst) ~= "table" then
        db[dbKey] = copy(src)
        what = "copied"
    else
        merge(dst, src, "-" .. realm)
        what = "merged"
    end
    db._packRealmMerged[old] = (type(time) == "function" and time()) or 1
    return what
end
