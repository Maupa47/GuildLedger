"""The Discord side: read uploads from #gl-ingest, react, post on a timer. Outbound connections only.

All database and webhook work runs on one worker thread (sqlite connection + blocking HTTP), so the
event loop never blocks and the archive is used by one thread only.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import discord as dpy

from . import ingest
from .config import BotConfig
from .post import make_poster, post_once
from .store import Archive, Outcome

log = logging.getLogger(__name__)

OK, BAD = "✅", "❌"
NO_MENTIONS = dpy.AllowedMentions.none()


class LedgerBot(dpy.Client):
    def __init__(self, cfg: BotConfig, once: bool = False):
        intents = dpy.Intents.none()
        intents.guilds = True
        intents.guild_messages = True
        intents.message_content = True  # privileged: needed to read the upload messages
        super().__init__(intents=intents, allowed_mentions=NO_MENTIONS)
        self.cfg = cfg
        self.once = once  # "backfill" command: catch up, post, exit
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="archive")
        self._archive: Archive | None = None
        self._poster = None
        self._post_task: asyncio.Task | None = None
        self._backfilling = asyncio.Lock()
        self._missed = False  # a live upload arrived during a backfill: run it once more

    async def _db(self, fn: Callable[..., Any], *args: Any) -> Any:
        return await asyncio.get_running_loop().run_in_executor(self._pool, fn, *args)

    async def setup_hook(self) -> None:
        def open_archive():
            self._archive = Archive(self.cfg.db_path)
            self._poster = make_poster(self._archive, self.cfg)
        await self._db(open_archive)

    async def on_ready(self) -> None:
        log.info("connected as %s; ingest channel %s; %d collector webhook(s)",
                 self.user, self.cfg.ingest_channel_id, len(self.cfg.collectors))
        await self.backfill()  # every (re)connect: whatever arrived while the bot was away
        if self.once:
            await self._db(post_once, self._archive, self.cfg, self._poster)
            await self.close()
            return
        if self._post_task is None:
            self._post_task = asyncio.create_task(self._post_loop())

    async def _post_loop(self) -> None:
        while not self.is_closed():
            try:
                await self._db(post_once, self._archive, self.cfg, self._poster)
            except Exception:  # noqa: BLE001 - keep the loop alive; the next round retries
                log.exception("posting round failed")
            await asyncio.sleep(self.cfg.post_every)

    async def backfill(self) -> None:
        async with self._backfilling:
            channel = self.get_channel(self.cfg.ingest_channel_id)
            if channel is None:
                try:
                    channel = await self.fetch_channel(self.cfg.ingest_channel_id)
                except dpy.DiscordException as e:
                    log.error("cannot open the ingest channel %s: %s", self.cfg.ingest_channel_id, e)
                    return
            n = 0
            while True:
                self._missed = False
                last = await self._db(self._archive.last_ingest_id)
                after = dpy.Object(id=last) if last else None
                async for msg in channel.history(limit=None, after=after, oldest_first=True):
                    await self.handle(msg)
                    n += 1
                if not self._missed:
                    break
            if n:
                log.info("backfill: looked at %d message(s) in the ingest channel", n)

    async def on_message(self, msg: dpy.Message) -> None:
        if msg.channel.id != self.cfg.ingest_channel_id:
            return
        if self._backfilling.locked():
            # Processing it now could move "last processed" past older messages the backfill has
            # not reached yet; the backfill picks it up in order instead.
            self._missed = True
            return
        await self.handle(msg)

    async def handle(self, msg: dpy.Message) -> None:
        collector = self.cfg.collectors.get(msg.webhook_id) if msg.webhook_id else None
        if collector is None:
            return  # not one of the configured collector webhooks: ignored (CLAUDE.md 7.1)
        data = None
        if len(msg.attachments) == 1 and msg.attachments[0].size <= ingest.MAX_ATTACHMENT:
            try:
                data = await msg.attachments[0].read()
            except dpy.DiscordException as e:
                log.warning("upload %s from %s: download failed (%s); will retry on next backfill",
                            msg.id, collector, e)
                return
        out: Outcome = await self._db(self._archive.process_upload, msg.id, collector, msg.content, data)
        if out.status == "seen":
            return
        try:
            if out.status == "ok":
                log.info("upload %s from %s: %s", msg.id, collector, out.result.summary())
                await msg.add_reaction(OK)
            else:
                log.warning("upload %s from %s rejected: %s", msg.id, collector, out.reason)
                await msg.add_reaction(BAD)
                await msg.reply(f"rejected: {out.reason}", mention_author=False, allowed_mentions=NO_MENTIONS)
        except dpy.DiscordException as e:
            log.warning("could not react to upload %s: %s", msg.id, e)

    async def close(self) -> None:
        if self._post_task:
            self._post_task.cancel()
        await super().close()
        if self._archive is not None:
            await self._db(self._archive.close)
        self._pool.shutdown(wait=True)
