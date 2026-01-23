"""Textual TUI for lemonaid inbox."""

import contextlib
import os
from datetime import datetime

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header, Static

from ..claude.patcher import apply_patch, check_status, find_binary
from ..config import load_config
from ..handlers import handle_notification
from . import db


def detect_terminal_env() -> str:
    """Detect which terminal environment we're running in."""
    if os.environ.get("TMUX"):
        return "tmux"
    if os.environ.get("WEZTERM_PANE"):
        return "wezterm"
    return "unknown"


def set_terminal_title(title: str) -> None:
    """Set the terminal/pane title via OSC escape sequence."""
    import sys

    # OSC 0 sets both icon name and window title
    sys.stdout.write(f"\033]0;{title}\007")
    sys.stdout.flush()


class LemonaidApp(App):
    """Lemonaid TUI - attention inbox for your lemons."""

    CSS = """
    DataTable {
        height: 1fr;
    }

    #status {
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
        Binding("m", "mark_read", "Mark Read"),
        Binding("a", "archive", "Archive"),
        Binding("P", "patch_claude", "Patch Claude", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.config = load_config()
        self.terminal_env = detect_terminal_env()
        self._claude_patch_status: str | None = None
        self._claude_binary = find_binary()
        # Enable ANSI colors for terminal transparency support
        if self.config.tui.transparent:
            self.ansi_color = True
            self.dark = True  # Use dark theme as base

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable()
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "lemonaid"
        self.sub_title = "attention inbox"

        # Apply transparent styles if configured
        if self.config.tui.transparent:
            self.screen.styles.background = "transparent"
            self.query_one(DataTable).styles.background = "transparent"

        self._setup_table()
        self._check_claude_patch()
        self._refresh_notifications()
        # Auto-refresh every 2 seconds
        self.set_interval(1.0, self._refresh_notifications)

    def _check_claude_patch(self) -> None:
        """Check Claude Code patch status."""
        if self._claude_binary:
            self._claude_patch_status = check_status(self._claude_binary)
        else:
            self._claude_patch_status = None

    def on_app_focus(self) -> None:
        """Refresh when the app regains focus."""
        self._refresh_notifications()

    def _setup_table(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_column("Time", width=10)
        table.add_column("", width=1)  # Unread indicator
        table.add_column("Name", width=20)
        table.add_column("Message")  # No width = expands to fill
        table.add_column("Channel", width=15)
        table.add_column("ID", width=5)
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

    def _refresh_notifications(self, *, stay_on_unread: bool = False) -> None:
        table = self.query_one(DataTable)

        # Remember current selection (both key and index)
        current_key = self._get_current_row_key()
        current_index = self._get_current_row_index()

        table.clear()

        with db.connect() as conn:
            # Filter to notifications handleable in current environment
            env_filter = self.terminal_env if self.terminal_env != "unknown" else None
            notifications = db.get_active(conn, terminal_env=env_filter)

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
                self._styled_cell(created, is_unread),
                indicator,
                self._styled_cell(n.name or "", is_unread),
                self._styled_cell(n.message, is_unread),
                self._styled_cell(n.channel, is_unread),
                self._styled_cell(str(n.id), is_unread),
                self._styled_cell(tty, is_unread),
                key=str(n.id),
            )

        # Restore cursor position
        if table.row_count > 0:
            target_index = None
            if stay_on_unread and unread_count > 0:
                # Stay on an unread item: use current index but cap at last unread
                target_index = min(current_index, unread_count - 1)
            elif stay_on_unread:
                # No unread left, go to top
                target_index = 0
            else:
                # Try to find the same row by key
                if current_key:
                    with contextlib.suppress(Exception):
                        target_index = table.get_row_index(current_key)
                # Fall back to same position (clamped to valid range)
                if target_index is None:
                    target_index = min(current_index, table.row_count - 1)
            table.move_cursor(row=target_index)

        status = self.query_one("#status", Static)
        total = len(notifications)
        read_count = total - unread_count
        env_label = f" [{self.terminal_env}]" if self.terminal_env != "unknown" else ""
        status_text = f"{unread_count} unread, {read_count} read{env_label}"

        # Add patch warning if Claude is unpatched
        if self._claude_patch_status == "unpatched":
            status_text += "  |  [bold cyan]P[/]atch Claude for faster notifications"

        status.update(status_text)

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
            # Keep cursor on unread items when possible
            self._refresh_notifications(stay_on_unread=True)

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

    def action_patch_claude(self) -> None:
        """Patch Claude Code binary for faster notifications."""
        if not self._claude_binary or self._claude_patch_status != "unpatched":
            return

        try:
            count = apply_patch(self._claude_binary)
            if count > 0:
                self._claude_patch_status = "patched"
                self.notify(f"Patched Claude Code ({count} locations). Restart Claude for effect.")
            else:
                self.notify("No patterns found to patch", severity="warning")
        except Exception as e:
            self.notify(f"Patch failed: {e}", severity="error")

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
    set_terminal_title("lma")
    app = LemonaidApp()
    app.run()


if __name__ == "__main__":
    main()
