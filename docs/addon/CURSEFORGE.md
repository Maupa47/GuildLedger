# CurseForge: project text and how to publish a version

For the admin. Copy the blocks below into the CurseForge project; the upload steps are at the end.

---

## Project settings

| Field | Value |
|---|---|
| Name | Amazing Forever Guild Pack |
| Game | World of Warcraft → WoW: Forever (interface 16001) |
| Categories | Guild, Chat & Communication (main); Professions, Map & Minimap |
| Licence | MIT |
| Logo | 400×400 PNG; avoid Blizzard art |

## Summary (the one line under the name)

```
A guild window and a silent guild-chat helper for WoW: Forever: roster, professions and recipes, calendar, Discord link.
```

## Description (paste into the description editor, Markdown mode)

```markdown
# Amazing Forever Guild Pack

Everything a **WoW: Forever** guild needs in one install: a clean guild window, every member's professions and
recipes at a glance, and a silent helper that keeps your guild's chat log complete for your officers.

The pack contains two addons. Each works on its own; together they show each other's information.

---

## 🏰 Amazing Hub — your guild window (`/amazing`)

- **Roster** — who is online, last seen, alts and ranks, at a glance.
- **Professions & recipes** — every member's professions and *known recipes*. Looking for a crafter?
  `/amazing craft <item>` tells you who can make it.
- **Guild** — calendar, activity and polls.
- **Ledger** — the state of GuildLedger and the Discord link box.
- **Settings** — tidy fold-out sections; *World map* lets you style the guild members' dots: round or square,
  size, outline and a colour for every class.
- **Raids, Loot, Trials** — off by default; switch them on in *Settings → Modules* if your guild uses them.
- **Classic or Modern look** — looks like the game's own windows by default; *Settings → Interface style*
  switches to a flat, dark Modern look.

Your professions and recipes are read automatically — no window to open — and shared only with guild members
who also use the hub.

## 📜 GuildLedger — install it and forget it

GuildLedger runs silently in the background. It remembers recent guild chat (at most 2,000 lines / 3 days)
and, when one of your officers missed some lines, quietly hands them over through the game's hidden addon
channel. Lines an officer has received are deleted from your copy right away.

- **No setup, no chat spam, no windows.** Nothing appears unless you type a command.
- **Guild members on the world map:** see where your guildmates are on the map of your zone, as class-coloured
  dots you can restyle. Never shown inside instances or during boss fights, never saved. `/gl map share off`
  hides you; `/gl map pins off` hides the dots.
- **Discord link (opt-in):** type `/link` in your guild's Discord, then `/gl link CODE` in game (or use the box
  in the hub's Ledger tab) and confirm in Discord. Officers can then give Discord roles by guild rank.
  `/unlink` removes it at any time.

| Command | |
|---|---|
| `/gl status` | what GuildLedger is doing right now, in plain words |
| `/gl who` | everyone online with GuildLedger |
| `/amazing` | open the guild window (`/amazing help` for all commands) |

## 🔒 Safe by design

- Talks **only** to your own guild, your group or a guild member — never in public channels, /say or /yell.
- Never posts in chat on its own. Features that would (welcome lines, loot announcements, consumable checks,
  `!note`) stay off until an officer switches them on.
- GuildLedger sends nothing during boss fights, as the game requires.
- No programs, no external downloads — just two addon folders.

## 🛡️ For guild officers

GuildLedger is the in-game half of a guild logging system: officers who run it as a *collector* send the guild
chat and every join, leave, kick and rank change to a permanent archive and to Discord. That part needs a small
companion program and a personal upload link from your guild's GuildLedger admin; it is **not** part of this
download. In game: `/gl collector on`, then `/reload`.

Guilds that don't use the logging system can still use everything else; GuildLedger then simply does nothing.

## Privacy

Members' guild chat is shared only with the guild's own officers' collectors, which archive it for the guild.
Positions on the world map are shared only with guild members looking at the same zone and are never stored.

---

Made by **Maupa**. Amazing Hub is based on the MIT-licensed guild addon *GuildOS* — thank you!
Licence: MIT (see `LICENSE.txt` and `AmazingHub/THIRD_PARTY.md`).
```

## Changelog for 0.6.0

