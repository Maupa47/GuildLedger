"""Relay (CLAUDE.md 5.7): several clients in one simulated guild; addon messages are delivered to every
online client, like the GUILD channel. Synthetic names only."""

from game import ALIA, BRAM, Game, Spool, parse

COLL, MEM, MEM2 = "Coll Lector", "Mem Ber", "Sec Ond"


class Guild:
    def __init__(self, players):
        self.games, self.online, self.saved, self.pos = {}, set(), {}, 5000
        for name, role in players:
            self.games[name] = Game(role=role, name=name)
            self.online.add(name)
        self.addon_log = []  # (sender, message) of everything sent

    def g(self, name):
        return self.games[name]

    def pump(self):
        for name in sorted(self.online):
            W = self.games[name].W
            out = list(W.addonOut.values()) if W.addonOut else []
            W.addonOut = self.games[name].L.table()
            for m in out:
                self.addon_log.append((name, m["msg"]))
                for other in sorted(self.online):  # the sender gets its own message back, like in game
                    self.games[other].W.fire("CHAT_MSG_ADDON", m["prefix"], m["msg"], "GUILD", f"{name}-Forever",
                                             "", 0, 0, name, 0)

    def run(self, seconds):
        for _ in range(int(seconds)):
            for game in self.games.values():  # clocks of offline clients run on too
                game.run(1)
            self.pump()

    def say(self, who, text, sid=1):
        self.pos += 1
        for name, game in self.games.items():
            if name in self.online:
                game.W.say(sid, who[0], who[1], text, game.L.table_from({"pos": self.pos}))
            else:  # the server keeps it; this client sees it as history after login
                game.W.addHistory(sid, who[0], who[1], game.W.server, None, self.pos)
        self.pump()

    def logout(self, name):
        game = self.games[name]
        self.saved[name] = game.sv_text()
        game.W.logout()
        game.L.execute("GuildLedgerDB = nil")
        self.online.discard(name)

    def login(self, name):
        game = self.games[name]
        game.L.execute(self.saved.pop(name))
        game.load()
        self.online.add(name)

    def texts(self, name):
        return [r for r in self.g(name).chat() if r.get("m")]

    def sent(self, kind):
        return [m for _, m in self.addon_log if m.startswith(kind + "\t")]


def gap_scenario(members=(MEM,), lines=10, text=lambda i: f"while you were away {i}"):
    guild = Guild([(COLL, "collector")] + [(m, "member") for m in members])
    guild.run(40)
    guild.say(ALIA, "before")
    guild.run(5)
    guild.logout(COLL)
    for i in range(lines):
        guild.say((ALIA, BRAM)[i % 2], text(i))
        guild.run(3)
    guild.run(30)
    guild.login(COLL)
    return guild


def test_collector_gap_is_filled_by_a_member_and_member_drops_the_lines():
    guild = gap_scenario()
    guild.run(150)  # history sync, ask after 30 s, answers paced 1/s, confirmations
    coll = {r["m"]: r for r in guild.texts(COLL)}
    for i in range(10):
        row = coll[f"while you were away {i}"]
        assert row["src"] == "live" and row["rb"] == f"{MEM}-Forever"
    assert coll["before"].get("rb") is None  # captured by the collector itself
    left = [r["m"] for r in guild.texts(MEM)]
    assert left == ["before"]  # confirmed lines are dropped; the rest waits (or expires)
    assert len(guild.sent("T")) == 10 and guild.sent("G")
    for name in guild.games:
        assert guild.g(name).errors == 0, guild.g(name).last_error()


def test_long_line_with_umlauts_and_emoji_survives_the_split():
    long = "Grüße an alle 🙂 " * 25  # > 400 bytes, multi-byte characters at the cut points
    guild = gap_scenario(lines=1, text=lambda i: long.strip())
    guild.run(120)
    got = [r["m"] for r in guild.texts(COLL) if r.get("rb")]
    assert got == [long.strip()]
    assert len(guild.sent("T")) >= 3  # it went out in several pieces


def test_two_members_do_not_send_the_same_lines_twice():
    guild = gap_scenario(members=(MEM, MEM2), lines=12)
    guild.run(200)
    assert len([r for r in guild.texts(COLL) if r.get("rb")]) == 12
    ids = [m.split("\t")[1] for m in guild.sent("T")]
    assert len(ids) <= 14, f"{len(ids)} line messages for 12 lines"  # at most a collision or two


