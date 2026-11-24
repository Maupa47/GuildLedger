# Hub audit: GuildOS as the base of the guild window (Phase 8)

2026-11-14. Source: GuildOS **1.20.1**, commit `80883a096cdf9fa1366fb1a248e99b4462d74a21` (2026-11-10), MIT,
© 2026 danielcosta42, in `/vendor-ref/GuildOS` (git-ignored). One build serves TBC Anniversary (20506), WoW: Forever
(16001) and retail (120105). Size: ~70 modules, ~37 UI files (UI alone ≈ 27 000 lines), 139 test scripts in `tools/`.
Verdicts below are from file headers and greps; Phase 9 confirms each by reading the code before changing it.

## 1. What it has that we want (keep)

| Area | Files | Notes |
|---|---|---|
| Window, layout, feature registry | `UI/Window.lua`, `UI/Layout.lua`, `UI/Helpers.lua`, `UI/FeatureRegistry.lua`, `UI/Features.lua`, `UI/Dashboard.lua`, `UI/Minimap.lua` | the hub window; features can be switched per guild |
| **Professions** | `Modules/Professions.lua` (459), `Modules/ProfSync.lua` (147), `Modules/ProfDirectory.lua` (201), `Data/ProfCatalogForever.lua` | every member's professions and recipes **without opening a window** (`GetProfessionInfo`, `IsPlayerSpell` over a static Forever catalogue), synced between users |
| **Recipes / who can craft** | `Modules/RecipeTracker.lua` (753), `UI/RecipesPanel.lua` (590), `UI/ProfessionsPanel.lua` (749), `UI/CraftFinder.lua` (294) | the recipe browser you asked for; CraftFinder must be re-pointed from the mesh to guild data only |
| Roster, member detail | `UI/RosterFrame.lua` (3 439), `UI/MemberDetail.lua` (1 613), `Modules/RosterColumns.lua`, `Modules/AltRoster.lua`, `Modules/AltAutoDetect.lua`, `Modules/OfficerNotes.lua` | roster with last seen, alts, notes |
| Guild management | `Modules/TrialTracker.lua`, `Modules/GuildManager.lua`, `Modules/ModPresets.lua`, `UI/ManagementPanel.lua`, `Modules/BanList.lua` | trials, leadership tools |
| Raids, loot (tracking only) | `Modules/RaidTracker.lua`, `Modules/LootTracker.lua`, `Modules/Readiness.lua`, `Modules/SpecChecker.lua`, `UI/RaiderPanel.lua`, `UI/AuditPanel.lua` | attendance and loot history |
| Calendar, bulletin, polls | `Modules/Calendar.lua`, `Modules/GameCalendar.lua`, `Modules/Bulletin.lua`, `Modules/Polls.lua`, `UI/CalendarPanel.lua` | in-guild only |
| Plumbing | `Core/*`, `Modules/CommSystem.lua`, `Modules/SyncService.lua`, `Modules/DataCollector.lua`, `Modules/Backup.lua`, `Modules/ExportImport.lua`, `Modules/Search.lua`, `Locales/*` | its own comms (prefix `GUILDOS`, AceComm + ChatThrottleLib, GUILD/RAID/WHISPER) |

## 2. Talks beyond our guild (remove in Phase 9)

| What | Files | Why it goes |
|---|---|---|
| Cross-addon presence mesh "ChehulNet" | `Libs/LibChehulMesh.lua`, `Modules/ChehulNet.lua`, `Modules/ChehulNetWire.lua`, `Modules/Mesh.lua`, `Modules/ChehulGossip.lua` | joins a public chat channel (`JoinChannel`), prefixes `ChehulNet`, `ChehulPing`, `ChehulAlert`, `ChehulTrace`, `ChehulPeers`, `ChehulRelay`, YELL relays; globals `_G.ChehulMesh`, `_G.ChehulNet` shared with other Chehul addons |
| Alliance (cross-guild federation) | `Modules/Alliance.lua` (2 365), `Modules/AllianceSync.lua`, `Modules/AllianceChat.lua`, `UI/AlliancePanel.lua` | prefix `ChehulAlly`, its own chat channel |
| Recruitment over the mesh | `Modules/RecruitBeacon.lua`, `UI/RecruitBeacon.lua`, `Modules/GuildFinder.lua`, `UI/GuildFinder.lua`, `Modules/JoinRequests.lua`, `UI/JoinRequests.lua`, `Modules/CraftNet.lua` | realm-wide broadcasts, guildless boot screen |
| Web companion (guildos.me) | `Inbox.lua` (global `GuildOSInbox`, a file the companion overwrites), `Modules/CompanionExport.lua`, `Modules/CompanionImport.lua`, `UI/WebPanel.lua`, `Modules/Activation.lua`, `Modules/Founding.lua`, `UI/Founding.lua` | its own website and companion; our companion/bot replace it |

## 3. Posts in chat (keep but **off by default**, decision 7)

`Modules/CallToArms.lua`, `Modules/LFGBoard.lua`, `Modules/RecruitmentSystem.lua` (welcome/auto-invite),
`Modules/RecruitScanner.lua`, `Modules/RecruitEngagement.lua`, `Modules/LootMaster.lua`, `Modules/RaidPlan.lua`,
`Modules/NoteCommand.lua` (`!note`), `Modules/ChatTweaks.lua`, `Modules/ConsumableChecker.lua`.

## 4. Overlap with GuildLedger (switch off in the hub)

| Hub module | GuildLedger does it | Decision |
|---|---|---|
| `Modules/GuildChat.lua` | `Chat.lua` + relay (archive, Discord) | off: two addons reading the same club history double the requests |
| `Modules/RosterLog.lua` | `Roster.lua` (sys + diff + guild log) | off; the hub can show GuildLedger's events through the bridge (Phase 10) |
| `Modules/GuildMap.lua`, `UI/GuildMap.lua` | `Map.lua` (decision 6: on by default) | off: theirs shares exact positions only opt-in and uses its own messages |

## 5. Client-specific parts

