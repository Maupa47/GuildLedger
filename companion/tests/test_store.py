import copy

import pytest

from guildledger.store import SchemaError
from guildledger.svparse import parse_file

G = "100200300"


@pytest.fixture
def basic(fixtures):
    return parse_file(str(fixtures / "basic.lua"))


def count(spool, table):
    return spool.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def chat(spool, rid):
    return spool.db.execute("SELECT * FROM chat WHERE id=?", (rid,)).fetchone()


def test_import_twice_adds_nothing(spool, basic):
    first = spool.import_sv(basic, "c1")
    assert first.chat_new == 6  # 7 rows, the event row folds into the meta row
    assert first.chat_merged == 1
    assert first.events_new == 5
    assert first.members_new == 3
    before = (count(spool, "chat"), count(spool, "events"), count(spool, "members"))

    second = spool.import_sv(basic, "c2")
    assert second.changed == 0
    assert second.min_ts is None
    assert (count(spool, "chat"), count(spool, "events"), count(spool, "members")) == before


def test_rows_stored_as_given(spool, basic):
    spool.import_sv(basic, "c1")
    r = chat(spool, "1794420010200000:1001")
    assert r["author"] == "Bram Exampleson"
    assert r["guid"] == "Player-1111-0000BBBB"
    assert r["ts_utc"] == 1794420010
    assert r["edited"] == 1 and r["src"] == "live" and r["first_collector"] == "c1"
    assert "|Hitem:2140" in r["text"]  # stored raw; cleaning happens on output
    assert chat(spool, "1794420030400000:1003")["stream"] == "o"
    assert chat(spool, "1794420040500000:1004")["from_discord"] == 1
    deleted = chat(spool, "1794420050600000:1005")
    assert deleted["deleted"] == 1 and deleted["text"] is None


def test_event_row_fills_meta_row(spool, basic):
    spool.import_sv(basic, "c1")
    r = chat(spool, "1794420020300000:1002")
    assert r["text"] == "this line lost its club partner"
    assert r["src"] == "live"
    assert chat(spool, "ev|1794420021|Cora Sample|1a2b3c4d") is None


def test_meta_row_arriving_after_event_row_takes_it_over(spool, basic):
    rows = basic["GuildLedgerDB"]["guilds"][G]["chat"]
    meta, ev = rows[2], rows[3]
    only_event = copy.deepcopy(basic)
    only_event["GuildLedgerDB"]["guilds"][G]["chat"] = [ev]
    only_meta = copy.deepcopy(basic)
    only_meta["GuildLedgerDB"]["guilds"][G]["chat"] = [meta]

    spool.import_sv(only_event, "c1")
    spool.db.execute("UPDATE chat SET posted=1")
    res = spool.import_sv(only_meta, "c2")
    assert res.chat_merged == 1 and res.chat_new == 0
    r = chat(spool, meta["id"])
    assert r["text"] == ev["m"] and r["src"] == "live"
    assert r["posted"] == 1  # already shown once; must not be posted again
    assert chat(spool, ev["id"]) is None


def test_later_copy_fills_text_and_flags_but_never_overwrites(spool, basic):
    spool.import_sv(basic, "c1")
    other = copy.deepcopy(basic)
    rows = other["GuildLedgerDB"]["guilds"][G]["chat"]
    rows[6]["m"] = "deleted line text from another collector"
    rows[0]["m"] = "a different text"
    rows[0]["del"] = True
    res = spool.import_sv(other, "c2")
    assert res.chat_updated == 2
    assert chat(spool, rows[6]["id"])["text"] == "deleted line text from another collector"
    first = chat(spool, rows[0]["id"])
    assert first["text"] == "hello guild" and first["deleted"] == 1
    assert first["first_collector"] == "c1"


def test_later_copy_fills_unknown_author_and_discord_flag(spool, basic):
    first = copy.deepcopy(basic)
    row = first["GuildLedgerDB"]["guilds"][G]["chat"][6]
    row.pop("g", None)
    row.pop("fd", None)
    row["a"] = "?"
    spool.import_sv(first, "c1")
    assert chat(spool, row["id"])["author"] == "?"
    second = copy.deepcopy(first)
    row2 = second["GuildLedgerDB"]["guilds"][G]["chat"][6]
    row2["a"], row2["fd"] = "discordfriend", True
    assert spool.import_sv(second, "c2").chat_updated == 1
    got = chat(spool, row["id"])
    assert got["author"] == "discordfriend" and got["from_discord"] == 1
    # a named author is never replaced
    row2["a"] = "someone else"
    spool.import_sv(second, "c3")
    assert chat(spool, row["id"])["author"] == "discordfriend"


