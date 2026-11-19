"""API.lua: GuildLedgerAPI, the bridge the Amazing Hub's Ledger tab reads (docs/dev/PACK_PLAN.md section 8)."""

from game import Game
from test_addon_relay import Guild


def api(game):
    return game.L.globals().GuildLedgerAPI


def lines(status):
    return [(l["kind"], l["text"]) for l in status["lines"].values()]


def test_status_lines_are_exactly_what_gl_status_prints():
    game = Game()
    game.run(30)
    printed = game.slash("status").split("\n")
    game.W.printed = game.L.table()
    st = api(game).GetStatus()
    assert len(game.W.printed) == 0, "GetStatus prints nothing"
    captured = lines(st)
    assert len(captured) == len(printed)
    for (kind, text), out in zip(captured, printed):
        assert text in out, (kind, text, out)
    assert [k for k, _ in captured][0] == "print"
    assert ("head", "World map") in captured and ("head", "Saving") in captured
    assert st["version"] == game.W.ns.Store.VERSION and st["role"] == "collector"
    assert st["errors"] == 0 and st["lockdown"] is False
    # chat output works normally again afterwards
    assert "status, version" in game.slash("status")


def test_member_role_and_modules():
    game = Game(role="member", name="Mem Ber")
    a = api(game)
    assert a.IsCollector() is False and a.GetStatus()["role"] == "member"
    assert set(a.GetModules().values()) >= {"Chat", "Comms", "Roster", "Relay", "Map", "Link"}
    assert a.apiVersion == 1


def test_map_switches_are_quiet_and_shared_with_the_command():
    game = Game(role="member", name="Mem Ber")
    a = api(game)
    m = a.GetMap()
    assert m["available"] is True and m["share"] is True and m["pins"] is True
    game.W.printed = game.L.table()
    a.SetMapShare(False)
    a.SetMapPins(False)
    assert len(game.W.printed) == 0, "no chat line from the hub's switches"
    m = a.GetMap()
    assert m["share"] is False and m["pins"] is False
    assert "not shared" in game.slash("status")
    game.slash("map share on")
    assert a.GetMap()["share"] is True
    game.reload()
    assert api(game).GetMap()["share"] is True and api(game).GetMap()["pins"] is False  # saved


def test_link_state_is_a_plain_copy():
    game = Game(role="member", name="Mem Ber")
    a = api(game)
    assert a.GetLink()["requested"] is False
    game.slash("link ABCD2345")
    info = a.GetLink()
    assert info["code"] == "ABCD2345" and info["acked"] is False and info["expired"] is False
    info["code"] = "CHANGED"
    assert a.GetLink()["code"] == "ABCD2345"
    game.run(1900)
    assert a.GetLink()["expired"] is True


def test_request_link_is_quiet_and_answers():
    game = Game(role="member", name="Mem Ber")
    a = api(game)
    game.W.printed = game.L.table()
    ok, msg = a.RequestLink("nope")
    assert ok is False and "not a link code" in msg
    ok, msg = a.RequestLink(" abcd 2345 ")
    assert ok is True and "sent" in msg
    assert len(game.W.printed) == 0, "no chat line from the hub's link box"
    assert a.GetLink()["code"] == "ABCD2345"
    assert "not a link code" in game.slash("link nope")  # /gl link still prints


def test_newer_version_seen_in_the_guild():
    guild = Guild([("Old Timer", "member"), ("New Comer", "member")])
    old, new = guild.g("Old Timer"), guild.g("New Comer")
    new.W.ns.Store.VERSION = "9.9.9"
    guild.run(30)  # hellos
    ver, who = api(old).NewerVersion()
    assert ver == "9.9.9" and who.startswith("New Comer")
    assert api(new).NewerVersion() == (None, None)


def test_safe_when_guildledger_switched_itself_off():
    game = Game(role=None)
    game.L.execute("GuildLedgerDB.schema = 99")
    game.reload()
    a = api(game)
    st = a.GetStatus()
    assert st["disabled"] and "newer GuildLedger" in st["lines"][1]["text"]
    assert a.IsCollector() is False and a.GetMap()["available"] is False
    a.SetMapShare(False)  # no error, no effect
    assert a.GetLink()["requested"] is False


def test_collector_switch_is_saved_and_reports_the_running_role():
    game = Game(role="member", name="Mem Ber")
    a = api(game)
    assert tuple(a.GetCollector()) == (False, False)
    a.SetCollector(True)
    assert game.W.ns.Store.Opts().collector is True
    assert tuple(a.GetCollector()) == (True, False), "wanted on, still running as member until /reload"
    a.SetCollector(False)
    assert tuple(a.GetCollector()) == (False, False)
    assert tuple(api(Game()).GetCollector()) == (True, True)
