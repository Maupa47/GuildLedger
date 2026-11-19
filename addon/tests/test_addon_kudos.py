"""Kudos.lua: the line for Doc Taco, every 30 minutes, on his own PC only."""

from game import Game

LINE = "We all think you are really pretty"


def said(game):
    return sum(LINE in str(v) for v in game.W.printed.values())


def test_doc_taco_hears_it_every_30_minutes():
    game = Game(role="member", name="Doc Taco")
    game.run(29 * 60)
    assert said(game) == 0  # not at login, not before 30 minutes
    game.run(2 * 60)
    assert said(game) == 1
    game.run(30 * 60)
    assert said(game) == 2
    assert game.errors == 0


def test_spelling_with_a_hyphen_or_other_case_counts():
    ns = Game(role="member", name="Doc Taco").W.ns
    assert ns.Kudos.IsFor("Doc-Taco") and ns.Kudos.IsFor("doc taco")
    assert not ns.Kudos.IsFor("Doc") and not ns.Kudos.IsFor("Doc Tacos") and not ns.Kudos.IsFor(None)


def test_nobody_else_hears_it():
    game = Game(role="member", name="Alia Testwood")
    game.run(2 * 3600)
    assert said(game) == 0
