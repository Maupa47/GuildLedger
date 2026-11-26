"""Discord side of professions (crafts.py, PLAN_COMMUNITY D4): the profession forum round and /craft."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord as dpy
from discord import app_commands

from . import crafts
from .common import reply
from .directory_ui import forum_round

if TYPE_CHECKING:
    from ..client import LedgerBot


async def crafts_round(bot: "LedgerBot") -> int:
    """One round (every 10 minutes): the profession forum's posts, at most 10 writes."""
    forum = bot._crafts
    return await forum_round(bot, "professions.forum", forum, lambda: forum.plan(forum.wanted()), "professions")


def register_crafts(bot: "LedgerBot") -> None:
    async def recipe_choices(inter: dpy.Interaction, current: str):
        hits = await bot._db(crafts.search, bot._archive.db, current)
        return [app_commands.Choice(name=label, value=str(spell)) for label, spell in hits]

    @bot.tree.command(name="craft", description="Who in the guild can craft something, and what it takes")
    @app_commands.autocomplete(recipe=recipe_choices)
    @app_commands.describe(recipe="A recipe or the item it makes (start typing, names are suggested)")
    async def craft(inter: dpy.Interaction, recipe: str):
        spell = await bot._db(crafts.resolve, bot._archive.db, recipe)
        if spell is None:
            await reply(inter, "No recipe matches that. Start typing and pick one of the suggestions.")
            return
        await reply(inter, await bot._db(crafts.answer, bot._archive.db, spell))
