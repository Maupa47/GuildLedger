----------------------------------------------------------------------
-- Amazing Hub - how many of each material the guild bank holds (Amazing Forever Guild Pack 0.7.0; our own file)
--
-- H9 (PLAN_COMMUNITY W19). The opened recipe (UI/CraftOrdersPanel.lua CreateCraftDetail) already multiplies its
-- materials by the order's quantity ("MATERIALS × N", the - and + buttons) and shows "have / need" from the
-- player's bags. Here each material's name gets "· bank N" after it, from the last picture of the guild bank
-- (GuildBank:CountOf; the Bank tab fills whenever a member with the hub opens the bank). Nothing when the hub
-- has never seen the bank, or the bank holds none.
--
-- Copied in by tools/rebrand-hub.py from addon/hub-extra/; edit it there.
----------------------------------------------------------------------
local M = {}
AmazingHub.PackMaterials = M

-- The bank's count of `itemID`, or nil when there is no picture of the bank or none in it.
function M.BankCount(itemID)
    local B = AmazingHub.GuildBank
    if not (B and B.CountOf and B.Newest) then return nil end
    local ok, ts = pcall(B.Newest, B)
    if not ok or not ts or ts <= 0 then return nil end
    local ok2, n = pcall(B.CountOf, B, itemID)
    if ok2 and type(n) == "number" and n > 0 then return n end
    return nil
end

function M.Suffix(itemID)
    local n = M.BankCount(itemID)
    return n and ("  |cff8c8c8c\194\183 bank " .. n .. "|r") or ""
end

----------------------------------------------------------------------
-- Under the crafters (round H-b, 2026-11-26): "Recipe: [the recipe]" and "Learned from: [the plans, pattern,
-- formula ... that teaches it]", each linked into chat by Shift + click and shown as a tooltip on hover.
-- The recipe's link: Compat.SpellLink (a recipe is a spell); what teaches it: the catalogue's recipe item
-- (ProfDirectory row `recipeItem`, handed over by the Crafts panel, tools/rebrand-hub.py).
----------------------------------------------------------------------
local LINE_Y = { -110, -128 }   -- under the crafters column's "+N more" line (CraftOrdersPanel: WHO_LINES = 3)

local function linkLine(d)
    local b = CreateFrame("Button", nil, d)
    b:SetHeight(16)
    b.text = AmazingHub.UI:CreateText(b, "", 11)
    b.text:SetPoint("LEFT", 0, 0)
    b.text:SetPoint("RIGHT", 0, 0)
    b.text:SetJustifyH("LEFT")
    b.text:SetWordWrap(false)
    b:SetScript("OnClick", function(self)
        if self.link and IsShiftKeyDown and IsShiftKeyDown() and HandleModifiedItemClick then
            HandleModifiedItemClick(self.link)
        end
    end)
    b:SetScript("OnEnter", function(self)
        if self.link and GameTooltip then
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:SetHyperlink(self.link)
            GameTooltip:Show()
        end
    end)
    b:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    return b
end

-- The two lines' texts and links for recipe `r`: { { label, link } ... }, only those that are known.
function M.RecipeLines(r)
    local out = {}
    local Links = AmazingHub.PackLinks
    local spell = r and (r.recipeId or r.id)
    local recipe = type(spell) == "number" and Links and Links.RecipeLink(spell) or nil
    if recipe then out[#out + 1] = { label = "Recipe: ", link = recipe } end
    local teach = r and r.recipeItem
    if type(teach) == "number" and teach > 0 then
        local _, link = AmazingHub.Compat.GetItemInfo(teach)
        -- not cached yet: the catalogue's name, and the asking above loads it for the next paint
        local W = AmazingHub.Wishlist
        local name = W and W.catalog and W.catalog[teach] and W.catalog[teach].name
        out[#out + 1] = { label = "Learned from: ", link = link, text = link or name or ("item " .. teach) }
    end
    return out
end

function M.PaintLines(d)
    d.packLines = d.packLines or { linkLine(d), linkLine(d) }
    local lines = M.RecipeLines(d.recipe)
    local w = d:GetWidth() or 600
    local colW
    if d.IsStacked and d:IsStacked() then colW = math.max(60, math.floor((w - 34 - 8 - 18) / 2))
    else colW = math.max(120, math.floor((w - 34 - 248 - 16 - 18) / 2)) end
    local x2 = 34 + colW + 18
    for i, b in ipairs(d.packLines) do
        local e = lines[i]
        b:SetShown(e ~= nil)
        if e then
            b:ClearAllPoints()
            b:SetPoint("TOPLEFT", d, "TOPLEFT", x2, LINE_Y[i])
            b:SetWidth(colW)
            b.link = e.link
            b.text:SetText("|cff8c8c8c" .. e.label .. "|r" .. (e.text or e.link))
        end
    end
end

-- After the detail paints: the recipe lines, and the bank's count after each material's name.
function M.Decorate(d)
    pcall(M.PaintLines, d)
    local r, O = d.recipe, AmazingHub.CraftOrders
    if not (r and r.item and O and O.Reagents and d.mats) then return end
    local ok, rg = pcall(O.Reagents, O, r.item, nil, r.recipeId)
    if not ok or type(rg) ~= "table" then return end
    for i, m in ipairs(d.mats) do
        local x = rg[i]
        if x and m.name and m.name.GetText then
            local s = M.Suffix(x.itemID)
            if s ~= "" then m.name:SetText((m.name:GetText() or "") .. s) end
        end
    end
end

local create = AmazingHub.CreateCraftDetail
if create then
    function AmazingHub:CreateCraftDetail(...)
        local d = create(self, ...)
        if type(d) == "table" and d.Paint then
            local paint = d.Paint
            function d:Paint(...)
                local out = paint(self, ...)
                local ok, err = pcall(M.Decorate, self)
                if not ok and AmazingHub.RecordError then AmazingHub:RecordError("Materials: " .. tostring(err)) end
                return out
            end
        end
        return d
    end
end
