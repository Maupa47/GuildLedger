-- Amazing Hub Settings additions (tools/hub-extra/SettingsPlus.lua, as built into addon/AmazingHub/UI): fold-out
-- sections and the World map section, with fake frames that keep their anchor points, a fake upstream Settings
-- page and a fake GuildLedgerAPI. Run by addon/tests/test_hub.py with ADDON = the AmazingHub folder.
ADDON = ADDON or "."

local function check(cond, what)
  if not cond then error("FAIL: " .. what, 0) end
end

-- ── Fake widgets that remember their anchors ──────────────────────────────
local NOOP = { __index = function() return function() end end }
local made = {}
local function obj(parent, kind)
  local o = setmetatable({ parent = parent, kind = kind, shown = true, points = {}, scripts = {}, kids = {},
    regions = {}, text = "", h = 0 }, NOOP)
  function o:GetParent() return self.parent end
  function o:SetPoint(point, a, b, c, d)
    local rel, relPoint, x, y
    if type(a) == "number" then rel, relPoint, x, y = self.parent, point, a, b
    elseif type(b) == "string" then rel, relPoint, x, y = a, b, c or 0, d or 0
    elseif type(b) == "number" then rel, relPoint, x, y = a, point, b, c
    else rel, relPoint, x, y = a or self.parent, point, 0, 0 end
    self.points[#self.points + 1] = { point, rel, relPoint, x, y }
  end
  function o:GetPoint(i) local p = self.points[i or 1]; if p then return p[1], p[2], p[3], p[4], p[5] end end
  function o:GetNumPoints() return #self.points end
  function o:ClearAllPoints() self.points = {} end
  function o:Show() self.shown = true end
  function o:Hide() self.shown = false end
  function o:IsShown() return self.shown end
  function o:SetText(t) self.text = t end
  function o:GetText() return self.text end
  function o:SetScript(k, fn) self.scripts[k] = fn end
  function o:GetWidth() return 600 end
  function o:SetHeight(h) self.h = h end
  function o:GetHeight() return self.h end
  function o:GetChildren() return unpack(self.kids) end
  function o:GetRegions() return unpack(self.regions) end
  function o:CreateTexture() local t = obj(self, "Texture"); self.regions[#self.regions + 1] = t; return t end
  function o:CreateFontString() local t = obj(self, "FontString"); self.regions[#self.regions + 1] = t; return t end
  function o:GetName() return self.name end
  made[#made + 1] = o
  return o
end
local function child(parent, kind)
  local c = obj(parent, kind)
  if parent then parent.kids[#parent.kids + 1] = c end
  return c
end
local function region(parent)
  local r = obj(parent, "FontString")
  parent.regions[#parent.regions + 1] = r
  return r
end

function CreateFrame(kind, name, parent)
  local f = child(parent, kind)
  f.name = name
  if name then _G[name] = f end
  return f
end

local UI = {}
function UI:CreateHeaderText(parent, text) local fs = region(parent); fs.text = text; fs.header = true; return fs end
function UI:CreateText(parent, text) local fs = region(parent); fs.text = text; return fs end
function UI:CreateCheckbox(parent, label)
  local f = child(parent, "Frame")
  f.label, f.text = label, label
  f.checkbox = { checked = false }
  function f.checkbox:SetChecked(v) self.checked = v end
  return f
end
function UI:CreateButton(parent, text) local b = child(parent, "Button"); b.text = text; b.label = obj(b); return b end

local settings = {}
AmazingHub = {
  UI = UI,
  Colors = setmetatable({}, { __index = function() return { r = 1, g = 1, b = 1 } end }),
}
function AmazingHub:GetSetting(k) return settings[k] end
function AmazingHub:SetSetting(k, v) settings[k] = v end
local mapOpened = 0
function AmazingHub:ToggleGuildMap() mapOpened = mapOpened + 1 end

-- ── A fake upstream Settings page: three sections, 100 px apart ────────────
local scroll = obj(nil, "ScrollFrame")
local content = child(scroll, "Frame")
local builds = 0
function AmazingHub:RefreshSettingsPanel(c, category)
  for _, k in ipairs({ c:GetChildren() }) do k:Hide() end
  for _, r in ipairs({ c:GetRegions() }) do r:Hide() end
  builds = builds + 1
  c.__settingsCat = category or rawget(c, "__settingsCat") or "general"
  local title = UI:CreateText(c, "Settings")
  title:SetPoint("TOPLEFT", 0, 0)
  local y = 40
  for _, name in ipairs({ "MY PROFILE", "MODULES", "CHAT" }) do
    local h = UI:CreateHeaderText(c, name, 12)
    h:SetPoint("TOPLEFT", 0, -y)
    local box = UI:CreateCheckbox(c, name .. " option")
    box:SetPoint("TOPLEFT", 0, -(y + 24))
    local hint = UI:CreateText(c, name .. " hint")
    hint:SetPoint("LEFT", box, "RIGHT", 8, 0) -- anchored to a sibling
    y = y + 100
  end
  c:SetHeight(y)
end

dofile(ADDON .. "/UI/SettingsPlus.lua")

local function find(text, onlyShown)
  for _, o in ipairs(made) do
    if o.text == text and (o.shown or not onlyShown) and o.parent == content then return o end
  end
end
local function current(text)
  local hit
  for _, o in ipairs(made) do if o.text == text and o.parent == content and o.shown then hit = o end end
  return hit
end
local function y(o) local _, _, _, _, yy = o:GetPoint(1); return -yy end

-- ── Without GuildLedger: the World map section says what is missing ────────
GuildLedgerAPI = nil
AmazingHub:RefreshSettingsPanel(content)
check(current("+  MY PROFILE") and current("+  MODULES") and current("+  CHAT") and current("+  CHAT MESSAGES")
  and current("+  WORLD MAP"),
  "every section heading is closed by default (+), the World map section included")
check(not current("MODULES option") and not current("CHAT hint"), "a closed section's controls are hidden")
check(current("Settings"), "the page title above the first section stays")
check(y(current("+  MODULES")) == 64 and y(current("+  CHAT")) == 88, "closed sections move the rest up")
check(content:GetHeight() < 300, "the page gets shorter")

-- opening a section: click its heading
local function headingButton(fs)
  for _, o in ipairs(made) do
    if o.kind == "Button" and o.shown and o.parent == content and o.points[1] and o.points[1][2] == fs then return o end
  end
end
headingButton(current("+  MODULES")).scripts.OnClick()
check(settings.openSections and settings.openSections.MODULES == true, "the open section is remembered")
check(current("-  MODULES") and current("MODULES option") and current("MODULES hint"), "the opened section shows")
check(not current("CHAT option"), "the others stay closed")
check(y(current("-  MODULES")) == 64 and y(current("MODULES option")) == 88 and y(current("+  CHAT")) == 164,
  "an open section keeps its height and the rest follows")
headingButton(current("-  MODULES")).scripts.OnClick()
check(current("+  MODULES") and not current("MODULES option"), "and closes again")
settings.openSections = { ["WORLD MAP"] = true, ["CHAT MESSAGES"] = true, ["COLLECTOR (OFFICERS)"] = true }
AmazingHub:RefreshSettingsPanel(content)
local ok = false
for _, o in ipairs(made) do
  if o.shown and o.parent == content and type(o.text) == "string" and o.text:find("Needs GuildLedger", 1, true) then
    ok = true
  end
end
check(ok, "without GuildLedger the World map section says it needs it")

-- ── With GuildLedger ──────────────────────────────────────────────────────
local calls = {}
GuildLedgerAPI = {
  apiVersion = 1,
  GetMap = function()
    return { available = true, share = true, pins = false, shape = "round", size = 12, outline = true,
      sizeMin = 6, sizeMax = 24, near = "any", names = false, shareScope = "all", self = false,
      views = { zone = true, continent = true, world = false },
      colors = { { class = "MAGE", r = 0.25, g = 0.78, b = 0.92, custom = false },
                 { class = "WARRIOR", r = 0.78, g = 0.61, b = 0.43, custom = true } } }
  end,
  SetMapShare = function(on) calls[#calls + 1] = "share " .. tostring(on) end,
  SetMapPins = function(on) calls[#calls + 1] = "pins " .. tostring(on) end,
  SetMessages = function(on) calls[#calls + 1] = "messages " .. tostring(on) end,
  GetDevMode = function() return false end,
  GetWelcome = function() return true end,
  SetWelcome = function(on) calls[#calls + 1] = "welcome " .. tostring(on) end,
  SetDevMode = function(on) calls[#calls + 1] = "dev " .. tostring(on) end,
  GetCollector = function() return false, false end,
  SetCollector = function(on) calls[#calls + 1] = "collector " .. tostring(on) end,
  SetMapLook = function(what, a, r, g, b)
    local rest = type(r) == "number" and string.format("%.1f %.1f %.1f", r, g, b) or (r ~= nil and tostring(r) or "")
    calls[#calls + 1] = table.concat({ what, tostring(a), rest }, " ")
    return true
  end,
}
local picked
ColorPickerFrame = {
  SetupColorPickerAndShow = function(self, info) picked = info end,
  GetColorRGB = function() return 1, 0, 0 end,
  GetPreviousValues = function() return 0.3, 0.8, 0.9 end,
}
AmazingHub:RefreshSettingsPanel(content)
local function box(label)
  for _, o in ipairs(made) do if o.shown and o.label == label and o.checkbox then return o end end
end
local share = box("Show my position to guild members on the world map")
local pins = box("Show guild members on my world map")
check(share and pins and share.checkbox.checked == true and pins.checkbox.checked == false,
  "the two map switches are in Settings and show GuildLedger's state")
share.checkbox.onChanged(nil, false)
pins.checkbox.onChanged(nil, true)
local function button(text)
  for _, o in ipairs(made) do if o.shown and o.kind == "Button" and o.text == text then return o end end
end
local msgs = box("Show chat messages from the Amazing Forever Guild Pack")
check(msgs and msgs.checkbox.checked == false, "a chat-messages switch, off by default")
msgs.checkbox.onChanged(nil, true)
check(settings.chatMessages == true and calls[#calls] == "messages true", "it switches the hub and GuildLedger together")
msgs.checkbox.onChanged(nil, false)
check(settings.chatMessages == false and calls[#calls] == "messages false", "and off again")
local hello = box("Greeting and the guild's message of the day when I log in")
check(hello and hello.checkbox.checked == true, "a login-greeting switch, on by default")
hello.checkbox.onChanged(nil, false)
check(calls[#calls] == "welcome false", "the greeting switch writes through GuildLedgerAPI")
local own = box("Show my own dot (off: only the game's arrow shows you)")
check(own and own.checkbox.checked == false, "an own-dot switch, off by default")
own.checkbox.onChanged(nil, true)
check(calls[#calls] == "self true ", "the own-dot switch writes through SetMapLook")
local dev = box("Developer mode: show what GuildLedger sends and receives")
check(dev and dev.checkbox.checked == false, "a developer-mode switch, off by default")
dev.checkbox.onChanged(nil, true)
check(calls[#calls] == "dev true", "developer mode writes through GuildLedgerAPI")
local coll = box("I am a collector (I run the GuildLedger companion on this PC)")
check(coll and coll.checkbox.checked == false, "a collector switch, off by default")
check(not button("Reload now"), "no reload button while the switch matches the running role")
coll.checkbox.onChanged(nil, true)
check(calls[#calls] == "collector true", "the collector switch writes through GuildLedgerAPI")
check(button("Reload now"), "after a change a reload button shows")
coll.checkbox.onChanged(nil, false)
check(calls[#calls] == "collector false" and not button("Reload now"), "switched back: no reload needed")
calls = {}
share.checkbox.onChanged(nil, false)
pins.checkbox.onChanged(nil, true)
button("Square").scripts.OnClick()
check(calls[1] == "share false" and calls[2] == "pins true" and calls[3] == "shape square ",
  "switches and shape write through GuildLedgerAPI: " .. table.concat(calls, ", "))
local slider = _G.AmazingHubMapDotSlider
check(slider and slider.scripts.OnValueChanged, "a size slider")
slider.scripts.OnValueChanged(slider, 17.6)
check(calls[#calls] == "size 18 ", "the slider sets the size in whole pixels")
box("Dark outline (easier to see on bright maps)").checkbox.onChanged(nil, false)
check(calls[#calls] == "outline false ", "the outline switch")

-- class colours: left-click opens the game's colour picker, right-click resets
local mage, warrior
for _, o in ipairs(made) do
  if o.shown and o.kind == "Button" and o.parent == content and o.scripts.OnClick then
    for _, r in ipairs(o.regions) do
      if r.text == "Mage" then mage = o elseif r.text == "Warrior  *" then warrior = o end
    end
  end
end
check(mage and warrior, "one button per guild class; a class with its own colour is marked *")
mage.scripts.OnClick(mage, "LeftButton")
check(picked and math.abs(picked.r - 0.25) < 1e-6, "the colour picker opens with the current colour")
picked.swatchFunc()
check(calls[#calls] == "color MAGE 1.0 0.0 0.0", "a chosen colour is saved for the class")
picked.cancelFunc()
check(calls[#calls] == "color MAGE 0.3 0.8 0.9", "cancel puts the old colour back")
warrior.scripts.OnClick(warrior, "RightButton")
check(calls[#calls] == "color WARRIOR ", "right-click: back to the game's colour")
-- when and where
button("In my zone").scripts.OnClick()
check(calls[#calls] == "near zone ", "show only members in my zone")
button("Only my zone's map").scripts.OnClick()
check(calls[#calls] == "shareScope zone ", "only viewers of my zone see me")
local continentBox, worldBox = box("Continent maps"), box("World map")
check(continentBox and continentBox.checkbox.checked == true and worldBox.checkbox.checked == false,
  "one switch per kind of map, showing the current choice")
continentBox.checkbox.onChanged(nil, false)
check(calls[#calls] == "view continent false", "no dots on continent maps")
box("Names next to the dots (otherwise when you point at a dot)").checkbox.onChanged(nil, true)
check(calls[#calls] == "names true ", "names next to the dots")
button("Reset map options").scripts.OnClick()
check(calls[#calls] == "reset nil ", "reset")
button("Open world map").scripts.OnClick()
check(mapOpened == 1, "open the world map from Settings")

-- other categories get no World map section
content.__settingsCat = "about"
AmazingHub:RefreshSettingsPanel(content, "about")
check(not current("-  WORLD MAP") and not current("+  WORLD MAP"), "the World map section is on the General page only")
return "ok"
