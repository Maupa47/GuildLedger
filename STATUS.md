# GuildLedger — status

Last updated: 2026-11-13. Keep this file current when something changes (what runs, what is open).

## What runs right now

| Part | Where | Version / state |
|---|---|---|
| Bot | VPS `<server address>`, systemd `guildledger-bot` | deployed 2026-11-13 00:19 (schema-2 aware); archive ~9 300 chat rows, ~110 events |
| Collectors | the admin (Maupa) and two officers (listed in `[collectors]` of `bot/config.toml`) | companion in `mode = "upload"` → `#gl-ingest` |
| Addon on the admin PC | linked from the repo (`tools/install.ps1`) | **v0.2.1**, role collector |
| Members | one test member | had v0.2.0 (relay bug, see below), needs **v0.2.1** |
| Backups | VPS, daily 04:30, 14 days | restore check passed 2026-11-12 |
| Code | GitHub `Maupa47/GuildLedger` (private) | this commit |

Posting delay: bot holds chat 60 s (`hold_chat_seconds` in `bot/config.toml`). Discord can only be as current
as the last `/reload` or logout of any collector (WoW writes the addon's data only then).

## Done

- **Phase 0–6 (v1, all verified in game / on the server):** chat capture (live text paired with server IDs,
  history as "text not captured"), roster capture (system messages, roster comparison, guild event log),
  companion (parser, spool, export, direct posting, upload mode), bot (merge, archive, posting, backfill),
  VPS deployment with backups, hardening (timing 0.7–3 ms in game, ring buffers), README, officer package.
- **Phase 7 (v0.2, relay) — built, tests green (142), in-game test NOT passed yet:** one addon, two roles.
  Members (default) keep recent lines and answer a collector's "who has text for these times?" over hidden
  guild addon messages; collectors fill their gaps (CLAUDE.md 5.7, schema 2). Server already deployed with it.
  - First in-game try (2026-11-13 00:33): nothing was relayed. Cause found: the addon held all messages
    because `AreOutgoingAddonChatMessagesRestricted()` said "restricted" on this realm. Fixed in **v0.2.1**
    (the send result decides, like GuildOS); `/gl status` now shows messages sent/received and the last
    send result.

## Next steps (in order)

1. **Relay test with v0.2.1** (docs/INGAME_TESTS.md, Phase 7):
   - admin: `/reload` (repo-linked addon updates itself); member: replace the addon folder with
     `dist/GuildLedger-member-0.2.1.zip` (build it with `tools/package-collector.ps1` if `dist/` is empty).
   - both online ~30 s → `/gl status` on both: `last send result 0`, `received` > 0.
     If the result is 3/8/11 or `received` stays 0: screenshots of both `/gl status` + debug lines.
   - gap test: admin offline ~10 min while the member chats in guild, back online, wait 2 min →
     `/gl status` "filled N line(s) from members"; after `/reload` the lines reach Discord with text.
2. **The other collecting officers → v0.2.1:** new collector zip; replace the `GuildLedger` addon folder **and**
   `companion/guildledger` together (old companion refuses schema 2), keep their `config.toml`.
3. **Roll out to members:** pin `GuildLedger-member-0.2.1.zip` in the guild Discord.
4. Open check from Phase 6: boss fight / chat lockdown in game (write `/g` during an encounter → no Lua error,
   `caught up (+N)` after; the line arrives as "text not captured" or, with v0.2, may be filled by a member).
5. Later (v2 in CLAUDE.md): Discord slash commands `/seen`, `/joined`, `/activity` from the archive.

## Working on it from another machine

- `git clone https://github.com/Maupa47/GuildLedger.git`; tests: `pip install pytest lupa discord.py`, then
  `python -m pytest addon/tests companion/tests bot/tests` (no game, no Discord, no secrets needed).
- **Not in git (secrets, by design):** `bot/config.toml` (bot token, webhooks, collector IDs — the source for
  the server config) and `companion/config.toml` (your webhook). Without them you can code and test, but not
  deploy or collect. To deploy from another PC, copy `bot/config.toml` over yourself (not via git/chat) and
  have your SSH key for `<server>` there.
- Deploy code changes: `powershell -ExecutionPolicy Bypass -File .\tools\deploy.ps1`; config only:
  `… deploy.ps1 -UpdateConfig`. Never `-FirstTime` again (it was done; setup refuses to replace the archive).
- Server checks: README.md "Bot host" table (status, logs, archive stats, backup + restore check).
- Where things are explained: CLAUDE.md (spec and rules), shared/schema.md (formats, merge rules),
  docs/API_FINDINGS.md (what the game really does), docs/INGAME_TESTS.md (test steps per phase), README.md.

## Known limits

- Chat text only exists for lines a collector (or, with v0.2, a member) saw live and outside a boss fight;
  the rest is archived as "who wrote when". Server history reaches ~27 h back.
- Roster changes seen only by the roster comparison have a time window, not an exact time.
- Collectors and (since v0.2) members are trusted to send real text; relayed lines are checked against the
  server's message ID, author and time, and marked with who relayed them (`rb` / `relayed_by`).
