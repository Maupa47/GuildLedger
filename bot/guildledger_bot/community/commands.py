"""Slash commands and the link confirmation buttons (Discord side of link.py and activity.py).

All answers are ephemeral (only the asker sees them). Officer commands need the Manage Roles permission.
Database work runs on the bot's worker thread (bot._db), never in the event loop.
"""

from __future__ import annotations

import io
import logging
import time
from typing import TYPE_CHECKING

import discord as dpy
from discord import app_commands

from . import activity
from .common import NO_MENTIONS, esc, is_officer, reply, ts  # noqa: F401 (re-exported)
from .roles import register_roles

if TYPE_CHECKING:
    from ..client import LedgerBot

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------------- confirmation buttons

class LinkButton(dpy.ui.DynamicItem[dpy.ui.Button], template=r"gl:link:(?P<act>yes|no):(?P<cid>[0-9]+)"):
    """A Confirm / Not me button; persistent (works after a restart) through its custom_id."""

    def __init__(self, act: str, cid: int):
        super().__init__(dpy.ui.Button(
            label="Confirm" if act == "yes" else "Not me",
            style=dpy.ButtonStyle.success if act == "yes" else dpy.ButtonStyle.secondary,
            custom_id=f"gl:link:{act}:{cid}"))
        self.act, self.cid = act, cid

    @classmethod
    async def from_custom_id(cls, interaction: dpy.Interaction, item: dpy.ui.Button, match):  # noqa: ARG003
        return cls(match["act"], int(match["cid"]))

    async def callback(self, interaction: dpy.Interaction) -> None:
        bot: LedgerBot = interaction.client  # type: ignore[assignment]
        msg = await bot._db(bot._links.answer, self.cid, interaction.user.id, self.act == "yes")
        try:
            await interaction.response.edit_message(content=msg, view=None)
        except dpy.DiscordException:
            await interaction.response.send_message(msg, ephemeral=True)
        if msg.startswith("Linked"):
            await after_link(bot, interaction.user.id, interaction)


async def after_link(bot: "LedgerBot", user_id: int, interaction: dpy.Interaction | None = None) -> None:
    """Roles and nickname; the first time a user is linked also the role menus and the public line (D1 5)."""
    await bot.sync_roles(user_id)
    if not await bot._db(bot._links.first_link_done, user_id):
        return
    from .rolemenus_ui import PANEL_TEXT, panel_view
    if interaction is not None:
        try:
            if interaction.guild is not None:  # roles can only be changed on the server
                view = await panel_view(bot)
                if view is not None:
                    await interaction.followup.send(PANEL_TEXT, view=view, ephemeral=True,
                                                    allowed_mentions=NO_MENTIONS)
            else:
                where = await bot._db(bot._settings.get_int, "rolemenu.channel", 0)
                if where:
                    await interaction.followup.send(f"Next: pick your interest and language roles in <#{where}>.",
                                                    allowed_mentions=NO_MENTIONS)
        except dpy.DiscordException as e:
            log.info("role menus after the first link of %s: %s", user_id, e)
    channel_id = await bot._db(bot._settings.get_int, "announce.channel", 0)
    main = await bot._db(bot._links.main_name, user_id)
    if channel_id and main:
        channel = bot.get_channel(channel_id)
        try:
            if channel is not None:
                await channel.send(f"👋 <@{user_id}> joined us, main **{esc(main)}**.", allowed_mentions=NO_MENTIONS)
        except dpy.DiscordException as e:
            log.info("announce channel %s: %s", channel_id, e)


async def may_see_others(bot: "LedgerBot", inter: dpy.Interaction) -> bool:
    """Decision 5: everyone with the linked-member role (without such a role: everyone linked), and officers."""
    if is_officer(inter):
        return True
    verified, _ = await bot._db(bot._links.role_settings, bot.cfg.verified_role_id, bot.cfg.rank_roles)
    if verified:
        return any(r.id == verified for r in getattr(inter.user, "roles", []))
    return bool(await bot._db(bot._links.chars, inter.user.id))


async def characters_text(bot: "LedgerBot", target: dpy.abc.User) -> str:
    from .directory import char_line
    from .directory_ui import armory_template
    rows = await bot._db(bot._links.chars, target.id)
    if not rows:
        return f"{esc(target.display_name)} has no linked characters."
    main = await bot._db(bot._links.main_name, target.id)
    template = await armory_template(bot)
    rows.sort(key=lambda r: (r["name"] != main, -(r["in_guild"] or 0), -(r["level"] or 0), r["name"]))
    lines = [char_line(r, template, main=r["name"] == main) for r in rows]
    thread = await bot._db(bot._directory.thread_of_user, target.id)
    post = f"\nForum post: <#{thread}>" if thread else ""
    return f"Characters of {esc(target.display_name)}:\n" + "\n".join(lines) + post


def confirm_view(cid: int) -> dpy.ui.View:
    view = dpy.ui.View(timeout=None)
    view.add_item(LinkButton("yes", cid))
    view.add_item(LinkButton("no", cid))
    return view


