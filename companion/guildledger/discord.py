"""Discord formatting (CLAUDE.md 7.4) and a small webhook client (stdlib only).

Webhook URLs are secrets: they are never logged, and errors only name the webhook's role ("chat").
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import Any, Callable

from .wowtext import plain

log = logging.getLogger(__name__)

MAX_CONTENT = 1900  # Discord allows 2000; leave room
MAX_LINE = 1700
MAX_EMBEDS = 10
SUPPRESS_EMBEDS = 1 << 2  # message flag: no link previews
NO_MENTIONS = {"parse": []}
USER_AGENT = "GuildLedger-Companion/0.1 (python urllib)"

NO_TEXT = "*(text not captured)*"
# "!link CODE" typed in guild chat links a character to Discord (bot, docs/dev/archive/PLAN_COMMUNITY.md D1): the log
# channels never show the code.
LINK_CODE = re.compile(r"(?i)^(\s*!link\s+)\S+")


def mask_link_code(text: str) -> str:
    return LINK_CODE.sub(lambda m: m.group(1) + "••••", text)

# ---------------------------------------------------------------------- escaping

_MD = re.compile(r"([\\*_~`|>\[\]<])")
_LINE_START = re.compile(r"^(\s*)([#\-+]|\d+\.)", re.MULTILINE)
_MASS = re.compile(r"@(everyone|here)", re.IGNORECASE)
ZWSP = "​"


def escape(text: str) -> str:
    """Plain text that Discord shows literally: no formatting, no mentions, no masked links."""
    s = _MD.sub(r"\\\1", text)
    s = _LINE_START.sub(lambda m: m.group(1) + "\\" + m.group(2), s)
    s = _MASS.sub(lambda m: "@" + ZWSP + m.group(1), s)
    return s


def wow_to_discord(text: str | None) -> str:
    """WoW chat text -> safe Discord text: links become their [Name], colours and textures go."""
    return escape(" ".join(plain(text).split()))


def _clip(s: str, limit: int) -> str:
    return s if len(s) <= limit else s[: limit - 1] + "…"


# ---------------------------------------------------------------------- chat lines

def _local(ts: int, tz: tzinfo | None) -> datetime:
    return datetime.fromtimestamp(ts, tz)


def date_header(ts: int, tz: tzinfo | None) -> str:
    return f"**── {_local(ts, tz).strftime('%A, %Y-%m-%d')} ──**"


def chat_line(r: Any, tz: tzinfo | None, full_date: bool = False) -> str:
    fmt = "%Y-%m-%d %H:%M" if full_date else "%H:%M"
    parts = [f"`{_local(r['ts_utc'], tz).strftime(fmt)}`"]
    if r["stream"] == "o":
        parts.append("`[Officer]`")
    elif r["stream"] in ("d", "x"):
        parts.append(f"`[{'Discord' if r['stream'] == 'd' else 'Other'}]`")
    name = f"**{escape(r['author'])}**"
    if r["from_discord"]:
        name += " *(Discord)*"
    text = wow_to_discord(mask_link_code(r["text"])) if r["text"] is not None else NO_TEXT
    flags = (" *(edited)*" if r["edited"] else "") + (" *(deleted)*" if r["deleted"] else "")
    return _clip(f"{' '.join(parts)} {name}: {text}{flags}", MAX_LINE)


def gap_line(first: int, last: int, count: int, authors: int, tz: tzinfo | None, full_date: bool = False) -> str:
    fmt = "%Y-%m-%d %H:%M" if full_date else "%H:%M"
    span = _local(first, tz).strftime(fmt)
    if last != first:
        span += "–" + _local(last, tz).strftime("%H:%M")
    who = f" from {authors} member{'s' if authors != 1 else ''}" if authors else ""
    return f"`{span}` *{count} message{'s' if count != 1 else ''}{who} — text not captured*"


def pack(lines: list[tuple[str, list[Any]]], header: str | None = None) -> list[tuple[str, list[Any]]]:
    """Group (line, keys) into messages of at most MAX_CONTENT chars. Returns (content, keys)."""
    out: list[tuple[str, list[Any]]] = []
    buf: list[str] = [header] if header else []
    keys: list[Any] = []
    size = len(header) + 1 if header else 0
    for line, k in lines:
        if buf and size + len(line) + 1 > MAX_CONTENT:
            out.append(("\n".join(buf), keys))
            buf, keys, size = [], [], 0
        buf.append(line)
        keys.extend(k)
        size += len(line) + 1
    if buf and keys:
        out.append(("\n".join(buf), keys))
    return out


# ---------------------------------------------------------------------- roster embeds

GREEN, RED, GREY, BLUE, ORANGE = 0x2ECC71, 0xE74C3C, 0x95A5A6, 0x3498DB, 0xE67E22
_TITLE = {"join": "joined the guild", "leave": "left the guild", "kick": "was kicked",
          "promote": "was promoted", "demote": "was demoted"}
_COLOR = {"join": GREEN, "leave": RED, "kick": RED, "promote": BLUE, "demote": ORANGE}
_SOURCE = {"sys": "seen live", "diff": "roster comparison (time is a window)",
           "log": "guild event log (time to the hour)"}


def event_embed(r: Any, late: bool = False) -> dict[str, Any]:
    precise = bool(r["precise"])
    w = r["window_from"] if "window_from" in r.keys() else None
    if precise:
        when = f"<t:{r['ts_utc']}:f>"
    elif w is not None and w < r["ts_utc"]:
        when = f"between <t:{w}:f> and <t:{r['ts_utc']}:t>"
    else:
        when = f"about <t:{r['ts_utc']}:f>"
    fields = [{"name": "When", "value": when, "inline": True}]
    if r["actor"]:
        fields.append({"name": "By", "value": escape(r["actor"]), "inline": True})
    if r["detail"]:
        fields.append({"name": "Rank", "value": escape(r["detail"]), "inline": True})
    footer = _SOURCE.get(r["src"], r["src"]) + (" · late entry" if late else "")
    return {
        "description": _clip(f"**{escape(r['name'])}** {_TITLE.get(r['kind'], r['kind'])}", 4000),
        "color": _COLOR.get(r["kind"], GREY) if precise else GREY,
        "fields": fields,
        "footer": {"text": footer},
    }


# ---------------------------------------------------------------------- webhook client

class WebhookError(RuntimeError):
    """Posting failed in a way that retrying now will not fix (bad URL, permissions, outage)."""


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes


Transport = Callable[..., Response]  # (url, data, content_type="application/json") -> Response


def urllib_transport(url: str, data: bytes, content_type: str = "application/json") -> Response:
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": content_type, "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return Response(resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read())
    except urllib.error.HTTPError as e:
        return Response(e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read() or b"")


class Webhook:
    """One Discord webhook. ``post`` returns only after Discord confirmed the message."""

    def __init__(self, url: str, role: str, transport: Transport = urllib_transport,
                 sleep: Callable[[float], None] = time.sleep):
        if not url.startswith("https://"):
            raise WebhookError(f"{role} webhook is not set (or not an https URL) in config.toml")
        sep = "&" if "?" in url else "?"
        self._url = url + sep + "wait=true"
        self.role = role
        self._transport = transport
        self._sleep = sleep

    def __repr__(self) -> str:  # never show the URL
        return f"Webhook({self.role})"

    def post(self, content: str | None = None, embeds: list[dict[str, Any]] | None = None) -> None:
        payload: dict[str, Any] = {"allowed_mentions": NO_MENTIONS}
        if content:
            payload["content"] = content
            payload["flags"] = SUPPRESS_EMBEDS
        if embeds:
            payload["embeds"] = embeds
        self._send(json.dumps(payload).encode("utf-8"), "application/json")

    def post_file(self, content: str, filename: str, data: bytes, mime: str = "application/gzip") -> None:
        """A message with one attachment (multipart/form-data, as Discord's webhook API takes it)."""
        boundary = "gl" + hashlib.sha256(data).hexdigest()[:30]
        payload = json.dumps({"content": content, "allowed_mentions": NO_MENTIONS}).encode("utf-8")
        crlf = b"\r\n"
        body = b"".join([
            f"--{boundary}".encode(), crlf,
            b'Content-Disposition: form-data; name="payload_json"', crlf,
            b"Content-Type: application/json", crlf, crlf,
            payload, crlf,
            f"--{boundary}".encode(), crlf,
            f'Content-Disposition: form-data; name="files[0]"; filename="{filename}"'.encode(), crlf,
            f"Content-Type: {mime}".encode(), crlf, crlf,
            data, crlf,
            f"--{boundary}--".encode(), crlf,
        ])
        self._send(body, f"multipart/form-data; boundary={boundary}")

    def _send(self, data: bytes, content_type: str) -> None:
        failures = 0
        while True:
            try:
                r = self._transport(self._url, data, content_type)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                failures += 1
                if failures > 3:
                    raise WebhookError(f"{self.role} webhook: network error ({type(e).__name__})") from None
                self._sleep(2 * failures)
                continue
            if 200 <= r.status < 300:
                if r.headers.get("x-ratelimit-remaining") == "0":
                    self._sleep(_float(r.headers.get("x-ratelimit-reset-after"), 1.0))
                return
            if r.status == 429:
                wait = _retry_after(r)
                log.info("%s webhook rate limited; waiting %.1f s", self.role, wait)
                self._sleep(wait)
                continue
            if r.status >= 500:
                failures += 1
                if failures > 3:
                    raise WebhookError(f"{self.role} webhook: Discord error {r.status}")
                self._sleep(2 * failures)
                continue
            raise WebhookError(f"{self.role} webhook rejected the message (HTTP {r.status}{_reason(r)})")


def _float(v: Any, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _retry_after(r: Response) -> float:
    try:
        return max(0.1, float(json.loads(r.body.decode("utf-8")).get("retry_after", 1.0)))
    except (ValueError, AttributeError):
        return _float(r.headers.get("retry-after"), 1.0)


def _reason(r: Response) -> str:
    try:
        msg = json.loads(r.body.decode("utf-8")).get("message")
    except (ValueError, AttributeError):
        return ""
    return f": {msg}" if isinstance(msg, str) else ""
