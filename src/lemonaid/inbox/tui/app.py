"""Main Lemonaid TUI application."""

import contextlib
import dataclasses
import os
import shlex
import subprocess
import time
from datetime import datetime
from typing import cast

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header, Input, Static

from ...claude import watcher as claude_watcher
from ...claude.patcher import apply_patch, check_status, find_binary
from ...codex import watcher as codex_watcher
from ...config import load_config
from ...handlers import handle_notification
from ...lemon_watchers import (
    detect_terminal_switch_source,
    fish_path,
    start_unified_watcher,
)
from ...log import get_logger
from ...openclaw import watcher as openclaw_watcher
from ...opencode import watcher as opencode_watcher
from .. import db
from .screens import RenameScreen
from .utils import set_terminal_title, styled_cell

_DAY_SECONDS = 86400


_log = get_logger("tui")


def _format_timestamp(ts: float) -> str:
    dt = datetime.fromtimestamp(ts)
    if time.time() - ts < _DAY_SECONDS:
        return dt.strftime("%H:%M:%S")
    return dt.strftime("%Y-%m-%d")


_RESUMABLE_BACKENDS = {"claude", "codex", "openclaw", "opencode"}


def _backend_label(channel: str, overrides: dict[str, str]) -> str:
    prefix = channel.split(":")[0] if ":" in channel else channel
    return overrides.get(prefix, prefix)


def _build_resume_command(notification: db.Notification) -> tuple[str, list[str]] | None:
    """Build a (cwd, shell_command_string) for resuming a session.

    Returns None if there's not enough metadata to build a useful command.
    """
    cwd = notification.metadata.get("cwd")
    if not cwd:
        return None

    session_id = notification.metadata.get("session_id", "")
    if notification.channel.startswith("claude:") and session_id:
        return (cwd, ["claude", "--resume", session_id])

    if notification.channel.startswith("codex:") and session_id:
        return (cwd, ["codex", "resume", session_id])

    if notification.channel.startswith("openclaw:"):
        from ...openclaw.utils import build_resume_argv

        argv = build_resume_argv(notification.metadata)
        if argv:
            return (cwd, argv)

    if notification.channel.startswith("opencode:") and session_id:
        return (cwd, ["opencode", "--session", session_id])

    return None


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


def _stretch_columns(
    table: DataTable,
    flex_specs: list[tuple[int, int, float]],
    total_width: int,
) -> None:
    """Distribute remaining table width among flex columns.

    Textual DataTable doesn't natively expand columns to fill available width.
    Each flex_spec is (column_index, min_width, weight).
    Remaining space after fixed columns is divided proportionally by weight,
    with a minimum floor of min_width.
    """
    if not flex_specs or not table.columns or total_width <= 0:
        return

    columns = list(table.columns.values())
    flex_indices = {idx for idx, _, _ in flex_specs}
    padding_total = 2 * table.cell_padding * len(columns) + 1
    fixed_total = sum(c.width for i, c in enumerate(columns) if i not in flex_indices)
    remaining = total_width - fixed_total - padding_total
    if remaining <= 0:
        return

    total_weight = sum(frac for _, _, frac in flex_specs)
    for idx, min_w, frac in flex_specs:
        if idx < len(columns):
            share = int(remaining * frac / total_weight) if total_weight else min_w
            columns[idx].auto_width = False
            columns[idx].width = max(share, min_w)


