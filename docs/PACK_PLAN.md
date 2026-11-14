# Combined guild addon — build instructions for Claude Code (Phases 8–14)

Revision 2, 2026-11-13 (decisions and corrections in section 0; they override the rest).
Revision 1, 2026-11-13. Extends `CLAUDE.md`; it does not replace it.
Working names: package **Amazing**, hub folder **AmazingHub** (rename freely, see section 3).

You (Claude Code) are extending the GuildLedger repository into one downloadable guild package.
Read this whole file, then `CLAUDE.md`, the status file, `shared/schema.md` and `docs/API_FINDINGS.md`
before writing code. Sections 4 and 5 are hard constraints. Where this file and `CLAUDE.md` disagree,
section 5 lists the only intended changes; everything else in `CLAUDE.md` still applies.

---

## 0. Revision 2 — decisions taken and corrections (overrides sections 1–14 where they differ)

**Decisions by the admin (2026-11-13)**
- **Name:** CurseForge project **"Amazing Forever Guild Pack"** (under review). The addon folder stays
  `GuildLedger`, its SavedVariables `GuildLedgerDB`, its slash command `/gl`: nothing to rename, no
  `sv_path` changes for collectors.
- **No fork for now (decision 3).** Map, Discord link and activity are built **inside GuildLedger**. The hub
  (GuildOS fork, sections 7–8) is postponed; decide after the new modules run. Members who want the hub's
  features can install GuildOS itself from CurseForge next to the pack.
- **Version 0.4.0** for the first pack release (GuildLedger is already 0.3.0).
- **Testing:** the in-game relay check is not a precondition any more (section 2); relay, map, link and
  activity are tested together in one combined test round when the modules are built.
- **2026-11-14:** licence **MIT** (decision 2, `LICENSE`). Decision 5: linked guild members get the existing
  Discord role **guild-member**; rank roles are many and change (and use emojis), so the bot reads the server's
  roles and the guild ranks and officers set the mapping with `/roles` in Discord (saved in the archive, not in
  config.toml); nicknames: decided later (left alone). Decision 6: map sharing **on by default** with
  `/gl map share off` (overrides rule 8 "opt-in" for the map; positions are still never stored or uploaded).
  Decision 4 (GuildOS courtesy) and 7 (hub chat behaviour) only matter with a fork.
- **2026-11-14, decision 3 revised: fork GuildOS after all** (the admin wants its guild window: professions,
  recipes, recipe browser, roster). Phase 8 audit: docs/HUB_AUDIT.md. Hub decisions: folder `AmazingHub`, title
  "Amazing Hub", slash `/amazing`; chat-posting features **off, officers can enable** (decision 7); the hub's own
  guild chat log, roster log and map are **off** - GuildLedger's are used (bridge in Phase 10); the admin contacts the
  GuildOS author before publishing (decision 4). Sections 7–8 (Phase 9 fork, Phase 10 bridge) apply again; pack
  version with the hub: 0.5.0.

**Corrections**
1. **Roster data must reach the server** before link and activity can work: today collectors upload chat
   lines and roster *events* only; the bot's `members` table stays empty. New phase R (below) uploads the
   trusted roster snapshot (who is in the guild, rank, level, class, first/last seen online).
2. **One comms layer first.** `Relay.lua` owns the only send queue and a fixed list of message kinds. Before
   map and link, split it into `Comms.lua` (prefix, registration, paced queue **with priorities**, send
   result handling, counters, receive dispatch by kind) and the users of it (`Relay.lua`, later `Map.lua`,
   `Link.lua`). A map position must not wait behind 150 relayed chat lines.
3. **Message budgets for what exists too** (rule 9): hello every 15 min, who, need/text/got. Written in
   `shared/schema.md` before new kinds are added.
4. **Map sources:** extend the `/vendor-ref` sparse checkout with the map documentation and
   `Blizzard_MapCanvas` / `Blizzard_SharedMapDataProviders` before writing `Map.lua`.
5. `/seen` "last online" comes from the last roster snapshot that showed the member online: approximate;
   the bot says so.

