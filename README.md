# GuildLedger

Permanent log of a WoW: Forever guild's chat and roster changes (joins, leaves, kicks, promotions),
archived in SQLite and posted to Discord. Several officers ("collectors") can collect at once; their data
is merged so every line and event appears exactly once.

```
Officer PCs                                         Server (Infomaniak VPS, <server address>)
 WoW + GuildLedger addon --SavedVariables-->         guildledger-bot (systemd)
 companion (watch, mode "upload") --#gl-ingest-->     merges uploads into the archive (SQLite)
                                                      posts to #chat-log and #roster-log (webhooks)
```

- **Addon** (`addon/GuildLedger`): reads guild chat (text only while someone collects; message ID, author
  and time always) and roster changes (live system messages, roster comparison, guild event log).
  Data leaves the game only through its SavedVariables file on `/reload` or logout.
- **Companion** (`companion/`, Python stdlib only): watches that file, keeps a local spool and either posts
  directly to two webhooks (`mode = "direct"`, single collector) or uploads to `#gl-ingest` (`mode = "upload"`).
- **Bot** (`bot/`, discord.py): reads `#gl-ingest`, merges, archives, posts. Outbound connections only.

Design, rules and API facts: [CLAUDE.md](CLAUDE.md). Row formats and merge rules: [shared/schema.md](shared/schema.md).
Measured game behaviour: [docs/API_FINDINGS.md](docs/API_FINDINGS.md). Test checklists: [docs/INGAME_TESTS.md](docs/INGAME_TESTS.md).

## Adding an officer as a collector (admin)

1. Discord: `#gl-ingest` → *Edit Channel → Integrations → Webhooks → New Webhook*, name it after the officer.
2. Copy its URL. The number after `/api/webhooks/` is its **ID**. In `bot\config.toml` add under `[collectors]`:
   `<ID> = "<character name>"`.
3. Send it to the server: `powershell -ExecutionPolicy Bypass -File .\tools\deploy.ps1 -UpdateConfig`.
4. Build the package: `powershell -ExecutionPolicy Bypass -File .\tools\package-collector.ps1` →
   `dist\GuildLedger-collector-<version>.zip`.
5. Send the officer the zip, and the webhook URL privately (DM). They follow [docs/COLLECTOR.md](docs/COLLECTOR.md).

**Revoking** a collector: delete their webhook in Discord (takes effect at once) and remove their line from
`[collectors]` (`deploy.ps1 -UpdateConfig`). Their earlier rows stay in the archive.

## Your own setup (admin PC)

- Addon: `.\tools\install.ps1` links `addon\GuildLedger` into the AddOns folder (changes apply on `/reload`).
- Companion: `companion\config.toml` (git-ignored), started with `companion\start-companion.cmd` or
  `python -m guildledger --config config.toml watch` in `companion\`.
- Useful: `python -m guildledger --config config.toml stats`, `… export` (plain-text logs in `companion\logs\`).

## Bot host (server)

| Task | Command (PowerShell on the admin PC) |
|---|---|
| First install (done 2026-11-12) | `.\tools\deploy.ps1 -FirstTime` (sends code, `bot\config.toml`, `bot\archive.db`) |
| Update code | `.\tools\deploy.ps1` (config and data stay) |
| Change config (collectors, webhooks) | edit `bot\config.toml`, then `.\tools\deploy.ps1 -UpdateConfig` |
| Status | `ssh <server> "systemctl status guildledger-bot --no-pager"` |
| Logs | `ssh <server> "journalctl -u guildledger-bot -n 100 --no-pager"` |
| Archive stats | `ssh <server> "sudo -u guildledger /opt/guildledger/venv/bin/python -m guildledger_bot --config /etc/guildledger/config.toml check"` |
| Backup now + restore check | `ssh <server> "sudo systemctl start guildledger-backup && sudo -u guildledger /opt/guildledger/venv/bin/python -m guildledger_bot --config /etc/guildledger/config.toml verify-backup"` |

(Run scripts with `powershell -ExecutionPolicy Bypass -File …` unless you allowed local scripts with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.)

Layout on the server: code `/opt/guildledger/src`, venv `/opt/guildledger/venv`, config
`/etc/guildledger/config.toml` (600), archive `/var/lib/guildledger/guildledger.db`, daily backups
`/var/lib/guildledger/backups/` (04:30, kept 14 days; also posted to `#gl-backup` if `[backup] webhook` is set).
The bot opens no port; the firewall allows only SSH.

**Restore from a backup** (e.g. on a new server after `deploy.ps1 -FirstTime` without an archive):
```
ssh <server>
sudo systemctl stop guildledger-bot
sudo -u guildledger sh -c 'gunzip -c /var/lib/guildledger/backups/guildledger-YYYYMMDD-HHMMSS.db.gz > /var/lib/guildledger/guildledger.db'
sudo rm -f /var/lib/guildledger/guildledger.db-wal /var/lib/guildledger/guildledger.db-shm
sudo systemctl start guildledger-bot
```
The bot then catches up on every upload in `#gl-ingest` newer than the backup, without duplicates.

## Development

```
pip install pytest lupa discord.py
python -m pytest addon/tests companion/tests bot/tests
```
`addon/tests` run the real addon files under Lua 5.1 against a stub client (`addon/tests/wowstub.lua`).
All test data is synthetic. Never commit `config.toml`, databases, logs or real chat.

## Privacy

This stores and republishes members' guild chat. Announce it in the guild info, keep the log channels
officer-only, and decide how long to keep the archive.
