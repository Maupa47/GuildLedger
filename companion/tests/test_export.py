from datetime import timezone

from guildledger.export import export, guild_dir_name
from guildledger.svparse import parse_file
from guildledger.wowtext import plain


def test_plain_text():
    s = "|cff0070dd|Hitem:2140::::::::20:::::|h[Carving Knife]|h|r and |TInterface\\Icons\\x:0|t|A:atlas:0:0|a done"
    assert plain(s) == "[Carving Knife] and  done"
    assert plain("a || b") == "a | b"
    assert plain("|cnIQ4:epic|r") == "epic"
    assert plain("|Kw12|k") == "(protected text)"
    assert plain(None) == ""


def test_guild_dir_name():
    assert guild_dir_name("Synthetic Guild", "1") == "Synthetic Guild"
    assert guild_dir_name("a/b:c", "1") == "a_b_c"
    assert guild_dir_name("..", "42") == "42"


def test_export_files(spool, fixtures, tmp_path):
    spool.import_sv(parse_file(str(fixtures / "basic.lua")), "c1")
    files = export(spool, tmp_path, timezone.utc)
    names = sorted(p.name for p in files)
    assert names == ["chat-2026-11-11.log", "roster-2026.log"]

    chat = (tmp_path / "Synthetic Guild" / "chat-2026-11-11.log").read_text(encoding="utf-8").splitlines()
    assert chat == [
        "[2026-11-11 18:00:00] [G] Alia Testwood: hello guild",
        "[2026-11-11 18:00:10] [G] Bram Exampleson: anyone got [Carving Knife]? (edited)",
        "[2026-11-11 18:00:20] [G] Cora Sample: this line lost its club partner",
        "[2026-11-11 18:00:30] [O] Alia Testwood: officer note: @everyone check bank",
        "[2026-11-11 18:00:40] [G Discord] DiscordUser: hi from discord",
        "[2026-11-11 18:00:50] [G] Bram Exampleson: (text not captured) (deleted)",
    ]

    roster = (tmp_path / "Synthetic Guild" / "roster-2026.log").read_text(encoding="utf-8").splitlines()
    assert roster == [  # the diff row is superseded by the log row and not exported
        "[2026-11-11 15:00:00] LEAVE Dax Gone (approx., log)",
        "[2026-11-11 15:13:20] JOIN Cora Sample",
        "[2026-11-11 18:00:50] KICK Eli Rowdy by Alia Testwood",
        "[2026-11-11 18:00:55] PROMOTE Bram Exampleson by Alia Testwood -> Member",
    ]


def test_export_is_idempotent(spool, fixtures, tmp_path):
    spool.import_sv(parse_file(str(fixtures / "basic.lua")), "c1")
    export(spool, tmp_path, timezone.utc)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.log")}
    export(spool, tmp_path, timezone.utc)
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*.log")}


def test_export_uses_timezone(spool, fixtures, tmp_path):
    from datetime import timedelta

    spool.import_sv(parse_file(str(fixtures / "basic.lua")), "c1")
    export(spool, tmp_path, timezone(timedelta(hours=7)))
    # 18:00 UTC + 7 h crosses midnight
    assert (tmp_path / "Synthetic Guild" / "chat-2026-11-12.log").exists()
