# Community plan — build instructions for Claude Code (pack 0.7 to 0.9)

Revision 3, 2026-11-24: decision 9 answered: Linked Roles are not built; phase D6 dropped.
Revision 2, 2026-11-24: decisions 1, 4, 8 and 11 answered by the admin (section 4), armory address confirmed.
Archived 2026-11-26: all phases built (pack and bot 0.7.0). Decisions: docs/dev/DECISIONS.md; what is still to check in game: docs/dev/INGAME_TESTS.md.
Revision 1, 2026-11-24. Extends `CLAUDE.md` and `docs/dev/archive/PACK_PLAN.md`; it replaces neither.
Checked against this repository at commit `f68542a` (pack 0.6.0; `pytest addon/tests companion/tests bot/tests`:
270 passed, 1 skipped because `vendor-ref/GuildOS` is not checked out) and against upstream GuildOS **1.40.0**
(commit `1f9fa9d4d9b9c9bd0b4061e4dbfd1dde940235fb`, 2026-11-23).

You (Claude Code) are extending the project in three directions at once: a Discord sign-up and community side,
a newer guild window, and a clearer repository. Save this file as `docs/dev/archive/PLAN_COMMUNITY.md` and read it whole,
then `CLAUDE.md`, `STATUS.md`, `shared/schema.md`, `docs/dev/API_FINDINGS.md` and `docs/addon/HUB_AUDIT.md`.
Sections 4 and 5 are hard constraints. One phase per session; stop after each phase as section 5 rule 10 says.

Words used here: **GuildLedger** = the silent addon (`addon/GuildLedger`). **Hub** = Amazing Hub, the guild
window (`addon/AmazingHub`, generated). The admin sometimes says "guild ledger" for the hub window. **Bot** = the
one Discord bot on the server. **Collector** = an officer whose PC runs the companion.

---

## 1. What the admin asked for (2026-11-24)

| # | Wish | Lands in | Phase |
|---|---|---|---|
| W1 | Sign-up in Discord starts with a bot check (today: Pandez Guard) | bot | D1 |
| W2 | Server nickname = in-game name | bot (after the link, automatic) | D1 |
| W3 | Alts known per member, without typing names | bot (account tag, exists) | D1, D3 |
| W4 | Every guild character listed in Discord, usable with 600+ characters, armory link each | bot | D3 |
| W5 | Characters reachable from a member's profile: right-click → Apps → Characters (Linked Roles: decided against, decision 9) | bot | D3 |
| W6 | Interest roles and language roles (no play times) | bot | D2 |
| W7 | Welcome as a private message with the addon download link | bot | D1 |
| W8 | Professions and recipes in Discord: who can craft what (forum) | companion, bot | X, D4 |
| W9 | Guild bank visible in Discord | companion, bot | X, D5 |
| W10 | Fewer third-party bots where ours can do the job | bot, admin | D7 |
| W11 | New windows open in front of the guild window | hub | H1 |
| W12 | A search bar with drop-down results instead of the search button; settings among the results; a result jumps to its place | hub | H2 |
| W13 | A reset button wherever a filter or search is active | hub | H3 |
| W14 | Sorting by a column (e.g. level) mixes online and offline members | hub | H4 |
| W15 | Closed while minimised → reopens full size | hub | H5 |
| W16 | Guild chat annotation: on by default, class icon off, level on, alt tag on but only for members who set one themselves | hub | H6 |
| W17 | Shift + left click links items and recipes into chat | hub | H7 |
| W18 | "Link your other characters?" comes back at every reload and seems to do nothing | hub | U, H8 |
| W19 | Materials needed for recipes | hub | U, H9 |
| W20 | Item and recipe database to search; base for wishes and reserves from raids and dungeons | tools, hub, bot | C |
| W21 | Entry date per member, worked out from the first guild chat activity | GuildLedger, hub, bot | G4, H10 |
| W22 | Guild bank tab that updates whenever someone opens the bank | hub | U |
| W23 | Core sign-up: what it is and how it works | answered in section 10 | U |
| W24 | "Maupa's sprite wishes…" greeting 30 s after login | GuildLedger | G1 |
| W25 | Faster updates of guild members' map dots | GuildLedger | G2 |
| W26 | Project in three parts (addon pack, collection, Discord), logical and readable for people | repo | S |

Decided **not now**: a consent notice (no), invite tracking, guest and alumni roles, removing unverified accounts,
play-time roles.

## 2. What the analysis found (build on these, do not rediscover them)

1. **Much is built but not yet verified.** `STATUS.md` "Next steps" 1 to 5 are open: bot 0.6.0 not deployed, the
   pack round (relay, map, **link**, activity) and the bridge round not run in game. The Discord sign-up stands
   on the link, so the link must work in game before D1 is trusted (Phase 0).
