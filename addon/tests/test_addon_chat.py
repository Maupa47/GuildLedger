"""Runs the real addon files under LuaJIT (via lupa) against tests/wowstub.lua.

Dev-only dependency:  pip install lupa pytest
Run from the repo root:  python -m pytest addon/tests
"""

import pytest
from game import ALIA, BRAM, CORA, ADDON_DIR, FILES, STUB, Game, by_src, lupa, parse, Spool  # noqa: F401


def test_login_syncs_history_as_meta_rows():
    g = Game(history=250)
    g.run(60)
    rows = g.chat()
    assert g.errors == 0, g.last_error()
    assert len(rows) == 250 and all(r["src"] == "meta" and "m" not in r for r in rows)
    assert {r["a"] for r in rows} == {ALIA[0], BRAM[0], CORA[0]}
    assert all(r["g"].startswith("Player-") for r in rows)
    assert all(":" in r["id"] and "e" not in r["id"] for r in rows)  # no exponent notation
    assert g.sv()["guilds"]["42"]["name"] == "Synthetic Guild"
    assert "cursor" in g.sv()["guilds"]["42"]


def test_server_history_limit_finishes_and_sets_cursor():
    g = Game(history=400)
    g.W.retain = 230  # the server only serves the newest 230
    g.W.dropUntil = g.W.now + 8  # and ignores the first requests after login
    g.run(200)
    assert g.errors == 0, g.last_error()
    assert len(g.chat()) == 230
    out = g.slash("status")
    assert "server sent nothing older" in out and "running" not in out
    assert g.sv()["guilds"]["42"]["cursor"]["g"]
    # next session only walks back to the cursor
    for i in range(7):
        g.W.addHistory(1, BRAM[0], BRAM[1], g.W.server + i)
    g.W.downloaded[1] = g.W.downloaded[1] + 7
    g.reload()
    g.run(60)
    assert len(g.chat()) == 237
    assert "caught up (+7)" in g.slash("status")


def test_debug_log_is_saved():
    g = Game(history=150)
    g.slash("debug on")
    g.slash("sync")
    g.run(60)
    diag = g.sv()["diag"]
    assert any("start: cursor" in line for line in diag)
    assert any("request #" in line for line in diag)
    assert any("done:" in line for line in diag)


def test_live_lines_pair_in_either_order():
    g = Game()
    g.run(10)
    g.say(ALIA, "hello |cff0070dd|Hitem:1|h[Thing]|h|r", clubFirst=False)
    g.say(BRAM, "club event first", clubFirst=True, gap=0.6)
    g.say(CORA, "chat first with gap", gap=0.5)
    g.run(10)
    live = sorted(by_src(g.chat(), "live"), key=lambda r: r["id"])  # stored when paired, not in order
    assert g.errors == 0, g.last_error()
    assert [(r["a"], r["m"]) for r in live] == [
        (ALIA[0], "hello |cff0070dd|Hitem:1|h[Thing]|h|r"),
        (BRAM[0], "club event first"),
        (CORA[0], "chat first with gap"),
    ]
    assert all(":" in r["id"] and not r["id"].startswith("ev|") for r in live)
    assert len(g.chat()) == 3


def test_same_author_twice_pairs_in_order():
    g = Game()
    g.run(10)
    g.say(ALIA, "first", clubFirst=True)
    g.say(ALIA, "second", clubFirst=True)
    g.say(ALIA, "third")
    g.run(10)
    rows = sorted(g.chat(), key=lambda r: r["id"])
    assert [r["m"] for r in rows] == ["first", "second", "third"]


def test_control_characters_and_discord_flag():
    g = Game()
    g.run(10)
    g.say(BRAM, "line\nbreak\ttab", discord=True)
    g.run(10)
    (r,) = g.chat()
    assert r["m"] == "line break tab"
    assert r["fd"] is True


def test_discord_bridged_history_gets_discord_name():
    g = Game(history=3)
    g.W.addHistory(1, None, None, g.W.server - 10, "discordfriend")
    g.W.downloaded[1] = 4
    g.run(10)
    rows = {r["id"]: r for r in by_src(g.chat(), "meta")}
    d = [r for r in rows.values() if r.get("fd")]
    assert len(d) == 1 and d[0]["a"] == "discordfriend" and "g" not in d[0]
    assert all(r["a"] != "?" for r in rows.values())
    assert g.errors == 0


@pytest.mark.parametrize("chat_name", ["", "discordfriend"])
@pytest.mark.parametrize("club_first", [False, True])
def test_discord_bridged_live_line_pairs(chat_name, club_first):
    g = Game(history=3)
    g.run(10)
    g.slash("debug on")
    g.W.say(1, None, None, "hi from discord", g.L.table_from(
        {"bridged": "discordfriend", "chatName": chat_name, "clubFirst": club_first, "gap": 0.4}))
    g.run(10)
    live = by_src(g.chat(), "live")
    assert len(live) == 1
    r = live[0]
    assert r["m"] == "hi from discord" and r["a"] == "discordfriend" and r.get("fd") is True
    assert not by_src(g.chat(), "event")
    diag = " | ".join(g.sv()["diag"])
    assert "from Discord" in diag and "without GUID: author {discordInfo,isSelf}" in diag
    assert g.errors == 0


def test_unpaired_halves_become_meta_and_event_rows():
    g = Game()
    g.run(80)  # let the login sync give up on the empty stream first; it would otherwise find Bram's line
    g.say(ALIA, "club part never got a chat event", noChat=True)
    g.say(BRAM, "chat event without club partner", noClub=True)
    g.run(10)
    rows = g.chat()
    meta, event = by_src(rows, "meta"), by_src(rows, "event")
    assert len(meta) == 1 and "m" not in meta[0] and meta[0]["a"] == ALIA[0]
    assert len(event) == 1 and event[0]["id"].startswith("ev|") and event[0]["m"].startswith("chat event")


