"""The bot's Discord handling with fake message objects (no connection to Discord)."""

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("discord")

from guildledger.upload import build_file, describe  # noqa: E402
from guildledger_bot.client import BAD, OK, LedgerBot  # noqa: E402
from guildledger_bot.config import BotConfig  # noqa: E402

G = "100200300"
CHANNEL = 555
ALPHA_HOOK, STRANGER_HOOK = 11, 99


def cfg(tmp_path):
    return BotConfig(token="x", ingest_channel_id=CHANNEL, collectors={ALPHA_HOOK: "Alpha"},
                     chat_webhook="https://discord.invalid/c", roster_webhook="https://discord.invalid/r",
                     db_path=tmp_path / "archive.db")


class Msg:
    def __init__(self, mid, content, data, webhook_id=ALPHA_HOOK, channel=CHANNEL):
        self.id, self.content, self.webhook_id = mid, content, webhook_id
        self.channel = SimpleNamespace(id=channel)
        self.reactions, self.replies = [], []

        async def read():
            return data
        self.attachments = [SimpleNamespace(size=len(data), read=read)] if data is not None else []

    async def add_reaction(self, emoji):
        self.reactions.append(emoji)

    async def reply(self, text, **kw):
        assert kw.get("allowed_mentions") is not None
        self.replies.append(text)


def upload_msg(mid, text, webhook_id=ALPHA_HOOK, corrupt=False):
    row = {"id": f"{1794355200 + mid}000000:{mid}", "t": 1794355200 + mid, "s": "g", "a": "Alia Testwood",
           "m": text, "src": "live"}
    data = build_file(G, "Synthetic Guild", "Alpha", [row], [])
    content = describe("Alpha", 1, data)
    return Msg(mid, content, data[:-3] if corrupt else data, webhook_id)


class FakeChannel:
    def __init__(self, messages):
        self.messages = messages

    def history(self, limit=None, after=None, oldest_first=True):
        after_id = after.id if after else 0
        msgs = [m for m in self.messages if m.id > after_id]

        async def gen():
            for m in sorted(msgs, key=lambda m: m.id):
                yield m
        return gen()


async def make_bot(tmp_path, channel=None):
    bot = LedgerBot(cfg(tmp_path))
    await bot.setup_hook()
    if channel is not None:
        bot.get_channel = lambda cid: channel if cid == CHANNEL else None
    return bot


async def shutdown(bot):
    await bot._db(bot._archive.close)
    bot._pool.shutdown(wait=True)


def test_upload_is_merged_and_acknowledged(tmp_path):
    async def go():
        bot = await make_bot(tmp_path)
        m = upload_msg(1, "hello")
        await bot.on_message(m)
        n = await bot._db(lambda: bot._archive.db.execute("SELECT COUNT(*) FROM chat").fetchone()[0])
        await bot.on_message(m)  # the same message again (e.g. gateway replay): nothing new
        await shutdown(bot)
        return m, n
    m, n = asyncio.run(go())
    assert m.reactions == [OK] and n == 1


def test_unknown_webhook_and_other_channels_are_ignored(tmp_path):
    async def go():
        bot = await make_bot(tmp_path)
        stranger = upload_msg(1, "invented", webhook_id=STRANGER_HOOK)
        human = upload_msg(2, "typed by a person", webhook_id=None)
        elsewhere = upload_msg(3, "other channel")
        elsewhere.channel = SimpleNamespace(id=777)
        for m in (stranger, human, elsewhere):
            await bot.on_message(m)
        n = await bot._db(lambda: bot._archive.db.execute("SELECT COUNT(*) FROM chat").fetchone()[0])
        await shutdown(bot)
        return (stranger, human, elsewhere), n
    msgs, n = asyncio.run(go())
    assert n == 0 and all(m.reactions == [] for m in msgs)


def test_bad_upload_gets_cross_and_reason(tmp_path):
    async def go():
        bot = await make_bot(tmp_path)
        m = upload_msg(1, "x", corrupt=True)
        await bot.on_message(m)
        await shutdown(bot)
        return m
    m = asyncio.run(go())
    assert m.reactions == [BAD] and m.replies == ["rejected: sha256 does not match the attachment"]


def test_backfill_after_downtime_and_restart_adds_no_duplicates(tmp_path):
    msgs = [upload_msg(i, f"line {i}") for i in range(1, 6)]

    async def first():
        bot = await make_bot(tmp_path, FakeChannel(msgs[:2]))
        await bot.backfill()
        await shutdown(bot)

    async def after_downtime():
        bot = await make_bot(tmp_path, FakeChannel(msgs))  # three uploads arrived while it was down
        await bot.backfill()
        await bot.backfill()  # a reconnect runs it again
        rows = await bot._db(lambda: [r[0] for r in bot._archive.db.execute("SELECT text FROM chat ORDER BY ts_utc")])
        await shutdown(bot)
        return rows
    asyncio.run(first())
    rows = asyncio.run(after_downtime())
    assert rows == [f"line {i}" for i in range(1, 6)]
    assert [len(m.reactions) for m in msgs] == [1, 1, 1, 1, 1]


def test_live_message_during_backfill_waits_for_it(tmp_path):
    msgs = [upload_msg(i, f"line {i}") for i in range(1, 4)]

    async def go():
        channel = FakeChannel(msgs[:2])
        bot = await make_bot(tmp_path, channel)
        async with bot._backfilling:
            channel.messages.append(msgs[2])
            await bot.on_message(msgs[2])  # arrives mid-backfill: deferred
        assert msgs[2].reactions == [] and bot._missed
        await bot.backfill()
        last = await bot._db(bot._archive.last_ingest_id)
        await shutdown(bot)
        return last
    assert asyncio.run(go()) == 3
    assert all(m.reactions == [OK] for m in msgs)


def test_slash_commands_are_registered(tmp_path):
    async def go():
        bot = await make_bot(tmp_path)
        names = sorted(c.name for c in bot.tree.get_commands())
        await shutdown(bot)
        return names
    assert asyncio.run(go()) == ["Characters", "activity", "bank", "chars", "collector", "craft", "dkp", "inactive", "joined", "link",
                                 "linkapprove", "linkstatus", "loot", "main", "roles", "seen", "setup", "unlink",
                                 "whois", "wish", "wishlist"]
