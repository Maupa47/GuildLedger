"""Loot outside the game (shared/schema.md 7): two collectors upload Amazing Hub's data -> the bot archives each
row once, posts loot / points / a raid summary once, and answers the /dkp /loot /wish queries.
Synthetic data only; fake transports stand in for Discord."""

import gzip
import json
import sys
from pathlib import Path

from guildledger import discord, loot as gl_loot
from guildledger.store import Spool
from guildledger.svparse import parse, parse_file
from guildledger.upload import Uploader, describe
from guildledger_bot.collection import loot
from guildledger_bot.store import Archive

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "companion" / "tests"))
from hub_fixture import FIX, T0, hub_lua  # noqa: E402

from test_merge import FakeIngest, FakeLog  # noqa: E402

G = "100200300"


def collector_upload(tmp_path, name, shift):
    s = Spool(tmp_path / f"{name}.db")
    s.import_sv(parse_file(str(FIX / "basic.lua")), name)
    gl_loot.import_hub(s.db, parse(hub_lua(shift=shift)), s.guild_names(), name, T0 + 5000 + shift)
    ingest = FakeIngest()
    Uploader(s, discord.Webhook("https://x/ingest", "ingest", ingest), name).run()
    return s, ingest.messages


def archive_with_two_collectors(tmp_path):
    a = Archive(tmp_path / "bot.db")
    mid = 1
    for name, shift in (("Testa Collector", 0), ("Second Officer", 2)):
        _, msgs = collector_upload(tmp_path, name.replace(" ", ""), shift)
        for _, content, data in msgs:
            out = a.process_upload(mid, name, content, data)
            assert out.status == "ok", out.reason
            mid += 1
    return a


def count(a, table):
    return a.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_two_collectors_give_every_row_once(tmp_path):
    a = archive_with_two_collectors(tmp_path)
    assert count(a, "points") == 3
    assert count(a, "loot") == 1  # the same award, stamped 2 s apart by the two officers
    assert count(a, "raids") == 1  # the same raid night
    assert count(a, "standings") == 3 and count(a, "wishlists") == 1
    raid = a.db.execute("SELECT * FROM raids").fetchone()
    assert json.loads(raid["bosses"])[0]["name"] == "Ragnaros" and len(json.loads(raid["players"])) == 2


def test_an_unknown_row_type_is_ignored_not_rejected(tmp_path):
    a = Archive(tmp_path / "bot.db")
    lines = [{"type": "guild", "guild": G, "name": "Synthetic Guild"},
             {"type": "future-thing", "guild": G, "x": 1},
             {"type": "points", "guild": G, "id": "p1", "pool": "", "t": T0, "member": "alia testwood",
              "name": "Alia Testwood", "delta": 5, "kind": "adjust", "reason": "", "by": "Testa Officer"}]
    data = gzip.compress(("\n".join(json.dumps(x) for x in lines) + "\n").encode(), mtime=0)
    out = a.process_upload(7, "Testa Collector", describe("Testa Collector", 2, data), data)
    assert out.status == "ok" and count(a, "points") == 1


def test_loot_posts_lines_and_one_raid_summary_once(tmp_path):
    a = archive_with_two_collectors(tmp_path)
    assert "Alia Testwood" in loot.display_names(a.db, G)  # from the roster in basic.lua
    fake = FakeLog()
    p = loot.LootPoster(a.db, discord.Webhook("https://x/loot", "loot", fake), None, hold=600, now=lambda: T0 + 99999)
    n = p.run(since=0)
    assert n >= 4
    text = "\n".join(fake.chat)
    assert "**Alia Testwood** got **[Thunderfury]** (Molten Core)" in text
    assert "**+10** Boss kill: Ragnaros by Testa Officer: Alia Testwood, Bram Exampleson" in text
    assert "**-30**" in text
    assert len(fake.embeds) == 1
    e = fake.embeds[0]
    assert e["title"] == "Raid: Molten Core"
    fields = {f["name"]: f["value"] for f in e["fields"]}
    assert fields["Bosses killed (1)"] == "Ragnaros"
    assert "Alia Testwood" in fields["Attendance (2)"]  # shown by the guild member's name, not "Name-Realm"
    assert "Thunderfury" in fields["Loot (1)"]
    assert fields["Standings (top 2)"].startswith("1. Bram Exampleson: 90")
    assert p.run(since=0) == 0 and len(fake.embeds) == 1  # nothing twice


