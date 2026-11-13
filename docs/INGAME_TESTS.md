# In-game tests

Run these after each phase and paste the results back to Claude Code.
Use BugSack/BugGrabber (or `/console scriptErrors 1`) so Lua errors are visible.

---

## Phase 0: GLProbe

### Setup

1. In PowerShell from the repo root: `.\tools\install.ps1`
   (links into `D:\World of Warcraft\_forever_\Interface\AddOns`; pass `-AddOnsDir "<path>"` for another folder).
2. Start Forever, enable **GLProbe** in the AddOn list, log in with a character **in the guild**
   (ideally an officer). Stay out of combat and instances throughout.
3. **Do not open the guild/Communities window** (J / Ctrl+J) until step 6 says so. Item 4 depends on it.

### Steps

| # | Do | Expect / note down |
|---|---|---|
| 1 | Wait ~20 s after login, then `/glprobe` | Lines `1)` … `7)`, then `5) guild event log: N entries`. No Lua errors. If it says "no usable range yet" or "roster empty", wait 5 s and run `/glprobe` again. |
| 2 | `/glprobe depth` | `3) paging back…`, then within a few minutes `3) depth done (<reason>): P pages, M messages, oldest <date>`. Note the reason (`beginning`, `page cap`, `timeout…`). |
| 3 | Ask a guildmate (or a 2nd account) to write **3 lines** in `/g`. Still no guild window open. | — |
| 4 | `/glprobe live` | Copy the `4) unfocused:` line. Key values: `CLUB_MESSAGE_ADDED`, `CHAT_MSG_GUILD`, `range_grew`. |
| 5 | `/glprobe focus`, then have 3 more `/g` lines written, then `/glprobe live` | Copy both `4)` lines. Note whether any unread marker / blinking appeared on the guild micro button or chat after focusing. |
| 6 | Now open the guild window, Chat tab, and look at it. Close it. | Does the guild window show anything odd (unread count, jump)? |
| 7 | `/reload` | — |
| 8 | Open `WTF\Account\<ACCOUNT>\SavedVariables\GLProbe.lua` in a text editor. | Is message text readable plain text (umlauts/emoji correct, `|H…|h` links intact)? Are IDs like `"1731329999123456:0"` (not `1.7e+15`)? |

### Please paste back

- All `GLProbe:` chat lines (screenshot or copy from chat log).
- The whole `GLProbe.lua` SavedVariables file **with chat text and names replaced** by `X` if you
  do not want to share them (keep the structure, field names, `<secret>`/`<nil>` markers and IDs).
  At minimum: `build`, `chat.streams`, `chat.authorFieldCounts`, one `chat.messages` entry,
  `depth`, `live`, `roster.row1`, `formats`, `eventLog.first` (first 3), `eventLog.last` (last 3).
