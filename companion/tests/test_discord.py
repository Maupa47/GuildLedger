"""Phase 4: direct Discord posting. A fake transport stands in for Discord; no network."""

import json
import zlib
from datetime import timezone

import pytest

from guildledger import discord
from guildledger.direct import HOLD_EVENTS, Poster
from guildledger.store import Spool

G = "100200300"
T0 = 1794355200  # 2026-11-11 00:00 UTC
URL_CHAT = "https://discord.invalid/api/webhooks/1/secret-chat"
URL_ROSTER = "https://discord.invalid/api/webhooks/2/secret-roster"


class FakeDiscord:
    def __init__(self):
        self.sent = []  # (role, payload)
        self.script = []  # responses to hand out first: (status, headers, body)

    def __call__(self, url, data, content_type="application/json"):
        assert "wait=true" in url
        role = "chat" if "secret-chat" in url else "roster"
        if self.script:
            status, headers, body = self.script.pop(0)
            if status != 200:
                return discord.Response(status, headers, body)
        self.sent.append((role, json.loads(data) if content_type == "application/json" else data))
        return discord.Response(200, {}, b"{}")

    def contents(self):
        return [p["content"] for r, p in self.sent if r == "chat"]

    def embeds(self):
        return [e for r, p in self.sent if r == "roster" for e in p["embeds"]]


def chat(i, t, m="hello", a="Alia Testwood", s="g", src=None, **kw):
    row = {"id": f"{t * 1000000:.0f}:{i}", "t": t, "s": s, "a": a, "g": f"Player-1111-{zlib.crc32(a.encode()) % 10**8:08d}",
           "src": src or "live"}
    if m is not None:
        row["m"] = m
    else:
        row["src"] = src or "meta"
    row.update(kw)
    return row


def sv(chat_rows=(), events=()):
    return {"GuildLedgerDB": {"schema": 1, "guilds": {G: {"name": "Synthetic Guild", "chat": list(chat_rows),
                                                          "ev": list(events)}}}}


def poster(spool, fake, meta="summary", now=None):
    return Poster(spool, discord.Webhook(URL_CHAT, "chat", fake, sleep=lambda s: None),
                  discord.Webhook(URL_ROSTER, "roster", fake, sleep=lambda s: None),
                  timezone.utc, meta, now=now or (lambda: T0 + 10 * 86400))


@pytest.fixture
def fake():
    return FakeDiscord()


def test_first_run_skips_backlog_then_posts_new_rows_once(spool, fake):
    spool.import_sv(sv([chat(1, T0, "old line")]), "c1")
    res = poster(spool, fake).run()
    assert res.skipped_backlog == 1 and fake.sent == []
    spool.import_sv(sv([chat(1, T0, "old line"), chat(2, T0 + 60, "new line")]), "c1")
    poster(spool, fake).run()
    poster(spool, fake).run()  # restart: nothing twice
    assert len(fake.sent) == 1
    assert fake.contents() == ["`00:01` **Alia Testwood**: new line"]


def test_post_backlog_posts_everything_in_order_with_date_lines(spool, fake):
    rows = [chat(3, T0 + 86400, "next day"), chat(1, T0, "first"), chat(2, T0 + 5, "second")]
    spool.import_sv(sv(rows), "c1")
    poster(spool, fake).run(post_backlog=True)
    (msg,) = fake.contents()
    assert msg.splitlines() == [
        "**── Wednesday, 2026-11-11 ──**",
        "`00:00` **Alia Testwood**: first",
        "`00:00` **Alia Testwood**: second",
        "**── Thursday, 2026-11-12 ──**",
        "`00:00` **Alia Testwood**: next day",
    ]
    payload = fake.sent[0][1]
    assert payload["allowed_mentions"] == {"parse": []} and payload["flags"] == discord.SUPPRESS_EMBEDS


def test_escaping_mentions_links_and_markup(spool, fake):
    nasty = ("@everyone look |cff0070dd|Hitem:2140::|h[Carving Knife]|h|r **bold** <@123> "
             "|TInterface\\icon:0|t ||pipe `code` > quote [x](https://evil.example)")
    spool.import_sv(sv([chat(1, T0, nasty, a="Under_Score*Name")]), "c1")
    poster(spool, fake).run(post_backlog=True)
    line = fake.contents()[0].splitlines()[1]
    assert "@​everyone" in line and "@everyone" not in line
    assert "\\[Carving Knife\\]" in line and "Hitem" not in line and "|cff" not in line and "|T" not in line
    assert "\\*\\*bold\\*\\*" in line and "\\<@123" in line and "\\|pipe" in line and "\\`code\\`" in line
    assert "\\[x\\](https://evil.example)" in line
    assert "**Under\\_Score\\*Name**" in line


