"""The Discord side of D1-D3 with fake Discord objects (no connection). Synthetic data only."""

import asyncio
from types import SimpleNamespace

import pytest

dpy = pytest.importorskip("discord")

from guildledger_bot.community import directory_ui, rolemenus_ui  # noqa: E402
from guildledger_bot.community.directory import Directory  # noqa: E402
from guildledger_bot.community.link import Links  # noqa: E402
from guildledger_bot.community.rolemenus import RoleMenus  # noqa: E402
from guildledger_bot.community.settings import Settings  # noqa: E402
from guildledger_bot.store import Archive  # noqa: E402

T0 = 1794355200


class FakeBot:
    def __init__(self, a):
        self.cfg = SimpleNamespace(grace_days=7, verified_role_id=0, rank_roles={})
        self._settings = Settings(a)
        self._menus = RoleMenus(a)
        self._links = Links(a)
        self._directory = Directory(a, now=lambda: T0)
        self._menu_refusal_logged = False
        self.ops = []
        self.channels = {}

    async def _db(self, fn, *args):
        return fn(*args)

    async def ops_line(self, text):
        self.ops.append(text)

    async def setting(self, key, default=None):
        return self._settings.get(key, default)

    def get_channel(self, cid):
        return self.channels.get(cid)

    async def fetch_channel(self, cid):
        raise dpy.NotFound(SimpleNamespace(status=404, reason="x"), "gone")


class Role(SimpleNamespace):
    pass


class Guild:
    def __init__(self, roles, refuse=False):
        self.roles = roles
        self.refuse = refuse
        self.made = []

    def get_role(self, i):
        return next((r for r in self.roles if r.id == i), None)

    async def create_role(self, name, **kw):
        assert kw["permissions"].value == 0 and kw["mentionable"] is False
        r = Role(id=1000 + len(self.made), name=name)
        self.made.append(r)
        self.roles.append(r)
        return r


class Member:
    def __init__(self, roles, refuse=False):
        self.roles = list(roles)
        self.refuse = refuse
        self.id = 77

    async def add_roles(self, *roles, reason=None):
        if self.refuse:
            raise dpy.Forbidden(SimpleNamespace(status=403, reason="x"), "no")
        self.roles += roles

    async def remove_roles(self, *roles, reason=None):
        self.roles = [r for r in self.roles if r not in roles]


@pytest.fixture
def bot(tmp_path):
    a = Archive(tmp_path / "a.db")
    yield FakeBot(a)
    a.close()


def test_role_panel_selection_makes_and_gives_roles(bot):
    rank = Role(id=5, name="Officer")
    raids = Role(id=11, name="Raids")
    guild = Guild([rank, raids, Role(id=600, name="Deutsch")])
    bot._menus.add("interests", "Raids", 11)
    bot._menus.add("interests", "PvP", 12)  # role 12 was deleted in Discord
    bot._menus.preset("languages")
    m = Member([rank])
    inter = SimpleNamespace(guild=guild, user=m)
    text = asyncio.run(rolemenus_ui.apply_selection(bot, inter, "interests", ["Raids", "PvP"]))
    assert "Raids" in text and "PvP" in text
    assert [r.name for r in guild.made] == ["PvP"]
    text = asyncio.run(rolemenus_ui.apply_selection(bot, inter, "languages", ["Deutsch"]))
    assert [r.name for r in guild.made] == ["PvP"], "a hand-made role with the same name is used"
    assert {r.name for r in m.roles} == {"Officer", "Raids", "PvP", "Deutsch"}
    asyncio.run(rolemenus_ui.apply_selection(bot, inter, "interests", []))
    assert {r.name for r in m.roles} == {"Officer", "Deutsch"}, "only the menu's roles were taken"
    assert asyncio.run(rolemenus_ui.apply_selection(bot, inter, "interests", [])) == "Nothing changed."


def test_refused_role_change_is_told_and_logged_once(bot):
    guild = Guild([Role(id=11, name="Raids")])
    bot._menus.add("interests", "Raids", 11)
    inter = SimpleNamespace(guild=guild, user=Member([], refuse=True))
    for _ in range(2):
        text = asyncio.run(rolemenus_ui.apply_selection(bot, inter, "interests", ["Raids"]))
        assert "did not let me" in text
    assert len(bot.ops) == 1


