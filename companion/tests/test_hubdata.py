"""Hub data outside the game (shared/schema.md 8): professions, guild bank, alt links from AmazingHub.lua.
Synthetic data only."""

from guildledger import hubdata
from guildledger.store import Spool
from guildledger.svparse import parse, parse_file
from hub_fixture import FIX, T0


def hubdata_lua(bank_t=T0 + 100, skill=150, unlink=False, ledger_extra=False):
    alt = ('{ ["removed"] = true, ["author"] = "Offi Cer-Forever", ["ts"] = %d }' % (T0 + 50) if unlink
           else '{ ["main"] = "Alia Testwood-Forever", ["author"] = "Offi Cer-Forever", ["ts"] = %d }' % (T0 + 10))
    extra_line = ('{ ["k"] = 0, ["t"] = %d, ["ty"] = "d", ["n"] = "Bram Exampleson", ["g"] = 50000 },' % (T0 + 300)
                  if ledger_extra else "")
    return f'''
AmazingHubDB = {{
["Synthetic Guild-Forever"] = {{
  ["professions"] = {{
    ["Alia Testwood-Forever"] = {{ ["src"] = "addon", ["ts"] = {T0 + skill}, ["profs"] = {{
        [197] = {{ ["rank"] = {skill}, ["max"] = 225, ["h"] = 1, ["n"] = 3, ["recipes"] = {{ 2387, 2389, 3915 }}, ["extra"] = {{}} }},
        [186] = {{ ["rank"] = 40, ["max"] = 75, ["h"] = 2, ["n"] = 0, ["recipes"] = {{}}, ["extra"] = {{}} }},
    }} }},
    ["Bram Exampleson-Forever"] = {{ ["src"] = "native", ["ts"] = {T0}, ["profs"] = {{ [164] = {{}} }} }},
  }},
  ["guildBank"] = {{
    ["tabs"] = {{
      {{ ["name"] = "Mats", ["ts"] = {bank_t}, ["by"] = "Offi Cer", ["slots"] = {{
          [1] = {{ ["id"] = 2589, ["c"] = 20 }}, [7] = {{ ["id"] = 2592, ["c"] = 5 }} }} }},
    }},
    ["moneyNow"] = 1234567, ["moneyTs"] = {bank_t}, ["moneyBy"] = "Offi Cer",
    ["ledger"] = {{
      {{ ["k"] = 1, ["t"] = {T0 + 200}, ["ty"] = "d", ["n"] = "Alia Testwood", ["id"] = 2589, ["c"] = 20 }},
      {{ ["k"] = 1, ["t"] = {T0 + 200}, ["ty"] = "d", ["n"] = "Alia Testwood", ["id"] = 2589, ["c"] = 20 }},
      {extra_line}
    }},
  }},
  ["altSync"] = {{ ["v"] = 1, ["rev"] = {{}}, ["links"] = {{ ["Cora Sample-Forever"] = {alt} }} }},
}},
}}
'''


def spool(tmp_path):
    s = Spool(tmp_path / "s.db")
    s.import_sv(parse_file(str(FIX / "basic.lua")), "Testa Collector")
    return s


def n(s, table):
    return s.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_rows_from_the_hub_tables():
    rows = hubdata.rows_from_hub(parse(hubdata_lua())["AmazingHubDB"]["Synthetic Guild-Forever"])
    profs = {(r["member"], r["prof"]): r for r in rows["prof"]}
    assert profs[("alia testwood", 197)]["recipes"] == [2387, 2389, 3915] and profs[("alia testwood", 197)]["skill"] == 150
    assert profs[("bram exampleson", 164)]["src"] == "native" and profs[("bram exampleson", 164)]["skill"] is None
    assert profs[("alia testwood", 197)]["name"] == "Alia Testwood"           # the surname is kept, the realm dropped
    tab = rows["bank_tab"][0]
    assert tab["tab"] == 1 and tab["slots"] == [[1, 2589, 20], [7, 2592, 5]]
    assert rows["bank_money"] == [{"t": T0 + 100, "copper": 1234567, "by": "Offi Cer"}]
    assert [r["id"][16:] for r in rows["bank_log"]] == ["", "#2"]  # two equal deposits stay two
    assert rows["altlink"][0]["main"] == "Alia Testwood-Forever"


def test_import_twice_adds_nothing_and_newer_data_replaces(tmp_path):
    s = spool(tmp_path)
    first = hubdata.import_hub(s.db, parse(hubdata_lua()), s.guild_names(), "Testa Collector")
    assert first.profs == 3 and first.tabs == 1 and first.money == 1 and first.log_new == 2 and first.alts == 1
    assert len(hubdata.pending(s.db, s.guild_names() and next(iter(s.guild_names())))) == 8
    g = next(iter(s.guild_names()))
    hubdata.mark_uploaded(s.db, g, hubdata.pending(s.db, g))
    again = hubdata.import_hub(s.db, parse(hubdata_lua()), s.guild_names(), "Testa Collector")
    assert again.changed == 0 and hubdata.pending(s.db, g) == []
    # an older bank picture changes nothing; a newer skill, a new ledger line and an unlink do
    later = hubdata.import_hub(s.db, parse(hubdata_lua(bank_t=T0 + 50, skill=160, unlink=True, ledger_extra=True)),
                               s.guild_names(), "Testa Collector")
    assert later.tabs == 0 and later.money == 0 and later.profs == 1 and later.log_new == 1 and later.alts == 1
    kinds = sorted(k for k, _ in hubdata.pending(s.db, g))
    assert kinds == ["altlink", "bank_log", "prof"]
    assert s.db.execute("SELECT removed FROM alt_links").fetchone()[0] == 1
    assert n(s, "hub_profs") == 3 and n(s, "bank_log") == 3
