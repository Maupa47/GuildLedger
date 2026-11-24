"""D1 bot check and welcome (docs/dev/PLAN_COMMUNITY.md). No Discord."""

import random

import pytest

from guildledger_bot.community import onboarding as ob
from guildledger_bot.community.settings import Settings
from guildledger_bot.store import Archive

T0 = 1794355200
U = 5005


class Clock:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t


@pytest.fixture
def gate(tmp_path):
    a = Archive(tmp_path / "a.db")
    clock = Clock()
    yield ob.Gate(a, now=clock, rng=random.Random(7)), clock, a
    a.close()


def answer_of(g, user):
    return g.db.execute("SELECT answer FROM gate_tasks WHERE user_id=?", (user,)).fetchone()[0]


def test_task_has_five_different_buttons_and_names_one(gate):
    g, clock, _ = gate
    t = g.new_task(U)
    assert t.status == "task" and len(t.labels) == 5 and len(set(t.labels)) == 5
    named = dict(ob.SYMBOLS)
    right = t.labels[answer_of(g, U)]
    assert named[right] in t.text


def test_right_button_passes(gate):
    g, clock, _ = gate
    g.new_task(U)
    assert g.check(U, answer_of(g, U)).status == "passed"
    assert g.passed(U)
    assert g.check(U, 0).status == "none", "a task is used once"


def test_three_wrong_tries_lock_for_ten_minutes(gate):
    g, clock, _ = gate
    g.new_task(U)
    wrong = (answer_of(g, U) + 1) % 5
    assert g.check(U, wrong).tries_left == 2
    assert g.check(U, wrong).tries_left == 1
    assert g.check(U, wrong).status == "locked"
    assert g.new_task(U).status == "locked"
    clock.t += ob.LOCK_SECONDS - 5
    assert g.new_task(U).status == "locked"
    clock.t += 10
    assert g.new_task(U).status == "task"


def test_task_expires(gate):
    g, clock, _ = gate
    g.new_task(U)
    clock.t += ob.TASK_TTL + 1
    assert g.check(U, answer_of(g, U)).status == "expired", "even the right button is too late"


def test_young_account_is_sent_to_an_officer(gate):
    g, clock, _ = gate
    assert g.new_task(U, account_created=T0 - 86400, min_age_days=7).status == "young"
    assert g.new_task(U, account_created=T0 - 8 * 86400, min_age_days=7).status == "task"
    assert g.new_task(U, account_created=T0 - 86400, min_age_days=0).status == "task"


def test_new_task_replaces_the_old_one(gate):
    g, clock, _ = gate
    g.new_task(U)
    first = answer_of(g, U)
    for _ in range(10):
        g.new_task(U)
    assert g.db.execute("SELECT COUNT(*) FROM gate_tasks").fetchone()[0] == 1
    assert isinstance(first, int)


def test_welcome_has_the_steps_and_the_addon_link():
    text = ob.welcome_text(None, "https://example.invalid/pack")
    assert ob.DEFAULT_WELCOME in text and "/gl link CODE" in text and "!link CODE" in text
    assert "https://example.invalid/pack" in text
    assert ob.welcome_text("Hi **there**", None).startswith("Hi **there**")
    assert len(ob.welcome_text("x" * 5000, None)) <= 1990


def test_settings_round_trip(tmp_path):
    a = Archive(tmp_path / "s.db")
    s = Settings(a)
    assert s.get("gate.role") is None and s.get_bool("nickname", True) is True
    s.set("gate.role", 123)
    s.set("nickname", False)
    s.set("welcome.text", "Grüße ✨")
    assert s.get_int("gate.role") == 123 and s.get_bool("nickname", True) is False
    assert Settings(a).get("welcome.text") == "Grüße ✨"
    s.set("gate.role", None)
    assert s.get("gate.role") is None and "gate.role" not in s.all()
    a.close()
