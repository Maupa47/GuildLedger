"""Activity (docs/PACK_PLAN.md section 11): /seen, /joined, /activity, /inactive. Counts and times only, never
message text. "Last seen online" comes from the newest roster snapshot that showed the member online, so it
is approximate (as good as the times a collector was online)."""

from __future__ import annotations

from typing import Any

from .link import Links

PRECISION = {"sys": "exact", "log": "to the hour (guild log)", "diff": "a time window (roster comparison)"}


def find_chars(links: Links, name: str) -> list[dict[str, Any]]:
    """Members matching a character name (case-insensitive, whole name)."""
    rows = links.db.execute("SELECT * FROM members WHERE lower(name)=lower(?) ORDER BY in_guild DESC, last_seen DESC",
                            (name.strip(),)).fetchall()
    return [dict(r) for r in rows]


def last_chat(links: Links, guild: str, guid: str, name: str) -> int | None:
    r = links.db.execute("SELECT MAX(ts_utc) FROM chat WHERE guild=? AND (guid=? OR (guid IS NULL AND author=?))",
                         (guild, guid, name)).fetchone()
    return r[0] if r else None


def chat_count(links: Links, guild: str, guid: str, since: int) -> int:
    return links.db.execute("SELECT COUNT(*) FROM chat WHERE guild=? AND guid=? AND ts_utc >= ?",
                            (guild, guid, since)).fetchone()[0]


def seen(links: Links, chars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for c in chars:
        out.append({"name": c["name"], "in_guild": bool(c["in_guild"]), "online": c["last_seen"],
                    "chat": last_chat(links, c["guild"], c["guid"], c["name"])})
    return out


def joined(links: Links, char: dict[str, Any]) -> dict[str, Any]:
    r = links.db.execute(
        "SELECT ts_utc, window_from, src, actor FROM events WHERE guild=? AND kind='join' AND superseded_by IS NULL"
        " AND (guid=? OR name=?) ORDER BY ts_utc DESC LIMIT 1", (char["guild"], char["guid"], char["name"])).fetchone()
    if r:
        return {"when": r["ts_utc"], "from": r["window_from"], "precision": PRECISION.get(r["src"], r["src"]),
                "by": r["actor"]}
    return {"when": char["first_seen"], "from": None, "precision": "first seen by GuildLedger (joined earlier)",
            "by": None}


def activity(links: Links, user_id: int, now: int) -> list[dict[str, Any]]:
    out = []
    for c in links.chars(user_id):
        out.append({
            "name": c["name"], "in_guild": bool(c["in_guild"]), "level": c["level"], "class": c["class"],
            "rank": c["rank_name"], "online": c["last_seen"],
            "lines7": chat_count(links, c["guild"], c["guid"], now - 7 * 86400),
            "lines30": chat_count(links, c["guild"], c["guid"], now - 30 * 86400),
        })
    return out


def inactive(links: Links, days: int, now: int) -> tuple[dict[int, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Members in the guild not seen online for `days`: grouped by Discord user, and the unlinked ones.

    A linked user counts as inactive only if *all* their characters in the guild are inactive."""
    cutoff = now - days * 86400
    rows = links.db.execute(
        "SELECT m.name, m.guid, m.guild, m.last_seen, m.level, m.rank_name, l.discord_user_id FROM members m"
        " LEFT JOIN links l ON l.guild=m.guild AND l.guid=m.guid WHERE m.in_guild=1").fetchall()
    by_user: dict[int, list[dict[str, Any]]] = {}
    active_users: set[int] = set()
    unlinked = []
    for r in rows:
        d = dict(r)
        quiet = d["last_seen"] is None or d["last_seen"] < cutoff
        if d["discord_user_id"] is None:
            if quiet:
                unlinked.append(d)
            continue
        if not quiet:
            active_users.add(d["discord_user_id"])
        by_user.setdefault(d["discord_user_id"], []).append(d)
    grouped = {u: chars for u, chars in by_user.items() if u not in active_users}
    unlinked.sort(key=lambda d: (d["last_seen"] or 0))
    return grouped, unlinked
