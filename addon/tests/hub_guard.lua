-- Amazing Hub's outbound guard (tools/rebrand-hub.py patches), against the real Core/Core.lua and Core/Compat.lua
-- under a stubbed client. Run by addon/tests/test_hub.py with ADDON = the AmazingHub folder.
-- Raises on the first failed check.
ADDON = ADDON or "."

local function check(cond, what)
  if not cond then error("FAIL: " .. what, 0) end
end

-- ── The client ──────────────────────────────────────────────────────────
DEFAULT_CHAT_FRAME = { AddMessage = function() end }
StaticPopupDialogs, UISpecialFrames, CLASS_ICON_TCOORDS, RAID_CLASS_COLORS = {}, {}, {}, {}
SlashCmdList = {}
function CreateFrame()
  local f = { scripts = {} }
  function f:RegisterEvent() end
  function f:UnregisterEvent() end
  function f:SetScript(k, fn) self.scripts[k] = fn end
  function f:Show() end
  function f:Hide() end
  return f
end
function GetServerTime() return 1757800000 end
function GetTime() return 1000 end
function time() return 1757800000 end
function IsInGuild() return true end
function IsInRaid() return false end
function IsInGroup() return false end
function IsInInstance() return false end
function hooksecurefunc() end
function debugstack() return "" end
function GetBuildInfo() return "1.60.1", "70888", "", 16001 end
function GetRealmName() return "Forever" end
function GetLocale() return "enUS" end
function strtrim(s) return (s:gsub("^%s+", ""):gsub("%s+$", "")) end
tinsert, strlower, strupper, strfind = table.insert, string.lower, string.upper, string.find
C_Timer = { After = function() end, NewTicker = function() return { Cancel = function() end } end }
local registry = {}
LibStub = setmetatable({
  NewLibrary = function(_, name) registry[name] = registry[name] or {}; return registry[name] end,
  GetLibrary = function(_, name) return registry[name] end,
}, { __call = function(_, name) registry[name] = registry[name] or {}; return registry[name] end })
AmazingHub = { L = setmetatable({}, { __index = function(_, k) return k end }), VERSION = "test" }

local GUILD = { ["Ana"] = true, ["Lethaniel Blightwood"] = true }
C_GuildInfo = { MemberExistsByName = function(name) return GUILD[name] == true end }

local addon, chat, joined = {}, {}, 0
C_ChatInfo = {
  SendAddonMessage = function(prefix, text, channel, target) addon[#addon + 1] = channel .. ":" .. tostring(target) end,
  SendChatMessage = function(text, chatType, lang, target) chat[#chat + 1] = chatType .. ":" .. tostring(target) end,
}
function JoinChannelByName() joined = joined + 1 end

dofile(ADDON .. "/Core/Core.lua")
dofile(ADDON .. "/Core/Compat.lua")
local Compat = AmazingHub.Compat
AmazingHub.RecordError = function() end
AmazingHub.IsGuildmate = function() return false end

-- ── Addon messages ──────────────────────────────────────────────────────
for _, ch in ipairs({ "GUILD", "OFFICER", "PARTY", "RAID", "INSTANCE_CHAT" }) do
  Compat.SendAddonMessage("AMAZINGHUB", "x", ch)
end
check(#addon == 5, "guild, officer, party, raid and instance addon messages go (" .. #addon .. ")")
addon = {}
Compat.SendAddonMessage("AMAZINGHUB", "x", "CHANNEL", 5)
Compat.SendAddonMessage("AMAZINGHUB", "x", "YELL")
Compat.SendAddonMessage("AMAZINGHUB", "x", "SAY")
Compat.SendAddonMessageNow("AMAZINGHUB", "x", "CHANNEL", 5)
check(#addon == 0, "no addon message to a channel, SAY or YELL")
Compat.SendAddonMessage("AMAZINGHUB", "x", "WHISPER", "Stranger")
Compat.SendAddonMessageNow("AMAZINGHUB", "x", "WHISPER", "Stranger")
check(#addon == 0, "no addon whisper to somebody outside the guild")
Compat.SendAddonMessage("AMAZINGHUB", "x", "WHISPER", "Lethaniel Blightwood")
check(#addon == 1 and addon[1] == "WHISPER:Lethaniel Blightwood", "an addon whisper to a guild member goes")
AmazingHub.IsGuildmate = function(_, name) return name == "Bob" end
C_GuildInfo.MemberExistsByName = nil
Compat.SendAddonMessage("AMAZINGHUB", "x", "WHISPER", "Bob")
check(#addon == 2, "without MemberExistsByName the hub's own roster decides")

-- ── Chat lines ──────────────────────────────────────────────────────────
check(Compat.SendChatMessage("hi", "SAY") == false and Compat.SendChatMessage("hi", "YELL") == false
  and Compat.SendChatMessage("hi", "CHANNEL") == false, "Compat.SendChatMessage: no SAY, YELL or channel")
check(#chat == 0, "and nothing was sent")
Compat.SendChatMessage("hi", "GUILD")
check(#chat == 1, "a guild line goes")
chat = {}
Compat.GuardedChat("hi", "CHANNEL", nil, 4)
Compat.GuardedChat("hi", "WHISPER", nil, "Stranger")
Compat.GuardedChat("hi", "SAY")
check(#chat == 0, "GuardedChat: no channel, no whisper to a stranger, no SAY")
Compat.GuardedChat("hi", "WHISPER", nil, "Bob")
Compat.GuardedChat("hi", "RAID")
check(#chat == 2, "GuardedChat: a whisper to a guild member and a raid line go")

-- ── Channels ────────────────────────────────────────────────────────────
check(Compat.JoinChannel("SomePublicChannel") == false and joined == 0, "Compat.JoinChannel never joins")

return "ok"
