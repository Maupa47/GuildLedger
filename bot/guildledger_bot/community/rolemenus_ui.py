"""Discord side of the role menus (rolemenus.py): the panel with one multi-select per group."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord as dpy

from .common import NO_MENTIONS
from .rolemenus import GROUPS

if TYPE_CHECKING:
    from ..client import LedgerBot

log = logging.getLogger(__name__)

PANEL_TEXT = ("**Pick your roles.** Choose what you are interested in and which languages you speak; pick again"
              " at any time to change it (an empty choice removes the roles of that menu).")


class RoleSelect(dpy.ui.DynamicItem[dpy.ui.Select], template=r"gl:rm:(?P<grp>[a-z]+)"):
    def __init__(self, grp: str, options: list[dpy.SelectOption] | None = None):
        options = options or [dpy.SelectOption(label="(empty)", value="-")]
        super().__init__(dpy.ui.Select(custom_id=f"gl:rm:{grp}", placeholder=GROUPS.get(grp, grp),
                                       min_values=0, max_values=len(options), options=options))
        self.grp = grp

    @classmethod
    async def from_custom_id(cls, interaction, item, match):  # noqa: ARG003
        return cls(match["grp"], list(item.options) or None)

    async def callback(self, interaction: dpy.Interaction) -> None:
        bot: LedgerBot = interaction.client  # type: ignore[assignment]
        values = [v for v in (interaction.data or {}).get("values", []) if v != "-"]
        await interaction.response.defer(ephemeral=True, thinking=True)
        text = await apply_selection(bot, interaction, self.grp, values)
        await interaction.followup.send(text, ephemeral=True, allowed_mentions=NO_MENTIONS)


async def apply_selection(bot: "LedgerBot", interaction: dpy.Interaction, grp: str, values: list[str]) -> str:
    guild, member = interaction.guild, interaction.user
    if guild is None or not hasattr(member, "add_roles"):  # a Member, not a DM user
        return "Role menus work only on the server."
    existing = {r.id for r in guild.roles}
    plan = await bot._db(bot._menus.plan, grp, values, {r.id for r in member.roles}, existing)
    add_ids = list(plan.add)
    try:
        for label in plan.create:
            role = dpy.utils.get(guild.roles, name=label)  # a role the admin made by hand is used
            if role is None:
                role = await guild.create_role(name=label, permissions=dpy.Permissions.none(), mentionable=False,
                                               reason="GuildLedger role menu: first member picked it")
            await bot._db(bot._menus.set_role, grp, label, role.id)
            if role not in member.roles:
                add_ids.append(role.id)
        add = [guild.get_role(i) for i in add_ids if guild.get_role(i)]
        remove = [guild.get_role(i) for i in plan.remove if guild.get_role(i)]
        if add:
            await member.add_roles(*add, reason="GuildLedger role menu")
        if remove:
            await member.remove_roles(*remove, reason="GuildLedger role menu")
    except dpy.Forbidden:
        if not bot._menu_refusal_logged:
            bot._menu_refusal_logged = True
            log.error("role menu: Discord refused a role change; the bot's role must sit above the menu roles"
                      " (Server Settings → Roles) and it needs Manage Roles")
            await bot.ops_line("❌ Role menu: Discord refused a role change. Move the bot's role above the menu"
                               " roles (Server Settings → Roles).")
        return "Discord did not let me change your roles. An officer has been told."
    except dpy.DiscordException as e:
        log.error("role menu for %s failed: %s", member.id, e)
        return "Something went wrong; please try again later."
    if not (add or remove):
        return "Nothing changed."
    parts = []
    if add:
        parts.append("added " + ", ".join(r.name for r in add))
    if remove:
        parts.append("removed " + ", ".join(r.name for r in remove))
    return "Done: " + "; ".join(parts) + "."


async def panel_view(bot: "LedgerBot") -> dpy.ui.View | None:
    view = dpy.ui.View(timeout=None)
    for grp in await bot._db(bot._menus.groups):
        entries = await bot._db(bot._menus.entries, grp)
        options = [dpy.SelectOption(label=e.label[:100], value=e.label[:100], emoji=e.emoji or None)
                   for e in entries]
        view.add_item(RoleSelect(grp, options))
    return view if view.children else None
