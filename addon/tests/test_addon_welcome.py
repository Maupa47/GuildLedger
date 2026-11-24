"""Welcome.lua: at login a greeting from Maupa's sprite and the guild's message of the day; on by default."""

from game import Game

GREETING = "Maupa's sprite wishes you a wonderful journey and blows a kiss your way!"


def lines(game):
    return [str(v) for v in game.W.printed.values()]


def test_greeting_and_message_of_the_day_at_login():
    game = Game(role="member")
    game.W.fire("GUILD_MOTD", "Raid on Friday | bring flasks\nand food")
    game.run(32)
    out = lines(game)
    assert sum(GREETING in m for m in out) == 1
    motd = [m for m in out if "message of the day" in m]
    assert motd == ["|cff33ff99The guild message of the day is:|r Raid on Friday || bring flasks and food"]
    game.run(3600)
    assert sum(GREETING in m for m in lines(game)) == 1  # once per login
    assert game.errors == 0, game.last_error()


def test_without_a_message_of_the_day_only_the_greeting_after_waiting():
    game = Game(role="member")
    game.run(28)
    assert not any(GREETING in m for m in lines(game))  # 30 s after login (W24)
    game.run(30)
    out = lines(game)
    assert sum(GREETING in m for m in out) == 1 and not any("message of the day" in m for m in out)


def test_not_after_reload_and_switch_off():
    game = Game(role="member")
    game.run(45)
    game.reload()
    game.W.printed = game.L.table()
    game.run(45)
    assert not any(GREETING in m for m in lines(game))  # /reload is not a login
    api = game.L.globals().GuildLedgerAPI
    assert api.GetWelcome() is True
    assert "Login greeting: |cff888888off|r" in game.slash("welcome off") + game.slash("status")
    assert api.GetWelcome() is False
    game.W.logout()
    game.W.printed = game.L.table()
    game.load()
    game.run(45)
    assert not any(GREETING in m for m in lines(game))


def test_secret_message_of_the_day_is_ignored():
    game = Game(role="member")
    game.L.execute("W.fire('GUILD_MOTD', W.SECRET)")
    game.run(45)
    assert sum(GREETING in m for m in lines(game)) == 1
    assert game.errors == 0, game.last_error()
