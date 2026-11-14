"""Comms.lua: one paced queue with priorities for every module's addon messages."""

from game import Game


def queued(g, text, prio):
    g.L.execute(f'W.ns.Comms.Send([[{text}]], {prio})')


def test_high_priority_overtakes_bulk_and_order_is_kept_within_a_priority():
    g = Game()
    g.run(25)  # hello goes out first
    g.W.addonOut = g.L.table()
    for i in range(5):
        queued(g, f"T\tbulk{i}", 3)
    queued(g, "Xhigh-1", 1)
    queued(g, "Hnormal", 2)
    queued(g, "Xhigh-2", 1)
    g.run(8)
    sent = [m["msg"] for m in g.W.addonOut.values()]
    assert sent[:3] == ["Xhigh-1", "Xhigh-2", "Hnormal"]
    assert sent[3:] == [f"T\tbulk{i}" for i in range(5)]


def test_full_queue_drops_the_lowest_priority_first():
    g = Game()
    g.run(25)
    g.W.lockdown = True  # nothing goes out
    for i in range(300):
        queued(g, f"T\tbulk{i}", 3)
    queued(g, "Xhigh", 1)
    assert g.W.ns.Comms.Waiting() == 300 and g.W.ns.Comms.stats.dropped == 1
    g.W.lockdown = False
    g.run(3)
    assert g.W.addonOut[len(g.W.addonOut)]["msg"] == "Xhigh" or any(
        m["msg"] == "Xhigh" for m in g.W.addonOut.values())


def test_handler_gets_sender_and_self_flag():
    g = Game(name="Me Myself")
    g.run(25)
    g.L.execute("W.got = {} W.ns.Comms.Handle('Z', function(s, t, me) table.insert(W.got, s .. '|' .. t .. '|' .. tostring(me)) end)")
    g.W.fire("CHAT_MSG_ADDON", "GuildLedger", "Zhi", "GUILD", "Other One-Forever", "", 0, 0, "O", 0)
    g.W.fire("CHAT_MSG_ADDON", "GuildLedger", "Zme", "GUILD", "Me Myself-Forever", "", 0, 0, "M", 0)
    g.W.fire("CHAT_MSG_ADDON", "OtherAddon", "Zno", "GUILD", "Other One-Forever", "", 0, 0, "O", 0)
    g.W.fire("CHAT_MSG_ADDON", "GuildLedger", "Zwhisper", "WHISPER", "Other One-Forever", "", 0, 0, "O", 0)
    assert list(g.W.got.values()) == ["Other One-Forever|Zhi|false", "Me Myself-Forever|Zme|true"]
