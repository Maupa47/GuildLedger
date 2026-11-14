"""Daily coverage report and health warnings (#gl-ops). Synthetic data; fake Discord."""

import json
from datetime import datetime, timezone

import pytest

from guildledger import discord
from guildledger_bot.ops import Ops, build_report, day_bounds
from guildledger_bot.store import Archive

G = "100200300"
DAY = datetime(2026, 11, 12, tzinfo=timezone.utc)
D0 = int(DAY.timestamp())


class Fake:
    def __init__(self):
        self.sent = []

    def __call__(self, url, data, content_type="application/json"):
        self.sent.append(json.loads(data)["content"])
        return discord.Response(200, {}, b"{}")


def row(i, t, text=None, rb=None):
    r = {"id": f"{t}000000:{i}", "t": t, "s": "g", "a": "Alia Testwood", "g": "Player-1-A",
         "src": "live" if text else "meta"}
    if text:
        r["m"] = text
    if rb:
        r["rb"] = rb
    return r


@pytest.fixture
def archive(tmp_path):
    a = Archive(tmp_path / "a.db")
    rows = [row(i, D0 + 3600 + i * 60, f"line {i}") for i in range(10)]  # 01:00-01:09 with text
    rows += [row(100 + i, D0 + 2 * 3600 + i * 120, None) for i in range(30)]  # 02:00-02:58 no text
    rows += [row(200 + i, D0 + 4 * 3600 + i * 60, f"relayed {i}", rb="Mem Ber-Forever") for i in range(5)]
    events = [{"id": "join|Dara||1", "t": D0 + 5000, "p": True, "k": "join", "n": "Dara", "src": "sys"}]
    a.import_rows(G, "Synthetic Guild", rows, events, "Alpha")
    a.db.execute("INSERT INTO uploads VALUES(1, 'Alpha', 45, 'x', ?, 'ok', '')", (D0 + 6000,))
    a.db.commit()
    yield a
    a.close()


def test_report_content(archive):
    start, end = day_bounds(DAY, timezone.utc)
    text = build_report(archive, start, end, timezone.utc)
    assert "Thursday, 2026-11-12" in text
    assert "**45** lines · **33%** with text (15)" in text
    assert "filled by members: 5" in text and "without text: 30" in text
    assert "02:00–02:58 (30 lines)" in text
    assert "Roster: join 1" in text and "Uploads: Alpha 1 (45 rows)" in text


def test_report_once_a_day_after_the_hour(archive):
    fake = Fake()
    hook = discord.Webhook("https://discord.invalid/ops", "ops", fake, sleep=lambda s: None)
    now = [D0 + 86400 + 5 * 3600]  # 05:00 next day: too early
    ops = Ops(archive, hook, "UTC", report_hour=6, alert_after_hours=1e9, now=lambda: now[0])
    ops.tick()
    assert fake.sent == []
    now[0] += 3600  # 06:00
    ops.tick()
    ops.tick()
    assert len(fake.sent) == 1 and "2026-11-12" in fake.sent[0]


def test_warning_after_silence_and_note_when_uploads_resume(archive):
    fake = Fake()
    hook = discord.Webhook("https://discord.invalid/ops", "ops", fake, sleep=lambda s: None)
    now = [D0 + 6000 + 3 * 3600]
    ops = Ops(archive, hook, "UTC", report_hour=99, alert_after_hours=6, now=lambda: now[0])
    ops.tick()
    assert fake.sent == []  # 3 h: fine
    now[0] += 4 * 3600
    ops.tick()
    ops.tick()
    assert len(fake.sent) == 1 and "No upload for 7 h" in fake.sent[0]
    archive.db.execute("INSERT INTO uploads VALUES(2, 'Alpha', 3, 'y', ?, 'ok', '')", (now[0],))
    archive.db.commit()
    ops.tick()
    assert len(fake.sent) == 2 and "arriving again" in fake.sent[1]
    ops.tick()
    assert len(fake.sent) == 2


def test_no_webhook_means_silent(archive):
    Ops(archive, None, "UTC").tick()  # nothing to send to, nothing raised
