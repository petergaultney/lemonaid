"""Drawing the inbox list's rows, other-terminals table and fold line."""

import dataclasses
from collections import abc

from rich.text import Text
from textual.widgets import DataTable, Static

from .... import resume
from ....config import Config
from ... import db
from ..rows import inbox_rows, row_parts, table_rows
from . import inbox_frame


@dataclasses.dataclass(frozen=True)
class Drawn:
    """Counts from one refresh, for the status line."""

    unread: int
    read: int
    matches: int  # rows in both tables; only meaningful while searching
    other: bool  # whether any other-terminal rows exist
    other_shown: bool


def can_resume_detached(notification: db.Notification, config: Config) -> bool:
    return notification.switch_source in {"tmux", "cmux"} and bool(
        resume.build_resume_command(config, notification.channel, notification.metadata)
    )


def _detached_marker(notification: db.Notification, detached: abc.Set[str], config: Config) -> Text:
    if notification.channel not in detached:
        return Text()

    marker = Text(" · detached", style="dim")
    if not can_resume_detached(notification, config):
        marker.append(" · resume unavailable", style="dim red")

    return marker


def fold_label(
    config: Config, fold_name: str, fold_open: bool, count: int, hidden_groups: int = 0
) -> str:
    """The fold's one line: which statuses, how many, any groups it hides, and its key.

    *count* includes folded rows in groups, which hide in place under
    their headers, and *hidden_groups* the groups with every row folded.
    """
    key = config.tui.keybindings.fold[:1]
    group = f"{fold_name or ', '.join(config.tui.fold_statuses) or 'folded'} ({count})"
    if fold_open:
        return f"▴ {group} above" + (f" · {key} to fold" if key else "")

    hidden = f" · {hidden_groups} group{'s' if hidden_groups != 1 else ''} hidden"
    return (
        f"▸ {group}" + (hidden if hidden_groups > 0 else "") + (f" · {key} to show" if key else "")
    )


def active_row(
    n: db.Notification,
    row_index: int,
    frame: inbox_frame.Frame,
    detached: abc.Set[str],
    area: str,
    parts: row_parts.RowParts,
    config: Config,
) -> list[Text]:
    return inbox_rows.active_row(
        n,
        row_index,
        n.channel in frame.focused_channels,
        n.channel in frame.pinned,
        frame.emojis,
        parts.backend_value(n, n.is_unread),
        parts.where_cell(n, n.is_unread, area),
        _detached_marker(n, detached, config),
        config.tui,
        frame.wordybins.get(n.channel, ""),
        frame.numbers.get(n.channel),
    )[1]


def other_table(
    label: Static,
    table: DataTable,
    rows: list[db.Notification],
    frame: inbox_frame.Frame,
    areas: abc.Mapping[str, str],
    parts: row_parts.RowParts,
    config: Config,
    card_width: int,
    card_shape: tuple[int, int],
) -> None:
    """Show the sessions switchable only from another terminal, always dimmed."""
    label.update("── non-switchable ──")
    label.display = True
    table.display = True
    table_rows.sync_rows(
        table,
        [
            inbox_rows.other_row(
                n,
                frame.emojis,
                parts.backend_value(n, False),
                parts.where_cell(n, False, areas.get(n.channel, "")),
                config.tui,
                frame.wordybins.get(n.channel, ""),
                frame.numbers.get(n.channel),
            )
            for n in rows
        ],
        card_width,
        card_shape,
        contexts_by_row={
            str(n.id): parts.context_parts(n, False, areas.get(n.channel, "")) for n in rows
        },
    )
