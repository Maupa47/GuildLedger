-- Link (docs/dev/PACK_PLAN.md section 10): tie characters to a Discord user. Addons have no network, so a link
-- request travels: member's addon -> guild addon channel -> any online collector -> SavedVariables ->
-- companion -> #gl-ingest -> bot, which asks the Discord user to confirm. Only that confirmation links.
--   L code tag   member: "/gl link CODE" was typed (re-sent every 3 min until acknowledged, 30 min at most)
--   Y code       collector: "recorded" (acknowledged means recorded, not linked)
--   A tag        member: once per session on any character of an account that requested a link (alts)
-- tag: a random identifier generated once per account (not a secret; it groups an account's characters).

local _, ns = ...
local C, S = ns.Compat, ns.Store
local Comms = ns.Comms
local M = ns.Module("Link")
ns.Link = M

local SEP = Comms.SEP
local CODE_TTL = 1800
local RESEND_EVERY = 180
local ALT_DELAY = 45 -- s after login
local ACK_GAP = 60 -- s: a collector acknowledges the same code at most this often
local ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789" -- no I, O, 0, 1 (the bot uses the same)
local CODE_PATTERN = "^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]+$"

local lastSent = -1e9
local altSent = false
local ackedAt = {} -- collector: [code] = GetTime()
local stats = { passedOn = 0, alts = 0 }

local function club()
    if ns.Chat and ns.Chat.Club then return ns.Chat.Club() end
end

local function newTag()
    local t = {}
    for i = 1, 10 do
        local k = math.random(1, #ALPHABET)
        t[i] = ALPHABET:sub(k, k)
    end
    return table.concat(t)
end

local function state()
    local st = S.LinkState()
    if not st.tag then st.tag = newTag() end
    return st
end
M.State = state

local function validCode(code)
    return type(code) == "string" and #code == 8 and code:match(CODE_PATTERN) ~= nil
end

local function guidOf(sender)
    local cid = club()
    if not cid then return nil end
    for guid, m in pairs(S.Guild(cid).roster or {}) do
        if m.n and (sender == m.n or sender:sub(1, #m.n + 1) == m.n .. "-") then return guid end
    end
end

---------------------------------------------------------------------------------------------------
-- Member side
---------------------------------------------------------------------------------------------------

local function sendPending()
    local st = state()
    local p = st.pending
    if not p or p.acked or C.Now() - p.at > CODE_TTL then return end
    if C.Clock() - lastSent < RESEND_EVERY then return end
    lastSent = C.Clock()
    Comms.Send(table.concat({ "L", p.code, st.tag }, SEP), Comms.HIGH)
end

-- Takes a code from Discord's /link; returns ok, message (printed by /gl link, shown by the hub's Ledger tab).
function M.Submit(code)
    code = type(code) == "string" and code:gsub("%s", ""):upper() or ""
    if not validCode(code) then
        return false, "that is not a link code. In Discord, use /link: it shows an 8-character code; then type"
            .. " /gl link CODE here."
    end
    if not C.HasComm then
        return false, "linking is not available in this game version"
    end
    local st = state()
    st.pending = { code = code, at = C.Now() }
    lastSent = -1e9
    sendPending()
    return true, "link code sent to the officers' collectors. When one is online, Discord asks you to confirm"
        .. " (check your Discord messages). It is re-sent automatically for 30 minutes."
end

function M.Request(code)
    local _, msg = M.Submit(code)
    ns.Print(msg)
end

Comms.Handle("Y", function(_, text, me)
    if me then return end
    local code = text:match("^Y\t(%S+)$")
    local p = state().pending
    if not p or code ~= p.code or p.acked then return end
    p.acked = true
    state().requested = true
    ns.Notice("a collector received your link code. Confirm it in Discord to finish linking.")
end)

---------------------------------------------------------------------------------------------------
-- Collector side
---------------------------------------------------------------------------------------------------

Comms.Handle("L", function(sender, text, me)
    if me or not S.IsCollector() then return end
    local cid = club()
    local code, tag = text:match("^L\t(%S+)\t(%S+)$")
    if not cid or not validCode(code) or not tag or #tag > 20 then return end
    local now = C.Now()
    if S.AddLink(cid, { id = "link|" .. code .. "|" .. sender, t = now, k = "link", code = code, tag = tag,
        n = sender, g = guidOf(sender) }) then
        stats.passedOn = stats.passedOn + 1
    end
    if C.Clock() - (ackedAt[code] or -1e9) >= ACK_GAP then
        ackedAt[code] = C.Clock()
        Comms.Send("Y" .. SEP .. code, Comms.HIGH)
    end
end)

Comms.Handle("A", function(sender, text, me)
    if me or not S.IsCollector() then return end
    local cid = club()
    local tag = text:match("^A\t(%S+)$")
    if not cid or not tag or #tag > 20 then return end
    local now = C.Now()
    if S.AddLink(cid, { id = "alt|" .. tag .. "|" .. sender .. "|" .. math.floor(now / 86400), t = now, k = "alt",
        tag = tag, n = sender, g = guidOf(sender) }) then
        stats.alts = stats.alts + 1
    end
end)

---------------------------------------------------------------------------------------------------
-- Startup, status
---------------------------------------------------------------------------------------------------

function M.OnInit()
    if not C.HasComm then return end
    state()
    C.Ticker(10, function() ns.Safe("Link.resend", sendPending) end)
    C.After(ALT_DELAY, function()
        ns.Safe("Link.alt", function()
            local st = state()
            if st.requested and not altSent and club() then
                altSent = true
                Comms.Send("A" .. SEP .. st.tag, Comms.HIGH)
            end
        end)
    end)
end

-- Plain copy of the link state (GuildLedgerAPI): no table of ours leaves.
function M.Info()
    local st = state()
    local p = st.pending
    local info = { requested = st.requested and true or false }
    if p then
        info.code, info.sentAt, info.acked = p.code, p.at, p.acked and true or false
        info.expired = (not p.acked) and C.Now() - p.at > CODE_TTL
    end
    return info
end

function M.Status()
    ns.Head("Discord link")
    if not C.HasComm then
        ns.Line("Not available in this game version.")
        return
    end
    local st = state()
    local p = st.pending
    if p and not p.acked and C.Now() - p.at <= CODE_TTL then
        ns.Line("Your code " .. p.code .. " was sent at " .. date("%H:%M", p.at) .. "; waiting for a collector to"
            .. " be online (re-sent every 3 minutes).")
    elseif p and p.acked then
        ns.Line("Your code " .. p.code .. " reached a collector. Confirm it in Discord if you have not yet.")
    elseif p then
        ns.Line("Your code " .. p.code .. " expired without reaching a collector. Get a new one with /link in"
            .. " Discord.")
    else
        ns.Line("Not requested. In Discord use /link, then type /gl link CODE here.")
    end
    if st.requested then
        ns.Line("Your other characters are offered to your Discord account automatically when you log in.")
    end
    if S.IsCollector() then
        ns.Line(string.format("Link requests passed on since login: %d (alts: %d).", stats.passedOn, stats.alts))
    end
end