def test_old_rows_are_archived_not_posted_and_recent_rows_wait(tmp_path):
    a = archive_with_two_collectors(tmp_path)
    fake = FakeLog()
    p = loot.LootPoster(a.db, discord.Webhook("https://x/loot", "loot", fake), None, hold=600, now=lambda: T0 + 1000)
    p.run(since=T0 + 700)  # bot started after the boss kill: those points are history
    assert not any("Boss kill" in line for line in fake.chat)
    assert not fake.embeds  # the raid ended at +3600, still inside the hold
    assert any("Thunderfury" in line for line in fake.chat) is False  # +890 > now - hold


def test_queries_and_discord_wishes(tmp_path):
    a = archive_with_two_collectors(tmp_path)
    g = loot.main_guild(a.db)
    assert g == G
    top = loot.standings(a.db, g)
    assert [r["name"] for r in top] == ["Bram Exampleson", "Alia Testwood"]
    assert loot.standings(a.db, g, "Core A")[0]["name"] == "Cora Sample"
    assert loot.standings(a.db, g, "", "alia TESTWOOD")[0]["current"] == 60
    assert loot.recent_loot(a.db, g, "Alia Testwood")[0]["item_name"] == "Thunderfury"
    assert loot.resolve_item(a.db, g, "thunderfury")[:2] == (19019, "Thunderfury")
    assert loot.resolve_item(a.db, g, "https://www.wowhead.com/classic/item=18832/brutality-blade")[0] == 18832
    assert loot.resolve_item(a.db, g, "no such thing")[0] is None
    assert loot.wish_add(a.db, g, "Alia Testwood", 18832, "Item 18832", False, 42)
    assert not loot.wish_add(a.db, g, "alia testwood", 18832, "Item 18832", False, 42)  # already there
    assert loot.wish_add(a.db, g, "Alia Testwood", 19019, None, True, 42)
    assert loot.wish_export(a.db, g, "Alia Testwood") == "GLW1:Alia Testwood:18832,19019o"
    w = loot.wishlist(a.db, g, "Bram Exampleson")
    assert [i["item"] for i in w["game"]] == [19019, 18832] and w["discord"] == []
    assert loot.wish_remove(a.db, g, "Alia Testwood", 18832) == 1
    assert loot.wish_remove(a.db, g, "Alia Testwood", None) == 1
    assert loot.wish_export(a.db, g, "Alia Testwood") is None


def test_bot_config_reads_the_loot_section(tmp_path):
    from guildledger_bot import config
    f = tmp_path / "c.toml"
    f.write_text('[discord]\ntoken = "t"\ningest_channel_id = 1\n[collectors]\n5 = "A"\n[post]\nchat_webhook = "https://x"\n'
                 '[loot]\nwebhook = "https://y"\nhold_seconds = 60\nstandings_top = 5\n', encoding="utf-8")
    c = config.load(f)
    assert c.loot_webhook == "https://y" and c.loot_hold == 60 and c.loot_top == 5


def test_catalog_names_and_search():
    """Phase C: the generated catalogue (shared/catalog/items.json) gives names and /wish add suggestions."""
    from guildledger_bot import catalog
    items = catalog.items()
    assert len(items) > 1000, "shared/catalog/items.json is in the repository"
    some = next(iter(items.values()))
    assert catalog.name_of(some["id"]) == some["name"]
    hits = catalog.search_items(some["name"][:4])
    assert hits and len(hits) <= 25 and all(some["name"][:4].lower() in h["name"].lower() for h in hits)
    assert catalog.search_items("x") == [] and len(catalog.label(some)) <= 100
    assert catalog.recipes() and {"spell", "name", "profession", "materials"} <= set(catalog.recipes()[0])