2. **Upstream GuildOS moved from 1.20.1 (our pin) to 1.40.0 in 13 days** and already contains several wishes
   (its `CHANGELOG.md`):
   - W18: 1.26.1 fixes exactly this (the question no longer returns at every login for linked characters, and
     Link works with no officer online); 1.39.0 `Modules/AltSync.lua` (#424) syncs each link on its own with
     author and time. Its header describes the old fault: one table replaced the receiver's whole table, so any
     officer with an old or empty table wiped everybody's links.
   - W22: 1.31.0 `Modules/GuildBank.lua`, `UI/GuildBankPanel.lua`: whoever opens the bank reads every tab, the
     log and the money and shares it (SyncService domain `gbank`); a Bank tab shows it from anywhere.
   - W19: 1.34.0 one Crafts tab, a recipe opened in place with its materials and crafters; 1.34.2 catalogue for
     build 1.60.1.71037.
   - W21 (partly): 1.39.0 `Modules/MemberHistory.lua` and a Joined column, officers only, fed by the roster log.
   - W23: 1.26.0 new core sign-up window; 1.30.0 moved Search and Sync to the title bar and Core Sign-up into
     Raids.
   - Also: 1.21.1 answers sync requests at most every two minutes (the heaviest traffic in a big guild);
     1.29.0 reorganised Settings into six sub-tabs (now `UI/SettingsPanel.lua`).
   Still missing upstream at 1.40.0: W11 to W17 and W20 (checked in its source: the roster comparator still
   says "Online always first", `UI:ToggleMain` only toggles, `Search.lua` is still a popup of text lines, no
   `SetToplevel` outside the bank drawer, the same four `ChatTweaks.DEFAULTS`).
3. **Re-pinning is feasible.** Of the 61 entries in `PATCHES` (`tools/rebrand-hub.py`), 45 still match upstream
   1.40.0 exactly once; 16 no longer match: `UI/FeaturePanels.lua` 9, `UI/PointsPanel.lua` 2,
   `UI/ManagementPanel.lua` 2, `Core/Config.lua` 1, `Modules/RecipeTracker.lua` 1, `UI/ProfessionsPanel.lua` 1.
   `tools/hub-extra/SettingsPlus.lua` wraps the old `RefreshSettingsPanel` and needs rework for the six sub-tabs.
4. **New upstream features act for the player or reach outside the guild** and need a verdict before they ship:
   bank organise and cleanup (move, withdraw, sell), Leadership > Bulk actions (promote, demote, remove), join
   dates written into notes, whispers to members without the addon, one-click warn whispers, birthday and group
   lines in guild chat, several welcome messages, the alliance code written into the guild info and the guild
   master's note, a hidden password-protected channel for allied chat.
5. **W18 in the pinned hub** has two more faults, found by reading the code: a member's own claim (`SELF_ALT`)
   is sent once and only holds if an officer with the hub is online to apply it; and
   `AltAutoDetect:DetectOwnAlts` always proposes the highest-level character as main, so for an officer a group
   already linked under another main can be offered again, `AmazingHub:LinkAlt` refuses it, and its error line
   is hidden by the quiet-chat rule (`PackTweaks.lua`).
6. **W20:** on Forever the wishlist search has nothing to search. `Wishlist:RebuildItemIndex` seeds a static raid
   list only on TBC Anniversary and the Encounter Journal only on retail; on Forever only items already on
   somebody's list are found.
7. **W19 in the pinned hub:** reagents are in the catalogue (`ProfCatalog.F.reagents`,
   `ProfDirectory.Reagents(id)`) but shown only in the recipe card that opens on a click
   (`ShowCard` in `UI/ProfessionsPanel.lua`), as plain names.
8. **W12:** `Modules/Search.lua` finds members, recipes and loot; its results are text, not clickable.
   `UI:OpenWindow(id, sub, filter)` (`UI/Window.lua`) already opens a tab and a sub-tab with a filter.
9. **W16:** `ChatTweaks.DEFAULTS` = enabled false, classIcon true, level true, altTag true; defaults only fill
   missing keys, so changing the table does nothing on existing installs.
10. **Bot today:** `/link`, `/unlink`, `/chars`, `/whois`, `/linkstatus`, `/seen`, `/joined`, `/activity`,
    `/inactive`, `/roles`, `/collector`, `/dkp`, `/loot`, `/wishlist`, `/wish`. `[link] set_nickname` exists
    (highest-level linked character). Intents: guilds, guild messages, message content. No listening port.
    `bot/pyproject.toml` lists `packages = ["guildledger_bot"]` by name: a sub-package that is not listed is
    not installed on the server.
11. **The companion already reads the hub's file** (`companion/guildledger/loot.py` reads `AmazingHub.lua`,
    `shared/schema.md` 7). Professions, bank and alt links can travel the same way without touching the addon.
