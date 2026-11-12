"""Roster capture (CLAUDE.md 5.4) against the stub client. Synthetic names only."""

import pytest
from game import ADDON_DIR, FILES, STUB, Game, Spool, lupa, parse

NEW = ("Dara Newcomer", "Player-1111-0000DDDD")
OFFICER = "Ola Officer"


def ready_game(members=40):
    g = Game(members=members)
    g.run(30)  # login quiet time, first roster answer, first snapshot, event log
    return g


def kinds(events, src=None):
    return sorted((e["k"], e["n"]) for e in events if src is None or e["src"] == src)


def test_first_snapshot_stores_roster_without_events():
    g = ready_game()
    gd = g.guild()
    assert len(gd["roster"]) == 40
    assert gd["rosterAt"] > 0
    assert g.events() == []
    m0 = gd["roster"]["Player-1111-00000000"]
    assert m0["n"] == "Member000 Rostered" and m0["r"] == 4 and m0["rn"] == "Initiate" and m0["c"] == "MAGE"
    assert "ls" in m0  # online
    assert "ls" not in gd["roster"]["Player-1111-00000001"]  # offline: never seen online yet
    assert g.errors == 0, g.last_error()


def test_live_join_leave_kick_promote_are_precise_sys_events():
    g = ready_game()
    g.W.join(NEW[0], NEW[1])
    g.run(20)
    g.W.leave("Member001 Rostered")
    g.run(20)
    g.W.kick("Member002 Rostered", OFFICER)
    g.run(20)
    g.W.promote(OFFICER, "Member003 Rostered", "Veteran")
    g.run(20)
    ev = g.events()
    sys = [e for e in ev if e["src"] == "sys"]
    assert kinds(sys) == [("join", NEW[0]), ("kick", "Member002 Rostered"), ("leave", "Member001 Rostered"),
                          ("promote", "Member003 Rostered")]
    assert all(e["p"] is True for e in sys)
    by = {e["k"]: e for e in sys}
    assert by["kick"]["by"] == OFFICER and by["promote"]["by"] == OFFICER and by["promote"]["d"] == "Veteran"
    assert by["join"]["g"] == NEW[1]  # filled in from the roster refresh that followed
    assert by["leave"]["g"] == "Player-1111-00000001"
    assert by["join"]["id"] == f"join|{NEW[0]}||{by['join']['t'] // 5}"
    # the roster refresh after each change must not add diff rows for the same change
    assert [e for e in ev if e["src"] == "diff"] == []
    assert g.errors == 0, g.last_error()


def test_system_messages_in_first_seconds_after_login_are_ignored():
    g = Game(members=10)
    g.run(2)
    g.W.sysRaw(f"{NEW[0]} has joined the guild.")
    g.run(30)
    assert [e for e in g.events() if e["src"] == "sys"] == []
    g.W.sysRaw("Some Body has joined the guild.")
    g.run(1)
    assert kinds(g.events(), "sys") == [("join", "Some Body")]


def test_changes_while_offline_become_diff_and_log_events():
    g = ready_game()
    before = g.guild()["rosterAt"]

    def change():
        g.W.join(NEW[0], NEW[1])
        g.W.leave("Member005 Rostered")
        g.W.kick("Member006 Rostered", OFFICER)

    g.offline(3 * 3600, change)
    g.run(30)
    ev = g.events()
    diff = [e for e in ev if e["src"] == "diff"]
    assert kinds(diff) == [("join", NEW[0]), ("leave", "Member005 Rostered"), ("leave", "Member006 Rostered")]
    assert all(e["p"] is False and e["w"] == before and e["t"] > before for e in diff)
    log = {e["n"]: e for e in ev if e["src"] == "log"}
    assert log[NEW[0]]["k"] == "join" and log["Member005 Rostered"]["k"] == "leave"
    kick = log["Member006 Rostered"]
    assert kick["k"] == "kick" and kick["by"] == OFFICER
    # the log gives elapsed hours -> a one-hour window that contains the real time
    real = g.W.server - 30 - 3 * 3600 / 2
    assert kick["t"] - kick["w"] == 3600 and kick["w"] <= real <= kick["t"]
    assert [e for e in ev if e["src"] == "sys"] == []  # no system messages while away
    assert g.errors == 0, g.last_error()


