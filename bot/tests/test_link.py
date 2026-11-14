"""Discord link and activity logic (no Discord). Synthetic data only."""

import pytest

from guildledger_bot import activity
from guildledger_bot.link import ALPHABET, MAX_OPEN, Links
from guildledger_bot.store import Archive

G = "42"
T0 = 1794355200
USER, OTHER = 1001, 2002


class Clock:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t


@pytest.fixture
def env(tmp_path):
    a = Archive(tmp_path / "a.db")
    clock = Clock()
    links = Links(a, now=clock)
    members = [{"g": "P-ANN", "n": "Ann One", "r": 2, "rn": "Officer", "l": 30, "c": "MAGE", "ls": T0 - 3600},
               {"g": "P-ALT", "n": "Ann Alt", "r": 5, "rn": "Member", "l": 12, "c": "DRUID", "ls": T0 - 40 * 86400},
               {"g": "P-BOB", "n": "Bob Two", "r": 4, "rn": "Member", "l": 25, "c": "ROGUE", "ls": T0 - 20 * 86400}]
    with a.db:
        a.import_roster(G, T0, members)
    yield a, links, clock
    a.close()


def request(a, kind, name, guid=None, code=None, tag="TAGANN0001", t=None, rid=None):
    row = {"id": rid or f"{kind}|{code}|{name}|{t}", "t": t or T0 + 10, "k": kind, "tag": tag, "n": name}
    if code:
        row["code"] = code
    if guid:
        row["g"] = guid
    with a.db:
        a.import_links(G, [row], "Collector")


def test_code_format():
    a = Archive(":memory:")
    code = Links(a).new_code(USER)
    assert len(code) == 8 and set(code) <= set(ALPHABET)


def test_full_link_needs_the_users_confirmation(env):
    a, links, clock = env
    code = links.new_code(USER)
    request(a, "link", "Ann One-Forever", code=code)  # sender carries the realm; guid unknown to the collector
    assert links.process() == 1
    (c,) = links.to_notify()
    assert (c.discord_user_id, c.name, c.kind) == (USER, "Ann One", "link")
    assert links.chars(USER) == []  # nothing linked before the click
    assert "not for you" in links.answer(c.id, OTHER, True)
    assert "Linked" in links.answer(c.id, USER, True)
    assert [ch["name"] for ch in links.chars(USER)] == ["Ann One"]
    assert links.whois("ann one") == [(USER, "Ann One")]
    assert "already answered" in links.answer(c.id, USER, True)
    request(a, "link", "Ann One-Forever", code=code, rid="again")
    links.process()
    assert links.to_notify() == [] and "code already used" in links.log[-1]


@pytest.mark.parametrize("case,expect", [
    ("expired", "code expired"), ("unknown", "unknown code"), ("not member", "not a current guild member")])
def test_requests_that_are_refused(env, case, expect):
    a, links, clock = env
    code = links.new_code(USER)
    if case == "expired":
        request(a, "link", "Ann One", code=code, t=T0 + 1801)
    elif case == "unknown":
        request(a, "link", "Ann One", code="ZZZZZZZZ")
    else:
        request(a, "link", "Stranger Person", code=code)
    assert links.process() == 0
    assert expect in links.log[-1]


def test_replayed_code_from_another_character_can_be_rejected_and_stays_blocked(env):
    a, links, clock = env
    code = links.new_code(USER)
    request(a, "link", "Bob Two", code=code)  # Bob saw Ann's code in the addon channel and replayed it
    links.process()
    (c,) = links.to_notify()
    assert c.name == "Bob Two"
    assert "will not be linked" in links.answer(c.id, USER, False)
    assert links.chars(USER) == []
    request(a, "link", "Bob Two", code=code, rid="replay2")
    links.process()
    assert "blocked" in links.log[-1] and links.to_notify() == []


def test_alt_is_offered_to_the_linked_user(env):
    a, links, clock = env
    code = links.new_code(USER)
    request(a, "link", "Ann One", code=code)
    links.process()
    links.answer(links.to_notify()[0].id, USER, True)
    request(a, "alt", "Ann Alt", tag="TAGANN0001", rid="alt1")
    request(a, "alt", "Bob Two", tag="TAGBOB0001", rid="alt2")  # an unknown tag: nothing happens
    assert links.process() == 1
    (c,) = links.to_notify()
    assert (c.name, c.kind, c.discord_user_id) == ("Ann Alt", "alt", USER)
    links.answer(c.id, USER, True)
    assert sorted(ch["name"] for ch in links.chars(USER)) == ["Ann Alt", "Ann One"]


