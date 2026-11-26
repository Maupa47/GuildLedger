"""Discord side of the guild bank (bank.py, PLAN_COMMUNITY D5): the bank channel, the officers' ledger, /bank."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord as dpy
from discord import app_commands

from . import bank
from .common import NO_MENTIONS, reply

if TYPE_CHECKING:
    from ..client import LedgerBot

log = logging.getLogger(__name__)


async def _channel(bot: "LedgerBot", key: str):
    cid = await bot._db(bot._settings.get_int, key, 0)
    if not cid:
        return None
    ch = bot.get_channel(cid)
    if ch is None:
        try:
            ch = await bot.fetch_channel(cid)
        except dpy.DiscordException as e:
            log.error("bank: channel %s (%s): %s", cid, key, e)
            return None
    return ch if isinstance(ch, (dpy.TextChannel, dpy.Thread)) else None


async def bank_round(bot: "LedgerBot") -> int:
    """One round: the bank channel's messages (edited in place), then new ledger lines. Returns writes done."""
    board, done = bot._bank, 0
    ch = await _channel(bot, "bank.channel")
    if ch is not None:
        for w in await bot._db(board.plan, ch.id):
            try:
                ids = await _apply(ch, w)
                await bot._db(board.done, ch.id, w, ids)
                done += 1
            except dpy.Forbidden as e:
                log.error("bank: Discord refused a write in #%s (needs Send Messages, Read Message History): %s",
                          ch, e)
                break
            except dpy.DiscordException as e:
                log.warning("bank: %s %s failed: %s", w.action, w.key, e)
    led = await _channel(bot, "bank.ledger")
    if led is not None:
        if await bot._db(bot._settings.get_int, "bank.ledger_started", 0) != led.id:
            n = await bot._db(board.start_ledger)
            await bot._db(bot._settings.set, "bank.ledger_started", led.id)
            log.info("bank ledger: %d earlier line(s) archived without posting", n)
        messages, keys = await bot._db(board.ledger_batches)
        try:
            for m in messages:
                await led.send(m, allowed_mentions=NO_MENTIONS)
                done += 1
            if keys:
                await bot._db(board.ledger_posted, keys)
        except dpy.DiscordException as e:
            log.warning("bank ledger: posting failed: %s", e)
    return done


async def _apply(ch, w: bank.Write) -> list[int]:
    if w.action == "delete":
        for mid in w.message_ids:
            try:
                await ch.get_partial_message(mid).delete()
            except dpy.NotFound:
                pass
        return []
    ids = list(w.message_ids)
    for i, text in enumerate(w.messages):
        if i < len(ids):
            try:
                await ch.get_partial_message(ids[i]).edit(content=text, allowed_mentions=NO_MENTIONS)
                continue
            except dpy.NotFound:
                pass
            ids[i] = (await ch.send(text, allowed_mentions=NO_MENTIONS)).id
        else:
            ids.append((await ch.send(text, allowed_mentions=NO_MENTIONS)).id)
    for extra in ids[len(w.messages):]:
        try:
            await ch.get_partial_message(extra).delete()
        except dpy.DiscordException:
            pass
    return ids[:len(w.messages)]


def register_bank(bot: "LedgerBot") -> None:
    async def item_choices(inter: dpy.Interaction, current: str):
        hits = await bot._db(bank.search, bot._archive.db, current)
        return [app_commands.Choice(name=label, value=str(item)) for label, item in hits]

    @bot.tree.command(name="bank", description="How many of an item the guild bank holds, and in which tab")
    @app_commands.autocomplete(item=item_choices)
    @app_commands.describe(item="An item in the guild bank (start typing, names are suggested)")
    async def bank_cmd(inter: dpy.Interaction, item: str):
        iid = await bot._db(bank.resolve, bot._archive.db, item)
        if iid is None:
            await reply(inter, "The guild bank holds nothing by that name (as last read).")
            return
        await reply(inter, await bot._db(bank.answer, bot._archive.db, iid))
