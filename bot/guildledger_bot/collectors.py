"""Collectors set up from Discord (0.6.0): `/collector invite @officer`, a button for that officer, and the bot
makes their personal upload webhook in #gl-ingest and hands them a ready collector package (zip).

- The registry (which webhook belongs to whom) lives in the archive database, next to the uploads. The
  `[collectors]` lines in config.toml keep working beside it.
- The webhook URL is a secret: it goes into the officer's zip and nowhere else. It is never stored here
  (the bot reads it back from Discord when the officer asks for the package again) and never logged.
- Database work runs on the bot's worker thread (bot._db); Discord calls on the event loop.
"""

from __future__ import annotations

import io
import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord as dpy
from discord import app_commands

from guildledger import package

if TYPE_CHECKING:
    from .client import LedgerBot
    from .store import Archive

log = logging.getLogger(__name__)
NO_MENTIONS = dpy.AllowedMentions.none()

_DDL = """
CREATE TABLE IF NOT EXISTS collector_invites(
  discord_user_id INTEGER PRIMARY KEY, name TEXT NOT NULL, invited_by INTEGER, created_at INTEGER NOT NULL,
  channel_id INTEGER);
CREATE TABLE IF NOT EXISTS collectors(
  webhook_id INTEGER PRIMARY KEY, discord_user_id INTEGER NOT NULL UNIQUE, name TEXT NOT NULL,
  created_at INTEGER NOT NULL, channel_id INTEGER, first_upload_at INTEGER);
"""

STEPS = (
    "**Your GuildLedger collector package** (only you can see this message).\n"
    "1. Download the zip and unzip it somewhere permanent, e.g. `Documents\\GuildLedger`.\n"
    "2. Double-click **`start-companion.cmd`** in it. It finds your WoW folder by itself and installs Python if"
    " it is missing. Answer **Y** when it asks about starting with Windows.\n"
    "3. In game: `/amazing` → Settings → **Collector (officers)** → tick the box → *Reload now*"
    " (or type `/gl collector on`, then `/reload`).\n"
    "That is all; it works for every character on your WoW accounts. The zip contains your personal upload"
    " link: **never share the zip or its `config.toml`**. Guide: `COLLECTOR.md` inside."
)


def clean_name(name: str) -> str:
    """A collector name for the archive and the upload message: one line, no control characters."""
    name = re.sub(r"[\x00-\x1f\x7f`]", " ", name or "")
    return re.sub(r"\s+", " ", name).strip()[:40]


@dataclass
class Collector:
    webhook_id: int
    user_id: int
    name: str
    created_at: int
    channel_id: int | None
    first_upload_at: int | None
    last_upload_at: int | None = None


