# GuildLedger row formats and ID rules

Shared contract between the addon (SavedVariables), the companion (spool.db, uploads) and the bot (archive).
Schema version **1**. Any change after Phase 2 needs a `schema` bump and a migration in all three (CLAUDE.md 10.6).

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

`cursor[<s>]` newest club ID up to which a history sync completed; `floor` unix s of the oldest row kept
after a ring-buffer trim (history sync never re-adds older rows); `opts` (`officer`, `other`, `debug`, `pageCap`).

### Roster entry (`roster["<GUID>"]`)

`n` name, `r` rank index, `rn` rank name, `l` level, `c` class file, `fs` first seen, `ls` last seen (unix s).

## 2. SQLite (spool.db on collectors, archive on the bot)

```sql
chat(guild, id, stream, ts_utc, author, guid, text, from_discord, edited, deleted, src,
     first_collector, posted, uploaded,               -- uploaded: companion only
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
   `text` where it is NULL (then `src` becomes `live`). Existing text is never changed.
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
`rowcount` counts chat and event rows, not the guild line. The bot takes the collector name from its own
webhook-ID list, never from the file. A row the companion changes after uploading it (text filled, flags,
actor) is uploaded again; the bot merges it by the rules above.