def test_event_row_dropped_when_club_row_has_text(spool, basic):
    data = copy.deepcopy(basic)
    rows = data["GuildLedgerDB"]["guilds"][G]["chat"]
    dup = {**rows[0], "id": "ev|1794420002|Alia Testwood|deadbeef", "t": 1794420002, "src": "event"}
    rows.append(dup)
    res = spool.import_sv(data, "c1")
    assert chat(spool, dup["id"]) is None
    assert res.chat_merged == 1 and res.chat_dup == 1


def test_event_row_outside_window_is_kept(spool, basic):
    data = copy.deepcopy(basic)
    rows = data["GuildLedgerDB"]["guilds"][G]["chat"]
    rows.append({**rows[0], "id": "ev|1794420009|Alia Testwood|0000beef", "t": 1794420009, "src": "event"})
    spool.import_sv(data, "c1")
    assert chat(spool, "ev|1794420009|Alia Testwood|0000beef") is not None


def test_events_supersede(spool, basic):
    spool.import_sv(basic, "c1")
    rows = {r["id"]: r for r in spool.db.execute("SELECT * FROM events")}
    assert rows["leave|Dax Gone||diff:498450"]["superseded_by"] == "leave|Dax Gone||log:498447"
    assert rows["leave|Dax Gone||log:498447"]["superseded_by"] is None
    assert rows["kick|Eli Rowdy|Alia Testwood|358884010"]["actor"] == "Alia Testwood"
    assert rows["promote|Bram Exampleson|Alia Testwood|358884011"]["detail"] == "Member"
    visible = [r["id"] for r in spool.event_rows(G)]
    assert "leave|Dax Gone||diff:498450" not in visible


def test_sys_event_in_adjacent_bucket_is_duplicate(spool, basic):
    spool.import_sv(basic, "c1")
    other = copy.deepcopy(basic)
    other["GuildLedgerDB"]["guilds"][G]["ev"] = [{
        "id": "kick|Eli Rowdy|Alia Testwood|358884011", "t": 1794420056, "p": True,
        "k": "kick", "n": "Eli Rowdy", "by": "Alia Testwood", "src": "sys",
    }]
    res = spool.import_sv(other, "c2")
    assert res.events_new == 0 and res.events_dup == 1


def test_members_leave_and_rejoin(spool, basic):
    spool.import_sv(basic, "c1")
    other = copy.deepcopy(basic)
    roster = other["GuildLedgerDB"]["guilds"][G]["roster"]
    del roster["Player-1111-0000CCCC"]
    spool.import_sv(other, "c1")
    gone = spool.db.execute("SELECT in_guild FROM members WHERE guid='Player-1111-0000CCCC'").fetchone()
    assert gone["in_guild"] == 0
    spool.import_sv(basic, "c1")
    back = spool.db.execute("SELECT in_guild FROM members WHERE guid='Player-1111-0000CCCC'").fetchone()
    assert back["in_guild"] == 1


def test_malformed_rows_are_skipped(spool, basic):
    data = copy.deepcopy(basic)
    rows = data["GuildLedgerDB"]["guilds"][G]["chat"]
    rows += [{"id": "x"}, "not a table", {**rows[0], "id": "1:2", "s": "q"},
             {**rows[0], "id": "ev|1|x|y", "src": "event", "m": None}]
    res = spool.import_sv(data, "c1")
    assert res.skipped == 4


@pytest.mark.parametrize("db", [{}, {"GuildLedgerDB": {"schema": 2}}, {"GuildLedgerDB": "x"}])
def test_schema_check(spool, db):
    with pytest.raises(SchemaError):
        spool.import_sv(db, "c1")


def test_empty_guild_tables(spool):
    res = spool.import_sv({"GuildLedgerDB": {"schema": 1, "guilds": {"5": {"name": "Empty", "chat": {}}}}}, "c1")
    assert res.changed == 0 and res.guilds == ["5"]


def test_stats(spool, basic):
    spool.import_sv(basic, "c1")
    (s,) = spool.stats()
    assert s["name"] == "Synthetic Guild"
    assert s["chat"] == 6 and s["chat_with_text"] == 5 and s["chat_meta_only"] == 1
    assert s["events"] == 5 and s["events_superseded"] == 1
    assert s["event_kinds"] == {"join": 1, "kick": 1, "leave": 1, "promote": 1}
    assert s["members_in_guild"] == 3


def test_old_spool_gets_window_column(tmp_path):
    import sqlite3

    from guildledger.store import Spool
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE events(guild TEXT NOT NULL, id TEXT NOT NULL, ts_utc INTEGER NOT NULL,"
               " precise INTEGER NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL, guid TEXT, actor TEXT,"
               " detail TEXT, src TEXT NOT NULL, first_collector TEXT, superseded_by TEXT,"
               " posted INTEGER NOT NULL DEFAULT 0, uploaded INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (guild, id))")
    db.commit()
    db.close()
    with Spool(path) as spool:
        cols = {r["name"] for r in spool.db.execute("PRAGMA table_info(events)")}
        assert "window_from" in cols
    with Spool(path):  # second open: nothing to do
        pass