12. **Discord limits that shape the design:** a bot cannot write a member's server profile text; profile text
    takes no named links and at most 190 characters. A server holds at most 1000 active threads, forum posts
    included (archived posts stay readable); a forum has at most 20 tags, a post 5. One message: 10 embeds,
    6000 characters in all, 4096 per embed description. An autocomplete list shows 25 choices.
13. **Armory:** Forever has no realms; a character is found by first name and surname. EU address, confirmed
    with the admin's own character (the page loads; the address is not written here, the repository is public):
    `https://worldofwarcraft.blizzard.com/en-us/forever/eu/armory/character/firstname-surname`, so the rule is
    lower case with a hyphen for the space. Profiles exist from level 10 after one logout. Not yet checked:
    a name with a special letter.

## 3. Structure: three parts

```
PART 1  addon pack (every player, CurseForge)      addon/GuildLedger, addon/AmazingHub (generated), addon/hub-extra
PART 2  collection (officers + server)             companion/, bot/guildledger_bot/collection/
PART 3  Discord community (every member)           bot/guildledger_bot/community/, docs/discord/
shared                                             shared/schema.md, shared/catalog/, bot/guildledger_bot/{config,store,client}.py
```

Where a new thing goes:

| It is… | It goes to… |
|---|---|
| captured from the game, relayed or uploaded with strict rules, no window | GuildLedger |
| something a player sees or clicks in game; guild data the hub syncs itself (alts, professions, bank) | the hub: a file in `addon/hub-extra/` first, a patch in `tools/rebrand-hub.py` only where no hook exists |
| read from a SavedVariables file and sent to the server | companion |
| merged into the archive or posted to a log channel | bot, `collection/` |
| anything a Discord member sees or does | bot, `community/`, one module per feature |

`collection/` never imports from `community/`. Both use `store.py` and `config.py`. One bot process, one database.
This refines `PACK_PLAN.md` section 4 ("new modules live in GuildLedger"): capture and transport stay in
GuildLedger; what the hub already syncs and shows stays in the hub.

## 4. Decisions the admin must make

Moved to [docs/dev/DECISIONS.md](../DECISIONS.md) (section "Community plan, pack 0.7").

## 5. Rules (additions to `CLAUDE.md` 10 and `PACK_PLAN.md` 5, which all stay)

1. **Do not invent WoW or Discord API.** WoW names marked "candidate" here are leads to verify in
   `/vendor-ref` (forever branch) or in code proven on Forever. Discord: only what discord.py 2.4+ documents.
2. **Never edit `addon/AmazingHub` by hand.** Own files in `addon/hub-extra/`, patches in the script, each
   applying exactly once. Prefer wrapping a hub function from an own file over patching its text.
3. **Nothing the pack does in game on the player's behalf is on by default**: no chat line, whisper, note
   change, rank change, bank move or sale (decision 7).
4. **Every new addon message kind gets its budget row in `shared/schema.md` 5 before code.** New upload rows are
   written into `shared/schema.md` first. Deploy the bot before any companion that sends something new.
5. **Bot settings an admin changes live in Discord** (`/setup …`, saved in the `state` table like `/roles`).
   `config.toml` keeps only secrets and what the process needs to start.
6. **Bot permissions stay minimal**: never Administrator. Needed in total: Manage Roles, Manage Nicknames,
   Manage Webhooks in `#gl-ingest`, and in its own channels Send Messages, Embed Links, Create Posts, Send
   Messages in Threads, Manage Threads, Read Message History. No Server Members intent: every flow starts from
   a member's click or command.
7. `allowed_mentions = none` everywhere. Names from the game are escaped. No member data on the public website.
8. **No new Python dependency without asking.** (aiohttp arrives with discord.py; Pillow does not.)
9. Tests use synthetic data. Pure logic (what to post, what changed) is separate from Discord calls and tested
   without Discord, as `link.py` and `commands.py` are today.
10. After each phase: tests green, `docs/dev/INGAME_TESTS.md` gets the checks a person must run, `STATUS.md`
    updated, a summary of what to verify, then **stop and wait**.

## 6. Order

```
0  land what is built ─► S structure ─► D1 sign-up ─► D2 roles ─► D3 characters        (Discord, pack 0.7)
                          └► G small GuildLedger changes (any time after S)
U  re-pin the hub ─► H hub changes                                                      (pack 0.8)
C  catalogue ─► X hub data to the server ─► D4 professions ─► D5 bank                   (pack 0.9)
D7 bots · P publish and tidy
```

U is the largest step and independent of D1 to D3. Do U on a branch; 0.6.x stays releasable from the old pin
until the hub round in U3 passed.

## 7. Phases

### Phase 0 — Land what is built (no new code)

