"""Textual TUI for lemonaid inbox."""

import contextlib
from datetime import datetime

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header, Static

from ..config import load_config
from ..handlers import handle_notification
from . import db


class LemonaidApp(App):
    """Lemonaid TUI - attention inbox for your lemons."""

    CSS = """
    DataTable {
        height: 1fr;
    }

    #status {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "quit", "Quit", show=False),
        Binding("g", "refresh", "Refresh", show=False),
        Binding("r", "mark_read", "Mark Read"),
        Binding("a", "archive", "Archive"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.config = load_config()

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable()
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "lemonaid"
        self.sub_title = "attention inbox"
        self._setup_table()
        self._refresh_notifications()
        # Auto-refresh every 2 seconds
        self.set_interval(2.0, self._refresh_notifications)

    def on_app_focus(self) -> None:
        """Refresh when the app regains focus."""
        self._refresh_notifications()

    def _setup_table(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_column("", width=1)  # Unread indicator
        table.add_column("ID", width=5)
        table.add_column("Time", width=10)
        table.add_column("Channel", width=25)
        table.add_column("Title")  # No width = expands to fill
        table.add_column("TTY", width=12)

    def _get_current_row_key(self) -> str | None:
        """Get the row key (notification ID) at current cursor."""
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return None
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
            return row_key.value if row_key else None
        except Exception:
            return None

    def _styled_cell(self, value: str, is_unread: bool) -> Text:
        """Style a cell value based on read/unread status."""
        if is_unread:
            return Text(value, style="bold cyan")
        return Text(value, style="dim")

    def _get_current_row_index(self) -> int:
        """Get the current cursor row index."""
        table = self.query_one(DataTable)
        return table.cursor_coordinate.row

    def _refresh_notifications(self, fallback_row_index: int | None = None) -> None:
        table = self.query_one(DataTable)

        # Remember current selection (both key and index)
        current_key = self._get_current_row_key()
        current_index = self._get_current_row_index()

        table.clear()

        with db.connect() as conn:
            notifications = db.get_active(conn)

        unread_count = 0
        for n in notifications:
            created = datetime.fromtimestamp(n.created_at).strftime("%H:%M:%S")
            tty = n.metadata.get("tty", "")
            if tty:
                tty = tty.replace("/dev/", "")

            is_unread = n.is_unread
            if is_unread:
                unread_count += 1

            indicator = Text("●", style="bold cyan") if is_unread else Text("")
            table.add_row(
                indicator,
                self._styled_cell(str(n.id), is_unread),
                self._styled_cell(created, is_unread),
                self._styled_cell(n.channel, is_unread),
                self._styled_cell(n.title, is_unread),
                self._styled_cell(tty, is_unread),
                key=str(n.id),
            )

        # Restore cursor position
        if table.row_count > 0:
            target_index = None
            # First try to find the same row by key
            if current_key:
                with contextlib.suppress(Exception):
                    target_index = table.get_row_index(current_key)
            # Fall back to same position (clamped to valid range)
            if target_index is None:
                idx = fallback_row_index if fallback_row_index is not None else current_index
                target_index = min(idx, table.row_count - 1)
            table.move_cursor(row=target_index)

        status = self.query_one("#status", Static)
        total = len(notifications)
        read_count = total - unread_count
        status.update(f"{unread_count} unread, {read_count} read")

    def action_refresh(self) -> None:
        self._refresh_notifications()

    def action_mark_read(self) -> None:
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return

        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        if row_key:
            notification_id = int(row_key.value)
            with db.connect() as conn:
                db.mark_read(conn, notification_id)
            self._refresh_notifications()

    def action_archive(self) -> None:
        """Archive the selected session (removes from active list)."""
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return

        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        if row_key:
            notification_id = int(row_key.value)
            with db.connect() as conn:
                db.archive(conn, notification_id)
            self._refresh_notifications()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle Enter on a row - switch to that session without marking as read.

        The notification will be marked read when the user actually submits input
        in that session (via the UserPromptSubmit hook).
        """
        if event.row_key is None:
            return

        notification_id = int(event.row_key.value)

        with db.connect() as conn:
            notification = db.get(conn, notification_id)
            if notification:
                handle_notification(notification.channel, notification.metadata, self.config)


def main() -> None:
    app = LemonaidApp()
    app.run()


if __name__ == "__main__":
    main()
