"""Item and recipe catalogue for WoW: Forever (docs/dev/archive/PLAN_COMMUNITY.md phase C, W20).

Source: Blizzard's game tables as exported by wago.tools (product `wowf`), one CSV per table:
    https://wago.tools/db2/<Table>/csv?build=<build>
Forever ships no Encounter Journal tables (JournalInstance/JournalEncounter/JournalEncounterItem are missing for
every Forever build, checked 2026-11-24), so there is no "which boss drops what" here: the hub learns that from
loot players see. Raids that are not open yet are encrypted in the exports; run this again after they open.

Writes:
    addon/hub-extra/Data/ItemCatalog.lua   items players may wish for (equippable, uncommon or better), Forever only
    shared/catalog/items.json              the same items, for the bot (/wish add autocomplete)
    shared/catalog/recipes.json            profession recipes: spell, name, profession, materials, item made
    shared/catalog/names.json              every item's English name by ID, for the bot (bank, materials)

    python tools/build-catalog.py [--build 1.60.1.71037] [--cache DIR]

Data © Blizzard Entertainment; exports by wago.tools. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = "1.60.1.71037"
TABLES = ["ItemSparse", "Item", "SkillLine", "SkillLineAbility", "SpellEffect", "SpellReagents", "SpellName"]
CREATE_ITEM = 24
PROFESSION_CATEGORIES = {11, 9}  # primary, secondary (cooking, first aid, fishing)
MIN_QUALITY = 2                 # uncommon
MAX_LUA_BYTES = 400 * 1024
SLOTS = {1: "head", 2: "neck", 3: "shoulder", 4: "shirt", 5: "chest", 6: "waist", 7: "legs", 8: "feet", 9: "wrist",
         10: "hands", 11: "finger", 12: "trinket", 13: "one-hand", 14: "shield", 15: "ranged", 16: "back",
         17: "two-hand", 18: "bag", 19: "tabard", 20: "chest", 21: "main hand", 22: "off hand", 23: "held in off hand",
         24: "ammo", 25: "thrown", 26: "ranged", 28: "relic"}


def num(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def fetch(table: str, build: str, cache: Path | None) -> list[dict]:
    path = cache / f"{table}-{build}.csv" if cache else None
    if path and path.is_file():
        text = path.read_text("utf-8")
    else:
        url = f"https://wago.tools/db2/{table}/csv?build={build}"
        req = urllib.request.Request(url, headers={"User-Agent": "guildledger-catalog/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            text = r.read().decode("utf-8")
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, "utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def build_items(t: dict) -> list[dict]:
    kind = {num(r["ID"]): r for r in t["Item"]}
    out = []
    for r in t["ItemSparse"]:
        iid, q = num(r["ID"]), num(r.get("OverallQualityID"))
        inv = num(r.get("InventoryType")) or num(kind.get(iid, {}).get("InventoryType"))
        name = (r.get("Display_lang") or "").strip()
        if not name or q < MIN_QUALITY or q > 5 or inv not in SLOTS or inv in (18, 19, 24):
            continue
        out.append({"id": iid, "name": name, "quality": q, "slot": SLOTS[inv], "ilvl": num(r.get("ItemLevel")),
                    "req": num(r.get("RequiredLevel"))})
    out.sort(key=lambda x: x["id"])
    return out


def build_recipes(t: dict) -> list[dict]:
    lines = {num(r["ID"]): r["DisplayName_lang"] for r in t["SkillLine"]
             if num(r.get("CategoryID")) in PROFESSION_CATEGORIES and num(r["ID"]) not in (2933, 2934)}
    names = {num(r["ID"]): r["Name_lang"] for r in t["SpellName"]}
    made = {}
    for e in t["SpellEffect"]:
        if num(e.get("Effect")) == CREATE_ITEM and num(e.get("EffectItemType")):
            made.setdefault(num(e["SpellID"]), num(e["EffectItemType"]))
    reagents = {}
    for r in t["SpellReagents"]:
        mats = [[num(r[f"Reagent_{i}"]), num(r[f"ReagentCount_{i}"])] for i in range(8)
                if num(r.get(f"Reagent_{i}")) and num(r.get(f"ReagentCount_{i}"))]
        if mats:
            reagents[num(r["SpellID"])] = mats
    item_names = {num(r["ID"]): (r.get("Display_lang") or "").strip() for r in t["ItemSparse"]}
    out, seen = [], set()
    for r in t["SkillLineAbility"]:
        line, spell = num(r["SkillLine"]), num(r["Spell"])
        if line not in lines or spell in seen or spell not in reagents or num(r.get("AcquireMethod")) == 3:
            continue
        seen.add(spell)
        item = made.get(spell, 0)
        out.append({"spell": spell, "name": names.get(spell) or item_names.get(item) or str(spell),
                    "profession": lines[line], "skill": num(r.get("MinSkillLineRank")),
                    "item": item, "item_name": item_names.get(item, ""), "materials": reagents[spell]})
    out.sort(key=lambda x: (x["profession"], x["skill"], x["name"]))
    return out


def lua_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def render_lua(items: list[dict], build: str) -> str:
    head = ("-- Amazing Hub item catalogue for WoW: Forever. GENERATED by tools/build-catalog.py from build "
            f"{build}: do not edit.\n-- Data (c) Blizzard Entertainment; exports by wago.tools. Items players may wish "
            "for: id = { name, quality, slot, item level }.\n-- Loaded on Forever only (addon/hub-extra/ItemCatalog.lua);"
            " no boss or instance: Forever has no Encounter Journal data.\n")
    rows = [f"[{i['id']}]={{{lua_str(i['name'])},{i['quality']},{lua_str(i['slot'])},{i['ilvl']}}}," for i in items]
    return head + "AmazingHubItemCatalog = {\nbuild = " + lua_str(build) + ",\nitems = {\n" + "\n".join(rows) + "\n}}\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--build", default=BUILD)
    p.add_argument("--cache", type=Path)
    args = p.parse_args(argv)
    t = {name: fetch(name, args.build, args.cache) for name in TABLES}
    items, recipes = build_items(t), build_recipes(t)
    lua = render_lua(items, args.build)
    if len(lua.encode("utf-8")) > MAX_LUA_BYTES:
        sys.exit(f"ItemCatalog.lua would be {len(lua) // 1024} KB, over the {MAX_LUA_BYTES // 1024} KB limit")
    (ROOT / "addon" / "hub-extra" / "Data").mkdir(parents=True, exist_ok=True)
    (ROOT / "addon" / "hub-extra" / "Data" / "ItemCatalog.lua").write_text(lua, "utf-8", newline="\n")
    cat = ROOT / "shared" / "catalog"
    cat.mkdir(parents=True, exist_ok=True)
    meta = {"build": args.build, "source": "wago.tools exports of Blizzard game data"}
    (cat / "items.json").write_text(json.dumps({**meta, "items": items}, ensure_ascii=False, separators=(",", ":")),
                                    "utf-8", newline="\n")
    names = {num(r["ID"]): (r.get("Display_lang") or "").strip() for r in t["ItemSparse"]
             if (r.get("Display_lang") or "").strip()}
    (cat / "names.json").write_text(json.dumps({**meta, "names": {str(k): v for k, v in sorted(names.items())}},
                                               ensure_ascii=False, separators=(",", ":")), "utf-8", newline="\n")
    (cat / "recipes.json").write_text(json.dumps({**meta, "recipes": recipes}, ensure_ascii=False,
                                                 separators=(",", ":")), "utf-8", newline="\n")
    print(f"build {args.build}: {len(items)} items ({len(lua) // 1024} KB Lua), {len(recipes)} recipes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
