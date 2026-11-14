# GuildLedger row formats and ID rules

Shared contract between the addon (SavedVariables), the companion (spool.db, uploads) and the bot (archive).
Schema version **3** (since 2026-11-13; 2 → 3 adds `guilds[..].links` and the account key `link`;
before that: 1 → 2 adds the chat key `rb`, the archive column `relayed_by` and
`opts.collector`; schema-1 files and uploads stay readable). Any change needs a `schema` bump and a migration
in all three (CLAUDE.md 10.6).

## 1. SavedVariables (`GuildLedgerDB`)

See CLAUDE.md 5.2 for the full Lua layout. Per guild (`guilds["<clubId>"]`):

### Chat row

| Key | Type | Meaning |
|---|---|---|
| `id` | string | `"<epoch µs>:<position>"` (club ID, both `%.0f`) or `"ev|<t>|<author>|<hash8>"` for `src="event"` |
| `t` | int | unix seconds UTC (`floor(epoch / 1e6)`, or `GetServerTime()` for `event`) |
| `s` | string | stream: `g` guild, `o` officer, `d` discord, `x` other |
| `a` | string | author name as the client gives it (may contain a space: "First Last") |
| `g` | string? | author GUID |
| `m` | string? | text, control characters replaced by a space. **nil = text not captured** |
| `fd` | bool | came from Discord |
| `ed`, `del` | bool | edited / deleted |
| `src` | string | `live` (club ID + live text), `meta` (club ID, no text), `event` (live text, no club ID) |
| `rb` | string? | schema 2: the text was relayed in game by this member (CLAUDE.md 5.7); nil = captured by the collector itself |

### Roster event row

| Key | Type | Meaning |
|---|---|---|
| `id` | string | `sys`: `kind|target|actor|floor(t/5)`; `diff`/`log`: `kind|target|actor|<src>:floor(t/3600)` |
| `t` | int | unix seconds UTC. `sys`: when seen. `diff`/`log`: the **latest** possible time |
| `w` | int? | `diff`/`log` only: the **earliest** possible time (`diff`: previous trusted snapshot, nil when unknown; `log`: `t` − 1 h, or − 1 day when the log gave days) |
| `p` | bool | precise timestamp |
| `k` | string | `join`, `leave`, `kick`, `promote`, `demote` |
| `n` | string | target name |
| `g` | string? | target GUID |
| `by` | string? | actor name |
| `d` | string? | detail (new rank for promote/demote) |
| `src` | string | `sys`, `diff`, `log` |

`log` rows: `join`←`join`, `leave`←`quit`, `kick`←`remove`, `promote`/`demote` as named; for kick/promote/demote
`by` = player1, `n` = player2 (Phase 0: `invite` has player1 = inviter). Because elapsed hours shift as time
passes, the same log entry read later may land in the neighbouring hour bucket: a `log` row with the same
kind, name and actor within ±2 h of a stored one is the same event.

`w` was added in Phase 3, before any event row had been written by any version, so `schema` stays 1.

### Addon-only keys (ignored by companion and bot)

`opts.collector` (schema 2: true = collector role, false/nil = member); `cursor[<s>]` newest club ID up to which a history sync completed; `floor` unix s of the oldest row kept
after a ring-buffer trim (history sync never re-adds older rows); `opts` (`officer`, `other`, `debug`, `pageCap`).

### Roster entry (`roster["<GUID>"]`)

`n` name, `r` rank index, `rn` rank name, `l` level, `c` class file, `fs` first seen, `ls` last seen (unix s).

## 2. SQLite (spool.db on collectors, archive on the bot)

```sql
chat(guild, id, stream, ts_utc, author, guid, text, from_discord, edited, deleted, src,
     first_collector, posted, uploaded, relayed_by,   -- uploaded: companion only; relayed_by: schema 2
     PRIMARY KEY (guild, stream, id))
events(guild, id, ts_utc, precise, kind, name, guid, actor, detail, src,
       first_collector, superseded_by, posted, uploaded,
       PRIMARY KEY (guild, id))
members(guild, guid, name, first_seen, last_seen, in_guild, PRIMARY KEY (guild, guid))
guilds(guild PRIMARY KEY, name)
```

`guild` is the club ID as a string. `text` NULL = not captured. Booleans are 0/1.

## 3. Merge rules (chat)

1. Same `(guild, stream, id)` → same message. A later copy may set `edited`/`deleted` to 1 and may fill
   `text` where it is NULL (then `src` becomes `live`, `relayed_by` comes with it). Existing text is never
   changed. If the text-less row was already posted, it is posted again with its text as a late entry.
2. An `event` row (text, no club ID) whose author (GUID, else name) has a `meta`/`live` row in the same
   stream within ±3 s is not stored as its own row: it fills the text of a `meta` row, or is dropped
   when the row already has text.
3. A `meta` row arriving after such an `event` row takes over its text; the `event` row is removed if it
   was not yet posted or uploaded.

## 3b. Merge rules (events)

1. Same `id` → same event. A `sys` row within ±10 s of a `sys` row with the same kind, name and actor is the same.
2. A `log` row within ±2 h of a `log` row with the same kind, name and actor is the same.
3. `diff` rows of the same kind and member (GUID, else name) from different collectors whose windows `[w, t]`
   overlap are the same change: one row is kept, narrowed to the intersection of both windows.