def test_reload_and_later_log_reads_add_nothing():
    g = ready_game()
    g.offline(3 * 3600, lambda: (g.W.join(NEW[0], NEW[1]), g.W.leave("Member005 Rostered")))
    g.run(30)
    n = len(g.events())
    assert n == 4  # 2 diff + 2 log
    g.reload()
    g.run(30)
    assert len(g.events()) == n
    for _ in range(4):  # elapsed hours tick over; the same log entries land in other hour buckets
        g.run(40 * 60)
        g.slash("sync")
        g.run(30)
    assert len(g.events()) == n
    g.offline(600)
    g.run(30)
    assert len(g.events()) == n
    assert g.errors == 0, g.last_error()


def test_roster_still_loading_is_not_trusted():
    g = Game(members=40)
    g.W.rosterHole = 7
    g.run(30)
    assert "rosterAt" not in g.guild()
    assert "not loaded" in g.slash("status")
    g.W.rosterHole = None
    g.slash("sync")
    g.run(30)
    assert len(g.guild()["roster"]) == 40 and g.events() == []


def test_mass_disappearance_is_refused_until_confirmed():
    g = ready_game()
    removed = []
    for _ in range(12):  # 30 % of the guild
        removed.append(g.W.roster[1]["name"])
        g.L.execute("table.remove(W.roster, 1)")
    g.slash("sync")
    g.run(15)
    assert [e for e in g.events() if e["src"] == "diff"] == []
    assert "refused" in g.slash("status")
    for _ in range(4):  # still the same after several reads over minutes: a real purge
        g.run(70)
        g.slash("sync")
        g.run(15)
    diff = [e for e in g.events() if e["src"] == "diff"]
    assert sorted(e["n"] for e in diff) == sorted(removed)
    assert g.errors == 0, g.last_error()


def test_lockdown_system_message_is_ignored_without_errors():
    g = ready_game()
    g.W.setLockdown(True)
    g.W.join(NEW[0], NEW[1])
    g.run(20)
    g.W.setLockdown(False)
    g.run(400)  # periodic roster request catches it as a diff event
    assert kinds(g.events(), "sys") == []
    assert kinds(g.events(), "diff") == [("join", NEW[0])]
    assert g.errors == 0, g.last_error()


@pytest.mark.parametrize("fmt,msg,expect", [
    ("%s has been kicked out of the guild by %s.", "A B has been kicked out of the guild by C-D.", ["A B", "C-D"]),
    ("%2$s wurde von %1$s aus der Gilde geworfen.", "Opfer Name wurde von Täter aus der Gilde geworfen.",
     ["Täter", "Opfer Name"]),
    ("%s (Lvl. %d) joined [x]?", "Q (Lvl. 7) joined [x]?", ["Q", "7"]),
])
def test_format_to_pattern(fmt, msg, expect):
    g = Game()
    roster = [m for m in g.W.ns.modules.values() if m.name == "Roster"][0]
    pat, order = roster.toPattern(fmt)
    caps = g.L.eval("function(s, p) return {s:match(p)} end")(msg, pat)
    args = {}
    for i, num in order.items():
        args[num] = caps[i]
    assert [args[k] for k in sorted(args)] == expect


def test_player_links_in_system_messages():
    g = ready_game()
    g.W.sysRaw(f"|Hplayer:{NEW[0]}|h[{NEW[0]}]|h has joined the guild.")
    g.run(1)
    assert kinds(g.events(), "sys") == [("join", NEW[0])]


def test_status_shows_roster():
    g = ready_game()
    out = g.slash("status")
    assert "roster: 40 members stored" in out and "event log" in out


def test_missing_roster_api_without_errors():
    L = lupa.LuaRuntime(unpack_returned_tuples=True)
    W = L.eval(f"dofile([[{STUB}]])")
    L.execute("C_GuildInfo = nil; QueryGuildEventLog = nil")
    W.loadAddon(ADDON_DIR, L.table_from(FILES), "GuildLedger")
    W.login()
    W.advance(120)
    out = W.slash("status")
    assert W.ns.errors == 0, W.ns.lastError
    assert "eventlog" in out and "roster" in out and "API missing" in out


