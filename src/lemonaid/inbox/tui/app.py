"""Main Lemonaid TUI application."""

import contextlib
import os
from datetime import datetime

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header, Static

from ...claude import watcher as claude_watcher
from ...claude.patcher import apply_patch, check_status, find_binary
from ...codex import watcher as codex_watcher
from ...config import load_config
from ...handlers import handle_notification
from ...lemon_watchers import detect_terminal_env, start_unified_watcher
from .. import db
from .screens import RenameScreen
from .utils import set_terminal_title, styled_cell


def _build_bindings(keys: str, action: str, label: str, show: bool = True) -> list[Binding]:
    """Build Binding objects for all keys mapped to an action.

    Args:
        keys: String of characters, each is a key binding
        action: The action name (without 'action_' prefix)
        label: Human-readable label for the action
        show: Whether to show in footer (only first key will be shown)

    Returns:
        List of Binding objects
    """
    if not keys:
        return []

    bindings = []
    # First key gets the visible binding
    bindings.append(Binding(keys[0], action, label, show=show))

    # Additional keys get hidden bindings
    for key in keys[1:]:
        bindings.append(Binding(key, action, label, show=False))

    return bindings


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

    def __init__(self, scratch_mode: bool = False) -> None:
        super().__init__()
        self.config = load_config()
        self._setup_keybindings()
        self.terminal_env = detect_terminal_env()
        self._claude_patch_status: str | None = None
        self._claude_binary = find_binary()
        self._scratch_mode = scratch_mode
        # Enable ANSI colors for terminal transparency support
        if self.config.tui.transparent:
            self.ansi_color = True
            self.dark = True  # Use dark theme as base

    def _setup_keybindings(self) -> None:
        """Build keybindings from config."""
        kb = self.config.tui.keybindings

        # Main commands
        for b in _build_bindings(kb.quit, "quit", "Quit"):
            self.bind(b.key, b.action, description=b.description, show=b.show)
        self.bind("escape", "quit", description="Quit", show=False)

        for b in _build_bindings(kb.refresh, "refresh", "Refresh", show=False):
            self.bind(b.key, b.action, description=b.description, show=b.show)

        for b in _build_bindings(kb.jump_unread, "jump_unread", "Jump Unread"):
            self.bind(b.key, b.action, description=b.description, show=b.show)

        for b in _build_bindings(kb.mark_read, "mark_read", "Mark Read"):
            self.bind(b.key, b.action, description=b.description, show=b.show)

        for b in _build_bindings(kb.archive, "archive", "Archive"):
            self.bind(b.key, b.action, description=b.description, show=b.show)

        for b in _build_bindings(kb.rename, "rename", "Rename"):
            self.bind(b.key, b.action, description=b.description, show=b.show)

        # Patch Claude (always hidden, always 'P')
        self.bind("P", "patch_claude", description="Patch Claude", show=False)

        # Arrow key alternatives (if configured)
        if len(kb.up_down) == 2:
            up, down = kb.up_down
            self.bind(up, "cursor_up", description="Up", show=False)
            self.bind(down, "cursor_down", description="Down", show=False)

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
        self._refresh_notifications()
        # Auto-refresh every 2 seconds
        self.set_interval(1.0, self._refresh_notifications)
        # Start transcript watchers for auto-dismiss, message updates, and exit detection
        start_unified_watcher(
            backends=[claude_watcher, codex_watcher],
            get_active=self._get_active_for_watcher,
            mark_read=self._mark_channel_read,
            update_message=self._update_channel_message,
            archive_channel=self._archive_channel,
        )
        # Check Claude patch status after initial render (reads 180MB binary)
        self.call_later(self._check_claude_patch)

    def _check_claude_patch(self) -> None:
        """Check Claude Code patch status in a background thread."""
        if not self._claude_binary:
            self._claude_patch_status = None
            return

        import threading

        def check():
            status = check_status(self._claude_binary)
            # Schedule UI update back on main thread
            self.call_from_thread(self._set_patch_status, status)

        threading.Thread(target=check, daemon=True).start()

    def _set_patch_status(self, status: str) -> None:
        """Set patch status and refresh UI (called from main thread)."""
        self._claude_patch_status = status
        self._refresh_notifications()

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
                styled_cell(created, is_unread),
                indicator,
                styled_cell(n.name or "", is_unread),
                styled_cell(n.message, is_unread),
                styled_cell(n.channel, is_unread),
                styled_cell(str(n.id), is_unread),
                styled_cell(tty, is_unread),
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

    def action_quit(self) -> None:
        """Quit the app, or just hide the pane in scratch mode."""
        if self._scratch_mode:
            self._hide_scratch_pane()
        else:
            self.exit()

    def action_cursor_up(self) -> None:
        """Move cursor up in the table."""
        self.query_one(DataTable).action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move cursor down in the table."""
        self.query_one(DataTable).action_cursor_down()

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

    def action_rename(self) -> None:
        """Rename the selected session."""
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return

        row_key = self._get_current_row_key()
        if not row_key:
            return

        notification_id = int(row_key)
        with db.connect() as conn:
            notification = db.get(conn, notification_id)

        if not notification:
            return

        def handle_rename(new_name: str | None) -> None:
            if new_name is None:
                # User cancelled
                return
            # Empty string means clear override, otherwise set the name
            name_to_set = new_name.strip() if new_name.strip() else None
            with db.connect() as conn:
                db.update_name(conn, notification_id, name_to_set)
            self._refresh_notifications()

        self.push_screen(
            RenameScreen(current_name=notification.name or ""),
            handle_rename,
        )

    def action_jump_unread(self) -> None:
        """Jump directly to the earliest unread session."""
        with db.connect() as conn:
            env_filter = self.terminal_env if self.terminal_env != "unknown" else None
            notifications = db.get_active(conn, terminal_env=env_filter)

        # Find the earliest (oldest) unread - they're sorted newest first
        unread = [n for n in notifications if n.is_unread]
        if not unread:
            self.notify("No unread notifications", severity="information")
            return

        # Move cursor to earliest unread row, then select it (same path as Enter)
        earliest_row = len(unread) - 1
        table = self.query_one(DataTable)
        table.move_cursor(row=earliest_row)
        table.action_select_cursor()

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

    def _hide_scratch_pane(self) -> None:
        """Hide this pane by breaking it to a new window (for scratch mode)."""
        import subprocess

        pane_id = os.environ.get("TMUX_PANE")
        if pane_id:
            subprocess.run(
                ["tmux", "break-pane", "-d", "-s", pane_id],
                capture_output=True,
            )

    def _get_active_for_watcher(
        self,
    ) -> list[tuple[str, str, str, float, bool, str | None]]:
        """Get active notifications for the transcript watcher.

        Returns list of (channel, session_id, cwd, created_at, is_unread, tty).
        """
        with db.connect() as conn:
            env_filter = self.terminal_env if self.terminal_env != "unknown" else None
            notifications = db.get_active(conn, terminal_env=env_filter)

        result = []
        for n in notifications:
            session_id = n.metadata.get("session_id")
            cwd = n.metadata.get("cwd")
            tty = n.metadata.get("tty")
            if session_id and cwd:
                result.append(
                    (n.channel, session_id, cwd, n.created_at, n.is_unread, tty)
                )
        return result

    def _mark_channel_read(self, channel: str) -> int:
        """Mark all notifications for a channel as read."""
        with db.connect() as conn:
            return db.mark_all_read_for_channel(conn, channel)

    def _update_channel_message(self, channel: str, message: str) -> int:
        """Update the message for a channel."""
        with db.connect() as conn:
            return db.update_message(conn, channel, message)

    def _archive_channel(self, channel: str) -> None:
        """Archive all notifications for a channel (session exited)."""
        with db.connect() as conn:
            notification = db.get_by_channel(conn, channel, unread_only=False)
            if notification:
                db.archive(conn, notification.id)

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
                # In scratch/auto-dismiss mode, hide the pane after navigation
                if self._scratch_mode:
                    self._hide_scratch_pane()


def main() -> None:
    set_terminal_title("lma")
    app = LemonaidApp()
    app.run()
