-- The countdown on the Dashboard with no client to try it on (issue #232), run against the real
-- UI/Dashboard.lua: when it works, the slices of the guild; when it fails, in the module or in the
-- drawing, the card it replaced, with the rest of the Dashboard drawn and the error in /amazing errors.
--
--   luajit -e 'ADDON="."' tools/dashboard-countdown.lua
--
-- Exits 1 on the first failed check.
ADDON = ADDON or "."

local checks = 0
local function check(cond, what)
  checks = checks + 1
  if not cond then
    io.stderr:write("FAIL: " .. what .. "\n")
    os.exit(1)
  end
end

-- Any frame, any method: numbers where the layout does arithmetic, itself everywhere else.
local NUM = { GetWidth = 300, GetHeight = 120, GetFrameLevel = 1, GetStringHeight = 12, GetStringWidth = 40 }
local stub
stub = setmetatable({}, { __index = function(_, k)
  if NUM[k] then return function() return NUM[k] end end
  if k == "GetChildren" or k == "GetRegions" then return function() end end
  return function() return stub end
end })
DEFAULT_CHAT_FRAME = { AddMessage = function() end }
function CreateFrame() return stub end
function hooksecurefunc() end
function GetBuildInfo() return "2.5.6", "60000", "", 20506 end
WOW_PROJECT_BURNING_CRUSADE_CLASSIC, WOW_PROJECT_ID = 5, 5
function GetRealmName() return "Realm" end
function UnitName() return "Me" end
function GetNumGuildMembers() return 0, 0 end
function IsInGuild() return true end
function GetGuildInfo() return "Guild", "Rank", 5 end
function GetServerTime() return 1000 end
C_Timer = { After = function() end, NewTicker = function() return { Cancel = function() end } end }
Enum = { SendAddonMessageResult = {} }
AmazingHub = { L = setmetatable({}, { __index = function(_, k) return k end }), VERSION = "test" }
dofile(ADDON .. "/Core/Core.lua")
dofile(ADDON .. "/Core/Compat.lua")
dofile(ADDON .. "/Core/Data.lua")
dofile(ADDON .. "/Core/Utils.lua")
local texts = {}
AmazingHub.UI = setmetatable({
  GetFeature = function() return nil end,
  CreateText = function(_, _, t) texts[#texts + 1] = tostring(t); return stub end,
  CreateButton = function(_, _, t) texts[#texts + 1] = tostring(t); return stub end,
  CreateHeaderText = function(_, _, t) texts[#texts + 1] = tostring(t); return stub end,
}, { __index = function() return function() return stub end end })
dofile(ADDON .. "/UI/Dashboard.lua")
function AmazingHub:CreateGuildChatFeed() return function() end end
AmazingHub.Recruitment = { MemberMayPost = function() return true end, SetParticipation = function() end }

local function shown(text)
  for _, t in ipairs(texts) do
    if t:find(text, 1, true) then return true end
  end
  return false
end

local function show(countdown)
  AmazingHub.db = { settings = { modules = {} }, guildRecruitment = { enabled = true, message = "We recruit" } }
  AmazingHub.Readiness = { GetReport = function() return {} end, Countdown = countdown }
  AmazingHub.State.errors = {}
  texts = {}
  local refresh = AmazingHub:CreateDashboardPanel(stub)
  local ok, err = pcall(refresh)
  check(ok, "the dashboard draws (" .. tostring(err) .. ")")
end

local THE_OLD_CARD = "No readiness data yet"
local THE_REST = "Guild is recruiting"

-- ── It works: the slices ──────────────────────────────────────────
local function slices(ready, s)
  return function()
    return { open = false, days = 36, cap = 60, cores = {}, guild = { ready = ready, slices = s } }
  end
end
show(slices(27, { dungeons = 5, raids = { { size = 10, count = 2 }, { size = 20, count = 1 } } }))
check(shown("Can form") and shown("5 groups"), "27 at 60: the line of what the guild can form")
check(shown("2×10") and shown("1×20"), "with each raid's size")
check(shown(THE_REST), "and the rest of the Dashboard")
check(not shown(THE_OLD_CARD), "the old card is not there")

show(slices(3, { dungeons = 0, raids = {}, short = 2, shortSize = 5 }))
check(not shown("Can form"), "nothing to form yet: no such line")

-- ── It fails: the card it replaced ────────────────────────────────
show(function() error("no such thing on this client") end)
check(shown(THE_OLD_CARD), "the module fails: the old card")
check(shown(THE_REST), "and the rest of the Dashboard is drawn")
check(#AmazingHub.State.errors == 1, "and /amazing errors has it")

show(function() return { cap = 60 } end)
check(shown(THE_OLD_CARD), "the drawing fails on what the module gave: the old card")
check(shown(THE_REST), "and the rest of the Dashboard is drawn")
check(#AmazingHub.State.errors == 1, "and /amazing errors has it")

-- ── Off Forever: the card it always was, and no error ─────────────
show(function() return nil end)
check(shown(THE_OLD_CARD) and #AmazingHub.State.errors == 0, "no countdown here: the old card, and nothing recorded")

-- ── The guild's setup (issue #217) ────────────────────────────────────
local function setup(activation)
  AmazingHub.Activation = activation
  show(function() return nil end)
  AmazingHub.Activation = nil
end
setup({
  STEPS = { "publish", "bot", "account", "members", "run" },
  ShouldShow = function() return true end,
  Read = function() return { done = 2, steps = { publish = true, bot = true }, staleDays = 4 } end,
})
check(shown("SET UP AMAZING HUB FOR YOUR GUILD"), "the card, for who it is due")
check(shown("Publish through the companion") and shown("First group run"), "with its steps")
check(shown("Verified 4 days ago"), "and how old what the site said is")
check(shown(THE_REST), "and the rest of the Dashboard")

setup({ STEPS = {}, ShouldShow = function() return false end })
check(shown(THE_REST) and #AmazingHub.State.errors == 0, "not due: nothing changes")

setup({ STEPS = {}, ShouldShow = function() error("no such thing on this client") end })
check(shown(THE_REST), "a failure leaves the Dashboard as it was")
check(#AmazingHub.State.errors == 1, "and /amazing errors has it")

-- ── The Achievements tab (issue #216): it draws, with something and with nothing ──
dofile(ADDON .. "/UI/AchievementsPanel.lua")
AmazingHub.ApplyFont = function() end
AmazingHub.UI.CreateScrollFrame = function() return stub, stub end
date = os.date
AmazingHub.State.errors = {}
AmazingHub.Achievements = {
  Renown = function() return 7, 700 end,
  Insignia = function() return "Interface/AddOns/AmazingHub/Media/renown-horde-2", "Company" end,
  Next = function() return { { title = "Ready", current = 8, target = 10 } } end,
  Earned = function() return { { title = "First", at = 1000 } } end,
}
AmazingHub:CreateAchievementsPanel(stub)
AmazingHub.Achievements.Insignia = function() return nil, nil end   -- an older site: the line alone
AmazingHub:CreateAchievementsPanel(stub)
AmazingHub.Achievements = { Renown = function() return nil end }
AmazingHub:CreateAchievementsPanel(stub)
check(#AmazingHub.State.errors == 0, "the tab draws, with a block and without one")

print(("dashboard-countdown: %d checks passed"):format(checks))
