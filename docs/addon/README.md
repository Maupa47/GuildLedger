# Amazing Forever Guild Pack

Two addons for WoW: Forever guilds, made by Maupa:

- **GuildLedger** — silently helps your officers keep a complete log of guild chat. Nothing to set up.
- **Amazing Hub** — a guild window (`/amazing`): roster, professions and recipes, calendar, and more.

**Install** with the CurseForge app, or by hand: open the zip and drag the two folders `GuildLedger` and
`AmazingHub` into `World of Warcraft\_forever_\Interface\AddOns\`. (Windows' *Extract All* puts them into an
extra folder named after the zip; the game does not look inside it. Either type the AddOns folder as the
destination, or move the two folders out of the extra folder.) In the end you need
`AddOns\GuildLedger\GuildLedger.toc` and `AddOns\AmazingHub\AmazingHub.toc`.

Both addons work on their own; together the hub shows GuildLedger's state and its world-map options.

## GuildLedger

While you play, GuildLedger remembers recent guild chat lines (at most 2,000 lines, nothing older than 3 days).
When an officer's GuildLedger missed some lines (for example because the officer was offline), yours sends
them over in the background through the game's hidden addon channel. Lines an officer has received are deleted
from your copy right away. It never writes in chat and shows no messages unless you type a command.

If your guild does not use GuildLedger, the addon does nothing useful; it does not hurt either.

Commands (all optional):

| Command | What it does |
|---|---|
| `/gl status` | What GuildLedger is doing right now, in plain words |
| `/gl who` | Everyone online with GuildLedger: role, version, how much they shared |
| `/gl map share off` / `on` | Stop / resume showing your position to guild members on the world map (never in instances or boss fights, never saved) |
| `/gl map pins off` / `on` | Hide / show other members' dots on your world map |
| `/gl map shape round` / `square`, `/gl map size 6-24`, `/gl map outline on` / `off`, `/gl map reset` | The look of the dots (colours per class: in the hub's Settings) |
| `/gl link CODE` | Link your characters to your Discord account (see below) |

**Discord link (opt-in):** in your guild's Discord type `/link`; the bot answers with an 8-character code. Type
that code in game with `/gl link CODE` (or into the box in the hub's Ledger tab). When an officer's collector is
online, Discord asks you to confirm. Your other characters are offered to you too; press "Not me" for anything
that is not yours. `/unlink` in Discord removes the link.

## Amazing Hub: `/amazing`

A guild window with:

- **Roster** with last seen, alts and ranks
- **Professions**: every member's professions and known recipes, and who can craft an item (`/amazing craft <item>`)
- **Guild**: calendar, activity, polls
- **Ledger**: what GuildLedger is doing and the Discord link box
- **Settings**: every section folds open and closed; *World map* has the map switches and the look of the guild
  members' dots: round or square, size, outline, a colour per class
- **Raids, Loot, Trials**: off by default; tick them in *Settings → Modules* if your guild uses them

The window looks like the game's own windows (**Classic**); *Settings → Interface style* switches to a flat
**Modern** look (or `/amazing style modern`). `/amazing help` lists all commands.

Your own professions and recipes are read automatically and shared with guild members who also have the hub.
The hub talks only to your guild, your group or a guild member: never in public channels, /say or /yell.
Features that post in chat (welcome lines, loot announcements, consumable checks, `!note`) are off until an
officer switches them on.

## For officers: becoming a collector

Collectors are the officers whose PCs send the guild log to Discord. That needs two things that are not part
of this download:

1. In game: `/gl collector on`, then `/reload`. The addon then also reads the guild chat history, tracks joins,
   leaves and kicks, and asks members for lines it missed.
2. The **GuildLedger companion** (a small program for your PC) and your personal upload link. Ask your guild's
   GuildLedger admin for the collector package; it contains a step-by-step guide (`COLLECTOR.md`).

## Licence and credits

GuildLedger: MIT licence (`LICENSE.txt`). Amazing Hub is based on the MIT-licensed guild addon GuildOS; its
notice is in `AmazingHub\THIRD_PARTY.md`.
