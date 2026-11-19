"""Slash commands for the loot data (shared/schema.md 7): /dkp, /loot, /wishlist and /wish add|remove|export.

Everyone may look things up. A wish can be changed for one's own linked characters (/link); officers (Manage
Roles) for anyone. All answers are ephemeral; database work runs on the bot's worker thread.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord as dpy
from discord import app_commands

from . import loot
from .commands import NO_MENTIONS, esc, is_officer, ts

if TYPE_CHECKING:
    from .client import LedgerBot

NO_DATA = ("No loot data yet. It arrives once an officer with the companion has Amazing Hub's Raids/Loot tabs"
           " in use (Settings -> Loot -> loot system) and has done a /reload or logout.")


def register_loot(bot: "LedgerBot") -> None:
    tree = bot.tree

    async def reply(inter: dpy.Interaction, text: str) -> None:
        await inter.response.send_message(text[:1990], ephemeral=True, allowed_mentions=NO_MENTIONS)

    def db():
        return bot._archive.db

    async def guild() -> str | None:
        return await bot._db(loot.main_guild, db())

    async def own_chars(inter: dpy.Interaction) -> list[str]:
        rows = await bot._db(bot._links.chars, inter.user.id)
        return [r["name"] for r in rows if r.get("in_guild", 1) != 0]

    async def may_change(inter: dpy.Interaction, character: str) -> bool:
        if is_officer(inter):
            return True
        return character.strip().lower() in {c.lower() for c in await own_chars(inter)}

    async def default_char(inter: dpy.Interaction, character: str | None) -> str | None:
        if character:
            return character.strip()
        mine = await own_chars(inter)
        return mine[0] if mine else None

    @tree.command(name="dkp", description="DKP / points standings (Amazing Hub), or one character's points")
    @app_commands.describe(character="Character name (empty: the top of the list)",
                           pool="Raid core's own points (empty: the guild's)")
    async def dkp(inter: dpy.Interaction, character: str | None = None, pool: str | None = None):
        g = await guild()
        if g is None:
            await reply(inter, NO_DATA)
            return
        rows = await bot._db(loot.standings, db(), g, pool or "", character, 25)
        if not rows:
            pools = await bot._db(loot.pools, db(), g)
            hint = (" Pools: " + ", ".join(p or "(guild)" for p in pools)) if pools else ""
            await reply(inter, (f"No points for **{esc(character)}**." if character else NO_DATA) + hint)
            return
        mode = (rows[0]["mode"] or "dkp").upper()
        if character:
            s = rows[0]
            await reply(inter, f"**{esc(s['name'])}** ({mode}{', ' + esc(pool) if pool else ''}): {s['current']:g}"
                        f" (earned {s['earned']:g}, spent {s['spent']:g}) - as of {ts(s['seen_at'], 'R')}")
            return
        lines = [f"{i}. **{esc(s['name'])}** {s['current']:g}" for i, s in enumerate(rows, 1)]
        newest = max(s["seen_at"] for s in rows)
        await reply(inter, f"{mode} standings{' - ' + esc(pool) if pool else ''} (as of {ts(newest, 'R')}):\n"
                    + "\n".join(lines))

    @tree.command(name="loot", description="Items handed out recently (Amazing Hub's loot history)")
    @app_commands.describe(character="Character name (empty: everyone)")
    async def loot_cmd(inter: dpy.Interaction, character: str | None = None):
        g = await guild()
        if g is None:
            await reply(inter, NO_DATA)
            return
        rows = await bot._db(loot.recent_loot, db(), g, character, 15)
        if not rows:
            await reply(inter, f"No items recorded for **{esc(character)}**." if character else NO_DATA)
            return
        lines = [f"{ts(r['ts_utc'], 'd')} **{esc(r['name'])}**: [{esc(r['item_name'] or str(r['item_id']))}]"
                 f"{' (' + esc(r['raid']) + ')' if r['raid'] else ''}" for r in rows]
        await reply(inter, ("Recent loot" + (f" of {esc(character)}" if character else "") + ":\n") + "\n".join(lines))

    async def show_wishlist(inter: dpy.Interaction, character: str | None) -> None:
        g = await guild()
        name = await default_char(inter, character)
        if g is None or not name:
            await reply(inter, "Name a character (or link yours with /link)." if g else NO_DATA)
            return
        w = await bot._db(loot.wishlist, db(), g, name)
        if not w["game"] and not w["discord"]:
            await reply(inter, f"**{esc(name)}** has no wishlist.")
            return

        def item(i):
            return f"[{esc(i.get('name') or str(i['item']))}] ({i['item']}){' - off spec' if i.get('off') else ''}"
        lines = [f"Wishlist of **{esc(w['name'])}**:"]
        if w["game"]:
            lines.append(f"In game (as of {ts(w['seen_at'], 'R')}):")
            lines += [f"{k}. {item(i)}" for k, i in enumerate(w["game"], 1)]
        if w["discord"]:
            lines.append("Added in Discord (not in game yet; /wish export gives the string to paste):")
            lines += [f"- {item(i)}" for i in w["discord"]]
        await reply(inter, "\n".join(lines))

    @tree.command(name="wishlist", description="A character's wishlist (Amazing Hub, plus wishes added in Discord)")
    @app_commands.describe(character="Character name (empty: your linked character)")
    async def wishlist(inter: dpy.Interaction, character: str | None = None):
        await show_wishlist(inter, character)

    wish = app_commands.Group(name="wish", description="Your wishlist from Discord", guild_only=True)

    @wish.command(name="add", description="Add an item to a wishlist (item ID, Wowhead link or exact item name)")
    @app_commands.describe(item="Item ID, a Wowhead link, or the item's name", character="Your character (empty: your"
                           " linked one); officers: anyone", offspec="Off spec (main spec if not ticked)")
    async def wish_add(inter: dpy.Interaction, item: str, character: str | None = None, offspec: bool = False):
        g = await guild()
        name = await default_char(inter, character)
        if g is None or not name:
            await reply(inter, "Name a character (or link yours with /link)." if g else NO_DATA)
            return
        if not await may_change(inter, name):
            await reply(inter, f"**{esc(name)}** is not one of your linked characters (/chars). Officers can change"
                        " anyone's wishes.")
            return
        iid, iname, problem = await bot._db(loot.resolve_item, db(), g, item)
        if iid is None:
            await reply(inter, f"Item not found: {esc(problem)}")
            return
        added = await bot._db(loot.wish_add, db(), g, name, iid, iname, offspec, inter.user.id)
        label = f"[{esc(iname)}] ({iid})" if iname else f"item {iid}"
        await reply(inter, (f"Added {label} to **{esc(name)}**'s wishlist" if added
                            else f"{label} is already on **{esc(name)}**'s Discord wishlist")
                    + ". To get it into the game: /wish export, then paste the string in Amazing Hub.")

    @wish.command(name="remove", description="Remove an item (or all Discord-added items) from a wishlist")
    @app_commands.describe(item="Item ID, Wowhead link or name (empty: all items added in Discord)",
                           character="Your character (empty: your linked one); officers: anyone")
    async def wish_remove(inter: dpy.Interaction, item: str | None = None, character: str | None = None):
        g = await guild()
        name = await default_char(inter, character)
        if g is None or not name:
            await reply(inter, "Name a character (or link yours with /link)." if g else NO_DATA)
            return
        if not await may_change(inter, name):
            await reply(inter, f"**{esc(name)}** is not one of your linked characters.")
            return
        iid = None
        if item:
            iid, _, problem = await bot._db(loot.resolve_item, db(), g, item)
            if iid is None:
                await reply(inter, f"Item not found: {esc(problem)}")
                return
        n = await bot._db(loot.wish_remove, db(), g, name, iid)
        await reply(inter, f"Removed {n} item(s) from **{esc(name)}**'s Discord wishlist." if n
                    else "Nothing to remove (only items added in Discord can be removed here; the in-game list is"
                         " changed in game).")

    @wish.command(name="export", description="The string to paste into Amazing Hub's wishlist import")
    @app_commands.describe(character="Your character (empty: your linked one)")
    async def wish_export(inter: dpy.Interaction, character: str | None = None):
        g = await guild()
        name = await default_char(inter, character)
        if g is None or not name:
            await reply(inter, "Name a character (or link yours with /link)." if g else NO_DATA)
            return
        s = await bot._db(loot.wish_export, db(), g, name)
        if not s:
            await reply(inter, f"**{esc(name)}** has no wishes added in Discord.")
            return
        await reply(inter, "Copy this line, then in game: /amazing → Wishlist → Import, paste, Import:\n"
                    f"```\n{s}\n```")

    @wish.command(name="list", description="A character's wishlist (same as /wishlist)")
    @app_commands.describe(character="Character name (empty: your linked character)")
    async def wish_list(inter: dpy.Interaction, character: str | None = None):
        await show_wishlist(inter, character)

    tree.add_command(wish)
