----------------------------------------------------------------------
-- Amazing Hub - a search box in the title bar with results as you type (Amazing Forever Guild Pack 0.8.0;
-- our own file, not upstream)
--
-- H2 (PLAN_COMMUNITY W12). The title bar's Search button becomes a box. Typing two letters or more opens a list
-- under it, grouped, at most MAX rows a group: Members, Recipes, Items, Bank, Settings, Tabs. A click (or Enter
-- on the marked row; Up and Down move the mark where the client offers them) goes there:
--   member  -> the Roster tab and the member's card
--   recipe  -> the Crafts tab opened on that recipe (AmazingHub:ShowCraftFor)
--   item    -> the Bank tab when the bank holds it, else the wishlist window
--   bank    -> the Bank tab
--   setting -> the Settings page, the section opened, scrolled to the switch, which blinks (SettingsPlus index)
--   tab     -> that tab
-- Shift + click puts the item's link into chat instead; a recipe that makes no item links the recipe.
-- `/amazing search text` and upstream's search window stay; Search:Query keeps its shape.
--
-- Copied in by tools/rebrand-hub.py from addon/hub-extra/; edit it there.
----------------------------------------------------------------------
local UI = AmazingHub.UI
local L = AmazingHub.L
local S = {}
AmazingHub.PackSearch = S

S.MAX = 8          -- rows per group
S.MIN_CHARS = 2
S.BOX_W = 225
S.DROP_W = 380
local ROW_H, HEAD_H = 18, 16

local function lower(s) return type(s) == "string" and s:lower() or "" end
local function has(hay, q) return lower(hay):find(q, 1, true) ~= nil end

