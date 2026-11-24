# Status

Last updated: 2026-11-24. Keep this file current when something changes. Overview of the project: [README.md](README.md).

## What runs right now

| | Where | State |
|---|---|---|
| **Part 1: addon pack** | | |
| Admin PC | CurseForge copies in the AddOns folder (no longer linked from the repo: the CurseForge app deleted repo files through the links on 2026-11-24) | 0.6.0 |
| Players | CurseForge "Amazing Forever Guild Pack" | 0.6.0 |
| **Part 2: collection system** | | |
| Bot | the VPS (`<server>` = `[deploy] ssh` in `bot\config.toml`), systemd `guildledger-bot` | 0.6.0, deployed 2026-11-24 with the `[loot]` webhook; 3 collector webhooks |
| Collectors | the admin and two officers | officers: `/collector invite` still to do (bot needs *Manage Webhooks* in `#gl-ingest`) |
| Backups | VPS, daily 04:30, 14 days | restore check passed 2026-11-12 |
| Monitoring | `#gl-ops` | **off**: `[ops] webhook` empty (docs/collection/ADMIN.md section 5) |
| Code | GitHub `Maupa47/GuildLedger` (public) | CI runs every test on push; release `v0.6.0` published |
| **Part 3: Discord community** | | |
| Link, roles | the same bot | `/link`, `/roles`, lookups run since 0.4.0; link chain not yet verified in game (Phase 0 below) |
| Sign-up, role menus, character forum | the same bot | **built, not deployed** (pack 0.7.0, docs/dev/PLAN_COMMUNITY.md D1-D3) |

Discord can only be as current as the last `/reload` or logout of any collector (WoW writes addon data only
then); the bot then holds chat 60 s before posting.

## Next steps (in order)

1. **Phase 0 of the community plan:** run the checks in docs/dev/INGAME_TESTS.md "Community round 0.7.0" C0
   first (one member links a main and an alt through the whole chain), then E1–E8, D1–D8, B38–B48, M1–M6.
2. **Deploy the 0.7.0 bot** (`.\tools\deploy.ps1`), then set it up in Discord: docs/discord/SERVER.md
   (bot permissions, `/setup gate` in a test channel first, role menus, character forum). Checks C1–C14.
3. **Monitoring:** `#gl-ops` webhook (ADMIN.md section 5): the bot check and role menus report there.
4. **Addon 0.7.0** (login greeting after 30 s, faster map dots, link requests waiting, join dates): CurseForge
   upload after the in-game checks C15–C18.
5. **Re-pin the hub to GuildOS 1.40** (plan phase U): audit done (docs/addon/HUB_AUDIT.md section 10). Waiting for
   the admin: decision 7 (what acts for the player). Answered: alt tag for every link, copy the saved data over
   to the new key; then U2 on a branch.
   Item catalogue (phase C): `tools/build-catalog.py` → `shared/catalog/` (bot `/wish add` suggestions) and
   `addon/hub-extra/Data/ItemCatalog.lua` (hub search, wired in after the re-pin). Forever has no boss loot data.
6. GLMeterProbe: run `/glmeter` (M1–M6) so the result can be recorded and the probe removed.

Defaults in use until the admin decides otherwise (docs/dev/PLAN_COMMUNITY.md section 4): nickname = the main's
whole name (2); interests Raids, Dungeons, PvP, Levelling, Crafting, Social (3); everyone with the linked-member
role may look up others (5); Joined column officers only (6); no public "joined" line (12, `/setup announce`).
`!link CODE` in guild chat: kept, codes from guild chat live 10 minutes, the member still confirms in Discord,
our log channels mask the code (Blizzard's own Discord bridge does not; it is not working at the moment).
`/link approve` is named `/linkapprove`: Discord does not allow sub-commands under a command that is used on
its own (`/link`).

## Done (newest first)

- **0.7.0 community round (2026-11-24, built, not deployed, not tested against Discord or in game):**
  bot split into `collection/` and `community/`; hub sources in `addon/hub-extra/`. Discord: Verify button with a
  bot check, private welcome with a *Get my link code* button, `/setup …` (gate, welcome, addon, nickname,
  announce, rolemenu, directory, armory, show), `/main`, `/linkapprove`, `!link CODE` in guild chat, role menus for
  interests and 20 languages, right-click → Apps → Characters, `/whois` with suggestions and armory links, and a
  character forum kept up to date. GuildLedger: greeting after 30 s, map dots every 3–10 s with gliding, collectors
  see waiting link requests (hub: *Send now*), join dates from the first guild chat line (`GetJoined`, bot `/joined`).

- **0.6.0, easy collector setup (2026-11-19, not deployed, not tested on Windows or against Discord):**
  `/collector invite @officer` → the officer presses a button → the bot creates their webhook, registers it
  and hands them a zip with a finished `config.toml` (`/collector remove`, `/collector list`). The companion
  finds the WoW data files itself (every account, so alts on a second account count), installs Python through
  winget if missing, asks once about autostart, sends a test upload ("… is connected" in Discord) and updates
  itself from the GitHub release (settings never touched). Collector switch in the hub: Settings → Collector
  (officers). To switch on: `deploy.ps1`, give the bot **Manage Webhooks** in `#gl-ingest`, push tag `v0.6.0`
  (docs/collection/ADMIN.md sections 3 and 4). Checks E1–E8 in docs/dev/INGAME_TESTS.md.

- **Loot outside the game (2026-11-18, not deployed):** the companion also reads `AmazingHub.lua` (points log,
  standings, loot history, wishlists, raid nights); the bot archives it, posts to a loot channel (`[loot] webhook`)
  and answers `/dkp`, `/loot`, `/wishlist`, `/wish add|remove|list|export`; the hub's wishlist window imports the
  `/wish export` line. Order: bot first (`deploy.ps1`), then the officers' new collector zip (an old bot refuses
  the new upload files). Checks D1–D8 in docs/dev/INGAME_TESTS.md.
