----------------------------------------------------------------------
-- Amazing Hub - wishlist import from Discord (Amazing Forever Guild Pack 0.5.4; our own file, not upstream)
-- The GuildLedger bot's `/wish export` gives one line (shared/schema.md section 7):
--   GLW1:<character>:<itemID>[o],<itemID>[o],...      o = off spec, oldest first
-- The wishlist window gets an "Import from Discord" button in its title bar (tools/rebrand-hub.py); the line is
-- pasted into a box.
-- Each item not yet on the player's own list is added the way the window's "+ Add" does (Wishlist:AddToWishlist,
-- which also sends the list to the guild). Items the client has not cached yet are asked again a few times.
-- A line for another character is refused.
--
-- Copied in by tools/rebrand-hub.py from tools/hub-extra/; edit it there.
----------------------------------------------------------------------
local UI = AmazingHub.UI
local C = AmazingHub.Colors

local W = {}
AmazingHub.WishImport = W

local RETRIES, RETRY_GAP = 5, 1.5 -- s: uncached items are tried again this often

local function same(a, b)
    local function norm(s) return (s:lower():gsub("%-", " ")) end
    return type(a) == "string" and type(b) == "string" and norm(a) == norm(b)
end

-- ok, character, items ({ { id, offspec }, ... }) | nil, reason
function W.Parse(text)
    if type(text) ~= "string" then return nil, "nothing pasted" end
    text = text:gsub("^%s+", ""):gsub("%s+$", "")
    if text:sub(1, 5) ~= "GLW1:" then return nil, "this is not a line from the bot's /wish export" end
    local rest = text:sub(6)
    local cut = rest:match("^.*():") -- the last colon: names may hold spaces, never a colon
    if not cut then return nil, "the line is cut off" end
    local who, list = rest:sub(1, cut - 1), rest:sub(cut + 1)
    if who == "" then return nil, "the line names no character" end
    local items, seen = {}, {}
    for part in list:gmatch("[^,]+") do
        local id, os = part:match("^%s*(%d+)(o?)%s*$")
        id = tonumber(id)
        if not id or id < 1 then return nil, "the item list is damaged (" .. part .. ")" end
        if not seen[id] then
            seen[id] = true
            items[#items + 1] = { id = id, offspec = os == "o" }
        end
    end
    if #items == 0 then return nil, "the line has no items" end
    return true, who, items
end

-- Add what is missing to my own list. Returns added, already (counts so far; uncached items follow later).
function W.Apply(items, done)
    local WL = AmazingHub.Wishlist
    if not WL then return 0, 0 end
    local have = {}
    for _, e in ipairs(WL:GetMyList()) do have[e.itemId] = true end
    local added, already, waiting = 0, 0, {}
    for _, it in ipairs(items) do
        if have[it.id] then
            already = already + 1
        elseif WL:ItemFacts(it.id) then
            local _, link = WL:ItemFacts(it.id)
            WL:AddToWishlist(it.id, link, it.offspec)
            added = added + 1
        else
            waiting[#waiting + 1] = it
        end
    end
    if #waiting > 0 and (done or 0) < RETRIES and C_Timer and C_Timer.After then
        C_Timer.After(RETRY_GAP, function() W.Apply(waiting, (done or 0) + 1) end)
    elseif #waiting > 0 then
        AmazingHub:Print(string.format("[Wishlist] %d item(s) unknown to the game client; try the import again later.",
            #waiting))
    end
    return added, already
end

-- The whole import: check, add, say what happened. Returns ok, message.
function W.Import(text)
    local ok, who, items = W.Parse(text)
    if not ok then return false, who end
    local me = AmazingHub.Compat.PlayerName and AmazingHub.Compat.PlayerName()
    if not same(who, me) then
        return false, "this list is for " .. who .. "; log in with that character to import it"
    end
    local added, already = W.Apply(items)
    return true, string.format("[Wishlist] Imported from Discord: %d new, %d already on your list%s.", added, already,
        added + already < #items and ", the rest follows when the game knows the items" or "")
end

function W.ShowPopup()
    if W.popup then W.popup:Hide() end
    local f = CreateFrame("Frame", "AmazingHubWishImportPopup", UIParent, "BackdropTemplate")
    f:SetSize(460, 220)
    f:SetPoint("CENTER")
    if f.SetBackdrop then
        f:SetBackdrop({ bgFile = "Interface\\Buttons\\WHITE8x8", edgeFile = "Interface\\Buttons\\WHITE8x8", edgeSize = 1 })
        f:SetBackdropColor(0.058, 0.058, 0.075, 0.98)
        f:SetBackdropBorderColor(C.border.r, C.border.g, C.border.b, C.border.a)
    end
    if UI.StylePopup then UI:StylePopup(f) end
    f:SetFrameStrata("DIALOG")
    f:EnableMouse(true)

    local title = UI:CreateText(f, "Import wishlist from Discord", 13, C.gold.r, C.gold.g, C.gold.b)
    title:SetPoint("TOP", 0, -10)
    local hint = UI:CreateText(f, "In Discord type /wish export, copy the line that starts with GLW1: and paste it"
        .. " here (Ctrl+V).", 10, C.silver.r, C.silver.g, C.silver.b)
    hint:SetPoint("TOPLEFT", 14, -32)
    hint:SetWidth(432)
    hint:SetJustifyH("LEFT")

    local box = CreateFrame("EditBox", nil, f, "InputBoxTemplate")
    box:SetSize(420, 24)
    box:SetPoint("TOPLEFT", 20, -80)
    box:SetAutoFocus(true)
    box:SetMaxLetters(2000)
    box:SetScript("OnEscapePressed", function() f:Hide() end)

    local result = UI:CreateText(f, "", 10, C.text.r, C.text.g, C.text.b)
    result:SetPoint("TOPLEFT", 14, -116)
    result:SetWidth(432)
    result:SetJustifyH("LEFT")

    local go = UI:CreateButton(f, "Import", 100, 26)
    go:SetPoint("BOTTOMRIGHT", -12, 10)
    local function run()
        local ok, msg = W.Import(box:GetText())
        if ok then
            result:SetTextColor(C.green.r, C.green.g, C.green.b)
            box:SetText("")
            if AmazingHub.WishlistFrame and AmazingHub.WishlistFrame:IsShown() and AmazingHub.RefreshWishlistFrame then
                AmazingHub:RefreshWishlistFrame()
            end
        else
            result:SetTextColor(C.red.r, C.red.g, C.red.b)
        end
        result:SetText(msg)
    end
    go:SetScript("OnClick", run)
    box:SetScript("OnEnterPressed", run)
    local close = UI:CreateButton(f, "Close", 80, 26)
    close:SetPoint("RIGHT", go, "LEFT", -6, 0)
    close:SetScript("OnClick", function() f:Hide() end)

    f:Show()
    W.popup = f
    return f
end
