-- Wires AmazingHub into the shared AmzHubNet presence mesh (see AmzHubNet.lua).
-- AmazingHub works fully standalone; this only adds cross-addon recognition.
-- Kept thin on purpose: the AmazingHub-side logic (what to advertise, what to do
-- with peers) lives in AmazingHub.Mesh (Modules/Mesh.lua). Both callbacks read the
-- facade lazily, so they are safe even though Mesh.lua loads after this file.
local CN = _G.AmzHubNet
if not CN then
    return
end

-- Show network alerts in Amazing Hub's identity (gold). Forever-dismissed ids persist in our
-- SavedVariables (AmazingHubDB.alertDismissed), resolved at call time (after SV load).
if CN.EnableAlerts then
    CN:EnableAlerts({
        accent = { 1.0, 0.843, 0.0 },
        title = "Amazing Hub",
        priority = 2,
        store = function()
            AmazingHubDB = AmazingHubDB or {}
            AmazingHubDB.alertDismissed = AmazingHubDB.alertDismissed or {}
            return AmazingHubDB.alertDismissed
        end,
    })
end

-- LibAmzHubMesh v7: the Maupa clients the mesh heard outlive a /reload and start the next login's peer exchange
-- (AmazingHubDB.meshPeers, name -> time()).
local Mesh = _G.AmzHubMesh
if Mesh and Mesh.PeerStore then
    Mesh:PeerStore(function()
        AmazingHubDB = AmazingHubDB or {}
        AmazingHubDB.meshPeers = AmazingHubDB.meshPeers or {}
        return AmazingHubDB.meshPeers
    end)
end

CN:Register("gos",
    -- caps: advertise our version (tiny + non-sensitive; it rides a public post).
    function()
        return (AmazingHub and AmazingHub.Mesh and AmazingHub.Mesh:BuildCaps()) or ""
    end,
    -- onPeer: hand cross-addon presence to the AmazingHub facade for the UI.
    function(short, peer)
        if AmazingHub and AmazingHub.Mesh then
            AmazingHub.Mesh:OnPeer(short, peer)
        end
    end)

-- What the backoffice's DIAG (AmzHubNet v11, issue #276) is told about Amazing Hub: the gossip, and the whisper
-- spelling its self-test kept (false: no echo came back), plus the last channel probe's verdict.
if CN.RegisterDiag then
    CN:RegisterDiag("gos", function()
        local parts = { "v=" .. tostring(AmazingHub and AmazingHub.VERSION or "?") }
        local gossip = AmazingHub and AmazingHub.AmzHubGossip
        if gossip and gossip.Stats then
            local s = gossip:Stats()
            parts[#parts + 1] = string.format("wsp=%s;rounds=%d;adsIn=%d;adsOut=%d;drop=%d;gpeers=%d",
                tostring(s.whisper), s.rounds or 0, s.adsIn or 0, s.adsOut or 0, s.dropped or 0, s.peers or 0)
        end
        local ch = type(AmazingHubDB) == "table" and AmazingHubDB.probeChannel
        if type(ch) == "table" then
            parts[#parts + 1] = "chTimer=" .. tostring(ch.timer) .. ";chClick=" .. tostring(ch.click)
        end
        return table.concat(parts, ";")
    end)
end
