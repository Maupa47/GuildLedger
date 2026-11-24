"""Counter channels (docs/dev/PLAN_COMMUNITY.md D7): channel names such as "Guild members: 512", "Linked: 140",
kept current for the case that ServerStats is removed. `/setup counters category:` makes two locked voice
channels in that category; a round renames them when the number changed, at most every 15 minutes (Discord
allows only two renames of a channel per 10 minutes). Needs Manage Channels in that category only.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import discord as dpy

if TYPE_CHECKING:
    from ..client import LedgerBot

log = logging.getLogger(__name__)

EVERY = 900
KINDS = ("members", "linked")


def names(status: dict) -> dict[str, str]:
    """Wanted channel names from Links.status()."""
    return {"members": f"Guild members: {status['members']}", "linked": f"Linked: {status['linked']}"}


async def setup_counters(bot: "LedgerBot", category: dpy.CategoryChannel) -> str:
    guild = category.guild
    status = await bot._db(bot._links.status)
    want = names(status)
    locked = {guild.default_role: dpy.PermissionOverwrite(connect=False, view_channel=True)}
    made = {}
    try:
        for kind in KINDS:
            ch = await guild.create_voice_channel(want[kind], category=category, overwrites=locked,
                                                  reason="GuildLedger counters")
            made[kind] = ch.id
    except dpy.Forbidden:
        return "I need *Manage Channels* in that category to make the counter channels."
    await bot._db(bot._settings.set, "counters.channels", made)
    return "Counter channels made: " + ", ".join(f"<#{i}>" for i in made.values()) + ". They update every 15 minutes."


async def counters_round(bot: "LedgerBot") -> int:
    if time.monotonic() - bot._counters_at < EVERY:
        return 0
    bot._counters_at = time.monotonic()
    channels = await bot.setting("counters.channels") or {}
    if not channels:
        return 0
    want = names(await bot._db(bot._links.status))
    n = 0
    for kind, cid in channels.items():
        ch = bot.get_channel(int(cid))
        if ch is None or kind not in want or ch.name == want[kind]:
            continue
        try:
            await ch.edit(name=want[kind], reason="GuildLedger counters")
            n += 1
        except dpy.DiscordException as e:
            log.info("counter channel %s: %s", cid, e)
    return n
