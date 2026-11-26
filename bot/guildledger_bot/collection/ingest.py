"""Read and check one upload from #gl-ingest (shared/schema.md 4). Pure functions, no Discord."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from dataclasses import dataclass, field
from typing import Any

from guildledger.hubdata import ROW_TYPES as HUB_TYPES
from guildledger.loot import ROW_TYPES as LOOT_TYPES

MAX_ATTACHMENT = 1024 * 1024  # companion files are <= 500 KB
MAX_UNZIPPED = 32 * 1024 * 1024
MAX_ROWS = 200_000


class Rejected(ValueError):
    """The upload is not usable; the message gets a ❌ and this reason."""


@dataclass
class Header:
    collector: str
    rows: int
    sha256: str


@dataclass
class GuildRows:
    name: str | None = None
    chat: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    roster: tuple[int, list[dict[str, Any]]] | None = None
    links: list[dict[str, Any]] = field(default_factory=list)
    loot: list[tuple[str, dict[str, Any]]] = field(default_factory=list)  # (type, row), shared/schema.md 7
    hub: list[tuple[str, dict[str, Any]]] = field(default_factory=list)  # (type, row), shared/schema.md 8


def parse_content(content: str) -> Header:
    """'gl1 <collector> <rowcount> <sha256>' (the collector name may contain spaces)."""
    parts = (content or "").strip().split()
    if len(parts) < 4 or parts[0] != "gl1":
        raise Rejected("not a gl1 upload message")
    sha, rows = parts[-1].lower(), parts[-2]
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise Rejected("bad sha256")
    if not rows.isdigit():
        raise Rejected("bad row count")
    return Header(" ".join(parts[1:-2]), int(rows), sha)


def decode(data: bytes, header: Header) -> dict[str, GuildRows]:
    if len(data) > MAX_ATTACHMENT:
        raise Rejected("attachment too large")
    if hashlib.sha256(data).hexdigest() != header.sha256:
        raise Rejected("sha256 does not match the attachment")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
            raw = gz.read(MAX_UNZIPPED + 1)
    except (OSError, EOFError) as e:
        raise Rejected("attachment is not gzip") from e
    if len(raw) > MAX_UNZIPPED:
        raise Rejected("attachment unpacks too large")

    out: dict[str, GuildRows] = {}
    count = 0
    for n, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise Rejected(f"line {n} is not JSON") from e
        if not isinstance(obj, dict) or not isinstance(obj.get("guild"), str):
            raise Rejected(f"line {n} has no guild")
        g = out.setdefault(obj["guild"], GuildRows())
        kind = obj.pop("type", None)
        if kind == "guild":
            name = obj.get("name")
            g.name = name if isinstance(name, str) and name else g.name
            continue
        obj.pop("guild", None)
        obj.pop("collector", None)  # the bot trusts the webhook, not the file
        if kind == "chat":
            g.chat.append(obj)
        elif kind == "event":
            g.events.append(obj)
        elif kind == "link":
            g.links.append(obj)
        elif kind == "roster":
            at, members = obj.get("at"), obj.get("members")
            if not isinstance(at, int) or not isinstance(members, list):
                raise Rejected(f"line {n}: bad roster record")
            if g.roster is None or at > g.roster[0]:
                g.roster = (at, members)
        elif kind in LOOT_TYPES:
            g.loot.append((kind, obj))
        elif kind in HUB_TYPES:
            g.hub.append((kind, obj))
        else:
            pass  # a newer companion's row type: counted, not used (never reject a whole upload for it)
        count += 1
        if count > MAX_ROWS:
            raise Rejected("too many rows")
    if count != header.rows:
        raise Rejected(f"row count {count} does not match the message ({header.rows})")
    return out