```
- Settings → Collector (officers): one switch, "I am a collector (I run the GuildLedger companion on this PC)",
  with a "Reload now" button after a change. Replaces typing /gl collector on|off. Players change nothing.
- Everything from 0.5.4 (below) is included.
```

## Changelog for 0.5.4

```
- New Settings → Chat messages → Developer mode (or /gl dev on): GuildLedger tells you in chat what it
  shares with other players: chat history found after login, which collector asked for missing chat text,
  how many lines came from which player, how many are still missing, and when everything is complete.
- Collectors fetch long gaps faster: while players keep sending missing lines, the collector asks again
  after about a minute instead of waiting 15 minutes.
- /gl status → Sharing with other players: lines still without text (with times), and who filled how many.
- Item tooltips: "Crafted by" lists at most 5 guild members (online first) and counts the rest.
- The minimap button and guild-window button now say "Amazing Hub" everywhere.
- A greeting when you log in, from Maupa's sprite, with the guild's message of the day
  (switch it off in Settings → Chat messages or with /gl welcome off).
- Click a column heading in the DKP standings and the Professions tables to sort by it; click again for the
  other direction.
- World map: your own dot is hidden (the game's arrow shows you); Settings → World map → "Show my own dot"
  brings it back (/gl map me on).
- Your own tag in guild chat: with "Annotate guild chat" on, the hub writes a tag such as "(alt of …)" in
  front of each guild line. Settings → General → Chat → "What others see in the brackets for my lines": type
  a short text (e.g. "Floy", 16 characters at most) or tick "Show no tag at all". Empty = the usual alt tag.
- Settings → Loot opens with the LOOT SYSTEM section unfolded, so DKP / Points is easy to find.
- Wishlist window: "Import from Discord" adds the wishes you entered in your guild's Discord (/wish export there).
```

## Changelog for 0.5.3

```
- Quiet by default: neither addon writes anything in chat by itself any more (no login line, no sync notices).
  The answers to your own commands and clicks still show.
- New Settings → Chat messages: switch the pack's chat messages back on (or /gl messages on).
- Guild members on the map, new options in Settings → World map:
  - show only members in your zone or on your continent (e.g. in Elwynn Forest: only those in Elwynn Forest)
  - choose on which maps dots appear: zone maps, continent maps, the world map
  - names next to the dots
  - "Who sees me": only players who open the map of your zone, not continent or world maps
```

## Changelog for 0.5.2 (already released)

```
- Settings: every section folds open and closed (all closed at first), so the page stays tidy.
- New Settings → World map section: show/hide your position and the guild members' dots, and style the dots:
  round or square, size, dark outline, and a colour for every class (with a live preview).
  Also by command: /gl map shape round|square, /gl map size 6-24, /gl map outline on|off, /gl map reset.
- The map switches moved from the Ledger tab to Settings → World map.
- The download unpacks cleanly into two folders, GuildLedger and AmazingHub.
```

## Changelog for 0.5.1 (already released)

```
- Amazing Hub looks like the game's own windows by default (Classic); Modern in Settings → Interface style.
- Raids, Loot and Trials tabs are off by default; switch them on in Settings → Modules.
- Discord link box in the hub's Ledger tab.
```

---

## Publish a new version

1. **Version number** — raise it in three places, all the same (e.g. `0.5.2`):
   - `addon/GuildLedger/GuildLedger.toc` → `## Version:`
   - `addon/GuildLedger/Store.lua` → `S.VERSION`
   - `tools/rebrand-hub.py` → `HUB_VERSION`
2. **Rebuild the hub:** `python tools/rebrand-hub.py`
3. **Run the tests:** `python -m pytest addon/tests companion/tests bot/tests` (all must pass).
4. **Build the packages:** `powershell -ExecutionPolicy Bypass -File .\tools\package-collector.ps1`
   → `dist\Amazing-Forever-Guild-Pack-<version>.zip` (and the collector zip, which is **never** uploaded).
5. **Upload:** CurseForge → your project → *Files* → *Upload File* → choose the Pack zip.
   - Game version: WoW: Forever 1.60.1 (interface 16001)
   - Release type: *Release* (or *Beta* for a test round)
   - Changelog: the lines for this version (as above)
6. CurseForge checks every file; the pack contains only Lua, TOC, XML, fonts, textures and text, so there is
   nothing for its scan to flag. Approval usually takes a few hours.
