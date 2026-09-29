"""Relay Comment threads in a Markdown document.

A thread is an optional `{==highlight==}` followed by one or more comment blocks,
`{{key="value" ...>>text<<}}`, with nothing in between. The Relay Comments plugin reads
the attributes in any order and omits `authorId` when it equals `author`, so both are
optional here too; a block's author is `author`, falling back to `authorId`.
"""

import re
from collections import abc

_ATTRS = r'(?:\s*[A-Za-z_][\w-]*="[^"]*")*'
_BLOCK = re.compile(r"\{\{(" + _ATTRS + r")\s*>>(.*?)<<\}\}", re.S)
_THREAD = re.compile(r"(?:\{==.*?==\})?(?:\{\{" + _ATTRS + r"\s*>>.*?<<\}\})+", re.S)
_ATTR = re.compile(r'([A-Za-z_][\w-]*)="([^"]*)"')
_HIGHLIGHT = re.compile(r"\{==(.*?)==\}", re.S)


def _last_block(thread: str) -> tuple[str, str]:
    """(author, text) of the thread's last block."""
    attrs_raw, text = _BLOCK.findall(thread)[-1]
    attrs = dict(_ATTR.findall(attrs_raw))
    return attrs.get("author") or attrs.get("authorId", ""), text


def unanswered_threads(text: str, mine: abc.Set[str]) -> list[str]:
    """Threads whose last block is not signed with one of `mine`."""
    return [m.group(0) for m in _THREAD.finditer(text) if _last_block(m.group(0))[0] not in mine]


def thread_gist(thread: str) -> str:
    author, text = _last_block(thread)
    return f"{author}: {text.strip().replace(chr(10), ' ')[:100]}"


def body_without_threads(text: str) -> str:
    """The prose a human or lemon wrote: comment blocks removed, highlighted text kept."""

    def keep_highlight(m: re.Match) -> str:
        h = _HIGHLIGHT.match(m.group(0))
        return h.group(1) if h else ""

    return _THREAD.sub(keep_highlight, text)
