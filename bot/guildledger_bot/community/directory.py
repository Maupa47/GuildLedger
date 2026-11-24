"""Character directory (docs/dev/PLAN_COMMUNITY.md D3): every guild character listed in a Discord forum.

Pure logic, no Discord: what each forum post should say (`wanted`), and which writes bring the forum there
(`plan`). The Discord side (client) applies at most WRITES_PER_ROUND writes per round and stores each post's
thread, messages and hash in `directory_posts`.

Posts:
- one per linked Discord user: title = the main's name, tag = the main's class, one line per character;
- "Not linked yet" posts in fixed alphabetical blocks for every other guild character, so all are listed;
- one help post that explains /whois and right-click → Apps → Characters.
A user whose characters all left the guild gets "left the guild" for the grace period, then the post goes.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from ..store import Archive
from .common import esc

WRITES_PER_ROUND = 10
MAX_MESSAGE = 1900          # one Discord message: 2000 characters; a little room
MAX_TITLE = 100
ARMORY_MIN_LEVEL = 10       # Blizzard has a profile from level 10, after one logout
DEFAULT_ARMORY = "https://worldofwarcraft.blizzard.com/en-us/forever/eu/armory/character/{name}"  # decision 11
BLOCKS = ["A-C", "D-F", "G-I", "J-L", "M-O", "P-R", "S-U", "V-Z", "#"]

_DDL = """
CREATE TABLE IF NOT EXISTS directory_posts(
  kind TEXT NOT NULL, key TEXT NOT NULL, thread_id INTEGER, message_ids TEXT NOT NULL DEFAULT '[]',
  hash TEXT, updated_at INTEGER, PRIMARY KEY (kind, key));
