"""The title lemonaid pushes to a Claude session: `<emoji> <name> (<WordyBin>)`.

One-way: lemonaid's emoji, name and brief ID win over whatever Claude holds. A
session with neither an emoji nor a brief gets no title, so sessions that are not
lemons keep the names Claude gave them.

Claude's title for the session is imported back as its inbox name, so a name
read from a lemon's transcript arrives decorated and is made bare by `canonical`.
"""

import sqlite3

from .. import brief
from ..inbox import db, emoji


def _is_emoji_token(token: str) -> bool:
    """Whether *token* is an emoji or keycap: symbols beyond ASCII and no letters."""
    return not any(char.isalpha() for char in token) and any(ord(char) > 0x2000 for char in token)


def _bare_name(name: str, wordybin: str) -> str:
    first, _, rest = name.partition(" ")
    bare = rest if rest and _is_emoji_token(first) else name
    return bare.removesuffix(f" ({wordybin})") if wordybin else bare


def build(name: str, session_emoji: str, wordybin: str) -> str:
    if not (session_emoji or wordybin):
        return ""

    return " ".join(
        part
        for part in (
            session_emoji,
            _bare_name(name, wordybin),
            f"({wordybin})" if wordybin else "",
        )
        if part
    )


def _decoration(conn: sqlite3.Connection, channel: str) -> tuple[str, str]:
    """(emoji, WordyBin) of the session, each "" when it has none."""
    lemon_id = brief.identity.by_channel(conn).get(channel, "")
    return emoji.by_channel(conn).get(channel, ""), (
        brief.identity.brief_name(lemon_id) if lemon_id else ""
    )


def canonical(conn: sqlite3.Connection, channel: str, name: str) -> str:
    """*name* without the emoji and `(WordyBin)` a push put around it, for a lemon."""
    session_emoji, wordybin = _decoration(conn, channel)
    return _bare_name(name, wordybin) if session_emoji or wordybin else name


def pending(conn: sqlite3.Connection, channel: str, current_title: str) -> str:
    """The title to push to *channel*'s session, or "" when it already has it."""
    row = db.get_by_channel(conn, channel, unread_only=False)
    if row is None:
        return ""

    title = build(row.name or "", *_decoration(conn, channel))
    return "" if title == current_title else title