- **0.5.4 (2026-11-17/18):** login greeting with the guild message of the day (`/gl welcome`), own map dot off by
  default (`/gl map me`), sortable DKP and Professions columns, Settings → Loot opens on LOOT SYSTEM, wishlist import;
  and from 2026-11-17: developer mode (`/gl dev`, Settings → Chat messages): readable relay reports (history
  found, asked for, received from whom, still missing, complete); follow-up ask rounds ~65 s apart while lines keep
  coming; `/gl status` shows the missing text and who filled it.
- **0.5.3 (2026-11-15):** quiet chat by default with a Settings switch (`/gl messages`); map options: show
  members anywhere / on my continent / in my zone, dots per kind of map, names, "who sees me: my zone only".
- **0.5.2 (2026-11-15, on CurseForge):** Settings sections fold out; World map section with the dot look (shape, size,
  outline, class colours), map switches moved there from the Ledger tab; zips with standard paths.
- **0.5.1 (2026-11-14):** hub in the game's Classic look by default (Modern in Settings); Raids,
  Loot, Trials tabs off by default (Settings → Modules); docs sorted into addon / collection / dev; config examples
  rewritten with where-to-find-it comments (companion: `[general]` section, old layout still read); dead code
  and the Phase 0 probe addon removed.
- **Names and tabs:** nothing in game says GuildOS (hub = Amazing Hub, maker = Maupa; MIT notice kept in
  LICENSE, TOC metadata, THIRD_PARTY.md); Achievements, Alliance, Recruitment, Web tabs hidden; Discord link box.
- **Phase 10, bridge:** `GuildLedgerAPI` and the hub's Ledger tab (status, map switches, update notice).
- **Phase 9, Amazing Hub (0.5.0):** GuildOS fork generated by `tools/rebrand-hub.py`; talks only to guild,
  group and guild members; chat-posting features off. Hub test round passed (2026-11-14).
- **0.4.0 pack plan** (docs/dev/PACK_PLAN.md): message queue (`Comms.lua`), roster upload, world-map dots,
  Discord link (schema 3) with roles, activity commands `/seen`, `/joined`, `/activity`, `/inactive`.
- **0.2–0.3:** member/collector roles with relay of missed chat text (schema 2), `/gl who`, plain-language
  `/gl status`, silent by default, CurseForge package, `#gl-ops` report, CI, companion autostart.
- **Phases 0–6 (v1, verified):** chat capture, roster capture, companion, bot, VPS deployment with backups,
  hardening.

## Working on it from another machine

- `git clone https://github.com/Maupa47/GuildLedger.git`; tests: `pip install pytest lupa discord.py`, then
  `python -m pytest addon/tests companion/tests bot/tests` (no game, Discord or secrets needed).
- **Not in git (secrets):** `bot\config.toml` and `companion\config.toml`. Copy them over yourself (never via
  git or chat) to deploy or collect; also your SSH key for `<server>`.
- Never run `deploy.ps1 -FirstTime` again (setup refuses to replace the archive).

## Known limits

- Chat text exists only for lines a collector or member saw live and outside a boss fight; the rest is
  archived as "who wrote when". Server history reaches ~27 h back.
- Roster changes seen only by the roster comparison have a time window, not an exact time.
- Collectors and members are trusted to send real text; relayed lines are checked against the server's
  message ID, author and time, and marked with who relayed them.
