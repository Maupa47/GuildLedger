# Status

Last updated: 2026-11-19. Keep this file current when something changes. Overview of the project: [README.md](README.md).

## What runs right now

| | Where | State |
|---|---|---|
| **Part 1: addon pack** | | |
| Admin PC | linked from the repo (`tools\install.ps1`) | v0.5.4 (GuildLedger + Amazing Hub), role collector |
| Players | CurseForge "Amazing Forever Guild Pack" | 0.5.2 released; 0.5.3 built (upload state: see the admin); 0.5.4 ready in `dist\` |
| **Part 2: collection system** | | |
| Bot | the VPS (`<server>` = `[deploy] ssh` in `bot\config.toml`), systemd `guildledger-bot` | updated 2026-11-14 18:19 (link + activity commands, `server_id` set); archive ~9 300 chat rows |
| Collectors | the admin and two officers (`[collectors]` in `bot\config.toml`) | admin: up to date; the two officers: need the 0.5.4 collector zip (admin is checking with them) |
| Backups | VPS, daily 04:30, 14 days | restore check passed 2026-11-12 |
| Monitoring | `#gl-ops` | **off**: `[ops] webhook` empty (docs/collection/ADMIN.md section 5) |
| Code | GitHub `Maupa47/GuildLedger` (public) | CI runs every test on push |

Discord can only be as current as the last `/reload` or logout of any collector (WoW writes addon data only
then); the bot then holds chat 60 s before posting.

## Next steps (in order)

1. **Easy collector setup (0.6.0):** deploy the bot, Manage Webhooks in `#gl-ingest`, tag `v0.6.0`, then run
   checks E1–E8. After that officers are added with `/collector invite` and update by themselves. The two
   existing officers: invite them (new package, new link) or send them the 0.6.0 zip once; later updates are
   automatic either way.
2. **Discord roles:** `/roles verified …`, `/roles rank …`, `/roles show` (docs/collection/ADMIN.md section 2).
3. **Monitoring:** `#gl-ops` webhook (ADMIN.md section 5).
4. **In-game test rounds** (docs/dev/INGAME_TESTS.md): bridge round B1–B15 (alone: `/reload` is enough), pack
   round (relay, map, link, activity; needs a second player).
5. **Upload 0.5.4 to CurseForge** (docs/addon/CURSEFORGE.md) after the tests and the GuildOS author's answer.
6. Open decision: Discord nicknames (`set_nickname`). Later: delete the hub's unused upstream modules
   (docs/addon/HUB_AUDIT.md section 9).

## Done (newest first)

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
