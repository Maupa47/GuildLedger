"""Loot outside the game (shared/schema.md 7): reading Amazing Hub's AmazingHub.lua into the spool.
Synthetic data only."""


from guildledger import loot
from guildledger.store import Spool
from guildledger.svparse import parse, parse_file
from hub_fixture import FIX, T0, hub_lua


def spool_with_guild(tmp_path, name="s.db"):
    s = Spool(tmp_path / name)
    s.import_sv(parse_file(str(FIX / "basic.lua")), "Testa Collector")
    return s


def test_hub_rows_carry_points_standings_loot_wishlists_raids(tmp_path):
    rows = loot.rows_from_hub(loot.hub_guilds(parse(hub_lua()))["Synthetic Guild-Forever"], seen=T0 + 5000)
    assert len(rows["points"]) == 3 and {r["member"] for r in rows["points"]} == {"alia testwood", "bram exampleson"}
    assert {(r["pool"], r["name"], r["cur"]) for r in rows["standing"]} == {
        ("", "Alia Testwood", 60), ("", "Bram Exampleson", 90), ("Core A", "Cora Sample", 12)}
    assert rows["loot"][0]["item"] == 19019 and rows["loot"][0]["item_name"] == "Thunderfury"
    assert [i["item"] for i in rows["wishlist"][0]["items"]] == [19019, 18832]
    assert rows["wishlist"][0]["items"][1]["off"] is True
    raid = rows["raid"][0]
    assert raid["name"] == "Molten Core" and raid["bosses"][0]["name"] == "Ragnaros" and len(raid["players"]) == 2


def test_import_twice_adds_nothing_and_unchanged_rows_are_not_uploaded_again(tmp_path):
    s = spool_with_guild(tmp_path)
    data = parse(hub_lua())
    first = loot.import_hub(s.db, data, s.guild_names(), "Testa Collector", T0 + 5000)
    assert first.points_new == 3 and first.loot_new == 1 and first.raids_new == 1 and first.wishlists == 1
    assert first.standings == 3
    g = "100200300"
    loot.mark_uploaded(s.db, g, loot.pending(s.db, g))
    again = loot.import_hub(s.db, data, s.guild_names(), "Testa Collector", T0 + 6000)  # a later /reload
    assert again.changed == 0
    assert loot.pending(s.db, g) == []
    changed = loot.import_hub(s.db, parse(hub_lua(alia_points=75, wish=(19019,))), s.guild_names(), "Testa Collector",
                              T0 + 7000)
    assert changed.standings == 1 and changed.wishlists == 1
    kinds = sorted(k for k, _ in loot.pending(s.db, g))
    assert kinds == ["standing", "wishlist"]


def test_unknown_guild_and_noguild_are_skipped(tmp_path):
    s = Spool(tmp_path / "empty.db")  # no GuildLedger guild known yet
    res = loot.import_hub(s.db, parse(hub_lua()), s.guild_names(), "x", T0)
    assert res.changed == 0


def test_companion_import_command_reads_a_hub_file(tmp_path):
    from guildledger.__main__ import main
    cfg = tmp_path / "config.toml"
    cfg.write_text('[general]\nmode = "upload"\n', encoding="utf-8")
    (tmp_path / "AmazingHub.lua").write_text(hub_lua(), encoding="utf-8")
    assert main(["--config", str(cfg), "import", str(FIX / "basic.lua"), "--no-export"]) == 0
    assert main(["--config", str(cfg), "import", str(tmp_path / "AmazingHub.lua")]) == 0
    with Spool(tmp_path / "spool.db") as s:
        assert s.db.execute("SELECT COUNT(*) FROM points").fetchone()[0] == 3


def test_config_hub_path_defaults_next_to_the_guildledger_file(tmp_path):
    from guildledger import config
    cfg = tmp_path / "config.toml"
    cfg.write_text("sv_path = 'C:/WoW/WTF/Account/X/SavedVariables/GuildLedger.lua'\n", encoding="utf-8")
    c = config.load(cfg)
    assert c.loot and c.hub_path.name == "AmazingHub.lua" and c.hub_path.parent == c.sv_path.parent
    cfg.write_text("sv_path = 'C:/a/GuildLedger.lua'\n[loot]\nenabled = false\nhub_sv_path = 'D:/b/AmazingHub.lua'\n",
                   encoding="utf-8")
    c = config.load(cfg)
    assert not c.loot and str(c.hub_path).replace("\\", "/") == "D:/b/AmazingHub.lua"
