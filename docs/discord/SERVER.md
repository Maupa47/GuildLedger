# Discord server: admin guide

For the guild's Discord admin. This covers part 3 of the project, the Discord community: the bot's
permissions, channels and roles, the sign-up with the bot check, role menus, the character forum, and which
other bots are still needed. The collection system (uploads, log channels, collectors, server) is in
[../collection/ADMIN.md](../collection/ADMIN.md). What members do is in [MEMBERS.md](MEMBERS.md).

Every setting in this guide is made **in Discord** with `/setup …` (you need *Manage Server*); `/setup show`
lists them all. `bot\config.toml` keeps only the token, the IDs the bot needs to start, and the webhooks.

## 1. The bot application (once)

1. https://discord.com/developers/applications → your app → **Bot**: turn on **Message Content Intent**
   (needed to read the collectors' uploads). The *Server Members* intent stays **off**: every sign-up step starts
   with a member's click or command.
2. **Installation**: scopes `bot` and `applications.commands`. Permissions, all of them and nothing more (never
   Administrator):
   - Manage Roles (gate role, rank roles, menu roles), Manage Nicknames (nickname = main character)
   - View Channels, Send Messages, Embed Links, Read Message History, Add Reactions
   - Create Posts, Send Messages in Threads, Manage Threads (character forum)
   - Manage Webhooks: give it **only in `#gl-ingest`** (channel settings → Permissions), for `/collector invite`
3. **Server Settings → Roles**: drag the bot's role **above** every role it hands out: the role from the bot
   check, the linked-member role, the rank roles and every interest and language role. Discord refuses
   anything else and the bot says so in `#gl-ops`.

## 2. Channels

| Channel | Who sees it | Who writes | For |
|---|---|---|---|
| verify channel (e.g. `#welcome`) | everyone | nobody (only the button) | the Verify button |
| roles channel (e.g. `#pick-roles`) | members | nobody | the role panel |
| character forum (e.g. `#characters`, a **forum** channel) | linked members | only the bot | one post per member |
| `#gl-ingest`, `#guild-chat-log`, `#guild-roster-log`, `#gl-ops` | admins/officers | bot, collectors | collection system ([ADMIN.md](../collection/ADMIN.md)) |

In the forum and the roles channel, members get no *Send Messages* / *Create Posts*. In the forum, create
**tags named after the classes** (Warrior, Paladin, Hunter, Rogue, Priest, Shaman, Mage, Warlock, Druid): each
member's post gets the tag of their main's class. (A forum may have at most 20 tags.)

## 3. Sign-up: bot check → welcome → link

What a new member sees: the **Verify** button → a small task (press the named one of five buttons) → the role
→ a private welcome message with the addon link, the link steps and a **Get my link code** button → after the
link their nickname and roles follow by themselves, and they are offered the role menus once.

Set it up:

| Command | What it does |
|---|---|
| `/setup gate channel:#welcome role:@Member min_account_age_days:7` | posts the Verify button; the check gives that role. Accounts younger than the age (0 = off) are told to ask an officer |
| `/setup welcome` | a window to write your own welcome text (empty = the default text; the link steps are always added) |
| `/setup addon url:https://…` | the addon pack's download page, shown in the welcome |
| `/setup nickname mode:on` | nickname = the member's main character, whole name (the server owner's cannot be set by a bot) |
| `/setup announce channel:#general` | optional public line "👋 @member joined us, main **Name**" after their first link (default: none) |

Rules of the check: three wrong tries → ten minutes' wait; a task expires after two minutes; passes and lockouts
are logged to `#gl-ops`. It keeps scripted accounts out; the proof that someone is in the guild is the link.

Officer shortcuts:
- `/linkapprove user:@member character:Name` links a current guild member at once (for members who cannot wait
  for a collector). Recorded as approved by you.
- `/linkstatus`, `/unlink user:@member`, `/roles …` as before.

### Moving over from Pandez Guard (decision 1)

Keep the two roles Pandez Guard uses: the one members get after its check, and the one for bots.

1. `/setup gate` in a **test channel** with the members' role. Try it with a second Discord account: Verify →
   task → role → private message.
2. `/setup gate` again in the real verify channel (the old button in the test channel can be deleted).
3. Switch off Pandez Guard's verify panel, delete its message.
4. Rename the members' role if you like: a rename keeps the role's ID, so channel permissions stay.
5. Before removing Pandez Guard: check in Server Settings → Roles that the members' role is an **ordinary role**
   (not "managed by an integration"). A bot's own role disappears with the bot.
6. Remove Pandez Guard.

## 4. Roles for linked members, role menus

**By guild rank** (as before): `/roles verified role:@guild-member`, `/roles rank rank:<rank> role:@role` for
each rank, `/roles show`, `/roles sync`.

**Role menus** (interests and languages; members pick them themselves):

