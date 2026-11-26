"""Hub data outside the game (shared/schema.md 8): two collectors upload professions, the guild bank and alt links
from Amazing Hub's data -> the bot archives each row once. Synthetic data only; a fake transport stands in for
Discord."""

import sys
from pathlib import Path

from guildledger import discord, hubdata
from guildledger.store import Spool
from guildledger.svparse import parse, parse_file
from guildledger.upload import Uploader
from guildledger_bot.store import Archive

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "companion" / "tests"))
from hub_fixture import FIX, T0  # noqa: E402
from test_hubdata import hubdata_lua  # noqa: E402

from test_merge import FakeIngest  # noqa: E402


def upload(tmp_path, name, lua):
    s = Spool(tmp_path / f"{name}.db")
    s.import_sv(parse_file(str(FIX / "basic.lua")), name)
    hubdata.import_hub(s.db, parse(lua), s.guild_names(), name)
    ingest = FakeIngest()
    Uploader(s, discord.Webhook("https://x/ingest", "ingest", ingest), name).run()
    return ingest.messages


def count(a, table):
    return a.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_two_collectors_give_every_hub_row_once_and_the_newest_wins(tmp_path):
    a = Archive(tmp_path / "bot.db")
    mid = 1
    for name, lua in (("TestaCollector", hubdata_lua()),
                      ("SecondOfficer", hubdata_lua(bank_t=T0 + 400, skill=170))):
        msgs = upload(tmp_path, name, lua)
        for _, content, data in msgs:
            out = a.process_upload(mid, name, content, data)
            assert out.status == "ok", out.reason
            mid += 1
    assert count(a, "hub_profs") == 3 and count(a, "bank_tabs") == 1 and count(a, "bank_money") == 1
    assert count(a, "bank_log") == 2 and count(a, "alt_links") == 1
    assert a.db.execute("SELECT skill FROM hub_profs WHERE member='alia testwood' AND prof=197").fetchone()[0] == 170
    assert a.db.execute("SELECT read_at FROM bank_tabs").fetchone()[0] == T0 + 400