def test_forged_line_is_rejected():
    guild = gap_scenario(lines=1)
    coll = guild.g(COLL)
    guild.games[MEM].L.execute("W.ns.Store.PruneMember = function() end")
    # The member's own copy is withheld; an impostor answers with a different author GUID.
    guild.games[MEM].L.execute("W.ns.Relay.lineMessages = function() return {} end")
    guild.run(35)
    meta = [r for r in coll.chat() if not r.get("m")]
    assert meta, "the collector should still have its gap"
    row = meta[-1]
    payload = "\t".join(["g", str(row["t"]), row["a"], "Player-9999-FAKEFAKE", "0", "invented text"])
    coll.W.fire("CHAT_MSG_ADDON", "GuildLedger", f"T\t{row['id']}\t1/1\t{payload}", "GUILD", "Evil-Forever",
                "", 0, 0, "Evil", 0)
    coll.run(1)
    assert all(r.get("m") != "invented text" for r in coll.chat())
    assert coll.errors == 0, coll.last_error()


def test_member_waits_out_a_lockdown():
    guild = gap_scenario(lines=3)
    guild.g(MEM).W.lockdown = True
    guild.run(80)
    assert not [r for r in guild.texts(COLL) if r.get("rb")]
    guild.g(MEM).W.lockdown = False
    guild.run(30)
    assert len([r for r in guild.texts(COLL) if r.get("rb")]) == 3
    assert guild.g(MEM).errors == 0, guild.g(MEM).last_error()


def test_member_role_skips_history_and_roster_and_keeps_only_text():
    g = Game(history=50, members=20, role="member")
    g.run(60)
    assert (g.W.requests or 0) == 0 and g.W.rosterRequests == 0
    g.say(ALIA, "kept")
    g.say(BRAM, "no partner", noClub=True)  # no server ID: useless to a collector
    g.run(10)
    assert [r["m"] for r in g.chat()] == ["kept"]
    out = g.slash("status")
    assert "Role: Member" in out and "Not tracked by members" in out and "Lines kept for collectors: 1" in out
    assert g.errors == 0, g.last_error()


def test_member_buffer_limits():
    g = Game(role="member")
    g.L.execute("W.ns.Store.MEMBER_MAX = 30")
    g.run(30)
    for i in range(50):
        g.say(ALIA, f"line {i}")
        g.run(1)
    g.run(300)  # housekeeping
    rows = g.chat()
    assert len(rows) == 30 and rows[-1]["m"] == "line 49"
    g.run(3 * 86400 + 600)  # three days later everything is gone
    assert g.chat() == []


def test_new_install_is_member_and_old_install_becomes_collector():
    fresh = Game(role=None)
    fresh.run(30)
    assert fresh.sv()["opts"]["collector"] is False and fresh.sv()["schema"] == 3

    old = Game(role=None)
    old.W.unload()
    old.L.execute('GuildLedgerDB = { schema = 1, opts = { debug = false }, guilds = { ["42"] = { chat = {} } } }')
    old.load()
    old.run(30)
    assert old.sv()["schema"] == 3 and old.sv()["opts"]["collector"] is True


def test_relayed_text_reaches_the_companion(tmp_path):
    guild = gap_scenario(lines=2)
    guild.run(120)
    data = parse(guild.g(COLL).sv_text())
    with Spool(tmp_path / "s.db") as spool:
        spool.import_sv(data, "c1")
        rows = spool.db.execute("SELECT text, relayed_by FROM chat WHERE relayed_by IS NOT NULL").fetchall()
        assert sorted(r[0] for r in rows) == ["while you were away 0", "while you were away 1"]
        assert {r[1] for r in rows} == {f"{MEM}-Forever"}


def test_split_is_utf8_safe():
    g = Game()
    split = g.W.ns.Comms.SplitUtf8
    s = "ä" * 150  # 300 bytes
    parts = list(split(s, 7).values())
    assert "".join(parts) == s and all(len(p.encode("latin-1", "surrogateescape")) <= 7 for p in parts)


