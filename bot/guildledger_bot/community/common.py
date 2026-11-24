"""Small helpers every community command uses: escaping, Discord timestamps, officer check, ephemeral replies."""

from __future__ import annotations

import discord as dpy

NO_MENTIONS = dpy.AllowedMentions.none()


def ts(t: int | None, style: str = "f") -> str:
    return f"<t:{int(t)}:{style}>" if t else "never"


def esc(s: str | None) -> str:
    return dpy.utils.escape_markdown(s or "?")


def is_officer(inter: dpy.Interaction) -> bool:
    p = getattr(inter, "permissions", None)
    return bool(p and (p.manage_roles or p.administrator))


def is_admin(inter: dpy.Interaction) -> bool:
    p = getattr(inter, "permissions", None)
    return bool(p and (p.manage_guild or p.administrator))


async def reply(inter: dpy.Interaction, text: str, file: dpy.File | None = None,
                view: dpy.ui.View | None = None) -> None:
    """Ephemeral answer, cut to Discord's limit; a follow-up when the interaction was already answered."""
    kw: dict = {"ephemeral": True, "allowed_mentions": NO_MENTIONS}
    if file:
        kw["file"] = file
    if view:
        kw["view"] = view
    if inter.response.is_done():
        await inter.followup.send(text[:1990], **kw)
    else:
        await inter.response.send_message(text[:1990], **kw)
