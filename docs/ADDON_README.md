# GuildLedger

Helps your guild's officers keep a log of guild chat. **Nothing to set up and nothing to do:** install it
and play. It never writes in chat, never shows windows or messages, and needs no extra program.

## What it does

While you play, GuildLedger remembers recent guild chat lines (at most 2,000 lines, nothing older than
3 days). When one of your officers' GuildLedger asks for lines it missed (for example because the officer
was offline), yours sends them over in the background, invisibly, through the game's addon channel. Lines an
officer has received are deleted from your copy right away.

If your guild does not use GuildLedger, the addon simply does nothing useful; it does not hurt either.

## Commands (all optional)

- `/gl status` — what GuildLedger is doing right now, in plain words.
- `/gl who` — everyone online with GuildLedger: who collects, which version, how much they shared.
- Guild members on the world map: your position is shown to guild members who look at the map of your zone
  (never in instances or boss fights; never saved). `/gl map share off` stops it, `/gl map share on` resumes.
  `/gl map pins off` hides other members' dots on your world map.
- `/gl link CODE` — link your characters to your Discord account: use `/link` in the guild Discord, type the
  code here, then confirm in Discord. Your other characters are offered to you automatically; press "Not me"
  for anything that is not yours. `/unlink` in Discord removes it.

## Amazing Hub (the second folder): `/amazing`

The pack also contains **Amazing Hub**, a guild window: roster with last seen and alts, everybody's professions
and **known recipes**, a recipe browser that shows who can craft what (`/amazing craft <item>`), trials, raid
attendance and loot history, calendar, polls. `/amazing` opens it (`/amazing help` lists more). Its **Ledger**
tab shows what GuildLedger is doing (the same as `/gl status`) and has the world-map switches.

Your own professions and recipes are read automatically (no window to open) and shared with guild members who
also have the hub. Members without it show only their profession names. The hub talks only to your guild, your
group, or a guild member: never in public channels, /say or /yell. Features that post in chat (welcome lines,
loot announcements, consumable checks, `!note`) are off until an officer switches them on.

Amazing Hub is based on [GuildOS](https://github.com/danielcosta42/GuildOS) by Chehul (danielcosta42), MIT
licence; see `THIRD_PARTY.md` in its folder.

## For officers: becoming a collector

Collectors are the officers whose PCs send the guild log to Discord. That needs two extra things that are
not part of this download:

1. In game: `/gl collector on`, then `/reload`. The addon then also reads the guild chat history and tracks
   joins, leaves and kicks, and asks members for lines it missed.
2. The **GuildLedger companion** (a small program for your PC) and your personal upload link. Ask your
   guild's GuildLedger admin for the collector package; it contains a step-by-step guide (`COLLECTOR.md`).

Without the companion, a collector's data stays on the PC and never reaches Discord.
