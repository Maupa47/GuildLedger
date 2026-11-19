"""Link.lua: /gl link CODE travels member -> guild addon channel -> collector (simulated guild)."""

from game import Spool, parse
from test_addon_relay import COLL, MEM, Guild

CODE = "ABCD2345"


def link_guild():
    guild = Guild([(COLL, "collector"), (MEM, "member")])
    guild.run(30)
    return guild


def sent(guild, who, kind):
    return [m for s, m in guild.addon_log if s == who and m.startswith(kind + "\t")]


def test_code_reaches_a_collector_is_acknowledged_and_stops_resending():
    guild = link_guild()
    mem = guild.g(MEM)
    out = mem.slash(f"link {CODE.lower()}")  # case does not matter
    assert "link code sent" in out
    guild.run(5)
    links = guild.g(COLL).guild().get("links") or []
    rows = links if isinstance(links, list) else list(links.values())
    assert len(rows) == 1 and rows[0]["code"] == CODE and rows[0]["k"] == "link"
    assert rows[0]["n"] == f"{MEM}-Forever"
    tag = mem.sv()["link"]["tag"]
    assert rows[0]["tag"] == tag and len(tag) == 10
    assert sent(guild, COLL, "Y") == [f"Y\t{CODE}"]
    assert mem.sv()["link"]["pending"]["acked"] is True and mem.sv()["link"]["requested"] is True
    guild.run(600)
    assert len(sent(guild, MEM, "L")) == 1  # acknowledged: no re-sending
    assert "reached a collector" in mem.slash("status")


def _chat(game):
    return "\n".join(str(v) for v in game.W.printed.values())


def test_the_later_confirmation_is_quiet_unless_messages_are_on():
    guild = link_guild()
    mem = guild.g(MEM)
    mem.slash(f"link {CODE}")  # resets the chat log; the answer to the command itself always shows
    guild.run(5)
    assert "collector received your link code" not in _chat(mem)  # default: nothing unasked in chat
    assert "Chat messages: |cff888888off|r" in mem.slash("status")
    assert "on" in mem.slash("messages on")
    assert mem.L.globals().GuildLedgerAPI.GetMessages() is True
    mem.L.globals().GuildLedgerAPI.SetMessages(False)
    assert mem.L.globals().GuildLedgerAPI.GetMessages() is False
    mem.slash("messages on")
    mem.L.execute("GuildLedgerDB.link.pending.acked = false")
    guild.run(200)  # re-sent, acknowledged again
    assert "collector received your link code" in _chat(mem)


def test_without_a_collector_the_code_is_resent_until_it_expires():
    guild = Guild([(MEM, "member")])
    guild.run(30)
    guild.g(MEM).slash(f"link {CODE}")
    guild.run(1900)
    n = len(sent(guild, MEM, "L"))
    assert 9 <= n <= 11  # every 3 minutes for 30 minutes
    guild.run(600)
    assert len(sent(guild, MEM, "L")) == n
    assert "expired" in guild.g(MEM).slash("status")


def test_bad_code_is_refused_locally():
    guild = link_guild()
    out = guild.g(MEM).slash("link 0O1I")
    assert "not a link code" in out
    guild.run(10)
    assert sent(guild, MEM, "L") == []


def test_alt_announces_itself_once_after_login_and_the_tag_stays():
    guild = link_guild()
    mem = guild.g(MEM)
    mem.slash(f"link {CODE}")
    guild.run(10)
    tag = mem.sv()["link"]["tag"]
    guild.logout(MEM)  # same account, next character (the account-wide file carries the tag)
    guild.run(5)
    guild.login(MEM)
    guild.run(120)
    assert sent(guild, MEM, "A") == [f"A\t{tag}"]
    assert mem.sv()["link"]["tag"] == tag
    rows = guild.g(COLL).guild()["links"]
    rows = rows if isinstance(rows, list) else list(rows.values())
    assert [r["k"] for r in rows] == ["link", "alt"]


def test_members_do_not_record_link_requests():
    guild = Guild([(MEM, "member"), ("Oth Er", "member")])
    guild.run(30)
    guild.g(MEM).slash(f"link {CODE}")
    guild.run(10)
    assert not guild.g("Oth Er").guild().get("links")
    assert sent(guild, "Oth Er", "Y") == []


def test_link_request_reaches_companion_and_bot_archive(tmp_path):
    guild = link_guild()
    guild.g(MEM).slash(f"link {CODE}")
    guild.run(10)
    data = parse(guild.g(COLL).sv_text())
    with Spool(tmp_path / "s.db") as spool:
        res = spool.import_sv(data, "c1")
        assert res.links_new == 1
        assert spool.import_sv(data, "c1").links_new == 0
        (row,) = spool.pending_links("42")
        assert row["code"] == CODE and row["k"] == "link"
