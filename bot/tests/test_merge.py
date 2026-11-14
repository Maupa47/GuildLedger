"""Phase 5: two collectors with overlapping data -> uploads -> bot archive -> every line/event once.
Synthetic data only; a fake transport stands in for Discord."""

import gzip
import json
from datetime import timezone

import pytest

from guildledger import discord
from guildledger.direct import Poster
from guildledger.store import Spool
from guildledger.upload import MAX_FILE, Uploader, build_file, describe
from guildledger_bot.store import Archive

G = "100200300"
T0 = 1794355200  # 2026-11-11 00:00 UTC
NOW = T0 + 86400  # long after: nothing is held back
ALIA = ("Alia Testwood", "Player-1111-0000AAAA")
BRAM = ("Bram Exampleson", "Player-1111-0000BBBB")
CORA = ("Cora Sample", "Player-1111-0000CCCC")


def multipart(body: bytes, content_type: str) -> tuple[str, bytes]:
    boundary = content_type.split("boundary=")[1].encode()
    parts = [p for p in body.split(b"--" + boundary) if p.strip(b"\r\n-")]
    content, data = None, None
    for p in parts:
        head, _, payload = p.partition(b"\r\n\r\n")
        payload = payload[:-2]  # trailing CRLF
        if b'name="payload_json"' in head:
            content = json.loads(payload)["content"]
        elif b'name="files[0]"' in head:
            data = payload
    return content, data


class FakeIngest:
    """Collects what the companion uploads, as messages in #gl-ingest."""

    def __init__(self):
        self.messages = []  # (message_id, content, data)

    def __call__(self, url, data, content_type="application/json"):
        content, file = multipart(data, content_type)
        self.messages.append((1000 + len(self.messages), content, file))
        return discord.Response(200, {}, b"{}")


class FakeLog:
    def __init__(self):
        self.chat, self.embeds = [], []

    def __call__(self, url, data, content_type="application/json"):
        p = json.loads(data)
        if "content" in p:
            self.chat.extend(line for line in p["content"].splitlines() if not line.startswith("**"))
        self.embeds.extend(p.get("embeds", []))
        return discord.Response(200, {}, b"{}")


def chat(pos, t, who, m=None, src=None):
    row = {"id": f"{t * 1000000:.0f}:{pos}", "t": t, "s": "g", "a": who[0], "g": who[1]}
    if m is not None:
        row["m"], row["src"] = m, src or "live"
    else:
        row["src"] = "meta"
    return row


def event_row(t, who, m):
    return {"id": f"ev|{t}|{who[0]}|deadbeef", "t": t, "s": "g", "a": who[0], "g": who[1], "m": m, "src": "event"}


def sv(chat_rows, events):
    return {"GuildLedgerDB": {"schema": 1, "guilds": {G: {"name": "Synthetic Guild", "chat": chat_rows,
                                                          "ev": events}}}}


# Collector A was online early, B later; they overlap in the middle.
A_CHAT = [chat(1, T0 + 10, ALIA, "hello"), chat(2, T0 + 20, BRAM, "anyone?"),
          chat(3, T0 + 30, CORA),  # A missed the text (lockdown)
          event_row(T0 + 41, ALIA, "lost its club partner on A")]
B_CHAT = [chat(1, T0 + 10, ALIA, "hello"), chat(3, T0 + 30, CORA, "B had this one"),
          chat(4, T0 + 40, ALIA),  # club row for A's event row, no text on B
          chat(5, T0 + 50, BRAM, "late joiner line")]
A_EV = [{"id": f"join|Dara Newcomer||{(T0 + 100) // 5}", "t": T0 + 100, "p": True, "k": "join",
         "n": "Dara Newcomer", "src": "sys"},
        {"id": "leave|Quiet Leaver||diff:1", "t": T0 + 7200, "w": T0, "p": False, "k": "leave",
         "n": "Quiet Leaver", "g": "Player-1111-0000EEEE", "src": "diff"}]
B_EV = [{"id": f"join|Dara Newcomer||{(T0 + 103) // 5}", "t": T0 + 103, "p": True, "k": "join",
         "n": "Dara Newcomer", "src": "sys"},  # same message, next 5 s bucket
        {"id": "leave|Quiet Leaver||diff:2", "t": T0 + 5400, "w": T0 + 1800, "p": False, "k": "leave",
         "n": "Quiet Leaver", "g": "Player-1111-0000EEEE", "src": "diff"}]