TBC-only: `Modules/AttunementTracker.lua`, TBC consumables, TMB import. Retail-only: `Modules/MythicPlus.lua`,
`Modules/TradeCouncil.lua`, `UI/TradeCouncil.lua`, `Data/ConsumablesRetail.lua`, `Data/ProfCatalogRetail.lua`.
Client detection: `Core/Compat.lua` (`isAnniversary`, `isRetail`; Forever is "neither"; "never branch on
WOW_PROJECT_ID"). On Forever these hide themselves through the feature registry; Phase 9 checks each tab.

## 6. Libraries, globals, saved data

- Libraries (each keeps its licence file): LibStub, CallbackHandler-1.0, LibSerialize, LibDeflate, ChatThrottleLib,
  AceComm-3.0. LibChehulMesh is removed with the mesh.
- Globals: `GuildOS` (the addon table), `GuildOSDB`, `GuildOSInbox`, `SLASH_GUILDOS1/2` (`/guildos`, `/gos`),
  `BINDING_HEADER_GUILDOS`, `BINDING_NAME_GUILDOS_TOGGLE`, plus the mesh's `ChehulMesh` / `ChehulNet`.
- SavedVariables: `GuildOSDB` (account-wide).

## Decisions (2026-11-14)

Folder `AmazingHub`, title "Amazing Hub", slash `/amazing` · section 3 off by default, officers can enable ·
section 4 off (GuildLedger's chat log, roster log and map are used) · the admin contacts the GuildOS author before
publishing · pack version 0.5.0.

## 7. Patch set for the fork (Phase 9)

1. **Copy** the pinned tree to `addon/AmazingHub/` (name per decision), keep `LICENSE`, add `THIRD_PARTY.md`.
2. **Rebrand by script** (`tools/rebrand-hub.py`), so a newer GuildOS can be pulled again: folder, TOC title,
   global `GuildOS` → hub name, `GuildOSDB` → `<Hub>DB`, `/guildos` `/gos` → hub slash, prefix `GUILDOS` → hub prefix,
   `Interface\AddOns\GuildOS\` media paths, binding names, the visible "Guild OS" brand text (credit stays in About).
   A real GuildOS install next to ours then never sees or disturbs our data.
3. **Remove** section 2 (files, TOC lines, every call into them; replace with no-ops where the UI asks).
4. **Defaults:** section 3 off, section 4 off, retail/TBC tabs hidden on Forever.
5. **TOC:** `## Interface: 16001`, `## OptionalDeps: GuildLedger`, version 0.5.0.
6. **Package:** `dist/Amazing-Forever-Guild-Pack-<v>.zip` with both folders (`GuildLedger/`, `AmazingHub/`).
7. **Tests:** run GuildOS's own Lua tests that survive the removal, plus ours.

Rough size: Phase 9 (fork, rebrand, removal, defaults) is the big one, several sessions; Phase 10 (bridge: hub
shows GuildLedger status, events, map/link toggles) is small.

## 8. Phase 9 result (2026-11-14, built, NOT tested in game)

`tools/rebrand-hub.py` builds `addon/AmazingHub/` from the pinned checkout (refuses another commit unless told).
Never edit the folder by hand; `addon/tests/test_hub.py` rebuilds it and fails on any difference.

**Approach changed from "remove" to "neutralise":** the section 2 modules are called from ~18 files each, so deleting
them means rewriting GuildOS. Instead every way out of the guild is closed at the choke points:

- `Core/Compat.lua`: `Compat.AllowedOutbound` lets addon messages and chat lines go only to GUILD, OFFICER, PARTY,
  RAID, RAID_WARNING, INSTANCE_CHAT, or a WHISPER to a guild member (`C_GuildInfo.MemberExistsByName`, else the
  hub's own roster). `SendAddonMessage`, `SendAddonMessageNow`, `SendChatMessage` check it; `JoinChannel` never joins.
- Every file that called the client's `SendChatMessage` / `JoinChannelByName` / `JoinTemporaryChannel` directly
  (9 files) gets guarded file-locals in front (`Compat.GuardedChat`, `nil`). The client globals are not replaced,
  so Blizzard's chat is not tainted.
- Mesh library: its `Send` refuses everything but guild/group/guild-member whispers; prefix root `AmzHub`.
- Renamed: `GuildOS`→`AmazingHub` (DB, inbox, media paths), `GUILDOS`→`AMAZINGHUB` (prefix, bindings),
  `Chehul<Name>`→`AmzHub<Name>` (mesh globals and prefixes), "Guild OS"→"Amazing Hub", `/amazing` + `/amazinghub`.
  The author credit ("Chehul", GitHub link) stays.

**Defaults:** `OFF_UNTIL_TESTED` = alliance, recruitment, web, founding; modules lootMaster, consumableChecker,
recruitment off; `!note` replies off. GuildChat off; GuildMap off (never sends, ignores positions).
**RosterLog stays on** (changed from section 4): it only reads the game's join/leave line and shares within the
guild, and the trial tracker depends on it for automatic trials.

**Tests:** GuildOS's own 121 checks run on the built tree (`test_upstream_checks`): 101 pass; the 20 that fail are
listed with reasons in `addon/tests/test_hub.py` `EXPECTED_FAIL` (all are the intended blocks or switched-off
features, plus 2 that fail upstream too); a new failure fails the test. `addon/tests/hub_guard.lua` checks the guard
itself (and fails when the guard is removed).

**Recipes need the hub on each member's PC:** a member's professions, skill and known recipes are read on their own
client (no window needed) and shared over guild addon messages / whispers to guildmates (allowed by the guard).
Members without the pack show only their profession names (from the Communities roster), no skill, no recipes.

Not done: physically deleting the dead section 2 files; `.pkgmeta`; hiding the dead tabs (they are off).

## 9. Names, hidden tabs, Discord link box (2026-11-14, after Phase 10)

- **Names (admin's decision):** nothing in the hub says GuildOS, Guild OS, Guild-OS or Chehul any more: the hub is
  "Amazing Hub", its maker "Maupa". GuildOS's website `guildos.me` is called "the guild website" (only in texts of
  switched-off features). The About "Links" popup lists the pack, not the upstream project. The MIT copyright notice
  stays where the licence requires it and no player sees it: `addon/AmazingHub/LICENSE`, the TOC's `X-Upstream`
  line, THIRD_PARTY.md. In upstream's test scripts the test character "Chehul" became "Chaupa" (same length and
  sort position, which the checks rely on). `test_no_upstream_names_left` keeps it that way.
- **Alert popups:** upstream let five named characters (its author's) push popups to every user. The list is now
  empty; renamed names could have been taken by anyone.
- **Hidden tabs** (`addon/hub-extra/PackTweaks.lua`; window, minimap menu and Settings): Achievements, Alliance,
  Recruitment, Web. The Journal stays (in-game data).
- **Off by default** (0.5.1, admin's wish): Raids, Loot, Trials. `AmazingHub.OFF_BY_DEFAULT` in PackTweaks plus a
  rebrand patch in `IsFeatureEnabled`: a tab nobody set is off, also on installs that predate this; a player's
  tick in Settings → MODULES is saved and wins. The background trackers (raid, loot, trial) keep running.
- **Settings** (`addon/hub-extra/SettingsPlus.lua`, 0.5.2): wraps upstream's `RefreshSettingsPanel` without patching
  it. While upstream builds the page, its `UI:CreateHeaderText` calls are recorded; afterwards every recorded
  heading becomes a fold-out ("+"/"-", state in `settings.openSections`, all closed by default); a closed
  section's controls are hidden and everything below moves up by re-anchoring. On the General page a
  **WORLD MAP** section is appended: GuildLedger's map switches (moved from the Ledger tab) and the dot look
  (`GuildLedgerAPI.SetMapLook`), class colours through the game's `ColorPickerFrame:SetupColorPickerAndShow`
  (Blizzard_ColorPickerFrame, Mainline and Classic, forever branch).
- **Discord link box** in the Ledger tab (`GuildLedgerAPI.RequestLink`, same as `/gl link CODE`).
- **Classic look by default** (admin's wish): upstream's "forever" style (the game's own bronze frames, tabs,
  buttons and the game's font) is the default and is called **Classic**; upstream's flat default is **Modern**.
  Settings → Interface style, or `/amazing style classic|modern` (both need a reload). A client without the
  game's art falls back to Modern. Upstream called its bronze style a beta; B14 checks it in game.

### Upstream modules the pack does not use

| Group | Files | State |
|---|---|---|
| Presence mesh | `Libs/LibAmzHubMesh.lua`, `Modules/AmzHubNet.lua`, `AmzHubNetWire.lua`, `Mesh.lua`, `AmzHubGossip.lua` | loaded, every send outside the guild blocked |
| Alliance | `Modules/Alliance.lua`, `AllianceSync.lua`, `AllianceChat.lua`, `UI/AlliancePanel.lua` | tab hidden, off |
| Recruiting network | `Modules/RecruitBeacon.lua`, `GuildFinder.lua`, `JoinRequests.lua`, `CraftNet.lua`, `RecruitScanner.lua`, `RecruitmentSystem.lua`, `RecruitEngagement.lua` + their UI files | tab hidden, off, sends blocked |
| Web companion | `Inbox.lua`, `Modules/CompanionExport.lua`, `CompanionImport.lua`, `Activation.lua`, `Founding.lua`, `Achievements.lua`, `UI/WebPanel.lua`, `UI/Founding.lua`, `UI/AchievementsPanel.lua` | tabs hidden, off |
| Replaced by GuildLedger | `Modules/GuildChat.lua`, `Modules/GuildMap.lua`, `UI/GuildMap.lua` | off |
| Other game versions | `Modules/MythicPlus.lua`, `TradeCouncil.lua`, `UI/TradeCouncil.lua`, `AttunementTracker.lua`, `Data/ConsumablesRetail.lua`, `Data/ProfCatalogRetail.lua` | hidden by the hub itself on Forever |
| Posts in chat (usable) | `CallToArms`, `LFGBoard`, `LootMaster`, `ConsumableChecker`, `RaidPlan`, `NoteCommand`, `ChatTweaks` | off until an officer turns them on |

Deleting the files for good would need edits in ~18 files each; they cost only load time. Left for later.

## 10. Re-pin to GuildOS 1.40.0 (audit, Phase U1, 2026-11-24)

Upstream 1.40.0 = commit 1f9fa9d (checked out at `vendor-ref/GuildOS-140`). Nothing is rebuilt yet: `addon/AmazingHub`
is still built from 1.20.1 (`PINNED`). Open before U2: decision 7 (default: everything that acts for the player
off). Answered 2026-11-24: no H6 marker (10.8), copy the saved data over (10.5).

- Old pin: 1.20.1 = `80883a0` (`vendor-ref/GuildOS`). New: 1.40.0 = `1f9fa9d` (`vendor-ref/GuildOS-140`).
- Patch check: a throw-away script (not in the repo; write it again for the next re-pin). It imports
  `tools/rebrand-hub.py`, runs the same `rename()` after the CRLF→LF step (with `test=True` under `tools/`) on
  every text file, then counts each `PATCHES` anchor in its renamed file. This matches the script's own order: copy and rename first, then `PATCHES`, then
  `PATCHES_ALL`, `EXTRAS` and the shadow guard.
- Against 1.20.1 all 61 patches apply, and `PATCHES_ALL` matches 3×, as expected.

### 10.1 New files since 1.20.1

Nothing under `Modules/` or `UI/` was removed.
- Media: the Spectral fonts, `drop-shadow.tga` and `glow-gold.tga` are gone. IBM Plex Sans Regular, Medium and
  SemiBold arrive with `OFL-IBMPlexSans.txt`, so THIRD_PARTY.md needs the font line updated.
- Many new `tools/*.lua` tests arrive too. They are copied as before and are covered by `addon/tests/test_hub.py`.

| File | Verdict | Reason |
|---|---|---|
| `Core/WhisperQueue.lua` | keep | Paces whispers on Forever (#393). It sends through `Compat.SendWhisper` and the addon queue, so the guard must be on those (10.2). |
| `Data/GroupActivities.lua` | keep | Activity tiles for the Groups tab. |
| `Modules/AddonReminder.lua`, `UI/RemindPanel.lua` | hidden | Leadership > "Without GuildOS" whispers members who do **not** run the addon. That breaks the pack rule. |
| `Modules/AllianceLink.lua` | hidden, and must not start | It starts for every member with no feature switch (`MODULE_START` in `Core/Core.lua`): see 10.2 A1. |
| `Modules/AltDeparture.lua`, `UI/AltDepartureDialog.lua` | keep | Officer dialog when a main leaves: new main, unlink or ban. Data only. "Remove alts" queues them in Bulk actions. |
| `Modules/AltSync.lua` | keep | One synced entry per alt link (#424). Fixes the "an old officer wipes every link" fault (10.7). |
| `Modules/Birthdays.lua` | keep but off | Calendar, Profile and roster column are fine. The /g announcement is already off upstream (`birthdayAnnounce`). |
| `Modules/BulkActions.lua`, `UI/BulkPanel.lua` | keep but off: hide the `bulk` sub-tab | Promote, demote or remove by rules. On Forever it only prints the line to type, but it is a mass rank and removal tool. |
| `Modules/CraftOrders.lua`, `UI/CraftOrdersPanel.lua` | keep | Crafts tab order queue (W19). Trade and mail fill only on a click. "Ask them" only opens `/w name` in the chat box. |
| `Modules/Discipline.lua`, `UI/WarnDialog.lua` | keep but off | Warn = a whisper on click plus a record. Proposal: record without the whisper (10.2). |
| `Modules/Groups.lua`, `UI/GroupsPanel.lua` | keep, change two defaults | New Groups tab (on). Its guild line and auto-invite defaults are on upstream (10.2 A3). |
| `Modules/GuildBank.lua`, `UI/GuildBankPanel.lua` | keep | Bank tab (W22). Read and share is passive. Organize moves items only on a click. |
| `Modules/GuildBankCleanup.lua` | keep but off: hide the `cleanup` sub-tab | Withdraw, sell and deposit gold, all clicked, officers only. |
| `Modules/GuildBankPlan.lua` | keep | Organize plan (pure). |
| `Modules/GuildRules.lua` | keep | Rules text written by officers, read by members. Only a warning names a rule. |
| `Modules/LootCouncil.lua`, `UI/LootCouncil.lua` | keep (Loot tab is off by default) | Council voting over addon messages in raid. |
| `Modules/LootRule.lua`, `UI/LootWindow.lua` | keep (Loot off by default) | One Loot window: Rule, Accounts, Lists, History (1.26). It replaces the loot, DKP and wishlist views in FeaturePanels. |
| `Modules/MemberHistory.lua` | keep | Join and leave history, Joined column (W21). Officers only. |
| `Modules/MemberMarks.lua`, `UI/MarksPanel.lua`, `UI/OfficerSheet.lua` | keep | Nicknames, safe list and sheets for officers. `Compat.OfficerAddonChannel()` is nil on Forever, so they stay on the officer's own client there. |
| `Modules/ModAlerts.lua`, `UI/ModAlerts.lua` | keep but off | Officers' chat alerts. `PREF_DEFAULTS.enabled = true`. Its login catch-up reads the club history (`Compat.GuildChatHistory`), which makes it a second reader next to GuildLedger (section 4). |
| `Modules/ModFlood.lua`, `Modules/Newcomer.lua` | keep but off (with ModAlerts) | They feed the same alert panel. They send nothing. |
| `Modules/NoteDates.lua` | keep | Writes join dates into notes. On Forever `Compat.CanWriteNote` is false, so it lists the text to type. |
| `Modules/SiteLoot.lua` | hidden (inert) | Loot data from guildos.me. Used only when a site raid is imported. |
| `UI/SettingsPanel.lua` | keep (rework our files) | Settings in six sub-tabs: profile, interface, chat, modules, rules, data. The Settings part of `UI/FeaturePanels.lua` moved here (it fell from 4622 to 2678 lines). |

### 10.2 Things that act for the player

Upstream defaults are what a fresh install gets. "Guard" means our `Compat.AllowedOutbound` (patch #0–#3) and the
shadow head. The 1.40 shadow pass finds direct `SendChatMessage` in 11 module files: AddonReminder, AllianceChat,
CallToArms, ConsumableChecker, Discipline, GuildChat, LootMaster, RecruitmentSystem, RecruitScanner,
GuildBankPanel and Probe.

**A. Blockers: these get past the guard in 1.40 and need new patches.**

| # | File / entry point | Upstream | Proposal |
|---|---|---|---|
| A1 | `Modules/AllianceLink.lua` | Automatic, every member. | Patch: `function Link:Initialize()` + `do return end -- Amazing Hub: no alliance (section 2)`. |
| | | On `GUILD_ROSTER_UPDATE`, `Link:ReadGuildMasterNote()` takes a `GOS=TAG:key` code from the GM's public note. `EnsureJoined` → `Compat.JoinPrivateChannel("GOSA"..tag, key)` joins a hidden password channel, and `RemoveChannelFromFrames` hides it. | |
| | | `Compat.HookChatSend` → `Link:OnPlayerChat` copies **every /g line the player types** into that channel (`Compat.SendChannelMessage`), so it reaches other guilds. | |
| | | `Link:_WriteNote` / `_RepairNote` write the GM's public note (Anniversary only). | |
| | | Any code in the GM's note, put there by anyone with note rights, turns this on. | |
| | | I found no `GetGuildInfoText` read in `Modules/Alliance*.lua`. The changelog's "guild info" seems to mean the GM's note. | |
| A2 | `Core/Compat.lua`: `SendWhisper`, `SendChannelMessage`, `JoinPrivateChannel` (all new) | They call `C_ChatInfo.SendChatMessage` / `JoinTemporaryChannel` directly inside Compat. Compat is `SHADOW_SKIP`, and our patches guard only `SendChatMessage`, `SendAddonMessage(Now)` and `JoinChannel`. | Three patches: |
| | | | `SendWhisper`: `if not Compat.AllowedOutbound("WHISPER", target) then return false end` |
| | | | `SendChannelMessage`: `do return false end` |
| | | | `JoinPrivateChannel`: `do return false end` |
| | | | Also add the new names to the guard tests (`test_raw_addon_sends_only_in_guarded_places`). |
| | `Compat.SendGuildStream(streamId, text)` (already in 1.20.1) | `C_Club.SendMessage`. Guild only. It is used only by `GuildChat`, which we switch off. | No change. |

**B. New or changed actions.**

| # | What | File / entry point | Upstream default | Proposed default | How to switch it off |
|---|---|---|---|---|---|
| B1 | Group line in /g, said again every 10 min | `LFGBoard:_SayInGuild` ← `Groups:Create(…, toGuild)`, `Groups:Tick` (`ANNOUNCE_EVERY = 600`), `Groups:PostNow` | on: `LFGBoard.DEFAULTS.postToGuild = true` pre-ticks the box | off | Patch `LFGBoard.DEFAULTS`: `postToGuild = false`. Existing installs already have `true` saved in `db.lfgPrefs` (also in 1.20.1), so H6-style one-time marker code is needed to reset it once. |
| B2 | Auto-invite whoever asks, plus "Whisper me inv" in the line | `Groups:_OnInviteWhisper` (~L642), request path ~L712, `Compat.InviteUnit` | on: `DEFAULTS.autoInvite = true` | off | Same patch: `autoInvite = false`. The key is new, so the default reaches existing installs too. |
| B3 | Ready check, convert to raid, invite from the queue | `Groups:ReadyCheck` / `ConvertToRaid` / invite buttons | click | keep | – |
| B4 | Birthday line in /g, once a day per member | `Birthdays:_Say` (~L658) → `Compat.SendChatMessage(…, "GUILD")` | off (`birthdayAnnounce`) | off | Already off. |
| B5 | Birthdays into the game calendar | `GameCalendar` → `Compat.CalendarCreateGuildAnnouncement` | click, officer | keep | – |
| B6 | Whisper reminder to members without the addon | `Reminder:Remind(key)` → WhisperQueue / `Compat.SendWhisper` | click, officer | **hidden** | Patch the `{ key = "remind", … }` entry out of the Leadership `SUBS` list in `UI/ManagementPanel.lua` (like #51 Engagement), and `Reminder:Remind` → `do return false end`. |
| B7 | Warn whisper | `Discipline:Warn` → `Compat.SendWhisper` (L534); `UI/WarnDialog.lua` | click, officer | off (record only) | Patch L534 so the whisper is not sent, or let A2's guard decide (it only lets whispers to guild members through). Admin decides. |
| B8 | Bulk promote, demote, remove | `BulkActions:Arm` / `_TypedNext` → `Compat.GuildRankCommand`. On Forever `Compat.SecureGuildMacro()` is false, so it only prints "/gpromote X" to type. | per click, officer | hidden | Patch the `{ key = "bulk", … }` entry out of the Leadership `SUBS`. |
| | | | | | Note: the `/click AmazingHubBulkNext` macro path has no mouse-down, so `PackTweaks`' quiet Print would also hide the line to type. |
| B9 | Ranks arrows and Suggestions > Promote | `GuildManager:Promote/Demote/Kick` → `_protectedNotice` (opens the game's panel) | click | keep, with our "only below your rank" patches | #47 and #50 apply; #48/#49 need rework (10.3). |
| B10 | Join dates into public or officer notes | `NoteDates` L336 → `Compat.SetGuildPublicNote` / `SetGuildOfficerNote` (the latter is new) | click, officer. Forever: refused (`CanEditPublicNote`/`CanEditOfficerNote` are false off Anniversary), so only the text is shown. | keep | – |
| B11 | Alliance code into the GM's note | `AllianceLink:SetCode` / `_RepairNote` | see A1 | off | A1. |
| B12 | Bank organize (move items) | `GuildBank:SortStep` → `Compat.GuildBankPickup/Split` | click, needs tab rights | keep | – |
| B13 | Bank cleanup: withdraw, sell at a vendor, deposit gold | `Cleanup:WithdrawMarked` / `WithdrawStep` (`Compat.GuildBankAutoStore`), `SellOut` / `SellStep` (`Compat.UseContainerItem` while `MERCHANT_SHOW`), `DepositOwed` (`Compat.DepositGuildBankMoney`) | click, officer | hidden | Remove `"cleanup"` from the `subs` of the `bank` feature (patch `UI/Features.lua`), or a `PackTweaks` wrap that empties `Cleanup.WithdrawMarked`. |
| B14 | "Announce in guild chat" (bank needs) | `UI/GuildBankPanel.lua` ~L907 `SendChatMessage(text,"GUILD")` | click | keep | – |
| B15 | Craft delivery by trade or mail | `CraftOrdersPanel` → `Compat.InitiateTrade`, `ClickTradeButton`, `SetTradeMoney`; `CraftOrders` → `FillSendMail`, `ClickSendMailItemButton` | click | keep | It fills the window; the player still presses Trade or Send. |
| B16 | Start raid: invite, convert, arrange groups | `CompanionImport` ~L1368–1642 | click, raid owner, site raid only | inert | The web feature is hidden, so there is no site plan. |
| B17 | Welcome lines (now several, drawn at random) | `Recruitment:SendWelcomeText` → `SendChatMessage(…,"GUILD")` | `welcomeEnabled = true`, but the module is gated by feature `recruitment` | off | Patch #8 (`recruitment = false`) still applies. Also set `welcomeEnabled = false` as a second guard. |
| B18 | Version notice ("a newer version is out") | CommSystem version check | prints | quiet | `PackTweaks` Print gate. |
| – | Loot master and consumable lines | unchanged | – | – | Patch #8 still applies. |

No module calls `GuildLeave`, `GuildUninvite` or `SetGuildInfoText` on its own. `SetGuildInfoText` and
`GuildSetMOTD` are only in `GuildManager:SetGuildInfo/SetMOTD` (Leadership > MOTD, a click). On Forever the MOTD
opens the game's panel.

### 10.3 The patch list against 1.40.0

Measured with `check.py`:
- **45 of 61 apply.** The 16 that fail are FeaturePanels 9, PointsPanel 2, ManagementPanel 2, Core/Config 1,
  RecipeTracker 1 and ProfessionsPanel 1, which **confirms the plan**.
- **Correction:** the `PATCHES_ALL` entry on `tools/style.lua` now finds **5** anchors instead of 3. Two new test
  blocks were added, around L445 (pixel edges) and L498 (screen parts #371). Decide whether those blocks also
  assume the flat look and set `times=5`, or anchor the three old ones separately. Run the Lua test to see.
- Also blocking: the new test `tools/whisper-not-found.lua:275` contains the upstream author's GitHub name
  (`danielcosta42/chehulnet` in a comment). `OLD_NAMES` stops the build there, so it needs a patch.
  The `GuildOS.toc` header lines are replaced by `rewrite_toc` (check that `X-Website` sits in that header).
  `UI/SettingsPanel.lua`'s match goes away with #16.

The 45 that apply:
- #0–#14: guards, mesh, alerts, Core defaults, NoteCommand, GuildChat, GuildMap.
- #17–#34: test fixture and Style.
- #36, #42–#45, #47, #50–#55.

Applying is not always enough:
- #7 `OFF_UNTIL_TESTED` lists `alliance`, but `AllianceLink` has no feature gate (A1).
- #12–#14: Settings still offers the minimap dots through `GuildMap:IsMinimapDots` (#15 below).

| # | Patch | Result | What changed upstream; new target |
|---|---|---|---|
| 15 | no minimap-dots switch | rework | Moved to `UI/SettingsPanel.lua` `PAGES.interface`. Target `    if AmazingHub.GuildMap then\n        F:Check(L["Show guildmates in your zone on the minimap"]` → `if false and …` (1 match). |
| 16 | About links | rework (file only) | Same text, now in `UI/SettingsPanel.lua` `PAGES.data` (1 match). |
| 35 | hub version | rework | `AmazingHub.VERSION           = "1.40.0"  -- kept in sync…`. Target `AmazingHub.VERSION           = "1.40.0"`. |
| 37 | tooltip: 5 crafters at most | **no longer needed** | 1.34.0 `RecipeTracker.TooltipPick`: 3 names, online first, "+N more" (`AppendCrafters`). Drop it. |
| 38 | wishlist: Import from Discord | rework | Site-held lists added `siteLine`/`siteBtn` after the Sync button. Target `    f.syncBtn = syncBtn\n` in `UI/FeaturePanels.lua` (1). Move the button left of `syncBtn`. `AddToWishlist` now refuses site lists (`ListIsFromSite`), which is harmless. |
| 39 | DKP headings as sort buttons | rework | `UI/PointsPanel.lua` now builds `heads[col.key]` from `STAND_COLS` (keys `rank,name,cur,earned,spent`) and calls `SetText(TITLES[key])` on every redraw inside `refresh()`. Insert after that `for _, col in ipairs(STAND_COLS)` loop: `TS.Headers("dkp", {{heads.name,"name",TITLES.name},{heads.cur,"current",TITLES.cur,true},{heads.earned,"earned",TITLES.earned,true},{heads.spent,"spent",TITLES.spent,true}}, refresh)`, only when `not account`. |
| 40 | DKP sorted | rework | Target `            list = inScope(P.GetStandings, P)\n` (1). Append `TS.Apply("dkp", list, TS.POINTS)`. Rows still have `name,current,earned,spent`. The `#` column becomes a position. |
| 41 | Professions sorted | rework | Old anchor gone: the recipes branch now inserts a detail row (`UI.WithDetail`). Sort `out` **before** `if UI.WithDetail then` (recipes), and after `state.results = state.line and D.MemberRows(state.line) or {}\n            state.detailAt, state.detailRows = nil, nil\n` (crafters). Sorting after `WithDetail` would move the detail row. |
| 46 | ChatTag settings | rework | Now `PAGES.chat`. Target `setCt("altShort"),\n        { indent = 2 * SUB_INDENT, enabled = function() return annotating() and ct().altTag ~= false end })\n` (1). Insert `if AmazingHub.ChatTag then AmazingHub.ChatTag.BuildForm(F, SUB_INDENT) end`. Needs a Form-based builder (10.4). |
| 48+49 | Ranks arrows only where allowed | rework, now one patch | The Ranks list is a virtual list. Target `        row.downBtn:SetShown(canDemote)\n        row.upBtn:SetShown(canPromote)\n` in `fillRow` (1) → `…SetShown(canDemote and AmazingHub.GuildManager:MayDemote(m.rankIndex))` / `MayPromote`. `GM` is not in scope there. |
| 56–58 | Loot equity texts | rework (file only) | Moved to `UI/LootWindow.lua` (1 each; `L["dry"]`/`L["well-fed"]` match once there). |
| 59+60 | UI scale buttons | rework | Slider now in `PAGES.interface` inside `scaleRow`, placed by `F:Row(scaleRow, { wide = true, place = … })`. Replace the block from `    local scale = CreateFrame("Slider", "AmazingHubScaleSlider", scaleRow, …)` to the end of its `F:Sync(...)` with five `UI:CreateButton(scaleRow, …)` and a `F:Sync(markScale)`. Adjust the `place` function, which reads `scale`. |

New patches needed (besides A1, A2, B1, B2, B6–B8, B13, B17):
- `CommSystem.LEGACY_ALT_MAX = "1.38.0"`: set it to our last pre-AltSync version, e.g. `"0.6.99"`, as 10.7 explains.
- `PackTweaks` `DESC.loot` text (10.4).

### 10.4 Our own files (`addon/hub-extra`)

The script now copies them from `addon/hub-extra/`. CLAUDE.md section 4 still says `/tools/hub-extra/`.

| File | Uses upstream | Still there in 1.40? | Rework |
|---|---|---|---|
| `TableSort.lua` | `GetSetting` / `SetSetting`, `CreateFrame` on a font string's parent; `Modules/Points` `GetStandings` rows, `ProfDirectory` rows | yes, same row fields | Only patches #39–#41 (10.3). |
| `ChatTag.lua` | `DataCollector:GetBroadcastData` (#43 applies), `CommSystem:BroadcastMyData`, `ChatTweaks` `own` (#44, #45 apply), `UI:CreateCheckbox/CreateText` | yes | Add `ChatTag.BuildForm(F, indent)` built from `F:Check` / `F:Field`, and drop the y-offset builder. The officer nickname (#429, `cfg.nick`, from `MemberMarks:Nick`) comes before the level. Our own tag still takes the alt-tag slot, and both can show. |
| `WishImport.lua` | `AmazingHub.WishlistFrame`, `RefreshWishlistFrame`, `Wishlist:AddToWishlist`, `UI:StylePopup` | yes (FeaturePanels L2035/2054; `Helpers:StylePopup`) | Patch #38 anchor only. The Lists sub-tab of the Loot window is another way in; the button is only in the popup. |
| `LedgerPanel.lua` | `UI:RegisterFeature{id="ledger",order=96,build}`, `UI:CreateScrollFrame/CreateText/CreateButton`, `ApplyFont`, `SafeCall` | yes | None expected. Check the tab bar width with the two new tabs, Bank and Groups. |
| `SettingsPlus.lua` | Wraps `AmazingHub:RefreshSettingsPanel(content, category)` and records `UI.CreateHeaderText` during it. Appends Messages, World map and Collector when `content.__settingsCat == "general"`, then re-anchors to fold. | **shape changed** | See below. |
| `PackTweaks.lua` | `UI:GetFeature(id).condition`, `HIDDEN_FEATURES`, `OFF_BY_DEFAULT` (patch #9 applies), `AmazingHub.Print`, `SlashCmdList.AMAZINGHUB`, `UI.CreateButton/CreateCheckbox` | yes | See below. |

**SettingsPlus: what changed.** It is now `RefreshSettingsPanel(content, key)` in `UI/SettingsPanel.lua`:
- It builds a `Form` once per content and "shape". `PAGES[key](F)` adds rows, `F:Section(title)` makes a plain
  font string row (no `CreateHeaderText`), and `F:Layout()` re-anchors every row on each refresh and resize.
- There is no "general" key any more (`OLD_KEYS.general = "profile"`).
- So nothing is recorded, our sections are never added, and any re-anchoring is undone at the next Layout.

**SettingsPlus: rework.**
1. Wrap `RefreshSettingsPanel` and keep the returned `F`.
2. Only when `F ~= content.__amzForm` (a fresh build), append our rows through the Form API:
   `F:Section("Chat messages")` + `F:Check(...)` on `key == "chat"`, the World map on `"interface"`, and the
   Collector on `"profile"` (or `"data"`). Then `F:Refresh()`.
   Our colour and shape pickers become rows with `F:Row(frame, { h = … })` or `{ place = fn }`.
3. Fold: mark each section's rows and give them `shown = function() return open[title] end`, so Form's own Layout
   hides them. Take the headings from the Form rows: wrap `getmetatable(F).__index.Section` once, to tag the
   rows that follow, and force a rebuild with `content.__settingsShape = nil`.
4. Upstream's `shapeOf(key)` rebuilds the modules and chat pages when officer state or modules change. Our rows
   must be added again then, which comes for free when we key on `F`.
5. Patch #46 moves into the chat page (above). `Form`, `PAGES` and `newForm` are file-locals: work only through
   the returned `F`.

**PackTweaks: rework.**
1. `HIDDEN_FEATURES`: achievements, alliance, recruitment and web still exist.
   - `achievements` is now `tab=false, opens={"guild","achievements"}`. `IsFeatureAllowed` honours `condition`,
     but check that the Guild hub's sub-tab bar asks it.
   - `trials` (`opens` recruitment) disappears with Recruitment.
2. Upstream's Leadership sub-tabs are a file-local `SUBS` list, not features, so hiding them needs patches:
   `bulk`, `remind` and maybe `alerts`/`alertrules` (as #51). The same goes for the `bank` feature's
   `"cleanup"` sub.
3. `OFF_BY_DEFAULT` (raids, loot, trials): `loot` is now "one Loot window for every member", and the `dkp` and
   `wishlist` features open its sub-tabs, so they vanish with it.
   - `DESC.loot` ("officers: loot history") is out of date. Suggest "Loot window: rule, points, lists, history".
   - Decide whether `groups` belongs in `OFF_BY_DEFAULT`.
4. Print gate: it still fits `GuildOS:Print` (Core.lua L844) and `SlashCmdList["AMAZINGHUB"]`. Gap: the bulk
   `/click` macro (B8).
5. The `CreateCheckbox` wrap still covers Settings, because `Form:Check` uses `UI:CreateCheckbox` and
   `.checkbox`.

### 10.5 Saved data (`AmazingHubDB`)

- The key is still `guildName.."-"..GuildRealm()` (`ResolveGuildDB`, byte-identical). `_dbVersion` 2 is a no-op
  for us.
- **1.34.1 (#394):** `GuildRealm()` now uses `RealmName()`. When the client answers `""` (Forever since 21/11) it
  falls back to the realm saved in `GuildOSDB.accountChars` (`rememberedRealm`, Utils.lua ~L248). Effects:
  - Our current 1.20.1 fork has probably been writing to `AmazingHubDB["Guild-"]` since 21/11. That is unverified
    for our install; check the file. The data from before 21/11 is under `"Guild-<realm>"`.
  - The 1.40 fork goes back to `"Guild-<realm>"`, so the old data reappears.
  - What was written under `"Guild-"` since then is **not merged**. It stays orphaned in the file.
  - Member keys become `Name-Realm` again (`GetPlayerKey`). `LocalizeStoredMemberTables` is skipped because
    `storedKeysLocalized` already equals the realm.
  - Going back to the old fork reads `"Guild-"` again, so the switch is one-way in practice.
- **Decision (admin, 2026-11-24): copy the data over.** U2 adds a one-time step in our own code (hub-extra), run
  before `ResolveGuildDB`, guarded by a marker (`AmazingHubDB._packRealmMerged = 1`): for every key
  `"<guild>-"`, merge it into `"<guild>-<realm>"` (realm from `GuildOSDB.accountChars`, as upstream does).
  No target yet → move it as a whole. Both present → keys missing in the target are copied; on a conflict the
  `"<guild>-"` value wins (it is the newer one); array-like lists (loot history, logs) get the entries the target
  does not have yet, appended. Member keys `Name` are copied to `Name-Realm` only where that key is free.
  The `"<guild>-"` key stays in the file (nothing is deleted), so the copy can be checked. Tests with lupa.
- One-time, additive migrations (nothing pre-existing is deleted; `DB_DEFAULTS` fills only missing keys):
  - `AltSync:Migrate` builds `db.altSync = {v=1, links, rev}` from `db.altLinks`, with `legacy=true, ts=0`. From
    then on `altLinks` is a view rebuilt from it, so edits made by an old fork after a downgrade are overwritten.
  - `MemberHistory:Migrate` (`memberHistoryMigrated`).
  - `CoreManager:MigrateLink/MigrateGuests` (site guilds only).
  - `GuildBank` `ledgerV` (new data).
  - `LootRule:FromLegacy` builds the rule from the old settings on the fly.

### 10.6 `companion/guildledger/loot.py`

It reads `points`, `cores[c].points`, `lootHistory`, `guildWishlists` and `raidTracker.sessions`
(`rows_from_hub`, loot.py:146–213). **All are still written at the same path with the same fields:**
- `points`: log entries gain `rk`. New `accounts`, `queues` and `weekly` are not read. `cdelta` counters never go
  into `log`.
- Since 1.27 a raid group may use its parent roster's pool, so its own `cores[c].points` can be empty or stale.
- `lootHistory`: new `why`, `awarded`, `from`, `instanceID`, `playerKey`, `count`.
- `raidTracker.sessions`: new `difficulty`, `raidId`, `groupTag`.

Risk from 10.5, which exists already with the current fork:
- The file can hold `"Guild-<realm>"` and `"Guild-"` for one guild. `match_guild` maps both to one club.
- `_merge_standing` and `_merge_wishlist` keep the first one seen, possibly the stale orphan.
- Raid `players` keys differ ("Name-Realm" vs "Name").
- Proposal (Phase G or X): per guild, take the db with the newest data, or skip keys ending in `-`.

### 10.7 Mixed versions (pack 0.6.0 hub next to a 1.40-based hub; same renamed prefixes)

- **Transport.** CommSystem envelope, LibDeflate and LibSerialize are unchanged. Unknown message types fall
  through the `msgType` chain silently on both sides.
- **SyncService.** `PROTOCOL_VERSION` is 2 on both. An unknown domain has no handler, so it is ignored. The old
  hub ignores `alt`, `gbank*`, `craftorder`, `marks`, `osheet`, `discipline`, `reminder`, `modalert`,
  `birthday` and `allylink`. New `guildcfg` actions fall into the old `OnOfficerMaxRankSync`, which bails out
  without `data.max`. **No Lua errors expected** (not run in game).
- **Alt links.**
  - The old hub sends the whole table (`AL`) and **replaces** its own `db.altLinks` with what it receives.
  - The new hub only merges an old `AL`: it adds new alts as unconfirmed, never removes, and sets `legacyGone`.
    New clients sync per link in domain `alt`.
  - The new hub sends `AL` (mark `{v=2}`) only while it hears legacy clients. The old hub then takes the new
    hub's `LegacyView`, as intended. Old officers still wipe old members' tables, as today.
  - **Fork pitfall:** "legacy" is `version <= LEGACY_ALT_MAX ("1.38.0")` (`CommSystem:_AfterLegacyAlt`), and our
    VERSION is `0.6.x`. So every fork client, new ones too, counts as legacy and `AL` never stops. It is harmless
    but wasted traffic; patch `LEGACY_ALT_MAX` (10.3).
- **Professions.** `RC` (`RecipeTracker:HandleIncoming`) is identical and `BC` only adds a version check. Craft
  orders are invisible to the old hub. **No loss.**
- **Points.** There is **data damage on the old side**:
  - A new snapshot or delta for a core the old hub does not have lands in its guild pool (old
    `CoreManager:GetPointsDB` falls back to `db.points`) and can replace `db.points.standings/config`.
  - The old hub also ignores `cdelta`, `qset` and EPGP `acct`.
  - This only matters with the Loot tab in use (off by default). Officers should update together.
- **Officer notes.**
  - The new hub sends `ON`/`OA`, `osheet` and `marks` over the OFFICER channel only, and on Forever that channel
    is nil (they stay on the officer's own client).
  - The old hub accepts `ON`/`OA` only over GUILD, so old officers stop getting new officers' notes.
  - The new hub still reads the old `ON` over GUILD, but not the old `OA`.
- **Alliance:** the protocol was rebuilt in 1.25. It is off in both (A1); interop not traced.

### 10.8 H6: can a self-claimed alt link be told apart from an officer's?

**No.** 1.40 `Modules/AltSync.lua`:
- Entry: `{ main = mainKey, author = <officer name>, ts = GetServerTime() }`. The tombstone is
  `{ removed = true, author, ts }` (`AltSync:Write`). The revision is kept apart in `s.rev[alt]`.
- On the wire: `{ k = alt, m = main, x = removed, a = author, t = ts, r = rev }`, domain `alt`.
- `AltSync:Write` returns 0 unless `IsOfficer()`.
- A member's claim travels as `SELF_ALT` (`{main, alts}` / `{unlink=…}`), waits in the account-wide
  `altPending[sig] = { main, alts, guild, ts }`, and is applied by an online officer's
  `AltAutoDetect:HandleSelfClaim` → `AltSync:Commit` → `Write`. So `author` is **the applying officer** and `ts`
  is when it was applied.
- The only other marks are `legacy = true` (from before #424, no author, revision 0) and `legacyGone`. Neither
  says who claimed the link.
- To show "(alt of …)" only for self-claimed links, we need our own field or record. Options:
  - our own `altClaimed[alt] = true`, set where `HandleSelfClaim` commits, synced by us;
  - or treat "the alt's own account sent the `SELF_ALT`" as the test on the member's own client only.
  
  That is an admin question (decision 8).
- **Decision (admin, 2026-11-24): both count the same.** No marker of our own. H6 shows the member's own tag text
  when set, else "(alt of …)" for every known alt link, whoever entered it.

### 10.9 W18: upstream's 1.26.1 fix

- Commit `e06b1b4` (#353): "o pedido de vincular não volta para um grupo já vinculado, e vincular vincula".
  - Files: `Modules/AltAutoDetect.lua` (pure `PlanGroup`, `DetectOwnAlts` ~L98, `LinkOwnAlts` returns the number
    changed) and `Modules/CommSystem.lua`.
  - Follow-ups: `52e1273`, `6d29ed5`, `8048c55`, `e4ef977`, `f6a487f`. The rework in #424 is `730b1b7`,
    `a1e2f18`, `478e666`.
- **"Already linked":** every own guild character resolves to `altLinks[key] or key`. One root (`nRoots == 1`)
  means no prompt, whoever the main is. 1.20.1 demanded that every alt point at the highest-level character
  (old AltAutoDetect L71–78).
- **Saved keys:**
  - "Not now" → `GuildOSDB.altDeclined[GroupSignature(group)] = true` (account-wide; a changed group asks again).
  - Once per session → `AltAutoDetect._prompted`, not saved.
  - A waiting claim → `GuildOSDB.altPending`.
  - `/gos myalts` (`PromptNow`) ignores both.
- **"Link links with no officer online"** holds only on the member's own client (`PlanGroup` + `Overlay`). Other
  clients see the link once an officer hears it: `ResendPending` at each login, and `OnOfficerLinks` once per
  session.
- **The highest-level-as-main fault (plan 2.5) is partly fixed:**
  - Fixed: an existing main is kept.
  - Still there: a new group still gets `group[1]`, the highest level. The prompt offers only Link / Not now; the
    member can change the main afterwards with `SetOwnMain`.

### 10.10 What blocks a rebuild (U2)

1. A1 and A2: without these patches, a GM note holding a `GOS=` code sends the guild's /g to other guilds, and
   `Compat.SendWhisper` bypasses the guard. They must be in before anything ships.
2. 16 reworked or dropped patches (10.3), `PATCHES_ALL` style.lua 5× instead of 3×, and the author name in
   `tools/whisper-not-found.lua`.
3. Rework `SettingsPlus.lua` (Form API) and `ChatTag.BuildSettings`. Until then our Settings sections (chat
   messages, map, collector) silently disappear: there is no error, just nothing shown.
4. Admin decision 7 on: B1/B2 defaults, B6/B8/B13 hidden, B7 whisper, ModAlerts off, Groups tab on or off.
   (H6 claim marker: not needed, decision 8 answered 2026-11-24.)
5. Then: `PINNED`, the TOC `X-Upstream` line, THIRD_PARTY (IBM Plex), `EXPECTED_FAIL` in `addon/tests/test_hub.py`,
   and guard tests for the new Compat senders.

### 10.11 U2 done (2026-11-24, branch `repin-140`)

The hub is built from 1.40.0 (`PINNED = "1f9fa9d"`, hub version 0.7.0): 87 patches, 3 counted (`PATCHES_ALL`).
- **A1/A2:** `AllianceLink:Initialize` returns at once; `Compat.SendWhisper` goes through `AllowedOutbound`
  (guild members only); `Compat.SendChannelMessage` and `Compat.JoinPrivateChannel` do nothing.
- **Decision 7 (admin, 2026-11-24): hidden in the CurseForge pack, available in the admin's own install.** The
  new addon folder `addon/AmazingHubDev` (linked by `tools/install.ps1`, never packed by
  `tools/package-collector.ps1`) sets the global `AmazingHubDevFeatures = true`; the hub lists it under
  `OptionalDeps`, so it loads first. Without it:
  - Groups: `postToGuild` and `autoInvite` read as off (`LFGBoard:Pref`, `Groups` `pref`), `_SayInGuild` says
    nothing, both switches are hidden. Defaults are off in both cases.
  - Leadership: the sub-tabs `bulk`, `remind`, `alerts`, `alertrules` are taken out of `SUBTABS`;
    `Reminder:Remind` refuses; `/amazing bulk` and `/amazing altgroup` say "Not available"; the member window
    has no "Promote/Demote alts".
  - Bank: `AmazingHub.GuildBankCleanup` is not set (the sub-tab is absent, the bank bar has no Cleanup button).
  - Warn: always recorded only (`Discipline:Warn` returns "silent"); the window hides the whisper box.
  - Chat alerts: `ModAlerts`, `ModFlood`, `Newcomer` are not set, so nothing starts and nothing syncs.
  - Also, for everybody: `RecruitmentSystem` `welcomeEnabled = false`.
- **Decision 8:** both kinds of alt link count the same; no marker (10.8).
- **Saved data (10.5):** `addon/hub-extra/PackMigrate.lua`, called from `ResolveGuildDB` before the realm key is
  used: once per guild it copies `"<guild>-"` into `"<guild>-<realm>"` (newer wins, lists get the missing
  entries, member keys get the realm); nothing is deleted. The companion skips the stale `"<guild>-"` key when
  the realm key exists (`loot.hub_guilds`).
- **Reworked:** #15, #16, #35, #38–#41, #46, #48+#49, #56–#60 as in 10.3; #37 dropped. `LEGACY_ALT_MAX` = 0.6.99.
  `SettingsPlus.lua` rebuilt on upstream's Form (our sections on the Chat, Interface and Profile pages; fold-out
  through the rows' `shown`); `ChatTag.BuildForm`. Upstream's new `specs/` folder is not copied; its JSON test
  data is renamed like the Lua.
- **Tests:** `addon/tests/test_hub.py` runs upstream's checks; `DEV_ONLY` lists the ten that must fail without
  the developer addon and pass with it. New expected failures are listed with their reasons (`EXPECTED_FAIL`).
  `hub_settings.lua` tests our sections on a fake Form; a test covers `PackMigrate`.
- **C3 (item catalogue):** `addon/hub-extra/Data/ItemCatalog.lua` + `ItemCatalog.lua` fill `Wishlist.catalog` on
  Forever (5,217 items), so the wishlist box and search find every wishable item by name.
- **Open:** in-game round U3 (docs/dev/INGAME_TESTS.md "Hub round U3"). Then H1–H10.
