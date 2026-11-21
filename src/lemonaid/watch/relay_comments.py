"""Relay Comment threads in a Markdown document.

A thread is an optional `{==highlight==}` followed by one or more comment blocks,
`{{key="value" ...>>text<<}}`, with nothing in between. The Relay Comments plugin reads
the attributes in any order and omits `authorId` when it equals `author`, so both are
optional here too; a block's author is `author`, falling back to `authorId`.

A plain CriticMarkup comment, `{>>text<<}`, written by an editor without Relay, starts a
thread too. It has no author, so it waits on every reader until a signed block follows it.
"""

import re
from collections import abc

from . import clip

_ATTRS = r'(?:\s*[A-Za-z_][\w-]*="[^"]*")*'
_BLOCK = re.compile(r"\{\{(" + _ATTRS + r")\s*>>(.*?)<<\}\}", re.S)
# a comment block of either kind: a plain one has no author
_ANY_BLOCK = re.compile(r"\{\{(" + _ATTRS + r")\s*>>(.*?)<<\}\}|\{>>(.*?)<<\}", re.S)
_THREAD = re.compile(r"(?:\{==.*?==\})?(?:\{\{" + _ATTRS + r"\s*>>.*?<<\}\}|\{>>.*?<<\})+", re.S)
_ATTR = re.compile(r'([A-Za-z_][\w-]*)="([^"]*)"')
_HIGHLIGHT = re.compile(r"\{==(.*?)==\}", re.S)


def _last_block(thread: str) -> tuple[str, str]:
    """(author, text) of the thread's last block; a plain comment has no author."""
    attrs_raw, signed_text, plain_text = list(_ANY_BLOCK.finditer(thread))[-1].groups()
    if plain_text is not None:
        return "", plain_text

    attrs = dict(_ATTR.findall(attrs_raw))
    return attrs.get("author") or attrs.get("authorId", ""), signed_text


Regions = abc.Sequence[tuple[int, int]]


def _threads(text: str, code: Regions) -> list[re.Match]:
    """The threads in `text`, leaving out markup that starts inside a `code` region, where a
    doc quotes it as an example. A delimiter in code is passed over before its end is
    looked for, so an unfinished example can't swallow a real comment after the code."""
    found, at = [], 0
    while (m := _THREAD.search(text, at)) is not None:
        inside = next(((s, e) for s, e in code if s <= m.start() < e), None)
        if inside is not None:
            at = max(inside[1], m.start() + 1)
            continue
        found.append(m)
        at = m.end()
    return found


def unanswered_threads(text: str, mine: abc.Set[str], code: Regions = ()) -> list[str]:
    """Threads whose last block is not signed with one of `mine`."""
    return [m.group(0) for m in _threads(text, code) if _last_block(m.group(0))[0] not in mine]


def last_authors(text: str) -> list[str]:
    """Who wrote last in each thread, in document order."""
    return [_last_block(m.group(0))[0] for m in _THREAD.finditer(text)]


def _shown(author: str) -> str:
    return author or "(a comment with no author)"


def thread_gist(thread: str) -> str:
    author, text = _last_block(thread)
    return f"{_shown(author)}: {text.strip().replace(chr(10), ' ')[:100]}"


def thread_text(thread: str) -> str:
    """The thread's last comment in full, line breaks kept, under its author."""
    author, text = _last_block(thread)
    return f"{_shown(author)}:\n{clip.shorten(text.strip(), clip.COMMENT_LIMIT)}"


def body_without_threads(text: str, code: Regions = ()) -> str:
    """The prose a human or lemon wrote: comment blocks removed, highlighted text kept, and
    markup in `code` left alone, since it is an example and part of the prose."""
    parts, at = [], 0
    for m in _threads(text, code):
        h = _HIGHLIGHT.match(m.group(0))
        parts += [text[at : m.start()], h.group(1) if h else ""]
        at = m.end()
    return "".join([*parts, text[at:]])
