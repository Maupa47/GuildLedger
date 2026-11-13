# GuildLedger — build instructions for Claude Code

Working name: **GuildLedger** (rename freely; keep addon folder, TOC name and SavedVariables name in sync).
Revision 3, 2026-11-11 (Phase 0 results folded in; see docs/API_FINDINGS.md). Target: WoW: Forever client 1.60.1, Interface `16001`.
API facts in this revision were checked against (a) Blizzard's own API documentation files as shipped in build **1.60.1.70888** (mirror: `Gethe/wow-ui-source`, branch `forever`) and (b) the source of GuildOS, an MIT-licensed Forever guild addon that already reads server-side guild chat.

You (Claude Code) are building a guild-logging toolchain for a large WoW: Forever guild. Read this whole file before writing code. Sections 2 and 10 are hard constraints.

---

## 1. Goal

Must have (v1):

1. Log **guild chat**: who wrote what, when (exact timestamp), kept permanently outside the game.
2. Log **guild joins and leaves** (incl. kicks) with timestamps.
3. Push both to **Discord**, plus a durable archive (SQLite + plain-text export).
4. Work with **several collectors** (officers running the addon) without duplicate or missing entries.

Later (v2): slash commands in Discord (`/seen`, `/joined`, `/activity`), per-member activity report.

Non-goals: raid tools, loot, in-game UI beyond slash commands, anything that sends chat or performs guild actions.
(Hidden **addon messages** on the guild channel are allowed for the relay in 5.7 only; decided by the admin 2026-11-13.)

## 2. Platform facts (verified — do not contradict)

**Client**
- Forever is the retail (Midnight) client with game type `camelot`. Interface `16001`. Product folder during beta: `_classic_beta_`. Classic-only globals are gone; Midnight's Secret Values system applies in full.
- Addons have no network and no file I/O. Data leaves the game only through `SavedVariables`, written to disk on `/reload`, logout or exit. An external companion must read that file.
- Forever names can have a **surname** ("Lethaniel Blightwood"; the game spells it with a hyphen where a space is not allowed). Never split a name on `-` or a space to find a realm. Treat the full name string as opaque and prefer GUIDs as keys where available.

**Guild chat (C_Club) — confirmed in Blizzard's `ClubDocumentation.lua` for 1.60.1 and measured in game by GuildOS (2026-10-07)**
- The guild is a club: `C_Club.GetGuildClubId()`. `C_Club.GetStreams(clubId)` lists streams; `Enum.ClubStreamType`: `General=0, Guild=1, Officer=2, Discord=3, Other=4`. `streamType` is never secret. Officer is listed only to those who may read it.
- The **server keeps guild chat**. After login the Guild stream already held ~100 earlier messages; `C_Club.RequestMoreMessagesBefore(clubId, streamId, messageId?, count?)` fetches older ones, answered by `CLUB_MESSAGE_HISTORY_RECEIVED(clubId, streamId, downloadedRange, contiguousRange)`. How far back the server goes is still unmeasured.
- Read with `C_Club.GetMessageRanges(clubId, streamId)` → array of `{ oldestMessageId, newestMessageId }` (use the **last** range; ignore it if newest < oldest), then `C_Club.GetMessagesBefore(clubId, streamId, newestId, count)` or `C_Club.GetMessagesInRange(clubId, streamId, oldest, newest)`. Also `C_Club.GetMessageInfo`, `C_Club.IsBeginningOfStream`.
- `ClubMessageInfo = { messageId = { epoch, position }, content, author, destroyer?, destroyed, edited }`. `epoch` is **microseconds** since the UNIX epoch; there is no separate timestamp field. `epoch:position` is a stable, server-assigned ID, identical for every client.
- **`content` is a protected kstring (`kstringClubMessage`)**: addon code reads `"|Kw123|k"`, never the words; no API decodes it (Phase 0, 2026-11-11). C_Club therefore gives ID, exact time, author and GUID of every message (incl. history before login), but **no text**.
- `author` is a `ClubMemberInfo`. Phase 0 (2026-11-11) saw `guid` populated on every message, plus `name` (full name with surname, no realm), `classID`, `guildRank`, `memberId` and more. Use `guid` when present; still nil-check it. `author.discordInfo` (nilable) has `fromDiscord`, `globalName`, `lastOnlineName`.
- **Text comes only from the live `CHAT_MSG_GUILD` / `CHAT_MSG_OFFICER` event** (`text` is `cstring`, plain outside lockdown). Each live line pairs 1:1 with a `CLUB_MESSAGE_ADDED` for the same stream and author GUID; the two arrive 0–0.6 s apart in **either order**. `FocusStream` is not needed: `CLUB_MESSAGE_ADDED` fires without it.
- Events: `INITIAL_CLUBS_LOADED()`, `CLUB_STREAMS_LOADED(clubId)`, `CLUB_MESSAGE_ADDED(clubId, streamId, messageId)`, `CLUB_MESSAGE_UPDATED(clubId, streamId, messageId)`, `CLUB_STREAM_ADDED/REMOVED`, `CLUB_MEMBER_ADDED/REMOVED/UPDATED(clubId, memberId)`.
- `C_Club.FocusStream(clubId, streamId)` / `UnfocusStream` are what the Communities window calls when it shows a stream; they are not lockdown-restricted.
- Live event `CHAT_MSG_GUILD(text, playerName, …)`: `guid` is argument 12, `discordInfo` argument 18. `CHAT_MSG_OFFICER` and `CHAT_MSG_SYSTEM` share the layout.

