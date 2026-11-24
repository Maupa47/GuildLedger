"""Discord roles and nickname of linked members (decision 5, docs/dev/PACK_PLAN.md): /roles and sync_roles."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import discord as dpy
from discord import app_commands

from .common import esc, reply

if TYPE_CHECKING:
    from ..client import LedgerBot

log = logging.getLogger(__name__)


async def sync_roles(bot: "LedgerBot", user_id: int) -> None:
    """Roles by guild rank, the verified role, the nickname. Off unless configured."""
    cfg = bot.cfg
    if not cfg.server_id or not bot._links:
        return
    verified_id, rank_roles = await bot._db(bot._links.role_settings, cfg.verified_role_id, cfg.rank_roles)
    set_nick = await bot.setting_bool("nickname", cfg.set_nickname)
    if not (rank_roles or verified_id or set_nick):
        return
    server = bot.get_guild(cfg.server_id)
    if server is None:
        return
    try:
        member = server.get_member(user_id) or await server.fetch_member(user_id)
    except dpy.DiscordException:
        return
    rank, inside = await bot._db(bot._links.desired_rank, user_id)
    out_since = await bot._db(bot._links.out_of_guild_since, user_id)
    managed = set(rank_roles.values()) | ({verified_id} if verified_id else set())
    if inside:
        want = {rank_roles[rank]} if rank in rank_roles else set()
        if verified_id:
            want.add(verified_id)
    elif out_since is not None and time.time() - out_since > cfg.grace_days * 86400:
        want = set()
    else:
        return  # left recently: keep roles during the grace period
    have = {r.id for r in member.roles} & managed
    try:
        add = [server.get_role(i) for i in want - have if server.get_role(i)]
        remove = [server.get_role(i) for i in have - want if server.get_role(i)]
        if add:
            await member.add_roles(*add, reason="GuildLedger link: guild rank")
        if remove:
            await member.remove_roles(*remove, reason="GuildLedger link: guild rank changed or left")
        if set_nick and inside:
            nick = await bot._db(bot._links.main_name, user_id)
            if nick and member.nick != nick[:32]:
                if member.id == server.owner_id:
                    if user_id not in bot._owner_nick_logged:
                        bot._owner_nick_logged.add(user_id)
                        log.info("nickname of the server owner cannot be set by a bot (wanted %r)", nick[:32])
                else:
                    await member.edit(nick=nick[:32], reason="GuildLedger link: main character")
    except dpy.Forbidden:
        log.error("roles/nickname for %s refused: give the bot Manage Roles and Manage Nicknames and move its"
                  " role above the roles it assigns", user_id)
    except dpy.DiscordException as e:
        log.error("roles/nickname for %s failed: %s", user_id, e)


def register_roles(bot: "LedgerBot") -> None:
    roles = app_commands.Group(name="roles", description="Officers: which Discord roles linked members get",
                               default_permissions=dpy.Permissions(manage_roles=True), guild_only=True)

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
        nick = await bot.setting_bool("nickname", bot.cfg.set_nickname)
        lines.append("Nicknames: " + ("set to the main character" if nick else "left alone") + " (/setup nickname)")
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
