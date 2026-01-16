"""Textual TUI for lemonaid."""

import json
import subprocess
from datetime import datetime

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header, Static

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
        Binding("r", "refresh", "Refresh"),
        Binding("enter", "open", "Open"),
        Binding("d", "mark_read", "Mark Read"),
    ]

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

    def _setup_table(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_column("ID", width=4)
        table.add_column("Time", width=10)
        table.add_column("Channel", width=30)
        table.add_column("Title", width=50)

    def _refresh_notifications(self) -> None:
        table = self.query_one(DataTable)
        table.clear()

        notifications = db.get_unread()

        for n in notifications:
            created = datetime.fromtimestamp(n["created_at"]).strftime("%H:%M:%S")
            table.add_row(
                str(n["id"]),
                created,
                n["channel"][:28] + ".." if len(n["channel"]) > 30 else n["channel"],
                n["title"][:48] + ".." if len(n["title"]) > 50 else n["title"],
                key=str(n["id"]),
            )

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
            db.mark_read(notification_id)
            self._refresh_notifications()

    def action_open(self) -> None:
        """Open the selected notification - mark read and run handler if configured."""
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return

        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        if not row_key:
            return

        notification_id = int(row_key.value)

        # Get the notification details
        conn = db.get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM notifications WHERE id = ?", (notification_id,)
            ).fetchone()

            if row and row["metadata"]:
                metadata = json.loads(row["metadata"])

                # Check for handler command in metadata
                if "handler" in metadata:
                    handler = metadata["handler"]
                    # Run the handler command
                    try:
                        subprocess.run(handler, shell=True, check=False)
                    except Exception as e:
                        self.notify(f"Handler error: {e}", severity="error")

                # Check for wezterm-specific handler
                elif "workspace" in metadata and "pane_id" in metadata:
                    self._switch_wezterm_pane(metadata["workspace"], metadata["pane_id"])

            # Mark as read
            db.mark_read(notification_id, conn)
        finally:
            conn.close()

        self._refresh_notifications()

    def _switch_wezterm_pane(self, workspace: str, pane_id: int) -> None:
        """Switch to a WezTerm workspace and pane."""
        import base64
        import os
        import sys

        value = f"{workspace}|{pane_id}"
        encoded = base64.b64encode(value.encode()).decode()
        seq = f"\033]1337;SetUserVar=switch_workspace_and_pane={encoded}\007"

        # Write to stdout to send to the terminal
        os.write(sys.stdout.fileno(), seq.encode())

        # Exit the TUI so the switch can happen
        self.exit()


def main() -> None:
    app = LemonaidApp()
    app.run()


if __name__ == "__main__":
    main()