def test_companion_import_supersedes_and_shows_window(tmp_path):
    from guildledger.export import export
    g = ready_game()
    g.offline(3 * 3600, lambda: (g.W.join(NEW[0], NEW[1]), g.W.kick("Member006 Rostered", OFFICER)))
    g.run(30)
    g.W.leave("Member007 Rostered")  # live: sys
    g.run(30)
    data = parse(g.sv_text())
    with Spool(tmp_path / "spool.db") as spool:
        first = spool.import_sv(data, "c1")
        assert first.skipped == 0 and first.events_new == len(g.events())
        assert spool.import_sv(data, "c1").changed == 0
        live = {(r["kind"], r["name"], r["src"]) for r in spool.event_rows("42")}
        # diff join loses to the log join; the diff leave of a kicked member loses to the log kick;
        # the log quit of Member007 loses to the live sys leave
        assert live == {("join", NEW[0], "log"), ("kick", "Member006 Rostered", "log"),
                        ("leave", "Member007 Rostered", "sys")}
        assert spool.db.execute("SELECT COUNT(*) FROM members WHERE in_guild=1").fetchone()[0] == 39
        files = export(spool, tmp_path / "logs", None)
        roster = [p for p in files if p.name.startswith("roster")][0].read_text(encoding="utf-8")
        assert "KICK Member006 Rostered by Ola Officer (between " in roster


def test_event_log_arriving_in_pieces_stores_each_entry_once_and_prints_one_line():
    g = ready_game()
    base = g.W.server - 5 * 3600
    for i in range(150):  # older history than the first snapshot; a leave every 2 minutes
        g.L.execute(f'table.insert(W.glog, {{ kind = "quit", p1 = "Gone{i:03d} Person", at = {base + i * 120} }})')
    g.slash("debug on")
    g.W.printed = g.L.table()
    for end in range(100, 151):  # Phase 3: the event fires again for every entry that arrives
        g.W.glogEnd = end
        g.W.fire("GUILD_EVENT_LOG_UPDATE")
    g.run(10)
    log = [e for e in g.events() if e["src"] == "log"]
    assert sorted(e["n"] for e in log) == [f"Gone{i:03d} Person" for i in range(150)]
    printed = [m for m in g.W.printed.values() if "event log" in m]
    assert len(printed) == 1 and "51 read(s), +150 new" in printed[0]
    g.W.fire("GUILD_EVENT_LOG_UPDATE")
    g.run(10)
    assert len([e for e in g.events() if e["src"] == "log"]) == 150
    assert g.errors == 0, g.last_error()


def test_log_entry_first_without_actor_then_with_actor_is_one_event(tmp_path):
    g = ready_game()
    entry = '{ kind = "remove", p1 = %s, p2 = "Emma Example", at = W.server - 600 }'
    g.L.execute("table.insert(W.glog, " + entry % "nil" + ")")
    g.W.fire("GUILD_EVENT_LOG_UPDATE")
    g.L.execute("W.glog[#W.glog].p1 = 'Ola Officer'")  # the next piece names the actor
    g.W.fire("GUILD_EVENT_LOG_UPDATE")
    g.run(10)
    kicks = [e for e in g.events() if e["k"] == "kick"]
    assert len(kicks) == 1 and kicks[0]["by"] == OFFICER
    # the companion merges the same two stages when they come from different files
    first = parse(g.sv_text())
    row = [e for e in first["GuildLedgerDB"]["guilds"]["42"]["ev"] if e["k"] == "kick"][0]
    del row["by"]
    with Spool(tmp_path / "s.db") as spool:
        spool.import_sv(first, "c1")
        res = spool.import_sv(parse(g.sv_text()), "c2")
        assert res.events_updated == 1 and res.events_new == 0
        rows = spool.db.execute("SELECT actor FROM events WHERE kind='kick'").fetchall()
        assert [r[0] for r in rows] == [OFFICER]


def test_event_ring_buffer_keeps_newest():
    g = ready_game(members=5)
    g.L.execute("W.ns.Store.MAX_EV = 50")
    for i in range(700):
        g.W.sysRaw(f"Name{i:04d} Person has joined the guild.")
        g.run(6)  # different 5 s buckets
    ev = g.events()
    assert 50 <= len(ev) <= 550
    assert ev[-1]["n"] == "Name0699 Person" and all(e["n"] != "Name0000 Person" for e in ev)
    assert g.errors == 0, g.last_error()
