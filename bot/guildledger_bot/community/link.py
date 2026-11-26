"""Discord link (docs/dev/archive/PACK_PLAN.md section 10): characters <-> Discord users. Pure database logic, no Discord.

Flow: /link gives the Discord user a one-time code -> in game `/gl link CODE` -> a collector records it ->
upload -> `process()` checks it and opens a *confirmation* for that Discord user -> only the user's click
("Confirm" / "Not me") creates the link or blocks the character. Alts: a character whose account tag
belongs to a linked user gets the same kind of confirmation.
"""

from __future__ import annotations

import re
import secrets
import time
import json
from dataclasses import dataclass
from typing import Any

from ..store import Archive

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I, O, 0, 1 (same as the addon)
CODE_LEN = 8
CODE_TTL = 1800
CHAT_CODE_TTL = 600  # "!link CODE" in guild chat: everyone there sees the line, so a shorter life
CHAT_CODE = re.compile(r"^\s*!link\s+([A-Za-z0-9]{%d})\b" % CODE_LEN)
MAX_OPEN = 3  # open confirmations per Discord user

_DDL = """
CREATE TABLE IF NOT EXISTS link_codes(
  code TEXT PRIMARY KEY, discord_user_id INTEGER NOT NULL, created_at INTEGER NOT NULL, used_at INTEGER);
CREATE TABLE IF NOT EXISTS links(
  guild TEXT NOT NULL, guid TEXT NOT NULL, name TEXT NOT NULL, discord_user_id INTEGER NOT NULL, tag TEXT,
  linked_at INTEGER NOT NULL, via_collector TEXT, PRIMARY KEY (guild, guid));
CREATE TABLE IF NOT EXISTS link_blocks(
  discord_user_id INTEGER NOT NULL, guild TEXT NOT NULL, guid TEXT NOT NULL,
  PRIMARY KEY (discord_user_id, guild, guid));
CREATE TABLE IF NOT EXISTS link_confirms(
  id INTEGER PRIMARY KEY AUTOINCREMENT, discord_user_id INTEGER NOT NULL, guild TEXT NOT NULL, guid TEXT NOT NULL,
  name TEXT NOT NULL, tag TEXT, code TEXT, via_collector TEXT, created_at INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'open', notified INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS link_user_state(discord_user_id INTEGER PRIMARY KEY, out_since INTEGER);
CREATE TABLE IF NOT EXISTS link_mains(discord_user_id INTEGER PRIMARY KEY, guild TEXT NOT NULL, guid TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS link_welcomed(discord_user_id INTEGER PRIMARY KEY, at INTEGER NOT NULL);
"""


@dataclass
class Confirm:
    id: int
    discord_user_id: int
    guild: str
    guid: str
    name: str
    kind: str  # "link" (typed a code) or "alt" (another character of a linked account)