**Build order (replaces sections 6–12)**

| Step | What | Section |
|---|---|---|
| C | `Comms.lua` with priorities; `Relay.lua` on top; budgets in `shared/schema.md` | correction 2, 3 |
| R | Roster snapshot upload (companion) and members table on the bot | correction 1 |
| M | `Map.lua` (sharing, WATCH/POS, pins) | 9 (Phase 11) |
| L | Discord link (addon, companion, bot; schema 3) | 10 (Phase 12) |
| A | Activity commands (bot) | 11 (Phase 13) |
| P | Publish 0.4.0 | 12 (Phase 14) |

**Progress (2026-11-13):** C, R, M, L, A built and covered by tests (no in-game test yet; one combined test
round, docs/INGAME_TESTS.md "Pack test round"). Decisions 2, 5, 6 answered on 2026-11-14 (see above); nicknames still open.
Map dots are plain frames on the map canvas (see docs/API_FINDINGS.md "Map"), not `AcquirePin`.
**Progress (2026-11-14):** Phase 9 built: `addon/AmazingHub` from `tools/rebrand-hub.py`, pack version 0.5.0, both
folders in the pack zip, THIRD_PARTY.md. Section 2 modules are neutralised (guard at every way out), not deleted;
RosterLog stays on (trials need it). Details and test status: docs/HUB_AUDIT.md section 8. Not tested in game.
Hub round reported OK by the admin 2026-11-14.
**Progress (2026-11-14, later):** Phase 10 built: `GuildLedger/API.lua` (global `GuildLedgerAPI`, apiVersion 1:
Version, IsCollector, GetModules, GetStatus = the exact `/gl status` lines, GetMap / SetMapShare / SetMapPins
(quiet), GetLink, NewerVersion) and the hub's **Ledger** tab (`tools/hub-extra/LedgerPanel.lua`, copied in by the
rebrand script): status, map switches, update notice; `/amazing map` opens the world map. Not tested in game
(docs/INGAME_TESTS.md "Bridge test round"). Deviation from section 8: the two map setters are the only
state-changing calls (the plan asked for toggles); Link stays `/gl link CODE` (a code is typed, not toggled).

## 1. Goal

Guild members install **one CurseForge project** and get, working together:

1. Everything GuildLedger does today (chat and roster capture, member relay, collector role).
2. A guild hub window: roster with last seen, professions and recipe browser, officer notes, trial
   tracker, raid attendance, loot history. This comes from a fork of GuildOS (MIT).
3. **Guild members on the world map** (new, own code).
4. **Discord link**: each character is tied to a Discord user; the bot sets roles and nicknames and
   answers "who is this" (new, own code in addon, companion and bot).
5. Activity per person in Discord (`/seen`, `/joined`, `/activity`, inactive list), using the link.

Non-goals: boss mods, combat helpers, loot-distribution systems (EPGP, DKP), anything that automates
gameplay, anything that reads the screen or memory.

## 2. Preconditions

- **Phase 7 (relay) must be verified in game with v0.2.1 before Phase 9 starts.** The map and the Discord
  link ride on the same addon-message path. If it is not verified, do Phase 8 only.
- Do not break the running system: the bot on the VPS, the collectors' companions and the archive stay
  compatible at every step. Every schema change follows `CLAUDE.md` rule 6 (bump, migration in Lua,
  companion and bot, `shared/schema.md` first).

## 3. Decisions the human must make (ask, do not assume)

Ask these at the end of Phase 8, in one message, and wait.

1. **Names.** Package name on CurseForge, hub folder name, slash command. "Guild Ledger Forever" is taken
   on CurseForge by another author. Check whether that addon's *folder* is also called `GuildLedger`; if
   yes, ours must be renamed (with SavedVariables migration and a new `sv_path` for every collector).
2. **License** of our own code (MIT or All Rights Reserved). GuildOS code stays MIT either way.
3. **Fork or not.** Default in this file: fork GuildOS as the hub. Alternative: no hub, only GuildLedger
   plus the new modules. Present what Phase 8 found.