| Command | What it does |
|---|---|
| `/setup rolemenu preset group:languages` | registers 20 languages (English, Deutsch, Français, …, Other). A role is **made the first time a member picks it** (plain role, no permissions); a role you made by hand with the same name is used instead |
| `/setup rolemenu preset group:interests` | Raids, Dungeons, PvP, Levelling, Crafting, Social |
| `/setup rolemenu add group:interests label:Raids role:@Raiders emoji:⚔️` | add or change one entry, with your own role |
| `/setup rolemenu remove group:… label:…` | remove an entry (the role itself stays) |
| `/setup rolemenu post channel:#pick-roles` | posts the panel: one menu per group, at most 25 entries each |

After changing a menu, post the panel again and delete the old message. A member's choice adds and removes
only the roles of that menu, never any other role. Roles with moderator permissions are refused.

## 5. Characters

- **Right-click a member → Apps → Characters** and `/chars user:` show all their characters (main first) with
  level, class, rank, last seen and an armory link. `/whois character:` suggests names while typing.
- Who may look up others (decision 5): everyone with the linked-member role (`/roles verified`); without such a
  role, everyone who linked a character. Officers always.
- **Character forum:** `/setup directory forum:#characters`. The bot keeps one post per linked member (title: the
  main; body: one line per character), "Not linked yet: A-C" … posts listing everybody else, and a help post.
  It checks every 10 minutes and writes at most 10 changes per round, so the first fill of a big guild takes
  a while. A member whose characters all left gets "(left)" for the grace period (`[link] grace_days`, 7), then
  the post goes.
- **Armory links:** `/setup armory url:https://worldofwarcraft.blizzard.com/en-us/forever/eu/armory/character/{name}`
  is the default (decision 11); an empty `url` switches the links off. Only characters level 10 and up get one.
  Names with a special letter (ä, é, …) get none until such a name has been checked once.
- Members choose their main with `/main character:` (else the highest level counts).
- **Profession forum (0.7.0):** `/setup professions forum:#professions` (a forum nobody but the bot posts in;
  the bot needs the same rights there as in the character forum). One post per profession: the crafters with
  their skill and last seen, then every recipe someone in the guild knows ("Recipe - Name, Name (+3)"), kept up
  to date every 10 minutes. The data comes from Amazing Hub through the collectors' companions, so it needs the
  0.7.0 bot deployed first and a collector who runs the 0.7.0 companion. Members look things up with `/craft`.
- **Guild bank (0.7.0):** `/setup bank channel:#guild-bank ledger_channel:#bank-ledger`. The bank channel gets one
  message for the gold and one per tab (items by name with counts, when and by whom it was read), edited in
  place every 5 minutes; members should only read it. The ledger channel (who put in or took out what) must be
  **officers only**: the bot warns when everyone can see it, and posts only lines that arrive after it was set.
  The bot needs Send Messages and Read Message History in both. The picture comes from Amazing Hub: it is as
  new as the last time a member with the hub opened the bank. Members ask with `/bank item:`.

## 6. Checklist

- [ ] Bot permissions as in section 1; its role above every role it gives
- [ ] Verify channel, roles channel, character forum with class tags; members cannot post in the last two
- [ ] `/setup gate`, `/setup welcome`, `/setup addon`, `/setup nickname on`
- [ ] `/roles verified`, `/roles rank …`
- [ ] `/setup rolemenu preset …`, `/setup rolemenu post`
- [ ] `/setup directory`
- [ ] Profession forum (members cannot post), `/setup professions`
- [ ] Bank channel (read only for members) and an officers-only ledger channel, `/setup bank`
- [ ] Remove *Change Nickname* from the member roles if nicknames should stay equal to the main
- [ ] Pin the text from [MEMBERS.md](MEMBERS.md) section "Pinned post"

## 7. The other bots (judged by their commands, 2026-11-18)

Not jobs for our bot: moderation, tickets, giveaways, music, patch news, stream alerts, levels.

| Bot | Verdict |
|---|---|
| Pandez Guard | replaced by the sign-up (section 3); remove after the cutover |
| Invite Tracker | remove: invite tracking is not wanted now, its verify is replaced, giveaways and message counts exist twice |
| ServerStats | remove if the counter channels are not needed, or after `/setup counters category:` (our bot keeps "Guild members: N" and "Linked: N" current, every 15 minutes; needs *Manage Channels* in that category only) |
| Discohook Utils | if its welcomer is in use, our welcome replaces it; keep it only if buttons on Discohook messages are used |
| Koya | overlaps with Dyno and Arcane; keep only for what is really used. Role menus set up in Koya, Dyno or Arcane move to section 4 |
| EasyPoll | Discord's built-in polls may be enough: your call |
| Dyno | keep as the one moderation bot; switch off its poll and giveaway modules |
| Arcane | keep for levels; switch off its moderation commands |
| GiveawayBot, Ticket Tool, PatchBot, NotifyMe, Wowhead Bot, the music bot | keep |

Decision 10: we remove none; this is your checklist.