def test_officer_stream_only_when_enabled():
    g = Game()
    g.run(10)
    g.say(ALIA, "secret officer stuff", sid=2)
    g.run(10)
    assert g.chat() == []
    assert "officer" in g.slash("officer on")
    g.say(ALIA, "now logged", sid=2)
    g.run(10)
    rows = g.chat()
    assert [(r["s"], r.get("m")) for r in rows if r["src"] == "live"] == [("o", "now logged")]


def test_lockdown_loses_text_but_keeps_meta_and_never_errors():
    g = Game()
    g.run(10)
    g.say(ALIA, "before")
    g.run(10)
    g.W.setLockdown(True)
    g.say(BRAM, "during boss fight")
    g.say(CORA, "also during")
    status = g.slash("status")
    g.run(30)
    assert g.errors == 0, g.last_error()
    assert "lockdown" in status
    assert len(g.chat()) == 1
    g.W.setLockdown(False)
    g.run(30)
    rows = g.chat()
    assert g.errors == 0, g.last_error()
    assert [(r["a"], r.get("m"), r["src"]) for r in sorted(rows, key=lambda r: r["t"])] == [
        (ALIA[0], "before", "live"),
        (BRAM[0], None, "meta"),
        (CORA[0], None, "meta"),
    ]


def test_reload_adds_no_duplicates_and_catches_up():
    g = Game(history=120)
    g.run(60)
    g.say(ALIA, "live before reload")
    g.run(10)
    before = len(g.chat())
    g.reload()
    g.run(60)
    assert len(g.chat()) == before
    # written while "logged out": appears as meta after the next login
    for i in range(5):
        g.W.addHistory(1, BRAM[0], BRAM[1], g.W.server + i)
    g.W.downloaded[1] = g.W.downloaded[1] + 5
    g.reload()
    g.run(60)
    assert len(g.chat()) == before + 5
    assert g.errors == 0, g.last_error()


def test_text_from_live_fills_a_meta_row_from_history_sync():
    g = Game()
    g.run(10)
    m = g.say(ALIA, "late chat half", clubFirst=True, gap=2)
    g.slash("sync")  # sync stores the club message as meta before the chat half arrives
    g.run(10)
    (r,) = g.chat()
    assert r["m"] == "late chat half" and r["src"] == "live"


def test_no_guild_stays_idle():
    g = Game(club=False)
    g.run(120)
    out = g.slash("status")
    assert "idle" in out
    assert g.errors == 0, g.last_error()
    assert g.sv()["guilds"] == {}


def test_status_and_flush():
    g = Game(history=10)
    g.run(30)
    out = g.slash("status")
    assert "Synthetic Guild" in out and "chat spooled 10" in out and "errors: 0" in out
    g.slash("flush")
    assert g.W.reloaded == 1
    assert "/gl status" in g.slash("bogus")


def test_ring_buffer_trims_oldest_and_sync_does_not_readd():
    g = Game()
    g.L.execute("W.ns.Store.MAX_CHAT = 50")
    g.run(10)
    for i in range(600):
        g.say(ALIA, f"msg {i}")
        g.run(1)
    g.run(700)  # past the 600 s periodic sync, which walks the server history again
    rows = g.chat()
    floor = g.sv()["guilds"]["42"]["floor"]
    assert g.errors == 0, g.last_error()
    assert len(rows) <= 50 + 500
    assert all(r["t"] >= floor for r in rows)
    assert all(r["src"] == "live" for r in rows)
    assert max(rows, key=lambda r: r["t"])["m"] == "msg 599"


def test_saved_file_imports_into_companion(tmp_path):
    g = Game(history=30)
    g.run(60)
    g.say(ALIA, 'quotes "x" and backslash \\ and ümlaut 🙂')
    g.say(BRAM, "orphan", noClub=True)
    g.run(10)
    data = parse(g.sv_text())
    with Spool(tmp_path / "spool.db") as spool:
        first = spool.import_sv(data, "c1")
        second = spool.import_sv(data, "c1")
        assert first.skipped == 0
        assert first.chat_new == 32 and second.changed == 0
        text = spool.db.execute("SELECT text FROM chat WHERE author=? AND src='live'", (ALIA[0],)).fetchone()[0]
        assert text == 'quotes "x" and backslash \\ and ümlaut 🙂'


def test_missing_club_api_disables_chat_without_errors():
    L = lupa.LuaRuntime(unpack_returned_tuples=True)
    W = L.eval(f"dofile([[{STUB}]])")
    L.execute("C_Club = nil")
    W.loadAddon(ADDON_DIR, L.table_from(FILES), "GuildLedger")
    W.login()
    W.advance(120)
    out = W.slash("status")
    assert W.ns.errors == 0, W.ns.lastError
    assert "missing API: club" in out and "idle" in out


def test_only_allowed_globals():
    L = lupa.LuaRuntime(unpack_returned_tuples=True)
    L.eval(f"dofile([[{STUB}]])")
    before = set(L.eval("(function() local t = {} for k in pairs(_G) do t[#t+1] = k end return t end)()").values())
    g = L.globals()
    g.W.loadAddon(ADDON_DIR, L.table_from(FILES), "GuildLedger")
    g.W.login()
    g.W.advance(30)
    after = set(L.eval("(function() local t = {} for k in pairs(_G) do t[#t+1] = k end return t end)()").values())
    assert after - before == {"GuildLedgerDB", "SLASH_GUILDLEDGER1", "SLASH_GUILDLEDGER2"}