----------------------------------------------------------------------
-- What matches (pure apart from the hub's own readers; tested under lupa)
----------------------------------------------------------------------

local function memberRows(q, add)
    local Search = AmazingHub.Search
    if not (Search and Search.Query) then return end
    local ok, res = pcall(Search.Query, Search, q)
    if not ok or type(res) ~= "table" then return end
    for _, m in ipairs(res.members or {}) do
        add({ text = string.format("%s  |cff8c8c8cL%d%s|r", m.name, m.level or 0, m.online and "" or " \194\183 offline"),
              class = m.class, go = function() S.OpenMember(m.name) end })
    end
end

local function recipeRows(q, add)
    local D = AmazingHub.ProfDirectory
    if not (D and D.RecipeRows) then return end
    local ok, rows = pcall(D.RecipeRows, nil, nil, q)
    if not ok or type(rows) ~= "table" then return end
    table.sort(rows, function(a, b)
        local ka, kb = #(a.crafters or {}) > 0, #(b.crafters or {}) > 0
        if ka ~= kb then return ka end
        return lower(a.name) < lower(b.name)
    end)
    for _, r in ipairs(rows) do
        local n = #(r.crafters or {})
        add({ text = string.format("%s  |cff8c8c8c%s|r", r.name,
                  n > 0 and string.format("%d crafters", n) or "nobody in the guild"),
              item = (r.out and r.out > 0) and r.out or nil, spell = r.id,
              go = function()
                  if r.out and r.out > 0 and AmazingHub.ShowCraftFor then AmazingHub:ShowCraftFor(r.out)
                  else UI:OpenWindow("recipes") end
              end })
    end
end

local function bankCount(id)
    local B = AmazingHub.GuildBank
    if not (B and B.CountOf) then return 0 end
    local ok, n = pcall(B.CountOf, B, id)
    return (ok and type(n) == "number") and n or 0
end

local function itemRows(q, add)
    local W = AmazingHub.Wishlist
    local cat = W and W.catalog
    if type(cat) ~= "table" then return end
    local hits = {}
    for id, e in pairs(cat) do
        if type(e) == "table" and has(e.name, q) then hits[#hits + 1] = { id = id, name = e.name } end
    end
    table.sort(hits, function(a, b)
        local sa, sb = lower(a.name):sub(1, #q) == q, lower(b.name):sub(1, #q) == q -- names that start with it first
        if sa ~= sb then return sa end
        return lower(a.name) < lower(b.name)
    end)
    for _, h in ipairs(hits) do
        add({ text = h.name, item = h.id, go = function()
            if bankCount(h.id) > 0 then UI:OpenWindow("bank")
            elseif AmazingHub.ShowWishlistFrame then AmazingHub:ShowWishlistFrame() end
        end })
    end
end

local function bankRows(q, add)
    local B = AmazingHub.GuildBank
    if not (B and B.Index and B.ItemInfo) then return end
    local ok, index = pcall(B.Index, B)
    if not ok or type(index) ~= "table" then return end
    local W, seen = AmazingHub.Wishlist, {}
    for _, e in ipairs(index.list or {}) do
        if not seen[e.id] then
            local okI, info = pcall(B.ItemInfo, B, e.id, e.l)
            local name = (okI and info and info.name)
                or (W and W.catalog and W.catalog[e.id] and W.catalog[e.id].name)
            if name and has(name, q) then
                seen[e.id] = true
                add({ text = string.format("%s  |cff8c8c8c\195\151%d|r", name, bankCount(e.id)), item = e.id,
                      go = function() UI:OpenWindow("bank") end })
            end
        end
    end
end

local function settingRows(q, add)
    local Plus = AmazingHub.SettingsPlus
    for _, e in ipairs(Plus and Plus.Index and Plus.Index() or {}) do
        if has(e.label, q) or has(e.section, q) then
            local where = e.pageLabel .. (e.section and e.section ~= e.label and (" \226\128\186 " .. e.section) or "")
            add({ text = string.format("%s  |cff8c8c8c%s|r", e.label, where),
                  go = function() Plus.Reveal(e) end })
        end
    end
end

local function tabRows(q, add)
    for _, id in ipairs(UI.featureOrder or {}) do
        local def = UI.features and UI.features[id]
        if def and def.tab and has(def.label, q) and S.TabShown(def) then
            add({ text = def.label, go = function() UI:OpenWindow(id) end })
        end
    end
end

-- Whether a tab is in the window for this player.
function S.TabShown(def)
    if def.condition and not def.condition() then return false end
    if UI.IsFeatureAbsent and UI:IsFeatureAbsent(def) then return false end
    if not AmazingHub:IsFeatureEnabled(def.id) then return false end
    if UI.IsFeatureAllowed and not UI:IsFeatureAllowed(def) then return false end
    return true
end

S.GROUPS = {
    { key = "members",  title = "MEMBERS",  rows = memberRows },
    { key = "recipes",  title = "RECIPES",  rows = recipeRows },
    { key = "items",    title = "ITEMS",    rows = itemRows },
    { key = "bank",     title = "BANK",     rows = bankRows },
    { key = "settings", title = "SETTINGS", rows = settingRows },
    { key = "tabs",     title = "TABS",     rows = tabRows },
}

-- { { key, title, rows = { { text, go, item?, class? } } } } for `text`, empty groups left out.
function S.Query(text)
    local q = lower(text):gsub("^%s+", ""):gsub("%s+$", "")
    local out = {}
    if #q < S.MIN_CHARS then return out end
    for _, g in ipairs(S.GROUPS) do
        local rows = {}
        local function add(r) if #rows < S.MAX then rows[#rows + 1] = r end end
        local ok, err = pcall(g.rows, q, add)
        if not ok and AmazingHub.RecordError then AmazingHub:RecordError("Search " .. g.key .. ": " .. tostring(err)) end
        if #rows > 0 then out[#out + 1] = { key = g.key, title = L[g.title], rows = rows } end
    end
    return out
end

-- The Roster tab and the member's card.
function S.OpenMember(name)
    UI:OpenWindow("roster")
    local key = AmazingHub.GetPlayerKey and AmazingHub:GetPlayerKey(name)
    local data = key and AmazingHub.db and AmazingHub.db.members and AmazingHub.db.members[key]
    if data and AmazingHub.ShowMemberDetail then AmazingHub:ShowMemberDetail(data) end
end

----------------------------------------------------------------------
-- The box and its list
----------------------------------------------------------------------
local drop, box
local rows, heads = {}, {}
local flat, marked = {}, 0

local function C() return AmazingHub.Colors end

local function hide()
    if drop then drop:Hide() end
end

local function pick(r)
    if not r then return end
    hide()
    if box then box:ClearFocus() end
    if IsShiftKeyDown and IsShiftKeyDown() and (r.item or r.spell) then
        -- the item; a recipe that makes none (an enchant) links itself, as in the Crafts list
        local Links = AmazingHub.PackLinks
        local link = r.item and select(2, AmazingHub.Compat.GetItemInfo(r.item)) or nil
        if not link and r.spell and Links then link = Links.RecipeLink(r.spell) end
        if link and HandleModifiedItemClick then HandleModifiedItemClick(link) end
        return
    end
    AmazingHub:SafeCall(r.go)
end

local function paintMark()
    for i, b in ipairs(rows) do
        if b:IsShown() then b.hl:SetShown(b.index == marked) end
        if i > #flat then break end
    end
end

local function row(i)
    if rows[i] then return rows[i] end
    local b = CreateFrame("Button", nil, drop)
    b:SetHeight(ROW_H)
    local hl = b:CreateTexture(nil, "BACKGROUND")
    hl:SetAllPoints()
    hl:SetColorTexture(C().accent.r, C().accent.g, C().accent.b, 0.25)
    hl:Hide()
    b.hl = hl
    b.text = UI:CreateText(b, "", 11)
    b.text:SetPoint("LEFT", 10, 0)
    b.text:SetPoint("RIGHT", -6, 0)
    b.text:SetJustifyH("LEFT")
    b.text:SetWordWrap(false)
    b:SetScript("OnClick", function(self) pick(self.data) end)
    b:SetScript("OnEnter", function(self)
        marked = self.index
        paintMark()
        if self.data and self.data.item and GameTooltip then
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:SetHyperlink("item:" .. self.data.item)
            GameTooltip:Show()
        end
    end)
    b:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    rows[i] = b
    return b
end

local function head(i)
    if heads[i] then return heads[i] end
    local fs = UI.CreateHeaderText and UI:CreateHeaderText(drop, "", 10) or UI:CreateText(drop, "", 10)
    heads[i] = fs
    return fs
end

function S.Render(text)
    if not drop then return end
    local groups = S.Query(text)
    for _, b in ipairs(rows) do b:Hide() end
    for _, h in ipairs(heads) do h:Hide() end
    flat, marked = {}, 1
    if #groups == 0 then hide(); return end
    local y, ri = 6, 0
    for gi, g in ipairs(groups) do
        local h = head(gi)
        h:ClearAllPoints()
        h:SetPoint("TOPLEFT", drop, "TOPLEFT", 8, -y)
        h:SetText(g.title)
        h:Show()
        y = y + HEAD_H
        for _, r in ipairs(g.rows) do
            ri = ri + 1
            local b = row(ri)
            b:ClearAllPoints()
            b:SetPoint("TOPLEFT", drop, "TOPLEFT", 2, -y)
            b:SetPoint("RIGHT", drop, "RIGHT", -2, 0)
            b.data, b.index = r, ri
            b.text:SetText(r.text)
            local col = r.class and AmazingHub.GetClassColor and { AmazingHub:GetClassColor(r.class) }
            if col and col[1] then b.text:SetTextColor(col[1], col[2], col[3]) else
                b.text:SetTextColor(C().text.r, C().text.g, C().text.b) end
            b:Show()
            flat[ri] = r
            y = y + ROW_H
        end
        y = y + 4
    end
    drop:SetHeight(y + 4)
    drop:Show()
    if drop.Raise then drop:Raise() end
    paintMark()
end

local function move(step)
    if #flat == 0 then return end
    marked = ((marked - 1 + step) % #flat) + 1
    paintMark()
end

function S.Attach(f)
    local btn = f and f.searchButton
    if not btn or f.__packSearch or not UI.CreateInput then return false end
    f.__packSearch = true
    btn:SetWidth(S.BOX_W)
    if btn.label then btn.label:SetText("") end
    btn:SetScript("OnClick", nil)
    box = UI:CreateInput(btn, S.BOX_W, btn:GetHeight() or 20, { placeholder = "Search everything", max = 40 })
    box:SetAllPoints(btn)
    f.packSearchBox = box

    drop = CreateFrame("Frame", "AmazingHubSearchDrop", UIParent, "BackdropTemplate")
    drop:SetFrameStrata("FULLSCREEN_DIALOG")
    drop:SetClampedToScreen(true)
    drop:SetWidth(S.DROP_W)
    drop:SetPoint("TOPLEFT", box, "BOTTOMLEFT", 0, -2)
    drop:SetBackdrop({ bgFile = "Interface\\Buttons\\WHITE8x8", edgeFile = "Interface\\Buttons\\WHITE8x8",
                       edgeSize = (UI.Edge and UI:Edge(drop)) or 1 })
    drop:SetBackdropColor(C().panel.r, C().panel.g, C().panel.b, 0.98)
    drop:SetBackdropBorderColor(C().lineHi.r, C().lineHi.g, C().lineHi.b, 1)
    drop:Hide()
    S.drop = drop

    box:HookScript("OnTextChanged", function(self) S.Render(self:GetText()) end)
    box:HookScript("OnEditFocusGained", function(self) S.Render(self:GetText()) end)
    box:SetScript("OnEnterPressed", function() pick(flat[marked]) end)
    box:HookScript("OnEscapePressed", hide)
    box:HookScript("OnEditFocusLost", function()
        -- a click on a row takes the focus first: give the click time to land
        if AmazingHub.Compat.After then AmazingHub.Compat.After(0.2, function()
            if box and not box:HasFocus() then hide() end
        end) end
    end)
    -- Up and Down: an EditBox script not proven on Forever yet, so only where the client takes it.
    pcall(box.SetScript, box, "OnArrowPressed", function(_, key)
        if key == "UP" then move(-1) elseif key == "DOWN" then move(1) end
    end)
    f:HookScript("OnHide", hide)
    if f.LayoutTitle then AmazingHub:SafeCall(f.LayoutTitle, f) end
    return true
end

-- `/amazing search text` puts the text in the box when the window has it.
function S.Fill(text)
    if not box then return false end
    box:SetText(text or "")
    box:SetFocus()
    return true
end

local getMain = UI.GetMainWindow
if getMain then
    function UI:GetMainWindow(...)
        local f = getMain(self, ...)
        if f and not f.__packSearch then AmazingHub:SafeCall(S.Attach, f) end
        return f
    end
end

local Search = AmazingHub.Search
if Search and Search.Show then
    local show = Search.Show
    function Search:Show(initial, ...)
        local f = UI:GetMainWindow()
        if f and box and initial and initial ~= "" then
            f:Show()
            return S.Fill(initial)
        end
        return show(self, initial, ...)
    end
end
