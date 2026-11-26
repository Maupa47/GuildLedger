"""The guild bank in Discord (PLAN_COMMUNITY D5): tab messages, gold, ledger lines and /bank, from synthetic hub
data. No Discord."""

import sys
from pathlib import Path

from guildledger import hubdata
from guildledger.svparse import parse, parse_file
from guildledger_bot.community import bank
from guildledger_bot.store import Archive

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "companion" / "tests"))
from hub_fixture import FIX, T0  # noqa: E402
from test_hubdata import hubdata_lua  # noqa: E402


def archive(tmp_path, **kw):
    a = Archive(tmp_path / "bot.db")
    a.import_sv(parse_file(str(FIX / "basic.lua")), "Testa Collector")
    hubdata.import_hub(a.db, parse(hubdata_lua(**kw)), a.guild_names(), "Testa Collector")
    return a


def test_gold_text():
    assert bank.gold(1234567) == "123g 45s 67c" and bank.gold(50000) == "5g" and bank.gold(0) == "0c"
    assert bank.gold(123456789012) == "12'345'678g 90s 12c"


def test_one_message_per_tab_edited_only_when_it_changes(tmp_path):
    a = archive(tmp_path)
    b = bank.Board(a)
    want = b.wanted()
    assert list(want) == ["money", "tab:1"]
    assert "123g 45s 67c" in want["money"][0] and "Offi Cer" in want["money"][0]
    tab = "\n".join(want["tab:1"])
    assert tab.startswith("**Tab 1: Mats** (2 items)") and "Linen Cloth x20" in tab and "Wool Cloth x5" in tab
    writes = b.plan(555)
    assert [w.action for w in writes] == ["create", "create"]
    for w in writes:
        b.done(555, w, [1])
    assert b.plan(555) == []                                  # nothing changed: nothing written
    hubdata.import_hub(a.db, parse(hubdata_lua(bank_t=T0 + 900)), a.guild_names(), "x")
    assert {w.action for w in b.plan(555)} == {"edit"}        # a newer reading: edited in place
    assert [w.action for w in b.plan(777)] == ["create", "create"]   # another channel starts fresh


def test_ledger_posts_new_lines_once_and_never_the_old_ones(tmp_path):
    a = archive(tmp_path)
    b = bank.Board(a)
    assert b.start_ledger() == 2                              # the two lines already archived are not posted
    assert b.ledger_batches() == ([], [])
    hubdata.import_hub(a.db, parse(hubdata_lua(ledger_extra=True)), a.guild_names(), "x")
    msgs, keys = b.ledger_batches()
    assert len(keys) == 1 and "**Bram Exampleson** deposited 5g" in msgs[0]
    b.ledger_posted(keys)
    assert b.ledger_batches() == ([], [])


def test_bank_lookup(tmp_path):
    a = archive(tmp_path)
    hits = bank.search(a.db, "lin")
    assert hits == [("Linen Cloth (x20)", 2589)]
    assert bank.resolve(a.db, "Wool") == 2592
    assert "**Linen Cloth** x20 in the guild bank" in bank.answer(a.db, 2589) and "Mats: 20" in bank.answer(a.db, 2589)
    assert "holds no" in bank.answer(a.db, 4306)
    empty = Archive(tmp_path / "empty.db")
    assert "No picture of the guild bank yet" in bank.answer(empty.db, 2589)
