"""Sign-up in Discord (docs/dev/archive/PLAN_COMMUNITY.md D1): the bot check behind the Verify button and the welcome.

Pure database logic, no Discord. A click on Verify gives a small task: five buttons in random order, the text
names one. The right answer stays here (table gate_tasks), never in a button's id: the buttons only carry their
position. Three wrong tries lock the user out for ten minutes; a task expires after two minutes; an account
younger than the set minimum age is told to ask an officer.
This keeps scripted accounts out. The proof that someone belongs to the guild is the link (link.py).
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass

from ..store import Archive

# (button label, how the task names it). Plain words and emoji: readable for people, dull for scripts.
SYMBOLS = [("🍎", "the apple"), ("🐟", "the fish"), ("🌙", "the moon"), ("🔑", "the key"), ("🎲", "the dice"),
           ("🌲", "the tree"), ("⚔️", "the swords"), ("🛡️", "the shield"), ("🍄", "the mushroom"), ("🐉", "the dragon"),
           ("🔥", "the fire"), ("❄️", "the snowflake"), ("🏹", "the bow"), ("🧪", "the potion"), ("🐺", "the wolf")]
CHOICES = 5
TASK_TTL = 120
MAX_TRIES = 3
LOCK_SECONDS = 600

_DDL = """
CREATE TABLE IF NOT EXISTS gate_tasks(
  user_id INTEGER PRIMARY KEY, options TEXT NOT NULL, answer INTEGER NOT NULL, created_at INTEGER NOT NULL,
  tries INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS gate_locks(user_id INTEGER PRIMARY KEY, until INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS gate_passed(user_id INTEGER PRIMARY KEY, at INTEGER NOT NULL);
"""


@dataclass
class Task:
    status: str            # "task", "locked", "young"
    text: str = ""
    labels: list[str] | None = None
    wait: int = 0          # seconds until the lock ends (locked)


@dataclass
class Result:
    status: str            # "passed", "wrong", "locked", "expired", "none"
    text: str
    tries_left: int = 0


class Gate:
    def __init__(self, archive: Archive, now=time.time, rng: random.Random | None = None):
        self.a, self.now = archive, now
        self.rng = rng or random.SystemRandom()
        self.db = archive.db
        self.db.executescript(_DDL)

    def _locked_for(self, user_id: int) -> int:
        r = self.db.execute("SELECT until FROM gate_locks WHERE user_id=?", (user_id,)).fetchone()
        left = (r[0] - int(self.now())) if r else 0
        return max(0, left)

    def new_task(self, user_id: int, account_created: float | None = None, min_age_days: int = 0) -> Task:
        wait = self._locked_for(user_id)
        if wait:
            return Task("locked", f"Too many wrong tries. Try again in {wait // 60 + 1} minute(s).", wait=wait)
        if min_age_days and account_created is not None and self.now() - account_created < min_age_days * 86400:
            return Task("young", f"Your Discord account is newer than {min_age_days} day(s). Please ask an"
                                 " officer to let you in.")
        picks = self.rng.sample(range(len(SYMBOLS)), CHOICES)
        answer = self.rng.randrange(CHOICES)
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO gate_tasks(user_id, options, answer, created_at, tries)"
                            " VALUES(?,?,?,?,0)", (user_id, json.dumps(picks), answer, int(self.now())))
        return Task("task", f"Quick check that you are a person: press **{SYMBOLS[picks[answer]][1]}**.",
                    [SYMBOLS[i][0] for i in picks])

    def check(self, user_id: int, position: int) -> Result:
        """The user pressed the button at `position` (0..4) of their current task."""
        wait = self._locked_for(user_id)
        if wait:
            return Result("locked", f"Too many wrong tries. Try again in {wait // 60 + 1} minute(s).")
        r = self.db.execute("SELECT * FROM gate_tasks WHERE user_id=?", (user_id,)).fetchone()
        if r is None:
            return Result("none", "This check is over. Press **Verify** again.")
        now = int(self.now())
        if now - r["created_at"] > TASK_TTL:
            with self.db:
                self.db.execute("DELETE FROM gate_tasks WHERE user_id=?", (user_id,))
            return Result("expired", "This check took too long. Press **Verify** again.")
        if position == r["answer"]:
            with self.db:
                self.db.execute("DELETE FROM gate_tasks WHERE user_id=?", (user_id,))
                self.db.execute("INSERT OR REPLACE INTO gate_passed VALUES(?,?)", (user_id, now))
            return Result("passed", "Thanks, you are in.")
        tries = r["tries"] + 1
        with self.db:
            if tries >= MAX_TRIES:
                self.db.execute("DELETE FROM gate_tasks WHERE user_id=?", (user_id,))
                self.db.execute("INSERT OR REPLACE INTO gate_locks VALUES(?,?)", (user_id, now + LOCK_SECONDS))
                return Result("locked", f"That was not it, {MAX_TRIES} times. Try again in"
                                        f" {LOCK_SECONDS // 60} minutes.")
            self.db.execute("UPDATE gate_tasks SET tries=? WHERE user_id=?", (tries, user_id))
        named = SYMBOLS[json.loads(r["options"])[r["answer"]]][1]
        return Result("wrong", f"That was not it ({MAX_TRIES - tries} tr{'y' if MAX_TRIES - tries == 1 else 'ies'}"
                               f" left). Press **{named}**.", MAX_TRIES - tries)

    def passed(self, user_id: int) -> bool:
        return self.db.execute("SELECT 1 FROM gate_passed WHERE user_id=?", (user_id,)).fetchone() is not None


# ------------------------------------------------------------------------------------------- welcome

DEFAULT_WELCOME = ("Welcome to the guild's Discord! To see the guild channels, link your WoW character to"
                   " your Discord account. It takes a minute.")


def welcome_text(custom: str | None, addon_url: str | None) -> str:
    """The private welcome: the admin's text, the addon link and the three link steps."""
    parts = [(custom or DEFAULT_WELCOME).strip()]
    steps = ["**Link your character:**",
             "1. Press **Get my link code** below (or type `/link` here).",
             "2. In WoW, type `/gl link CODE` on your character"
             + (f" (needs the guild's addon pack: {addon_url})." if addon_url else " (needs the guild's addon pack)."),
             "   No addon? Write `!link CODE` in guild chat instead (the code works 10 minutes).",
             "3. I send you a message: press **Confirm**. Your other characters follow by themselves."]
    parts.append("\n".join(steps))
    return "\n\n".join(parts)[:1990]