def test_open_confirmations_are_capped_and_survive_a_restart(env, tmp_path):
    a, links, clock = env
    code = links.new_code(USER)
    for i, name in enumerate(["Ann One", "Ann Alt", "Bob Two"]):
        request(a, "link", name, code=code, rid=f"r{i}")
    links.process()
    assert len(links.open_for(USER)) == MAX_OPEN
    links.mark_notified(links.to_notify()[0].id, delivered=False)  # DMs closed
    restarted = Links(a, now=clock)
    assert len(restarted.open_for(USER)) == MAX_OPEN  # /link shows them again with buttons
    assert len(restarted.to_notify()) == MAX_OPEN - 1


def test_character_linked_to_someone_else_is_not_offered(env):
    a, links, clock = env
    c1 = links.new_code(USER)
    request(a, "link", "Ann One", code=c1)
    links.process()
    links.answer(links.to_notify()[0].id, USER, True)
    c2 = links.new_code(OTHER)
    request(a, "link", "Ann One", code=c2, rid="other")
    links.process()
    assert "linked to another Discord user" in links.log[-1]


def test_unlink_removes_everything(env):
    a, links, clock = env
    code = links.new_code(USER)
    request(a, "link", "Ann One", code=code)
    links.process()
    links.answer(links.to_notify()[0].id, USER, True)
    assert links.unlink(USER) == 1
    assert links.chars(USER) == [] and links.whois("Ann One") == []


def test_status_and_roles(env):
    a, links, clock = env
    code = links.new_code(USER)
    request(a, "link", "Ann One", code=code)
    links.process()
    links.answer(links.to_notify()[0].id, USER, True)
    st = links.status()
    assert st["members"] == 3 and st["linked"] == 1 and st["users"] == 1
    assert st["unlinked"] == ["Ann Alt", "Bob Two"]
    assert links.desired_rank(USER) == ("Officer", True)
    assert links.main_name(USER) == "Ann One"
    assert links.out_of_guild_since(USER) is None
    with a.db:
        a.import_roster(G, T0 + 100, [{"g": "P-BOB", "n": "Bob Two"}])  # Ann left
    clock.t = T0 + 500
    assert links.desired_rank(USER) == (None, False)
    assert links.out_of_guild_since(USER) == T0 + 500


def test_activity_queries(env):
    a, links, clock = env
    a.import_rows(G, "Guild", [{"id": f"{T0 - 3600 * i}000000:{i}", "t": T0 - 3600 * i, "s": "g", "a": "Ann One",
                                "g": "P-ANN", "m": "hi", "src": "live"} for i in range(1, 6)], [], "c1")
    a.import_rows(G, "Guild", [], [{"id": "join|Bob Two||1", "t": T0 - 86400, "p": True, "k": "join",
                                    "n": "Bob Two", "g": "P-BOB", "src": "sys"}], "c1")
    (ann,) = activity.find_chars(links, "ann one")
    (s,) = activity.seen(links, [ann])
    assert s["online"] == T0 - 3600 and s["chat"] == T0 - 3600
    (bob,) = activity.find_chars(links, "Bob Two")
    j = activity.joined(links, bob)
    assert j["when"] == T0 - 86400 and j["precision"] == "exact"
    assert "first seen" in activity.joined(links, ann)["precision"]
    code = links.new_code(USER)
    request(a, "link", "Ann One", code=code)
    links.process()
    links.answer(links.to_notify()[0].id, USER, True)
    (act,) = activity.activity(links, USER, T0)
    assert act["lines7"] == 5 and act["level"] == 30
    grouped, unlinked = activity.inactive(links, 14, T0)
    assert grouped == {}  # Ann's only linked character is active
    assert [u["name"] for u in unlinked] == ["Ann Alt", "Bob Two"]


def test_role_settings_saved_in_the_archive_win_over_config(env):
    a, links, clock = env
    assert links.role_settings(5, {"Member": 7}) == (5, {"Member": 7})  # nothing set: config.toml
    links.set_verified_role(111)
    links.set_rank_role("Officer", 222, {"Member": 7})
    assert links.role_settings(5, {"Member": 7}) == (111, {"Member": 7, "Officer": 222})
    links.set_rank_role("Member", None)
    links.set_verified_role(None)
    assert links.role_settings(5, {}) == (0, {"Officer": 222})
    assert [r[0] for r in links.guild_ranks()] == ["Officer", "Member"]
