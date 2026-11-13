# GuildLedger for officers: becoming a collector

GuildLedger keeps a permanent log of our guild chat and of joins, leaves, kicks and rank changes, and posts
it to the officer log channels in Discord. Every officer who runs it while playing fills gaps the others
miss. It never writes in chat or does anything in the guild on its own; it only reads.

You need: Windows, WoW: Forever, and about 15 minutes once.
From the guild admin you get: this zip, and a **webhook URL** (a long link starting with
`https://discord.com/api/webhooks/…`). The webhook URL is like a password: don't share or post it.

## 1. Install Python (once)

1. Download **Python 3.12** (or newer) from https://www.python.org/downloads/.
2. Run the installer. On the first screen tick **"Add python.exe to PATH"**, then *Install Now*.

## 2. Install the addon

1. Unzip `GuildLedger-collector-….zip` somewhere permanent, e.g. `Documents\GuildLedger`.
2. Copy the folder **`GuildLedger`** (the one with `GuildLedger.toc` inside) into your WoW AddOns folder:
   `…\World of Warcraft\_forever_\Interface\AddOns\`
3. Start WoW. At character select, *AddOns* → make sure **GuildLedger** is ticked.
4. In game type **`/gl collector on`**, then **`/reload`**. This makes your addon a collector (it also reads
   the guild history and the roster, and asks members' addons for lines it missed).
   `/gl status` shows `collector on` and what it collected.

## 3. Set up the companion (the small program that sends the log to Discord)

1. In the unzipped folder open `companion`. Copy `config.example.toml` and rename the copy to
   **`config.toml`**. Open it with Notepad.
2. Change these lines (keep the quotes):
   - `sv_path` → the path of your GuildLedger file. Replace `YOURACCOUNT` with your account folder name,
     which you find in `…\World of Warcraft\_forever_\WTF\Account\`. Example:
     `sv_path = 'D:\World of Warcraft\_forever_\WTF\Account\MYACCOUNT\SavedVariables\GuildLedger.lua'`
     (that file appears after your first logout or `/reload` with the addon on).
   - `collector` → your character name, e.g. `collector = "Lethaniel Blightwood"`.
   - `mode` must be `"upload"` (it already is).
   - Under `[upload]`: `ingest_webhook = "…"` → paste the webhook URL from the admin.
3. Save.

## 4. Every time you play

1. Double-click **`start-companion.cmd`** in the `companion` folder. A window opens and says
   `watching …`. Leave it open (minimise it) while you play.
2. Play normally. After each `/reload` or logout the window shows `uploaded N row(s)`. That's it.
   `/gl flush` in game does a `/reload` to send right away.
3. Close the window when you're done for the day.

If the window was closed while you played, nothing is lost: next time it sends everything it missed.

## Questions

- **Officer chat:** off by default. `/gl officer on` also collects officer chat; ask the admin first
  (it ends up in the officer log channel).
- **During boss fights** the game hides chat from addons. Lines written then are logged as "message
  written, text not captured". That is normal.
- **Something looks wrong:** send the admin a screenshot of `/gl status` and of the companion window.
  Never send `config.toml` or the webhook URL.
