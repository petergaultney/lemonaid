"""The cells of one row in the snoozed list."""

from rich.text import Text

from .. import db
from . import row_cells
from .screens import format_wake_time
from .utils import styled_cell


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
