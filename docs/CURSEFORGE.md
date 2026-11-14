# CurseForge project: text and upload steps

For the admin. The addon package for CurseForge is built by `tools/package-collector.ps1` as
`dist/Amazing-Forever-Guild-Pack-<version>.zip` (the `GuildLedger` folder with the Lua files, the TOC and `README.md`;
no programs, so CurseForge's automatic check for runnable files has nothing to flag). The collector
package with the companion is **not** uploaded to CurseForge; officers get it from the admin.

## Upload a new version

1. Raise `## Version:` in `addon/GuildLedger/GuildLedger.toc` and `S.VERSION` in `addon/GuildLedger/Store.lua`
   (same number), and `HUB_VERSION` in `tools/rebrand-hub.py`, then run `python tools/rebrand-hub.py`.
2. `powershell -ExecutionPolicy Bypass -File .\tools\package-collector.ps1`
3. CurseForge → your project → *Files* → *Upload file* → `dist\Amazing-Forever-Guild-Pack-<version>.zip`.
   Game version: WoW: Forever (interface 16001). Release type: *Release* (or *Beta* for test rounds).
   Changelog: one or two lines from STATUS.md.

## Summary (short description)

Silent helper for your guild's chat log: keeps recent guild chat and shares it with your officers' collectors. No setup, no chat spam.

## Description

**GuildLedger** helps guild officers keep a complete log of guild chat and roster changes (joins, leaves,
kicks, promotions) in Discord.

**For members: install it and forget it.** GuildLedger works silently in the background. It remembers recent
guild chat lines (at most 2,000 lines / 3 days) and, when an officer's GuildLedger missed some lines, sends
them over through the game's hidden addon channel. Lines an officer has received are deleted from your copy.
It never writes in chat, shows no windows and needs no extra program.

Commands (optional): `/gl status` shows what it is doing; `/gl who` lists everyone online with GuildLedger.

**Guild members on the world map:** your position is shown to guild members who look at the map of your zone,
never inside instances or during boss fights, never saved or uploaded. `/gl map share off` turns it off for
you; `/gl map pins off` hides the other members' dots on your map.

**Discord link (opt-in):** `/link` in your guild's Discord gives a code; `/gl link CODE` in game; you confirm in
Discord. Lets officers see which Discord user plays which character, and can give Discord roles by guild rank.
`/unlink` in Discord removes it at any time.

**For officers (collectors):** `/gl collector on` and `/reload` turns on history and roster tracking. The
upload to Discord needs the GuildLedger companion and a personal upload link from your guild's GuildLedger
admin.

Guilds that do not use GuildLedger: the addon does nothing for you; it is harmless but not useful.

**Amazing Hub** (included): a guild window, `/amazing`. Roster with last seen and alts, every member's
professions and known recipes, a recipe browser with who can craft what, trials, raid attendance, loot history,
calendar and polls. Talks only to your own guild, group or guild members; features that post in chat are off until
an officer turns them on. Based on GuildOS by Chehul (danielcosta42), MIT, with thanks.

Licence: MIT (GuildLedger); Amazing Hub: MIT, © 2026 danielcosta42 (GuildOS) — see THIRD_PARTY.md.
