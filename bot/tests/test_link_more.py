"""D1 link additions (docs/dev/archive/PLAN_COMMUNITY.md): /main, /link approve, "!link CODE" in guild chat, masking."""

from guildledger.discord import chat_line, mask_link_code
from guildledger_bot.community.link import CHAT_CODE_TTL, Links

from test_link import G, OTHER, T0, USER, env, request  # noqa: F401 (fixture)

OFFICER = 3003


def chat(a, author, text, t, guid=None, rid=None, stream="g"):
    with a.db:
        a.db.execute("INSERT INTO chat(guild, id, stream, ts_utc, author, guid, text, src, first_collector)"
                     " VALUES(?,?,?,?,?,?,?,?,?)", (G, rid or f"{t}:0", stream, t, author, guid, text, "live", "Col"))


def test_chat_code_opens_a_confirmation_for_the_code_owner(env):
    a, links, clock = env
    code = links.new_code(USER)
    chat(a, "Bob Two", f"!link {code.lower()}", T0 + 30, guid="P-BOB")
    assert links.process() == 1
    (c,) = links.to_notify()
    assert (c.discord_user_id, c.name, c.kind) == (USER, "Bob Two", "link")
    assert links.answer(c.id, USER, True).startswith("Linked")
    assert [r["name"] for r in links.chars(USER)] == ["Bob Two"]


def test_chat_code_rows_are_read_once(env):
    a, links, clock = env
    code = links.new_code(USER)
    chat(a, "Bob Two", f"!link {code}", T0 + 30, guid="P-BOB")
    links.process()
    links.process()
    assert len(links.open_for(USER)) == 1
    # other lines, officer stream, a code inside a sentence: ignored
    chat(a, "Ann One", f"my code is !link {code}", T0 + 40, guid="P-ANN", rid="b")
    chat(a, "Ann One", f"!link {code}", T0 + 41, guid="P-ANN", rid="c", stream="o")
    links.process()
    assert len(links.open_for(USER)) == 1


def test_chat_code_lives_ten_minutes(env):
    a, links, clock = env
    code = links.new_code(USER)
    chat(a, "Bob Two", f"!link {code}", T0 + CHAT_CODE_TTL + 5, guid="P-BOB")
    links.process()
    assert links.open_for(USER) == [] and "expired" in links.log[-1]


def test_chat_code_used_by_a_stranger_can_be_refused(env):
    a, links, clock = env
    code = links.new_code(USER)
    chat(a, "Bob Two", f"!link {code}", T0 + 30, guid="P-BOB")          # someone read the code in chat
    chat(a, "Ann One", f"!link {code}", T0 + 40, guid="P-ANN", rid="2")  # the real owner
    links.process()
    by_name = {c.name: c for c in links.open_for(USER)}
    assert "will not be linked" in links.answer(by_name["Bob Two"].id, USER, False)
    assert links.answer(by_name["Ann One"].id, USER, True).startswith("Linked")
    chat(a, "Bob Two", f"!link {code}", T0 + 50, guid="P-BOB", rid="3")
    links.process()
    assert [r["name"] for r in links.chars(USER)] == ["Ann One"]


def test_link_code_is_masked_in_the_log_channel():
    assert mask_link_code("!link ABCD2345") == "!link ••••"
    assert mask_link_code("  !LINK abcd2345 thanks") == "  !LINK •••• thanks"
    assert mask_link_code("I typed !link ABCD2345") == "I typed !link ABCD2345", "only a line that starts with it"
    row = {"ts_utc": T0, "stream": "g", "author": "Bob Two", "from_discord": 0, "text": "!link ABCD2345",
           "edited": 0, "deleted": 0}
    assert "ABCD2345" not in chat_line(row, None)


def test_officer_approves_a_current_member(env):
    a, links, clock = env
    assert "Linked" in links.approve(OFFICER, USER, "ann one")
    (r,) = links.chars(USER)
    assert r["name"] == "Ann One" and r["via_collector"] == f"approved by {OFFICER}"
    assert "already linked to this user" in links.approve(OFFICER, USER, "Ann One")
    assert "another Discord user" in links.approve(OFFICER, OTHER, "Ann One")
    assert "not a current guild member" in links.approve(OFFICER, USER, "Nobody Here")


def test_approve_refuses_a_member_who_left(env):
    a, links, clock = env
    with a.db:
        a.db.execute("UPDATE members SET in_guild=0 WHERE name='Bob Two'")
    assert "not a current guild member" in links.approve(OFFICER, USER, "Bob Two")


def test_main_character_is_chosen_or_the_highest_level(env):
    a, links, clock = env
    links.approve(OFFICER, USER, "Ann One")   # level 30
    links.approve(OFFICER, USER, "Ann Alt")   # level 12
    assert links.main_name(USER) == "Ann One"
    assert links.set_main(USER, "ann alt") == "Main character: Ann Alt."
    assert links.main_name(USER) == "Ann Alt"
    assert "not one of your linked" in links.set_main(USER, "Bob Two")
    links.unlink(USER, "Ann Alt")
    assert links.main_name(USER) == "Ann One", "a main that is no longer linked falls back"
    links.set_main(USER, None)
    assert links.main_name(USER) == "Ann One"


def test_first_link_is_reported_once(env):
    a, links, clock = env
    assert links.first_link_done(USER) is False
    links.approve(OFFICER, USER, "Ann One")
    assert links.first_link_done(USER) is True
    assert links.first_link_done(USER) is False
    restarted = Links(a, now=clock)
    assert restarted.first_link_done(USER) is False