def test_messages_stay_under_the_limit(spool, fake):
    rows = [chat(i, T0 + i, "x" * 300) for i in range(40)]
    spool.import_sv(sv(rows), "c1")
    poster(spool, fake).run(post_backlog=True)
    assert len(fake.contents()) > 1
    assert all(len(c) <= discord.MAX_CONTENT for c in fake.contents())
    assert sum(c.count("**Alia Testwood**") for c in fake.contents()) == 40
    long = chat(99, T0 + 999, "y" * 5000)
    spool.import_sv(sv([long]), "c1")
    poster(spool, fake).run()
    assert len(fake.contents()[-1]) <= discord.MAX_CONTENT and fake.contents()[-1].endswith("…")


def test_markers_for_officer_discord_edited_deleted(spool, fake):
    rows = [chat(1, T0, "secret plans", s="o"), chat(2, T0 + 1, "from my phone", fd=True),
            chat(3, T0 + 2, "typo", ed=True), chat(4, T0 + 3, "oops", **{"del": True})]
    spool.import_sv(sv(rows), "c1")
    poster(spool, fake).run(post_backlog=True)
    lines = fake.contents()[0].splitlines()[1:]
    assert lines[0].startswith("`00:00` `[Officer]` **Alia Testwood**")
    assert "**Alia Testwood** *(Discord)*: from my phone" in lines[1]
    assert lines[2].endswith("*(edited)*") and lines[3].endswith("*(deleted)*")


@pytest.mark.parametrize("mode", ["summary", "lines", "skip"])
def test_rows_without_text(spool, fake, mode):
    rows = [chat(1, T0, "before")]
    rows += [chat(10 + i, T0 + 3600 + i * 60, None, a=f"Member{i % 3}") for i in range(30)]
    rows += [chat(2, T0 + 7200, "after")]
    spool.import_sv(sv(rows), "c1")
    poster(spool, fake, meta=mode).run(post_backlog=True)
    text = "\n".join(fake.contents())
    if mode == "summary":
        assert "`01:00–01:29` *30 messages from 3 members — text not captured*" in text
        assert text.count("text not captured") == 1
    elif mode == "lines":
        assert text.count("*(text not captured)*") == 30
    else:
        assert "not captured" not in text and "before" in text and "after" in text
    unposted = spool.db.execute("SELECT COUNT(*) FROM chat WHERE posted=0").fetchone()[0]
    assert unposted == 0


def test_late_rows_get_their_own_block(spool, fake):
    spool.import_sv(sv([chat(5, T0 + 600, "newer")]), "c1")
    poster(spool, fake).run(post_backlog=True)
    spool.import_sv(sv([chat(1, T0, "older, from another session")]), "c1")
    poster(spool, fake).run()
    late = fake.contents()[-1].splitlines()
    assert late[0].startswith("**Late entries**")
    assert late[1] == "`2026-11-11 00:00` **Alia Testwood**: older, from another session"


def test_rate_limit_is_honoured_and_failures_resume(spool, fake):
    spool.import_sv(sv([chat(1, T0, "a")]), "c1")
    fake.script = [(429, {}, b'{"retry_after": 0.5}')]
    slept = []
    p = Poster(spool, discord.Webhook(URL_CHAT, "chat", fake, sleep=slept.append), None, timezone.utc)
    p.run(post_backlog=True)
    assert slept == [0.5] and len(fake.contents()) == 1

    spool.import_sv(sv([chat(2, T0 + 1, "b")]), "c1")
    fake.script = [(404, {}, b'{"message": "Unknown Webhook"}')]
    with pytest.raises(discord.WebhookError) as e:
        p.run()
    assert "Unknown Webhook" in str(e.value) and "secret" not in str(e.value)
    assert spool.db.execute("SELECT posted FROM chat WHERE text='b'").fetchone()[0] == 0
    p.run()  # webhook fixed: the row goes out now, once
    assert fake.contents()[-1].endswith(": b") and len(fake.contents()) == 2


def test_webhook_never_shows_its_url():
    w = discord.Webhook(URL_CHAT, "chat", FakeDiscord())
    assert "secret" not in repr(w)
    with pytest.raises(discord.WebhookError) as e:
        discord.Webhook("", "roster")
    assert "roster webhook is not set" in str(e.value)


def ev(k, n, t, src="sys", **kw):
    row = {"id": f"{k}|{n}|{kw.get('by', '')}|{src}:{t}", "t": t, "p": src == "sys", "k": k, "n": n, "src": src}
    row.update(kw)
    return row


