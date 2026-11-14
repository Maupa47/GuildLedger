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

if TYPE_CHECKING:
    from .client import LedgerBot

log = logging.getLogger(__name__)
NO_MENTIONS = dpy.AllowedMentions.none()


def ts(t: int | None, style: str = "f") -> str:
    return f"<t:{int(t)}:{style}>" if t else "never"


def esc(s: str | None) -> str:
    return dpy.utils.escape_markdown(s or "?")


def is_officer(inter: dpy.Interaction) -> bool:
    p = getattr(inter, "permissions", None)
    return bool(p and (p.manage_roles or p.administrator))


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
            await bot.sync_roles(interaction.user.id)


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


# --------------------------------------------------------------------------------- /roles (decision 5)

def register_roles(bot: "LedgerBot") -> None:
    roles = app_commands.Group(name="roles", description="Officers: which Discord roles linked members get",
                               default_permissions=dpy.Permissions(manage_roles=True), guild_only=True)

    async def reply(inter: dpy.Interaction, text: str) -> None:
        await inter.response.send_message(text[:1990], ephemeral=True, allowed_mentions=NO_MENTIONS)

    async def rank_names(inter: dpy.Interaction, current: str):
        ranks = await bot._db(bot._links.guild_ranks)
        return [app_commands.Choice(name=r[0][:100], value=r[0][:100]) for r in ranks
                if current.lower() in r[0].lower()][:25]

    @roles.command(name="show", description="Guild ranks, member counts and the Discord role each one gets")
    async def show(inter: dpy.Interaction):
        verified, ranks = await bot._db(bot._links.role_settings, bot.cfg.verified_role_id, bot.cfg.rank_roles)
        guild_ranks = await bot._db(bot._links.guild_ranks)
        lines = ["**Role for every linked guild member:** " + (f"<@&{verified}>" if verified else "none (/roles verified)")]
        lines.append("**Guild rank -> Discord role:**")
        for name, _, count in guild_ranks:
            lines.append(f"- {esc(name)} ({count} members): " + (f"<@&{ranks[name]}>" if name in ranks else "no role"))
        for name, rid in ranks.items():
            if name not in {g[0] for g in guild_ranks}:
                lines.append(f"- {esc(name)} (no member has this rank now): <@&{rid}>")
        if not guild_ranks:
            lines.append("- (no member list yet: it arrives with a collector's upload)")
        lines.append("Nicknames: " + ("set to the main character" if bot.cfg.set_nickname else "left alone"))
        await reply(inter, "\n".join(lines))

    @roles.command(name="verified", description="The role every member with a linked character in the guild gets")
    @app_commands.describe(role="e.g. @guild-member; leave empty to stop giving a role")
    async def verified(inter: dpy.Interaction, role: dpy.Role | None = None):
        await bot._db(bot._links.set_verified_role, role.id if role else None)
        await reply(inter, f"Linked guild members get {role.mention}." if role else "No role for linked members.")

    @roles.command(name="rank", description="The Discord role for one guild rank")
    @app_commands.describe(rank="Guild rank as in game", role="Discord role; leave empty to remove")
    @app_commands.autocomplete(rank=rank_names)
    async def rank(inter: dpy.Interaction, rank: str, role: dpy.Role | None = None):
        await bot._db(bot._links.set_rank_role, rank, role.id if role else None, bot.cfg.rank_roles)
        await reply(inter, f"Guild rank **{esc(rank)}** gets {role.mention}." if role
                    else f"Guild rank **{esc(rank)}** gets no role now.")

    @roles.command(name="sync", description="Apply the role settings to every linked member now")
    async def sync(inter: dpy.Interaction):
        await inter.response.defer(ephemeral=True, thinking=True)
        users = await bot._db(bot._links.linked_users)
        for uid in users:
            await bot.sync_roles(uid)
        await inter.followup.send(f"Checked the roles of {len(users)} linked member(s).", ephemeral=True)

    bot.tree.add_command(roles)


# --------------------------------------------------------------------------------- commands

def register(bot: "LedgerBot") -> None:
    tree = bot.tree
    register_roles(bot)

    async def reply(inter: dpy.Interaction, text: str, file: dpy.File | None = None) -> None:
        kw = {"ephemeral": True, "allowed_mentions": NO_MENTIONS}
        if file:
            kw["file"] = file
        await inter.response.send_message(text[:1990], **kw)

    @tree.command(name="link", description="Link your WoW characters to your Discord account")
    async def link(inter: dpy.Interaction):
        code = await bot._db(bot._links.new_code, inter.user.id)
        pending = await bot._db(bot._links.open_for, inter.user.id)
        text = (f"In WoW, type **`/gl link {code}`** (valid 30 minutes). An officer's GuildLedger must be online to"
                " pass it on; then I ask you here to confirm the character.")
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
        if target.id != inter.user.id and not is_officer(inter):
            await reply(inter, "Only officers can look up other users.")
            return
        rows = await bot._db(bot._links.chars, target.id)
        if not rows:
            await reply(inter, f"{esc(target.display_name)} has no linked characters.")
            return
        lines = [f"**{esc(r['name'])}** - level {r['level'] or '?'} {r['class'] or ''} {r['rank_name'] or ''}"
                 f"{'' if r['in_guild'] else ' (not in the guild)'} - last seen online {ts(r['last_seen'], 'R')}"
                 for r in rows]
        await reply(inter, f"Characters of {esc(target.display_name)}:\n" + "\n".join(lines))

    @tree.command(name="whois", description="Which Discord user plays this character")
    async def whois(inter: dpy.Interaction, character: str):
        rows = await bot._db(bot._links.whois, character)
        if not rows:
            await reply(inter, f"**{esc(character)}** is not linked to anyone.")
            return
        await reply(inter, "\n".join(f"**{esc(n)}** is played by <@{u}>." for u, n in rows))

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