class Registry:
    def __init__(self, archive: "Archive", now=time.time):
        self.db, self.now = archive.db, now
        self.db.executescript(_DDL)

    def invite(self, user_id: int, name: str, by: int | None, channel_id: int | None) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO collector_invites(discord_user_id, name, invited_by, created_at, channel_id)"
                " VALUES(?,?,?,?,?) ON CONFLICT(discord_user_id) DO UPDATE SET name=excluded.name,"
                " invited_by=excluded.invited_by, created_at=excluded.created_at, channel_id=excluded.channel_id",
                (user_id, name, by, int(self.now()), channel_id))
            self.db.execute("UPDATE collectors SET name=?, channel_id=? WHERE discord_user_id=?",
                            (name, channel_id, user_id))

    def invited(self, user_id: int) -> tuple[str, int | None] | None:
        r = self.db.execute("SELECT name, channel_id FROM collector_invites WHERE discord_user_id=?",
                            (user_id,)).fetchone()
        return (r[0], r[1]) if r else None

    def by_user(self, user_id: int) -> Collector | None:
        r = self.db.execute("SELECT webhook_id, discord_user_id, name, created_at, channel_id, first_upload_at"
                            " FROM collectors WHERE discord_user_id=?", (user_id,)).fetchone()
        return Collector(*r) if r else None

    def add(self, webhook_id: int, user_id: int, name: str, channel_id: int | None) -> None:
        """Register the officer's webhook (a second one for the same officer replaces the first)."""
        with self.db:
            self.db.execute("DELETE FROM collectors WHERE discord_user_id=?", (user_id,))
            self.db.execute("INSERT INTO collectors(webhook_id, discord_user_id, name, created_at, channel_id)"
                            " VALUES(?,?,?,?,?)", (webhook_id, user_id, name, int(self.now()), channel_id))

    def remove(self, user_id: int) -> int | None:
        """Forget the officer (invitation and webhook). Returns the webhook ID to delete in Discord."""
        c = self.by_user(user_id)
        with self.db:
            self.db.execute("DELETE FROM collector_invites WHERE discord_user_id=?", (user_id,))
            self.db.execute("DELETE FROM collectors WHERE discord_user_id=?", (user_id,))
        return c.webhook_id if c else None

    def names(self) -> dict[int, str]:
        return {r[0]: r[1] for r in self.db.execute("SELECT webhook_id, name FROM collectors")}

    def first_upload(self, webhook_id: int) -> Collector | None:
        """Mark the first accepted upload of a registered webhook; returns the collector that one time."""
        with self.db:
            n = self.db.execute("UPDATE collectors SET first_upload_at=? WHERE webhook_id=? AND"
                                " first_upload_at IS NULL", (int(self.now()), webhook_id)).rowcount
        if not n:
            return None
        r = self.db.execute("SELECT webhook_id, discord_user_id, name, created_at, channel_id, first_upload_at"
                            " FROM collectors WHERE webhook_id=?", (webhook_id,)).fetchone()
        return Collector(*r)

    def overview(self, config_collectors: dict[int, str]) -> tuple[list[Collector], list[tuple[str, int | None]],
                                                                    list[tuple[int, str]]]:
        """(registered collectors with their last upload, config-file collectors (name, last upload),
        open invitations (user id, name))."""
        last = {r[0]: r[1] for r in self.db.execute(
            "SELECT collector, MAX(received_at) FROM uploads WHERE status='ok' GROUP BY collector")}
        reg = [Collector(*r, last_upload_at=last.get(r[2])) for r in self.db.execute(
            "SELECT webhook_id, discord_user_id, name, created_at, channel_id, first_upload_at FROM collectors"
            " ORDER BY name")]
        cfg = [(name, last.get(name)) for name in sorted(set(config_collectors.values()))]
        have = {c.user_id for c in reg}
        open_ = [(r[0], r[1]) for r in self.db.execute(
            "SELECT discord_user_id, name FROM collector_invites ORDER BY created_at") if r[0] not in have]
        return reg, cfg, open_


# --------------------------------------------------------------------------------- Discord side

def zip_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-") or "collector"
    return f"GuildLedger-collector-{safe}.zip"


def webhook_name(name: str) -> str:
    n = f"GL {name}"[:80]
    return "GL collector" if re.search(r"discord|clyde", n, re.I) else n  # Discord refuses those words