def collect(tmp_path, name, data):
    spool = Spool(tmp_path / f"{name}.db")
    spool.import_sv(data, name)
    return spool


def upload(spool, name, ingest):
    hook = discord.Webhook("https://discord.invalid/api/webhooks/9/ingest", "ingest", ingest, sleep=lambda s: None)
    return Uploader(spool, hook, name, now=lambda: NOW).run()


def post_all(archive, log=None):
    log = log or FakeLog()
    hooks = [discord.Webhook(f"https://discord.invalid/{r}", r, log, sleep=lambda s: None) for r in ("chat", "roster")]
    Poster(archive, *hooks, timezone.utc, now=lambda: NOW, hold_chat=600).run(since=T0)
    return log


@pytest.fixture
def setup(tmp_path):
    ingest = FakeIngest()
    a, b = collect(tmp_path, "Alpha", sv(A_CHAT, A_EV)), collect(tmp_path, "Bravo", sv(B_CHAT, B_EV))
    upload(a, "Alpha", ingest)
    upload(b, "Bravo", ingest)
    archive = Archive(tmp_path / "archive.db")
    return ingest, archive, (a, b)


def feed(archive, ingest, names=("Alpha", "Bravo")):
    out = []
    for (mid, content, data), name in zip(ingest.messages, names):
        out.append(archive.process_upload(mid, name, content, data))
    return out


def test_two_collectors_every_line_and_event_once(setup):
    ingest, archive, _ = setup
    assert [o.status for o in feed(archive, ingest)] == ["ok", "ok"]
    rows = archive.db.execute("SELECT id, author, text, first_collector FROM chat ORDER BY ts_utc").fetchall()
    assert [(r["author"], r["text"]) for r in rows] == [
        ("Alia Testwood", "hello"), ("Bram Exampleson", "anyone?"), ("Cora Sample", "B had this one"),
        ("Alia Testwood", "lost its club partner on A"), ("Bram Exampleson", "late joiner line")]
    assert rows[3]["id"] == f"{(T0 + 40) * 1000000:.0f}:4"  # the club ID won over the event row

    log = post_all(archive)
    assert [line.split(": ", 1)[1] for line in log.chat] == [
        "hello", "anyone?", "B had this one", "lost its club partner on A", "late joiner line"]
    descs = [e["description"] for e in log.embeds]
    assert descs == ["**Dara Newcomer** joined the guild", "**Quiet Leaver** left the guild"]
    leave = log.embeds[1]["fields"][0]["value"]
    assert leave == f"between <t:{T0 + 1800}:f> and <t:{T0 + 5400}:t>"  # both windows intersected

    again = post_all(archive)
    assert again.chat == [] and again.embeds == []


def test_same_upload_twice_and_restart_change_nothing(setup, tmp_path):
    ingest, archive, _ = setup
    feed(archive, ingest)
    post_all(archive)
    assert [o.status for o in feed(archive, ingest)] == ["seen", "seen"]
    archive.close()
    reopened = Archive(tmp_path / "archive.db")
    assert [o.status for o in feed(reopened, ingest)] == ["seen", "seen"]
    log = post_all(reopened)
    assert log.chat == [] and log.embeds == []
    assert reopened.last_ingest_id() == 1001


def test_reupload_of_the_same_rows_under_a_new_message_adds_nothing(setup):
    ingest, archive, (a, b) = setup
    feed(archive, ingest)
    post_all(archive)
    # Discord accepted an upload but the companion did not see the answer: it sends the rows again.
    for spool in (a, b):
        spool.db.execute("UPDATE chat SET uploaded=0")
        spool.db.execute("UPDATE events SET uploaded=0")
        spool.db.commit()
    n = len(ingest.messages)
    upload(a, "Alpha", ingest)
    upload(b, "Bravo", ingest)
    for (mid, content, data), name in zip(ingest.messages[n:], ("Alpha", "Bravo")):
        out = archive.process_upload(mid, name, content, data)
        assert out.status == "ok" and out.result.chat_new == 0 and out.result.events_new == 0
    log = post_all(archive)
    assert log.chat == [] and log.embeds == []


