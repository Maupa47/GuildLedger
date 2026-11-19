"""Collectors set up from Discord (/collector invite): registry, personal package, first-upload notice."""

import asyncio
import gzip
import io
import tomllib
import zipfile
from types import SimpleNamespace

import pytest

pytest.importorskip("discord")

import discord as dpy  # noqa: E402

from guildledger.upload import describe  # noqa: E402
from guildledger_bot import collectors  # noqa: E402
from guildledger_bot.client import OK  # noqa: E402

from test_client import CHANNEL, Msg, make_bot, shutdown, upload_msg  # noqa: E402

OFFICER, ADMIN, INVITE_CHANNEL = 4242, 1, 888
SECRET = "https://discord.com/api/webhooks/7001/s3cr3t-token"


class FakeHook:
    def __init__(self, hid, token="s3cr3t-token"):
        self.id, self.token, self.deleted = hid, token, False

    @property
    def url(self):
        return f"https://discord.com/api/webhooks/{self.id}/{self.token}"

    async def delete(self, reason=None):
        self.deleted = True


class IngestChannel:
    def __init__(self, forbidden=False):
        self.created, self.forbidden = [], forbidden

    async def create_webhook(self, name, reason=None):
        if self.forbidden:
            raise dpy.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "Missing Permissions")
        hook = FakeHook(7001 + len(self.created))
        hook.name = name
        self.created.append(hook)
        return hook


class TextChannel:
    def __init__(self):
        self.sent = []

    async def send(self, text, **kw):
        assert kw["allowed_mentions"] is not None
        self.sent.append(text)


async def bot_with(tmp_path, ingest):
    bot = await make_bot(tmp_path)
    invite_channel = TextChannel()
    bot.get_channel = lambda cid: {CHANNEL: ingest, INVITE_CHANNEL: invite_channel}.get(cid)

    async def fetch_webhook(hid):
        for h in ingest.created:
            if h.id == hid and not h.deleted:
                return h
        raise dpy.NotFound(SimpleNamespace(status=404, reason="Not Found"), "Unknown Webhook")
    bot.fetch_webhook = fetch_webhook
    return bot, invite_channel


def unzip(file):
    with zipfile.ZipFile(io.BytesIO(file.fp.read())) as zf:
        return {n: zf.read(n) for n in zf.namelist()}


def test_invited_officer_gets_a_ready_package_and_is_registered(tmp_path, caplog):
    ingest = IngestChannel()
    caplog.set_level("DEBUG")

    async def go():
        bot, _ = await bot_with(tmp_path, ingest)
        none_text, none_file = await collectors.hand_out(bot, OFFICER)  # not invited
        await bot._db(bot._collectors.invite, OFFICER, "Offi Cer", ADMIN, INVITE_CHANNEL)
        text, file = await collectors.hand_out(bot, OFFICER)
        again_text, again = await collectors.hand_out(bot, OFFICER)  # pressed once more: same link, no new webhook
        hooks = dict(bot._hooks)
        await shutdown(bot)
        return none_text, none_file, text, file, again, hooks
    none_text, none_file, text, file, again, hooks = asyncio.run(go())
    assert none_file is None and "withdrawn" in none_text
    assert file.filename == "GuildLedger-collector-Offi-Cer.zip" and "start-companion.cmd" in text
    files = unzip(file)
    cfg = tomllib.loads(files["config.toml"].decode("utf-8"))
    assert cfg["upload"]["ingest_webhook"] == SECRET and cfg["collector"] == "Offi Cer"
    assert cfg["general"]["mode"] == "upload" and "sv_path" not in cfg
    assert "guildledger/__main__.py" in files and "start-companion.cmd" in files
    assert len(ingest.created) == 1 and ingest.created[0].name == "GL Offi Cer"
    assert unzip(again)["config.toml"] == files["config.toml"]
    assert hooks[7001] == "Offi Cer" and hooks[11] == "Alpha", "registered beside the config file's collectors"
    assert "s3cr3t" not in caplog.text and "s3cr3t" not in text, "the upload link is never logged or shown"