class PackageButton(dpy.ui.DynamicItem[dpy.ui.Button], template=r"gl:col:get:(?P<uid>[0-9]+)"):
    """"Get my collector package": works only for the invited officer, also after a bot restart."""

    def __init__(self, uid: int):
        super().__init__(dpy.ui.Button(label="Get my collector package", style=dpy.ButtonStyle.success,
                                       custom_id=f"gl:col:get:{uid}"))
        self.uid = uid

    @classmethod
    async def from_custom_id(cls, interaction: dpy.Interaction, item: dpy.ui.Button, match):  # noqa: ARG003
        return cls(int(match["uid"]))

    async def callback(self, interaction: dpy.Interaction) -> None:
        bot: LedgerBot = interaction.client  # type: ignore[assignment]
        if interaction.user.id != self.uid:
            await interaction.response.send_message("This button is for the invited officer only.",
                                                    ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        text, file = await hand_out(bot, self.uid)
        kw = {"file": file} if file else {}
        await interaction.followup.send(text, ephemeral=True, allowed_mentions=NO_MENTIONS, **kw)


def package_view(uid: int) -> dpy.ui.View:
    view = dpy.ui.View(timeout=None)
    view.add_item(PackageButton(uid))
    return view


async def _webhook_url(bot: "LedgerBot", user_id: int, name: str, channel_id: int | None) -> str:
    """The officer's upload link: their existing webhook if Discord still has it, else a new one."""
    reg = bot._collectors
    current = await bot._db(reg.by_user, user_id)
    if current is not None:
        try:
            hook = await bot.fetch_webhook(current.webhook_id)
            if hook.token:
                return hook.url
        except dpy.NotFound:
            pass  # deleted in Discord: make a new one
    channel = bot.get_channel(bot.cfg.ingest_channel_id) or await bot.fetch_channel(bot.cfg.ingest_channel_id)
    hook = await channel.create_webhook(name=webhook_name(name), reason=f"GuildLedger collector {name}")
    await bot._db(reg.add, hook.id, user_id, name, channel_id)
    await bot.refresh_collectors()
    log.info("collector %s: webhook %s created in the ingest channel", name, hook.id)
    return hook.url


async def hand_out(bot: "LedgerBot", user_id: int) -> tuple[str, dpy.File | None]:
    """Make (or re-make) the invited officer's package. Returns the answer text and the zip."""
    reg = bot._collectors
    inv = await bot._db(reg.invited, user_id)
    if inv is None:
        return "This invitation was withdrawn. Ask the GuildLedger admin for a new one.", None
    name, channel_id = inv
    try:
        url = await _webhook_url(bot, user_id, name, channel_id)
    except dpy.Forbidden:
        return ("I may not create webhooks in the upload channel. The admin has to give me the **Manage"
                " Webhooks** permission in `#gl-ingest`; then press the button again."), None
    except dpy.DiscordException as e:
        log.error("collector %s: could not get the webhook: %s", name, e)
        return "Discord refused that just now. Try the button again in a minute.", None
    try:
        data = await bot._db(lambda: package.build_zip(
            config_text=package.render_config(url, name, bot.cfg.timezone)))
    except (package.PackageError, OSError) as e:
        log.error("collector package: %s", e)
        return "The package could not be built on the server (the admin finds the reason in the bot's log).", None
    return STEPS, dpy.File(io.BytesIO(data), zip_name(name))


def register(bot: "LedgerBot") -> None:
    group = app_commands.Group(name="collector", description="Admin: officers whose PCs send the guild log",
                               default_permissions=dpy.Permissions(manage_guild=True), guild_only=True)

    def ts(t: int | None) -> str:
        return f"<t:{int(t)}:R>" if t else "never"

    @group.command(name="invite", description="Let an officer set up a collector: they get a button for their package")
    @app_commands.describe(user="The officer", name="Name in the archive (default: their linked main character,"
                                                    " else their Discord name)")
    async def invite(inter: dpy.Interaction, user: dpy.Member, name: str | None = None):
        if user.bot:
            await inter.response.send_message("That is a bot.", ephemeral=True)
            return
        label = clean_name(name or "") or clean_name(await bot._db(bot._links.main_name, user.id) or "") \
            or clean_name(user.display_name) or f"collector {user.id}"
        await bot._db(bot._collectors.invite, user.id, label, inter.user.id, inter.channel_id)
        await inter.response.send_message(
            f"{user.mention}, you are invited to run a **GuildLedger collector** (your PC sends the guild log to"
            f" the archive while you play; archive name: **{dpy.utils.escape_markdown(label)}**).\n"
            "Press the button to get your personal package; only you can use it, and you can press it again"
            " later to download the package once more.",
            view=package_view(user.id), allowed_mentions=dpy.AllowedMentions(users=[user]))

    @group.command(name="remove", description="Revoke an officer's collector: deletes their upload link")
    @app_commands.describe(user="The officer")
    async def remove(inter: dpy.Interaction, user: dpy.User):
        await inter.response.defer(ephemeral=True, thinking=True)
        webhook_id = await bot._db(bot._collectors.remove, user.id)
        await bot.refresh_collectors()
        note = "They had no collector set up here; any open invitation is withdrawn."
        if webhook_id is not None:
            note = "Their upload link is deleted: uploads from their PC stop working at once."
            try:
                hook = await bot.fetch_webhook(webhook_id)
                await hook.delete(reason=f"GuildLedger collector removed by {inter.user}")
            except dpy.NotFound:
                pass
            except dpy.DiscordException as e:
                log.error("collector removal: could not delete webhook %s: %s", webhook_id, e)
                note = ("Their uploads are ignored from now on, but I could not delete the webhook in Discord;"
                        " delete it by hand in `#gl-ingest` → Integrations → Webhooks.")
        await inter.followup.send(f"{user.mention}: {note}", ephemeral=True, allowed_mentions=NO_MENTIONS)

    @group.command(name="list", description="Who is set up as a collector, and when they last uploaded")
    async def list_(inter: dpy.Interaction):
        reg, cfg, open_ = await bot._db(bot._collectors.overview, bot.cfg.collectors)
        lines = ["**Collectors set up through the bot**"]
        lines += [f"- **{dpy.utils.escape_markdown(c.name)}** (<@{c.user_id}>): "
                  + (f"last upload {ts(c.last_upload_at)}" if c.first_upload_at else "package handed out, no upload yet")
                  for c in reg] or ["- none"]
        if cfg:
            lines.append("**From the config file** (`[collectors]`)")
            lines += [f"- **{dpy.utils.escape_markdown(n)}**: last upload {ts(t)}" for n, t in cfg]
        if open_:
            lines.append("**Invited, package not fetched yet**")
            lines += [f"- {dpy.utils.escape_markdown(n)} (<@{u}>)" for u, n in open_]
        await inter.response.send_message("\n".join(lines)[:1990], ephemeral=True, allowed_mentions=NO_MENTIONS)

    bot.tree.add_command(group)