def test_versions_seen_and_outdated_listed():
    guild = Guild([(COLL, "collector"), (MEM, "member")])
    guild.g(MEM).L.execute('W.ns.Store.VERSION = "0.2.0"')  # an old install
    guild.run(45)
    out = guild.g(COLL).slash("status")
    assert "GuildLedger versions seen" in out and "Outdated, should update" in out and f"{MEM}-Forever (0.2.0)" in out
    older = guild.g(COLL).W.ns.Relay.older
    assert older("0.2.9", "0.2.10") and not older("0.3.0", "0.2.10") and not older("0.2.2", "0.2.2")


def test_need_spam_is_rate_limited():
    guild = gap_scenario(lines=3)
    mem = guild.g(MEM)
    for _ in range(10):  # someone floods needs
        mem.W.fire("CHAT_MSG_ADDON", "GuildLedger", "N\tg\t1-9999999999", "GUILD", "Spammer-Forever",
                   "", 0, 0, "Spammer", 0)
    guild.run(60)
    sends = [m for s, m in guild.addon_log if s == MEM and m.startswith("T\t")]
    assert len(sends) <= 3 * 2  # answered once (plus the real collector's need), not ten times


def test_half_lines_from_one_sender_are_bounded():
    g = Game()
    g.run(30)
    for i in range(500):
        g.W.fire("CHAT_MSG_ADDON", "GuildLedger", f"T\t{i}:{i}\t1/3\tx", "GUILD", "Flood-Forever", "", 0, 0, "F", 0)
    g.run(1)
    assert g.errors == 0, g.last_error()
    n = g.L.eval("(function() local n = 0 for _ in pairs(W.ns.Relay) do n = n + 1 end return n end)()")
    assert n > 0  # still alive; the buffer cap itself is internal (40 per sender)


def test_many_separate_gaps_need_several_messages_and_all_get_filled():
    guild = Guild([(COLL, "collector"), (MEM, "member")])
    guild.run(40)
    guild.logout(COLL)
    for i in range(14):  # 14 gaps far apart -> 14 ranges -> more than one need message
        guild.say(ALIA, f"gap line {i}")
        guild.run(400)
    guild.login(COLL)
    guild.run(240)
    assert len(guild.sent("N")) >= 2
    got = sorted(r["m"] for r in guild.texts(COLL) if r.get("rb"))
    assert got == sorted(f"gap line {i}" for i in range(14))


def test_gl_who_lists_everyone_online_with_role_version_and_counts():
    guild = gap_scenario(members=(MEM, MEM2), lines=4)
    guild.run(150)
    coll = guild.g(COLL)
    coll.W.printed = coll.L.table()
    coll.slash("who")
    guild.run(40)
    out = "\n".join(coll.W.printed.values())
    assert "asking everyone online" in out
    assert "players online with GuildLedger: 3 (you included)" in out
    v = coll.W.ns.Store.VERSION
    assert f"Collector - version {v} - filled 4 line(s) from members" in out
    assert f"{MEM}-Forever - version {v}" in out and f"{MEM2}-Forever - version {v}" in out
    assert "gave" in out and "keeps" in out
    assert any(m == "W" for _, m in guild.addon_log)


def test_addon_is_silent_in_chat_without_commands():
    g = Game(role="member", history=20)
    g.W.printed = g.L.table()
    g.run(120)
    g.say(ALIA, "hello")
    g.L.execute("W.ns.Safe('test', function() error('boom') end)")  # an internal error
    g.run(30)
    assert list(g.W.printed.values()) == []  # nothing in chat
    assert g.errors == 1 and "Problems: 1 error(s)" in g.slash("status")


def test_periodic_hello_does_not_make_collectors_ask_again_and_again():
    guild = gap_scenario(lines=2)
    guild.run(120)
    asked = len(guild.sent("N"))
    guild.run(3 * 900)  # three rounds of periodic hellos, no new gaps
    assert len(guild.sent("H")) >= 6
    assert len(guild.sent("N")) - asked <= 3  # only the 15-minute timer, not every hello


def test_hello_from_old_version_is_understood():
    g = Game()
    g.run(30)
    g.W.fire("CHAT_MSG_ADDON", "GuildLedger", "H\t0.2.1\tm\t42", "GUILD", "Old Timer-Forever", "", 0, 0, "O", 0)
    g.W.printed = g.L.table()
    g.slash("who")
    g.run(40)
    out = "\n".join(g.W.printed.values())
    assert "Old Timer-Forever - version 0.2.1" in out and "(outdated)" in out and "keeps 42 line(s)" in out
