----------------------------------------------------------------------
-- Amazing Hub - click a column heading to sort by it, click again to flip ascending / descending
-- (Amazing Forever Guild Pack 0.5.4; our own file, not upstream). Used by the DKP standings and both Professions
-- tables (tools/rebrand-hub.py patches them); the Roster sorts this way already. Until a heading is clicked a table
-- keeps its own order. The choice is remembered per table (settings.tableSort).
--
-- Copied in by tools/rebrand-hub.py from addon/hub-extra/; edit it there.
----------------------------------------------------------------------
local T = {}
AmazingHub.TableSort = T

local UP = "|TInterface\\BUTTONS\\Arrow-Up-Up:12:12|t"     -- the Roster's own arrows (RosterFrame.lua)
local DOWN = "|TInterface\\BUTTONS\\Arrow-Down-Up:12:12|t"

local function store()
    local s = AmazingHub:GetSetting("tableSort")
    if type(s) ~= "table" then
        s = {}
        AmazingHub:SetSetting("tableSort", s)
    end
    return s
end

-- The chosen column of table `id` and its direction: key, asc (nil when none was chosen).
function T.Get(id)
    local e = store()[id]
    if type(e) == "table" and type(e.key) == "string" then return e.key, e.asc == true end
end

-- A click on column `key`: the same column flips, another one starts ascending (numbers: largest first).
function T.Toggle(id, key, numeric)
    local s = store()
    local e = s[id]
    if type(e) == "table" and e.key == key then
        e.asc = not e.asc
    else
        s[id] = { key = key, asc = not numeric }
    end
end

-- Sort `list` in place by the chosen column: getters[key](row) gives a number, a string or nil. Empty cells go
-- last either way; equal ones keep their order. Without a choice the list stays as it is.
function T.Apply(id, list, getters)
    local key, asc = T.Get(id)
    local get = key and getters and getters[key]
    if type(list) ~= "table" or not get then return list end
    local val, pos, text = {}, {}, false
    for i, row in ipairs(list) do
        local ok, v = pcall(get, row)
        if not ok then v = nil end
        if type(v) ~= "number" and type(v) ~= "string" then v = nil end
        if type(v) == "string" then text = true end
        val[row], pos[row] = v, i
    end
    if text then -- a number next to a string cannot be compared: all as lower-case text then
        for row, v in pairs(val) do val[row] = tostring(v):lower() end
    end
    table.sort(list, function(a, b)
        local va, vb = val[a], val[b]
        if va == nil or vb == nil then
            if va == vb then return pos[a] < pos[b] end
            return va ~= nil
        end
        if va == vb then return pos[a] < pos[b] end
        if asc then return va < vb end
        return va > vb
    end)
    return list
end

-- Make the heading `fs` (a font string) of column `key` clickable; label = its text without the arrow.
-- onChange() redraws the table. numeric: the first click sorts largest first.
function T.Header(fs, id, key, label, onChange, numeric)
    if not fs or not fs.GetParent then return end
    local btn = fs.amzSortButton
    if not btn then
        btn = CreateFrame("Button", nil, fs:GetParent())
        btn:SetAllPoints(fs)
        fs.amzSortButton = btn
    end
    btn:SetScript("OnClick", function()
        T.Toggle(id, key, numeric)
        onChange()
    end)
    local chosen, asc = T.Get(id)
    fs:SetText((label or "") .. (chosen == key and (" " .. (asc and UP or DOWN)) or ""))
end

-- heads = { { fs, key, label, numeric }, ... }
function T.Headers(id, heads, onChange)
    for _, h in ipairs(heads) do T.Header(h[1], id, h[2], h[3], onChange, h[4]) end
end

-- Column values of the Professions tables (Modules/ProfDirectory.lua's rows).
T.PROFESSIONS = {
    recipes = {
        name = function(r) return r.name end,
        skill = function(r) return r.yellow end,
        who = function(r) return type(r.crafters) == "table" and #r.crafters or 0 end,
        req = function(r) return r.reqSkill end,
    },
    crafters = {
        name = function(r) return r.name end,
        skill = function(r) return r.rank end,
        who = function(r) return r.count end,
        req = function(r) return r.spec end,
    },
}
T.PROFESSIONS_NUMERIC = { skill = true, who = true }

-- Column values of the DKP standings (Modules/Points.lua GetStandings rows).
T.POINTS = {
    name = function(s) return s.name end,
    current = function(s) return s.current end,
    earned = function(s) return s.earned end,
    spent = function(s) return s.spent end,
}
