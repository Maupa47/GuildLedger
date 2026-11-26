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


def plan_setup(stored: dict, existing: set[int]) -> tuple[dict[str, int], list[str]]:
    """Which counter channels to keep (they still exist: moved, not made again) and which kinds to make."""
    keep = {k: int(v) for k, v in (stored or {}).items() if k in KINDS and int(v) in existing}
    return keep, [k for k in KINDS if k not in keep]


async def setup_counters(bot: "LedgerBot", category: dpy.CategoryChannel) -> str:
    """Make the counter channels in `category`; a second run moves the existing ones there instead of making a
    second pair."""
    guild = category.guild
    want = names(await bot._db(bot._links.status))
    locked = {guild.default_role: dpy.PermissionOverwrite(connect=False, view_channel=True)}
    stored = await bot.setting("counters.channels") or {}
    keep, make = plan_setup(stored, {c.id for c in guild.channels})
    try:
        for kind, cid in keep.items():
            ch = guild.get_channel(cid)
            if ch is not None and ch.category_id != category.id:
                await ch.edit(category=category, reason="GuildLedger counters")
        for kind in make:
            ch = await guild.create_voice_channel(want[kind], category=category, overwrites=locked,
                                                  reason="GuildLedger counters")
            keep[kind] = ch.id
    except dpy.Forbidden:
        return "I need *Manage Channels* in that category to make or move the counter channels."
    await bot._db(bot._settings.set, "counters.channels", keep)
    return ("Counter channels: " + ", ".join(f"<#{keep[k]}>" for k in KINDS if k in keep)
            + ". They update every 15 minutes. To remove them, delete the two channels in Discord.")


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