def confirm_text(name: str, kind: str) -> str:
    if kind == "alt":
        return (f"GuildLedger: **{esc(name)}** logged in on the same WoW account as your linked character."
                " Link it to you as well?")
    return (f"GuildLedger: the character **{esc(name)}** used your link code in game. Is this you?"
            " If you did not type the code on that character, press **Not me**.")


# --------------------------------------------------------------------------------- commands

def register(bot: "LedgerBot") -> None:
    tree = bot.tree
    register_roles(bot)
    from .lootcmds import register_loot
    register_loot(bot)

    @tree.command(name="link", description="Link your WoW characters to your Discord account")
    async def link(inter: dpy.Interaction):
        from .onboarding_ui import code_text
        code = await bot._db(bot._links.new_code, inter.user.id)
        pending = await bot._db(bot._links.open_for, inter.user.id)
        text = code_text(code)
        mine = await bot._db(bot._links.chars, inter.user.id)
        if mine:
            main = await bot._db(bot._links.main_name, inter.user.id)
            text += ("\n\nLinked now: " + ", ".join(esc(r["name"]) for r in mine)
                     + (f"; main **{esc(main)}** (change it with /main)." if main else "."))
        if not pending:
            await reply(inter, text)
            return
        await reply(inter, text + f"\n\nYou also have {len(pending)} open confirmation(s), see below.")
        for c in pending:
            await inter.followup.send(confirm_text(c.name, c.kind), view=confirm_view(c.id), ephemeral=True,
                                      allowed_mentions=NO_MENTIONS)

    @tree.command(name="unlink", description="Remove the link of one or all of your characters")
    @app_commands.describe(character="Character name (empty: all your characters)",
                           user="Officers only: unlink all characters of this user")
    async def unlink(inter: dpy.Interaction, character: str | None = None, user: dpy.User | None = None):
        if user and user.id != inter.user.id:
            if not is_officer(inter):
                await reply(inter, "Only officers can unlink other users.")
                return
            n = await bot._db(bot._links.unlink, user.id, None)
            await reply(inter, f"Removed {n} link(s) of {esc(user.display_name)}.")
            await bot.sync_roles(user.id)
            return
        n = await bot._db(bot._links.unlink, inter.user.id, character)
        await reply(inter, f"Removed {n} link(s)." if n else "Nothing to remove.")
        await bot.sync_roles(inter.user.id)

    @tree.command(name="chars", description="Characters linked to a Discord user")
    async def chars(inter: dpy.Interaction, user: dpy.User | None = None):
        target = user or inter.user
        if target.id != inter.user.id and not await may_see_others(bot, inter):
            await reply(inter, "Link your own character first (/link), then you can look up others.")
            return
        await reply(inter, await characters_text(bot, target))

    async def characters_menu(inter: dpy.Interaction, user: dpy.Member):
        if user.id != inter.user.id and not await may_see_others(bot, inter):
            await reply(inter, "Link your own character first (/link), then you can look up others.")
            return
        await reply(inter, await characters_text(bot, user))

    tree.add_command(app_commands.ContextMenu(name="Characters", callback=characters_menu))

    async def member_names(inter: dpy.Interaction, current: str):
        names = await bot._db(bot._links.search_members, current)
        return [app_commands.Choice(name=n[:100], value=n[:100]) for n in names]

    async def my_chars(inter: dpy.Interaction, current: str):
        rows = await bot._db(bot._links.chars, inter.user.id)
        return [app_commands.Choice(name=r["name"][:100], value=r["name"][:100]) for r in rows
                if current.lower() in r["name"].lower()][:25]

    @tree.command(name="whois", description="Which Discord user plays this character")
    @app_commands.autocomplete(character=member_names)
    async def whois(inter: dpy.Interaction, character: str):
        from .directory import char_line
        from .directory_ui import armory_template
        rows = await bot._db(bot._links.lookup, character)
        if not rows:
            await reply(inter, f"No guild character called **{esc(character)}** is known.")
            return
        template = await armory_template(bot)
        out = []
        for r in rows:
            line = char_line(r, template)
            if r["uid"]:
                thread = await bot._db(bot._directory.thread_of_user, r["uid"])
                line += f" - played by <@{r['uid']}>" + (f" (<#{thread}>)" if thread else "")
            else:
                line += " - not linked to Discord yet"
            out.append(line)
        await reply(inter, "\n".join(out))

    @tree.command(name="main", description="Choose your main character (your nickname and forum post follow it)")
    @app_commands.describe(character="One of your linked characters; empty = the highest level counts")
    @app_commands.autocomplete(character=my_chars)
    async def main_cmd(inter: dpy.Interaction, character: str | None = None):
        msg = await bot._db(bot._links.set_main, inter.user.id, character)
        await reply(inter, msg)
        await bot.sync_roles(inter.user.id)

    @tree.command(name="linkapprove", description="Officers: link a guild member's character at once")
    @app_commands.describe(user="The Discord member", character="Their character (current guild member)")
    @app_commands.autocomplete(character=member_names)
    @app_commands.default_permissions(manage_roles=True)
    async def linkapprove(inter: dpy.Interaction, user: dpy.Member, character: str):
        if not is_officer(inter):
            await reply(inter, "Only officers can use this.")
            return
        msg = await bot._db(bot._links.approve, inter.user.id, user.id, character)
        await reply(inter, msg)
        if msg.startswith("Linked"):
            log.info("link approved by %s: %s -> %s", inter.user.id, character, user.id)
            await bot.ops_line(f"🔗 {inter.user} linked {character} to {user} (approved by hand).")
            await after_link(bot, user.id, None)

    @tree.command(name="linkstatus", description="Officers: how many guild members are linked")
    async def linkstatus(inter: dpy.Interaction):
        if not is_officer(inter):
            await reply(inter, "Only officers can use this.")
            return
        st = await bot._db(bot._links.status)
        text = (f"Guild members: {st['members']}, linked: {st['linked']} (by {st['users']} Discord users),"
                f" not linked: {len(st['unlinked'])}.")
        if len(st["unlinked"]) <= 40:
            await reply(inter, text + ("\nNot linked: " + ", ".join(esc(n) for n in st["unlinked"])
                                       if st["unlinked"] else ""))
        else:
            data = io.BytesIO("\n".join(st["unlinked"]).encode("utf-8"))
            await reply(inter, text + " List attached.", dpy.File(data, "not-linked.txt"))

    @tree.command(name="seen", description="When a character was last seen online and last wrote in guild chat")
    async def seen(inter: dpy.Interaction, character: str):
        chars = await bot._db(activity.find_chars, bot._links, character)
        if not chars:
            await reply(inter, f"No guild member called **{esc(character)}** is known.")
            return
        rows = await bot._db(activity.seen, bot._links, chars)
        lines = [f"**{esc(r['name'])}**{'' if r['in_guild'] else ' (not in the guild any more)'}: last seen online"
                 f" {ts(r['online'], 'R')}, last guild chat line {ts(r['chat'], 'R')}" for r in rows]
        await reply(inter, "\n".join(lines) + "\n-# Last seen online is approximate: it is when a collector last saw"
                    " them online.")

    @tree.command(name="joined", description="When a character joined the guild")
    async def joined(inter: dpy.Interaction, character: str):
        chars = await bot._db(activity.find_chars, bot._links, character)
        if not chars:
            await reply(inter, f"No guild member called **{esc(character)}** is known.")
            return
        j = await bot._db(activity.joined, bot._links, chars[0])
        when = (f"between {ts(j['from'])} and {ts(j['when'])}" if j["from"] and j["from"] < (j["when"] or 0)
                else ts(j["when"]))
        by = f", invited/added by {esc(j['by'])}" if j["by"] else ""
        await reply(inter, f"**{esc(chars[0]['name'])}** joined {when} ({j['precision']}){by}.")

    @tree.command(name="activity", description="Characters and guild chat activity of a Discord user")
    async def act(inter: dpy.Interaction, user: dpy.User | None = None):
        target = user or inter.user
        rows = await bot._db(activity.activity, bot._links, target.id, int(time.time()))
        if not rows:
            await reply(inter, f"{esc(target.display_name)} has no linked characters (see /link).")
            return
        lines = [f"**{esc(r['name'])}** - level {r['level'] or '?'}{'' if r['in_guild'] else ' (left)'}:"
                 f" {r['lines7']} guild chat lines in 7 days, {r['lines30']} in 30 days, last seen online"
                 f" {ts(r['online'], 'R')}" for r in rows]
        await reply(inter, f"Activity of {esc(target.display_name)}:\n" + "\n".join(lines))

    @tree.command(name="inactive", description="Officers: guild members not seen online for some days")
    @app_commands.describe(days="Days without being seen online (default 30)")
    async def inactive(inter: dpy.Interaction, days: app_commands.Range[int, 1, 365] = 30):
        if not is_officer(inter):
            await reply(inter, "Only officers can use this.")
            return
        grouped, unlinked = await bot._db(activity.inactive, bot._links, days, int(time.time()))
        lines = [f"Not seen online for {days}+ days (approximate):", f"Linked users: {len(grouped)}"]
        for uid, chars in grouped.items():
            lines.append(f"<@{uid}>: " + ", ".join(f"{c['name']} ({ts(c['last_seen'], 'R')})" for c in chars))
        lines.append(f"Not linked: {len(unlinked)}")
        lines += [f"{c['name']} ({ts(c['last_seen'], 'R')})" for c in unlinked]
        text = "\n".join(lines)
        if len(text) <= 1900:
            await reply(inter, text)
        else:
            csv = ["discord_user,character,last_seen_unix"]
            csv += [f"{u},{c['name']},{c['last_seen'] or ''}" for u, cs in grouped.items() for c in cs]
            csv += [f",{c['name']},{c['last_seen'] or ''}" for c in unlinked]
            await reply(inter, f"{len(grouped)} linked users and {len(unlinked)} unlinked characters; list attached.",
                        dpy.File(io.BytesIO("\n".join(csv).encode("utf-8")), f"inactive-{days}d.csv"))
