"""Discord side of the sign-up (onboarding.py): Verify button, the check's buttons, the welcome, Get my link code.

Every button is persistent through its custom_id (works after a restart). The check's buttons carry only their
position; the right answer is in the database.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord as dpy

from .common import NO_MENTIONS, esc
from .onboarding import welcome_text

if TYPE_CHECKING:
    from ..client import LedgerBot

log = logging.getLogger(__name__)

GATE_TEXT = ("**Welcome!** Press **Verify** to get access to the server. It is a quick check that you are a"
             " person; after it I send you how to link your WoW character.")


class VerifyButton(dpy.ui.DynamicItem[dpy.ui.Button], template=r"gl:gate:start"):
    def __init__(self):
        super().__init__(dpy.ui.Button(label="Verify", style=dpy.ButtonStyle.success, custom_id="gl:gate:start"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):  # noqa: ARG003
        return cls()

    async def callback(self, interaction: dpy.Interaction) -> None:
        bot: LedgerBot = interaction.client  # type: ignore[assignment]
        role_id = await bot._db(bot._settings.get_int, "gate.role", 0)
        member = interaction.user
        if role_id and isinstance(member, dpy.Member) and any(r.id == role_id for r in member.roles):
            await interaction.response.send_message("You are already verified.", ephemeral=True)
            return
        min_age = await bot._db(bot._settings.get_int, "gate.min_age_days", 0)
        created = member.created_at.timestamp() if getattr(member, "created_at", None) else None
        task = await bot._db(bot._gate.new_task, member.id, created, min_age)
        if task.status != "task":
            await interaction.response.send_message(task.text, ephemeral=True)
            if task.status == "locked":
                await bot.ops_line(f"Bot check: {member} is locked out for a while (too many wrong tries).")
            return
        view = dpy.ui.View(timeout=None)
        for i, label in enumerate(task.labels or []):
            view.add_item(PickButton(i, label))
        await interaction.response.send_message(task.text, view=view, ephemeral=True)


class PickButton(dpy.ui.DynamicItem[dpy.ui.Button], template=r"gl:gate:pick:(?P<i>[0-4])"):
    def __init__(self, i: int, label: str = "?"):
        super().__init__(dpy.ui.Button(label=label, style=dpy.ButtonStyle.secondary, custom_id=f"gl:gate:pick:{i}"))
        self.i = i

    @classmethod
    async def from_custom_id(cls, interaction, item, match):  # noqa: ARG003
        return cls(int(match["i"]), item.label or "?")

    async def callback(self, interaction: dpy.Interaction) -> None:
        bot: LedgerBot = interaction.client  # type: ignore[assignment]
        res = await bot._db(bot._gate.check, interaction.user.id, self.i)
        if res.status == "wrong":
            await interaction.response.edit_message(content=res.text)  # same buttons, one try less
            return
        if res.status != "passed":
            await interaction.response.edit_message(content=res.text, view=None)
            if res.status == "locked":
                await bot.ops_line(f"Bot check: {interaction.user} locked out after 3 wrong tries.")
            return
        await interaction.response.edit_message(content="Thanks, checking done. One moment…", view=None)
        await passed(bot, interaction)


async def passed(bot: "LedgerBot", interaction: dpy.Interaction) -> None:
    member = interaction.user
    role_id = await bot._db(bot._settings.get_int, "gate.role", 0)
    note = ""
    if role_id and isinstance(member, dpy.Member) and interaction.guild:
        role = interaction.guild.get_role(role_id)
        try:
            if role is None:
                raise LookupError("the gate role no longer exists (/setup gate)")
            await member.add_roles(role, reason="GuildLedger: passed the bot check")
        except (dpy.DiscordException, LookupError) as e:
            log.error("bot check: could not give the gate role to %s: %s", member.id, e)
            note = "\n(I could not give you the role; an officer has been told.)"
            await bot.ops_line(f"❌ Bot check: could not give the role to {member}: {e}")
    await bot.ops_line(f"✅ Bot check passed: {member} ({member.id}).")
    text, view = await welcome_message(bot)
    try:
        await member.send(text, view=view, allowed_mentions=NO_MENTIONS)
        await interaction.followup.send("You are in. I sent you a private message with the next steps." + note,
                                        ephemeral=True)
    except dpy.DiscordException:
        await interaction.followup.send(text + note, view=view, ephemeral=True, allowed_mentions=NO_MENTIONS)


async def welcome_message(bot: "LedgerBot") -> tuple[str, dpy.ui.View]:
    custom = await bot.setting("welcome.text")
    url = await bot.setting("addon.url")
    view = dpy.ui.View(timeout=None)
    view.add_item(CodeButton())
    return welcome_text(custom, url), view


class CodeButton(dpy.ui.DynamicItem[dpy.ui.Button], template=r"gl:link:code"):
    """Get my link code: the same as /link, from the welcome message."""

    def __init__(self):
        super().__init__(dpy.ui.Button(label="Get my link code", style=dpy.ButtonStyle.primary,
                                       custom_id="gl:link:code"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):  # noqa: ARG003
        return cls()

    async def callback(self, interaction: dpy.Interaction) -> None:
        bot: LedgerBot = interaction.client  # type: ignore[assignment]
        code = await bot._db(bot._links.new_code, interaction.user.id)
        await interaction.response.send_message(code_text(code), ephemeral=interaction.guild is not None,
                                                allowed_mentions=NO_MENTIONS)


def code_text(code: str) -> str:
    return (f"Your link code: **`{esc(code)}`**\n"
            f"- With the addon pack: in WoW type **`/gl link {code}`** (valid 30 minutes).\n"
            f"- Without the addon: write **`!link {code}`** in guild chat (valid 10 minutes).\n"
            "An officer's collector passes it on (after their next /reload or logout); then I ask you here to"
            " confirm the character.")


def gate_view() -> dpy.ui.View:
    view = dpy.ui.View(timeout=None)
    view.add_item(VerifyButton())
    return view
