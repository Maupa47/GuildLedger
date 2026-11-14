"""Shared harness: the real addon files under plain Lua 5.1 (lupa), like WoW, against wowstub.lua."""

import sys
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa.lua51")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "companion"))
from guildledger.store import Spool  # noqa: E402
from guildledger.svparse import parse  # noqa: E402

ADDON_DIR = (ROOT / "addon" / "GuildLedger").as_posix()
STUB = (Path(__file__).parent / "wowstub.lua").as_posix()
FILES = ["Compat.lua", "Store.lua", "Core.lua", "Comms.lua", "Chat.lua", "Roster.lua", "Relay.lua", "Map.lua", "Link.lua", "API.lua"]  # TOC order

ALIA = ("Alia Testwood", "Player-1111-0000AAAA")
BRAM = ("Bram Exampleson", "Player-1111-0000BBBB")
CORA = ("Cora Sample", "Player-1111-0000CCCC")


class Game:
    def __init__(self, history=0, club=True, members=0, role="collector", name="Testa Collector"):
        self.L = lupa.LuaRuntime(unpack_returned_tuples=True)
        self.W = self.L.eval(f"dofile([[{STUB}]])")
        # Each player's own random numbers, as on real clients (unseeded runtimes would all draw the same waits).
        self.L.execute(f"math.randomseed({sum(ord(c) * (i + 1) for i, c in enumerate(name)) % 2147483647})")
        self.name = name
        self.L.execute(f"function UnitName(u) if u == 'player' then return W.lockdown and W.SECRET or [[{name}]] end end")
        if role:  # an existing install with this role; role=None = brand-new install (defaults)
            self.L.execute(f"GuildLedgerDB = {{ schema = 3, opts = {{ collector = {str(role == 'collector').lower()} }} }}")
        if not club:
            self.W.clubId = None
        for i in range(members):  # roster before this collector ever logged in
            self.W.addMember(f"Member{i:03d} Rostered", f"Player-1111-{i:08X}",
                             self.L.table_from({"online": i % 4 == 0}))
        for i in range(history):  # chat written before this collector ever logged in
            who = (ALIA, BRAM, CORA)[i % 3]
            self.W.addHistory(1, who[0], who[1], self.W.server - (history - i) * 30)
        self.W.downloaded[1] = min(history, 100)  # the client holds ~100 after login
        self.load()

    def load(self):
        self.W.loadAddon(ADDON_DIR, self.L.table_from(FILES), "GuildLedger")
        self.W.login()

    def reload(self):
        sv = self.sv_text()
        self.W.unload()
        self.L.execute("GuildLedgerDB = nil")
        self.L.execute(sv)  # what WoW reads back from disk
        self.load()

    def offline(self, seconds, change=None):
        """Log out, let `change()` happen in the guild while away, log back in after `seconds`."""
        sv = self.sv_text()
        self.W.logout()
        self.L.execute("GuildLedgerDB = nil")
        self.W.advance(seconds / 2)
        if change:
            change()
        self.W.advance(seconds / 2)
        self.L.execute(sv)
        self.load()

    def run(self, seconds):
        self.W.advance(seconds)

    def say(self, who, text, sid=1, **opts):
        return self.W.say(sid, who[0], who[1], text, self.L.table_from(opts))

    def sv_text(self):
        return self.W.savedVariables("GuildLedgerDB")

    def sv(self):
        return parse(self.sv_text())["GuildLedgerDB"]

    def guild(self):
        return self.sv()["guilds"]["42"]

    def events(self):
        ev = self.guild().get("ev") or []
        return ev if isinstance(ev, list) else list(ev.values())

    def chat(self):
        g = self.sv()["guilds"]["42"]
        rows = g.get("chat") or []
        return rows if isinstance(rows, list) else list(rows.values())

    def slash(self, cmd):
        return self.W.slash(cmd)

    @property
    def errors(self):
        return self.W.ns.errors

    def last_error(self):
        return self.W.ns.lastError


def by_src(rows, src):
    return [r for r in rows if r["src"] == src]


