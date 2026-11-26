# Decisions

What the admin decided, in date order. Newer lines override older ones. `CLAUDE.md` keeps the facts, the rules and
the repository map and mentions a decision where code depends on it; the finished plans are in
[archive/](archive/). Add a dated line here whenever the admin decides something.

## Collection system (CLAUDE.md, v1)

| Date | Decision | Where it shows |
|---|---|---|
| 2026-11-11 | The bot runs on a small VPS (systemd, no open port); `mode = "direct"` stays for tests | CLAUDE.md 7.5, 11 |
| 2026-11-13 | Hidden addon messages on the guild channel are allowed, for the relay only (later also map and link, each with a budget in shared/schema.md 5) | CLAUDE.md 1, 5.6, 5.7 |
| 2026-11-13 | Two roles in one addon: member (default) and collector; schema 2 | CLAUDE.md 5.2, 5.7 |
| 2026-11-13 | Silent by default: nothing in chat unless the player types a command | CLAUDE.md 5.6 |
| 2026-11-13 | `/gl status` in plain words for every player | CLAUDE.md 5.5 |
| 2026-11-15 | Unasked lines only with `/gl messages on` | CLAUDE.md 5.6 |
| 2026-11-17 | Reports of what is sent and received only in developer mode (`/gl dev on`) | CLAUDE.md 5.6 |
| 2026-11-18 | Exception: the login greeting with the message of the day, on by default (30 s after login since 0.7.0) | CLAUDE.md 5.6 |
| 2026-11-19 | Easy collector setup (0.6.0): the bot builds each officer's package, the companion finds the files and updates itself | CLAUDE.md 6, 7.1 |

## Pack 0.4–0.5 (from docs/dev/archive/PACK_PLAN.md section 0)

**Decisions by the admin (2026-11-13)**
- **Name:** CurseForge project **"Amazing Forever Guild Pack"** (under review). The addon folder stays
  `GuildLedger`, its SavedVariables `GuildLedgerDB`, its slash command `/gl`: nothing to rename, no
  `sv_path` changes for collectors.
- **No fork for now (decision 3).** Map, Discord link and activity are built **inside GuildLedger**. The hub
  (GuildOS fork, sections 7–8) is postponed; decide after the new modules run. Members who want the hub's
  features can install GuildOS itself from CurseForge next to the pack.
- **Version 0.4.0** for the first pack release (GuildLedger is already 0.3.0).
- **Testing:** the in-game relay check is not a precondition any more (section 2); relay, map, link and
  activity are tested together in one combined test round when the modules are built.
- **2026-11-14:** licence **MIT** (decision 2, `LICENSE`). Decision 5: linked guild members get the existing
  Discord role **guild-member**; rank roles are many and change (and use emojis), so the bot reads the server's
  roles and the guild ranks and officers set the mapping with `/roles` in Discord (saved in the archive, not in
  config.toml); nicknames: decided later (left alone). Decision 6: map sharing **on by default** with
  `/gl map share off` (overrides rule 8 "opt-in" for the map; positions are still never stored or uploaded).
  Decision 4 (GuildOS courtesy) and 7 (hub chat behaviour) only matter with a fork.
- **2026-11-14, decision 3 revised: fork GuildOS after all** (the admin wants its guild window: professions,
  recipes, recipe browser, roster). Phase 8 audit: docs/addon/HUB_AUDIT.md. Hub decisions: folder `AmazingHub`, title
  "Amazing Hub", slash `/amazing`; chat-posting features **off, officers can enable** (decision 7); the hub's own
  guild chat log, roster log and map are **off** - GuildLedger's are used (bridge in Phase 10); the admin contacts the
  GuildOS author before publishing (decision 4). Sections 7–8 (Phase 9 fork, Phase 10 bridge) apply again; pack
  version with the hub: 0.5.0.

