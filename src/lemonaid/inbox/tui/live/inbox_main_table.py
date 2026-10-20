"""Drawing the inbox's main table: each lemon's row or card, and its group headers."""

import time
from collections import abc

from textual.widgets import DataTable

from ....config import Config
from ... import sections
from ..rows import row_parts, table_rows
from ..tables import layout
from ..utils import GUTTER_WIDTH
from . import group_headers, inbox_draw, inbox_entries, inbox_frame


def _child_counts(
    rows: abc.Sequence[sections.Row], parents: abc.Mapping[str, str]
) -> dict[str, int]:
    grouped: dict[int, dict[str, str]] = {}
    for row in rows:
        group = sections.row_group_id(row.key)
        if group is not None:
            grouped.setdefault(group, {})[row.notification.channel] = row.key
    counts: dict[str, int] = {}
    for members in grouped.values():
        for child in members:
            parent = parents.get(child, "")
            if parent in members and parent != child:
                key = members[parent]
                counts[key] = counts.get(key, 0) + 1
    return counts


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
) -> bool:
    """Bring *table* in line with *entries*; whether it was rebuilt rather than updated.

    `headers` are the group headers among the entries by key, `marked_header`
    the one drawn with the cursor's marker, and `card_shape` sizes cards for a
    given number of extra brief lines.
    """
    card_briefs = frame.active.cards
    drawn = [e for e in entries if isinstance(e, sections.Row)]
    child_counts = _child_counts(drawn, frame.parents)
    numbers_by_key = {e.key: i for i, e in enumerate(drawn)}  # jump digits skip headers
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
                header, card_width, len(table.columns), layout.NAME_CELL, key == marked_header
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
                    numbers_by_key[e.key],
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
        GUTTER_WIDTH,
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
    )
