"""Posting from the archive: the companion's Poster (guildledger.direct), driven by the bot's settings.
The bot posts through two webhooks in the log channels, like direct mode; it needs no send permission there."""

from __future__ import annotations

import logging

from guildledger import discord
from guildledger.config import resolve_tz
from guildledger.direct import PostResult, Poster

from . import loot
from ..config import BotConfig
from ..store import Archive

log = logging.getLogger(__name__)


def make_poster(archive: Archive, cfg: BotConfig, transport=None) -> Poster:
    kw = {"transport": transport} if transport else {}
    chat = discord.Webhook(cfg.chat_webhook, "chat", **kw) if cfg.chat_webhook else None
    roster = discord.Webhook(cfg.roster_webhook, "roster", **kw) if cfg.roster_webhook else None
    return Poster(archive, chat, roster, resolve_tz(cfg.timezone), cfg.meta, hold_chat=cfg.hold_chat)


def make_loot_poster(archive: Archive, cfg: BotConfig, transport=None) -> loot.LootPoster | None:
    if not cfg.loot_webhook:
        return None
    kw = {"transport": transport} if transport else {}
    return loot.LootPoster(archive.db, discord.Webhook(cfg.loot_webhook, "loot", **kw), resolve_tz(cfg.timezone),
                           cfg.loot_hold, cfg.loot_top)


def post_loot_once(archive: Archive, cfg: BotConfig, poster: loot.LootPoster | None) -> int:
    if poster is None:
        return 0
    try:
        n = poster.run(since=archive.post_since(cfg.post_since))
    except discord.WebhookError as e:
        log.error("loot posting: %s (will retry)", e)
        return 0
    if n:
        log.info("loot posting: %d row(s)", n)
    return n


def post_once(archive: Archive, cfg: BotConfig, poster: Poster | None = None) -> PostResult | None:
    poster = poster or make_poster(archive, cfg)
    try:
        res = poster.run(since=archive.post_since(cfg.post_since))
    except discord.WebhookError as e:
        log.error("posting: %s (will retry)", e)
        return None
    if res.chat_rows or res.events:
        log.info("posting: %s", res.summary())
    return res