def test_missing_permission_is_explained(tmp_path):
    async def go():
        bot, _ = await bot_with(tmp_path, IngestChannel(forbidden=True))
        await bot._db(bot._collectors.invite, OFFICER, "Offi Cer", ADMIN, INVITE_CHANNEL)
        out = await collectors.hand_out(bot, OFFICER)
        await shutdown(bot)
        return out
    text, file = asyncio.run(go())
    assert file is None and "Manage Webhooks" in text


def test_first_upload_is_announced_once_and_removal_stops_uploads(tmp_path):
    ingest = IngestChannel()

    async def go():
        bot, invite_channel = await bot_with(tmp_path, ingest)
        await bot._db(bot._collectors.invite, OFFICER, "Offi Cer", ADMIN, INVITE_CHANNEL)
        await collectors.hand_out(bot, OFFICER)
        empty = gzip.compress(b"", mtime=0)  # the companion's test upload at its first start
        hello = Msg(1, describe("Offi Cer", 0, empty), empty, webhook_id=7001)
        await bot.on_message(hello)
        real = upload_msg(2, "hello", webhook_id=7001)
        await bot.on_message(real)
        who = await bot._db(lambda: bot._archive.db.execute("SELECT first_collector FROM chat").fetchone()[0])
        # revoke
        webhook_id = await bot._db(bot._collectors.remove, OFFICER)
        await bot.refresh_collectors()
        late = upload_msg(3, "after removal", webhook_id=7001)
        await bot.on_message(late)
        n = await bot._db(lambda: bot._archive.db.execute("SELECT COUNT(*) FROM chat").fetchone()[0])
        reg, cfg, open_ = await bot._db(bot._collectors.overview, bot.cfg.collectors)
        await shutdown(bot)
        return hello, real, late, invite_channel.sent, who, webhook_id, n, (reg, cfg, open_)
    hello, real, late, sent, who, webhook_id, n, overview = asyncio.run(go())
    assert hello.reactions == [OK] and real.reactions == [OK]
    assert len(sent) == 1 and "is connected" in sent[0] and f"<@{OFFICER}>" in sent[0]
    assert who == "Offi Cer", "the archive names the collector from the registry, not from the file"
    assert webhook_id == 7001 and late.reactions == [] and n == 1
    assert overview == ([], [("Alpha", None)], [])


def test_registry_survives_a_restart_and_reinvite_renames(tmp_path):
    ingest = IngestChannel()

    async def first():
        bot, _ = await bot_with(tmp_path, ingest)
        await bot._db(bot._collectors.invite, OFFICER, "Offi Cer", ADMIN, INVITE_CHANNEL)
        await collectors.hand_out(bot, OFFICER)
        await shutdown(bot)

    async def second():
        bot, _ = await bot_with(tmp_path, ingest)
        hooks = dict(bot._hooks)
        await bot._db(bot._collectors.invite, OFFICER, "New Name", ADMIN, INVITE_CHANNEL)
        await bot.refresh_collectors()
        _, file = await collectors.hand_out(bot, OFFICER)
        renamed = dict(bot._hooks)
        reg, _, open_ = await bot._db(bot._collectors.overview, bot.cfg.collectors)
        await shutdown(bot)
        return hooks, renamed, file, reg, open_
    asyncio.run(first())
    hooks, renamed, file, reg, open_ = asyncio.run(second())
    assert hooks[7001] == "Offi Cer" and renamed[7001] == "New Name"
    assert len(ingest.created) == 1, "the same webhook is reused"
    assert tomllib.loads(unzip(file)["config.toml"].decode())["collector"] == "New Name"
    assert [c.name for c in reg] == ["New Name"] and open_ == []


def test_names_are_made_safe():
    assert collectors.clean_name("  Offi\n`Cer`\t ") == "Offi Cer"
    assert collectors.zip_name("Öffi Cér!") == "GuildLedger-collector-ffi-C-r.zip"
    assert collectors.webhook_name("Discord Fan") == "GL collector"


def test_commands_register(tmp_path):
    async def go():
        bot = await make_bot(tmp_path)
        names = {c.name for c in bot.tree.get_commands()}
        sub = {c.name for c in bot.tree.get_command("collector").commands}
        await shutdown(bot)
        return names, sub
    names, sub = asyncio.run(go())
    assert "collector" in names and sub == {"invite", "remove", "list"}
