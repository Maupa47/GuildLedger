"""Professions in Discord (docs/dev/PLAN_COMMUNITY.md D4): who can craft what, from the hub data the collectors
upload (hub_profs, shared/schema.md 8) and the recipe catalogue (shared/catalog/recipes.json).

Pure logic, no Discord: the forum posts (`CraftForum.wanted`, one per profession, kept up to date through the
directory's bookkeeping) and the `/craft` lookup (`search`, `answer`). The Discord side is crafts_ui.py.

A post per profession that somebody in the guild has:
- first message: the crafters, highest skill first, with their skill and when they were last seen;
- then the recipes somebody knows, by name: "Recipe - Name, Name, Name (+3)".
Only members the roster lists as in the guild count. A recipe ID the catalogue does not know shows as its number.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from .. import catalog
from .common import esc
from .directory import Directory, Post, split_messages

# WoW's skill-line IDs (the hub's `profs` keys) and their names.
PROFESSIONS = {
    164: "Blacksmithing", 165: "Leatherworking", 171: "Alchemy", 182: "Herbalism", 186: "Mining",
    197: "Tailoring", 202: "Engineering", 333: "Enchanting", 393: "Skinning", 755: "Jewelcrafting",
    773: "Inscription", 185: "Cooking", 129: "First Aid", 356: "Fishing",
}
NAMES_SHOWN = 3      # crafters named per recipe line before "(+N)"
CRAFTERS_SHOWN = 15  # in a /craft answer

HELP_TEXT = ("**Who can craft what**\n"
             "- One post per profession: the crafters with their skill, then every recipe someone in the guild knows.\n"
             "- `/craft` finds a recipe or the item it makes (start typing, names are suggested): who can craft it,"
             " when they were last seen, and the materials.\n"
             "- The lists come from Amazing Hub: a member shows up here once they log in with the addon"
             " (members without it show their profession only). Updated every 10 minutes.")


def prof_name(pid: int) -> str:
    return PROFESSIONS.get(int(pid), f"Profession {pid}")


def recipe_index() -> dict[int, dict]:
    return {int(r["spell"]): r for r in catalog.recipes() if r.get("spell")}


def recipe_name(spell: int, idx: dict[int, dict] | None = None) -> str:
    r = (idx if idx is not None else recipe_index()).get(int(spell))
    return r["name"] if r else f"#{spell}"


def _crafters(db, guild: str | None = None) -> list[dict[str, Any]]:
    """Every profession line of a member who is in the guild now, with the member's display name and last seen."""
    q = ("SELECT h.guild, h.member, h.prof, h.name AS hname, h.skill, h.max, h.recipes, h.extra, h.src,"
         " m.name AS mname, m.last_seen, m.in_guild FROM hub_profs h"
         " LEFT JOIN members m ON m.guild=h.guild AND lower(m.name)=h.member")
    args: tuple = ()
    if guild:
        q += " WHERE h.guild=?"
        args = (guild,)
    out = []
    for r in db.execute(q, args):
        if r["in_guild"] != 1:
            continue
        d = dict(r)
        d["name"] = d["mname"] or d["hname"]
        d["spells"] = set(json.loads(d["recipes"] or "[]")) | set(json.loads(d["extra"] or "[]"))
        out.append(d)
    return out


def crafter_line(c: dict[str, Any]) -> str:
    bits = [f"**{esc(c['name'])}**"]
    if c.get("skill") is not None:
        bits.append(f"{c['skill']}/{c['max']}" if c.get("max") else str(c["skill"]))
    elif c.get("src") == "native":
        bits.append("no addon: skill unknown")
    if c.get("last_seen"):
        bits.append(f"seen <t:{int(c['last_seen'])}:R>")
    return " · ".join(bits)


