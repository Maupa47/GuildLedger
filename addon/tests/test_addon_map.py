"""Map.lua: positions shared on demand between guild members (simulated guild, fake world map)."""

from test_addon_relay import Guild

SHARER, VIEWER = "Sha Rer", "Vie Wer"


def map_guild(share=True):
    guild = Guild([(SHARER, "member"), (VIEWER, "member")])
    if not share:
        guild.g(SHARER).slash("map share off")
    guild.run(25)
    return guild


def sent(guild, who, kind):
    return [m for s, m in guild.addon_log if s == who and m.startswith(kind + "\t")]


def dots(game):
    return [p for p in game.W.ns.Map.Positions().values()]


def test_viewer_sees_sharer_within_15_seconds_and_dot_lands_on_the_right_spot():
    guild = map_guild()
    view = guild.g(VIEWER)
    view.L.execute("WorldMapFrame.open = true")
    guild.run(15)
    pos = view.W.ns.Map.Positions()
    assert f"{SHARER}-Forever" in pos
    p = pos[f"{SHARER}-Forever"]
    assert (p["map"], p["x"], p["y"]) == (1429, 5000, 2500)
    x, y = view.W.ns.Map.project(p, 1429)
    assert abs(x - 0.5) < 1e-3 and abs(y - 0.25) < 1e-3
    x, y = view.W.ns.Map.project(p, 1415)  # continent view: projected through the zone's rectangle
    assert abs(x - 0.5) < 1e-3 and abs(y - 0.65) < 1e-3
    assert "Shown right now: 1" in view.slash("status")


def test_nothing_is_sent_when_nobody_looks_and_watching_stops_it():
    guild = map_guild()
    guild.run(120)
    assert sent(guild, SHARER, "P") == []  # nobody has the map open: silence
    guild.g(VIEWER).L.execute("WorldMapFrame.open = true")
    guild.run(40)
    p_while_open = len(sent(guild, SHARER, "P"))
    assert 1 <= p_while_open <= 3  # standing still: first position, then a refresh every 30 s
    assert 1 <= len(sent(guild, VIEWER, "V")) <= 2  # the viewer repeats itself at most every 30 s
    guild.g(VIEWER).L.execute("WorldMapFrame.open = false")
    guild.run(60)  # the last watch expires after 45 s
    later = len(sent(guild, SHARER, "P"))
    guild.run(120)
    assert len(sent(guild, SHARER, "P")) == later


def test_moving_sharer_updates_every_10_seconds_at_most():
    guild = map_guild()
    guild.g(VIEWER).L.execute("WorldMapFrame.open = true")
    for i in range(40):
        guild.g(SHARER).L.execute(f"W.where.x = {0.3 + i * 0.01}")
        guild.run(1)
    n = len(sent(guild, SHARER, "P"))
    assert 3 <= n <= 5


def test_no_sharing_when_off_in_an_instance_or_in_a_boss_fight():
    for setup in ("off", "instance", "lockdown"):
        guild = map_guild(share=setup != "off")
        sharer = guild.g(SHARER)
        if setup == "instance":
            sharer.W.instance = True
        if setup == "lockdown":
            sharer.W.lockdown = True
        guild.g(VIEWER).L.execute("WorldMapFrame.open = true")
        guild.run(60)
        assert sent(guild, SHARER, "P") == [], setup


def test_dots_fade_and_disappear_after_the_sharer_stops():
    guild = map_guild()
    view = guild.g(VIEWER)
    view.L.execute("WorldMapFrame.open = true")
    guild.run(15)
    guild.g(SHARER).slash("map share off")
    guild.run(70)
    assert dots(view) and "Shown right now: 1" in view.slash("status")
    guild.run(60)
    assert dots(view) == []


def test_sender_not_in_the_member_list_is_not_shown():
    guild = map_guild()
    view = guild.g(VIEWER)
    view.W.addMember("Some One Else", "Player-1-ELSE")  # the viewer's member list does not contain the sharer
    view.L.execute("WorldMapFrame.open = true")
    guild.run(30)
    assert "Shown right now: 0" in view.slash("status")


def test_viewer_with_pins_off_sends_no_watch():
    guild = map_guild()
    view = guild.g(VIEWER)
    view.slash("map pins off")
    view.L.execute("WorldMapFrame.open = true")
    guild.run(60)
    assert sent(guild, VIEWER, "V") == [] and sent(guild, SHARER, "P") == []


def test_sharing_is_on_by_default_and_an_old_automatic_off_does_not_count():
    guild = Guild([(SHARER, "member"), (VIEWER, "member")])  # nobody typed anything
    guild.g(SHARER).L.execute("GuildLedgerDB.opts.mapShare = false")  # what 0.4.0 wrote by itself
    guild.g(SHARER).reload()
    guild.run(25)
    guild.g(VIEWER).L.execute("WorldMapFrame.open = true")
    guild.run(15)
    assert f"{SHARER}-Forever" in guild.g(VIEWER).W.ns.Map.Positions()
    guild.g(SHARER).slash("map share off")
    guild.g(SHARER).reload()  # the choice is remembered
    assert "not shared" in guild.g(SHARER).slash("status")