**Secret Values / chat lockdown**
- `CHAT_MSG_GUILD`, `CHAT_MSG_OFFICER`, `CHAT_MSG_SYSTEM` payloads and every `C_Club` list/range/message function are `SecretInChatMessagingLockdown`. During a lockdown they return secrets.
- Test with the global `issecretvalue(v)` (exists; `canaccessvalue` also exists). Lockdown state: `C_ChatInfo.InChatMessagingLockdown()`. State change event: `ADDON_RESTRICTION_STATE_CHANGED(type, state)`.
- Addon code may pass a secret along but matching, comparing, concatenating, indexing with, or doing arithmetic on one **raises an error**. Always check first and return.

**Roster**
- `C_GuildInfo.GuildRoster()` requests a refresh; `GUILD_ROSTER_UPDATE` follows. Read with the globals `GetNumGuildMembers()` and `GetGuildRosterInfo(i)` (both in use on Forever). GUID is **return value 17**; name 1, rankName 2, rankIndex 3, level 4, classFile 11.
- `GetNumGuildMembers()` counts the whole guild regardless of "Show Offline Members". A roster is only trustworthy when the count is > 0 and **every** row returns a name; otherwise it is still loading.
- The **guild event log exists on Forever**: Blizzard's own `Blizzard_Communities/GuildInfo.lua` calls `QueryGuildEventLog()`, waits for `GUILD_EVENT_LOG_UPDATE`, then `GetNumGuildEvents()` and `type, player1, player2, rank, year, month, day, hour = GetGuildEventInfo(i)` with types `invite, join, promote, demote, remove, quit`. The time values are elapsed time (hour precision).
- System message format globals exist: `ERR_GUILD_JOIN_S`, `ERR_GUILD_LEAVE_S`, `ERR_GUILD_REMOVE_SS` (target, actor), `ERR_GUILD_PROMOTE_SSS`, `ERR_GUILD_DEMOTE_SSS` (actor, target, rank). Some locales (German) use numbered placeholders `%1$s` in a different order.

**Blizzard's native Discord link** (Forever since 2026-11-04) mirrors guild chat ⇄ one Discord channel, but in-game messages from members who have not linked their own Discord account are not shown in Discord, and joins/leaves are not reported. It is a complement, not a log. `C_GuildInfo.IsDiscordStreamSeparate()` tells whether Discord chat has its own stream (type 3).

## 3. Architecture

```
Collector PCs (any officer)                         Always-on machine (one)
┌──────────────────────────────┐                   ┌─────────────────────────────┐
│ WoW + GuildLedger addon      │                   │ GuildLedger bot             │
│   chat:   C_Club streams     │                   │  - reads uploads from       │
│   roster: system msgs + diff │                   │    #gl-ingest               │
│           + guild event log  │                   │  - merges/dedups into       │
│   -> SavedVariables file     │                   │    SQLite (the archive)     │
│        (on /reload, logout)  │                   │  - posts each row once to   │
│ Companion (Python)           │   Discord         │    #guild-chat-log and      │
│   parses file, keeps local   │ ───────────────►  │    #guild-roster-log        │
│   spool, uploads new rows    │  webhook upload   │  - v2: slash commands       │
└──────────────────────────────┘  (file attachment)└─────────────────────────────┘
```

- Discord is the transport between collectors and the bot. The bot only makes outbound connections, so it needs **no open port, domain or TLS setup**; it can run on a Raspberry Pi, NAS (Docker), home server or small VPS.
- Why merging is easy: chat rows carry the server's own ID, identical on every collector. Roster events get an ID from kind + target + a 5-second time bucket, so two collectors who saw the same join produce the same ID.
- **Single-collector mode** stays supported: the companion posts straight to two webhooks (`mode = "direct"`), no bot. Build this first; it is also the test path.
- Latency is bound to the collector's next `/reload` or logout. `/gl flush` triggers a reload. More collectors = shorter gaps and exact join/leave times more often.

## 4. Repository layout

