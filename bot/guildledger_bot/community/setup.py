"""/setup: bot settings an admin changes in Discord (Manage Server). Saved in the archive (settings.py).

docs/dev/PLAN_COMMUNITY.md 5.5: config.toml keeps only secrets and what the process needs to start.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

import discord as dpy
from discord import app_commands

from .common import NO_MENTIONS, esc, reply
from .onboarding_ui import GATE_TEXT, gate_view
from .rolemenus import GROUPS
from .rolemenus_ui import PANEL_TEXT, panel_view

if TYPE_CHECKING:
    from ..client import LedgerBot

log = logging.getLogger(__name__)


class WelcomeModal(dpy.ui.Modal, title="Welcome message"):
    text = dpy.ui.TextInput(label="Text before the link steps (empty = default)", style=dpy.TextStyle.paragraph,
                            required=False, max_length=1200)

    def __init__(self, bot: "LedgerBot", current: str | None):
        super().__init__()
        self.bot = bot
        self.text.default = current or ""

    async def on_submit(self, interaction: dpy.Interaction) -> None:
        value = (self.text.value or "").strip() or None
        await self.bot._db(self.bot._settings.set, "welcome.text", value)
        from .onboarding_ui import welcome_message
        preview, _ = await welcome_message(self.bot)
        await interaction.response.send_message("Saved. New members get:\n\n" + preview, ephemeral=True,
                                                allowed_mentions=NO_MENTIONS)


def register_setup(bot: "LedgerBot") -> None:
    setup = app_commands.Group(name="setup", description="Admins: bot settings (sign-up, roles, directory)",
                               default_permissions=dpy.Permissions(manage_guild=True), guild_only=True)
    S = bot._settings

    async def save(key, value):
        await bot._db(S.set, key, value)

    @setup.command(name="gate", description="Post the Verify button (bot check) and choose the role it gives")
    @app_commands.describe(channel="Where the Verify button goes (visible to everyone)",
                           role="The role members get after the check",
                           min_account_age_days="Discord accounts younger than this must ask an officer (0 = off)")
    async def gate(inter: dpy.Interaction, channel: dpy.TextChannel, role: dpy.Role,
                   min_account_age_days: app_commands.Range[int, 0, 365] = 0):
        me = inter.guild.me if inter.guild else None
        if me is not None and role >= me.top_role:
            await reply(inter, f"My role must sit above {role.mention} (Server Settings → Roles), or I cannot give it.")
            return
        try:
            msg = await channel.send(GATE_TEXT, view=gate_view(), allowed_mentions=NO_MENTIONS)
        except dpy.DiscordException as e:
            await reply(inter, f"I cannot post in {channel.mention}: {e}")
            return
        await save("gate.role", role.id)
        await save("gate.channel", channel.id)
        await save("gate.message", msg.id)
        await save("gate.min_age_days", min_account_age_days)
        await reply(inter, f"Verify button posted in {channel.mention}; it gives {role.mention}"
                    + (f"; accounts younger than {min_account_age_days} days are sent to an officer."
                       if min_account_age_days else ".") + " Try it with a second account before you switch off"
                    " the old bot's panel.")

    @setup.command(name="welcome", description="Edit the private welcome message new members get")
    async def welcome(inter: dpy.Interaction):
        await inter.response.send_modal(WelcomeModal(bot, await bot.setting("welcome.text")))

    @setup.command(name="addon", description="The download link of the addon pack shown in the welcome")
    @app_commands.describe(url="e.g. the CurseForge page; empty to remove")
    async def addon(inter: dpy.Interaction, url: str | None = None):
        if url and not url.startswith(("https://", "http://")):
            await reply(inter, "That does not look like a web address.")
            return
        await save("addon.url", url or None)
        await reply(inter, f"Addon link: {url}" if url else "No addon link in the welcome.")

    @setup.command(name="nickname", description="Set linked members' server nickname to their main character")
    async def nickname(inter: dpy.Interaction, mode: Literal["on", "off"]):
        await save("nickname", mode == "on")
        await reply(inter, "Nicknames follow the main character (needs Manage Nicknames; the server owner's"
                    " cannot be set)." if mode == "on" else "Nicknames are left alone.")

    @setup.command(name="announce", description="Channel for a public line when someone links for the first time")
    @app_commands.describe(channel="Empty: no public line")
    async def announce(inter: dpy.Interaction, channel: dpy.TextChannel | None = None):
        await save("announce.channel", channel.id if channel else None)
        await reply(inter, f"New links are announced in {channel.mention}." if channel else "No public line.")

    @setup.command(name="directory", description="The forum where every guild character is listed")
    @app_commands.describe(forum="A forum channel; members should not be able to post there. Empty: off")
    async def directory(inter: dpy.Interaction, forum: dpy.ForumChannel | None = None):
        await save("directory.forum", forum.id if forum else None)
        await reply(inter, (f"Directory: {forum.mention}. The first posts appear within 10 minutes and are written"
                            " 10 at a time. Tip: create forum tags named after the classes (Warrior, Mage, …);"
                            " posts get their main's class tag.") if forum else "Directory off (posts stay).")

    @setup.command(name="professions", description="The forum with one post per profession: crafters and recipes")
    @app_commands.describe(forum="A forum channel; members should not be able to post there. Empty: off")
    async def professions(inter: dpy.Interaction, forum: dpy.ForumChannel | None = None):
        await save("professions.forum", forum.id if forum else None)
        await reply(inter, (f"Professions: {forum.mention}. One post per profession appears within 10 minutes,"
                            " 10 at a time, and is kept up to date. Members look things up with /craft.")
                    if forum else "Profession forum off (posts stay).")

    @setup.command(name="bank", description="Where the guild bank is shown, and the officers' ledger channel")
    @app_commands.describe(channel="A channel for the bank's contents (one message per tab). Empty: off",
                           ledger_channel="An officers-only channel for who put in or took out what. Empty: off")
    async def bank(inter: dpy.Interaction, channel: dpy.TextChannel | None = None,
                   ledger_channel: dpy.TextChannel | None = None):
        await save("bank.channel", channel.id if channel else None)
        await save("bank.ledger", ledger_channel.id if ledger_channel else None)
        lines = [f"Bank: {channel.mention}, one message per tab, edited in place within 5 minutes." if channel
                 else "Bank channel off (messages stay)."]
        if ledger_channel:
            everyone = inter.guild.default_role if inter.guild else None
            public = everyone is not None and ledger_channel.permissions_for(everyone).view_channel
            lines.append(f"Ledger: {ledger_channel.mention}; new lines only (earlier ones are archived, not posted)."
                         + (" **Warning:** everyone can see that channel; the ledger should be officers only."
                            if public else ""))
        else:
            lines.append("Ledger off.")
        await reply(inter, "\n".join(lines))

    @setup.command(name="armory", description="Armory address with {name}; empty = no armory links")
    async def armory(inter: dpy.Interaction, url: str | None = None):
        if url and "{name}" not in url:
            await reply(inter, "The address needs `{name}` where the character name goes.")
            return
        await save("armory.url", url or "")
        await reply(inter, f"Armory links: `{url}`" if url else "No armory links.")

    @setup.command(name="counters", description="Channels showing the number of guild members and linked members")
    @app_commands.describe(category="The category for two locked voice channels (needs Manage Channels there)")
    async def counters(inter: dpy.Interaction, category: dpy.CategoryChannel):
        from .counters import setup_counters
        await inter.response.defer(ephemeral=True, thinking=True)
        await inter.followup.send(await setup_counters(bot, category), ephemeral=True, allowed_mentions=NO_MENTIONS)

    rolemenu = app_commands.Group(name="rolemenu", description="Interest and language role menus", parent=setup)

    @rolemenu.command(name="add", description="Add or change an entry of a role menu")
    @app_commands.describe(group="interests or languages", label="What members see", role="The Discord role",
                           emoji="Optional emoji")
    async def rm_add(inter: dpy.Interaction, group: Literal["interests", "languages"], label: str, role: dpy.Role,
                     emoji: str | None = None):
        me = inter.guild.me if inter.guild else None
        if me is not None and role >= me.top_role:
            await reply(inter, f"My role must sit above {role.mention}, or I cannot give it.")
            return
        if role.permissions.value and (role.permissions.administrator or role.permissions.manage_guild
                                       or role.permissions.manage_roles or role.permissions.ban_members):
            await reply(inter, "That role has moderator permissions; a role menu must not hand it out.")
            return
        await reply(inter, await bot._db(bot._menus.add, group, label, role.id, emoji))

    @rolemenu.command(name="remove", description="Remove an entry from a role menu (the role itself stays)")
    async def rm_remove(inter: dpy.Interaction, group: Literal["interests", "languages"], label: str):
        ok = await bot._db(bot._menus.remove, group, label)
        await reply(inter, "Removed." if ok else "No such entry.")

    @rolemenu.command(name="preset", description="Register the default list of a menu (roles made on first pick)")
    async def rm_preset(inter: dpy.Interaction, group: Literal["interests", "languages"]):
        n = await bot._db(bot._menus.preset, group)
        await reply(inter, f"{GROUPS[group]}: {n} entr{'y' if n == 1 else 'ies'} added. A role is created the"
                    " first time a member picks it (or a role with the same name is used).")

    @rolemenu.command(name="post", description="Post the role panel in a channel")
    async def rm_post(inter: dpy.Interaction, channel: dpy.TextChannel):
        view = await panel_view(bot)
        if view is None:
            await reply(inter, "The menus are empty: /setup rolemenu add or /setup rolemenu preset first.")
            return
        try:
            await channel.send(PANEL_TEXT, view=view, allowed_mentions=NO_MENTIONS)
        except dpy.DiscordException as e:
            await reply(inter, f"I cannot post in {channel.mention}: {e}")
            return
        await save("rolemenu.channel", channel.id)  # newly linked members are pointed there
        await reply(inter, f"Role panel posted in {channel.mention}. After changing a menu, post it again and"
                    " delete the old one.")

    @setup.command(name="show", description="All settings made with /setup")
    async def show(inter: dpy.Interaction):
        s = await bot._db(S.all)

        def ch(k):
            return f"<#{s[k]}>" if s.get(k) else "not set"

        def ro(k):
            return f"<@&{s[k]}>" if s.get(k) else "not set"

        lines = [
            f"**Bot check:** button in {ch('gate.channel')}, gives {ro('gate.role')},"
            f" minimum account age {s.get('gate.min_age_days', 0)} days",
            f"**Welcome:** {'own text' if s.get('welcome.text') else 'default text'}; addon link:"
            f" {esc(s.get('addon.url')) if s.get('addon.url') else 'none'}",
            f"**Nicknames:** {'main character' if s.get('nickname', bot.cfg.set_nickname) else 'left alone'}",
            f"**First link announced in:** {ch('announce.channel')}",
            f"**Profession forum:** {ch('professions.forum')}",
            f"**Guild bank:** {ch('bank.channel')}; ledger (officers): {ch('bank.ledger')}",
            "**Counter channels:** " + (", ".join(f"<#{i}>" for i in s["counters.channels"].values())
                                        if isinstance(s.get("counters.channels"), dict) and s["counters.channels"]
                                        else "not set"),
            f"**Directory forum:** {ch('directory.forum')}; armory: "
            + ("off" if s.get("armory.url") == "" else f"`{s.get('armory.url') or 'EU default'}`"),
        ]
        for grp, title in GROUPS.items():
            entries = await bot._db(bot._menus.entries, grp)
            lines.append(f"**{title} menu:** " + (", ".join(
                f"{esc(e.label)}" + (f" <@&{e.role_id}>" if e.role_id else " (made on first pick)")
                for e in entries) if entries else "empty"))
        await reply(inter, "\n".join(lines))

    bot.tree.add_command(setup)
