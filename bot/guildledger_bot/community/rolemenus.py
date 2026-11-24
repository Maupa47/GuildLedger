"""Role menus (docs/dev/PLAN_COMMUNITY.md D2): interest and language roles a member picks from a panel.

Pure database logic, no Discord. One group = one multi-select on the panel (at most 25 entries). A member's
selection adds and removes only roles registered in that group, never any other role. Language roles from the
preset start without a Discord role: the role is made the first time a member picks it (or an existing role
with the same name is used), so the server does not get twenty empty roles.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..store import Archive

MAX_ENTRIES = 25
GROUPS = {"interests": "Interests", "languages": "Languages"}

INTERESTS = ["Raids", "Dungeons", "PvP", "Levelling", "Crafting", "Social"]  # decision 3 (default)
# decision 4: the major European languages, each in its own spelling
LANGUAGES = ["English", "Deutsch", "Français", "Español", "Italiano", "Português", "Nederlands", "Polski",
             "Русский", "Українська", "Svenska", "Dansk", "Norsk", "Suomi", "Čeština", "Magyar", "Română",
             "Ελληνικά", "Türkçe", "Other"]

_DDL = """
CREATE TABLE IF NOT EXISTS rolemenu(
  grp TEXT NOT NULL, label TEXT NOT NULL, role_id INTEGER, emoji TEXT, pos INTEGER NOT NULL,
  PRIMARY KEY (grp, label));
"""


@dataclass
class Entry:
    grp: str
    label: str
    role_id: int | None
    emoji: str | None


@dataclass
class Plan:
    add: list[int]          # role IDs to give
    remove: list[int]       # role IDs to take
    create: list[str]       # labels whose role must be made (or found by name) first


class RoleMenus:
    def __init__(self, archive: Archive):
        self.db = archive.db
        self.db.executescript(_DDL)

    def entries(self, grp: str) -> list[Entry]:
        return [Entry(r["grp"], r["label"], r["role_id"], r["emoji"]) for r in self.db.execute(
            "SELECT * FROM rolemenu WHERE grp=? ORDER BY pos, label", (grp,))]

    def groups(self) -> list[str]:
        return [g for g in GROUPS if self.entries(g)]

    def add(self, grp: str, label: str, role_id: int | None, emoji: str | None = None) -> str:
        if grp not in GROUPS:
            return f"Unknown group {grp}: use one of {', '.join(GROUPS)}."
        label = label.strip()[:80]
        if not label:
            return "The label is empty."
        exists = self.db.execute("SELECT pos FROM rolemenu WHERE grp=? AND label=?", (grp, label)).fetchone()
        if exists is None and len(self.entries(grp)) >= MAX_ENTRIES:
            return f"{GROUPS[grp]} already has {MAX_ENTRIES} entries (Discord's limit for one menu)."
        if role_id and self.db.execute("SELECT 1 FROM rolemenu WHERE role_id=? AND NOT (grp=? AND label=?)",
                                       (role_id, grp, label)).fetchone():
            return "That role is already in a menu."
        pos = exists[0] if exists else (self.db.execute("SELECT COALESCE(MAX(pos), -1) + 1 FROM rolemenu WHERE grp=?",
                                                        (grp,)).fetchone()[0])
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO rolemenu VALUES(?,?,?,?,?)", (grp, label, role_id, emoji, pos))
        return f"{GROUPS[grp]}: **{label}** " + ("added." if exists is None else "updated.")

    def remove(self, grp: str, label: str) -> bool:
        with self.db:
            cur = self.db.execute("DELETE FROM rolemenu WHERE grp=? AND lower(label)=lower(?)", (grp, label))
        return cur.rowcount > 0

    def preset(self, grp: str) -> int:
        """Register the default list of a group (roles made on first pick). Returns how many were new."""
        labels = LANGUAGES if grp == "languages" else INTERESTS
        n = 0
        for label in labels:
            if not self.db.execute("SELECT 1 FROM rolemenu WHERE grp=? AND label=?", (grp, label)).fetchone():
                if self.add(grp, label, None).endswith("added."):
                    n += 1
        return n

    def set_role(self, grp: str, label: str, role_id: int) -> None:
        with self.db:
            self.db.execute("UPDATE rolemenu SET role_id=? WHERE grp=? AND label=?", (role_id, grp, label))

    def forget_role(self, role_id: int) -> None:
        """A role was deleted in Discord: the entry stays, its role is made again on the next pick."""
        with self.db:
            self.db.execute("UPDATE rolemenu SET role_id=NULL WHERE role_id=?", (role_id,))

    def plan(self, grp: str, selected: list[str], have: set[int], existing: set[int]) -> Plan:
        """What one member's selection changes. `have` = the member's role IDs, `existing` = the server's."""
        entries = self.entries(grp)
        chosen = set(selected)
        add, remove, create = [], [], []
        for e in entries:
            alive = e.role_id is not None and e.role_id in existing
            if e.label in chosen:
                if not alive:
                    create.append(e.label)
                elif e.role_id not in have:
                    add.append(e.role_id)
            elif alive and e.role_id in have:
                remove.append(e.role_id)
        return Plan(add, remove, create)
