-- Amazing Hub Settings additions (addon/hub-extra/SettingsPlus.lua, as built into addon/AmazingHub/UI) on top of a
-- fake of upstream's Form pages (UI/SettingsPanel.lua, GuildOS 1.40: rows top to bottom, re-anchored by Layout;
-- RefreshSettingsPanel(content, key) returns the Form). Fake frames, a fake GuildLedgerAPI.
-- Run by addon/tests/test_hub.py with ADDON = the AmazingHub folder.
ADDON = ADDON or "."

local function check(cond, what)
  if not cond then error("FAIL: " .. what, 0) end
end

-- ── Fake widgets ──────────────────────────────────────────────────────────
local NOOP = { __index = function() return function() end end }
local made = {}
local function obj(parent, kind)
  local o = setmetatable({ parent = parent, kind = kind, shown = true, points = {}, scripts = {}, kids = {},
    regions = {}, text = "", h = 0 }, NOOP)
  function o:GetParent() return self.parent end
  function o:SetPoint(...) self.points[#self.points + 1] = { ... } end
  function o:GetPoint(i) local p = self.points[i or 1]; if p then return unpack(p) end end
  function o:ClearAllPoints() self.points = {} end
  function o:SetAllPoints(t) self.allPoints = t end
  function o:SetShown(v) self.shown = v and true or false end
  function o:Show() self.shown = true end
  function o:Hide() self.shown = false end
  function o:IsShown() return self.shown end
  function o:SetText(t) self.text = t end
  function o:GetText() return self.text end
  function o:SetScript(k, fn) self.scripts[k] = fn end
  function o:GetWidth() return 600 end
  function o:SetHeight(h) self.h = h end
  function o:GetHeight() return self.h end
  function o:GetStringHeight() return 14 end
  function o:GetChildren() return unpack(self.kids) end
  function o:GetRegions() return unpack(self.regions) end
  function o:CreateTexture() local t = obj(self, "Texture"); self.regions[#self.regions + 1] = t; return t end
  function o:CreateFontString() local t = obj(self, "FontString"); self.regions[#self.regions + 1] = t; return t end
  function o:GetName() return self.name end
  function o:SetValue(v) self.value = v; if self.scripts.OnValueChanged then self.scripts.OnValueChanged(self, v) end end
  made[#made + 1] = o
  return o
end
local function child(parent, kind)
  local c = obj(parent, kind)
  if parent then parent.kids[#parent.kids + 1] = c end
  return c
end
function CreateFrame(kind, name, parent)
  local f = child(parent, kind)
  f.name = name
  if name then _G[name] = f end
  return f
end

local UI = {}
function UI:CreateText(parent, text) local fs = obj(parent, "FontString"); fs.text = text; parent.regions[#parent.regions + 1] = fs; return fs end
function UI:CreateSeparator(parent) return child(parent, "Frame") end
function UI:CreateCheckbox(parent, label)
  local f = child(parent, "Frame")
  f.label, f.text = obj(f), label
  f.checkbox = { checked = false, enabled = true }
  function f.checkbox:SetChecked(v) self.checked = v end
  function f.checkbox:Enable() self.enabled = true end
  function f.checkbox:Disable() self.enabled = false end
  return f
end
function UI:CreateButton(parent, text)
  local b = child(parent, "Button"); b.text = text; b.label = obj(b)
  function b:SetBaseColor(r, g, bb, a) self.base = { r, g, bb, a } end
  return b
end

local settings = {}
AmazingHub = {
  UI = UI,
  Colors = setmetatable({}, { __index = function() return { r = 1, g = 1, b = 1 } end }),
}
function AmazingHub:GetSetting(k) return settings[k] end
function AmazingHub:SetSetting(k, v) settings[k] = v end
function AmazingHub:ApplyFont() end
function AmazingHub:SafeCall(fn, ...) return pcall(fn, ...) end
local mapOpened = 0
function AmazingHub:ToggleGuildMap() mapOpened = mapOpened + 1 end

-- ── A fake of upstream's Form ─────────────────────────────────────────────
local Form = {}
Form.__index = Form
function Form:Row(o, opts)
  opts = opts or {}
  self.rows[#self.rows + 1] = { obj = o, h = opts.h, shown = opts.shown, place = opts.place, gap = opts.gap or 8 }
  return o
end
function Form:Sync(fn) self.syncs[#self.syncs + 1] = fn end
function Form:Refresh() for _, fn in ipairs(self.syncs) do fn() end; return self:Layout() end
function Form:Layout()
  local y = 0
  for _, r in ipairs(self.rows) do
    local on = not r.shown or r.shown() and true or false
    r.obj:SetShown(on)
    if on then
      r.obj:ClearAllPoints()
      r.obj:SetPoint("TOPLEFT", self.content, "TOPLEFT", 0, -y)
      r.y = y
      y = y + r.gap + (r.place and r.place(r.obj, 600, 600) or r.h or 14)
    end
  end
  self.content:SetHeight(y)
  return y
end
function Form:Section(title, shown)
  if #self.rows > 0 then self:Row(UI:CreateSeparator(self.content), { h = 1, shown = shown }) end
  local fs = self.content:CreateFontString()
  fs:SetText(title)
  fs.section = true
  return self:Row(fs, { shown = shown })
end
function Form:Note(text, opts)
  opts = opts or {}
  return self:Row(UI:CreateText(self.content, text), { shown = opts.shown })
end
function Form:Check(label, desc, get, set, opts)
  opts = opts or {}
  local f = UI:CreateCheckbox(self.content, label)
  f.checkbox.onChanged = function(_, v) set(v and true or false); self:Refresh() end
  self:Sync(function() f.checkbox:SetChecked(get() and true or false) end)
  self:Row(f, { h = 18, shown = opts.shown })
  if desc then self:Note(desc, { shown = opts.shown }) end
  return f
end
function Form:Buttons(list, opts)
  opts = opts or {}
  local holder = CreateFrame("Frame", nil, self.content)
  for _, spec in ipairs(list) do
    local b = UI:CreateButton(holder, spec[1])
    b:SetScript("OnClick", spec[2])
  end
  return self:Row(holder, { h = 26, shown = opts.shown })
end

-- Pages as upstream builds them: profile has two sections, interface one, chat one, modules two
local PAGES = {
  profile = function(F) F:Section("You"); F:Check("A profile switch", nil, function() return true end, function() end)
    F:Section("Getting started"); F:Note("Replay the intro") end,
  interface = function(F) F:Section("Appearance"); F:Note("UI scale") end,
  chat = function(F) F:Section("Guild chat"); F:Check("Annotate guild chat", nil, function() return true end, function() end) end,
  modules = function(F) F:Section("Tabs"); F:Note("Roster"); F:Section("Officer tools"); F:Note("Audit") end,
}
local builds, shape = 0, 1
function AmazingHub:RefreshSettingsPanel(content, key)
  key = ({ general = "profile" })[key] or key
  if not PAGES[key] then key = "profile" end
  local s = key .. shape
  local F = content.__settingsForm
  if not F or content.__settingsShape ~= s then
    if F then
      for _, k in ipairs({ content:GetChildren() }) do k:Hide() end
      for _, r in ipairs({ content:GetRegions() }) do r:Hide() end
    end
    builds = builds + 1
    F = setmetatable({ content = content, rows = {}, syncs = {} }, Form)
    PAGES[key](F)
    content.__settingsForm, content.__settingsShape = F, s
  end
  F:Refresh()
  return F
end

dofile(ADDON .. "/UI/SettingsPlus.lua")

local content = child(obj(nil, "ScrollFrame"), "Frame")
local function shown(text)
  for i = #made, 1, -1 do
    local o = made[i]
    if o.shown and (o.text == text or (type(o.text) == "string" and o.text:find(text, 1, true))) then
      local p = o.parent
      while p and p ~= content do if not p.shown then break end p = p.parent end
      if p == content then return o end
    end
  end
end
local function visible(o) -- shown, and every parent up to the page too
  local p = o
  while p and p ~= content do if not p.shown then return false end p = p.parent end
  return p == content
end
local function box(label)
  for i = #made, 1, -1 do local o = made[i]; if o.text == label and o.checkbox and visible(o) then return o end end
end
local function button(text)
  for i = #made, 1, -1 do local o = made[i]; if o.kind == "Button" and o.text == text and visible(o) then return o end end
end
local function clickArea(fs)
  for i = #made, 1, -1 do local o = made[i]; if o.kind == "Button" and o.allPoints == fs then return o end end
end

-- ── Without GuildLedger ───────────────────────────────────────────────────
GuildLedgerAPI = nil
local F = AmazingHub:RefreshSettingsPanel(content, "profile")
check(builds == 2, "the first page is built twice, so its headings are known: " .. builds)
check(shown("-  You") and shown("+  Getting started"), "the first section starts open, the next closed")
check(shown("A profile switch") and not shown("Replay the intro"), "a closed section's rows are hidden")
check(not shown("Collector (officers)"), "no collector section without GuildLedger")
clickArea(shown("+  Getting started")).scripts.OnClick()
check(settings.openSections["Getting started"] == true and shown("-  Getting started") and shown("Replay the intro"),
  "a click opens a section and it is remembered")
clickArea(shown("-  You")).scripts.OnClick()
check(not shown("A profile switch") and shown("+  You"), "and closes one")
local again = AmazingHub:RefreshSettingsPanel(content, "profile")
check(again == F and builds == 2, "a refresh of the same page builds nothing new")
check(#F.__amzHeads == 2, "our rows are added once per Form")

AmazingHub:RefreshSettingsPanel(content, "interface")
check(shown("+  World map") and not shown("Needs GuildLedger"), "the World map section starts closed")
clickArea(shown("+  World map")).scripts.OnClick()
check(shown("Needs GuildLedger"), "without GuildLedger the World map section says it needs it")

-- ── With GuildLedger ──────────────────────────────────────────────────────
local calls = {}
local map = { available = true, share = true, pins = false, shape = "round", size = 12, outline = true,
  sizeMin = 6, sizeMax = 24, near = "any", names = false, shareScope = "all", self = false,
  views = { zone = true, continent = true, world = false },
  colors = { { class = "MAGE", r = 0.25, g = 0.78, b = 0.92, custom = false },
             { class = "WARRIOR", r = 0.78, g = 0.61, b = 0.43, custom = true } } }
local collector = false
GuildLedgerAPI = {
  apiVersion = 1,
  GetMap = function() return map end,
  SetMapShare = function(on) calls[#calls + 1] = "share " .. tostring(on); map.share = on end,
  SetMapPins = function(on) calls[#calls + 1] = "pins " .. tostring(on) end,
  SetMessages = function(on) calls[#calls + 1] = "messages " .. tostring(on) end,
  GetDevMode = function() return false end,
  GetWelcome = function() return true end,
  SetWelcome = function(on) calls[#calls + 1] = "welcome " .. tostring(on) end,
  SetDevMode = function(on) calls[#calls + 1] = "dev " .. tostring(on) end,
  GetCollector = function() return collector, false end,
  SetCollector = function(on) calls[#calls + 1] = "collector " .. tostring(on); collector = on end,
  SetMapLook = function(what, a, r, g, b)
    local rest = type(r) == "number" and string.format("%.1f %.1f %.1f", r, g, b) or (r ~= nil and tostring(r) or "")
    calls[#calls + 1] = table.concat({ what, tostring(a), rest }, " ")
    if what == "near" or what == "shareScope" or what == "shape" then map[what] = a end
    return true
  end,
}
local picked
ColorPickerFrame = {
  SetupColorPickerAndShow = function(self, info) picked = info end,
  GetColorRGB = function() return 1, 0, 0 end,
  GetPreviousValues = function() return 0.3, 0.8, 0.9 end,
}

-- chat page: Chat messages
shape = 2 -- a new shape: upstream makes a fresh Form, ours are added to it
AmazingHub:RefreshSettingsPanel(content, "chat")
check(shown("-  Guild chat") and shown("+  Chat messages"), "the chat page: upstream's section open, ours closed")
clickArea(shown("+  Chat messages")).scripts.OnClick()
local msgs = box("Show chat messages from the Amazing Forever Guild Pack")
check(msgs and msgs.checkbox.checked == false, "a chat-messages switch, off by default")
msgs.checkbox.onChanged(nil, true)
check(settings.chatMessages == true and calls[#calls] == "messages true", "it switches the hub and GuildLedger together")
local hello = box("Greeting and the guild's message of the day when I log in")
check(hello and hello.checkbox.checked == true, "a login-greeting switch, on by default")
hello.checkbox.onChanged(nil, false)
check(calls[#calls] == "welcome false", "the greeting switch writes through GuildLedgerAPI")
local dev = box("Developer mode: show what GuildLedger sends and receives")
check(dev and dev.checkbox.checked == false, "a developer-mode switch, off by default")
dev.checkbox.onChanged(nil, true)
check(calls[#calls] == "dev true", "developer mode writes through GuildLedgerAPI")
check(not shown("World map") and not shown("Collector (officers)"), "only the chat section on the chat page")

-- profile page: Collector
AmazingHub:RefreshSettingsPanel(content, "profile")
clickArea(shown("+  Collector (officers)")).scripts.OnClick()
local coll = box("I am a collector (I run the GuildLedger companion on this PC)")
check(coll and coll.checkbox.checked == false, "a collector switch, off by default")
check(not button("Reload now"), "no reload button while the switch matches the running role")
coll.checkbox.onChanged(nil, true)
check(calls[#calls] == "collector true" and button("Reload now"), "after a change a reload button shows")
coll.checkbox.onChanged(nil, false)
check(calls[#calls] == "collector false" and not button("Reload now"), "switched back: no reload needed")

-- interface page: World map
AmazingHub:RefreshSettingsPanel(content, "interface")
check(shown("-  World map"), "a section opened before stays open on a fresh page")
local share = box("Show my position to guild members on the world map")
local pins = box("Show guild members on my world map")
check(share and pins and share.checkbox.checked == true and pins.checkbox.checked == false,
  "the two map switches show GuildLedger's state")
check(button("Only my zone's map"), "who sees me: shown while sharing")
calls = {}
share.checkbox.onChanged(nil, false)
check(calls[1] == "share false" and not button("Only my zone's map"), "sharing off hides who sees me")
share.checkbox.onChanged(nil, true)
pins.checkbox.onChanged(nil, true)
check(calls[3] == "pins true", "pins switch")
button("Square").scripts.OnClick()
check(calls[#calls] == "shape square " and button("Square").base[4] == 0.95 and button("Round").base[4] == 0.92,
  "shape writes through, and the chosen button is marked")
local slider = _G.AmazingHubMapDotSlider
check(slider and slider.scripts.OnValueChanged, "a size slider")
slider.scripts.OnValueChanged(slider, 17.6)
check(calls[#calls] == "size 18 ", "the slider sets the size in whole pixels")
box("Dark outline (easier to see on bright maps)").checkbox.onChanged(nil, false)
check(calls[#calls] == "outline false ", "the outline switch")
local mage, warrior
for _, o in ipairs(made) do
  if o.shown and o.kind == "Button" and o.scripts.OnClick then
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
button("In my zone").scripts.OnClick()
check(calls[#calls] == "near zone " and button("In my zone").base[4] == 0.95, "show only members in my zone")
button("Only my zone's map").scripts.OnClick()
check(calls[#calls] == "shareScope zone ", "only viewers of my zone see me")
local continentBox, worldBox = box("Continent maps"), box("World map")
check(continentBox and continentBox.checkbox.checked == true and worldBox.checkbox.checked == false,
  "one switch per kind of map, showing the current choice")
continentBox.checkbox.onChanged(nil, false)
check(calls[#calls] == "view continent false", "no dots on continent maps")
box("Names next to the dots (otherwise when you point at a dot)").checkbox.onChanged(nil, true)
check(calls[#calls] == "names true ", "names next to the dots")
local own = box("Show my own dot (off: only the game's arrow shows you)")
own.checkbox.onChanged(nil, true)
check(calls[#calls] == "self true ", "the own-dot switch writes through SetMapLook")
button("Reset map options").scripts.OnClick()
check(calls[#calls] == "reset nil ", "reset")
button("Open world map").scripts.OnClick()
check(mapOpened == 1, "open the world map from Settings")

-- a page without our sections
AmazingHub:RefreshSettingsPanel(content, "modules")
check(shown("-  Tabs") and shown("+  Officer tools") and not shown("World map") and not shown("Chat messages"),
  "the modules page folds, and gets none of our sections")

-- the title bar's search reads every page, and the headings and switches of the pages built so far
local idx, found, pages = AmazingHub.SettingsPlus.Index(), nil, 0
for _, e in ipairs(idx) do
  if not e.section and not e.F then pages = pages + 1 end
  if e.label == "Online members first, whatever column is sorted" then found = e end
end
check(pages == 6, "the search lists the six Settings pages")
check(found and found.page == "interface" and found.section == "Member list" and found.obj ~= nil,
  "and our switch with its page and section")
return "ok"