class Links:
    def __init__(self, archive: Archive, now=time.time):
        self.a, self.now = archive, now
        self.db = archive.db
        self.db.executescript(_DDL)
        self.log: list[str] = []  # what process() decided, for the bot's log

    # ------------------------------------------------------------------ codes

    def new_code(self, user_id: int) -> str:
        with self.db:
            while True:
                code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
                if not self.db.execute("SELECT 1 FROM link_codes WHERE code=?", (code,)).fetchone():
                    break
            self.db.execute("INSERT INTO link_codes(code, discord_user_id, created_at) VALUES(?,?,?)",
                            (code, user_id, int(self.now())))
        return code

    # ------------------------------------------------------------------ processing uploads

    def _member(self, guild: str, guid: str | None, sender: str) -> tuple[str, str] | None:
        """(guid, name) of a current guild member matching the sender, or None."""
        if guid:
            r = self.db.execute("SELECT guid, name FROM members WHERE guild=? AND guid=? AND in_guild=1",
                                (guild, guid)).fetchone()
            if r:
                return r["guid"], r["name"]
        for r in self.db.execute("SELECT guid, name FROM members WHERE guild=? AND in_guild=1", (guild,)):
            n = r["name"]
            if sender == n or sender.startswith(n + "-"):  # the sender may carry "-Realm"; never split names
                return r["guid"], n
        return None

    def _open_count(self, user_id: int) -> int:
        return self.db.execute("SELECT COUNT(*) FROM link_confirms WHERE discord_user_id=? AND status='open'",
                               (user_id,)).fetchone()[0]

    def _blocked(self, user_id: int, guild: str, guid: str) -> bool:
        return self.db.execute("SELECT 1 FROM link_blocks WHERE discord_user_id=? AND guild=? AND guid=?",
                               (user_id, guild, guid)).fetchone() is not None

    def _open_confirm(self, user_id: int, guild: str, guid: str, name: str, tag: str | None, code: str | None,
                      via: str | None) -> str:
        if self._blocked(user_id, guild, guid):
            return "blocked by the user"
        if self.db.execute("SELECT 1 FROM link_confirms WHERE discord_user_id=? AND guild=? AND guid=?"
                           " AND status='open'", (user_id, guild, guid)).fetchone():
            return "confirmation already open"
        if self._open_count(user_id) >= MAX_OPEN:
            return f"user has {MAX_OPEN} open confirmations"
        self.db.execute("INSERT INTO link_confirms(discord_user_id, guild, guid, name, tag, code, via_collector,"
                        " created_at) VALUES(?,?,?,?,?,?,?,?)",
                        (user_id, guild, guid, name, tag, code, via, int(self.now())))
        return "confirmation opened"

    def process(self) -> int:
        """Handle uploaded link requests not seen yet. Returns how many confirmations were opened."""
        opened = 0
        rows = self.db.execute("SELECT * FROM link_rows WHERE processed=0 ORDER BY ts_utc").fetchall()
        opened += self._process_chat_codes()
        with self.db:
            for r in rows:
                result = self._process_row(r)
                if result == "confirmation opened":
                    opened += 1
                self.log.append(f"link request {r['kind']} from {r['name']}: {result}")
                self.db.execute("UPDATE link_rows SET processed=1 WHERE guild=? AND id=?", (r["guild"], r["id"]))
        return opened

    def _process_chat_codes(self) -> int:
        """Members without the addon type "!link CODE" in guild chat; a collector archives the line with its text.
        Each chat row is looked at once (by rowid) and then treated like a link request from its author."""
        last = int(self.a.get_state("link.chat_rowid", "0") or 0)
        rows = self.db.execute(
            "SELECT rowid, guild, id, ts_utc, author, guid, text, first_collector FROM chat WHERE rowid>? AND"
            " stream='g' AND text LIKE '%!link %' ORDER BY rowid", (last,)).fetchall()
        top = self.db.execute("SELECT MAX(rowid) FROM chat").fetchone()[0] or 0
        opened = 0
        with self.db:
            for c in rows:
                m = CHAT_CODE.match(c["text"] or "")
                if not m:
                    continue
                req = {"guild": c["guild"], "guid": c["guid"], "name": c["author"], "kind": "chat",
                       "code": m.group(1).upper(), "ts_utc": c["ts_utc"], "tag": None,
                       "first_collector": c["first_collector"]}
                result = self._process_row(req)
                if result == "confirmation opened":
                    opened += 1
                self.log.append(f"link code in guild chat from {c['author']}: {result}")
        if top > last:
            self.a.set_state("link.chat_rowid", str(top))
        return opened

    def _process_row(self, r: Any) -> str:
        guild = r["guild"]
        member = self._member(guild, r["guid"], r["name"])
        if member is None:
            return "sender is not a current guild member"
        guid, name = member
        linked = self.db.execute("SELECT discord_user_id FROM links WHERE guild=? AND guid=?",
                                 (guild, guid)).fetchone()
        if r["kind"] in ("link", "chat"):
            code = self.db.execute("SELECT * FROM link_codes WHERE code=?", (r["code"],)).fetchone()
            if code is None:
                return "unknown code"
            if code["used_at"] is not None:
                return "code already used"
            ttl = CHAT_CODE_TTL if r["kind"] == "chat" else CODE_TTL
            if not (code["created_at"] - 60 <= r["ts_utc"] <= code["created_at"] + ttl):
                return "code expired"
            user = code["discord_user_id"]
            if linked:
                return "already linked" if linked[0] == user else "character is linked to another Discord user"
            return self._open_confirm(user, guild, guid, name, r["tag"], r["code"], r["first_collector"])
        # alt: another character of an account whose tag belongs to a linked user
        owner = self.db.execute("SELECT discord_user_id FROM links WHERE tag=? ORDER BY linked_at LIMIT 1",
                                (r["tag"],)).fetchone()
        if owner is None:
            return "account tag not linked"
        if linked:
            return "already linked"
        return self._open_confirm(owner[0], guild, guid, name, r["tag"], None, r["first_collector"])

    # ------------------------------------------------------------------ confirmations

    def to_notify(self) -> list[Confirm]:
        rows = self.db.execute("SELECT * FROM link_confirms WHERE status='open' AND notified=0 ORDER BY id").fetchall()
        return [Confirm(r["id"], r["discord_user_id"], r["guild"], r["guid"], r["name"],
                        "link" if r["code"] else "alt") for r in rows]

    def mark_notified(self, confirm_id: int, delivered: bool) -> None:
        with self.db:
            self.db.execute("UPDATE link_confirms SET notified=? WHERE id=?", (1 if delivered else 2, confirm_id))

    def open_for(self, user_id: int) -> list[Confirm]:
        rows = self.db.execute("SELECT * FROM link_confirms WHERE status='open' AND discord_user_id=? ORDER BY id",
                               (user_id,)).fetchall()
        return [Confirm(r["id"], r["discord_user_id"], r["guild"], r["guid"], r["name"],
                        "link" if r["code"] else "alt") for r in rows]

    def answer(self, confirm_id: int, user_id: int, accept: bool) -> str:
        """The Discord user's click. Only the user the confirmation belongs to can answer it."""
        r = self.db.execute("SELECT * FROM link_confirms WHERE id=?", (confirm_id,)).fetchone()
        if r is None or r["discord_user_id"] != user_id:
            return "This confirmation is not for you."
        if r["status"] != "open":
            return "This was already answered."
        now = int(self.now())
        with self.db:
            if not accept:
                self.db.execute("UPDATE link_confirms SET status='rejected' WHERE id=?", (confirm_id,))
                self.db.execute("INSERT OR IGNORE INTO link_blocks VALUES(?,?,?)", (user_id, r["guild"], r["guid"]))
                return f"OK, {r['name']} will not be linked to you."
            taken = self.db.execute("SELECT discord_user_id FROM links WHERE guild=? AND guid=?",
                                    (r["guild"], r["guid"])).fetchone()
            if taken and taken[0] != user_id:
                self.db.execute("UPDATE link_confirms SET status='expired' WHERE id=?", (confirm_id,))
                return f"{r['name']} was linked to another Discord account meanwhile."
            self.db.execute("INSERT OR REPLACE INTO links VALUES(?,?,?,?,?,?,?)",
                            (r["guild"], r["guid"], r["name"], user_id, r["tag"], now, r["via_collector"]))
            self.db.execute("UPDATE link_confirms SET status='confirmed' WHERE id=?", (confirm_id,))
            if r["code"]:
                self.db.execute("UPDATE link_codes SET used_at=? WHERE code=?", (now, r["code"]))
        return f"Linked: {r['name']} is now your character."

    # ------------------------------------------------------------------ officer approval, main character

    def find_member(self, name: str) -> list[dict[str, Any]]:
        """Current guild members called `name` (case-insensitive, whole name)."""
        return [dict(r) for r in self.db.execute(
            "SELECT guild, guid, name, level FROM members WHERE in_guild=1 AND lower(name)=lower(?)", (name,))]

    def approve(self, officer_id: int, user_id: int, name: str) -> str:
        """An officer links a current guild member at once (no code, no collector wait)."""
        found = self.find_member(name)
        if not found:
            return f"{name} is not a current guild member (as of the newest member list)."
        if len(found) > 1:
            return f"There are {len(found)} guild members called {name}; ask the member to use /link."
        m = found[0]
        taken = self.db.execute("SELECT discord_user_id FROM links WHERE guild=? AND guid=?",
                                (m["guild"], m["guid"])).fetchone()
        if taken:
            return (f"{m['name']} is already linked to this user." if taken[0] == user_id
                    else f"{m['name']} is linked to another Discord user; unlink it first.")
        with self.db:
            self.db.execute("INSERT INTO links VALUES(?,?,?,?,?,?,?)",
                            (m["guild"], m["guid"], m["name"], user_id, None, int(self.now()),
                             f"approved by {officer_id}"))
            self.db.execute("DELETE FROM link_blocks WHERE discord_user_id=? AND guild=? AND guid=?",
                            (user_id, m["guild"], m["guid"]))
        return f"Linked: {m['name']} is now a character of this user (approved by you)."

    def set_main(self, user_id: int, name: str | None) -> str:
        if not name:
            with self.db:
                self.db.execute("DELETE FROM link_mains WHERE discord_user_id=?", (user_id,))
            return "Main character cleared: your highest-level character counts as main."
        r = self.db.execute("SELECT guild, guid, name FROM links WHERE discord_user_id=? AND lower(name)=lower(?)",
                            (user_id, name)).fetchone()
        if r is None:
            return f"{name} is not one of your linked characters (see /link)."
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO link_mains VALUES(?,?,?)", (user_id, r["guild"], r["guid"]))
        return f"Main character: {r['name']}."

    def main_of(self, user_id: int) -> dict[str, Any] | None:
        """The main: the one the user chose (if still linked and in the guild), else the highest level in the guild."""
        r = self.db.execute(
            "SELECT l.name, l.guid, l.guild FROM link_mains x JOIN links l ON l.discord_user_id=x.discord_user_id"
            " AND l.guild=x.guild AND l.guid=x.guid JOIN members m ON m.guild=l.guild AND m.guid=l.guid"
            " WHERE x.discord_user_id=? AND m.in_guild=1", (user_id,)).fetchone()
        if r is None:
            r = self.db.execute(
                "SELECT l.name, l.guid, l.guild FROM links l JOIN members m ON m.guild=l.guild AND m.guid=l.guid"
                " WHERE l.discord_user_id=? AND m.in_guild=1 ORDER BY m.level DESC, l.linked_at LIMIT 1",
                (user_id,)).fetchone()
        return dict(r) if r else None

    def first_link_done(self, user_id: int) -> bool:
        """True exactly once: the first time a user has a confirmed link (role menus, public line)."""
        if not self.db.execute("SELECT 1 FROM links WHERE discord_user_id=?", (user_id,)).fetchone():
            return False
        with self.db:
            cur = self.db.execute("INSERT OR IGNORE INTO link_welcomed VALUES(?,?)", (user_id, int(self.now())))
        return cur.rowcount == 1

    # ------------------------------------------------------------------ queries and unlinking

    def unlink(self, user_id: int, name: str | None = None) -> int:
        with self.db:
            if name:
                cur = self.db.execute("DELETE FROM links WHERE discord_user_id=? AND lower(name)=lower(?)",
                                      (user_id, name))
            else:
                cur = self.db.execute("DELETE FROM links WHERE discord_user_id=?", (user_id,))
                self.db.execute("UPDATE link_confirms SET status='expired' WHERE discord_user_id=? AND status='open'",
                                (user_id,))
        return cur.rowcount

    def chars(self, user_id: int) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT l.name, l.guid, l.guild, m.in_guild, m.level, m.class, m.rank_name, m.last_seen, l.via_collector"
            " FROM links l"
            " LEFT JOIN members m ON m.guild=l.guild AND m.guid=l.guid WHERE l.discord_user_id=? ORDER BY l.name",
            (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def search_members(self, text: str, limit: int = 25) -> list[str]:
        """Guild member names for autocomplete: names starting with the text first, then names containing it."""
        t = (text or "").strip().lower()
        rows = [r[0] for r in self.db.execute(
            "SELECT DISTINCT name FROM members WHERE in_guild=1 AND instr(lower(name), ?) > 0"
            " ORDER BY (instr(lower(name), ?) = 1) DESC, name COLLATE NOCASE LIMIT ?", (t, t, limit))]
        return rows

    def lookup(self, name: str) -> list[dict[str, Any]]:
        """/whois: guild characters called `name` (also ones who left), with the Discord user if linked."""
        return [dict(r) for r in self.db.execute(
            "SELECT m.name, m.level, m.class, m.rank_name, m.in_guild, m.last_seen, l.discord_user_id AS uid"
            " FROM members m LEFT JOIN links l ON l.guild=m.guild AND l.guid=m.guid WHERE lower(m.name)=lower(?)"
            " ORDER BY m.in_guild DESC", (name,))]

    def whois(self, name: str) -> list[tuple[int, str]]:
        return [(r[0], r[1]) for r in self.db.execute(
            "SELECT discord_user_id, name FROM links WHERE lower(name)=lower(?)", (name,))]

    def status(self) -> dict[str, Any]:
        linked = self.db.execute("SELECT COUNT(*) FROM members m WHERE m.in_guild=1 AND EXISTS"
                                 " (SELECT 1 FROM links l WHERE l.guild=m.guild AND l.guid=m.guid)").fetchone()[0]
        total = self.db.execute("SELECT COUNT(*) FROM members WHERE in_guild=1").fetchone()[0]
        users = self.db.execute("SELECT COUNT(DISTINCT discord_user_id) FROM links").fetchone()[0]
        unlinked = [r[0] for r in self.db.execute(
            "SELECT name FROM members m WHERE in_guild=1 AND NOT EXISTS"
            " (SELECT 1 FROM links l WHERE l.guild=m.guild AND l.guid=m.guid) ORDER BY name")]
        return {"members": total, "linked": linked, "users": users, "unlinked": unlinked}

    # ------------------------------------------------------------------ roles (decision 5; off unless configured)

    def desired_rank(self, user_id: int) -> tuple[str | None, bool]:
        """Best guild rank among the user's characters in the guild (lowest rank index), and whether any is in."""
        r = self.db.execute(
            "SELECT m.rank_name FROM links l JOIN members m ON m.guild=l.guild AND m.guid=l.guid"
            " WHERE l.discord_user_id=? AND m.in_guild=1 ORDER BY m.rank_index LIMIT 1", (user_id,)).fetchone()
        return (r[0] if r else None), r is not None

    def out_of_guild_since(self, user_id: int) -> int | None:
        """When the user's last character left (tracked by role sync), None while one is in the guild."""
        _, inside = self.desired_rank(user_id)
        now = int(self.now())
        with self.db:
            if inside:
                self.db.execute("DELETE FROM link_user_state WHERE discord_user_id=?", (user_id,))
                return None
            self.db.execute("INSERT OR IGNORE INTO link_user_state VALUES(?, ?)", (user_id, now))
        return self.db.execute("SELECT out_since FROM link_user_state WHERE discord_user_id=?",
                               (user_id,)).fetchone()[0]

    def linked_users(self) -> list[int]:
        return [r[0] for r in self.db.execute("SELECT DISTINCT discord_user_id FROM links")]

    def main_name(self, user_id: int) -> str | None:
        """Nickname: the main's whole name (decision 2), see main_of."""
        m = self.main_of(user_id)
        return m["name"] if m else None

    # ------------------------------------------------------------------ role settings (set with /roles in Discord)

    def role_settings(self, cfg_verified: int = 0, cfg_ranks: dict[str, int] | None = None) -> tuple[int, dict[str, int]]:
        """(verified role ID, {guild rank name: role ID}). Settings made with /roles win over config.toml."""
        v = self.a.get_state("link.verified_role")
        verified = int(v) if v not in (None, "") else int(cfg_verified or 0)
        r = self.a.get_state("link.rank_roles")
        ranks = {str(k): int(x) for k, x in json.loads(r).items()} if r else dict(cfg_ranks or {})
        return verified, ranks

    def set_verified_role(self, role_id: int | None) -> None:
        self.a.set_state("link.verified_role", str(role_id or 0))

    def set_rank_role(self, rank: str, role_id: int | None, cfg_ranks: dict[str, int] | None = None) -> None:
        _, ranks = self.role_settings(0, cfg_ranks)
        if role_id:
            ranks[rank] = int(role_id)
        else:
            ranks.pop(rank, None)
        self.a.set_state("link.rank_roles", json.dumps(ranks, sort_keys=True))

    def guild_ranks(self) -> list[tuple[str, int | None, int]]:
        """Guild ranks as the newest member list has them: (name, rank index, members), highest rank first."""
        return [(r[0], r[1], r[2]) for r in self.db.execute(
            "SELECT rank_name, MIN(rank_index), COUNT(*) FROM members WHERE in_guild=1 AND rank_name IS NOT NULL"
            " GROUP BY rank_name ORDER BY MIN(rank_index), rank_name")]