4. **Courtesy to the GuildOS author** before publishing a fork (credit is mandatory, contact is optional
   but CurseForge moderators may ask about re-uploads).
5. **Discord verification.** The guild already has a verification process. Needed: which role marks a
   verified member, whether `/link` should require that role or grant it, which Discord roles map to
   which guild ranks, nickname policy (main character name, or leave nicknames alone).
6. **Map default**: sharing off until a member turns it on (default), or on with an opt-out.
7. **Hub behaviours that post in chat** (welcome message on join, recruitment popup): on or off for our
   guild. Default off.

## 4. Target architecture (hard constraint)

One project, one zip, several addon folders. The game loads them as separate addons; the user installs
and updates one thing.

```
Amazing-<version>.zip
├── GuildLedger/      our core: capture, relay, roles, comms, NEW Map and Link modules
└── AmazingHub/       fork of GuildOS: windows, roster, professions, notes, trials, raids, loot
```

- **GuildLedger keeps its folder name, its SavedVariables name and its rules.** That keeps every
  collector's `sv_path`, the companion, the bot and the tests unchanged.
- **New modules live in GuildLedger**, not in the hub: they need its comms layer, its roles and its
  secret-value discipline, and they must work when the hub is disabled.
- **The hub is the user interface.** It may show GuildLedger data through a small bridge (Phase 10).
  GuildLedger never depends on the hub; the hub treats GuildLedger as optional.
- Two comms prefixes (GuildLedger's and the hub's) run side by side. Do not merge the protocols.
- Outside the game nothing moves: companion on collector PCs → `#gl-ingest` → bot on the VPS.

Why not one folder: merging two codebases with different storage, comms and library rules is a rewrite
with no benefit for the user, and it makes pulling GuildOS updates impossible.

## 5. Rules (changes and additions to `CLAUDE.md` section 10)

1. **Still do not invent WoW API.** Every function and event must be found in `/vendor-ref` (Blizzard
   `forever` branch), in `docs/API_FINDINGS.md`, or in code that is proven to run on Forever. API names
   in this file marked "candidate" are leads to verify, not facts.
2. **Addon messages are allowed**, only through GuildLedger's existing comms layer (CLAUDE.md 5.7:
   the send result decides, counters in `/gl status`). No module sends on its own.
3. **Chat messages are still never sent by GuildLedger.** The hub's chat-posting features follow
   decision 7.
4. **Globals.** GuildLedger may add exactly one more global, `GuildLedgerAPI` (read-only functions,
   Phase 10). The hub keeps its own (renamed) globals.
5. **Libraries.** GuildLedger stays library-free. The hub keeps the libraries GuildOS bundles
   (LibStub, CallbackHandler-1.0, LibSerialize, LibDeflate, ChatThrottleLib), each with its licence file.
6. **Secret Values.** Check, then bail out — in every new module and in every hub file we touch.
7. **Licences.** Code may be copied only from MIT-licensed sources, with the notice kept in
   `THIRD_PARTY.md`. For "all rights reserved" addons (section 9) do not copy and do not port from their
   source; use only their public descriptions as feature ideas.
8. **Privacy.** Position sharing and Discord linking are opt-in per member, switchable off at any time,
   and described in plain words in the addon and on the project page. Positions are never stored on
   disk and never uploaded.
9. **Message budget.** The guild has about 1000 members. Every new message type needs a written budget
   (who sends, how often, worst case per minute for the whole guild) in `shared/schema.md` before code.
10. Stop after each phase, update `docs/INGAME_TESTS.md` and the status file, list what the human must
    verify, and wait.

## 6. Phase 8 — Audit (no code changes outside `/vendor-ref` and `/docs`)

Clone GuildOS into `/vendor-ref/guildos` at a pinned commit (record the hash). Its README states one
build serves TBC Anniversary (20506) and WoW: Forever (16001). Write `docs/HUB_AUDIT.md` with:

1. Module list with a verdict each: keep, keep but off by default, remove. Mark TBC-only parts
   (attunement tables, TMB import, TBC consumable lists) and how the build tells the clients apart.
