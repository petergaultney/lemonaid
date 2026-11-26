"""Edits to which block has which digit: a home group drawn as block 0 with the lemons in no group,
and a group traded with the one beside it in the inbox's group order, which the digits follow.
"""

from collections import abc
from pathlib import Path
from typing import Any

from ... import groups
from ...inbox import db
from ..layout import state
from ..model import Block


def with_home(saved: dict[str, Any], group: str) -> dict[str, Any]:
    """*saved* with *group* as the home group, or none for ""."""
    return {k: v for k, v in saved.items() if k != "home"} | ({"home": group} if group else {})


def set_home(group: str, where: Path | None = None) -> str:
    """Make *group* the home group, or clear it for ""; what happened, or why not."""
    if group:
        with db.connect() as conn:
            try:
                groups.store.find(conn, group)
            except LookupError as error:
                return str(error)

    state.update(lambda saved: with_home(saved, group), where)
    return (
        f'"{group}" is in the home block'
        if group
        else "the home block holds only lemons in no group"
    )


def renumber(found: abc.Sequence[Block], digit: str, offset: int) -> str:
    """Trade block *digit*'s group with the group *offset* blocks away, so they trade digits."""
    numbered = sorted((b for b in found if b.name), key=lambda b: int(b.digit))
    at = next((i for i, b in enumerate(numbered) if b.digit == digit), None)
    if at is None:
        return "only a group's block has a number to change"
    if not 0 <= at + offset < len(numbered):
        return f"block {digit} is already {'first' if offset < 0 else 'last'}"

    other = numbered[at + offset]
    with db.connect() as conn:
        groups.arrangement.swap(
            conn,
            groups.store.find(conn, numbered[at].name),
            groups.store.find(conn, other.name),
        )
    return f'"{numbered[at].name}" is block {other.digit}'