def test_changed_row_is_uploaded_again_and_fills_text(tmp_path):
    ingest = FakeIngest()
    a = collect(tmp_path, "Alpha", sv([chat(3, T0 + 30, CORA)], []))
    upload(a, "Alpha", ingest)
    a.import_sv(sv([chat(3, T0 + 30, CORA, "text arrived later")], []), "Alpha")  # same collector, later
    assert upload(a, "Alpha", ingest).rows == 1
    archive = Archive(tmp_path / "archive.db")
    for mid, content, data in ingest.messages:
        archive.process_upload(mid, "Alpha", content, data)
    assert archive.db.execute("SELECT text FROM chat").fetchone()[0] == "text arrived later"


@pytest.mark.parametrize("mangle,reason", [
    (lambda c, d: (c, d[:-5]), "sha256 does not match"),
    (lambda c, d: (c.replace(" 1 ", " 2 "), d), "row count"),
    (lambda c, d: ("hello there", d), "not a gl1 upload"),
    (lambda c, d: (c, None), "no attachment"),
])
def test_bad_uploads_are_rejected_with_a_reason(tmp_path, mangle, reason):
    data = build_file(G, "Synthetic Guild", "Alpha", [chat(1, T0, ALIA, "x")], [])
    content = describe("Alpha", 1, data)
    archive = Archive(tmp_path / "archive.db")
    c, d = mangle(content, data)
    out = archive.process_upload(77, "Alpha", c, d)
    assert out.status == "rejected" and reason in out.reason
    assert archive.db.execute("SELECT COUNT(*) FROM chat").fetchone()[0] == 0
    assert archive.process_upload(77, "Alpha", content, data).status == "seen"  # processed once


def test_not_gzip_rejected(tmp_path):
    data = b"plain text, not gzip"
    out = Archive(tmp_path / "a.db").process_upload(1, "Alpha", describe("Alpha", 0, data), data)
    assert out.status == "rejected" and "gzip" in out.reason


def test_rows_before_post_since_are_archived_not_posted(setup):
    ingest, archive, _ = setup
    feed(archive, ingest)
    log = FakeLog()
    hooks = [discord.Webhook(f"https://discord.invalid/{r}", r, log, sleep=lambda s: None) for r in ("chat", "roster")]
    res = Poster(archive, *hooks, timezone.utc, now=lambda: NOW, hold_chat=600).run(since=T0 + 45)
    assert [line.split(": ", 1)[1] for line in log.chat] == ["late joiner line"]
    assert res.skipped_backlog > 0
    assert archive.db.execute("SELECT COUNT(*) FROM chat").fetchone()[0] == 5


def test_chat_is_held_back_so_another_copy_can_add_text(tmp_path):
    ingest = FakeIngest()
    a = collect(tmp_path, "Alpha", sv([chat(3, T0 + 30, CORA)], []))
    upload(a, "Alpha", ingest)
    archive = Archive(tmp_path / "archive.db")
    archive.process_upload(*ingest.messages[0][:1], "Alpha", *ingest.messages[0][1:])
    log = FakeLog()
    hooks = [discord.Webhook(f"https://discord.invalid/{r}", r, log, sleep=lambda s: None) for r in ("chat", "roster")]
    p = Poster(archive, *hooks, timezone.utc, now=lambda: T0 + 60, hold_chat=600)
    p.run(since=T0)
    assert log.chat == []  # still within 10 minutes
    b = collect(tmp_path, "Bravo", sv([chat(3, T0 + 30, CORA, "B saw it live")], []))
    upload(b, "Bravo", ingest)
    archive.process_upload(*ingest.messages[1][:1], "Bravo", *ingest.messages[1][1:])
    p.now = lambda: T0 + 700
    p.run(since=T0)
    assert [line.split(": ", 1)[1] for line in log.chat] == ["B saw it live"]


def test_large_spool_is_split_under_the_size_limit(tmp_path):
    import random
    rnd = random.Random(1)
    rows = [chat(i, T0 + i, ALIA, "".join(rnd.choice("abcdefghijklmnopqrstuvwxyz ") for _ in range(200)))
            for i in range(12000)]
    ingest = FakeIngest()
    a = collect(tmp_path, "Alpha", sv(rows, []))
    res = upload(a, "Alpha", ingest)
    assert res.rows == 12000 and res.files > 1
    assert all(len(d) <= MAX_FILE for _, _, d in ingest.messages)
    archive = Archive(tmp_path / "archive.db")
    for mid, content, data in ingest.messages:
        assert archive.process_upload(mid, "Alpha", content, data).status == "ok"
    assert archive.db.execute("SELECT COUNT(*) FROM chat").fetchone()[0] == 12000
    first = gzip.decompress(ingest.messages[0][2]).decode().splitlines()[0]
    assert json.loads(first) == {"type": "guild", "guild": G, "name": "Synthetic Guild"}