class CraftForum(Directory):
    """The profession forum: one post per profession, edited in place when its text changes."""
    TABLE = "craft_posts"

    def wanted(self, guild: str | None = None) -> list[Post]:  # type: ignore[override]
        idx = recipe_index()
        by_prof: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for c in _crafters(self.db, guild):
            by_prof[c["prof"]].append(c)
        posts: list[Post] = [Post("help", "help", "How to find a crafter", [HELP_TEXT])]
        for pid in sorted(by_prof, key=prof_name):
            crafters = sorted(by_prof[pid], key=lambda c: (-(c["skill"] or -1), c["name"].lower()))
            who: dict[int, list[str]] = defaultdict(list)
            for c in crafters:
                for s in c["spells"]:
                    who[s].append(c["name"])
            header = f"**{prof_name(pid)}**: {len(crafters)} crafter{'s' if len(crafters) != 1 else ''}"
            messages = split_messages(header, [crafter_line(c) for c in crafters])
            lines = []
            for s in sorted(who, key=lambda s: recipe_name(s, idx).lower()):
                names = who[s]
                shown = ", ".join(esc(n) for n in names[:NAMES_SHOWN])
                more = f" (+{len(names) - NAMES_SHOWN})" if len(names) > NAMES_SHOWN else ""
                lines.append(f"{esc(recipe_name(s, idx))} - {shown}{more}")
            if lines:
                messages += split_messages(f"**Recipes known in the guild** ({len(lines)})", lines)
            posts.append(Post("prof", str(pid), prof_name(pid), messages))
        return posts


# ---------------------------------------------------------------------- /craft

def search(db, text: str, limit: int = 25) -> list[tuple[str, int]]:
    """(label, spell) for recipes whose name or item starts with / contains the text; known in the guild first."""
    t = (text or "").strip().lower()
    if len(t) < 2:
        return []
    known: set[int] = set()
    for c in _crafters(db):
        known |= c["spells"]
    hits = []
    for r in catalog.recipes():
        name, item = (r.get("name") or "").lower(), (r.get("item_name") or "").lower()
        if t in name or t in item:
            starts = name.startswith(t) or item.startswith(t)
            hits.append((int(r["spell"]) not in known, not starts, name, r))
    hits.sort(key=lambda h: h[:3])
    out = []
    for nk, _, _, r in hits[:limit]:
        label = f"{r['name']} ({r.get('profession') or '?'})" + ("" if nk else " - known in the guild")
        out.append((label[:100], int(r["spell"])))
    return out


def resolve(db, text: str) -> int | None:
    """The spell a /craft query means: a picked suggestion (its ID), else the best name match."""
    t = (text or "").strip()
    if t.isdigit():
        return int(t)
    hits = search(db, t, 1)
    return hits[0][1] if hits else None


def answer(db, spell: int) -> str:
    idx = recipe_index()
    r = idx.get(int(spell))
    title = f"**{esc(recipe_name(spell, idx))}**"
    lines = []
    if r:
        made = r.get("item_name") or (catalog.name_of(r["item"]) if r.get("item") else None)
        lines.append(title + f" ({esc(r.get('profession') or '?')}, skill {r.get('skill') or '?'})"
                     + (f" makes **{esc(made)}**" if made else ""))
        mats = [f"{n}x {esc(catalog.name_of(i) or f'item {i}')}" for i, n in (r.get("materials") or [])]
        if mats:
            lines.append("Materials: " + ", ".join(mats))
    else:
        lines.append(title)
    crafters = [c for c in _crafters(db) if int(spell) in c["spells"]]
    crafters.sort(key=lambda c: (-(c["last_seen"] or 0), c["name"].lower()))
    if not crafters:
        lines.append("Nobody in the guild has this recipe, as far as Amazing Hub's data shows.")
    else:
        lines.append(f"Crafters ({len(crafters)}): " + ", ".join(crafter_line(c) for c in crafters[:CRAFTERS_SHOWN])
                     + (f" (+{len(crafters) - CRAFTERS_SHOWN} more)" if len(crafters) > CRAFTERS_SHOWN else ""))
        lines.append("Order it in game: Amazing Hub > Crafts.")
    return "\n".join(lines)[:1900]
