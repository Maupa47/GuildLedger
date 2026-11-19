# Collection system: admin guide

For the GuildLedger admin. Covers the part outside the game: Discord, the bot on the server, the officers'
collectors, monitoring and backups. (Players only need the addon pack: [../addon/README.md](../addon/README.md).)

```
Officer PCs (collectors)                                Server (bot, always on)
 WoW + addon --SavedVariables file--> companion  --upload-->  #gl-ingest  -->  guildledger-bot
                                                                               merges into the archive (SQLite)
                                                                               posts to the chat and roster log channels
```

Run every PowerShell command below in the repository folder. If PowerShell refuses scripts, prefix them with
`powershell -ExecutionPolicy Bypass -File`, or allow local scripts once with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## 1. Where every setting lives

| File | On which machine | Contains | How it gets there |
|---|---|---|---|
| `bot\config.toml` | your PC (master copy, git-ignored) | bot token, channel and server IDs, webhooks, collector list | copy of `bot\config.example.toml`, filled in by you |
| `/etc/guildledger/config.toml` | server | the same | `.\tools\deploy.ps1 -UpdateConfig` |
| `companion\config.toml` | each collector PC (git-ignored) | game file path, name, personal upload webhook | copy of `companion\config.example.toml`, filled in by the officer |

Every value has a comment in the example file saying where to find it. Secrets (token, webhook URLs) never go
into git, chat or screenshots.

## 2. Discord setup (once)

1. **Channels** (all private: you, officers, the bot):
   - `#gl-ingest`: collectors upload here (bot: View Channel, Read Message History, Send Messages, Add Reactions)
   - `#guild-chat-log` and `#guild-roster-log`: the bot posts here through a webhook each
   - optional `#gl-ops` (monitoring, section 5) and `#gl-backup` (section 6)
2. **Bot application**: https://discord.com/developers/applications → your app.
   - *Bot*: turn on **Message Content Intent**. *Reset Token* → put it in `[discord] token`.
   - *Installation*: scopes `bot` and `applications.commands`; permissions **Manage Roles** (for `/roles`),
     plus Manage Nicknames only if `set_nickname = true`. Open the install link and authorise your server.
3. **Server Settings → Roles**: drag the bot's role above every role it should hand out.
4. Fill in `bot\config.toml` (`[discord]`, `[post]`, `[collectors]`), then `.\tools\deploy.ps1 -UpdateConfig`.
5. **Roles for linked members**, in Discord as an officer: `/roles verified role:@guild-member`, then
   `/roles rank rank:<guild rank> role:<Discord role>` for each rank, `/roles show` to check, `/roles sync`
   to apply now.

Slash commands: `/link`, `/unlink`, `/chars`, `/whois`, `/seen`, `/joined`, `/activity`, `/dkp`, `/loot`,
`/wishlist`, `/wish add|remove|export|list`; officers (Manage Roles): `/linkstatus`, `/inactive`, `/roles`, and
`/wish` for anyone's characters (members only for their own linked ones).

### Loot channel (optional, Amazing Hub's DKP, loot, wishlists, raids)

The collectors' companions also send Amazing Hub's loot data (from `AmazingHub.lua`, no setting needed on their
side). Without a loot channel it is only archived and the commands above work. To get posts:
1. Create a channel `#guild-loot` (officers, or the whole guild if you want the standings public), then
   *Edit Channel → Integrations → Webhooks → New Webhook → Copy Webhook URL*.
2. In `bot\config.toml` under `[loot]`: `webhook = "<that URL>"`. Then `.\tools\deploy.ps1 -UpdateConfig`.
3. The bot then posts there: each item handed out (`🎁 Name got [Item] (Raid)`), each points change (one line per
   award, e.g. `+10 Boss kill: Ragnaros by <officer>: <names>`), and after every raid night one summary (bosses
   killed, attendance, loot, top 10 standings). Rows wait `hold_seconds` (10 minutes) so every collector's copy is
   merged first. Rows from before the bot's first start are archived, not posted.

The data exists only if officers use Amazing Hub's loot tools in game (Settings → Modules: Raids, Loot; Settings →
Loot → loot system "DKP / Points" for points). `/wish add` stores wishes in the bot; `/wish export` gives the
player a line to paste into the game.

## 3. Adding an officer as a collector

1. Discord: `#gl-ingest` → *Edit Channel → Integrations → Webhooks → New Webhook*; name it after the officer.
2. *Copy Webhook URL*. The number right after `/api/webhooks/` is the webhook **ID**. In `bot\config.toml`
   under `[collectors]` add: `<ID> = "<character name>"`.
