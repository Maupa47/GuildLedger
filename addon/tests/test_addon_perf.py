"""Phase 6: timing with a big guild, on plain Lua 5.1 (WoW's language, no JIT). The numbers are this PC's,
not WoW's, but they show the order of magnitude and that no single step does unbounded work."""

from game import Game


def test_big_roster_and_long_history_stay_cheap_per_frame(capsys):
    g = Game(history=5000, members=1000)
    g.W.downloaded[1] = 5000  # first login after a long break: everything already downloaded
    g.run(60)
    perf = g.W.ns.perf
    snap, step = perf["roster snapshot"], perf["history step"]
    assert len(g.guild()["roster"]) == 1000
    assert len([r for r in g.chat() if r["src"] == "meta"]) == 5000
    assert step.n >= 10  # 5000 messages were split over many frames (<= 500 per step)
    with capsys.disabled():
        print(f"\n  Lua 5.1 on this PC: roster snapshot of 1000 members {snap.max:.1f} ms,"
              f" history step (<=500 messages) max {step.max:.1f} ms over {step.n} steps")
    assert snap.max < 250 and step.max < 250  # generous: a frame at 60 fps is 16 ms, a hitch is > 100 ms
    assert "Timing" not in g.slash("status")  # only with debug on
    g.slash("debug on")
    out = g.slash("status")
    assert "Timing (debug)" in out and "roster snapshot: " in out
    assert g.errors == 0, g.last_error()
