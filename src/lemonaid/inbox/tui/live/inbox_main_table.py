"""Drawing the inbox's main table: each lemon's row or card, and its group headers."""

import time
from collections import abc

from textual.widgets import DataTable

from ....config import Config
from ... import parent_order, sections
from ..rows import family_highlight, row_parts, table_rows
from ..tables import layout
from ..utils import GUTTER_WIDTH
from . import group_headers, inbox_draw, inbox_entries, inbox_frame


def draw(
    table: DataTable,
    entries: list[inbox_entries.Entry],
    headers: abc.Mapping[str, sections.Header],
    marked_header: str,
    frame: inbox_frame.Frame,
    detached: abc.Set[str],
    parts: row_parts.RowParts,
    config: Config,
    card_width: int,
    card_shape: abc.Callable[[int], tuple[int, int]],
    families: family_highlight.Highlighter | None = None,
    visible_counts: abc.Mapping[str, int] | None = None,
    keys: abc.Mapping[str, str] | None = None,
    digits: abc.Mapping[str, str] | None = None,
) -> bool:
    """Bring *table* in line with *entries*; whether it was rebuilt rather than updated.

    `headers` are the group headers among the entries by key, `marked_header`
    the one drawn with the cursor's marker, `card_shape` sizes cards for a
    given number of extra brief lines, `keys` gives each lemon's grove key by channel, and
    `digits` each group's block digit by name.
    """
    card_briefs = frame.active.cards
    drawn = [e for e in entries if isinstance(e, sections.Row)]
    visible = (
        visible_counts
        if visible_counts is not None
        else parent_order.counts((e.notification.channel for e in drawn), frame.parents)
    )
    child_counts = {
        e.key: (visible.get(e.notification.channel, 0), frame.child_totals[e.notification.channel])
        for e in drawn
        if frame.child_totals.get(e.notification.channel)
    }
    keys = keys or {}
    gutter = max([GUTTER_WIDTH, *(len(keys.get(e.notification.channel, "")) + 1 for e in drawn)])
    briefs = (
        {
            e.key: card_briefs[e.notification.channel]
            for e in drawn
            if e.notification.channel in card_briefs
        }
        if config.tui.brief_status
        else {}
    )
    age_inline = "age" in config.tui.card_fields
    extra_lines = max(
        (card.extra_lines(age_inline) for card in briefs.values() if card and card_width),
        default=0,
    )
    now = time.time()
    areas = {channel: card.area for channel, card in card_briefs.items() if card.area}
    header_cells = {
        key: (
            group_headers.cells(
                header,
                card_width,
                len(table.columns),
                layout.NAME_CELL,
                key == marked_header,
                (digits or {}).get(header.group.name, ""),
            ),
            group_headers.background(header),
        )
        for key, header in headers.items()
    }
    return table_rows.sync_rows(
        table,
        [
            (e.key, header_cells[e.key][0])
            if isinstance(e, sections.Header)
            else (
                e.key,
                inbox_draw.active_row(
                    e.notification,
                    keys.get(e.notification.channel, ""),
                    gutter,
                    frame,
                    detached,
                    areas.get(e.notification.channel, ""),
                    parts,
                    config,
                ),
            )
            for e in entries
        ],
        card_width,
        card_shape(extra_lines),
        gutter,
        config.tui.card_unread_style,
        {e.key: frame.emojis.get(e.notification.channel, "") for e in drawn},
        briefs,
        now,
        {
            e.key: parts.context_parts(
                e.notification,
                e.notification.is_unread,
                areas.get(e.notification.channel, ""),
                briefs.get(e.key),
                now,
            )
            for e in drawn
        },
        age_inline,
        config.tui.project_name_colors,
        header_cells,
        {
            e.key: headers[f"group:{group}"].group.color
            for e in drawn
            if (group := sections.row_group_id(e.key)) is not None and f"group:{group}" in headers
        },
        children_by_row=child_counts,
        families=families,
        leads={e.key for e in drawn if e.lead},
    )
