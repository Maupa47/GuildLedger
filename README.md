# GuildLedger / Amazing Forever Guild Pack

Guild tools for a WoW: Forever guild, made by Maupa. The project has **three parts**:

| Part | What it is | Who uses it | Code | Guide |
|---|---|---|---|---|
| **1. The addon pack** | Two in-game addons: **GuildLedger** (silent chat helper) and **Amazing Hub** (guild window, `/amazing`). Published on CurseForge as *Amazing Forever Guild Pack*. | every player | `addon/` | [docs/addon/README.md](docs/addon/README.md) |
| **2. The collection system** | Turns what the addon sees into a permanent archive and Discord log: a **companion** program on officers' PCs and the **bot** on the server. Never public. | officers (collectors) and the admin | `companion/`, `bot/guildledger_bot/collection/` | officers: [companion/COLLECTOR.md](companion/COLLECTOR.md) · admin: [docs/collection/ADMIN.md](docs/collection/ADMIN.md) |
| **3. The Discord community** | What members see and do in the guild's Discord: sign-up with a bot check, link their characters, nickname and roles, role menus, character lookups and a character forum. The same bot. | every Discord member; the admin sets it up | `bot/guildledger_bot/community/` | members: [docs/discord/MEMBERS.md](docs/discord/MEMBERS.md) · admin: [docs/discord/SERVER.md](docs/discord/SERVER.md) |

```
 PART 1: in the game (every player)       PART 2: outside the game (officers + server)       PART 3: Discord
 ┌───────────────────────────────┐        ┌──────────────────────┐    ┌──────────────────┐    ┌───────────────┐
 │ GuildLedger addon  Amazing Hub│ data   │ companion (officer PC)│──► │ bot: collection  │──► │ bot: community│
 │  members keep recent chat     │ file   │  reads the file,      │#gl-│  merges, archives│    │  sign-up, link│
 │  lines; collectors also log   │──────► │  uploads new rows     │ing.│  posts to the log│    │  roles, forum,│
 │  history and roster; hidden   │/reload └──────────────────────┘    │  channels        │    │  /whois, /seen│
 │  addon messages fill gaps     │ logout                             └──────────────────┘    └───────────────┘
 └───────────────────────────────┘
```

Players need only part 1. Without part 2 the addons still work; nothing reaches Discord. Part 3 reads the
archive of part 2 (one bot process, one database), so links and character lists are as current as the last
collector upload.

> **Names.** **GuildLedger**: the silent addon (`/gl`). **Amazing Hub**: the guild window (`/amazing`; some call it
> "the guild ledger" too). **The pack**: both addons together, *Amazing Forever Guild Pack* on CurseForge.
> **The bot**: our one Discord bot on the server (parts 2 and 3). **Collector**: an officer whose PC runs the
> companion and whose GuildLedger is switched to the collector role.

## Repository map

| Path | Part | Contents |
|---|---|---|
| `addon/GuildLedger/` | 1 | the GuildLedger addon (Lua) |
| `addon/AmazingHub/` | 1 | Amazing Hub, **generated** by `tools/rebrand-hub.py` from GuildOS: never edit by hand |
| `addon/hub-extra/` | 1 | the hub's own files (Ledger tab, pack settings, chat tag, …), copied in by the script |
| `addon/tests/` | 1 | addon tests (run the real Lua against a stub game client) |
| `companion/` | 2 | the collector program (Python, stdlib only), its starters and `config.example.toml` |
| `bot/guildledger_bot/collection/` | 2 | the bot's collection side: uploads, archive merge, log posts, collectors, monitoring, backups, loot |
| `bot/guildledger_bot/community/` | 3 | the bot's community side: sign-up, link, `/setup`, roles and role menus, character forum, lookups |
| `bot/` | 2+3 | `__main__.py`, `client.py`, `config.py`, `store.py` (shared), `config.example.toml`, server files in `bot/deploy/` |
| `shared/schema.md` | all | data formats and ID/merge rules shared by addon, companion and bot |
| `tools/` | — | `install.ps1` (link addons into the game), `package-collector.ps1` (build both zips), `deploy.ps1` (update the server), `rebrand-hub.py` |
| `docs/addon/` | 1 | player README (shipped in the zip), CurseForge text and publishing, how the hub is built (`HUB_AUDIT.md`) |
| `docs/collection/` | 2 | admin guide (the officer guide `COLLECTOR.md` is in `companion/`, it ships in every package) |
| `docs/discord/` | 3 | the server admin guide (`SERVER.md`) and the members' guide (`MEMBERS.md`) |
| `docs/dev/` | — | development notes: measured game behaviour, in-game test checklists, the plans (`PACK_PLAN.md`, `PLAN_COMMUNITY.md`) |
| `STATUS.md` | — | what runs right now and what is next |
| `CLAUDE.md` | — | full specification and rules (for Claude Code) |

## Settings files

Only part 2 has settings. Each has an example file with a comment on every value saying where to get it;
the real files are git-ignored because they hold secrets.

| Copy this … | … to this | Filled in by |
|---|---|---|
| (made by the bot) | `config.toml` in the officer's package | nobody: `/collector invite` in Discord builds it ([ADMIN.md](docs/collection/ADMIN.md) section 3); by hand: copy `companion/config.example.toml` |
| `bot/config.example.toml` | `bot/config.toml` (sent to the server with `deploy.ps1 -UpdateConfig`) | the admin ([ADMIN.md](docs/collection/ADMIN.md)) |

## Building and testing

```
pip install pytest lupa discord.py
python -m pytest addon/tests companion/tests bot/tests
python tools/rebrand-hub.py                                   # after changing addon/hub-extra or the script
powershell -ExecutionPolicy Bypass -File .\tools\package-collector.ps1   # dist\ zips
```

All test data is synthetic. Never commit `config.toml`, databases, logs or real chat.
Publishing on CurseForge: [docs/addon/CURSEFORGE.md](docs/addon/CURSEFORGE.md).

## Licence

MIT ([LICENSE](LICENSE)). Amazing Hub is based on GuildOS (MIT): [THIRD_PARTY.md](THIRD_PARTY.md).
