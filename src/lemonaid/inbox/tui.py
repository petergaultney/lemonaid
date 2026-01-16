"""Textual TUI for lemonaid inbox."""

from datetime import datetime

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
        Binding("r", "refresh", "Refresh"),
        Binding("g", "refresh", "Refresh", show=False),  # magit-style
        Binding("d", "mark_read", "Mark Read"),
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
        table.add_column("ID", width=4)
        table.add_column("Time", width=10)
        table.add_column("Channel", width=20)
        table.add_column("Title", width=40)
        table.add_column("TTY", width=15)

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

    def _refresh_notifications(self) -> None:
        table = self.query_one(DataTable)

        # Remember current selection
        current_key = self._get_current_row_key()

        table.clear()

        with db.connect() as conn:
            notifications = db.get_unread(conn)

        for n in notifications:
            created = datetime.fromtimestamp(n.created_at).strftime("%H:%M:%S")
            tty = n.metadata.get("tty", "")
            if tty:
                tty = tty.replace("/dev/", "")

            table.add_row(
                str(n.id),
                created,
                n.channel[:18] + ".." if len(n.channel) > 20 else n.channel,
                n.title[:38] + ".." if len(n.title) > 40 else n.title,
                tty,
                key=str(n.id),
            )

        # Restore cursor to same notification if it still exists
        if current_key and table.row_count > 0:
            try:
                row_index = table.get_row_index(current_key)
                table.move_cursor(row=row_index)
            except Exception:
                # Row no longer exists, cursor stays where it is (or at top)
                pass

        status = self.query_one("#status", Static)
        count = len(notifications)
        status.update(f"{count} unread notification{'s' if count != 1 else ''}")

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

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle Enter on a row - open the notification."""
        if event.row_key is None:
            return

        notification_id = int(event.row_key.value)

        with db.connect() as conn:
            notification = db.get(conn, notification_id)
            if notification:
                handled = handle_notification(
                    notification.channel, notification.metadata, self.config
                )
                if handled:
                    db.mark_read(conn, notification_id)
                    self.exit()
                    return

            db.mark_read(conn, notification_id)

        self._refresh_notifications()


def main() -> None:
    app = LemonaidApp()
    app.run()


if __name__ == "__main__":
    main()
