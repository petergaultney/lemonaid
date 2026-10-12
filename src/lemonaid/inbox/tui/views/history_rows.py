"""The session-history list: which archived sessions it shows, and each one's row."""

from collections import abc

from rich.text import Text
from textual.widgets import DataTable

from .... import resume
from ....brief import attached
from ....config import Config
from ... import db, search
from ..rows import brief_cards, card_context, cards, row_cells, row_parts, table_rows
from ..utils import styled_cell


def history_row(
    n: db.Notification,
    card: brief_cards.CardBrief | None,
    backend: Text,
    where: Text,
    context_parts: abc.Callable[[], list[card_context.Part]],
    neutral_timing: bool,
    card_width: int,
    card_shape: tuple[int, int],
) -> tuple[list[Text], int]:
    """The row's cells (one card cell when `card_width` is set) and its height."""
    name_cell = styled_cell(n.name or "", False, "name", history=True)
    if card and card.status:
        name_cell.append(
            f" · {card.status}",
            style=brief_cards.STATUS_STYLES.get(card.status, "dim"),
        )

    cells = [
        styled_cell(
            row_cells.format_timestamp(n.created_at),
            False,
            "time",
            history=True,
            neutral_timing=neutral_timing,
        ),
        Text(""),  # archived: never a marker, but cards index by position
        backend,
        name_cell,
        styled_cell(n.metadata.get("git_branch", ""), False, "branch", history=True),
        where,
        styled_cell(n.message, False, "message", history=True),
        Text(""),  # No TTY for archived
    ]
    if not card_width:
        shown = table_rows.without_marker(cells)  # columns drop the marker
        return shown, 1

    # Cards have no columns to drop, and index their fields by position.
    shown = cards.as_card(cells, card_width, *card_shape, context_parts=context_parts())
    return shown, table_rows.row_height(shown)


def load(text: str, searching_from: str | None, searching: bool) -> list[db.Notification]:
    """Archived sessions matching *text*; while searching, those switchable from
    `searching_from` that the search found in the archive.
    """
    with db.connect() as conn:
        if not searching:
            return db.get_history(conn, search=text)

        results = search.find(conn, text, include_history=True, switch_source=searching_from)
        return [result.notification for result in results if result.source == "archive"]


def fill(
    table: DataTable,
    notifications: abc.Iterable[db.Notification],
    config: Config,
    parts: row_parts.RowParts,
    brief_cache: brief_cards.BriefCache,
    card_width: int,
    card_shape: tuple[int, int],
) -> None:
    """Redraw *table* with the sessions that can be resumed, keeping the cursor's place."""
    notifications = [n for n in notifications if resume.has_resume_command(config, n.channel)]
    with db.connect() as conn:
        brief_paths = attached.by_channel(conn, [n.channel for n in notifications])

    current_row = table.cursor_coordinate.row if table.row_count > 0 else 0
    table.clear()
    for n in notifications:
        card = (path := brief_paths.get(n.channel)) and brief_cache.get(path)
        area = card.area if card else ""
        cells, height = history_row(
            n,
            card or None,
            parts.backend_value(n, False, history=True),
            parts.where_cell(n, False, area),
            lambda n=n, area=area: parts.context_parts(n, False, area),
            config.tui.project_name_colors,
            card_width,
            card_shape,
        )
        table.add_row(*cells, key=str(n.id), height=height)

    if table.row_count > 0:
        table.move_cursor(row=min(current_row, table.row_count - 1))
