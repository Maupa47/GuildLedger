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

from .collection import collectors, ingest
from .collection.ops import Ops
from .collection.post import make_loot_poster, make_poster, post_loot_once, post_once
from .community import commands, counters, crafts_ui, directory_ui, onboarding_ui, roles, rolemenus_ui, setup
from .community.crafts import CraftForum
from .community.directory import Directory
from .community.link import Links
from .community.onboarding import Gate
from .community.rolemenus import RoleMenus
from .community.settings import Settings
from .config import BotConfig
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
        self._loot_poster = None
        self._ops: Ops | None = None
        self._links: Links | None = None
        self._collectors: collectors.Registry | None = None
        self._settings: Settings | None = None
        self._gate: Gate | None = None
        self._menus: RoleMenus | None = None
        self._directory: Directory | None = None
        self._crafts: CraftForum | None = None
        self._owner_nick_logged: set[int] = set()
        self._menu_refusal_logged = False
        self._directory_at = 0.0
        self._crafts_at = 0.0
        self._counters_at = 0.0
        self._hooks: dict[int, str] = dict(cfg.collectors)  # webhook ID -> collector name (config + registry)
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
            self._loot_poster = make_loot_poster(self._archive, self.cfg)
            hook = gl_discord.Webhook(self.cfg.ops_webhook, "ops") if self.cfg.ops_webhook else None
            self._ops = Ops(self._archive, hook, self.cfg.timezone, self.cfg.report_hour,
                            self.cfg.alert_after_hours)
            self._links = Links(self._archive)
            self._collectors = collectors.Registry(self._archive)
            self._settings = Settings(self._archive)
            self._gate = Gate(self._archive)
            self._menus = RoleMenus(self._archive)
            self._directory = Directory(self._archive)
            self._crafts = CraftForum(self._archive)
        await self._db(open_archive)
        await self.refresh_collectors()
        commands.register(self)
        collectors.register(self)
        setup.register_setup(self)
        crafts_ui.register_crafts(self)
        self.add_dynamic_items(commands.LinkButton, collectors.PackageButton, onboarding_ui.VerifyButton,
                               onboarding_ui.PickButton, onboarding_ui.CodeButton, rolemenus_ui.RoleSelect)
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

    async def refresh_collectors(self) -> None:
        """Allowed upload webhooks: the config file's plus those made with /collector invite."""
        registered = await self._db(self._collectors.names)
        self._hooks = {**registered, **self.cfg.collectors}

    async def _welcome_collector(self, webhook_id: int) -> None:
        """The first accepted upload of a collector set up through the bot: tell the admin it works."""
        c = await self._db(self._collectors.first_upload, webhook_id)
        if c is None:
            return
        text = f"✅ <@{c.user_id}>'s collector (**{dpy.utils.escape_markdown(c.name)}**) is connected: first upload received."
        log.info("collector %s: first upload received", c.name)
        try:
            channel = self.get_channel(c.channel_id) if c.channel_id else None
            if channel is not None:
                await channel.send(text, allowed_mentions=NO_MENTIONS)
                return
        except dpy.DiscordException as e:
            log.info("could not announce collector %s in the invitation channel: %s", c.name, e)
        await self._db(self._ops.send, f"✅ Collector {c.name} is connected: first upload received.")

    async def on_ready(self) -> None:
        log.info("connected as %s; ingest channel %s; %d collector webhook(s)",
                 self.user, self.cfg.ingest_channel_id, len(self._hooks))
        await self.backfill()  # every (re)connect: whatever arrived while the bot was away
        if self.once:
            await self._db(post_once, self._archive, self.cfg, self._poster)
            await self._db(post_loot_once, self._archive, self.cfg, self._loot_poster)
            await self.close()
            return
        if self._post_task is None:
            self._post_task = asyncio.create_task(self._post_loop())

    async def _post_loop(self) -> None:
        while not self.is_closed():
            try:
                await self._db(post_once, self._archive, self.cfg, self._poster)
                await self._db(post_loot_once, self._archive, self.cfg, self._loot_poster)
                await self._db(self._ops.tick)
                await self._link_round()
                await self._directory_round()
                await self._crafts_round()
                await counters.counters_round(self)
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

    async def _directory_round(self) -> None:
        """Character forum (D3): every 10 minutes, at most 10 writes."""
        if time.monotonic() - self._directory_at < 600:
            return
        self._directory_at = time.monotonic()
        n = await directory_ui.directory_round(self)
        if n:
            log.info("directory: %d forum write(s)", n)

    async def _crafts_round(self) -> None:
        """Profession forum (D4): every 10 minutes, at most 10 writes."""
        if time.monotonic() - self._crafts_at < 600:
            return
        self._crafts_at = time.monotonic()
        n = await crafts_ui.crafts_round(self)
        if n:
            log.info("professions: %d forum write(s)", n)

    async def ops_line(self, text: str) -> None:
        """One line to #gl-ops when configured (never raises)."""
        if self._ops is None:
            return
        try:
            await self._db(self._ops.send, text)
        except Exception as e:  # noqa: BLE001
            log.info("ops line not sent: %s", e)

    async def sync_roles(self, user_id: int) -> None:
        await roles.sync_roles(self, user_id)

    async def setting(self, key: str, default: Any = None) -> Any:
        if self._settings is None:
            return default
        return await self._db(self._settings.get, key, default)

    async def setting_bool(self, key: str, default: bool = False) -> bool:
        if self._settings is None:
            return default
        return await self._db(self._settings.get_bool, key, default)

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
        collector = self._hooks.get(msg.webhook_id) if msg.webhook_id else None
        if collector is None:
            return  # not a collector's webhook (config file or /collector invite): ignored (CLAUDE.md 7.1)
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
                log.info("upload %s from %s: %s%s", msg.id, collector, out.result.summary(),
                         f"; {out.loot_result.summary()}" if out.loot_result and out.loot_result.changed else "")
                await msg.add_reaction(OK)
                if msg.webhook_id not in self.cfg.collectors:
                    await self._welcome_collector(msg.webhook_id)
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