- For the event log: one `remove` and one `invite` entry, and who actually kicked/invited whom
  (from the guild window's log tab), so the `player1`/`player2` roles can be confirmed.
- Your answers on unread markers (step 5/6) and readability (step 8).

After Phase 0, just disable GLProbe in the AddOn list. `.\tools\install.ps1 -Remove` removes the junctions
if you want them gone.

**Do not commit** `GLProbe.lua` from SavedVariables: it contains real guild chat.

---

## Phase 1: Companion core (no game needed)

Nothing to test in game yet: the addon that writes `GuildLedger.lua` comes in Phase 2.

1. From the repo root, run the tests:
   ```powershell
   cd companion
   python -m pytest
   ```
   Expect: `51 passed`.
2. Optional, to see the CLI work on the synthetic fixture (writes into a scratch folder, not your WoW folder):
   ```powershell
   cd companion
   python -m guildledger --db $env:TEMP\gl-test\spool.db import tests\fixtures\basic.lua --no-export
   python -m guildledger --db $env:TEMP\gl-test\spool.db import tests\fixtures\basic.lua --no-export
   python -m guildledger --db $env:TEMP\gl-test\spool.db stats
   ```
   Expect: the first import says `chat +6 … events +5, members +3`, the second `chat +0 … events +0, members +0`;
   `stats` shows "Synthetic Guild" with 6 chat rows (5 with text, 1 without).
3. Optional: `pip install tzdata`. Without it Windows has no time-zone database and the companion uses the
   PC's local time instead of `Europe/Zurich` (same result if the PC is set to Swiss time).

---

## Phase 2: Addon chat capture

The `GuildLedger` folder is already linked into `D:\World of Warcraft\_forever_\Interface\AddOns`
(`.\tools\install.ps1` does it again if needed). Use `/console scriptErrors 1` or BugSack to see Lua errors.

### Steps

| # | Do | Expect / note down |
|---|---|---|
| 1 | In the AddOn list: **disable GLProbe**, **enable GuildLedger**. Log in on the guild character. | No Lua error. |
| 2 | Wait ~30 s, then `/gl status` | `guild <name> (club …), streams g`; `chat spooled N: 0 with text, N without`; `last sync: <time> page cap 50 (+N)` or `beginning of stream`. N up to ~5000 (the first run pages back through the server history). `errors: 0`. |
| 3 | Write 2–3 lines in `/g` yourself; note the exact in-game times. Let guildmates chat for a few minutes. Wait 10 s, `/gl status` | `this session: +X live` where X ≈ number of `/g` lines since login; `pending 0/0` after a few seconds. |
| 4 | `/gl officer on`, write one line in `/o`, wait 10 s, `/gl status` | `streams g,o`; live count +1. (Only if you can see officer chat.) |
| 5 | `/reload` (or `/gl flush`) | — |
| 6 | Log out for ~10 minutes while the guild keeps chatting, then log back in, wait 30 s, `/gl status` | `last sync … caught up (+M)` where M ≈ lines written while you were away. These rows have no text (expected). |
| 7 | Optional: run a dungeon boss fight while people chat in `/g`, then `/gl status` after the fight | `needs sync` goes back to `false` shortly after combat; lines from the fight are counted as "without text". No errors. |
| 8 | `/reload` once more, then tell Claude Code you're done. | — |

Claude Code then reads `D:\World of Warcraft\_forever_\WTF\Account\<ACCOUNT>\SavedVariables\GuildLedger.lua`,
checks authors/times against what you noted in step 3, and imports it into a scratch spool with the companion.

### Developer tests (no game)

`addon/tests/` runs the real addon files under LuaJIT against a stub client (`wowstub.lua`):
```powershell
pip install lupa        # dev only; not needed by collectors
python -m pytest addon/tests companion/tests
```

### Phase 2b — messages from Discord (after the Phase 2 run)

1. `/reload` with `/gl debug on`.
2. Have someone write a line in the guild's linked Discord channel (or write one yourself from Discord) while you are online. Also write one line yourself in `/g`.
3. Wait ~10 s. Expected grey debug lines: `club g message without GUID: author {discordInfo,…}, discord yes`, and, if the game shows the Discord line in chat, `chat g from Discord: name …, guid …, discordInfo {…}`.
4. `/gl status`: `this session: +2 live` if the Discord line paired, otherwise `+1 live, +1 meta`. No errors.
5. `/reload`, then report. The Discord row in the file should have the sender's Discord name as `a` and `fd = true`.

## Phase 3: Addon roster capture

`/reload` loads the new `Roster.lua` (the files are junctioned). Keep `/gl debug on`.

### Steps

1. **First snapshot.** `/reload`, wait ~30 s, `/gl status`. Expected:
   `roster: 550 members stored, last snapshot HH:MM:SS (first, 550 members, +0 joined, -0 left)` and
   `event log HH:MM: 100 entries, +N new` (N = joins/leaves/kicks/rank changes in the last ~9 h: real history).
   If it says `not loaded (…)`, wait a minute and run `/gl status` again.
2. **Live (precise).** If you have an alt and invite rights: invite it and have it accept, then `/gquit` with it
   (or kick it). Each should print a grey `roster sys join: Name` / `roster sys leave: Name` /
   `roster sys kick: Name by You`. No alt? Just keep playing; real joins/leaves in a guild this size show the same lines.
3. **Kick roles (open Phase 0 question).** If you kicked someone: open the guild's event log in the guild window
   and check that it reads "You kicked Name". The saved file then tells me whether `remove` lists actor first.
4. **Offline (diff + log).** Log out for 1–2 hours, log back in, wait ~30 s, `/gl status`. Expected: the
   snapshot line shows `+X joined, -Y left` matching what happened while you were away, and the event log
   adds about the same entries again with actor names (for kicks).
5. **No duplicates.** `/reload`, wait 30 s, `/gl status`: `roster this session: +0 sys, +0 diff, +0 log`.
6. `/reload` once more and tell me you're done. I read the file and import it into a scratch spool.

### Developer tests (no game)

`python -m pytest addon/tests companion/tests` (needs `lupa`): `test_addon_roster.py` covers first
snapshot, live sys events, the login quiet period, offline diff+log, reload / hour-bucket drift, a roster
still loading, mass removal guard, lockdown, numbered (German) format strings, player links, missing API,
and the companion merge (diff < log < sys, leave/kick family, time window in the export).

## Phase 4: Direct Discord posting (single collector)

### Setup (once)

1. In Discord, create two **private, officer-only** channels (e.g. `#guild-chat-log`, `#guild-roster-log`).
   For each: *Edit Channel → Integrations → Webhooks → New Webhook → Copy Webhook URL*.
2. In `companion/`, copy `config.example.toml` to `config.toml` (git-ignored) and fill in `sv_path`,
   `collector`, and the two URLs under `[direct]`. Never paste the URLs anywhere else.
3. Optional: `pip install tzdata` so `timezone = "Europe/Zurich"` is used exactly (otherwise the PC's local time).

### Steps

1. Preview, sends nothing: `cd companion` then `python -m guildledger --config config.toml post --dry-run`.
   Expected: `(dry run, nothing sent) posted 0 chat row(s) … N older row(s) marked as posted without posting (first run)`.
   (With `--post-backlog` the preview shows everything already spooled.)
2. Start it: `python -m guildledger --config config.toml watch`. Expected log:
   `Discord: posted 0 chat row(s)… N older row(s) marked as posted…` (first run skips the backlog). Leave it running.
3. In game write a few `/g` lines, including `@everyone test` and an item link (shift-click an item), then `/reload`.
   Within a few seconds: the lines appear in the chat channel, once, in order, with `HH:MM`. `@everyone` pings
   nobody, the item shows as `[Item Name]`.
4. Roster: a live join/leave/kick/promote appears in the roster channel as a card (green join, red leave/kick,
   blue promote) after the next `/reload`. Roster-comparison and guild-log cards wait 10 minutes and are grey.
5. Stop `watch` (Ctrl+C), start it again, `/reload` in game without writing anything: nothing is posted twice.
6. Report: screenshots of both channels, and the `watch` console output (it never prints the webhook URLs).

## Phase 5: Bot + upload mode (run the bot on your PC first; the server comes in Phase 5b)

### A. Discord setup (once)

1. **Bot application.** https://discord.com/developers/applications → *New Application* (e.g. "GuildLedger").
   - *Bot* tab: *Reset Token* → copy it (shown once; keep it only in the bot's config file).
     Under *Privileged Gateway Intents* turn on **Message Content Intent**, save.
   - *Installation* (or *OAuth2 → URL Generator*): scope `bot`; permissions **View Channels, Read Message
     History, Add Reactions, Send Messages**. Open the generated link and add the bot to your server.
2. **`#gl-ingest`**: private channel. In its permissions add the bot (the four permissions above).
   Only admins and the bot should see it.
3. **One webhook per collector** in `#gl-ingest` (*Edit Channel → Integrations → Webhooks*), named after the
   officer. Its **ID** is the long number right after `/api/webhooks/` in the URL.
   For this test make two: `Maupa` and `Test2`, plus a third `Stranger` that you will NOT list in the bot config.
4. **Channel ID**: *User Settings → Advanced → Developer Mode* on; right-click `#gl-ingest` → *Copy Channel ID*.

### B. Bot on your PC (test)

1. `pip install "discord.py>=2.4,<3"`
2. Copy `bot/config.example.toml` to `bot/config.toml` (git-ignored) and fill in: token, ingest_channel_id,
   `[collectors]` with the IDs of `Maupa` and `Test2`, the two log-channel webhooks under `[post]`,
   `hold_chat_seconds = 60` (test only; 600 later), and `db_path = "archive.db"`.
3. `cd bot` then `python -m guildledger_bot --config config.toml check` → `config ok …`.
4. `python -m guildledger_bot --config config.toml run` → `connected as GuildLedger#…`. Leave it running.

### C. Companion in upload mode

1. Stop the companion's `watch` (Ctrl+C). In `companion/config.toml` set `mode = "upload"` and
   `ingest_webhook` = the **Maupa** webhook URL. Start `watch` again.
2. First upload sends the whole spool (~6 000 rows, a few files). Each upload message in `#gl-ingest` gets ✅.
   Nothing older than the bot's first start is posted (direct mode posted it already).
3. In game write a few `/g` lines, `/reload`. Expected: a new upload with ✅; about 1 minute later the lines
   appear in the chat log channel, once.

### D. Second collector, unknown webhook, restarts

1. Second collector (simulated): copy `companion/config.toml` to `companion/test2/config.toml`; set
   `collector = "Test2"`, `ingest_webhook` = the **Test2** URL. Run in a second window:
   `python -m guildledger --config test2/config.toml watch` (own spool in `test2/`; reads the same game file).
   Expected: Test2's uploads get ✅, but **nothing new** appears in the log channels (same rows = merged).
2. Unknown webhook: stop Test2's `watch`, set its `ingest_webhook` to the **Stranger** URL, start it again,
   then write a `/g` line and `/reload`. Expected: two uploads appear; Maupa's gets ✅, the Stranger one gets
   no reaction and changes nothing (the line is posted once, from Maupa's upload).
3. Bot restart: Ctrl+C the bot, write a few `/g` lines and `/reload` (upload lands while the bot is down),
   start the bot. Expected: it processes the missed upload (✅), posts those lines once; nothing older twice.
4. Report: screenshots of `#gl-ingest` and both log channels, and the bot's console output.
   Then delete `companion/test2/` and the Test2/Stranger webhooks.

## Phase 5b: Deploy to the server (Infomaniak VPS, <server address>)

Everything runs from PowerShell on your PC; `tools/deploy.ps1` packs the code (no secrets, databases or
logs), copies it over SSH and runs `bot/deploy/setup.sh` on the server.

1. Bot on the PC must be stopped (uploads wait in `#gl-ingest` meanwhile; nothing is lost).
2. `ssh <server> "echo ok"` → `ok` (key login works).
3. `cd <your GuildLedger folder>` then `.\tools\deploy.ps1 -DryRun` (lists files, sends nothing),
   then `.\tools\deploy.ps1 -FirstTime`. Expected at the end: `config ok …`, `active (running)`,
   `connected as Chatlogger#…`, the uploads made while the PC bot was off processed (✅), listening ports
   only `0.0.0.0:22` / `[::]:22` (and `127.0.0.53` / `127.0.0.54` from systemd-resolved, local only).
4. Write a `/g` line in game, `/reload`: ✅ in `#gl-ingest`, line in the log channel after ~10 minutes
   (server hold is 600 s).
5. Reboot test: `ssh <server> "sudo reboot"`, wait 1 minute, then
   `ssh <server> "systemctl is-active guildledger-bot; systemctl list-timers guildledger-backup.timer --no-pager"`
   → `active` and the next backup time.
6. Backup + restore check: `ssh <server> "sudo systemctl start guildledger-backup && sudo -u guildledger /opt/guildledger/venv/bin/python -m guildledger_bot --config /etc/guildledger/config.toml verify-backup"`
   → `backup … restores into a working database: {'chat': …, 'events': …, 'uploads': …}`.
7. Ports from outside (on the PC): `Test-NetConnection <server address> -Port 22` → `TcpTestSucceeded : True`;
   `-Port 80` and `-Port 443` → `False`.
8. Logs any time: `ssh <server> "journalctl -u guildledger-bot -n 50 --no-pager"`.
   Update after code changes: `.\tools\deploy.ps1` (without -FirstTime: config and data stay).

## Phase 6: Hardening

1. **Timing.** After a normal session (login, some chat, a few minutes), `/gl status` shows a line
   `timing ms last/max: history step …, roster snapshot …, event log read …`. Expected: every max well under
   50 ms (a frame at 60 fps is 16 ms; a noticeable hitch is > 100 ms). Screenshot it.
2. **Boss fight / chat lockdown.** In an instance during an encounter (or any time `/gl status` says
   `lockdown on`):
   - write a `/g` line during the fight → no Lua error (BugSack / error popup), `/gl status` works;
   - after the fight, within ~10 s: `last sync: … caught up (+N)`; the line from the fight is spooled
     without text (expected: the game hides chat from addons during lockdown);
   - after `/reload` it reaches Discord as `… message(s) … text not captured`.
3. **Collector package.** `powershell -ExecutionPolicy Bypass -File .\tools\package-collector.ps1`
   → `dist\GuildLedger-collector-0.1.0.zip`. Optional: give it to one officer with their own webhook
   (README "Adding an officer") and check their uploads get ✅.
4. **Starter.** Close your companion window; double-click `companion\start-companion.cmd` → window
   `GuildLedger companion` with `watching …`.

## Phase 7: Relay (members fill collectors' gaps) — v0.2.0, schema 2

Update order: server first (`deploy.ps1`), then every collector's addon **and** companion together (an old
companion refuses a schema-2 file), then members.

1. **Your addon stays a collector.** `/reload` → `/gl status` shows `collector on` (old installs are migrated).
2. **A member.** One guild member installs `GuildLedger-member-0.2.1.zip`. On their side `/gl status` shows
   `relay: role member; holding N line(s)`.
3. **The gap test.** You log out; the member stays online while the guild chats ~10 minutes; you log in and
   wait ~2 minutes (history sync, then the ask), then `/gl status` → `filled N line(s) from members`.
   Member side: `holding` goes down (confirmed lines are dropped).
4. `/reload`: those lines reach Discord with their text (lines already posted as "text not captured" come
   again as a late entry).
5. With `/gl debug on`: grey `relay: asking for text gaps …` (you) and `relay: … needs … ranges; I have …`
   (member).
