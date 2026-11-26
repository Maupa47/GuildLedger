----------------------------------------------------------------------
-- Amazing Hub - join dates from GuildLedger (Amazing Forever Guild Pack 0.8.0; our own file, not upstream)
--
-- H10 (PLAN_COMMUNITY W21). The hub's member history (Modules/MemberHistory.lua, officers only) knows when a
-- member joined only when an officer's hub saw it. GuildLedger knows more (GuildLedgerAPI.GetJoined, G4): its
-- join events and the first guild chat line of the current stay. Where that is earlier than what the history
-- has for the current stay, the history's reader (MemberHistory:JoinedAt: the Joined column, the officer sheet)
-- shows it, marked estimated ("~"). Read-only: nothing is written into the history, so nothing of this is sent
-- to other officers. Never replaced: an exact date (the game's own line) and a day read from the member's note.
-- Never before the end of the member's previous stay. Visibility is the history's: officers only (decision 6).
--
-- Copied in by tools/rebrand-hub.py from addon/hub-extra/; edit it there.
----------------------------------------------------------------------
local J = {}
AmazingHub.PackJoined = J

-- GuildLedger's earliest known start of the member's current stay, or nil.
function J.FromLedger(key)
    local api = GuildLedgerAPI
    if type(api) ~= "table" or type(api.GetJoined) ~= "function" or type(key) ~= "string" then return nil end
    -- A member key is "Name" or "Name-Realm"; Forever names never hold a hyphen (Core/Utils.lua LocalMemberKey).
    local name = key:match("^([^-]+)") or key
    local ok, j = pcall(api.GetJoined, name)
    if ok and type(j) == "table" and type(j.t) == "number" and j.t > 0 then return j.t end
    return nil
end

local MH = AmazingHub.MemberHistory
if MH and MH.JoinedAt and MH.Stints then
    local joinedAt = MH.JoinedAt
    function MH:JoinedAt(key, ...)
        local t, est = joinedAt(self, key, ...)
        if t and not est then return t, est end                       -- the game's own line
        local s = self:Stints(key)
        local last, prev = s[#s], s[#s - 1]
        if last and (last.leftAt ~= nil or last.joinSrc == "note") then return t, est end
        local g = J.FromLedger(key)
        if not g or (t and g >= t) then return t, est end
        if prev and prev.leftAt and g < prev.leftAt then return t, est end
        -- No passage known at all: GuildLedger's date stands only for a member the game's roster lists now.
        if not last and not (AmazingHub.IsGuildmate and AmazingHub:IsGuildmate(key)) then return t, est end
        return g, true
    end
end