class LemonaidApp(App):
    """Lemonaid TUI - attention inbox for your lemons."""

    CSS = """
    #main_table {
        height: 1fr;
    }

    #other_sources_label {
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
        text-style: italic;
    }

    #other_sources_table {
        height: auto;
        max-height: 8;
        color: $text-muted;
    }

    #status {
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }

    #history_filter {
        height: 3;
        border: solid $accent;
    }

    #history_table {
        height: 1fr;
    }
    """

    def __init__(self, scratch_mode: bool = False) -> None:
        super().__init__()
        self.config = load_config()
        self._setup_keybindings()
        self.current_env = detect_terminal_switch_source()
        self._claude_patch_status: str | None = None
        self._claude_binary = find_binary()
        self._scratch_mode = scratch_mode
        self._history_mode = False
        self._history_filter = ""
        self._exec_on_exit: tuple[str, list[str]] | None = None
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

        # Select row (Enter always works via DataTable, these are additional keys)
        for b in _build_bindings(kb.select, "select", "Switch"):
            self.bind(b.key, b.action, description=b.description, show=b.show)

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

        for b in _build_bindings(kb.history, "toggle_history", "History"):
            self.bind(b.key, b.action, description=b.description, show=b.show)

        for b in _build_bindings(kb.copy_resume, "copy_resume", "Copy"):
            self.bind(b.key, b.action, description=b.description, show=False)

        self.bind("slash", "filter_history", description="Filter", show=False)

        # Patch Claude (always hidden, always 'P')
        self.bind("P", "patch_claude", description="Patch Claude", show=False)

        # Arrow key alternatives (if configured)
        if len(kb.up_down) == 2:
            up, down = kb.up_down
            self.bind(up, "cursor_up", description="Up", show=False)
            self.bind(down, "cursor_down", description="Down", show=False)

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="main_table")
        yield Static("", id="other_sources_label")
        yield DataTable(id="other_sources_table", show_header=False)
        yield Input(placeholder="Filter by name, cwd, branch...", id="history_filter")
        yield DataTable(id="history_table")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "lemonaid"
        self.sub_title = "attention inbox"

        # Apply transparent styles if configured
        if self.config.tui.transparent:
            self.screen.styles.background = "transparent"
            self.query_one("#main_table", DataTable).styles.background = "transparent"
            self.query_one("#other_sources_table", DataTable).styles.background = "transparent"
            self.query_one("#history_table", DataTable).styles.background = "transparent"

        self._setup_table(self.query_one("#main_table", DataTable))
        other_table = self.query_one("#other_sources_table", DataTable)
        self._setup_table(other_table)

        history_table = self.query_one("#history_table", DataTable)
        self._setup_table(history_table)

        # Hide other sources section and history initially
        self.query_one("#other_sources_label", Static).display = False
        other_table.display = False
        history_table.display = False
        self.query_one("#history_filter", Input).display = False

        self._refresh_notifications()
        self.set_interval(1.0, self._refresh_notifications)
        # Start transcript watchers for auto-dismiss, message updates, and exit detection
        start_unified_watcher(
            backends=cast(
                list,
                [claude_watcher, codex_watcher, openclaw_watcher, opencode_watcher],
            ),
            get_active=self._get_active_for_watcher,
            mark_read=self._mark_channel_read,
            update_message=self._update_channel_message,
            archive_channel=self._archive_channel,
            mark_unread=self._mark_channel_unread,
        )
        self.call_later(self._check_claude_patch)
        self.call_later(self._stretch_all_tables)
        # Kick Footer to pick up dynamically-bound keys
        self.refresh_bindings()

    def _check_claude_patch(self) -> None:
        """Check Claude Code patch status in a child process (avoids GIL stall).

        The check does regex over a ~180MB binary. Running it in-process
        via a thread starves the Textual event loop because CPython's re
        module holds the GIL for the entire scan. A separate process has
        its own GIL.
        """
        if not self._claude_binary:
            self._claude_patch_status = None
            return

        import threading
        from concurrent.futures import ProcessPoolExecutor

        binary = self._claude_binary

        def check():
            try:
                with ProcessPoolExecutor(max_workers=1) as pool:
                    status = pool.submit(check_status, binary).result(timeout=10)
            except Exception:
                status = "unknown"
            self.call_from_thread(self._set_patch_status, status)

        threading.Thread(target=check, daemon=True).start()

    def _set_patch_status(self, status: str) -> None:
        """Set patch status and refresh UI (called from main thread)."""
        self._claude_patch_status = status
        self._refresh_notifications()

    def on_app_focus(self) -> None:
        """Refresh when the app regains focus."""
        self._refresh_notifications()

    def on_resize(self) -> None:
        self._stretch_all_tables()

    def _stretch_all_tables(self) -> None:
        w = self.size.width
        if w <= 0:
            return

        # (column_index, min_width, weight) — same layout for all tables
        # Name(3), Branch(4), CWD(5), Message(6) are flexible
        flex = [(3, 12, 0.10), (4, 12, 0.12), (5, 15, 0.15), (6, 25, 0.50)]
        _stretch_columns(self.query_one("#main_table", DataTable), flex, w)
        _stretch_columns(self.query_one("#other_sources_table", DataTable), flex, w)
        _stretch_columns(self.query_one("#history_table", DataTable), flex, w)

    def _setup_table(self, table: DataTable) -> None:
        table.cursor_type = "row"
        table.add_column("Time", width=10)
        table.add_column("", width=1)  # Unread indicator
        table.add_column("", width=3)  # Backend icon
        table.add_column("Name", width=14)
        table.add_column("Branch", width=14)
        table.add_column("CWD", width=25)
        table.add_column("Message", width=30)  # Stretched on resize
        table.add_column("TTY", width=10)

    def _get_current_row_key(self) -> str | None:
        """Get the row key (notification ID) at current cursor."""
        table = self.query_one("#main_table", DataTable)
        if table.row_count == 0:
            return None
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
            return row_key.value if row_key else None
        except Exception:
            return None

    def _get_current_row_index(self) -> int:
        """Get the current cursor row index."""
        table = self.query_one("#main_table", DataTable)
        return table.cursor_coordinate.row

    def _refresh_notifications(self, *, stay_on_unread: bool = False) -> None:
        # Don't refresh the active inbox while in history mode
        if self._history_mode:
            return

        main_table = self.query_one("#main_table", DataTable)
        other_table = self.query_one("#other_sources_table", DataTable)
        other_label = self.query_one("#other_sources_label", Static)

        # Remember current selection (both key and index) for both tables
        current_key = self._get_current_row_key()
        current_index = self._get_current_row_index()
        other_index = other_table.cursor_coordinate.row if other_table.row_count > 0 else 0
        focused_on_other = self.focused is other_table

        main_table.clear()
        other_table.clear()

        with db.connect() as conn:
            env_filter = self.current_env if self.current_env != "unknown" else None
            # Main table: only sessions switchable from the current environment
            current_notifications = db.get_active(conn, switch_source=env_filter)
            # Lower pane: everything we can't switch to
            if env_filter:
                all_notifications = db.get_active(conn, switch_source=None)
                other_notifications = [
                    n for n in all_notifications if n.switch_source != env_filter
                ]
            else:
                other_notifications = []

        unread_count = 0

        for n in current_notifications:
            created = _format_timestamp(n.created_at)
            tty = n.metadata.get("tty", "")
            if tty:
                tty = tty.replace("/dev/", "")

            is_unread = n.is_unread
            if is_unread:
                unread_count += 1

            indicator = Text("●", style="bold cyan") if is_unread else Text("")

            cwd = fish_path(n.metadata.get("cwd", ""))
            branch = n.metadata.get("git_branch", "")

            main_table.add_row(
                styled_cell(created, is_unread),
                indicator,
                styled_cell(_backend_label(n.channel, self.config.tui.backend_labels), is_unread),
                styled_cell(n.name or "", is_unread),
                styled_cell(branch, is_unread),
                styled_cell(cwd, is_unread),
                styled_cell(n.message, is_unread),
                styled_cell(tty, is_unread),
                key=str(n.id),
            )

        # Populate non-switchable table (always dim, not interactive).
        # Hide it if the terminal is too short — main table gets priority.
        _MIN_MAIN_ROWS = 5
        chrome = 4  # header + status + footer + other_label
        other_height = min(len(other_notifications), 8)
        room_for_main = self.size.height - chrome - other_height
        show_other = other_notifications and room_for_main >= _MIN_MAIN_ROWS

        if show_other:
            other_label.update("── non-switchable ──")
            other_label.display = True
            other_table.display = True

            for n in other_notifications:
                created = _format_timestamp(n.created_at)
                tty = n.metadata.get("tty", "")
                if tty:
                    tty = tty.replace("/dev/", "")

                indicator = Text("○", style="dim") if n.is_unread else Text("")

                cwd = fish_path(n.metadata.get("cwd", ""))
                branch = n.metadata.get("git_branch", "")

                other_table.add_row(
                    Text(created, style="dim"),
                    indicator,
                    Text(_backend_label(n.channel, self.config.tui.backend_labels), style="dim"),
                    Text(n.name or "", style="dim"),
                    Text(branch, style="dim cyan"),
                    Text(cwd, style="dim"),
                    Text(n.message, style="dim"),
                    Text(tty, style="dim"),
                    key=str(n.id),
                )
        else:
            other_label.display = False
            other_table.display = False
            if focused_on_other:
                self.query_one("#main_table", DataTable).focus()

        # Restore other table cursor
        if other_table.row_count > 0:
            other_table.move_cursor(row=min(other_index, other_table.row_count - 1))

        # Restore cursor position
        if main_table.row_count > 0:
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
                        target_index = main_table.get_row_index(current_key)
                # Fall back to same position (clamped to valid range)
                if target_index is None:
                    target_index = min(current_index, main_table.row_count - 1)
            main_table.move_cursor(row=target_index)

        status = self.query_one("#status", Static)
        displayed = main_table.row_count
        read_count = displayed - unread_count
        env_label = f" [{self.current_env}]" if self.current_env != "unknown" else ""
        status_text = f"{unread_count} unread, {read_count} read{env_label}"

        # Add patch warning if Claude is unpatched
        if self._claude_patch_status == "unpatched":
            status_text += "  |  [bold cyan]P[/]atch Claude for faster notifications"

        status.update(status_text)

    def action_quit(self) -> None:
        """Quit the app, or just hide the pane in scratch mode.

        In history mode, q quits directly (use h to return to active view).
        """
        if self._scratch_mode:
            self._hide_scratch_pane()
        else:
            self.exit()

    def action_toggle_history(self) -> None:
        self._set_history_mode(not self._history_mode)

    def _set_binding_footer(
        self, action: str, *, show: bool | None = None, label: str | None = None
    ) -> None:
        """Toggle visibility or label of the primary binding for an action."""
        found = False
        for key, bindings in self._bindings.key_to_bindings.items():
            for i, binding in enumerate(bindings):
                if binding.action != action:
                    continue

                replacements: dict = {}
                if not found and show is not None:
                    replacements["show"] = show
                if label is not None:
                    replacements["description"] = label
                if replacements:
                    self._bindings.key_to_bindings[key][i] = dataclasses.replace(
                        binding, **replacements
                    )
                found = True

    def _set_history_mode(self, enabled: bool) -> None:
        self._history_mode = enabled
        self._history_filter = ""

        main_table = self.query_one("#main_table", DataTable)
        other_label = self.query_one("#other_sources_label", Static)
        other_table = self.query_one("#other_sources_table", DataTable)
        history_table = self.query_one("#history_table", DataTable)
        history_filter = self.query_one("#history_filter", Input)

        # Inbox-only actions
        for action in ("jump_unread", "mark_read", "archive", "rename"):
            self._set_binding_footer(action, show=not enabled)

        # History-only actions
        for action in ("copy_resume", "filter_history"):
            self._set_binding_footer(action, show=enabled)

        # Relabel contextual actions
        self._set_binding_footer(
            "toggle_history",
            label="Exit History" if enabled else "History",
        )
        self._set_binding_footer(
            "select",
            label="Resume" if enabled else "Switch",
        )
        self.refresh_bindings()

        if enabled:
            self.sub_title = "session history"
            main_table.display = False
            other_label.display = False
            other_table.display = False
            history_table.display = True
            history_filter.display = False
            history_filter.value = ""
            self._refresh_history()
            history_table.focus()
        else:
            self.sub_title = "attention inbox"
            main_table.display = True
            history_table.display = False
            history_filter.display = False
            self._refresh_notifications()
            main_table.focus()

    def _refresh_history(self) -> None:
        history_table = self.query_one("#history_table", DataTable)
        current_row = history_table.cursor_coordinate.row if history_table.row_count > 0 else 0

        history_table.clear()

        with db.connect() as conn:
            notifications = db.get_history(conn, search=self._history_filter)

        for n in notifications:
            # Only show sessions from backends that support resume
            if not any(n.channel.startswith(f"{b}:") for b in _RESUMABLE_BACKENDS):
                continue

            created = _format_timestamp(n.created_at)
            cwd = fish_path(n.metadata.get("cwd", ""))
            branch = n.metadata.get("git_branch", "")

            history_table.add_row(
                Text(created, style="dim"),
                Text(""),  # No unread indicator for archived
                Text(_backend_label(n.channel, self.config.tui.backend_labels), style="dim"),
                Text(n.name or "", style=""),
                Text(branch, style="dim cyan"),
                Text(cwd, style="dim"),
                Text(n.message, style="dim"),
                Text("", style="dim"),  # No TTY for archived
                key=str(n.id),
            )

        if history_table.row_count > 0:
            history_table.move_cursor(row=min(current_row, history_table.row_count - 1))

        status = self.query_one("#status", Static)
        count = history_table.row_count
        status.update(f"{count} archived session{'s' if count != 1 else ''}")

    def _resume_session(self, *, copy_only: bool = False) -> None:
        """Resume the selected history session."""
        history_table = self.query_one("#history_table", DataTable)
        if history_table.row_count == 0:
            return

        row_key, _ = history_table.coordinate_to_cell_key(history_table.cursor_coordinate)
        if not row_key:
            return

        notification_id = int(row_key.value)
        with db.connect() as conn:
            notification = db.get(conn, notification_id)

        if not notification:
            return

        resume = _build_resume_command(notification)
        if not resume:
            self.notify("No cwd metadata — can't build resume command", severity="warning")
            return

        cwd, argv = resume
        quoted_argv = [shlex.quote(a) for a in argv]
        cmd_str = (
            f"cd {shlex.quote(cwd)} && {' '.join(quoted_argv)}"
            if argv
            else f"cd {shlex.quote(cwd)}"
        )
        mode = "copy" if copy_only else ("scratch-copy" if self._scratch_mode else "exec")
        _log.info("resume: %s (%s) -> %s", notification.channel, mode, cmd_str)

        # Unarchive so the session appears in the main inbox immediately
        with db.connect() as conn:
            conn.execute(
                "UPDATE notifications SET status = 'unread', read_at = NULL, created_at = ? WHERE id = ?",
                (time.time(), notification.id),
            )
            conn.commit()

        # Non-scratch, non-copy: exec in the current terminal
        if not copy_only and not self._scratch_mode and argv:
            self._exec_on_exit = (cwd, argv)
            self.exit()
            return

        # Copy to clipboard
        try:
            subprocess.run(["pbcopy"], input=cmd_str.encode(), check=True)
            self.notify(f"Copied: {cmd_str}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.notify(f"Resume: {cmd_str}", severity="information")

        if self._scratch_mode and not copy_only:
            self._hide_scratch_pane()

    def action_copy_resume(self) -> None:
        """Copy the resume command for the selected history session."""
        if not self._history_mode:
            return
        self._resume_session(copy_only=True)

    def action_filter_history(self) -> None:
        """Show the filter input in history mode."""
        if not self._history_mode:
            return
        history_filter = self.query_one("#history_filter", Input)
        history_filter.display = True
        history_filter.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "history_filter":
            self._history_filter = event.value
            self._refresh_history()

    def on_key(self, event: events.Key) -> None:
        """Handle special keys in the filter input."""
        if not (isinstance(self.focused, Input) and self.focused.id == "history_filter"):
            return

        # Down/Enter: keep filter active, move focus to table for navigation
        if event.key in ("down", "enter"):
            event.prevent_default()
            event.stop()
            self.query_one("#history_table", DataTable).focus()
            return

        # Escape: clear filter, hide it, focus table
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            self._history_filter = ""
            history_filter = self.query_one("#history_filter", Input)
            history_filter.value = ""
            history_filter.display = False
            self._refresh_history()
            self.query_one("#history_table", DataTable).focus()

    def _focused_table(self) -> DataTable:
        focused = self.focused
        if isinstance(focused, DataTable):
            return focused
        return self.query_one("#main_table", DataTable)

    def action_cursor_up(self) -> None:
        """Move cursor up, jumping to main table from other table when at top."""
        table = self._focused_table()
        if table.id == "other_sources_table" and table.cursor_coordinate.row == 0:
            main = self.query_one("#main_table", DataTable)
            main.focus()
            if main.row_count > 0:
                main.move_cursor(row=main.row_count - 1)
        else:
            table.action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move cursor down, jumping to other table from main table when at bottom."""
        table = self._focused_table()
        if table.id == "main_table" and table.cursor_coordinate.row >= table.row_count - 1:
            other = self.query_one("#other_sources_table", DataTable)
            if other.display and other.row_count > 0:
                other.focus()
                other.move_cursor(row=0)
                return

        table.action_cursor_down()

    def action_select(self) -> None:
        """Select the current row (same as Enter). No-op on non-switchable table."""
        table = self._focused_table()
        if self._history_mode and table.id == "history_table":
            self._resume_session()
        elif table.id == "main_table":
            table.action_select_cursor()

    def action_refresh(self) -> None:
        self._refresh_notifications()

    def action_mark_read(self) -> None:
        table = self._focused_table()
        if table.row_count == 0:
            return

        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        if row_key:
            notification_id = int(row_key.value)
            with db.connect() as conn:
                n = db.get(conn, notification_id)
                db.mark_read(conn, notification_id)
            if n:
                _log.info("mark_read: %s", n.channel)
            # Keep cursor on unread items when possible
            self._refresh_notifications(stay_on_unread=True)

    def action_archive(self) -> None:
        """Archive the selected session (removes from active list)."""
        table = self._focused_table()
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
        table = self.query_one("#main_table", DataTable)
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
            env_filter = self.current_env if self.current_env != "unknown" else None
            notifications = db.get_active(conn, switch_source=env_filter)

        # Find the earliest (oldest) unread - they're sorted newest first
        unread = [n for n in notifications if n.is_unread]
        if not unread:
            self.notify("No unread notifications", severity="information")
            return

        # Move cursor to earliest unread row, then select it (same path as Enter)
        earliest_row = len(unread) - 1
        table = self.query_one("#main_table", DataTable)
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
        pane_id = os.environ.get("TMUX_PANE")
        if pane_id:
            subprocess.run(
                ["tmux", "break-pane", "-d", "-s", pane_id],
                capture_output=True,
            )

    def _get_active_for_watcher(
        self,
    ) -> list[tuple[str, str, str, float, bool, str | None, str, str | None]]:
        """Get active notifications for the transcript watcher.

        Returns all sessions (not just switchable) so stale cleanup can
        archive dead sessions regardless of switch_source.

        Returns list of (channel, session_id, cwd, created_at, is_unread, tty, message, switch_source).
        """
        with db.connect() as conn:
            notifications = db.get_active(conn, switch_source=None)

        result = []
        for n in notifications:
            session_id = n.metadata.get("session_id")
            cwd = n.metadata.get("cwd")
            tty = n.metadata.get("tty")
            if session_id and cwd:
                result.append(
                    (
                        n.channel,
                        session_id,
                        cwd,
                        n.created_at,
                        n.is_unread,
                        tty,
                        n.message,
                        n.switch_source,
                    )
                )
        return result

    def _mark_channel_read(self, channel: str) -> int:
        """Mark all notifications for a channel as read."""
        with db.connect() as conn:
            return db.mark_all_read_for_channel(conn, channel)

    def _mark_channel_unread(self, channel: str) -> int:
        """Mark all notifications for a channel as unread (needs attention)."""
        with db.connect() as conn:
            return db.mark_unread_for_channel(conn, channel)

    def _update_channel_message(self, channel: str, message: str) -> int:
        """Update the message for a channel."""
        with db.connect() as conn:
            return db.update_message(conn, channel, message)

    def _archive_channel(self, channel: str) -> None:
        """Archive all notifications for a channel (session exited)."""
        with db.connect() as conn:
            conn.execute(
                "UPDATE notifications SET status = 'archived' WHERE channel = ?",
                (channel,),
            )
            conn.commit()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle Enter on a row.

        Main table: switch to session. History table: resume session.
        """
        if event.data_table.id == "history_table":
            self._resume_session()
            return

        if event.data_table.id != "main_table":
            return

        if event.row_key is None:
            return

        notification_id = int(event.row_key.value)

        with db.connect() as conn:
            notification = db.get(conn, notification_id)
            if notification:
                # Include channel in metadata for cwd-based fallback resolution
                metadata = {**notification.metadata, "channel": notification.channel}
                handle_notification(
                    metadata,
                    self.config,
                    switch_source=notification.switch_source,
                )
                # In scratch/auto-dismiss mode, hide the pane after navigation
                if self._scratch_mode:
                    self._hide_scratch_pane()


def main() -> None:
    set_terminal_title("lma")
    app = LemonaidApp()
    app.run()