def test_panel_has_one_menu_per_group(bot):
    async def go():
        bot._menus.add("interests", "Raids", 11)
        bot._menus.preset("languages")
        view = await rolemenus_ui.panel_view(bot)
        return [(c.item.custom_id, len(c.item.options), c.item.min_values, c.item.max_values) for c in view.children]
    assert asyncio.run(go()) == [("gl:rm:interests", 1, 0, 1), ("gl:rm:languages", 20, 0, 20)]


def test_counter_names():
    from guildledger_bot.community.counters import names
    assert names({"members": 512, "linked": 140}) == {"members": "Guild members: 512", "linked": "Linked: 140"}


# ------------------------------------------------------------------------------------------- forum

class FakeThread(dpy.Thread):
    def __init__(self, tid, name, tags):  # noqa: D107 - no super(): a plain fake
        self.id, self._name, self._tags, self.archived = tid, name, tags, False
        self.sent, self.edits, self.deleted = [], [], False

    @property
    def name(self):
        return self._name

    @property
    def applied_tags(self):
        return self._tags

    async def edit(self, **kw):
        self.edits.append(kw)
        self._name = kw.get("name", self._name)
        self._tags = kw.get("applied_tags", self._tags)
        self.archived = kw.get("archived", self.archived)

    async def send(self, text, **kw):
        self.sent.append(text)
        return SimpleNamespace(id=self.id * 100 + len(self.sent))

    def get_partial_message(self, mid):
        thread = self

        class P:
            async def edit(self, content, **kw):
                thread.edits.append({"message": mid, "content": content})

            async def delete(self):
                thread.edits.append({"deleted": mid})
        return P()

    async def delete(self):
        self.deleted = True


class FakeForum(dpy.ForumChannel):
    def __init__(self, bot, tags):  # noqa: D107
        self.bot, self.tags, self.made = bot, tags, []

    @property
    def available_tags(self):
        return self.tags

    async def create_thread(self, name, content, applied_tags, allowed_mentions):
        assert allowed_mentions is not None and len(name) <= 100 and len(content) <= 2000
        t = FakeThread(5000 + len(self.made), name, applied_tags)
        self.made.append(t)
        self.bot.channels[t.id] = t
        return SimpleNamespace(thread=t, message=SimpleNamespace(id=t.id))


def test_forum_round_writes_then_edits_only_the_changed_post(bot):
    a = bot._links.a
    with a.db:
        a.import_roster("42", T0, [{"g": "P-1", "n": "Ann One", "r": 2, "rn": "Officer", "l": 60, "c": "PRIEST"},
                                   {"g": "P-2", "n": "Bob Two", "r": 5, "rn": "Member", "l": 30, "c": "MAGE"}])
        a.db.execute("INSERT INTO links VALUES('42','P-1','Ann One',77,NULL,?, 'Col')", (T0,))
    priest = SimpleNamespace(id=9, name="Priest")
    forum = FakeForum(bot, [priest])
    bot.channels[1] = forum
    bot._settings.set("directory.forum", 1)
    assert asyncio.run(directory_ui.directory_round(bot)) == 3  # help, Ann's post, "Not linked yet: A-C"
    titles = sorted(t.name for t in forum.made)
    assert titles == ["Ann One", "How to find a character", "Not linked yet: A-C"]
    ann = next(t for t in forum.made if t.name == "Ann One")
    assert ann.applied_tags == [priest]
    assert asyncio.run(directory_ui.directory_round(bot)) == 0
    with a.db:
        a.db.execute("UPDATE members SET rank_name='Veteran' WHERE guid='P-1'")
    assert asyncio.run(directory_ui.directory_round(bot)) == 1
    assert any("Veteran" in e.get("content", "") for e in ann.edits)
    # deleted by hand in Discord: made again
    del bot.channels[ann.id]
    with a.db:
        a.db.execute("UPDATE members SET level=61 WHERE guid='P-1'")
    assert asyncio.run(directory_ui.directory_round(bot)) == 1
    assert len([t for t in forum.made if t.name == "Ann One"]) == 2
