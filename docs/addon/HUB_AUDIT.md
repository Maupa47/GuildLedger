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
- **Hidden tabs** (`tools/hub-extra/PackTweaks.lua`; window, minimap menu and Settings): Achievements, Alliance,
  Recruitment, Web. The Journal stays (in-game data).
- **Off by default** (0.5.1, admin's wish): Raids, Loot, Trials. `AmazingHub.OFF_BY_DEFAULT` in PackTweaks plus a
  rebrand patch in `IsFeatureEnabled`: a tab nobody set is off, also on installs that predate this; a player's
  tick in Settings → MODULES is saved and wins. The background trackers (raid, loot, trial) keep running.
- **Settings** (`tools/hub-extra/SettingsPlus.lua`, 0.5.2): wraps upstream's `RefreshSettingsPanel` without patching
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
