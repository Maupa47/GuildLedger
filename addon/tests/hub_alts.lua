-- H8 (PLAN_COMMUNITY W18): "Link your other characters?" is asked once, Link holds across reloads with no
-- officer online, and "Not now" is remembered. Runs the hub's real Core, Compat, Utils, CommSystem,
-- AltAutoDetect and AltSync, set up like upstream's tools/alt-autodetect.lua; synthetic names only.
ADDON = ADDON or "."

local function check(cond, what)
  if not cond then
    io.stderr:write("FAIL: " .. what .. "\n")
    error("FAIL: " .. what, 0)
  end
end

DEFAULT_CHAT_FRAME = { AddMessage = function() end }
function CreateFrame()
  local f = {}
  function f:RegisterEvent() end
  function f:SetScript() end
  return f
end
function hooksecurefunc() end
function GetBuildInfo() return "2.5.6", "60000", "", 20506 end
WOW_PROJECT_BURNING_CRUSADE_CLASSIC, WOW_PROJECT_ID = 5, 5
function GetRealmName() return "Realm" end
local now = 1000000
function GetServerTime() return now end
function GetTime() return 1 end
local afters = {}
C_Timer = { After = function(_, fn) afters[#afters + 1] = fn end,
            NewTicker = function() return { Cancel = function() end } end }
Enum = { SendAddonMessageResult = {} }

-- Rank 1 is the only officer rank; nobody of rank 1 is online in this test.
local ROSTER = { { "Boss", 1 }, { "Mainy", 5 }, { "Alty", 5 }, { "Thirdy", 5 } }
local me, level = "Mainy", 60
function UnitName() return me end
function UnitLevel() return level end
function UnitClass() return "Warrior", "WARRIOR" end
function IsInGuild() return true end
function GetNumGuildMembers() return #ROSTER end
function GetGuildRosterInfo(i) local r = ROSTER[i]; if r then return r[1] .. "-Realm", "Rank", r[2] end end
function GetGuildInfo()
  for _, r in ipairs(ROSTER) do if r[1] == me then return "Guild", "Rank", r[2] end end
end

local registry, store, n = {}, {}, 0
LibStub = setmetatable({ NewLibrary = function(_, k) registry[k] = registry[k] or {}; return registry[k] end,
  GetLibrary = function(_, k) return registry[k] end },
  { __call = function(_, k) registry[k] = registry[k] or {}; return registry[k] end })
LibStub("AmazingHub-LibSerialize").Serialize = function(_, t) n = n + 1; store["s" .. n] = t; return "s" .. n end
LibStub("AmazingHub-LibSerialize").Deserialize = function(_, s) if store[s] then return true, store[s] end return false end
LibStub("LibDeflate").DecodeForWoWAddonChannel = function(_, s) return s end
LibStub("LibDeflate").DecompressDeflate = function(_, s) return s end

AmazingHub = { L = setmetatable({}, { __index = function(_, k) return k end }), VERSION = "test" }
dofile(ADDON .. "/Core/Core.lua")
dofile(ADDON .. "/Core/Compat.lua")
dofile(ADDON .. "/Core/Utils.lua")
dofile(ADDON .. "/Modules/CommSystem.lua")
dofile(ADDON .. "/Modules/AltAutoDetect.lua")
dofile(ADDON .. "/Modules/AltSync.lua")
local CS, AD = AmazingHub.CommSystem, AmazingHub.AltAutoDetect
CS.pendingMessages = CS.pendingMessages or {}
CS.SendMessage = function() end

local asked = {}
AmazingHub.Dialogs = AmazingHub.Dialogs or {}
AmazingHub.ShowDialog = function(_, name, _, _, r)
  asked[#asked + 1] = r
  return { data = r }
end

-- What the game keeps between sessions: the account-wide table and the guild's saved data.
AmazingHubDB = {}
AmazingHub.db = { settings = { officerMaxRank = 1 } }

local K = function(name) return AmazingHub:GetPlayerKey(name, "Realm") end
local MAIN, ALT = K("Mainy"), K("Alty")

-- One login: the character is recorded, the prompt waits 10 s, everything due runs.
local function login(who, lvl)
  me, level = who, lvl
  AD._prompted, AD._resentAt = nil, nil
  asked = {}
  AD:RecordSelf()
  AD:_SchedulePrompt()
  local due = afters
  afters = {}
  for _, fn in ipairs(due) do fn() end
  return #asked
end

-- Mainy and Alty play on the same account; logging in on both records them.
check(login("Alty", 20) == 0, "one character alone: nothing to ask")
check(login("Mainy", 60) == 1, "a second character of the account in the guild: asked")
check(asked[1].main == MAIN, "the higher level is offered as the main")
check(login("Mainy", 60) == 1, "not answered: asked again at the next login")

-- Not now: remembered for this group.
AD:_RegisterPopup()
local dlg = AmazingHub.Dialogs["AMAZINGHUB_ALT_AUTODETECT"]
dlg.OnCancel(nil, asked[1])
check(login("Mainy", 60) == 0, "Not now: not asked again")
check(login("Alty", 20) == 0, "nor on the other character")

-- A new character changes the group: asked again; Link this time, as a member with no officer online.
login("Thirdy", 10)
check(#asked == 1, "a new character in the group: asked once more")
dlg.OnAccept(nil, asked[1])
check(AmazingHub.db.altLinks and AmazingHub.db.altLinks[ALT] == MAIN, "Link: Alty is an alt of Mainy at once")
check(login("Mainy", 60) == 0, "after Link: not asked at the next login, with no officer online")
check(AmazingHub.db.altLinks[ALT] == MAIN, "and the link still holds")
check(login("Alty", 20) == 0, "nor on the alt")
os.exit(0)