3. `.\tools\deploy.ps1 -UpdateConfig`
4. `.\tools\package-collector.ps1` → `dist\GuildLedger-collector-<version>.zip`
5. Send the officer the zip, and the webhook URL **privately** (DM). They follow `COLLECTOR.md` in the zip
   ([COLLECTOR.md](COLLECTOR.md)).

**Revoking:** delete their webhook in Discord (effective at once) and remove their line from `[collectors]`,
then `-UpdateConfig`. Their earlier rows stay in the archive.

**Your own PC as a collector:** `.\tools\install.ps1` links `addon\GuildLedger` and `addon\AmazingHub` into
the game's AddOns folder (changes apply on `/reload`). The companion: `companion\config.toml`, started with
`companion\start-companion.cmd`. Plain-text logs: `python -m guildledger --config config.toml export` in
`companion\` → `companion\logs\`.

## 4. Server operations

Server: a small VPS, key login only. Below, **`<server>`** stands for its SSH login (`user@address`), which is
kept in your git-ignored `bot\config.toml` under `[deploy] ssh` (`deploy.ps1` reads it from there). The bot
opens no port; the firewall allows only SSH.

| Task | Command (PowerShell on your PC) |
|---|---|
| Update the bot's code | `.\tools\deploy.ps1` (config and archive stay) |
| Send changed settings | edit `bot\config.toml`, then `.\tools\deploy.ps1 -UpdateConfig` |
| See what would be sent | `.\tools\deploy.ps1 -DryRun` |
| Status | `ssh <server> "systemctl status guildledger-bot --no-pager"` |
| Logs | `ssh <server> "journalctl -u guildledger-bot -n 100 --no-pager"` |
| Archive stats | `ssh <server> "sudo -u guildledger /opt/guildledger/venv/bin/python -m guildledger_bot --config /etc/guildledger/config.toml check"` |
| Report for a day | same as above with `report` (add `--day YYYY-MM-DD` for another day) |
| Backup now + restore check | `ssh <server> "sudo systemctl start guildledger-backup && sudo -u guildledger /opt/guildledger/venv/bin/python -m guildledger_bot --config /etc/guildledger/config.toml verify-backup"` |

`deploy.ps1 -FirstTime` was used once to set up the server (it also sends the archive). Never run it again:
the server refuses to replace an existing archive.

On the server: code `/opt/guildledger/src`, venv `/opt/guildledger/venv`, settings
`/etc/guildledger/config.toml` (mode 600), archive `/var/lib/guildledger/guildledger.db`, backups
`/var/lib/guildledger/backups/`.

## 5. Monitoring (`#gl-ops`)

Optional. Every morning (06:00) the bot posts a report for the previous day: chat lines, share with text,
lines filled by members, longest stretches without text, uploads per collector, roster changes. It also warns
when no upload arrived for 6 hours and notes every rejected upload.

1. Create a private channel `#gl-ops` (only you and officers).
2. `#gl-ops` → *Edit Channel → Integrations → Webhooks → New Webhook* → *Copy Webhook URL*.
3. `bot\config.toml`, section `[ops]`: `webhook = "<paste the URL>"`. Optionally change `report_hour`
   and `alert_after_hours`.
4. `.\tools\deploy.ps1 -UpdateConfig`
5. Check: the "Report for a day" command in section 4 posts a report to `#gl-ops` right away.

Also: GitHub Actions runs all tests on every push (repository → *Actions*); in game `/gl status` shows the
relay state and which addon versions others run.

## 6. Backups

Daily at 04:30 on the server, kept 14 days. Optional off-server copy: create a private `#gl-backup` channel,
a webhook in it, put its URL in `[backup] webhook`, `-UpdateConfig`.

**Restore** (e.g. on a new server):
```
ssh <server>
sudo systemctl stop guildledger-bot
sudo -u guildledger sh -c 'gunzip -c /var/lib/guildledger/backups/guildledger-YYYYMMDD-HHMMSS.db.gz > /var/lib/guildledger/guildledger.db'
sudo rm -f /var/lib/guildledger/guildledger.db-wal /var/lib/guildledger/guildledger.db-shm
sudo systemctl start guildledger-bot
```
The bot then catches up on every upload in `#gl-ingest` newer than the backup, without duplicates.

## 7. Privacy

The system stores and republishes members' guild chat. Announce it in the guild info, keep the log channels
officer-only, and decide how long to keep the archive.
