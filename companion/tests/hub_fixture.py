"""A synthetic AmazingHub.lua (Amazing Hub's SavedVariables) for the loot tests of companion and bot."""

from pathlib import Path

FIX = Path(__file__).parent / "fixtures"
T0 = 1794420000


def hub_lua(shift=0, alia_points=60, wish=(19019, 18832)):
    """An AmazingHub.lua as the game writes it. shift: this collector's clock stamped awards a bit later."""
    t = T0 + shift
    items = "".join(f'{{ ["itemId"] = {i}, ["itemLink"] = "|cffa335ee|Hitem:{i}::::::::60:::::|h[Item {i}]|h|r",'
                    f' ["order"] = {k}, ["isOffspec"] = {"true" if k == 2 else "false"} }},'
                    for k, i in enumerate(wish, 1))
    return f'''
AmazingHubDB = {{
["_dbVersion"] = 2,
["font"] = "game",
["_noguild-Forever"] = {{ ["points"] = {{ ["log"] = {{ {{ ["ts"] = 1, ["name"] = "Nobody", ["delta"] = 5 }} }} }} }},
["Synthetic Guild-Forever"] = {{
  ["points"] = {{
    ["mode"] = "dkp",
    ["standings"] = {{
      ["Alia Testwood-Forever"] = {{ ["name"] = "Alia Testwood", ["class"] = "MAGE", ["current"] = {alia_points},
                                    ["earned"] = 90, ["spent"] = 30 }},
      ["Bram Exampleson-Forever"] = {{ ["name"] = "Bram Exampleson", ["class"] = "WARRIOR", ["current"] = 90,
                                      ["earned"] = 90, ["spent"] = 0 }},
    }},
    ["log"] = {{
      {{ ["ts"] = {T0 + 900}, ["key"] = "Alia Testwood-Forever", ["name"] = "Alia Testwood", ["delta"] = -30,
         ["reason"] = "Item: [Item 19019]", ["author"] = "Testa Officer", ["kind"] = "spend" }},
      {{ ["ts"] = {T0 + 600}, ["key"] = "Alia Testwood-Forever", ["name"] = "Alia Testwood", ["delta"] = 10,
         ["reason"] = "Boss kill: Ragnaros", ["author"] = "Testa Officer", ["kind"] = "boss" }},
      {{ ["ts"] = {T0 + 600}, ["key"] = "Bram Exampleson-Forever", ["name"] = "Bram Exampleson", ["delta"] = 10,
         ["reason"] = "Boss kill: Ragnaros", ["author"] = "Testa Officer", ["kind"] = "boss" }},
    }},
  }},
  ["cores"] = {{
    ["Core A"] = {{ ["points"] = {{ ["mode"] = "epgp", ["standings"] = {{
      ["Cora Sample-Forever"] = {{ ["name"] = "Cora Sample", ["current"] = 12, ["earned"] = 12, ["spent"] = 0 }} }},
      ["log"] = {{}} }} }},
  }},
  ["lootHistory"] = {{
    {{ ["itemLink"] = "|cffa335ee|Hitem:19019::::::::60:::::|h[Thunderfury]|h|r", ["itemName"] = "Thunderfury",
       ["quality"] = 5, ["player"] = "Alia Testwood", ["playerKey"] = "Alia Testwood-Forever", ["count"] = 1,
       ["timestamp"] = {t + 890}, ["raid"] = "Molten Core", ["fromML"] = true }},
  }},
  ["guildWishlists"] = {{
    ["bram exampleson"] = {{ ["name"] = "Bram Exampleson", ["class"] = "WARRIOR", ["wishlist"] = {{ {items} }} }},
  }},
  ["raidTracker"] = {{ ["sessions"] = {{
    [{t}] = {{ ["instanceID"] = 409, ["name"] = "Molten Core", ["size"] = 40, ["startTime"] = {t},
      ["endTime"] = {t + 3600}, ["isGuildRaid"] = true,
      ["encounters"] = {{ {{ ["id"] = 672, ["name"] = "Ragnaros", ["startTime"] = {T0 + 500},
                            ["endTime"] = {T0 + 600}, ["success"] = true }} }},
      ["players"] = {{ ["Alia Testwood-Forever"] = true, ["Bram Exampleson-Forever"] = true }} }},
  }} }},
}},
}}
'''