"""

_ASCII_NAME = re.compile(r"^[A-Za-z]+(?: [A-Za-z]+)*$")


def armory_url(template: str | None, name: str, level: int | None) -> str | None:
    """Link to the character's armory page, or None. Rule (section 2 item 13): lower case, space -> hyphen.
    Names with a special letter get no link until such a name has been checked once (open point)."""
    if not template or "{name}" not in template or not name:
        return None
    if (level or 0) < ARMORY_MIN_LEVEL or not _ASCII_NAME.match(name):
        return None
    return template.replace("{name}", name.lower().replace(" ", "-"))


def char_line(c: dict[str, Any], template: str | None, main: bool = False) -> str:
    name = esc(c["name"])
    url = armory_url(template, c["name"], c.get("level"))
    shown = f"[{name}](<{url}>)" if url else f"**{name}**"
    bits = [shown + (" (main)" if main else "")]
    lvl = c.get("level")
    cls = (c.get("class") or "").title()
    if lvl or cls:
        bits.append(f"{lvl or '?'} {esc(cls)}".strip())
    if c.get("rank_name"):
        bits.append(esc(c["rank_name"]))
    if not c.get("in_guild", 1):
        bits.append("left the guild")
    elif c.get("last_seen"):
        bits.append(f"seen <t:{int(c['last_seen'])}:R>")
    return " · ".join(bits)


def split_messages(header: str, lines: list[str], limit: int = MAX_MESSAGE) -> list[str]:
    """Lines into messages of at most `limit` characters; the header starts the first."""
    out, buf = [], header
    for line in lines:
        line = line[:limit]
        if buf and len(buf) + 1 + len(line) > limit:
            out.append(buf)
            buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line
    if buf or not out:
        out.append(buf)
    return out


def block_of(name: str) -> str:
    first = (name[:1] or "#").upper()
    for b in BLOCKS[:-1]:
        if b[0] <= first <= b[2]:
            return b
    return "#"


@dataclass
class Post:
    kind: str                   # "user", "index", "help"
    key: str                    # user ID, block name, "help"
    title: str
    messages: list[str]
    tag: str | None = None      # forum tag name (the main's class), if the forum has such a tag

    @property
    def hash(self) -> str:
        raw = json.dumps([self.title, self.tag, self.messages], ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class Write:
    action: str                 # "create", "edit", "delete"
    post: Post | None
    kind: str
    key: str
    thread_id: int | None = None
    message_ids: list[int] = field(default_factory=list)


HELP_TEXT = ("**Find a character**\n"
             "- `/whois character:` tells who plays a character (start typing, names are suggested).\n"
             "- Right-click a member → **Apps** → **Characters** shows all their characters.\n"
             "- Each member who linked their characters has a post here, titled with their main.\n"
             "- Characters nobody linked yet are listed in the **Not linked yet** posts.\n"
             "Not here yet? Type `/link` and follow the steps.")


class Directory:
    def __init__(self, archive: Archive, now=time.time):
        self.a, self.now = archive, now
        self.db = archive.db
        self.db.executescript(_DDL)

    # ------------------------------------------------------------------ what the forum should show

    def wanted(self, template: str | None, grace_days: int, mains: dict[int, str] | None = None) -> list[Post]:
        """Every post the forum should have now. `mains` = {user: chosen main guid} (Links.main_of)."""
        mains = mains or {}
        rows = [dict(r) for r in self.db.execute(
            "SELECT l.discord_user_id AS uid, l.name AS lname, l.linked_at, l.guild, l.guid, m.name, m.level,"
            " m.class, m.rank_name, m.rank_index, m.last_seen, m.in_guild FROM links l"
            " LEFT JOIN members m ON m.guild=l.guild AND m.guid=l.guid ORDER BY l.discord_user_id")]
        by_user: dict[int, list[dict[str, Any]]] = {}
        linked: set[tuple[str, str]] = set()
        for r in rows:
            r["name"] = r["name"] or r["lname"]
            r["in_guild"] = r["in_guild"] if r["in_guild"] is not None else 0
            by_user.setdefault(r["uid"], []).append(r)
            if r["guid"]:
                linked.add((r["guild"], r["guid"]))
        posts: list[Post] = [Post("help", "help", "How to find a character", [HELP_TEXT])]
        now = self.now()
        for uid, chars in by_user.items():
            inside = [c for c in chars if c["in_guild"]]
            if not inside:
                last = max((c["last_seen"] or c["linked_at"] or 0) for c in chars)
                if now - last > grace_days * 86400:
                    continue  # gone: the post is removed
            pool = inside or chars
            main = next((c for c in pool if c["guid"] == mains.get(uid)), None) or max(
                pool, key=lambda c: (c["level"] or 0, -(c["linked_at"] or 0)))
            others = sorted((c for c in chars if c is not main),
                            key=lambda c: (-(c["in_guild"] or 0), -(c["level"] or 0), c["name"]))
            header = f"<@{uid}>" + ("" if inside else " - left the guild")
            lines = [char_line(main, template, main=True)] + [char_line(c, template) for c in others]
            title = main["name"][:MAX_TITLE] + ("" if inside else " (left)")
            posts.append(Post("user", str(uid), title, split_messages(header, lines),
                              tag=(main.get("class") or "").title() or None))
        blocks: dict[str, list[dict[str, Any]]] = {b: [] for b in BLOCKS}
        for r in self.db.execute("SELECT * FROM members WHERE in_guild=1 ORDER BY name COLLATE NOCASE"):
            if (r["guild"], r["guid"]) not in linked:
                blocks[block_of(r["name"])].append(dict(r))
        for b, chars in blocks.items():
            if not chars:
                continue
            header = f"**Not linked yet: {b}** ({len(chars)})"
            posts.append(Post("index", b, f"Not linked yet: {b}",
                              split_messages(header, [char_line(c, template) for c in chars])))
        return posts

    # ------------------------------------------------------------------ what to write

    def stored(self) -> dict[tuple[str, str], dict[str, Any]]:
        return {(r["kind"], r["key"]): {"thread_id": r["thread_id"], "message_ids": json.loads(r["message_ids"]),
                                         "hash": r["hash"]}
                for r in self.db.execute("SELECT * FROM directory_posts")}

    def plan(self, posts: list[Post], limit: int = WRITES_PER_ROUND) -> list[Write]:
        """Writes for posts whose hash changed, new posts and posts no longer wanted; at most `limit`.
        Order: help, then removals, then changed, then new, so a big first run still finishes in rounds."""
        have = self.stored()
        want = {(p.kind, p.key): p for p in posts}
        deletes = [Write("delete", None, k, key, s["thread_id"], s["message_ids"])
                   for (k, key), s in have.items() if (k, key) not in want]
        edits, creates = [], []
        for (k, key), p in want.items():
            s = have.get((k, key))
            if s is None or not s["thread_id"]:
                creates.append(Write("create", p, k, key))
            elif s["hash"] != p.hash:
                edits.append(Write("edit", p, k, key, s["thread_id"], s["message_ids"]))
        first = [w for w in creates + edits if w.kind == "help"]
        rest = deletes + [w for w in edits if w.kind != "help"] + [w for w in creates if w.kind != "help"]
        return (first + rest)[:limit]

    def done(self, w: Write, thread_id: int | None = None, message_ids: list[int] | None = None) -> None:
        """Record a write Discord confirmed."""
        with self.db:
            if w.action == "delete":
                self.db.execute("DELETE FROM directory_posts WHERE kind=? AND key=?", (w.kind, w.key))
                return
            self.db.execute("INSERT OR REPLACE INTO directory_posts VALUES(?,?,?,?,?,?)",
                            (w.kind, w.key, thread_id, json.dumps(message_ids or []), w.post.hash,
                             int(self.now())))

    def forget(self, kind: str, key: str) -> None:
        """The post was deleted in Discord: make it again next round."""
        with self.db:
            self.db.execute("DELETE FROM directory_posts WHERE kind=? AND key=?", (kind, key))

    def thread_of_user(self, user_id: int) -> int | None:
        r = self.db.execute("SELECT thread_id FROM directory_posts WHERE kind='user' AND key=?",
                            (str(user_id),)).fetchone()
        return r[0] if r else None
