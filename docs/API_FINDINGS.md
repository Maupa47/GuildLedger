# API findings (Phase 0)

Filled in from GLProbe output. Status: **run 1 done 2026-11-11 (build 1.60.1.70888, enUS, guild of 550). Run 2 (item 4c) done the same evening.**

## Checked from source (vendor-ref, build 1.60.1, `forever` branch)

All functions/events used by GLProbe and planned for GuildLedger exist in `Blizzard_APIDocumentationGenerated`:
`C_Club.GetGuildClubId, GetStreams, GetMessageRanges, GetMessagesBefore, GetMessagesInRange,
RequestMoreMessagesBefore, IsBeginningOfStream, FocusStream`, `C_ChatInfo.InChatMessagingLockdown`,
`C_GuildInfo.GuildRoster, IsDiscordStreamSeparate`, `issecretvalue`, `canaccessvalue`, `GetServerTime`,
`GetBuildInfo`, `GetTime`, `GetLocale`, `C_Timer.After`; events `INITIAL_CLUBS_LOADED`, `CLUB_STREAMS_LOADED`,
`CLUB_MESSAGE_ADDED`, `CLUB_MESSAGE_HISTORY_RECEIVED`, `ADDON_RESTRICTION_STATE_CHANGED`,
`GUILD_EVENT_LOG_UPDATE`. `QueryGuildEventLog`, `GetNumGuildEvents`, `GetGuildEventInfo` are undocumented
globals but called by `Blizzard_Communities/GuildInfo.lua`.

Details worth knowing:
- `RequestMoreMessagesBefore` returns `alreadyHasMessages` (bool). When true the history event may not fire.
- `ClubMemberInfo.name` "may be encoded as a Kstring" (doc comment).
- `ClubStreamInfo.streamType` is `NeverSecret`; `streamId`/`name` are not.
- `AddOnRestrictionType.Chat = 5` is the restriction type for chat lockdown.
- `WOW_PROJECT_ID` has no Forever constant in the UI source (GuildOS notes); GLProbe reads it raw.
- `wipe` is not documented; not used.

## Measured in game (run 1, 2026-11-11)

| # | Question | Result |
|---|---|---|
| 1 | Build, interface, `WOW_PROJECT_ID`, locale | 1.60.1 (70888), interface 16001, `WOW_PROJECT_ID` = 18, enUS. `issecretvalue` and `canaccessvalue` present. |
| 2 | Streams | Guild club id is a number. Streams: id 1 type 1 "Guild"; id 2 type 2 "Officer" (`leadersAndModeratorsOnly`). No Discord stream; `IsDiscordStreamSeparate()` = false. 1 message range. |
| 2 | Author fields | **`guid` present on 20/20 messages** (contradicts "often nil"). Also `name` (full name with surname, no realm), `memberId`, `classID`, `race`, `level`, `guildRank`, `guildRankOrder`, `zone`, notes, professions, `isSelf`, `isRemoteChat`, `clubType`=2, `presence`, `role`. |
| 2 | **Message text** | **`content` is a protected kstring: `"|Kw1|k"`, `"|Kw2|k"`, … numbered per session.** Docs type `kstringClubMessage`; no API decodes it. The text is only renderable in a FontString, never readable by addon code. |
| 3 | History depth | Hit the 30-page cap: 2 990 messages in 12 s, oldest 2026-11-10 21:42 UTC (~21 h back). Real limit unknown, at least ~3 000 messages / 21 h. `alreadyHasMessages` never true. One contiguous range. ~140 msgs/hour. |
| 4a | Unfocused live | `CLUB_MESSAGE_ADDED` fires for every `/g` line (30 = 30 `CHAT_MSG_GUILD`), range grows (28 grew, 2 same = timing). **No `FocusStream` needed.** |
| 4b | Focused | Same behaviour (2 = 2). `FocusStream` returned true; no visible side effects in the guild window. |
| 4c | Live text readable? pairs with club ID? | **Yes.** 10 `CHAT_MSG_GUILD` + 10 `CLUB_MESSAGE_ADDED`, all paired 1:1 by author GUID. `text` is plain (no `|K`), `playerName` = full name, arg 12 `guid` present, arg 11 `lineID` (per-client counter). Order varies: sometimes club first, sometimes chat first; gap 0–0.6 s (`GetTime`). `GetMessageInfo` in the event handler returns author name+GUID and the ID. Club epoch matches `GetServerTime()` to the second. Arg 18 `discordInfo` is a table (`fromDiscord`, `globalName`, `lastOnlineName`, `hasEmoji`, …). |
| 5 | Event log | 100 entries, covering only **~9 hours**. **Index 1 = oldest**, last = newest. Time fields = elapsed y/m/d/h (here 0/0/0/0..9). `invite`: player1 = inviter, player2 = invitee, rank = inviter's rank(?) e.g. "Guild Master". `join`/`quit`: player1 = member, player2 nil, rank = member's rank (`quit`) or "" (`join`). No `remove` entry seen yet — role order still unconfirmed. |
| 6 | Roster | 550 members. `GetGuildRosterInfo(1)` returns 17 values; **GUID at 17** (`Player-XXXX-XXXXXXXX`), name 1 without realm, rankName 2, rankIndex 3, level 4, classFile 11; position 9 = online (`true` for an online member; used for roster `ls` = last seen online). |
| 7 | Format strings (enUS) | `ERR_GUILD_JOIN_S` "%s has joined the guild." · `ERR_GUILD_LEAVE_S` "%s has left the guild." · `ERR_GUILD_REMOVE_SS` "%s has been kicked out of the guild by %s." · `ERR_GUILD_PROMOTE_SSS` "%s has promoted %s to %s." · `ERR_GUILD_DEMOTE_SSS` "%s has demoted %s to %s." |
| 8 | SavedVariables | Plain text, UTF-8 fine (non-ASCII names such as "ø" intact). IDs saved as `"1794421876704000:7593128703092"` (no exponent). Note: `position` is a large number (~10^13), not a small counter. |