def test_rows_direct_mode_already_posted_are_not_posted_again(tmp_path):
    """Switching a collector from direct to upload mode: what it already showed in Discord stays shown once."""
    from guildledger.direct import Poster as DirectPoster
    a = collect(tmp_path, "Alpha", sv([chat(1, T0 + 10, ALIA, "posted by direct mode")], [A_EV[0]]))
    direct_log = FakeLog()
    hooks = [discord.Webhook(f"https://discord.invalid/{r}", r, direct_log, sleep=lambda s: None)
             for r in ("chat", "roster")]
    DirectPoster(a, *hooks, timezone.utc, now=lambda: NOW).run(post_backlog=True)
    assert len(direct_log.chat) == 1 and len(direct_log.embeds) == 1
    a.import_sv(sv([chat(1, T0 + 10, ALIA, "posted by direct mode"), chat(2, T0 + 20, BRAM, "after the switch")],
                   [A_EV[0]]), "Alpha")
    ingest = FakeIngest()
    upload(a, "Alpha", ingest)
    archive = Archive(tmp_path / "archive.db")
    archive.process_upload(1, "Alpha", ingest.messages[0][1], ingest.messages[0][2])
    log = post_all(archive)  # since=T0: both rows are "new" to the bot by time
    assert [line.split(": ", 1)[1] for line in log.chat] == ["after the switch"]
    assert log.embeds == []


def roster_sv(at, members, chat_rows=()):
    data = sv(list(chat_rows), [])
    g = data["GuildLedgerDB"]["guilds"][G]
    g["rosterAt"] = at
    g["roster"] = {guid: dict(n=name, r=4, rn="Initiate", l=lvl, c="MAGE", fs=T0, ls=at)
                   for guid, name, lvl in members}
    return data


def test_member_list_reaches_the_bot_once_per_new_snapshot(tmp_path):
    ingest = FakeIngest()
    a = collect(tmp_path, "Alpha", roster_sv(T0 + 100, [("P-1", "Ann One", 10), ("P-2", "Bob Two", 20)]))
    upload(a, "Alpha", ingest)
    assert upload(a, "Alpha", ingest).files == 0  # nothing new: no second roster upload
    archive = Archive(tmp_path / "archive.db")
    for mid, content, data in ingest.messages:
        assert archive.process_upload(mid, "Alpha", content, data).status == "ok"
    rows = {r["name"]: r for r in archive.db.execute("SELECT * FROM members")}
    assert set(rows) == {"Ann One", "Bob Two"}
    assert rows["Bob Two"]["level"] == 20 and rows["Bob Two"]["rank_name"] == "Initiate"
    assert rows["Bob Two"]["class"] == "MAGE" and rows["Bob Two"]["in_guild"] == 1


def test_newest_snapshot_decides_who_is_in_the_guild(tmp_path):
    ingest = FakeIngest()
    old = collect(tmp_path, "Alpha", roster_sv(T0 + 100, [("P-1", "Ann One", 10), ("P-3", "Cat Three", 5)]))
    new = collect(tmp_path, "Bravo", roster_sv(T0 + 900, [("P-1", "Ann One", 11), ("P-2", "Bob Two", 20)]))
    upload(new, "Bravo", ingest)  # the newer snapshot arrives first
    upload(old, "Alpha", ingest)  # an older one from a collector who uploads late
    archive = Archive(tmp_path / "archive.db")
    for (mid, content, data), name in zip(ingest.messages, ("Bravo", "Alpha")):
        archive.process_upload(mid, name, content, data)
    rows = {r["name"]: r for r in archive.db.execute("SELECT * FROM members")}
    assert rows["Bob Two"]["in_guild"] == 1 and rows["Ann One"]["in_guild"] == 1
    assert rows["Ann One"]["level"] == 11  # the old snapshot does not overwrite newer details
    assert rows["Cat Three"]["in_guild"] == 0  # known from the old list, but gone in the newest