2. **Everything that talks beyond our guild**: the cross-addon presence mesh ("ChehulNet"), recruitment
   matching over it, network alert popups, `Inbox.lua`, guildless boot. Files, entry points, messages
   sent. These are removed in Phase 9.
3. Its desktop companion: what it reads and whether anything in the addon expects it.
4. Libraries and their licences; all globals; SavedVariables names and typical size.
5. Its comms: prefix, message types, send rates, behaviour during chat lockdown.
6. Overlap with GuildLedger: its guild chat history and roster log modules call the same club and
   roster APIs. Say whether both can run together without doubling requests, and what to switch off.
7. A proposed **patch set** for the fork (section 7) and a rough size for each later phase.

Then ask the decisions in section 3 and **stop**.

## 7. Phase 9 — Fork and package

- Copy the pinned GuildOS tree to `/addon/AmazingHub/`. Keep its `LICENSE`; add `THIRD_PARTY.md` at the
  repo root naming GuildOS, its author, the commit and each bundled library.
- **Rebrand by script, not by hand**: `tools/rebrand-hub.ps1` (or `.py`) renames folder, TOC, globals,
  SavedVariables, slash commands and comms prefix, so it cannot collide with a real GuildOS install.
  Keep our changes as a small, documented patch set on top, so a newer GuildOS commit can be pulled:
  copy upstream → run the script → re-apply patches → run tests.
- Remove everything listed under Phase 8 item 2. Set the defaults from decision 7. On Forever, hide
  TBC-only tabs.
- TOC: `## Interface: 16001`. Add `## OptionalDeps: GuildLedger` to the hub.
- Packaging: extend the packaging tool to build `dist/Amazing-<version>.zip` with both folders at the
  root and nothing else (no companion, config, tests, `.git`). Add a `.pkgmeta` so a tag can be
  released by a packager later. The collector zip (with companion) stays a separate, non-public build.
- Version: the package is 0.3.0; both TOCs carry it; each addon shows the other's version in its status.

