import math

import pytest

from guildledger.svparse import SVParseError, as_dict, as_list, parse, parse_file


@pytest.fixture
def tricky(fixtures):
    return parse_file(str(fixtures / "tricky_strings.lua"))


def test_top_level_names(tricky):
    assert set(tricky) == {"TrickyDB", "SecondVar"}
    assert tricky["SecondVar"] == 7


@pytest.mark.parametrize("key,expected", [
    ("quote", 'she said "hi"'),
    ("backslash", "C:\\Games\\WoW"),
    ("newline", "line1\nline2"),
    ("decimal", "Mädchen"),
    ("raw_utf8", "Testmagø 🙂"),
    ("brackets", "not a long string ]] [[ nope"),
    ("link", "|cffa335ee|Hitem:19019::::::::60:::::|h[Thunderfury, Blessed Blade of the Windseeker]|h|r"),
    ("single", "single 'quoted'"),
    ("tab", "a\tb"),
    ("pipes", "a || b"),
])
def test_strings(tricky, key, expected):
    assert tricky["TrickyDB"][key] == expected


def test_numbers_and_bools(tricky):
    t = tricky["TrickyDB"]
    assert t["neg"] == -42
    assert t["float"] == 3.25
    assert t["exp"] == 1794422681300000 and isinstance(t["exp"], int)
    assert math.isclose(t["negexp"], -0.0015)
    assert t["yes"] is True and t["no"] is False
    assert "gone" not in t


def test_tables(tricky):
    t = tricky["TrickyDB"]
    assert t["list"] == ["a", "b", "c"]
    assert t["sparse"] == {1: "x", 3: "z"}
    assert as_list(t["sparse"]) == ["x", "z"]
    assert t["mixed"] == {1: "pos1", "k": "v"}
    assert t["empty"] == {} and as_list(t["empty"]) == [] and as_dict(t["empty"]) == {}
    assert t["nested"]["deeper"]["deepest"] == [1, 2]


def test_str_input_matches_bytes_input(fixtures):
    raw = (fixtures / "tricky_strings.lua").read_bytes()
    assert parse(raw) == parse(raw.decode("utf-8"))


def test_bom_and_crlf():
    assert parse(b'\xef\xbb\xbfX = {\r\n["a"] = "b",\r\n}\r\n') == {"X": {"a": "b"}}


def test_invalid_utf8_is_replaced():
    assert parse(b'X = "bad \xff byte"')["X"] == "bad \ufffd byte"


@pytest.mark.parametrize("src", [
    'X = {',
    'X = "unterminated',
    'X = {["a"] "b"}',
    '= 5',
    'X = @',
    'X = "\\300"',
])
def test_errors(src):
    with pytest.raises(SVParseError):
        parse(src)


def test_large_input_is_fast():
    import time

    rows = ",\n".join(
        '{\n["id"] = "1794420000%06d:1",\n["t"] = 1794420000,\n["a"] = "Some Name",\n["m"] = "text \\"q\\" %d",\n}' % (i, i)
        for i in range(20000)
    )
    src = "GuildLedgerDB = {\n[\"chat\"] = {\n" + rows + "\n},\n}\n"
    start = time.perf_counter()
    out = parse(src)
    assert len(out["GuildLedgerDB"]["chat"]) == 20000
    assert time.perf_counter() - start < 10
