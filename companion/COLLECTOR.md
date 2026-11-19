# GuildLedger for officers: becoming a collector

GuildLedger keeps a permanent log of our guild chat and of joins, leaves, kicks and rank changes, and posts it
to the officer log channels in Discord. Every officer who runs it while playing fills gaps the others miss. It
never writes in chat or does anything in the guild on its own; it only reads.

You need: Windows 10 or 11, WoW: Forever with the **Amazing Forever Guild Pack** (CurseForge), and about five
minutes once.

## 1. Get your package (Discord)

The guild's GuildLedger admin invites you with `/collector invite`. You get a message with a button
**Get my collector package**: press it and download the zip the bot shows you (only you can see it).

The zip contains your personal upload link, which is like a password: **never share the zip or the file
`config.toml` in it.** Lost it or got a new PC? Press the button again.

## 2. Start it (your PC)

1. Unzip the package somewhere permanent, e.g. `Documents\GuildLedger`.
2. Double-click **`start-companion.cmd`**. The first time it
   - installs Python by itself if your PC does not have it (Windows may ask you to allow that),
   - asks whether it should start automatically with Windows: answer **Y**,
   - finds your WoW folder by itself and sends a test upload. The admin sees "… is connected" in Discord.
3. Leave the window open (minimise it) while you play.

If it says it cannot find a GuildLedger data file yet: do step 3 below, it notices by itself.
If it asks where your World of Warcraft folder is (unusual install location), paste the folder's path.

## 3. Switch the collector role on (in game, once)

`/amazing` → **Settings** → **Collector (officers)** → tick *I am a collector* → **Reload now**.
(Or type `/gl collector on`, then `/reload`.) `/gl status` now starts with `Role: Collector`.

This is saved for your whole WoW account: **it does not matter which of your characters you play**, main or
alt. Alts on a second WoW account work too: tick the box there once as well; the companion reads every
account on your PC.

## Every time you play

Nothing to do if you answered Y: the companion starts with Windows. Otherwise double-click
`start-companion.cmd`. After each `/reload` or logout the window shows `uploaded N row(s)`.
`/gl flush` in game does a `/reload` to send right away. If the companion was not running while you played,
nothing is lost: next time it sends everything it missed.

`autostart-on.cmd` / `autostart-off.cmd` switch the automatic start on and off later.

## Updates

- **The companion updates itself** when it starts (it fetches the newest version from the project's GitHub
  page). Your settings, your upload link and your data are never touched. If you update by hand instead:
  unzip a newer package over the old folder; it contains no `config.toml`, so yours stays.
- **The addons** update through CurseForge like any other addon.

## Questions

- **Loot data:** the companion also sends Amazing Hub's DKP/points, loot history, wishlists and raid attendance
  so the bot can show them in Discord (`/dkp`, `/loot`, `/wishlist`). Nothing to set up. To send none: in
  `config.toml` add a line `[loot]` and below it `enabled = false`.
- **Officer chat:** off by default. `/gl officer on` also collects officer chat; ask the admin first (it ends
  up in the officer log channel).
- **During boss fights** the game hides chat from addons. Lines written then are logged as "message written,
  text not captured". That is normal; members' addons often fill them in later.
- **I stop being an officer / a collector:** untick the box in game; the admin removes your upload link
  (`/collector remove`), after which the companion's uploads are refused. Delete the folder.
- **Something looks wrong:** send the admin a screenshot of `/gl status` and of the companion window. Never
  send `config.toml` or the zip.

## By hand (without the bot's package)

Copy `config.example.toml` to `config.toml`, fill in `collector` and `ingest_webhook` (the admin sends you the
link privately) and start `start-companion.cmd`. Everything else is the same.
