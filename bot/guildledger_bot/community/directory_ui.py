"""Discord side of the character directory (directory.py): applies the planned writes to the forum."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord as dpy

from .common import NO_MENTIONS
from .directory import DEFAULT_ARMORY, Write

if TYPE_CHECKING:
    from ..client import LedgerBot

log = logging.getLogger(__name__)


async def armory_template(bot: "LedgerBot") -> str:
    t = await bot.setting("armory.url", None)
    return DEFAULT_ARMORY if t is None else t  # "" = no links


async def directory_round(bot: "LedgerBot") -> int:
    """One round (every 10 minutes): work out the wanted posts, write what changed. Returns the writes done."""
    template = await armory_template(bot)

    def plan():
        mains = {}
        for uid in bot._links.linked_users():
            m = bot._links.main_of(uid)
            if m:
                mains[uid] = m["guid"]
        return bot._directory.plan(bot._directory.wanted(template, bot.cfg.grace_days, mains))

    return await forum_round(bot, "directory.forum", bot._directory, plan, "directory")


async def forum_round(bot: "LedgerBot", setting: str, planner, plan, label: str) -> int:
    """A forum the bot keeps up to date (the directory, the profession forum): the channel from `setting`,
    the writes from `plan()` (run in the worker pool), applied and recorded through `planner`."""
    forum_id = await bot._db(bot._settings.get_int, setting, 0)
    if not forum_id:
        return 0
    forum = bot.get_channel(forum_id)
    if forum is None:
        try:
            forum = await bot.fetch_channel(forum_id)
        except dpy.DiscordException as e:
            log.error("%s forum %s: %s", label, forum_id, e)
            return 0
    if not isinstance(forum, dpy.ForumChannel):
        log.error("%s: channel %s is not a forum", label, forum_id)
        return 0
    writes = await bot._db(plan)
    done = 0
    tags = {t.name.lower(): t for t in forum.available_tags}
    for w in writes:
        try:
            await _apply(bot, forum, tags, w, planner)
            done += 1
        except dpy.Forbidden as e:
            log.error("%s: Discord refused a write (needs Create Posts, Send Messages in Threads, Manage"
                      " Threads in the forum): %s", label, e)
            break
        except dpy.DiscordException as e:
            log.warning("%s: %s %s/%s failed: %s", label, w.action, w.kind, w.key, e)
    return done


async def _thread(bot: "LedgerBot", thread_id: int) -> dpy.Thread | None:
    t = bot.get_channel(thread_id)
    if t is None:
        try:
            t = await bot.fetch_channel(thread_id)
        except dpy.NotFound:
            return None
    return t if isinstance(t, dpy.Thread) else None


async def _apply(bot: "LedgerBot", forum: dpy.ForumChannel, tags: dict, w: Write, planner=None) -> None:
    planner = planner or bot._directory
    if w.action == "delete":
        t = await _thread(bot, w.thread_id) if w.thread_id else None
        if t is not None:
            await t.delete()
        await bot._db(planner.done, w)
        return
    p = w.post
    applied = [tags[p.tag.lower()]] if p.tag and p.tag.lower() in tags else []
    t = await _thread(bot, w.thread_id) if w.action == "edit" and w.thread_id else None
    if t is None:  # new, or deleted by hand in Discord: make it (again)
        made = await forum.create_thread(name=p.title, content=p.messages[0], applied_tags=applied,
                                         allowed_mentions=NO_MENTIONS)
        ids = [made.message.id]
        for m in p.messages[1:]:
            ids.append((await made.thread.send(m, allowed_mentions=NO_MENTIONS)).id)
        if p.kind == "help":
            try:
                await made.thread.edit(pinned=True)
            except dpy.DiscordException:
                pass
        await bot._db(planner.done, w, made.thread.id, ids)
        return
    if t.archived or t.name != p.title or {x.id for x in t.applied_tags} != {x.id for x in applied}:
        await t.edit(archived=False, name=p.title, applied_tags=applied)
    ids = list(w.message_ids)
    for i, text in enumerate(p.messages):
        if i < len(ids):
            try:
                await t.get_partial_message(ids[i]).edit(content=text, allowed_mentions=NO_MENTIONS)
                continue
            except dpy.NotFound:
                pass
            ids[i] = (await t.send(text, allowed_mentions=NO_MENTIONS)).id
        else:
            ids.append((await t.send(text, allowed_mentions=NO_MENTIONS)).id)
    for extra in ids[len(p.messages):]:
        try:
            await t.get_partial_message(extra).delete()
        except dpy.DiscordException:
            pass
    await bot._db(planner.done, w, t.id, ids[:len(p.messages)])