## Consequences for sections 5.3 / 5.4

- **Chat text cannot come from C_Club.** C_Club still gives the exact time, the stable server ID, author name and GUID for every message, including history from before login — but not the words.
- Text must come from `CHAT_MSG_GUILD` (`text` is `cstring`, secret only in lockdown) — i.e. **only lines that arrive while a collector is online** can be logged with text. 4c confirmed: the live line pairs with its `CLUB_MESSAGE_ADDED` ID by stream + author GUID within a few seconds, so rows keep the server ID and merging across collectors stays exact.
- History from C_Club is still useful as metadata: "X wrote at T" for offline periods (activity, `/seen`), with text missing.
- Event log covers only ~100 entries (~9 h in this guild): offline roster changes older than that are seen only by the roster diff.
- GUID is reliable in both roster and club author → key members by GUID.

## Measured in Phase 2 (2026-11-11, GuildLedger with `/gl debug on`)

| What | Result |
|---|---|
| History limit | Walking back reached 2026-11-10 17:57 UTC from 2026-11-11 21:07 UTC: **~27 h, ~5 000 messages** (~185/h). A request for anything older gets **no answer at all** (no `CLUB_MESSAGE_HISTORY_RECEIVED`; `IsBeginningOfStream` stays false). The addon now gives up after 15 s × 3 tries and saves its cursor. Default `pageCap` 50 × 100 = 5 000 is just enough; raise it if the guild gets busier. |
| Request timing | With the first request sent 5 s after `INITIAL_CLUBS_LOADED`, every request was answered within ~0.5 s (48 pages in ~25 s). The client keeps downloaded history across `/reload`. |
| Catch-up after logout | Login with a saved cursor: 1 page, "caught up (+8)", correct. |
| Live pairing | 650/650 live lines paired with a club ID, all with GUID, 0 unpaired. |
| Discord-bridged messages | ~10 % of club messages (478 of 5 582) have **no `author.name` and no `author.guid`**; they come over Blizzard's Discord link (no separate stream in this guild). `ClubMemberInfo.discordInfo` (`DiscordChatInfo`: `fromDiscord`, `globalName`, `lastOnlineName`, …) carries the sender; Blizzard's `CommunitiesChatFrame.lua` uses exactly this. While the collector was online, none of these produced a stored text: either no `CHAT_MSG_GUILD` fires for them or it fires with an empty `playerName` (the old code dropped that). **Open:** the next debug log shows which (`chat g from Discord: …` / `club g message without GUID: …`). |

## Measured in Phase 3 (2026-11-11)

| What | Result |
|---|---|
| System messages | enUS `ERR_GUILD_*` patterns matched kick (target, actor), join and promote (actor, target, rank) live; names come as plain text (no player link). |
| Event log `remove` | **player1 = actor, player2 = target** (log entry for a kick by the collector named the collector as player1). Same for `promote`. |
| Event log delivery | After one `QueryGuildEventLog()`, `GUILD_EVENT_LOG_UPDATE` fired ~50 times within 1 s; every read showed 100 entries, almost always with one new entry more than the read before (+0 for invites). The client seems to receive a longer log in pieces. A later query (after `/reload`) fired once. Index 1 was 7 h old. |
| `GUILD_ROSTER_UPDATE` | Fires every few seconds in a 542-member guild (logons/logoffs); snapshots are now spaced ≥ 30 s. A full read of 542 rows caused no visible hitch. |
| Sys vs diff | Kick → roster 541 → no diff row (suppressed by the sys kick); rejoin → 542 → no diff row. |

## Measured in Phase 6 (2026-11-12)

| What | Result |
|---|---|
| Timing in game (`debugprofilestop`) | roster snapshot of 541 members **3.0 ms** (max of 6), guild event log read 0.7 ms, history step (≤ 500 messages) 1.4 ms. All far below one frame (16 ms at 60 fps). |
| Chat lockdown during a boss fight | **not yet checked in game** (covered by the stub tests only). |

## Map (pack step M, 2026-11-13) — checked in the docs, not yet in game

From `MapDocumentation.lua`, `InstanceDocumentation.lua`, `UnitDocumentation.lua` (forever branch): `C_Map.GetBestMapForUnit`,
`C_Map.GetPlayerMapPosition` (returns a `Vector2DMixin`, read with `:GetXY()` as Blizzard's own map code does),
`C_Map.GetMapInfo` (`parentMapID`, `name`), `C_Map.GetMapRectOnMap`, `IsInInstance`, `UnitInParty`, `UnitInRaid`
(`SecretWhenUnitIdentityRestricted`). None of the map returns is marked secret; the addon checks anyway.
`WorldMapFrame` is loaded at start (not load-on-demand); `MapCanvasMixin:GetCanvas/GetCanvasScale/GetMapID` exist.
Dots are plain frames on the canvas (no `AcquirePin`: its pools need an XML template inheriting
`MapCanvasPinMixin`, which may not be loaded when our addon loads). **To check in game:** dots appear and scale,
no taint error when using the map in combat / clicking quest pins and flight points, positions in cities and
instances (expected: nothing sent inside instances).
