"""Professions in Discord (PLAN_COMMUNITY D4): the profession forum's posts and /craft, from synthetic hub data
and the real recipe catalogue (shared/catalog). No Discord."""

import sys
from pathlib import Path

from guildledger import hubdata
from guildledger.svparse import parse, parse_file
from guildledger_bot.community import crafts
from guildledger_bot.store import Archive

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "companion" / "tests"))
from hub_fixture import FIX  # noqa: E402
from test_hubdata import hubdata_lua  # noqa: E402


def archive(tmp_path):
    a = Archive(tmp_path / "bot.db")
    a.import_sv(parse_file(str(FIX / "basic.lua")), "Testa Collector")   # the roster: who is in the guild
    hubdata.import_hub(a.db, parse(hubdata_lua()), a.guild_names(), "Testa Collector")
    return a


def test_one_post_per_profession_with_crafters_and_recipes(tmp_path):
    a = archive(tmp_path)
    forum = crafts.CraftForum(a)
    posts = {(p.kind, p.key): p for p in forum.wanted()}
    assert ("help", "help") in posts
    tailoring = posts[("prof", "197")]
    assert tailoring.title == "Tailoring"
    text = "\n".join(tailoring.messages)
    assert "**Alia Testwood** · 150/225" in text
    assert "Linen Cloak - Alia Testwood" in text and "Brown Linen Shirt - Alia Testwood" in text
    assert text.index("Brown Linen Shirt") < text.index("Linen Cloak") < text.index("Red Linen Robe")
    assert "no addon: skill unknown" in "\n".join(posts[("prof", "164")].messages)   # Bram: native record
    assert posts[("prof", "186")].title == "Mining"
    # a write round creates every post; the same data again writes nothing
    writes = forum.plan(list(posts.values()), limit=50)
    assert {w.action for w in writes} == {"create"} and len(writes) == len(posts)
    for w in writes:
        forum.done(w, 1, [1])
    assert forum.plan(forum.wanted(), limit=50) == []
    assert forum.plan(crafts.CraftForum(a).wanted(), limit=50) == []   # the directory's table is not touched
    assert a.db.execute("SELECT COUNT(*) FROM craft_posts").fetchone()[0] == len(posts)   # its own table


def test_craft_search_and_answer(tmp_path):
    a = archive(tmp_path)
    hits = crafts.search(a.db, "linen cl")
    assert hits and hits[0][1] == 2387 and "known in the guild" in hits[0][0]
    assert crafts.search(a.db, "l") == []
    assert crafts.resolve(a.db, "2387") == 2387 and crafts.resolve(a.db, "Linen Cloak") == 2387
    text = crafts.answer(a.db, 2387)
    assert text.startswith("**Linen Cloak** (Tailoring") and "Materials:" in text and "Alia Testwood" in text
    nobody = crafts.answer(a.db, 2385)   # a tailoring recipe nobody here knows
    assert "Nobody in the guild has this recipe" in nobody
    assert crafts.recipe_name(999999999) == "#999999999"
