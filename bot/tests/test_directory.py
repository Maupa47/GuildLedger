"""D3 character directory (docs/dev/PLAN_COMMUNITY.md). No Discord. Synthetic names only."""

import random

import pytest

from guildledger_bot.community import directory as d
from guildledger_bot.community.link import Links
from guildledger_bot.store import Archive

G = "42"
T0 = 1794355200
TPL = d.DEFAULT_ARMORY


class Clock:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t


def member(i, name=None, level=None, rank=5, cls="MAGE"):
    return {"g": f"P-{i:04d}", "n": name or f"Name{i:04d} Sur", "r": rank, "rn": f"Rank{rank}",
            "l": level if level is not None else 10 + i % 51, "c": cls, "ls": T0 - 3600}


def link(a, uid, guid, name, t=T0):
    with a.db:
        a.db.execute("INSERT INTO links VALUES(?,?,?,?,?,?,?)", (G, guid, name, uid, None, t, "Col"))


@pytest.fixture
def env(tmp_path):
    a = Archive(tmp_path / "a.db")
    Links(a)  # makes the link tables
    clock = Clock()
    yield a, d.Directory(a, now=clock), clock
    a.close()


def apply(dr, writes):
    """Pretend Discord did every write."""
    for n, w in enumerate(writes):
        if w.action == "delete":
            dr.done(w)
        else:
            dr.done(w, w.thread_id or 1000 + n, list(range(len(w.post.messages))))


def test_armory_address():
    assert d.armory_url(TPL, "Testa Wanderer", 60).endswith("/character/testa-wanderer")
    assert d.armory_url(TPL, "Low Level", 9) is None, "no profile below level 10"
    assert d.armory_url(TPL, "Zoë Äpfel", 60) is None, "special letters wait until such a name was checked"
    assert d.armory_url("", "Some One", 60) is None and d.armory_url(None, "Some One", 60) is None


def test_user_post_lists_main_first_and_links(env):
    a, dr, clock = env
    with a.db:
        a.import_roster(G, T0, [member(1, "Ann One", 60, 2, "PRIEST"), member(2, "Ann Alt", 20),
                                member(3, "Bob Two", 30)])
    link(a, 77, "P-0001", "Ann One")
    link(a, 77, "P-0002", "Ann Alt")
    posts = {(p.kind, p.key): p for p in dr.wanted(TPL, 7)}
    p = posts[("user", "77")]
    assert p.title == "Ann One" and p.tag == "Priest"
    body = p.messages[0]
    assert body.startswith("<@77>") and body.index("Ann One") < body.index("Ann Alt")
    assert "(main)" in body and "/character/ann-one>" in body and "Rank2" in body
    idx = posts[("index", "A-C")]
    assert "Bob Two" in idx.messages[0] and "Ann One" not in idx.messages[0]
    assert ("help", "help") in posts


def test_chosen_main_comes_first(env):
    a, dr, _ = env
    with a.db:
        a.import_roster(G, T0, [member(1, "Ann One", 60), member(2, "Ann Alt", 20)])
    link(a, 77, "P-0001", "Ann One")
    link(a, 77, "P-0002", "Ann Alt")
    (p,) = [p for p in dr.wanted(TPL, 7, mains={77: "P-0002"}) if p.kind == "user"]
    assert p.title == "Ann Alt"


def test_second_run_writes_nothing_and_a_rank_change_one_post(env):
    a, dr, clock = env
    roster = [member(i) for i in range(40)]
    with a.db:
        a.import_roster(G, T0, roster)
    for i in range(0, 40, 4):
        link(a, 500 + i, f"P-{i:04d}", f"Name{i:04d} Sur")
    for _ in range(10):
        writes = dr.plan(dr.wanted(TPL, 7))
        if not writes:
            break
        apply(dr, writes)
    assert dr.plan(dr.wanted(TPL, 7)) == []
    roster[8]["r"], roster[8]["rn"] = 1, "Officer"
    with a.db:
        a.import_roster(G, T0 + 60, roster)
    writes = dr.plan(dr.wanted(TPL, 7))
    assert [(w.action, w.kind, w.key) for w in writes] == [("edit", "user", "508")]


def test_member_who_left_is_marked_then_removed(env):
    a, dr, clock = env
    roster = [member(1, "Ann One", 60), member(2, "Bob Two", 30)]
    with a.db:
        a.import_roster(G, T0, roster)
    link(a, 77, "P-0001", "Ann One")
    apply(dr, dr.plan(dr.wanted(TPL, 7)))
    with a.db:
        a.db.execute("UPDATE members SET in_guild=0 WHERE guid='P-0001'")
    posts = {(p.kind, p.key): p for p in dr.wanted(TPL, 7)}
    assert posts[("user", "77")].title == "Ann One (left)" and "left the guild" in posts[("user", "77")].messages[0]
    apply(dr, dr.plan(list(posts.values())))
    clock.t += 8 * 86400
    writes = dr.plan(dr.wanted(TPL, 7))
    assert [(w.action, w.key) for w in writes] == [("delete", "77")]


def test_write_limit_and_order(env):
    a, dr, _ = env
    with a.db:
        a.import_roster(G, T0, [member(i) for i in range(30)])
    for i in range(30):
        link(a, 900 + i, f"P-{i:04d}", f"Name{i:04d} Sur")
    writes = dr.plan(dr.wanted(TPL, 7))
    assert len(writes) == d.WRITES_PER_ROUND and writes[0].kind == "help"


def test_600_characters_stay_within_discord_limits(env):
    a, dr, _ = env
    rnd = random.Random(3)
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    roster = []
    for i in range(600):
        first = rnd.choice(letters) + "".join(rnd.choice("aeioulnrst") for _ in range(rnd.randint(3, 11)))
        roster.append(member(i, f"{first} {rnd.choice(letters)}{'x' * rnd.randint(3, 12)}", rnd.randint(1, 60)))
    with a.db:
        a.import_roster(G, T0, roster)
    for i in range(0, 200):  # 100 users with two characters each
        link(a, 10_000 + i // 2, f"P-{i:04d}", roster[i]["n"])
    posts = dr.wanted(TPL, 7)
    listed = sum(p.messages[0].count("\n") + sum(m.count("\n") + 1 for m in p.messages[1:])
                 for p in posts if p.kind == "index")
    assert listed == 400, "every unlinked character appears once"
    assert len([p for p in posts if p.kind == "user"]) == 100
    for p in posts:
        assert len(p.title) <= 100 and all(len(m) <= 2000 for m in p.messages)
    assert len(posts) < 1000, "Discord: at most 1000 active threads"


def test_split_messages_respects_the_limit():
    lines = [f"line {i} " + "x" * 50 for i in range(200)]
    out = d.split_messages("head", lines, limit=500)
    assert all(len(m) <= 500 for m in out) and out[0].startswith("head")
    assert sum(m.count("line ") for m in out) == 200
