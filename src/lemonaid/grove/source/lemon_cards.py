"""Each lemon's inbox card, made by the inbox's own card code, for select mode to show.

Made while loading, off the grove's event loop, since a card's project may take resolving paths.
"""

from collections import abc

from rich.text import Text

from ... import brief
from ...config import Config
from ...inbox import db
from ...inbox.tui.rows import card_context, cards, inbox_rows
from .inputs import Inputs

MESSAGE_LINES = 4


def _card(
    n: db.Notification, read: Inputs, config: Config, width: int, now: float
) -> tuple[Text, ...]:
    tui = config.tui
    card_brief = read.cards.get(n.channel)
    cwd, branch = n.metadata.get("cwd", ""), n.metadata.get("git_branch", "")
    project = card_context.project_part(
        config.places, cwd, branch, card_brief.area if card_brief else ""
    )
    lemon_id = read.lemon_ids.get(n.channel, "")
    _, cells = inbox_rows.active_row(
        n,
        "",
        0,
        False,
        n.channel in read.pinned,
        read.emojis,
        inbox_rows.backend_value(n, n.is_unread, tui, {}),
        inbox_rows.where_cell(n, n.is_unread, tui, lambda: project),
        Text(),
        tui,
        brief.identity.brief_name(lemon_id) if lemon_id else "",
        read.numbers.get(n.channel, ()),
    )
    (card,) = cards.as_card(
        cells,
        width,
        1,
        MESSAGE_LINES,
        0,
        tui.card_unread_style,
        read.emojis.get(n.channel, ""),
        card_brief,
        now,
        inbox_rows.context_parts(n, n.is_unread, tui, project, card_brief, now),
        "age" in tui.card_fields,
        tui.project_name_colors,
    )
    lines = card.split("\n")
    return tuple(lines[:-1] if lines and not lines[-1].plain.strip() else lines)


def by_channel(
    read: Inputs, config: Config, width: int, now: float
) -> abc.Mapping[str, tuple[Text, ...]]:
    """Each live lemon's card lines, *width* cells wide, without the blank line after it."""
    return {n.channel: _card(n, read, config, width, now) for n in read.rows}
