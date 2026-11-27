"""Relay Comment threads in a Markdown document.

A thread is an optional `{==highlight==}` followed by one or more comment blocks,
`{{key="value" ...>>text<<}}`, with nothing in between. The Relay Comments plugin reads
the attributes in any order and omits `authorId` when it equals `author`, so both are
optional here too; a block's author is `author`, falling back to `authorId`.
"""

import hashlib
import re
from collections import abc

COMMENT_LIMIT = 4000

_ATTRS = r'(?:\s*[A-Za-z_][\w-]*="[^"]*")*'
_BLOCK = re.compile(r"\{\{(" + _ATTRS + r")\s*>>(.*?)<<\}\}", re.S)
_THREAD = re.compile(r"(?:\{==.*?==\})?(?:\{\{" + _ATTRS + r"\s*>>.*?<<\}\})+", re.S)
_ATTR = re.compile(r'([A-Za-z_][\w-]*)="([^"]*)"')
_HIGHLIGHT = re.compile(r"\{==(.*?)==\}", re.S)
_SEPARATOR_ROW = re.compile(r"^\s*\|?(\s*:?-+:?\s*\|)+\s*:?-*:?\s*\|?\s*$")
_DASHES = re.compile(r"-{3,}")
_AROUND_PIPE = re.compile(r"[ \t]*\|[ \t]*")
_WHITESPACE = re.compile(r"\s+")


def _normalized(thread: str) -> str:
    """The thread with its layout removed, as lemonaid normalized it when it keyed threads."""
    lines = (
        _DASHES.sub("---", line) if _SEPARATOR_ROW.match(line) else line
        for line in thread.splitlines()
    )
    return _WHITESPACE.sub(" ", _AROUND_PIPE.sub("|", "\n".join(lines))).strip()


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text

    return (
        f"{text[:limit]}... ({len(text) - limit} characters omitted; read the source for the rest)"
    )


def last_block(thread: str) -> tuple[str, str]:
    """(author, text) of the thread's last block."""
    attrs_raw, text = _BLOCK.findall(thread)[-1]
    attrs = dict(_ATTR.findall(attrs_raw))
    return attrs.get("author") or attrs.get("authorId", ""), text


def threads(text: str) -> list[str]:
    return [m.group(0) for m in _THREAD.finditer(text)]


def key(thread: str) -> str:
    """Unchanged since the watcher kept Relay threads itself, so its saved cursors still match."""
    return hashlib.sha1(_normalized(thread).encode()).hexdigest()[:16]


def unanswered(text: str, mine: abc.Set[str]) -> list[str]:
    """Threads whose last block is not signed with one of `mine`."""
    return [t for t in threads(text) if last_block(t)[0] not in mine]


def gist(thread: str) -> str:
    author, text = last_block(thread)
    return f"{author}: {text.strip().replace(chr(10), ' ')[:100]}"


def full_text(thread: str) -> str:
    """The thread's last comment in full, line breaks kept, under its author."""
    author, text = last_block(thread)
    return f"{author}:\n{_shorten(text.strip(), COMMENT_LIMIT)}"


def body_without_threads(text: str) -> str:
    """The prose a human or lemon wrote: comment blocks removed, highlighted text kept."""

    def keep_highlight(m: re.Match[str]) -> str:
        h = _HIGHLIGHT.match(m.group(0))
        return h.group(1) if h else ""

    return _THREAD.sub(keep_highlight, text)
