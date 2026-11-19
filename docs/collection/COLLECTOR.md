# GuildLedger for officers: becoming a collector

GuildLedger keeps a permanent log of our guild chat and of joins, leaves, kicks and rank changes, and posts it
to the officer log channels in Discord. Every officer who runs it while playing fills gaps the others miss. It
never writes in chat or does anything in the guild on its own; it only reads.

You need: Windows, WoW: Forever, and about 15 minutes once.
From the guild admin you get: this zip, and a **webhook URL** (a long link starting with
`https://discord.com/api/webhooks/…`). The webhook URL is like a password: don't share or post it.

## 1. Install Python (once)

1. Download **Python 3.12** (or newer) from https://www.python.org/downloads/.
2. Run the installer. On the first screen tick **"Add python.exe to PATH"**, then *Install Now*.

## 2. Install the addons

1. Unzip `GuildLedger-collector-….zip` somewhere permanent, e.g. `Documents\GuildLedger`.
2. Copy the two folders **`GuildLedger`** and **`AmazingHub`** into your WoW AddOns folder:
   `…\World of Warcraft\_forever_\Interface\AddOns\`
   (If you already have them from CurseForge, that's fine: they are the same; replace them.)
3. Start WoW. At character select, *AddOns* → make sure **GuildLedger** and **Amazing Hub** are ticked.
4. In game type **`/gl collector on`**, then **`/reload`**. `/gl status` now starts with `Role: Collector`.
5. Log out once (or `/reload` again): this creates the file the companion reads.

## 3. Set up the companion (the small program that sends the log to Discord)

1. In the unzipped folder open `companion`. Copy `config.example.toml` and rename the copy to
   **`config.toml`**. Open it with Notepad. Only the three lines marked **FILL IN** at the top need changing;
   keep the quotes as they are.
2. **`sv_path`**: the path of your GuildLedger data file.
   1. In Explorer open your WoW folder → `_forever_` → `WTF` → `Account`. There is one folder per account,
      e.g. `12345678#1` or your account name.
   2. Open it → `SavedVariables`. You should see `GuildLedger.lua`.
   3. Click the file once, then *Copy as path* (right-click, or Ctrl+Shift+C).
   4. In `config.toml` replace the whole example path between the single quotes `' '` with what you copied
      (remove the double quotes `"` that *Copy as path* adds). Example:
      `sv_path = 'C:\Program Files (x86)\World of Warcraft\_forever_\WTF\Account\12345678#1\SavedVariables\GuildLedger.lua'`
3. **`collector`**: your main character's name, e.g. `collector = "Firstname Surname"`.
4. **`ingest_webhook`** (under `[upload]`): paste the webhook URL from the admin between the quotes.
5. Save. Leave everything below the line "leave as it is" unchanged.

## 4. Every time you play

1. Double-click **`start-companion.cmd`** in the `companion` folder. A window opens and says `watching …`.
   Leave it open (minimise it) while you play. If it shows an error about `config.toml`, it names the line to fix.
2. Play normally. After each `/reload` or logout the window shows `uploaded N row(s)`. That's it.
   `/gl flush` in game does a `/reload` to send right away.
3. Close the window when you're done for the day.

If the window was closed while you played, nothing is lost: next time it sends everything it missed.

**Start it automatically:** double-click **`autostart-on.cmd`** once. From then on the companion starts
minimised whenever you log in to Windows (`autostart-off.cmd` undoes it). Starting it twice is harmless: the
second window says "already running" and closes.

## Questions

- **Loot data:** the companion also sends Amazing Hub's DKP/points, loot history, wishlists and raid attendance
  (from `AmazingHub.lua` next to `GuildLedger.lua`) so the bot can show them in Discord (`/dkp`, `/loot`,
  `/wishlist`). Nothing to set up. To send none: in `config.toml` add `[loot]` and `enabled = false`.

- **Officer chat:** off by default. `/gl officer on` also collects officer chat; ask the admin first (it ends
  up in the officer log channel).
- **During boss fights** the game hides chat from addons. Lines written then are logged as "message written,
  text not captured". That is normal; members' addons often fill them in later.
- **Something looks wrong:** send the admin a screenshot of `/gl status` and of the companion window. Never
  send `config.toml` or the webhook URL.
