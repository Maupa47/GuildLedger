"""The Discord side: read uploads from #gl-ingest, react, post on a timer. Outbound connections only.

All database and webhook work runs on one worker thread (sqlite connection + blocking HTTP), so the
event loop never blocks and the archive is used by one thread only.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import time

import discord as dpy
from discord import app_commands

from . import commands, ingest
from .link import Links
from .config import BotConfig
from .ops import Ops
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
        self._ops: Ops | None = None
        self._links: Links | None = None
        self.tree = app_commands.CommandTree(self)
        self._roles_at = 0.0
        self._post_task: asyncio.Task | None = None
        self._backfilling = asyncio.Lock()
        self._missed = False  # a live upload arrived during a backfill: run it once more

    async def _db(self, fn: Callable[..., Any], *args: Any) -> Any:
        return await asyncio.get_running_loop().run_in_executor(self._pool, fn, *args)

    async def setup_hook(self) -> None:
        def open_archive():
            from guildledger import discord as gl_discord
            self._archive = Archive(self.cfg.db_path)
            self._poster = make_poster(self._archive, self.cfg)
            hook = gl_discord.Webhook(self.cfg.ops_webhook, "ops") if self.cfg.ops_webhook else None
            self._ops = Ops(self._archive, hook, self.cfg.timezone, self.cfg.report_hour,
                            self.cfg.alert_after_hours)
            self._links = Links(self._archive)
        await self._db(open_archive)
        commands.register(self)
        self.add_dynamic_items(commands.LinkButton)
        if not self.once:
            try:
                if self.cfg.server_id:
                    server = dpy.Object(id=self.cfg.server_id)
                    self.tree.copy_global_to(guild=server)
                    await self.tree.sync(guild=server)
                else:
                    await self.tree.sync()
            except dpy.DiscordException as e:
                log.error("could not register slash commands (re-invite the bot with the applications.commands"
                          " scope?): %s", e)

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
                await self._db(self._ops.tick)
                await self._link_round()
            except Exception:  # noqa: BLE001 - keep the loop alive; the next round retries
                log.exception("posting round failed")
            await asyncio.sleep(self.cfg.post_every)

    async def _link_round(self) -> None:
        """New link requests -> confirmations -> a DM with Confirm / Not me; hourly role sync."""
        if self._links is None:
            return
        await self._db(self._links.process)
        for line in self._links.log:
            log.info(line)
        self._links.log.clear()
        for c in await self._db(self._links.to_notify):
            delivered = False
            try:
                user = self.get_user(c.discord_user_id) or await self.fetch_user(c.discord_user_id)
                await user.send(commands.confirm_text(c.name, c.kind), view=commands.confirm_view(c.id),
                                allowed_mentions=NO_MENTIONS)
                delivered = True
            except dpy.DiscordException as e:
                log.info("link confirmation for %s: DM not possible (%s); /link shows it", c.discord_user_id, e)
            await self._db(self._links.mark_notified, c.id, delivered)
        if time.monotonic() - self._roles_at > 3600:
            self._roles_at = time.monotonic()
            for uid in await self._db(self._links.linked_users):
                await self.sync_roles(uid)

    async def sync_roles(self, user_id: int) -> None:
        """Decision 5 (docs/dev/PACK_PLAN.md): roles by guild rank, verified role, nickname. Off unless configured."""
        cfg = self.cfg
        if not cfg.server_id or not self._links:
            return
        verified_id, rank_roles = await self._db(self._links.role_settings, cfg.verified_role_id, cfg.rank_roles)
        if not (rank_roles or verified_id or cfg.set_nickname):
            return
        server = self.get_guild(cfg.server_id)
        if server is None:
            return
        try:
            member = server.get_member(user_id) or await server.fetch_member(user_id)
        except dpy.DiscordException:
            return
        rank, inside = await self._db(self._links.desired_rank, user_id)
        out_since = await self._db(self._links.out_of_guild_since, user_id)
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
            if cfg.set_nickname and inside and member.id != server.owner_id:
                nick = await self._db(self._links.main_name, user_id)
                if nick and member.nick != nick:
                    await member.edit(nick=nick[:32], reason="GuildLedger link: main character")
        except dpy.Forbidden:
            log.error("roles/nickname for %s refused: give the bot Manage Roles and Manage Nicknames and move its"
                      " role above the roles it assigns", user_id)
        except dpy.DiscordException as e:
            log.error("roles/nickname for %s failed: %s", user_id, e)

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
                await self._db(self._ops.send, f"❌ Upload from {collector} rejected: {out.reason}")
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
