-- Amazing Hub's Ledger tab (tools/hub-extra/LedgerPanel.lua, as built into addon/AmazingHub/UI) with fake frames
-- and a fake GuildLedgerAPI. Run by addon/tests/test_hub.py with ADDON = the AmazingHub folder. Raises on failure.
ADDON = ADDON or "."

local function check(cond, what)
  if not cond then error("FAIL: " .. what, 0) end
end

-- ── Fake widgets ────────────────────────────────────────────────────────
local NOOP = { __index = function() return function() end end } -- any other widget method: does nothing
local function frame()
  local f = setmetatable({ shown = true, scripts = {}, hooks = {}, text = "" }, NOOP)
  function f:GetText() return self.text end
  function f:SetText(t) self.text = t end
  function f:CreateFontString() return frame() end
  function f:SetPoint() end
  function f:ClearAllPoints() end
  function f:SetWidth() end
  function f:SetHeight() end
  function f:GetWidth() return 500 end
  function f:Show() self.shown = true end
  function f:Hide() self.shown = false end
  function f:IsShown() return self.shown end
  function f:SetScript(k, fn) self.scripts[k] = fn end
  function f:HookScript(k, fn) self.hooks[k] = fn end
  return f
end
local texts = {}
local UI = {}
function UI:CreateScrollFrame() return frame(), frame() end
function UI:CreateText()
  local fs = frame()
  function fs:SetJustifyH() end
  function fs:SetTextColor() end
  function fs:SetText(t) self.text = t end
  function fs:GetStringHeight() return 12 end
  texts[#texts + 1] = fs
  return fs
end
function UI:CreateCheckbox(_, label)
  local f = frame()
  f.label = label
  f.checkbox = { checked = false, enabled = true }
  function f.checkbox:SetChecked(v) self.checked = v end
  function f.checkbox:Enable() self.enabled = true end
  function f.checkbox:Disable() self.enabled = false end
  return f
end
function UI:CreateButton(_, text) local b = frame(); b.text = text; return b end
local features = {}
function UI:RegisterFeature(def) features[def.id] = def end

local mapOpened = 0
AmazingHub = {
  UI = UI,
  Colors = setmetatable({}, { __index = function() return { r = 1, g = 1, b = 1 } end }),
  Compat = { OpenWorldMap = function() mapOpened = mapOpened + 1 return true end },
}
function AmazingHub:ApplyFont() end
function AmazingHub:SafeCall(fn, ...) return fn(...) end
function AmazingHub:ToggleGuildMap() error("the hub's own guild map must be replaced") end
C_Timer = { NewTicker = function() return { Cancel = function() end } end }
local boxesMade = {}
function CreateFrame(kind) local f = frame(); f.kind = kind; boxesMade[#boxesMade + 1] = f; return f end

-- PackTweaks: the hidden tabs
local hiddenDefs = { achievements = {}, alliance = {}, recruitment = {}, web = {}, journal = {} }
function UI:GetFeature(id) return hiddenDefs[id] end
dofile(ADDON .. "/UI/PackTweaks.lua")
for _, id in ipairs({ "achievements", "alliance", "recruitment", "web" }) do
  check(hiddenDefs[id].condition and hiddenDefs[id].condition() == false, id .. " tab is hidden")
end
check(hiddenDefs.journal.condition == nil, "the journal tab stays")

dofile(ADDON .. "/UI/LedgerPanel.lua")

local function visible()
  local out = {}
  for _, fs in ipairs(texts) do if fs.shown then out[#out + 1] = fs.text end end
  return table.concat(out, "\n")
end

check(features.ledger and features.ledger.label == "Ledger", "the Ledger tab is registered")

-- ── Without GuildLedger ─────────────────────────────────────────────────
GuildLedgerAPI = nil
local parent = frame()
local refresh = features.ledger.build(parent, {})
check(visible():find("GuildLedger is not running", 1, true), "without GuildLedger the tab says so")

-- ── With GuildLedger ────────────────────────────────────────────────────
local set = {}
GuildLedgerAPI = {
  apiVersion = 1,
  Version = function() return "0.5.0" end,
  NewerVersion = function() return "0.6.0", "New Comer" end,
  GetMap = function() return { available = true, share = true, pins = false } end,
  SetMapShare = function(on) set.share = on end,
  SetMapPins = function(on) set.pins = on end,
  GetStatus = function()
    return { lines = {
      { kind = "print", text = "status, version 0.5.0" },
      { kind = "line", text = "Role: Member - keeps recent guild chat" },
      { kind = "head", text = "World map" },
      { kind = "line", text = "Your position: shared" },
    } }
  end,
}
texts = {}
parent = frame()
refresh = features.ledger.build(parent, {})
local v = visible()
check(v:find("GUILDLEDGER 0.5.0", 1, true), "version shown")
check(v:find("Update available: version 0.6.0", 1, true), "a newer version seen in the guild is shown")
check(v:find("Role: Member", 1, true) and v:find("World map", 1, true) and v:find("Your position: shared", 1, true),
  "the /gl status lines are shown")
check(not v:find("not running", 1, true), "and no 'not running'")

-- the switches mirror the settings and write through the API
-- (find the checkboxes through their onChanged handlers: the panel keeps them in upvalues)
local boxes = {}
local i = 1
while true do
  local name, val = debug.getupvalue(refresh, i)
  if not name then break end
  if type(val) == "table" and val.checkbox then boxes[val.label] = val end
  i = i + 1
end
local share = boxes["Show my position to guild members on the world map"]
local pins = boxes["Show guild members on my world map"]
check(share and pins, "both map switches exist")
check(share.checkbox.checked == true and pins.checkbox.checked == false, "the switches show GuildLedger's settings")
share.checkbox.onChanged(nil, false)
pins.checkbox.onChanged(nil, true)
check(set.share == false and set.pins == true, "the switches write through GuildLedgerAPI")

-- the Discord link box sends the code through the API and shows the answer
local linked
GuildLedgerAPI.GetLink = function() return { requested = false } end
GuildLedgerAPI.RequestLink = function(code)
  linked = code
  if code == "ABCD2345" then return true, "link code sent" end
  return false, "that is not a link code"
end
local codeBox
for _, f in ipairs(boxesMade) do if f.kind == "EditBox" then codeBox = f end end
check(codeBox and codeBox.scripts.OnEnterPressed, "a code box that sends on Enter")
codeBox:SetText("nope")
codeBox.scripts.OnEnterPressed(codeBox)
check(linked == "nope" and visible():find("that is not a link code", 1, true) and codeBox:GetText() == "nope",
  "a wrong code is refused, the answer is shown and the box keeps the text")
codeBox:SetText("ABCD2345")
codeBox.scripts.OnEnterPressed(codeBox)
check(linked == "ABCD2345" and visible():find("link code sent", 1, true) and codeBox:GetText() == "",
  "a good code goes, the answer is shown and the box is emptied")
GuildLedgerAPI.GetLink = function() return { requested = true, code = "ABCD2345", acked = true } end
refresh()
check(visible():find("reached a collector", 1, true), "the link state is shown")

-- /amazing map (ToggleGuildMap) opens the world map, where GuildLedger draws the guild
AmazingHub:ToggleGuildMap()
check(mapOpened == 1, "/amazing map opens the world map")

-- an API that raises does not break the tab
GuildLedgerAPI.GetStatus = function() error("boom") end
check(pcall(refresh), "a failing GuildLedgerAPI call does not raise in the tab")

-- another API version is treated as missing
GuildLedgerAPI.apiVersion = 2
refresh()
check(visible():find("GuildLedger is not running", 1, true), "an unknown API version is treated as missing")
return "ok"