```
/addon/GuildLedger/     GuildLedger.toc, Compat.lua, Store.lua, Core.lua, Chat.lua, Roster.lua, Relay.lua (5.7)
/addon/GLProbe/         Phase 0 throwaway probe addon
/companion/guildledger/ __main__.py, svparse.py, store.py, discord.py, upload.py, config.py
/companion/tests/       pytest; fixtures/*.lua (synthetic SavedVariables)
/bot/guildledger_bot/   __main__.py, ingest.py, merge.py, post.py, store.py
/bot/                   Dockerfile, guildledger-bot.service (systemd), config.example.toml
/shared/schema.md       row formats and ID rules used by addon, companion and bot
/docs/INGAME_TESTS.md   checklist the human runs after each phase
/docs/API_FINDINGS.md   what Phase 0 measured
/tools/install.ps1      junction addon folders into the Forever AddOns dir
/tools/deploy.ps1       pack code (no secrets/data), copy to the server over SSH, run bot/deploy/setup.sh
                        (-FirstTime: also config + archive; -UpdateConfig: config only; -DryRun: list only)
/tools/package-collector.ps1  dist/GuildLedger-collector-<version>.zip for another officer
/companion/start-companion.cmd  double-click starter for collectors
/docs/COLLECTOR.md      officer guide (in the collector zip); /docs/MEMBER.txt (in the member zip)
/README.md              admin + server operations; /STATUS.md what runs, what is done, what is next
/vendor-ref/            read-only reference checkouts (git-ignored), see section 9
.luacheckrc  .gitignore (config.toml, *.db, logs/, vendor-ref/)
```

## 5. Addon specification

### 5.1 TOC

```
## Interface: 16001
## Title: GuildLedger
## Notes: Logs guild chat and roster changes for export to Discord.
## Version: 0.1.0
## SavedVariables: GuildLedgerDB
Compat.lua
Store.lua
Core.lua
Chat.lua
Roster.lua
```

No libraries. Plain frames and an event table.

### 5.2 SavedVariables schema (`GuildLedgerDB`, account-wide; keep keys short)

```lua
GuildLedgerDB = {
  schema = 2,                -- 1 -> 2 (2026-11-13): chat key rb, opts.collector; nothing else changed
  meta = { addon = "0.1.0", writer = "<character name>", saved = 1731330000 },
  guilds = {
    ["<clubId>"] = {
      name = "Guild Name",
      chat = {            -- oldest first, ring-buffered
        { id = "1731329999123456:0",  -- "<epoch µs>:<position>", STRING
          t = 1731329999,             -- unix seconds UTC = floor(epoch / 1e6)
          s = "g",                    -- g=guild, o=officer, d=discord stream, x=other
          a = "First Last",           -- author name exactly as the client gives it
          g = "Player-…",             -- author GUID (nil-check anyway)
          m = "message text",         -- control chars replaced by a space; NIL when text unknown
          fd = false,                 -- came from Discord
          ed = false, del = false,
          rb = "Member Name",         -- schema 2: text relayed by this member (5.7); nil = own capture
          src = "live" },             -- "live" = club ID + live text | "meta" = club ID, no text
                                      -- | "event" = live text, no club ID (see 5.3)
      },
      cursor = { g = "1731329999123456:0" },   -- newest stored ID per stream
      roster = { ["Player-…GUID"] = { n="First Last", r=3, rn="Member", l=27, c="MAGE", fs=1731000000, ls=1731329000 } },
      rosterAt = 1731329000,       -- time of last trusted full snapshot
      ev = {              -- roster events, oldest first, ring-buffered
        { id = "join|First Last||346265999",   -- kind|target|actor|floor(t/5)
          t = 1731329999, p = true,            -- p = precise timestamp
          k = "join", n = "First Last", g = "Player-…", by = nil, d = nil, src = "sys" },   -- diff/log rows add w = earliest possible time (shared/schema.md)
      },
    },
  },
}
```

- Event kinds `k`: `join`, `leave`, `kick`, `promote`, `demote`. Sources: `sys` (live system message, precise), `diff` (roster comparison, `p=false`), `log` (guild event log, hour precision, `p=false`).
- `diff`/`log` IDs: `kind|target|actor|<src>:<floor(t/3600)>` (they are approximate; the bot merges them, see 7.3).
- Ring buffer: max 20 000 chat rows and 5 000 events per guild. The addon is a spool, not the archive.
- Microsecond epochs fit a double but may serialize in scientific notation: always build the ID with `string.format("%.0f:%.0f", epoch, position)`.

### 5.3 Chat capture (`Chat.lua`) — C_Club for IDs and times, live events for text

Revised after Phase 0: C_Club content is an unreadable kstring (section 2). Rows are built in two ways:

- **Live pairing (normal case, `src="live"`).** On `CHAT_MSG_GUILD` / `CHAT_MSG_OFFICER` (return if any payload value is secret): queue `{ stream, guid (arg 12), name (arg 2), text, fd = discordInfo.fromDiscord, at = GetTime() }`. On `CLUB_MESSAGE_ADDED` for the guild club and a selected stream: `C_Club.GetMessageInfo` → queue `{ stream, guid, name, id, epoch }`. Pair the oldest unmatched entries with the same stream and author GUID (fall back to name if a GUID is missing) whose `at` differ by ≤ 3 s; pairing works in either arrival order. Paired → one row with the club `id`, `t = floor(epoch/1e6)` and the text.
- After 5 s unpaired: a club entry → `src="meta"` row (no `m`); a chat entry → `src="event"` row (ID per fallback below, `t = GetServerTime()`).
- **History (`src="meta"`).** `SyncStream` below still runs at login and after a lockdown, but only adds rows the spool does not have yet, without text. These record that a message existed (who, when) while nobody was collecting.

The steps below describe `SyncStream` (history) and the event wiring; read "store rows" as "store `meta` rows for IDs not already in the spool".

1. Wait for clubs: on `INITIAL_CLUBS_LOADED` / `CLUB_STREAMS_LOADED` for the guild club (plus a 5 s retry timer after `PLAYER_ENTERING_WORLD`, max 12 tries). `clubId = C_Club.GetGuildClubId()`; if nil, stay idle.
2. Streams: `C_Club.GetStreams(clubId)`, select by `streamType` (1 guild; 2 officer only if `/gl officer on`; 3 discord; 4 other only if enabled). Never rely on list order. Skip any entry whose fields are secret.
3. Sync a stream (function `SyncStream`):
   - If `C_ChatInfo.InChatMessagingLockdown()` → set `needSync`, return.
   - `r = last of C_Club.GetMessageRanges`; if none → `C_Club.RequestMoreMessagesBefore(clubId, sid, nil)` and return (the history event re-enters).
   - Read `C_Club.GetMessagesBefore(clubId, sid, r.newestMessageId, 200)`; for each message check `issecretvalue` on `destroyed`, `messageId.epoch`, `content`, `author.name` first; store rows newer than the cursor (compare epoch, then position). Keep `destroyed` rows with `del = true` and empty text if content is unreadable.
   - If the oldest message read is still newer than the cursor and `not C_Club.IsBeginningOfStream(clubId, sid, r.oldestMessageId)` → `C_Club.RequestMoreMessagesBefore(clubId, sid, r.oldestMessageId, 200)` and continue on `CLUB_MESSAGE_HISTORY_RECEIVED`. Stop after 50 pages per login (configurable) or when the cursor is reached. First ever run: go back as far as the server allows up to the page cap.
4. Live: pairing as described above. `CLUB_MESSAGE_UPDATED` → re-read that message, set `ed` / `del`. Do not call `FocusStream` (Phase 0: not needed).
5. Lockdown end (`ADDON_RESTRICTION_STATE_CHANGED`, or a 5 s poll while `needSync`) → `SyncStream` for all streams. Lines written during a lockdown end up as `meta` rows: their text is lost.

Fallback path (`src = "event"`): a live line that found no club partner within 5 s. `t = GetServerTime()`, `id = "ev|" .. t .. "|" .. author .. "|" .. <8-hex hash of text>`. The bot merges an `event` row into a `meta` or `live` row with the same author (GUID, else name) within ±3 s.

Store text as the client gives it (hyperlinks and colour codes intact), only replacing control characters with a space. No parsing in Lua.

### 5.4 Roster capture (`Roster.lua`) — three layers

