"""D2 role menus (docs/dev/archive/PLAN_COMMUNITY.md). No Discord."""

import pytest

from guildledger_bot.community.rolemenus import LANGUAGES, MAX_ENTRIES, RoleMenus
from guildledger_bot.store import Archive


@pytest.fixture
def rm(tmp_path):
    a = Archive(tmp_path / "a.db")
    yield RoleMenus(a)
    a.close()


def test_selection_adds_and_removes_only_menu_roles(rm):
    rm.add("interests", "Raids", 11)
    rm.add("interests", "PvP", 12)
    rm.add("interests", "Social", 13)
    have = {12, 13, 99}  # 99: a role outside the menu (e.g. a rank role)
    p = rm.plan("interests", ["Raids", "Social"], have, existing={11, 12, 13, 99})
    assert p.add == [11] and p.remove == [12] and p.create == []
    p = rm.plan("interests", [], have, existing={11, 12, 13, 99})
    assert sorted(p.remove) == [12, 13] and 99 not in p.remove


def test_deleted_role_is_made_again(rm):
    rm.add("interests", "Raids", 11)
    p = rm.plan("interests", ["Raids"], set(), existing=set())
    assert p.create == ["Raids"] and p.add == []
    rm.forget_role(11)
    assert rm.entries("interests")[0].role_id is None


def test_language_preset_creates_roles_on_first_pick(rm):
    assert rm.preset("languages") == len(LANGUAGES) == 20
    assert rm.preset("languages") == 0, "registered once"
    p = rm.plan("languages", ["Deutsch", "Français"], set(), existing=set())
    assert p.create == ["Deutsch", "Français"]
    rm.set_role("languages", "Deutsch", 500)
    p = rm.plan("languages", ["Deutsch"], set(), existing={500})
    assert p.add == [500] and p.create == []


def test_limits_and_unknown_group(rm):
    assert "Unknown group" in rm.add("colours", "Red", 1)
    for i in range(MAX_ENTRIES):
        rm.add("interests", f"I{i}", 100 + i)
    assert "25 entries" in rm.add("interests", "One more", 999)
    assert "updated" in rm.add("interests", "I0", 100, "🎯"), "changing an entry is not a new one"
    assert "already in a menu" in rm.add("languages", "Deutsch", 101)


def test_remove_and_groups(rm):
    assert rm.groups() == []
    rm.add("languages", "English", 7)
    assert rm.groups() == ["languages"]
    assert rm.remove("languages", "english") and rm.groups() == []
