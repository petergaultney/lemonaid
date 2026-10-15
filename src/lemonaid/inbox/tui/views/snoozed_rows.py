"""The snoozed list and each of its rows."""

from rich.text import Text
from textual.widgets import DataTable

from ....brief import attached
from ....config import Config
from ... import db
from ..rows import brief_cards, row_cells, row_parts, table_rows
from ..rows.row_cells import format_wake_time
from ..utils import styled_cell


def snoozed_cells(
    n: db.Notification, backend: Text, where: Text, neutral_timing: bool
) -> list[Text]:
    return [
        row_cells.time_cell(n.created_at, False, history=True, neutral_timing=neutral_timing),
        Text("○", style="dim") if n.snooze_prev_status == "unread" else Text(""),
        backend,
        styled_cell(n.name or "", False, "name"),
        styled_cell(n.metadata.get("git_branch", ""), False, "branch"),
        where,
        styled_cell(n.message, False, "message"),
        Text(format_wake_time(n.snooze_until) if n.snooze_until else "", style="bold yellow"),
    ]


def fill(
    table: DataTable,
    config: Config,
    parts: row_parts.RowParts,
    brief_cache: brief_cards.BriefCache,
    card_width: int,
    card_shape: tuple[int, int],
) -> None:
    """Bring *table* in line with what is snoozed, keeping the cursor's place."""
    current_row = table.cursor_coordinate.row if table.row_count > 0 else 0
    with db.connect() as conn:
        notifications = db.get_snoozed(conn)
        brief_paths = attached.by_channel(conn, [n.channel for n in notifications])
    areas = {
        channel: card.area
        for channel, path in brief_paths.items()
        if (card := brief_cache.get(path))
    }

    rebuilt = table_rows.sync_rows(
        table,
        [
            (
                str(n.id),
                snoozed_cells(
                    n,
                    parts.backend_value(n, False),
                    parts.where_cell(n, False, areas.get(n.channel, "")),
                    config.tui.project_name_colors,
                ),
            )
            for n in notifications
        ],
        card_width,
        card_shape,
        contexts_by_row={
            str(n.id): parts.context_parts(n, False, areas.get(n.channel, ""))
            for n in notifications
        },
    )
    if rebuilt and table.row_count > 0:
        table.move_cursor(row=min(current_row, table.row_count - 1), scroll=False)