1. **Live system messages (exact time).** `CHAT_MSG_SYSTEM`; return if `issecretvalue(msg)`. Ignore everything in the first 8 s after login. Convert the client's own format globals to patterns at load: escape magic characters, support both `%s` and numbered `%1$s` placeholders and map captures back by number. Kinds: join, leave, kick (target, actor), promote/demote (actor, target, rank). `t = GetServerTime()`, `p = true`, ID per 5.2. After a join/leave, request a roster refresh.
2. **Roster comparison (covers offline time).** Request `C_GuildInfo.GuildRoster()` at login and at most once a minute; on `GUILD_ROSTER_UPDATE` debounce 1 s, then read all rows. Trust the snapshot only if count > 0 and every row has a name and GUID (not secret, not nil); additionally refuse it if more than 20 % of the stored roster would be gone. Compare by GUID: new → `join`, missing → `leave` (`src="diff"`, `t` = now; the true time lies between `rosterAt` and now). Skip a `diff` event when a `sys` event of the same kind for that name exists in the last 10 minutes. First snapshot ever creates no events.
3. **Guild event log (actor and approximate time for offline changes).** After each trusted snapshot that produced `diff` events, and once per login: `QueryGuildEventLog()` → on `GUILD_EVENT_LOG_UPDATE` read all entries, convert elapsed y/m/d/h to an approximate timestamp, map `join`→join, `quit`→leave, `remove`→kick (player1 = actor, player2 = target, confirmed in Phase 3: the log's `remove` for a kick by X lists X as player1), store with `src="log"`. Feature-detect all three functions. Phase 0: the log holds only 100 entries, index 1 = oldest; in a 550-member guild that is ~9 hours.

Cost: one pass over up to ~1000 rows per snapshot; no per-row string building beyond the name.

### 5.5 Slash commands

`/gl status` (guild, rows spooled, unsaved rows, last sync, lockdown, feature flags), `/gl sync`, `/gl flush` (`ReloadUI()`), `/gl officer on|off`, `/gl debug on|off`. Prefix output with `|cff33ff99GuildLedger|r:`.

### 5.6 Lua rules

- Lua 5.1. One file-local namespace (`local ADDON, ns = ...`). Globals only `GuildLedgerDB` and `SLASH_*`.
- Every Blizzard API call lives in `Compat.lua` behind an existence check; missing API disables the feature and shows in `/gl status`. No Lua errors on login, ever.
- `Compat.IsSecret(...)`: true if any argument is secret; false when `issecretvalue` does not exist.
- Wrap event handlers in `xpcall`; rate-limit error prints.
- Never send chat messages. Addon messages: only `Relay.lua`, only on the `GUILD` channel with the prefix
  `GuildLedger`, only the four kinds in 5.7, paced and held during lockdown (decision 2026-11-13).

### 5.7 Relay (`Relay.lua`): members fill collectors' text gaps (added 2026-11-13, schema 2)

One addon, two roles. **Member** (default for new installs): live chat capture only (rows with club ID and
text), no history sync, no roster; keeps at most 2 000 lines and 3 days. **Collector** (`/gl collector on`,
whoever runs the companion; existing schema-1 installs are migrated to collector): everything in 5.3/5.4,
plus asking members for its gaps. Role changes apply after `/reload`.

Verified API (ChatInfoDocumentation.lua, forever branch): `C_ChatInfo.RegisterAddonMessagePrefix(prefix)`,
`C_ChatInfo.SendAddonMessage(prefix, message, "GUILD")` → `Enum.SendAddonMessageResult` (0 Success,
3 AddonMessageThrottle, 8 ChannelThrottle, 11 AddOnMessageLockdown), `C_ChatInfo.AreOutgoingAddonChatMessagesRestricted()`,
event `CHAT_MSG_ADDON(prefix, text, channel, sender, …)` (not secret). Prefix ≤ 16 chars, message ≤ 255 bytes,
`SecretArguments = NotAllowed`.

Messages (fields separated by TAB; stored text never contains control characters):
- `H` version role(c|m) held — hello, 20 s after login.
- `N` stream ranges — collector: "who has text for these times?" `ranges` = `t1-t2,t3-t4,…` (unix s) built from
  its own text-less rows of the last 27 h (rows a few minutes apart form one range). Sent ~30 s after its history
  sync, when a member says hello (at most every 2 min) and every 15 min while gaps remain.
- `T` id k/n chunk — member: one line, split into n chunks of ≤ 200 bytes (UTF-8 safe). Chunk 1 starts with
  `stream TAB t TAB author TAB guid TAB fd TAB`, then the text.
- `G` id,id,… — collector: "have it"; every member deletes those lines.

Members answer a `N` after a random 2–8 s, at most 150 lines per `N`, and skip a line another member already
sent (they hear every `T`). Outgoing messages are paced to 1 per second, held during lockdown or a throttle,
queue capped at 300. A collector accepts a line only for a text-less row it already has with the same stream
and author GUID (else name); the row gets the text, `src = "live"` and `rb = <sender>` (relayed by). It never
replaces existing text. Rows the collector does not have are ignored (members expire them).

## 6. Companion (Python ≥ 3.11, stdlib only; runs on each collector PC)

- **Config** `config.toml`: `sv_path` (full path to `…\WTF\Account\<ACCOUNT>\SavedVariables\GuildLedger.lua`), `timezone = "Europe/Zurich"`, `mode = "direct" | "upload"`, `collector = "<name>"`; `[direct] chat_webhook, roster_webhook`; `[upload] ingest_webhook`. Webhook URLs are secrets: git-ignored, never logged.
- **Watch loop:** poll mtime/size every 2 s; read when changed and stable for 1 s; on parse error retry once, then wait for the next change. Never write to the SavedVariables file.
- **Parser** `svparse.py`: recursive descent for what WoW emits — top-level `Name = value`, tables with `["key"] =`, `[n] =`, positional entries, trailing `-- [n]` comments, strings with Lua escapes (`\"`, `\\`, `\n`, `\ddd`), numbers incl. exponent, `true/false/nil`. UTF-8 with `errors="replace"`. Test with quotes, backslashes, `|H` links, emoji, `]]`.
- **Local SQLite** (`spool.db`): same tables as the bot (7.2) plus `uploaded INT`. Insert-if-absent by ID.
- **mode = "direct":** post new rows to the two webhooks using the formatting rules in 7.4. First run marks existing rows as posted unless `--post-backlog`.
- **mode = "upload":** write new rows as gzip-compressed JSON Lines (`{"type":"chat"|"event","guild":…,"collector":…, …row}`), max 500 KB per file, and POST each as a file attachment to `ingest_webhook` with `content` = `gl1 <collector> <rowcount> <sha256>`. Mark rows uploaded on HTTP 2xx. Honour 429 `retry_after`.
- **Export:** `logs/<guild>/chat-YYYY-MM-DD.log` (`[YYYY-MM-DD HH:MM:SS] [G] Name: text`), `roster-YYYY.log`.
- **CLI:** `python -m guildledger watch | import <file> | export [--since] | stats`.
- Must also run on Linux; no Windows-only APIs.

## 7. Bot (Python ≥ 3.11, `discord.py`; one instance on an always-on machine)

### 7.1 Setup
- One Discord application/bot in the guild's server with the **Message Content** privileged intent enabled (needed to see webhook attachments). Permissions in `#gl-ingest`: View Channel, Read Message History, Add Reactions, Send Messages (for the ❌ reason). The bot posts to the two log channels through their **webhooks** (same formatting code as direct mode, `guildledger.direct.Poster`), so it needs no permission there.
- `#gl-ingest` is private (bot + admins). **One webhook per collector**, so a single collector can be revoked. Config lists allowed webhook IDs → collector names; uploads from any other author are ignored.

### 7.2 Storage (SQLite, WAL; this is the archive)
- `chat(guild, id, stream, ts_utc, author, guid, text, from_discord, edited, deleted, src, first_collector, posted, PRIMARY KEY(guild, stream, id))`
- `events(guild, id, ts_utc, precise, kind, name, guid, actor, detail, src, first_collector, superseded_by, posted, PRIMARY KEY(guild, id))`
- `members(guild, guid, name, first_seen, last_seen, in_guild, PRIMARY KEY(guild, guid))`
- `uploads(message_id PRIMARY KEY, collector, rows, sha256, received_at)` — an upload is processed once.

### 7.3 Merge rules
- **Chat:** insert-if-absent on `(guild, stream, id)`. A later copy may set `edited` / `deleted`, and may fill `text` (and `src` → `live`) on a row whose text is still NULL; it never changes existing text. An `event` row is merged into a `meta`/`live` row with the same author (GUID, else name) within ±3 s: it gives its text to a `meta` row, and is dropped otherwise. Hold `meta` rows 10 minutes before posting so a text-bearing copy from another collector can arrive; then post them as "(text not captured)".
- **Events (`sys`):** same ID → same event. Also treat IDs in the adjacent 5 s bucket with identical kind/target/actor as the same.
- **Events (`diff`, `log`):** if a `sys` event of the same kind and target exists within ±12 h (or inside the diff's window), mark the weaker one `superseded_by` and never post it. A `log` row supersedes a `diff` row for the same kind and target (better time, has actor). Hold `diff` rows 10 minutes before posting so a better row can arrive.
- Rows that arrive late (older than the newest already posted) are posted in a block headed "late entries" with their original times; never reorder or delete posted messages.

### 7.4 Posting
- Chat: batch lines into messages ≤ 1900 chars, `` `HH:MM` **Name**: text `` in local time, a date line when the day changes, a small marker for lines from Discord and for the officer stream.
- Roster: one embed per event — green join, red leave/kick, grey for approximate; show time (or time window), actor, source.
- Always `allowed_mentions = none`. Escape Discord markdown, neutralise `@everyone`/`@here`, turn WoW hyperlinks into `[Name]`, strip `|c…|r` and `|T…|t`.
- Set `posted` only after Discord confirms. Post in `ts_utc` order per channel. React ✅ on the processed upload message, ❌ plus a short reason on a rejected one.
- Deliverables: `Dockerfile`, systemd unit, `config.example.toml`, a `backfill` command that re-reads `#gl-ingest` history after downtime.

### 7.5 Deployment (decided and set up 2026-11-11: Infomaniak VPS Lite)

The host (replaces the earlier Hetzner plan):

| | |
|---|---|
| Provider | Infomaniak VPS Lite (Switzerland), server name `<server name>`, paid until 2027-11-11 |
| Size | 1 vCPU, 2 GB RAM, 20 GB NVMe; upgradable in place (~20 min downtime, then extend the volume) |
| OS | Ubuntu 26.04 LTS 64-bit, timezone Europe/Zurich |
| Address | `<server address>` (Porkbun; A `@` and A `*` → the VPS IPv4). Porkbun MX/SPF mail-forwarding records stay. |
| Login | `ssh <server>`, key auth only (admin's ed25519 key) |
| Firewall | Infomaniak firewall (manager → VPS → Firewall): inbound TCP 22 and ICMP only. On the host, ufw: deny incoming, allow outgoing, allow OpenSSH. |
| Already done (`server-baseline.sh`, idempotent) | apt upgrade; python3, python3-venv, sqlite3, git, unattended-upgrades, ufw, fail2ban installed; unattended security upgrades on; `/etc/ssh/sshd_config.d/10-hardening.conf` (PasswordAuthentication no, KbdInteractiveAuthentication no, PermitRootLogin no); fail2ban sshd jail (5 tries, 1 h ban); rebooted and verified |

- The bot must stay under ~150 MB RAM.
- The bot opens **no listening port**; no reverse proxy or TLS on this host. The domain is only for SSH.
- Provide `/bot/deploy/`:
  - `setup.sh` (idempotent): create system user `guildledger` (no login shell), install the venv under `/opt/guildledger`, data in `/var/lib/guildledger` (mode 700), config in `/etc/guildledger/config.toml` (mode 600, owner `guildledger`), install and enable the service and the backup timer. SSH hardening, ufw and unattended-upgrades are already done by the baseline; `setup.sh` may re-assert them idempotently but must not loosen them.
  - `guildledger-bot.service`: `Restart=always`, `RestartSec=10`, `User=guildledger`, `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ReadWritePaths=/var/lib/guildledger`, `PrivateTmp=yes`.
  - `backup.sh` + systemd timer (daily): `sqlite3 guildledger.db ".backup …"`, gzip, keep 14 days locally; optional upload of the newest backup as an attachment to a private `#gl-backup` channel so the archive survives loss of the server.
  - `update.sh`: `git pull`, reinstall into the venv, restart the service.
- Docker is optional; systemd + venv is the default path. Keep the `Dockerfile` working but do not require it.
- The bot token lives only in `/etc/guildledger/config.toml` on the server. Never in the repo, never on collector PCs.
- On start, the bot runs `backfill` automatically for uploads newer than its last processed one, so server downtime loses nothing.

## 8. Build order — stop after each phase for in-game verification

Claude Code cannot run WoW. After each phase update `docs/INGAME_TESTS.md` with exact steps and expected output, then **stop and ask the human to run them and paste results**.

**Phase 0 — GLProbe.** Most API questions are already answered (section 2). The probe only measures what is still open; `/glprobe` prints and saves to `GLProbeDB`:
1. `GetBuildInfo()` and `WOW_PROJECT_ID`.
2. Guild streams (`streamId`, `name`, `streamType`), message ranges, and the last 20 guild messages with **every field of `author` that is non-nil** (is `guid` present? is `name` plain text with surname?).
3. History depth: page back with `RequestMoreMessagesBefore` until `IsBeginningOfStream` or 30 pages; report the oldest date reached and the total count.
4. Without opening the guild window: do `CLUB_MESSAGE_ADDED` and new entries in `GetMessageRanges` appear when someone writes in /g? Repeat after `C_Club.FocusStream`. Log event names and counts only.
5. Guild event log: first 10 entries raw (confirm `player1`/`player2` roles for `remove` and `invite`).
6. `GetGuildRosterInfo(1)`: all return values, to confirm GUID at position 17.
7. Values of the five `ERR_GUILD_*` format strings on this client's locale.
8. After `/reload`: is the saved text in the file readable plain text?
Record results in `docs/API_FINDINGS.md` and adjust 5.3/5.4 before Phase 1.

**Phase 1 — Companion core** (no game needed): parser, spool DB, export, CLI, tests. Acceptance: `pytest` green; importing the same fixture twice adds zero rows.

**Phase 2 — Addon chat capture.** Acceptance: messages appear in the SavedVariables file after `/reload` with correct author and second-accurate time; messages written while logged out appear after next login; no Lua errors (BugSack); `/gl status` correct.

**Phase 3 — Addon roster capture.** Acceptance: a test character joining/leaving while the collector is online gives one precise event; while offline gives one `diff` (and a matching `log`) event at next login; `/reload` creates nothing new.

**Phase 4 — Direct Discord posting** (single collector). Acceptance: rows appear once, in order; restart posts nothing twice; `@everyone` and item links are harmless.

**Phase 5 — Bot + upload mode.** Acceptance: two collectors with overlapping data upload; every chat line and roster event appears exactly once; an upload from an unknown webhook is ignored; bot restart and `backfill` create no duplicates. Test merge rules with pytest fixtures before going near Discord.

**Phase 5b — Deploy to the VPS.** Acceptance: `setup.sh` on a fresh server brings the bot up; it survives a reboot; `systemctl status` clean; no port other than SSH answers from outside; the daily backup file restores into a working database.

**Phase 6 — Hardening:** ring buffer, timing with ~1000 members (`debugprofilestop()`), behaviour during a boss fight (lockdown), README with install steps for collectors and for the bot host.

## 9. Reference material (read, do not copy blindly)

Clone into `/vendor-ref/` (git-ignored) and consult before writing any WoW API call:

- **Blizzard UI source, Forever branch** — authoritative: `git clone --depth 1 --branch forever --filter=blob:none --sparse https://github.com/Gethe/wow-ui-source.git` then `git sparse-checkout set Interface/AddOns/Blizzard_APIDocumentationGenerated Interface/AddOns/Blizzard_Communities`. `ClubDocumentation.lua`, `ChatInfoDocumentation.lua`, `GuildInfoDocumentation.lua`, `DiscordDocumentation.lua` list every documented function, event, argument and `Secret*` flag. `Blizzard_Communities` shows how Blizzard's own guild window uses them.
- **GuildOS** (MIT) `https://github.com/danielcosta42/GuildOS` — `Core/Compat.lua` (search `GuildChatHistory`, `GuildChatStreams`, `IsSecret`, `InChatLockdown`), `Modules/GuildChat.lua`, `Modules/RosterLog.lua` (system-message parsing, 5 s event IDs), `Core/Utils.lua` (`MatchFormat`, `WholeRoster`), `docs/forever/README.md` (measured Forever behaviour), `tools/secret-values.lua` (how to unit-test secret handling under plain Lua).
- **DOINK** (MIT) `https://github.com/ryan-flan/DOINK` — `companion/` is a working SavedVariables-watcher that posts to a webhook.
- In game: `/api C_Club` and `/api C_GuildInfo` print the client's own documentation.

If code is reused from an MIT repo, keep its copyright notice in a `THIRD_PARTY.md`.

## 10. Rules for Claude Code

1. **Do not invent WoW API.** A function/event may be used only if it appears in section 2, in `/vendor-ref` for the `forever` branch, or in Phase 0 output. Your training data predates Forever; distrust it.
2. Secret Values: check, then bail out. Never branch on, concatenate, `tostring`, index with, or store a possibly secret value.
3. No network, file or OS access from Lua. No screen reading, memory reading, input injection or clientless bots in any component.
4. Small files, no frameworks in the addon, no UI beyond slash commands.
5. After each phase: summarise, list what the human must verify in game, and wait.
6. Schema changes after Phase 2 need a `schema` bump and a migration in Lua, companion and bot; update `/shared/schema.md` first.
7. Tests use synthetic data only. Never commit real chat, `config.toml`, databases or webhook URLs.

## 11. Known limits / open decisions

- **Where the bot runs: decided and set up** — Infomaniak VPS Lite `<server address>` (section 7.5). `mode = "direct"` remains for testing and as a fallback while the bot is not yet deployed.
- **Chat text exists only for lines written while at least one collector is online and not in a lockdown** (Phase 0: club history text is an unreadable kstring). Other lines are archived as "who wrote when" without text. More collectors online = fewer gaps.
- Server-side history depth: ~27 h / ~5 000 messages (Phase 2); older requests are silently ignored. This bounds the `meta` coverage, not the text.
- Messages bridged from Discord have no character name or GUID in the club; the author comes from `author.discordInfo` (`fd = true`).
- A character that joins and leaves entirely while no collector is online is visible only through the guild event log (last entries only).
- `diff` events have no exact time; shown as a window.
- Collectors are trusted: someone holding an ingest webhook can upload invented rows. One webhook per collector keeps this revocable and attributable.
- Privacy: this stores and republishes members' messages. Announce it in the guild info, keep the log channels officer-only, decide a retention period.

## 12. Existing addons checked (none cover the full requirement)

| Addon | Covers | Missing |
|---|---|---|
| Blizzard native Discord link | live guild chat ⇄ Discord | unlinked members' messages, joins/leaves, archive |
| GuildSpy (Forever) | joins, leaves, kicks, rank changes, in-game log | chat, export, Discord |
| GuildOS (Forever/Retail) | chat history tab (last 200 lines shown, not exported), roster log from system messages synced between officers in game | chat export, offline join/leave detection, leaves in Discord feed |
| Forever Guild Hub | guild chat history incl. offline (in game only) | export, Discord, roster log |
| DOINK + companion | SavedVariables → webhook pattern (own milestones only) | chat, roster |

## 13. Sources

- Blizzard API docs for 1.60.1.70888: https://github.com/Gethe/wow-ui-source/tree/forever
- GuildOS source and Forever notes: https://github.com/danielcosta42/GuildOS
- DOINK: https://github.com/ryan-flan/DOINK , https://www.curseforge.com/wow/addons/doink
- `C_Club.GetMessagesInRange`: https://warcraft.wiki.gg/wiki/API_C_Club.GetMessagesInRange
- Midnight API changes / Secret Values: https://warcraft.wiki.gg/wiki/Patch_12.0.0/Planned_API_changes
- Native Discord link in Forever: https://discord.com/blog/link-world-of-warcraft-with-discord , https://wowforeverinfo.com/news/discord-guild-chat-linking/
- Forever client facts: https://kami-labs.fr/en/addons-wow-forever/ , https://github.com/Thunderz96/forever-addon-kit
- GuildSpy: https://www.curseforge.com/wow/addons/guildspy
- Forever Guild Hub: https://www.curseforge.com/wow/addons/forever-guild-hub