Prepare one checklist for the admin from `STATUS.md` steps 1, 2 and 4 and `docs/dev/INGAME_TESTS.md`
(E1 to E8, the pack round, the bridge round) and wait for results. Minimum before D1: one member links a main
and an alt through the whole chain (code in Discord → `/gl link` → collector → upload → confirmation → role).
Anything that fails is fixed first.

### Phase S — Structure (no behaviour change)

1. **Bot packages.** Move modules; `python -m guildledger_bot` and every command stay as they are.

   | New place | Modules |
   |---|---|
   | `guildledger_bot/` | `__main__.py`, `client.py`, `config.py`, `store.py` |
   | `guildledger_bot/collection/` | `ingest.py`, `post.py`, `collectors.py`, `ops.py`, `backup.py`, `loot.py` |
   | `guildledger_bot/community/` | `link.py`, `activity.py`, `lootcmds.py`, `roles.py` (the `/roles` group from `commands.py` and `sync_roles` from `client.py`), `commands.py` (what is left), `common.py` (`reply`, `esc`, `ts`, `is_officer`) |

   `bot/pyproject.toml`: replace the fixed package list by package discovery for `guildledger_bot*`. Check the
   `Dockerfile`, `bot/deploy/setup.sh` and `tools/deploy.ps1 -DryRun` (the new folders must be listed). Add a
   test that fails when a file under `collection/` imports from `community/`.
2. **Hub sources:** move `tools/hub-extra/` to `addon/hub-extra/` (script constant, tests, docs).
3. **Probe:** `addon/GLMeterProbe/` is temporary; if its result is recorded in `docs/dev/API_FINDINGS.md`,
   remove it (git history keeps it), else finish recording it first.
4. **Docs for people.** `README.md`: three parts in the table and the picture, the repository map updated, and
   a short "Names" box (GuildLedger, Amazing Hub, the pack, the bot, collector). New `docs/discord/SERVER.md`
   (admin: channels, roles, permissions, `/setup`, bots kept and removed; move section 2 of
   `docs/collection/ADMIN.md` here and link back) and `docs/discord/MEMBERS.md` (what a member does: verify,
   link, pick roles, find a character or a crafter; text that can be pasted into Discord). `STATUS.md`: the
   "What runs right now" table gets a Part 3 block. `CLAUDE.md` section 4: the new map and a pointer to this file.

Acceptance: the same 270 tests pass (plus the new import test); `check` runs with the admin's config; the deploy
dry run lists `collection/` and `community/`; no file moved without its references.

### Phase D1 — Sign-up in Discord (W1, W2, W3, W7)

Flow for a new member: **Verify button → role → private welcome → link → nickname and roles by themselves.**

1. **`/setup` group** (Manage Server), values in the `state` table: `gate channel: role: min_account_age_days:`,
   `welcome` (a modal with the message text), `addon url:`, `nickname on|off`, `announce channel:`, `show`.
2. **Bot check** (`community/onboarding.py`). `/setup gate` posts one message with a persistent **Verify**
   button. A click answers ephemerally with a small task: five buttons in random order, one named in the text.
   The right answer is kept on the server, never in a button's id. Three tries, then ten minutes' wait; a task
   expires after two minutes; an account younger than the set age is told to ask an officer. Success: the gate
   role is given and the welcome is sent. One line per pass or lockout to `#gl-ops` when configured.
   This keeps scripted accounts out; the proof that someone belongs to the guild is the link.
3. **Welcome** as a private message: the admin's text, the addon link, the three link steps and a **Get my link
   code** button (does what `/link` does). If private messages are closed, the same text is shown ephemerally
   after the check. Default text in `docs/discord/MEMBERS.md`.