def test_roster_embeds(spool, fake):
    events = [ev("join", "Dara Newcomer", T0), ev("kick", "Bad Actor", T0 + 10, by="Ola Officer"),
              ev("promote", "Dara Newcomer", T0 + 20, by="Ola Officer", d="Member"),
              ev("leave", "Quiet Leaver", T0 + 3600, src="diff", w=T0 + 60)]
    spool.import_sv(sv(events=events), "c1")
    poster(spool, fake).run(post_backlog=True)
    e = fake.embeds()
    assert [x["description"] for x in e] == ["**Dara Newcomer** joined the guild", "**Bad Actor** was kicked",
                                             "**Dara Newcomer** was promoted", "**Quiet Leaver** left the guild"]
    assert e[0]["color"] == discord.GREEN and e[1]["color"] == discord.RED and e[3]["color"] == discord.GREY
    assert e[0]["fields"][0]["value"] == f"<t:{T0}:f>"
    assert {"name": "By", "value": "Ola Officer", "inline": True} in e[1]["fields"]
    assert {"name": "Rank", "value": "Member", "inline": True} in e[2]["fields"]
    assert e[3]["fields"][0]["value"] == f"between <t:{T0 + 60}:f> and <t:{T0 + 3600}:t>"
    assert "roster comparison" in e[3]["footer"]["text"]
    assert all(p["allowed_mentions"] == {"parse": []} for _, p in fake.sent)


def test_same_time_events_keep_log_order(spool, fake):
    events = [ev("kick", "Emma Example", T0, src="log", by="Ola Officer", w=T0 - 3600),
              ev("join", "Emma Example", T0, src="log", w=T0 - 3600)]
    spool.import_sv(sv(events=events), "c1")
    poster(spool, fake).run(post_backlog=True)
    assert [x["description"] for x in fake.embeds()] == ["**Emma Example** was kicked",
                                                         "**Emma Example** joined the guild"]


def test_superseded_never_posted_and_diff_waits(spool, fake):
    now = T0 + 10 * 86400
    events = [ev("leave", "Gone Person", now - 100, src="diff", w=now - 4000),
              ev("kick", "Gone Person", now - 1800, src="log", by="Ola Officer", w=now - 5400),
              ev("join", "Fresh Face", now - 100, src="diff", w=now - 4000)]
    spool.import_sv(sv(events=events), "c1")
    p = poster(spool, fake, now=lambda: now)
    p.run(post_backlog=True)
    assert [x["description"] for x in fake.embeds()] == ["**Gone Person** was kicked"]  # diff leave superseded
    p.now = lambda: now + HOLD_EVENTS
    p.run()
    assert [x["description"] for x in fake.embeds()][-1] == "**Fresh Face** joined the guild"
    assert len(fake.embeds()) == 2


def test_cli_post_uses_config(tmp_path, fixtures, monkeypatch, caplog):
    import shutil

    from guildledger import __main__ as cli
    sv_file = tmp_path / "GuildLedger.lua"
    shutil.copy(fixtures / "basic.lua", sv_file)
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'sv_path = "{sv_file.as_posix()}"\ntimezone = "UTC"\nmode = "direct"\n'
                   f'[direct]\nchat_webhook = "{URL_CHAT}"\nroster_webhook = "{URL_ROSTER}"\n', encoding="utf-8")
    fake = FakeDiscord()
    monkeypatch.setattr(discord, "urllib_transport", fake)
    monkeypatch.setattr(discord.Webhook.__init__, "__defaults__", (fake, discord.time.sleep))
    caplog.set_level("INFO")
    assert cli.main(["--config", str(cfg), "import", str(sv_file), "--no-export"]) == 0
    assert cli.main(["--config", str(cfg), "post", "--post-backlog"]) == 0
    assert fake.contents() and fake.embeds()
    assert cli.main(["--config", str(cfg), "post"]) == 0
    n = len(fake.sent)
    assert cli.main(["--config", str(cfg), "post"]) == 0 and len(fake.sent) == n
    assert "secret" not in caplog.text


def test_cli_dry_run_sends_nothing_and_marks_nothing(tmp_path, fixtures, capsys):
    import shutil

    from guildledger import __main__ as cli
    sv_file = tmp_path / "GuildLedger.lua"
    shutil.copy(fixtures / "basic.lua", sv_file)
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'sv_path = "{sv_file.as_posix()}"\ntimezone = "UTC"\nmode = "direct"\n'
                   f'[direct]\nchat_webhook = "{URL_CHAT}"\nroster_webhook = "{URL_ROSTER}"\n', encoding="utf-8")
    assert cli.main(["--config", str(cfg), "import", str(sv_file), "--no-export"]) == 0
    assert cli.main(["--config", str(cfg), "post", "--dry-run", "--post-backlog"]) == 0
    out = capsys.readouterr().out
    assert "[chat]" in out and "Alia Testwood" in out and "[roster]" in out and "secret" not in out
    with Spool(tmp_path / "spool.db") as spool:
        assert spool.db.execute("SELECT SUM(posted) FROM chat").fetchone()[0] == 0
        assert spool.get_state(f"direct_init:{G}") is None
