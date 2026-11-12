"""Parser for the Lua subset WoW writes into SavedVariables files.

Handles: top-level ``Name = value`` assignments, tables with ``["key"] =``, ``[n] =`` and positional
entries, ``-- [n]`` comments, double/single quoted strings with Lua escapes, numbers (incl. exponent,
hex, ``inf``/``nan`` as WoW may print them), ``true``/``false``/``nil``.

Strings are decoded from the file's raw bytes as UTF-8 with ``errors="replace"``, so ``\\ddd`` escapes
that form multi-byte characters come out right.

Tables become ``dict`` (keys ``str``/``int``/``float``/``bool``) unless every key is 1..n, in which case
they become ``list``. An empty table becomes an empty ``dict``; use :func:`as_list` / :func:`as_dict`.
"""

from __future__ import annotations

import math
import re
from typing import Any

__all__ = ["parse", "parse_file", "as_list", "as_dict", "SVParseError"]


class SVParseError(ValueError):
    """Raised for input that is not a valid SavedVariables file."""


_TOKEN = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<comment>--\[(?P<eq>=*)\[.*?\](?P=eq)\]|--[^\n]*)
  | (?P<str>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
  | (?P<num>0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>[{}\[\]=,;\-])
    """,
    re.VERBOSE | re.DOTALL,
)

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v",
            "\\": "\\", '"': '"', "'": "'", "\n": "\n"}
_ESC_RE = re.compile(r"\\(\d{1,3}|.)", re.DOTALL)


def _unescape(body: str) -> str:
    """Resolve Lua escapes in a latin-1 view of the bytes, then decode the bytes as UTF-8."""

    def repl(m: re.Match[str]) -> str:
        e = m.group(1)
        if e[0].isdigit():
            n = int(e)
            if n > 255:
                raise SVParseError(f"escape \\{e} out of range")
            return chr(n)
        return _ESCAPES.get(e, e)

    raw = _ESC_RE.sub(repl, body) if "\\" in body else body
    return raw.encode("latin-1").decode("utf-8", errors="replace")


def _tokenize(src: str) -> list[tuple[str, str, int]]:
    out: list[tuple[str, str, int]] = []
    pos, n = 0, len(src)
    while pos < n:
        m = _TOKEN.match(src, pos)
        if not m:
            raise SVParseError(f"unexpected character {src[pos]!r} at offset {pos}")
        kind = m.lastgroup
        if kind == "eq":  # inner group of a long comment
            kind = "comment"
        if kind not in ("ws", "comment"):
            out.append((kind, m.group(kind), pos))
        pos = m.end()
    out.append(("eof", "", n))
    return out


class _Parser:
    def __init__(self, tokens: list[tuple[str, str, int]]):
        self.toks = tokens
        self.i = 0

    def peek(self, k: int = 0) -> tuple[str, str, int]:
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def take(self) -> tuple[str, str, int]:
        t = self.toks[self.i]
        self.i += 1
        return t

    def expect(self, value: str) -> None:
        kind, v, pos = self.take()
        if v != value or kind not in ("op",):
            raise SVParseError(f"expected {value!r} at offset {pos}, got {v!r}")

    def chunk(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        while self.peek()[0] != "eof":
            kind, name, pos = self.take()
            if kind != "name":
                raise SVParseError(f"expected a variable name at offset {pos}, got {name!r}")
            self.expect("=")
            result[name] = self.value()
            if self.peek()[1] == ";":
                self.take()
        return result

    def value(self) -> Any:
        kind, v, pos = self.take()
        if kind == "str":
            return _unescape(v[1:-1])
        if kind == "num":
            return _number(v)
        if kind == "op" and v == "-":
            k2, v2, p2 = self.take()
            if k2 == "num":
                return -_number(v2)
            if k2 == "name" and v2 in ("inf", "nan"):
                return -_number(v2)
            raise SVParseError(f"expected a number after '-' at offset {p2}")
        if kind == "name":
            if v == "true":
                return True
            if v == "false":
                return False
            if v == "nil":
                return None
            if v in ("inf", "nan"):
                return _number(v)
            raise SVParseError(f"unexpected name {v!r} at offset {pos}")
        if kind == "op" and v == "{":
            return self.table()
        raise SVParseError(f"unexpected {v!r} at offset {pos}")

    def table(self) -> Any:
        items: dict[Any, Any] = {}
        next_index = 1
        while True:
            kind, v, pos = self.peek()
            if kind == "op" and v == "}":
                self.take()
                break
            if kind == "eof":
                raise SVParseError("unterminated table")
            if kind == "op" and v == "[":
                self.take()
                key = self.value()
                self.expect("]")
                self.expect("=")
                val = self.value()
                if key is None:
                    raise SVParseError(f"nil table key at offset {pos}")
                if isinstance(key, float) and key.is_integer():
                    key = int(key)
                if val is not None:
                    items[key] = val
            elif kind == "name" and self.peek(1)[1] == "=":
                self.take()
                self.take()
                val = self.value()
                if val is not None:
                    items[v] = val
            else:
                val = self.value()
                if val is not None:
                    items[next_index] = val
                next_index += 1
            sep = self.peek()
            if sep[0] == "op" and sep[1] in (",", ";"):
                self.take()
            elif not (sep[0] == "op" and sep[1] == "}"):
                raise SVParseError(f"expected ',' or '}}' at offset {sep[2]}, got {sep[1]!r}")
        return _normalize(items)


def _number(text: str) -> int | float:
    if text == "inf":
        return math.inf
    if text == "nan":
        return math.nan
    if text[:2] in ("0x", "0X"):
        return int(text, 16)
    if re.fullmatch(r"\d+", text):
        return int(text)
    f = float(text)
    # WoW writes integral doubles like 1.7944226813e+15; keep them exact as int.
    if f.is_integer() and abs(f) < 2**63:
        return int(f)
    return f


def _normalize(items: dict[Any, Any]) -> Any:
    n = len(items)
    if n and all(isinstance(k, int) and not isinstance(k, bool) for k in items):
        if set(items) == set(range(1, n + 1)):
            return [items[i] for i in range(1, n + 1)]
    return items


def parse(text: str | bytes) -> dict[str, Any]:
    """Parse SavedVariables source. ``bytes`` is preferred (exact UTF-8 handling)."""
    if isinstance(text, bytes):
        if text.startswith(b"\xef\xbb\xbf"):
            text = text[3:]
        src = text.decode("latin-1")
    else:
        # Re-encode so string bodies can be decoded uniformly as UTF-8 bytes.
        src = text.lstrip("\ufeff").encode("utf-8").decode("latin-1")
    return _Parser(_tokenize(src)).chunk()


def parse_file(path: str) -> dict[str, Any]:
    with open(path, "rb") as fh:
        return parse(fh.read())


def as_list(v: Any) -> list[Any]:
    """A table that should be a sequence: list as is, empty dict → [], sparse int keys → sorted values."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        ints = sorted(k for k in v if isinstance(k, int) and not isinstance(k, bool))
        return [v[k] for k in ints]
    return []


def as_dict(v: Any) -> dict[Any, Any]:
    """A table that should be a map: dict as is, list → {1: …}, anything else → {}."""
    if isinstance(v, dict):
        return v
    if isinstance(v, list):
        return {i + 1: x for i, x in enumerate(v)}
    return {}
