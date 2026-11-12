"""Turn WoW chat markup into plain text (export files) — Discord escaping lives in discord.py."""

from __future__ import annotations

import re

_LINK = re.compile(r"\|H[^|]*\|h(.*?)\|h", re.DOTALL)
_COLOR = re.compile(r"\|c(?:[0-9a-fA-F]{8}|n[^:|]*:)")
_TEXTURE = re.compile(r"\|T[^|]*\|t|\|A[^|]*\|a", re.DOTALL)
_KSTRING = re.compile(r"\|K[^|]*\|k")
_PIPE = "\x00PIPE\x00"


def plain(text: str | None) -> str:
    """Strip colour codes, textures and atlases; turn hyperlinks into their visible text."""
    if not text:
        return ""
    s = text.replace("||", _PIPE)
    s = _LINK.sub(lambda m: m.group(1), s)
    s = _COLOR.sub("", s).replace("|r", "")
    s = _TEXTURE.sub("", s)
    s = _KSTRING.sub("(protected text)", s)
    return s.replace(_PIPE, "|")