Acceptance: both addons load on Forever with no Lua error (BugSack) and no "out of date" flag; hub window
opens; no message leaves on any non-guild channel (check with the hub's own counters and `/gl status`);
GuildLedger capture and relay behave exactly as before; a second account with the real GuildOS installed
does not see or disturb ours.

## 8. Phase 10 — Bridge

- `GuildLedgerAPI`: `GetStatus()` (role, version, rows spooled, last sync, lockdown, comms counters),
  `GetModules()`, `IsCollector()`, and later `GetMapMembers()` and `GetLinkState()`. Plain tables, no
  secrets, no functions that change state.
- Hub: one "Ledger" settings page that shows that status and the toggles for Map and Link. If
  GuildLedger is missing, the page says so and nothing errors.
- Version awareness: GuildLedger's hello message already tells who runs which version; show an
  "update available" line when a newer version is seen from a guild member. No auto-update, no links.

Acceptance: hub works with GuildLedger disabled; GuildLedger works with the hub disabled; status shown
in the hub matches `/gl status`.

## 9. Phase 11 — Map module (`GuildLedger/Map.lua`, new)

Purpose: see guild members who share their position on the world map.

**Sharing**
- Off by default (decision 6). `/gl map share on|off`, `/gl map pins on|off`, `/gl map status`.
- Position source — candidates to verify in the map documentation in `/vendor-ref`:
  `C_Map.GetBestMapForUnit("player")`, `C_Map.GetPlayerMapPosition(mapID, "player")`. Record in
  `docs/API_FINDINGS.md` what they return in instances, in cities and during lockdown, and whether any
  return is flagged secret. If the position is nil or secret, send nothing.
- Never send inside instances, battlegrounds or during chat lockdown, and never while not in the guild.

**Protocol (demand-driven, so an idle guild sends nothing)**
- `WATCH <mapID>`: sent by a viewer while their world map is open, at most every 30 s.
- `POS <mapID> <x> <y>`: sent by a sharer only if a `WATCH` for their map or its parent was heard in the
  last 45 s, at most every 10 s, and only if the map changed or they moved more than a small threshold.
  `x`, `y` as integers 0–9999.
- No names in the payload: the sender comes from the message event; resolve it against the trusted
  roster (full name as an opaque string, never split) to get class and level. Ignore senders not in
  the roster.
- Write the budget (rule 9): worst case with N watchers and M sharers in one zone.

**Display**
- Pins on the world map in class colour, tooltip with name, level, zone and age of the position.
  Fade after 60 s without update, remove after 120 s. Skip party and raid members (the game shows them).
- Continent and world views: project zone positions to the parent map (candidate:
  `C_Map.GetMapRectOnMap`), or show a per-zone count if projection is not available.
- Study how Blizzard adds pins (`Blizzard_MapCanvas`, `Blizzard_SharedMapDataProviders` in
  `/vendor-ref`) and choose the method that does not taint the map. Test: open the map in combat, click
  quest pins and flight points, use the map with the hub open.
- Optional later: minimap pins; per-zone counts for members who do not share, from the roster's zone
  text.

Tests (lupa): encoding/decoding, throttles, watch expiry, pin expiry, unknown sender ignored, nothing
sent when sharing is off, in an instance, or when position is nil/secret. In game: two accounts, steps
in `docs/INGAME_TESTS.md`.

Acceptance: A shares, B opens the map → B sees A within 15 s; both close maps → counters show no
`POS` after 45 s; sharing off → nothing sent; no taint error; no Lua error during a boss fight.

## 10. Phase 12 — Discord link (addon, companion, bot; schema 3)

Addons have no network access. The link travels: member's addon → guild addon channel → any online
collector → SavedVariables → companion → `#gl-ingest` → bot.

**Flow**
1. Discord: member runs `/link`. Bot creates a one-time code (8 characters, no look-alike characters,
   valid 30 minutes, bound to that Discord user) and answers ephemerally: "type `/gl link CODE` in game".
2. Game: `/gl link CODE`. The addon stores the pending code account-wide and sends `LINK <code> <tag>`,
   where `<tag>` is a random account tag generated once and stored account-wide (an identifier, not a
   secret). It re-sends at login and every few minutes until a collector acknowledges or the code is
   30 minutes old.
3. Collector addon: on `LINK`, store `{ code, tag, sender name, sender GUID from the roster if known,
   time }` in a `links` spool (ring-buffered) and answer `LACK <code>`. Acknowledged means recorded,
   not linked.
4. Companion: uploads spool rows as type `link`.
5. Bot: accepts a row only if the code exists, is unused and unexpired, and the sender is a current
   guild member in the archive. It then **asks the Discord user to confirm** ("Link character X?",
   buttons Confirm / Not me). Only a confirmation creates the link. Confirmation is the security
   anchor, because any guild member can see and replay addon messages.
6. Alts: at login on any character, the addon sends `ALT <tag>` once per session if a link exists.
   When the bot sees a known tag from an unlinked character, it sends the same confirmation to the
   linked Discord user. At most 3 open confirmations per user; "Not me" blocks that character for
   that user.

Verify in `/vendor-ref` that the sender argument of the addon-message event is supplied by the game and
cannot be set by the sending addon, and record how surnames appear in it.

**Bot**
- Tables: `link_codes(code, discord_user_id, created_at, used_at)`,
  `links(guild, guid, name, discord_user_id, tag, linked_at, via_collector, status)`,
  `link_blocks(discord_user_id, guid)`.
- Confirmation by DM with persistent buttons (they must survive a bot restart). If DMs are closed:
  `/link` shows the user's pending confirmations ephemerally.
- After a link, per config `[link]`: set nickname (decision 5), add roles by guild rank from the latest
  trusted roster, add the verified role if configured. When a linked character leaves the guild
  (roster events already exist), re-evaluate; when the last one leaves, remove the rank roles after a
  grace period (default 7 days).
- Commands: `/link`, `/unlink [character]`, `/chars [user]`, `/whois <character>`; officers:
  `/linkstatus` (linked / unlinked counts, list of unlinked members), `/unlink user:`.
- Hints, not links: guild messages sent from Discord carry `author.discordInfo` (display name and last
  online character name, CLAUDE.md section 2). Store them as suggestions for officers. Display names are
  not unique, so never link from them.
- Discord permissions needed: Manage Roles, Manage Nicknames, application commands; the bot's role must
  sit above every role it assigns; the server owner's nickname cannot be changed. Document this in
  `README.md` and fail with a clear log line, never silently.
- `allowed_mentions = none` stays. `/unlink` deletes the link rows for that user.

Tests (pytest, synthetic data): expired code, reused code, sender not in guild, replayed `LINK` from
another character (must end in a confirmation the real user can reject), blocked character, alt flow,
bot restart with open confirmations, leave → role removal after grace. Addon (lupa): re-send and stop
on `LACK`, expiry, tag stability across characters.

Acceptance: a test member links main and one alt without any officer action beyond being online; roles
and nickname appear; `/whois` and `/chars` agree; a replayed code cannot link without the user's click;
`/unlink` removes everything.

## 11. Phase 13 — Activity (bot)

This is "v2" from CLAUDE.md, now per person instead of per character.

- `/seen <character|user>`: last time online (roster `ls`) and last chat line time.
- `/joined <character|user>`: join event with its precision (exact, window, or log).
- `/activity <user>`: characters, levels, chat lines in the last 7 and 30 days, last seen.
- Officers: `/inactive days:<n>`: members with no login for n days, grouped by Discord user, with
  unlinked characters listed separately. Ephemeral answers, CSV attachment for long lists.
- No message text is shown by these commands, only counts and times.

## 12. Phase 14 — Publish

- CurseForge project: description (what it does, what is logged, what is shared and with whom, how to
  switch each part off), licence per decision 2, credits to GuildOS, screenshots, changelog.
- Upload the package zip as a Beta first; game version Forever 1.60.1. A Release or Beta file must be
  approved before the project syncs to the CurseForge app.
- `README.md`: install for members (one project), for collectors (project plus companion), for the bot
  host. Update the pinned Discord post.
- Optional: release from a git tag with a packager and a CurseForge API token stored as a CI secret,
  never in the repo.

## 13. Reference material

Clone into `/vendor-ref/` (git-ignored). Read before use; copy only where the licence allows.

| Source | Licence | Use |
|---|---|---|
| Blizzard UI source, `forever` branch — https://github.com/Gethe/wow-ui-source/tree/forever | Blizzard | authoritative API, map canvas, addon-message docs |
| GuildOS — https://github.com/danielcosta42/GuildOS | MIT | fork base for the hub; `docs/forever`, `tools/secret-values.lua` |
| xeR's Forever Guild Link — https://www.curseforge.com/wow/addons/xers-forever-guildlink | MIT | profession and craft-request ideas, code reuse allowed with notice |
| GuildLink addon — https://github.com/Soche/guildlink-addon | check before use | character → Discord design (member types Discord ID, companion uploads) |
| FlockSync — https://github.com/GearDuckDev/FlockSync | check before use | "officer catcher" pattern for collecting member data |
| GuideMate's location — https://github.com/thesakia/guidemates-location | all rights reserved | **ideas only** |
| Guildon — https://www.curseforge.com/wow/addons/guildon | not stated on the page | **ideas only**: positions only to members looking at a map near you |
| Whereabouts — https://www.curseforge.com/wow/addons/whereabouts-forever | not stated on the page | **ideas only**: opt-in, map ID plus two numbers, nothing in instances |
| ForeverGuild+ — https://www.curseforge.com/wow/addons/foreverguildplus | all rights reserved | **ideas only** |

## 14. Known limits (tell the human, do not hide)

- A link or a position reaches Discord or other players only while the needed party is online: links
  need a collector online and that collector's next `/reload` or logout before the bot sees them.
- Map pins exist only for members who run the package and switched sharing on.
- Two addons in the addon list, one download. Disabling one must never break the other.
- The fork must be re-synced with GuildOS by hand when Forever patches break things; the rebrand script
  and patch set exist to make that an hour, not a week.
- The Forever addon API is still changing. Feature-detect, fail quiet, show the state in `/gl status`.