4. `leave` and `kick` are one family ("gone"). A `diff`/`log` row is superseded by a `sys` row of the same
   family and name within ±12 h; a `diff` row also by such a `log` row. Superseded rows are never posted.

## 4. Upload file (companion → bot, `mode = "upload"`)

gzip-compressed JSON Lines, ≤ 500 KB per file. First line per guild: `{"type": "guild", "guild": "<clubId>",
"name": "<guild name>"}`; then one object per row:
`{"type": "chat"|"event", "guild": "<clubId>", "collector": "<name>", ...row keys as in section 1}`
(events also carry `w` when known). Upload-only key `pd: true`: this collector already posted the row
itself in direct mode; the bot archives it as posted and never posts it again (switching a collector
from direct to upload mode causes no duplicates). Message `content`: `gl1 <collector> <rowcount> <sha256 of the gz file>`;
`rowcount` counts chat and event rows (and a roster record as one row), not the guild line.
Roster record (pack step R, 2026-11-13): `{"type": "roster", "guild": …, "at": <rosterAt>, "members": [{g, n, r, rn,
l, c, fs, ls}, …]}` — the collector's whole trusted roster, sent once per new snapshot. The receiver updates every
listed member (first_seen only down, last_seen only up); only the newest snapshot (by `at`) sets `in_guild`, so a
late upload of an older list never marks anyone as gone. Members table gains `rank_name, rank_index, level, class`
(additive migration in companion and bot). **Deploy the bot before collectors get a companion that sends roster
records:** older bots reject the unknown record type. The bot takes the collector name from its own
webhook-ID list, never from the file. A row the companion changes after uploading it (text filled, flags,
actor) is uploaded again; the bot merges it by the rules above.

## 5. Addon messages and budgets (guild channel, prefix `GuildLedger`)

All kinds go through `Comms.lua`: one queue per client, **at most 1 message per second per client** (all
kinds together), priorities HIGH > NORMAL > BULK, at most 300 waiting (the oldest of the lowest priority is
dropped), held during a boss-fight lock or a throttle. Every message ≤ 255 bytes. Budgets below assume
**1 000 members, all online** (worst case); a typical evening has 100–200 online.

| Kind | Sender | When | Priority | Worst case, whole guild |
|---|---|---|---|---|
| `H` hello | everyone | 20 s after login, then every 15 min; once per answered `W` | NORMAL | 1 000 / 900 s ≈ 1.1 msg/s (67/min) |
| `W` who | whoever types `/gl who` | at most once per 60 s per asker | NORMAL | 1 per asker; answers: each player at most one `H` per 5 min, spread over 30 s → ≤ 1 000 `H` in 30 s (≈ 33/s) once per 5 min |
| `N` need | collectors | ~30 s after their history sync, on a member's first hello (≥ 2 min apart), every 15 min while gaps remain; ≤ 3 messages per round | NORMAL | with 5 collectors: ≤ 15 per 2 min |
| `T` line | members (and collectors) holding asked lines | after a `N`, 2–8 s delay, ≤ 150 lines per round, 1–3 messages per line; others back off while one answers | BULK | ≤ 450 per round, paced 1/s by the answering client |
| `G` got | collectors | every 5 s while lines arrived, ≤ 6 ids per message | NORMAL | ≤ 1 per 6 relayed lines |
| `V` map watch | players with the world map open (pins on) | on opening/changing the map, then every 30 s while open | HIGH | 1 per 30 s per viewer; 200 viewers ≈ 7/s |
| `L` link request | a member who typed `/gl link CODE` | at once, then every 3 min until a collector answers `Y`, at most 30 min | HIGH | ≤ 10 per linking member |
| `Y` link received | collectors | answer to `L`, ≤ 1 per code per minute | HIGH | ≤ 1 per `L` |
| `A` alt | characters of an account that requested a link | once per session, 45 s after login | HIGH | ≤ 1 per login of a linked account |
| `P` map position | players with sharing on (off by default) | only while a `V` for their zone or a parent map was heard in the last 45 s; ≤ 1 per 10 s, only after moving or every 30 s | HIGH | 50 sharers in one watched zone, all moving: 5/s; nobody looking: 0 |

Receivers: every online GuildLedger client receives every message; handling one is a table lookup (no
disk, no chat output). New kinds (map, link) must add their row here before code (docs/PACK_PLAN.md rule 9).

## 6. Discord link (schema 3, docs/PACK_PLAN.md section 10)

SavedVariables: collectors keep `guilds["<clubId>"].links` (ring buffer, 500): `{ id, t, k = "link"|"alt", code?, tag,
n = sender as the game gives it, g = GUID from the collector's roster if known }`; every account keeps `link =
{ tag, pending = { code, at, acked }, requested }`. Upload type `link` (same keys). Companion and bot table
`link_rows(guild, id, ts_utc, kind, code, tag, name, guid, first_collector, uploaded, processed)`.
Bot tables: `link_codes(code, discord_user_id, created_at, used_at)`, `links(guild, guid, name, discord_user_id, tag,
linked_at, via_collector)`, `link_blocks(discord_user_id, guild, guid)`, `link_confirms(id, discord_user_id, guild,
guid, name, tag, code, via_collector, created_at, status open|confirmed|rejected|expired, notified 0|1|2)`,
`link_user_state(discord_user_id, out_since)`. Only a confirmation by the Discord user creates a `links` row; "Not me"
adds a block.