Hub decisions of 2026-11-14 ([HUB_AUDIT.md](../addon/HUB_AUDIT.md) "Decisions"): folder `AmazingHub`, title
"Amazing Hub", slash `/amazing`; posting features off by default, officers can enable; the hub's own chat log,
roster log and map off (GuildLedger's are used); nothing in game says GuildOS or its author (hub by "Maupa"); pack
version 0.5.0.

## Community plan, pack 0.7 (from docs/dev/archive/PLAN_COMMUNITY.md section 4)

Until a question was answered the default applied.

Ask each at the phase named; until answered use the default and say so in `STATUS.md`.

| # | Question | Default | Phase |
|---|---|---|---|
| 1 | Which role does the bot check give (the role Pandez gives today)? In which channel is the Verify button? | **Answered:** keep the two roles Pandez Guard set up, the one members get after the check and the one for bots. The admin renames the members' role; a rename keeps the role's ID, so channel permissions stay. `/setup gate role:` points at that role; the bots' role is not touched. Channel: the one Pandez uses today (assumed, confirm at D1) | D1 |
| 2 | Nickname: "Firstname Surname" of the main, or first name only? | whole name | D1 |
| 3 | Interest list | Raids, Dungeons, PvP, Levelling, Crafting, Social | D2 |
| 4 | Language list (which languages get a role) | **Answered:** all major European languages; the list is in D2 | D2 |
| 5 | Who may see other members' characters (right-click, forum)? | everyone with the linked-member role | D3 |
| 6 | Joined column for officers only (as upstream), or for every member (then the dates must also be synced to members' clients: extra work)? | officers | H10 |
| 7 | Which new upstream features that act for the player stay on (section 2 item 4)? | all off | U |
| 8 | Alt tag rule: shown only when the member chose a tag text or linked the alts themselves; a link only an officer entered shows no tag. Correct? | **Answered:** yes; revised 2026-11-24: both count the same (U1 found they cannot be told apart) | H6 |
| 9 | Linked Roles need a public web address on the server. Build it? | **Answered:** no. Not built: the nickname and the Characters command cover it, and the bot keeps opening no listening port | — |
| 10 | Which bots to remove (section 9) | none removed by us | D7 |
| 11 | Open your own character on the EU armory and paste the address | **Answered:** template `https://worldofwarcraft.blizzard.com/en-us/forever/eu/armory/character/{name}` (section 2 item 13) | D3 |
| 12 | A public line "X joined, main Y" after the first link: which channel? | none | D1 |

## Pack 0.7 (2026-11-24 to 26)

| Date | Decision | Where it shows |
|---|---|---|
| 2026-11-24 | Decision 7: the hub's tools that act for the player (group posts in /g, auto-invite, bulk rank changes, add-on reminders, chat alerts, bank cleanup, warning whispers) are hidden in the CurseForge pack and available in the admin's own install through the `AmazingHubDev` addon | HUB_AUDIT 10.11 |
| 2026-11-24 | Decision 8 revised: self-claimed and officer-entered alt links count the same | HUB_AUDIT 10.8 |
| 2026-11-24 | The hub's saved data without realm is copied to the realm key once | HUB_AUDIT 10.5 |
| 2026-11-24 | Re-pin the hub to GuildOS 1.40.0 | HUB_AUDIT 10.11 |
| 2026-11-25 | A column sort in the member list mixes online and offline members (setting to keep online first) | hub-extra/SettingsPlus.lua |
| 2026-11-26 | Shift + click in Crafts links the item; a recipe without an item links the recipe; the opened recipe also lists the recipe and what teaches it | hub-extra/Materials.lua |
| 2026-11-26 | Reset is always in the member toolbar | tools/rebrand-hub.py |
| 2026-11-26 | A craft order to one crafter also whispers them, in the CurseForge pack too (exception to "nothing on the player's behalf by default": only from the player's own Send click, guild members only) | hub-extra/OrderWhisper.lua |
| 2026-11-26 | Pack 0.7.0 is released with the re-pinned hub and phase H | docs/addon/CURSEFORGE.md |