4. **Link, made smoother** (`community/link.py`):
   - `/main character:` (autocomplete over the member's own linked characters) stores the main; without it the
     main is the highest-level linked character as today. Nickname = the main's name (decision 2), 32 characters
     at most; the server owner's nickname cannot be set: log once.
   - `/link approve user: character:` (Manage Roles): an officer links a current guild member at once, recorded
     as approved by that officer. For members who cannot wait for a collector.
   - **Without the addon:** the member types `!link CODE` in guild chat. When that line reaches the archive with
     its text, the bot treats it like a `link` row from that author and asks for the same confirmation. The log
     channel shows `!link ••••` instead of the code; the masking lives in the formatting code the companion's
     direct mode shares, so both mask. Limit: a collector must capture the line with text.
   - `/link` again shows open confirmations (exists) and, new, the member's linked characters and main.
5. **After the first confirmed link**: roles and nickname as today (`sync_roles`), the role menus of D2 offered
   once, and the optional public line (decision 12).
6. **Collectors see waiting link requests** (G3), so a link does not sit for hours.

Tests: task generation and checking, lockout, expiry, account age, welcome fallback, `/main`, nickname length,
approve (not in guild → refused), chat code (valid, expired, used, wrong author later rejected by "Not me"),
code masked in the posted line. Acceptance: a test account passes the check, gets the role and the message,
links with the addon and, separately, with the chat code; nickname and roles appear; restart loses nothing.

Cutover (admin, in `SERVER.md`): set up the gate in a test channel → try with a second account → move the button
to the real channel → switch off Pandez Guard's panel → rename the members' role → remove Pandez Guard. Before
removing it, check that the members' role is an ordinary role that members hold: a bot's own role (the one
Discord makes for the bot itself) disappears with the bot.

### Phase D2 — Role menus (W6)

`community/rolemenus.py`. `/setup rolemenu add group: label: role: [emoji:]`, `remove`, `post channel:`. A panel
with one multi-select per group (`interests`, `languages`; at most 25 entries each). A member's selection adds
and removes only roles registered in that group. The same panel is offered once after the first link. The bot's
role must sit above these roles; a refused change is said plainly to the member and logged once.

Languages (decision 4), shown in their own spelling: English, Deutsch, Français, Español, Italiano, Português,
Nederlands, Polski, Русский, Українська, Svenska, Dansk, Norsk, Suomi, Čeština, Magyar, Română, Ελληνικά,
Türkçe, and "Other". `/setup rolemenu languages preset` registers this list. So that the server does not get
twenty empty roles, a language role is created the first time a member picks it (plain role, no permissions,
below the bot's role); a role the admin made by hand with the same name is used instead.

Tests: selection → role changes, unknown or deleted role, a role outside the menu is never touched, a language
role is created once and reused.

### Phase D3 — Characters (W3, W4, W5)

1. **Right-click a member → Apps → Characters** (a user command) and `/chars`: the main first, then alts, each
   `[Name](armory)` with level, class, rank and last seen, plus a link to the member's forum post. Ephemeral.
   Who may look: decision 5 (today `/chars` on others is officers only).
2. **`/whois`** with autocomplete over the member list; the answer adds the armory link and the forum post.
3. **Character forum** (`community/directory.py`), `/setup directory forum:`:
   - one post per linked Discord user: title = main's name, tag = main's class, body = one line per character;
   - index posts "Not linked yet" in alphabetical blocks for every other guild character, so all are listed;
   - one pinned post that explains `/whois` and the right-click.
   A job every 10 minutes works out the wanted text of each post, compares a hash with the stored one and
   writes only what changed, at most 10 Discord writes per round; an archived post is reopened before editing.
   A member whose characters all left gets "left the guild" after the grace period, then the post is removed.
   Table `directory_posts(kind, key, thread_id, message_ids, hash, updated_at)`.
4. **Armory link:** `/setup armory url:` with `{name}` (lower case, space → hyphen), only for level 10 and
   above; the default is the EU template of decision 11; an empty template → no links. Check one name with a
   special letter before trusting the rule for such names; until then they get no link.

Tests: name → address, text of a post, the plan of writes for a changed roster (new, changed, unchanged, left),
the write limit, block splitting under the message limits. Acceptance: 600 synthetic characters produce posts
within every limit; a second run writes nothing; a rank change rewrites exactly one post.

### Phase G — GuildLedger, small changes

- **G1 (W24):** `Welcome.lua` `DELAY` 8 → 30. Update `test_addon_welcome.py` and `docs/addon/README.md`.
- **G2 (W25):** today a sharer sends at most one position per 10 s (`POS_GAP`), only after moving 30 of 9999
  units or every 30 s, and only while someone watches that map. New: the gap follows how many sharers were heard
  on the same zone map in the last 30 s: up to 10 → 3 s, up to 30 → 5 s, more → 10 s; `MOVE_MIN` 15. Viewers
  glide a dot between its last two positions (display only). Write the new `P` budget row first (30 sharers at
  5 s = 6 messages per second for the guild; today's row assumes 50 sharers at 10 s = 5). Older clients keep
  10 s. In game: the counters in `/gl status` show no throttling.
- **G3:** a collector with unsent link requests gets one notice (`ns.Notice`) and
  `GuildLedgerAPI.GetLinkQueue()`; the hub's Ledger tab shows "Link requests waiting: N" with a **Send now**
  button (= `/gl flush`).
- **G4 (W21):** per guild a small table `first[guid] = t`: the earliest guild chat line this client has seen
  from that member (live or history row), kept when the chat ring buffer is trimmed, dropped 90 days after the
  member left. `GuildLedgerAPI.GetJoined(guidOrName)` → `{ t, estimated, src = "join"|"chat"|"seen" }`: the
  earliest of a join event, `first` and the roster's `fs`. List the key under "Addon-only keys" in
  `shared/schema.md`. The bot needs no upload for this: `activity.joined` gets the same rule from its own chat
  table (earliest of join event, first chat line, first seen), and says which it used.

### Phase U — Re-pin the hub to upstream 1.40.x (W18, W19, W22, W23)

**U1 Audit (docs only).** Update `/vendor-ref/GuildOS` to the newest release (record the hash). Add section 10
to `docs/addon/HUB_AUDIT.md`:
1. every module and UI file new since 1.20.1 with a verdict: keep, keep but off, hidden;
2. everything new that posts, whispers, writes notes or guild info, changes ranks, moves or sells bank items, or
   leaves the guild (section 2 item 4): file, entry point, proposed default;
3. the patch list: applies / needs rework / no longer needed, one line each;
4. each own file (`SettingsPlus`, `TableSort`, `ChatTag`, `WishImport`, `LedgerPanel`, `PackTweaks`) against the
   new code: Settings sub-tabs, the Loot window, officer nicknames in chat (#429), new tabs to hide or switch off;
5. saved data: what upstream's migrations do to an existing `AmazingHubDB` (1.34.1 changed realm keys);
6. the tables `companion/guildledger/loot.py` reads: still there, same shape?
7. mixed versions: a member on pack 0.6.0 next to one on the new hub (alt links, professions, sync requests).
Ask decision 7 and **stop**.

**U2 Rebuild.** `PINNED`, the patches, the own files, `EXPECTED_FAIL` in `addon/tests/test_hub.py`. The guard
tests must cover every new file (`test_every_direct_chat_call_is_shadowed`,
`test_raw_addon_sends_only_in_guarded_places`, `test_no_upstream_names_left`).

**U3 Hub round in game** (new checklist): no Lua error at login; the alt question appears once, Link holds
across reloads with no officer online, Not now is remembered; Bank tab fills after one member opens the bank;
Crafts shows materials; Classic look; Settings; nothing leaves the guild (hub counters, `/gl status`); one member
still on 0.6.0 sees no errors.

### Phase H — Hub changes of our own (on the re-pinned hub)

**Built 2026-11-25 on `repin-140`** (own files in `addon/hub-extra/`: `Windows.lua` H1/H5, `SearchBox.lua` H2,
`ClearBox.lua` H3, `Links.lua` H7, `Materials.lua` H9, `Joined.lua` H10; `PackTweaks.lua` H6; `SettingsPlus.lua` H2
index and H4; test `hub_alts.lua` H8). Differences from the text below: H4's switch is in Settings → Interface →
"Member list" (the roster toolbar has no room), and the sort mixes by default since round U3. H3: "Reset" exists
for the member list (its search field's "×" clears search, rank and class); the other panels keep their own
controls. H7: recipes without an item (enchants) are not linked. H9: upstream's order quantity already multiplies
the materials; only the bank count is new. In-game check: docs/dev/INGAME_TESTS.md "Hub round H".

- **H1 (W11):** `hub-extra/Windows.lua`. The main window and every hub popup are top-level and come to the front
  when shown or clicked (wrap `UI:StylePopup` and the few creators that do not use it; the list comes from U1).
  The game's own dialogs still open above.
- **H2 (W12):** the title-bar Search button becomes a search box. Typing opens a list under it, grouped, at most
  8 rows a group: Members, Recipes, Items, Bank, Settings, Tabs. Up/Down/Enter and Esc work. A click goes there:
  member → Roster with the member's card; recipe → Crafts opened on that recipe; item → its wishlist or bank
  place; setting → the Settings sub-tab scrolled to the control, which flashes once; tab → that tab. Shift-click
  links instead (H7). The Settings rows come from an index filled while Settings is built (label, sub-tab,
  control); `PackTweaks.lua` already wraps `UI.CreateCheckbox` and can record them. `/amazing search text` puts
  the text in the box. `Search:Query` keeps its shape and gains the new groups; extend upstream's search test.
- **H3 (W13):** every search box shows a clear "×" while it holds text. A panel with filters shows **Reset**
  while anything differs from its default, and one click restores all of them (the panels: from U1).
- **H4 (W14):** setting `rosterOnlineFirst`, default off, as a checkbox beside "Show offline". Off: the chosen
  column alone decides the order. On: today's behaviour.
- **H5 (W15):** when the window is shown by the slash command, the minimap button or the key binding and it is
  folded to the bar, it unfolds (`UI:ToggleMain`; `UI:OpenWindow` does this already).
- **H6 (W16):** one-time change per account, guarded by a marker (`settings.packChatDefaults = 1`):
  annotate on, class icon off, level on, alt tag on. Later changes by the player are kept. Tag rule
  (decision 8, revised by the admin 2026-11-24): show the member's own tag text (`ChatTag.lua`) when set; else
  "(alt of …)" for every alt link, self-claimed or entered by an officer (U1: the two cannot be told apart). Upstream's alt entries carry `author`, but a member's
  claim is applied by an officer: find out in U1 whether the two can be told apart, and ask if not. Update
  `test_own_chat_tag_replaces_the_alt_tag_for_everyone_who_reads_it`.
- **H7 (W17):** one helper in an own file that puts a link into the open chat box, used by Crafts rows and
  materials, Bank items, wishlist and loot rows and search results. Candidates to verify: `ChatEdit_InsertLink`
  (upstream's bank panel hooks it behind an existence check), `ChatFrameUtil.InsertLink`. Item link: the second
  return of the hub's `Compat.GetItemInfo`; when the item is not loaded yet, ask for it and retry once. A recipe
  without an item (an enchant) needs a spell or recipe link: find the function in `/vendor-ref` or leave these
  rows unlinked and say so.
- **H8 (W18):** tests for the upstream fix under lupa (asked once; holds after Link; not asked again after Not
  now; holds with no officer online). `/amazing myalts` goes into `docs/addon/README.md`.
- **H9 (W19):** in the opened recipe: a "×N" box that multiplies the materials, and beside each material how
  many the guild bank holds (from the Bank data, when there is any).
- **H10 (W21):** an own file feeds upstream's member history where `GuildLedgerAPI.GetJoined` knows an earlier
  date for the current stay, marked estimated; a date an officer entered or read from a note is never replaced.
  Visibility per decision 6.

### Phase C — Item and recipe catalogue (W20)

**C1 Find the source, report, stop.** In this order: (a) wago.tools DB2 exports for the current Forever build:
`JournalInstance`, `JournalEncounter`, `JournalEncounterItem`, `ItemSparse`, `Item` (upstream generated
`Data/ProfCatalogForever.lua` and `Data/ForeverDungeons.lua` from that site); do Forever's dungeons and raids
have loot rows? (b) the game's Encounter Journal: upstream reads it on retail through `Compat.JournalLoot`; a
developer command lists what it returns on Forever. (c) if neither: a catalogue that grows from item links seen
in loot history, wishlists, the bank and guild chat.

**C2 Generator** `tools/build-catalog.py` → `addon/hub-extra/Data/ItemCatalog.lua` (item ID, English name,
quality, slot, instance and boss; header "Generated … do not edit"; at most 400 KB; loaded on Forever only) and
`shared/catalog/items.json`, `shared/catalog/recipes.json` (from the recipe catalogue: spell, name, profession,
materials, item made) for the bot.

**C3 Hub:** `Wishlist:RebuildItemIndex` also takes the catalogue on Forever, so the wishlist box and H2 find any
catalogue item, with its source shown. **C4 Bot:** `/wish add` gets autocomplete from `items.json`.

### Phase X — Hub data to the server (W8, W9)

**Built 2026-11-26** (`companion/guildledger/hubdata.py`, `shared/schema.md` 8, bot ingest and archive tables;
tests `companion/tests/test_hubdata.py`, `bot/tests/test_hub_bot.py`). Checked against the admin's real
AmazingHub.lua locally (counts only, nothing kept): ~1100 profession lines, 1 bank tab, money, 47 ledger lines,
7 alt links. Equal ledger lines in one hour stay apart (`…#n`). Nothing is posted yet: that is D4 and D5.

`companion/guildledger/hubdata.py`, same pattern as `loot.py` (which stays untouched). Write
`shared/schema.md` 8 first. Rows, in files of their own (`…-hub.jsonl.gz`):

| `type` | Content | Rule |
|---|---|---|
| `prof` | member, profession, skill, recipe IDs | key member + profession; newer `seen` replaces |
| `bank_tab` | tab, name, read time, read by, slots `[item, count]` | key tab; newer read time replaces |
| `bank_money` | time, copper | newest wins |
| `bank_log` | one ledger line with an ID built from its fields | insert-if-absent |
| `altlink` | alt, main, author, time, removed | key alt; newer time wins |

The exact hub tables are read from the re-pinned source and from a real `AmazingHub.lua` the admin supplies
privately (never committed); synthetic fixtures for the tests. The bot ignores unknown row types since 0.5.4;
still deploy the bot first.

### Phase D4 — Professions in Discord (W8)

**Built 2026-11-26** (`bot/guildledger_bot/community/crafts.py`, `crafts_ui.py`; the directory's forum bookkeeping
now serves any forum, `Directory.TABLE`; test `bot/tests/test_crafts.py`). Not deployed, not tried in Discord.

`/setup professions forum:`. One post per profession: the first message lists the crafters with their skill;
the following messages list recipes somebody knows, grouped, as "Recipe — Name, Name (+3)", edited in place by
hash. `/craft query:` with autocomplete over recipes and the items they make → who can craft it, last seen, the
materials. Names come from `shared/catalog/recipes.json`; an unknown ID is shown as its number.

### Phase D5 — Guild bank in Discord (W9)

**Built 2026-11-26** (`bot/guildledger_bot/community/bank.py`, `bank_ui.py`; item names for anything in the bank
from `shared/catalog/names.json`, new output of `tools/build-catalog.py`; test `bot/tests/test_bank.py`). Not
deployed, not tried in Discord.

`/setup bank channel: [ledger_channel:]`. One message per tab, edited in place: items by name with counts, when
and by whom it was read; the money. `/bank item:` with autocomplete → how many, in which tab. Ledger lines (who
put in or took out what) go only to the ledger channel, which should be officers only.

### Phase D6 — Linked Roles: dropped

Decision 9 (2026-11-24): not built. The number stays unused so the other phases keep their names. The bot
still opens no listening port (`CLAUDE.md` 7.5 stands).

### Phase D7 — Bots (W10)

**Built** with the 0.7.0 community work (`community/counters.py`, SERVER.md section 7); 2026-11-26: a second
`/setup counters` moves the existing channels instead of making another pair, `/setup show` lists them.

Section 9 goes into `docs/discord/SERVER.md` as the admin's checklist. Only one optional feature is built:
`/setup counters category:` keeps channel names such as "Guild members: N" and "Linked: N" current (a change at
most every 15 minutes), for the case that ServerStats is removed.

### Phase P — Publish and tidy

CurseForge text and changelog, `docs/addon/README.md`, the pinned Discord post from `MEMBERS.md`. Then tidy the
specification: decisions scattered over `CLAUDE.md` and `PACK_PLAN.md` ("Revision 2 overrides the rest") move
into one dated `docs/dev/DECISIONS.md`; finished plans move to `docs/dev/archive/`; `CLAUDE.md` keeps the facts,
the rules and the map. Nothing is deleted, only moved, and every link is checked.

## 8. Discord server checklist (admin, goes into `docs/discord/SERVER.md`)

- Channels: a verify channel (visible to everyone), a roles channel, a forum for characters, a forum for
  professions, a bank channel and an officers-only bank ledger channel.
- Roles: the bot's role above the gate role, the linked-member role, the rank roles and every interest and
  language role.
- Bot: the permissions of section 5 rule 6; in the forums and the bank channel members get no Send Messages.
- Members: remove "Change Nickname" from the member roles if nicknames should stay equal to the main.

## 9. The 14 bots on the server (judged by their commands, from the bot list of 2026-11-18)

| Bot | Verdict |
|---|---|
| Pandez Guard | replaced by D1; remove after the cutover |
| Invite Tracker | remove: invite tracking is not wanted now, its verify is replaced, giveaways and message counts exist twice |
| ServerStats | remove if the counters are not needed, or after the optional counters of D7 |
| Discohook Utils | if its welcomer is in use, D1 replaces it; keep the bot only if buttons on Discohook messages are used |
| Koya | overlaps with Dyno and Arcane; keep only for what is really used from it. Role menus set up in the Koya, Dyno or Arcane dashboard move to D2 |
| EasyPoll | Discord's built-in polls may be enough: the admin's call |
| Dyno | keep as the one moderation bot; switch off its poll and giveaway modules |
| Arcane | keep for levels; switch off its moderation commands |
| GiveawayBot, Ticket Tool, PatchBot, NotifyMe, Wowhead Bot, the music bot | keep |

Not jobs for our bot: moderation, tickets, giveaways, music, patch news, stream alerts, levels.

## 10. Answers to the admin's questions (keep in `docs/addon/README.md` where they fit)

- **Core sign-up.** A "core" is a fixed raid team an officer creates in Raids → Cores, with its own roster, loot
  rule and points. Core Sign-up lists the cores; a member picks one, a role and a note and presses Sign Up. The
  request is saved as pending and sent to the officers; an officer with the hub accepts (the member joins the
  core's roster) or declines. With no cores created the window is empty. Raids is off by default in the pack, so
  most members never see cores; after the re-pin the sign-up button lives inside Raids.
- **Map rate.** See G2: 10 s today, 3 to 10 s after G2.
- **Welcome.** A private message after the bot check (D1); a public line only if decision 12 names a channel.

## 11. Known limits (tell the admin, do not hide them)

- A link still waits for a collector's next `/reload` or logout; G3 and `/link approve` shorten it.
- The bot check stops scripts, not determined people.
- Recipes and the bank reach Discord only through collectors, so Discord shows the state of their last upload.
- Members without the pack show professions without recipes, as today.
- Join dates from before the archive began (about 2026-11-10) are "first seen" estimates.
- Alt tags and the Joined column on a member's client depend on what officers' clients synced.

## 12. Later (not in this plan)

Soft reserves per raid night from Discord; a way to bring server data back into the game (join dates and link
state for every client, wishlists without pasting a line); guest and alumni roles, invite tracking, removal of
unverified accounts; the loot and reward system and the cross-game honour idea.

Decided against (do not build unless the admin asks again): Discord Linked Roles.
