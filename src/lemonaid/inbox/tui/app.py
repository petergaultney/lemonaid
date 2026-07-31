"""Main Lemonaid TUI application."""

import contextlib
import dataclasses
import os
import shlex
import subprocess
import threading
import time
from collections import abc
from datetime import datetime
from typing import cast

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Header, Input, Static

from ... import claude, codex, openclaw, opencode
from ... import resume as resume_mod
from ...claude.patcher import apply_patch, check_status, find_binary
from ...config import load_config
from ...handlers import handle_notification
from ...lemon_watchers import (
    detect_terminal_switch_source,
    fish_path,
    start_unified_watcher,
)
from ...log import get_logger
from ...tmux.session import spawn_session
from .. import db, undo
from .screens import RenameScreen, SnoozeScreen, format_wake_time
from .utils import set_terminal_title, styled_cell

_DAY_SECONDS = 86400
_NAME_REFRESH_SECONDS = 20  # transcript re-scan cadence for session-name upgrades
_KEY_HINT_SECONDS = 10  # how long the footer's key hints stay up before yielding the row

_NAME_COLUMN = 3
_BRANCH_COLUMN = 4
_MESSAGE_COLUMN = 6
_TTY_COLUMN = 7
# Terminal widths at which the weakest columns stop earning their space.
# Crossing a threshold takes some width back from Name to pay for the column it
# re-introduces; that trade is intended, and Name stays far above the fixed
# 14 chars it had before these breakpoints existed.
_WIDE_LAYOUT_COLS = 132
_MEDIUM_LAYOUT_COLS = 104


_log = get_logger("tui")


def _format_timestamp(ts: float) -> str:
    dt = datetime.fromtimestamp(ts)
    if time.time() - ts < _DAY_SECONDS:
        return dt.strftime("%H:%M:%S")
    return dt.strftime("%Y-%m-%d")


def _backend_label(channel: str, overrides: dict[str, str]) -> str:
    prefix = channel.split(":")[0] if ":" in channel else channel
    return overrides.get(prefix, prefix)


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


def _sync_rows(table: DataTable, rows: list[tuple[str, list[Text]]]) -> bool:
    """Bring a DataTable in line with `rows`, in place where possible.

    `table.clear()` plus re-adding resets the cursor and scroll offset, which
    reads as the list flashing to the top on every refresh tick. When the row set
    and its order are unchanged — the common case, where only a message or status
    moved — cells are updated in place and the cursor never moves.

    Returns True if the table was rebuilt, meaning the caller has to restore the
    cursor itself. Textual has no public row-reorder API, so a genuine order
    change still costs a rebuild.
    """
    if [str(key.value) for key in table.rows] == [key for key, _ in rows]:
        for key, cells in rows:
            row_index = table.get_row_index(key)
            for column, value in enumerate(cells):
                table.update_cell_at((row_index, column), value, update_width=False)
        return False

    table.clear()
    for key, cells in rows:
        table.add_row(*cells, key=key)

    return True


def _hide_columns(table: DataTable, indices: abc.Container[int], labels: dict[int, str]) -> None:
    """Collapse the given columns to zero width, restoring the rest.

    Textual's DataTable has no column-visibility flag, so a hidden column is one
    with no label and no width. `labels` supplies the text to restore.
    """
    for i, column in enumerate(table.columns.values()):
        hidden = i in indices
        column.label = Text("" if hidden else labels.get(i, ""))
        if hidden:
            column.auto_width = False
            column.width = 0


def _rendered_width(table: DataTable) -> int:
    """The row width DataTable will report as its virtual width.

    Mirrors Column.get_render_width, which adds cell padding on both sides of every
    column — including one collapsed to zero width, which still costs its padding.
    """
    return sum(c.width + 2 * table.cell_padding for c in table.columns.values())


def _vertical_scrollbar_width(table: DataTable) -> int:
    """Width to hold back for the vertical scrollbar, whether or not it's showing.

    Reserved unconditionally rather than keyed on `show_vertical_scrollbar`: the two
    scrollbars are mutually dependent (narrower columns can retract the horizontal
    bar, which grows the viewport, which can retract the vertical one), so reading
    the live flag oscillates between two layouts. Costs two columns of flex width on
    a list short enough not to scroll.
    """
    return int(table.styles.scrollbar_size_vertical or 0)


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
    # A hidden column has been collapsed to zero width and draws no padding.
    hidden = sum(1 for i, c in enumerate(columns) if i not in flex_indices and not c.width)
    padding_total = 2 * table.cell_padding * (len(columns) - hidden) + 1
    fixed_total = sum(c.width for i, c in enumerate(columns) if i not in flex_indices)
    remaining = total_width - fixed_total - padding_total
    if remaining <= 0:
        return

    # Honour the minimums only while they fit. When the terminal is too narrow
    # for all of them, fall back to pure proportional division rather than
    # overflowing the table horizontally.
    total_weight = sum(frac for _, _, frac in flex_specs)
    honour_minimums = sum(min_w for _, min_w, _ in flex_specs) <= remaining

    budget = remaining
    for position, (idx, min_w, frac) in enumerate(flex_specs):
        if idx >= len(columns):
            continue

        share = int(remaining * frac / total_weight) if total_weight else min_w
        width = max(share, min_w) if honour_minimums else share
        # The last flex column absorbs the rounding remainder so the row fills
        # the width exactly instead of leaving a ragged gap.
        if position == len(flex_specs) - 1:
            width = max(width, budget)

        columns[idx].auto_width = False
        columns[idx].width = min(width, budget)
        budget -= columns[idx].width

    # `padding_total` only approximates what DataTable will charge, so reconcile
    # against the real measure: overshooting by one cell costs a whole row of height
    # to a horizontal scrollbar. Trim the widest column first and Name last.
    overflow = _rendered_width(table) - total_width
    while overflow > 0:
        trimmable = [idx for idx, _, _ in flex_specs if idx < len(columns) and columns[idx].width]
        if not trimmable:
            break

        # Name only gives up cells once nothing else has any left to give.
        candidates = [idx for idx in trimmable if idx != _NAME_COLUMN] or trimmable
        widest = max(candidates, key=lambda idx: columns[idx].width)
        columns[widest].width -= 1
        overflow -= 1


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

    /* Only ever displayed while the Footer is hidden, so it takes the Footer's
       row rather than costing the list a second one. */
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

    #snoozed_table {
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
        self._snoozed_mode = False
        self._history_filter = ""
        self._undo_stack = undo.Stack()
        self._last_name_refresh = 0.0
        self._exec_on_exit: tuple[str, list[str]] | None = None
        self._keys_shown = True
        self._hint_timer: Timer | None = None
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

        for b in _build_bindings(kb.snooze, "snooze", "Snooze"):
            self.bind(b.key, b.action, description=b.description, show=b.show)

        for b in _build_bindings(kb.snoozed_list, "toggle_snoozed", "Snoozed"):
            self.bind(b.key, b.action, description=b.description, show=b.show)

        for b in _build_bindings(kb.undo, "undo", "Undo"):
            self.bind(b.key, b.action, description=b.description, show=b.show)

        for b in _build_bindings(kb.history, "toggle_history", "History"):
            self.bind(b.key, b.action, description=b.description, show=b.show)

        for b in _build_bindings(kb.copy_resume, "copy_resume", "Copy"):
            self.bind(b.key, b.action, description=b.description, show=False)

        for b in _build_bindings(kb.tmux_resume, "tmux_resume", "Tmux"):
            self.bind(b.key, b.action, description=b.description, show=False)

        self.bind("slash", "filter_history", description="Filter", show=False)

        # Patch Claude (always hidden, always 'P')
        self.bind("P", "patch_claude", description="Patch Claude", show=False)

        # Key hints share the bottom row with the status text, so they're a toggle
        # rather than a permanent fixture. Hidden from the footer it controls.
        self.bind("question_mark", "toggle_keys", description="Keys", show=False)

        # Cross-table arrow navigation (always active)
        self.bind("up", "cursor_up", description="Up", show=False)
        self.bind("down", "cursor_down", description="Down", show=False)

        # Additional up/down keys (vim-style, if configured)
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
        yield DataTable(id="snoozed_table")
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

        snoozed_table = self.query_one("#snoozed_table", DataTable)
        self._setup_table(snoozed_table, wake_column=True)

        # Hide other sources section and the alternate views initially
        self.query_one("#other_sources_label", Static).display = False
        other_table.display = False
        history_table.display = False
        snoozed_table.display = False
        self.query_one("#history_filter", Input).display = False

        self._refresh_notifications()
        self.set_interval(1.0, self._refresh_notifications)
        # Start transcript watchers for auto-dismiss, message updates, and exit detection
        start_unified_watcher(
            backends=cast(
                list,
                [claude.watcher, codex.watcher, openclaw.watcher, opencode.watcher],
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
        self._show_keys(True)
        self._hint_timer = self.set_timer(_KEY_HINT_SECONDS, lambda: self._show_keys(False))

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

        # Name carries Claude's conversation title, which is what actually
        # distinguishes one session from another, so it gets the largest share of
        # flex space. Narrower terminals can't fit every column, and starving
        # Name to keep the others is the wrong trade: TTY is diagnostic, Branch is
        # usually inferable from CWD, and Message is mostly "Waiting in <path>",
        # which CWD already says. They come back as the terminal widens.
        if w >= _WIDE_LAYOUT_COLS:
            hidden: set[int] = set()
            flex = [(3, 40, 0.46), (4, 10, 0.11), (5, 12, 0.13), (6, 16, 0.30)]
        elif w >= _MEDIUM_LAYOUT_COLS:
            hidden = {_TTY_COLUMN}
            flex = [(3, 36, 0.48), (4, 9, 0.10), (5, 11, 0.12), (6, 14, 0.30)]
        else:
            hidden = {_TTY_COLUMN, _BRANCH_COLUMN, _MESSAGE_COLUMN}
            flex = [(3, 30, 0.72), (5, 10, 0.28)]

        for table_id in ("#main_table", "#other_sources_table", "#history_table", "#snoozed_table"):
            table = self.query_one(table_id, DataTable)
            # The snoozed view's last column is a wake time, not a TTY, and is
            # the whole point of that view — never hide it.
            table_hidden = hidden - {_TTY_COLUMN} if table_id == "#snoozed_table" else hidden
            _hide_columns(table, table_hidden, self._column_labels(table_id))
            # Which columns to show keys off the terminal width, so the layout doesn't
            # reshuffle when a scrollbar appears; how wide to draw them keys off what
            # the table can actually paint into.
            _stretch_columns(table, flex, w - _vertical_scrollbar_width(table))

    def _column_labels(self, table_id: str) -> dict[int, str]:
        return {
            0: "Time",
            3: "Name",
            _BRANCH_COLUMN: "Branch",
            5: "CWD",
            6: "Message",
            _TTY_COLUMN: "Wakes" if table_id == "#snoozed_table" else "TTY",
        }

    def _setup_table(self, table: DataTable, wake_column: bool = False) -> None:
        table.cursor_type = "row"
        # Time holds "HH:MM:SS" or the wider "YYYY-MM-DD" for older sessions.
        table.add_column("Time", width=10)
        table.add_column("", width=1)  # Unread indicator
        table.add_column("", width=3)  # Backend icon
        table.add_column("Name", width=24)
        table.add_column("Branch", width=12)
        table.add_column("CWD", width=16)
        table.add_column("Message", width=30)  # Stretched on resize
        # TTY holds "ttysNNN"; the snoozed view's wake label is "Fri 09:00".
        table.add_column("Wakes" if wake_column else "TTY", width=9 if wake_column else 7)

    def _active_table_id(self) -> str:
        if self._history_mode:
            return "#history_table"
        if self._snoozed_mode:
            return "#snoozed_table"

        return "#main_table"

    def _get_current_row_key(self) -> str | None:
        """Get the row key (notification ID) at current cursor."""
        table = self.query_one(self._active_table_id(), DataTable)
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

    def _active_row(self, n: db.Notification) -> tuple[str, list[Text]]:
        """Build the main-table row for a session, keyed by notification id."""
        is_unread = n.is_unread
        return str(n.id), [
            styled_cell(_format_timestamp(n.created_at), is_unread),
            Text("●", style="bold cyan") if is_unread else Text(""),
            styled_cell(_backend_label(n.channel, self.config.tui.backend_labels), is_unread),
            styled_cell(n.name or "", is_unread),
            styled_cell(n.metadata.get("git_branch", ""), is_unread),
            styled_cell(fish_path(n.metadata.get("cwd", "")), is_unread),
            styled_cell(n.message, is_unread),
            styled_cell(n.metadata.get("tty", "").replace("/dev/", ""), is_unread),
        ]

    def _other_row(self, n: db.Notification) -> tuple[str, list[Text]]:
        """Build the non-switchable-table row for a session. Always dimmed."""
        return str(n.id), [
            Text(_format_timestamp(n.created_at), style="dim"),
            Text("○", style="dim") if n.is_unread else Text(""),
            Text(_backend_label(n.channel, self.config.tui.backend_labels), style="dim"),
            Text(n.name or "", style="dim"),
            Text(n.metadata.get("git_branch", ""), style="dim cyan"),
            Text(fish_path(n.metadata.get("cwd", "")), style="dim"),
            Text(n.message, style="dim"),
            Text(n.metadata.get("tty", "").replace("/dev/", ""), style="dim"),
        ]

    def _refresh_notifications(self, *, stay_on_unread: bool = False) -> None:
        # Alternate views own the screen; the periodic tick still needs to wake
        # expired snoozes so they're waiting when the inbox comes back.
        if self._history_mode or self._snoozed_mode:
            self._wake_expired_snoozes()
            if self._snoozed_mode:
                self._refresh_snoozed()
            return

        self._wake_expired_snoozes()
        self._refresh_session_names()

        main_table = self.query_one("#main_table", DataTable)
        other_table = self.query_one("#other_sources_table", DataTable)
        other_label = self.query_one("#other_sources_label", Static)

        # Remember current selection (both key and index) for both tables
        current_key = self._get_current_row_key()
        current_index = self._get_current_row_index()
        other_index = other_table.cursor_coordinate.row if other_table.row_count > 0 else 0
        focused_on_other = self.focused is other_table

        with db.connect() as conn:
            env_filter = self.current_env if self.current_env != "unknown" else None
            # Main table: only sessions switchable from the current environment
            current_notifications = db.get_active(conn, switch_source=env_filter)
            # Lower pane: live sessions from other switchable terminals.
            # Headless sessions (switch_source IS NULL) are excluded — they can't be
            # switched to from anywhere, so they belong in history instead.
            if env_filter:
                all_notifications = db.get_active(conn, switch_source=None)
                other_notifications = [
                    n
                    for n in all_notifications
                    if n.switch_source is not None and n.switch_source != env_filter
                ]
            else:
                other_notifications = []

        unread_count = sum(1 for n in current_notifications if n.is_unread)
        rebuilt = _sync_rows(main_table, [self._active_row(n) for n in current_notifications])

        # Populate non-switchable table (always dim, not interactive).
        # Hide it if the terminal is too short — main table gets priority.
        _MIN_MAIN_ROWS = 5
        chrome = 3  # header + other_label + the shared status/footer row
        other_height = min(len(other_notifications), 8)
        room_for_main = self.size.height - chrome - other_height
        show_other = other_notifications and room_for_main >= _MIN_MAIN_ROWS

        if show_other:
            other_label.update("── non-switchable ──")
            other_label.display = True
            other_table.display = True
            _sync_rows(other_table, [self._other_row(n) for n in other_notifications])
        else:
            other_table.clear()
            other_label.display = False
            other_table.display = False
            if focused_on_other:
                self.query_one("#main_table", DataTable).focus()

        # Restore other table cursor
        if other_table.row_count > 0:
            other_table.move_cursor(row=min(other_index, other_table.row_count - 1))

        # Restore cursor position. An in-place update leaves the cursor where it
        # was, so only a rebuild (or an explicit jump) needs to move it — moving
        # it every tick is what made the list flash back to the top.
        if main_table.row_count > 0 and (rebuilt or stay_on_unread):
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

        read_count = main_table.row_count - unread_count
        env_label = f" [{self.current_env}]" if self.current_env != "unknown" else ""
        status_text = f"{unread_count} unread, {read_count} read{env_label}"

        # Add patch warning if Claude is unpatched
        if self._claude_patch_status == "unpatched":
            status_text += "  |  [bold cyan]P[/]atch Claude for faster notifications"

        self._set_status(status_text)

    def action_quit(self) -> None:
        """Quit the app, or just hide the pane in scratch mode.

        In history mode, q quits directly (use h to return to active view).
        The snoozed list is a subview, so q backs out of it instead.
        """
        if self._snoozed_mode:
            self._set_snoozed_mode(False)
            return

        if self._scratch_mode:
            self._hide_scratch_pane()
        else:
            self.exit()

    def action_toggle_history(self) -> None:
        if self._snoozed_mode:
            self._set_snoozed_mode(False)
        self._set_history_mode(not self._history_mode)

    def action_toggle_snoozed(self) -> None:
        if self._history_mode:
            self._set_history_mode(False)
        self._set_snoozed_mode(not self._snoozed_mode)

    def action_toggle_keys(self) -> None:
        # An explicit toggle outranks the startup timer, which would otherwise
        # hide the hints part-way through the user reading them.
        if self._hint_timer is not None:
            self._hint_timer.stop()
            self._hint_timer = None

        self._show_keys(not self._keys_shown)

    def _show_keys(self, shown: bool) -> None:
        self._keys_shown = shown
        self.query_one(Footer).display = shown
        self.query_one("#status", Static).display = not shown

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    def _refresh_session_names(self) -> None:
        """Pull newly-available backend titles into the inbox.

        Claude names a session only once it has some content, so the name in the
        inbox starts as a tmux/cwd placeholder. Hook fires alone would leave a
        long-running session stuck with that placeholder, so re-check here.

        Throttled and run off the event loop: resolving a title reads a
        transcript, which is too slow to do synchronously on every tick.
        """
        now = time.time()
        if now - self._last_name_refresh < _NAME_REFRESH_SECONDS:
            return

        self._last_name_refresh = now
        threading.Thread(target=self._scan_session_names, daemon=True).start()

    def _scan_session_names(self) -> None:
        with db.connect() as conn:
            candidates = [
                (n.id, n.metadata.get("session_id", ""), n.metadata.get("cwd", ""))
                for n in db.get_active(conn, switch_source=None)
                # Sessions already showing a Claude /rename are settled. Anything
                # else is re-read: an AI title can still be superseded by a later
                # /rename, so having one is not a reason to stop looking.
                if n.channel.startswith("claude:")
                and n.metadata.get("name_source") != "claude_rename"
                and n.metadata.get("session_id")
                and n.metadata.get("cwd")
            ]

        upgraded = False
        for notification_id, session_id, cwd in candidates:
            resolved = claude.notify.resolve_session_name(session_id, cwd)
            if not resolved:
                continue

            with db.connect() as conn:
                if db.refresh_auto_name(conn, notification_id, resolved.name, resolved.source):
                    upgraded = True
                    _log.info(
                        "name upgraded: %d -> %r (%s)",
                        notification_id,
                        resolved.name,
                        resolved.source,
                    )

        if upgraded:
            self.call_from_thread(self._refresh_notifications)

    def _wake_expired_snoozes(self) -> None:
        with db.connect() as conn:
            woken = db.wake_expired(conn)
        for channel in woken:
            _log.info("snooze expired: %s", channel)

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
        for action in ("jump_unread", "mark_read", "archive", "snooze"):
            self._set_binding_footer(action, show=not enabled)

        # History-only actions
        for action in ("copy_resume", "filter_history", "tmux_resume"):
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
            if not resume_mod.has_resume_command(self.config, n.channel):
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

        count = history_table.row_count
        self._set_status(f"{count} archived session{'s' if count != 1 else ''}")

    def _set_snoozed_mode(self, enabled: bool) -> None:
        self._snoozed_mode = enabled

        main_table = self.query_one("#main_table", DataTable)
        snoozed_table = self.query_one("#snoozed_table", DataTable)
        other_label = self.query_one("#other_sources_label", Static)
        other_table = self.query_one("#other_sources_table", DataTable)

        # Inbox-only actions don't apply to the snoozed list
        for action in ("jump_unread", "mark_read", "snooze"):
            self._set_binding_footer(action, show=not enabled)

        self._set_binding_footer(
            "toggle_snoozed",
            label="Exit Snoozed" if enabled else "Snoozed",
        )
        self._set_binding_footer("select", label="Wake" if enabled else "Switch")
        self.refresh_bindings()

        if enabled:
            self.sub_title = "snoozed"
            main_table.display = False
            other_label.display = False
            other_table.display = False
            snoozed_table.display = True
            self._refresh_snoozed()
            snoozed_table.focus()
        else:
            self.sub_title = "attention inbox"
            snoozed_table.display = False
            main_table.display = True
            self._refresh_notifications()
            main_table.focus()

    def _refresh_snoozed(self) -> None:
        snoozed_table = self.query_one("#snoozed_table", DataTable)
        current_row = snoozed_table.cursor_coordinate.row if snoozed_table.row_count > 0 else 0

        with db.connect() as conn:
            notifications = db.get_snoozed(conn)

        rebuilt = _sync_rows(
            snoozed_table,
            [
                (
                    str(n.id),
                    [
                        Text(_format_timestamp(n.created_at), style="dim"),
                        Text("○", style="dim") if n.snooze_prev_status == "unread" else Text(""),
                        Text(
                            _backend_label(n.channel, self.config.tui.backend_labels), style="dim"
                        ),
                        Text(n.name or "", style=""),
                        Text(n.metadata.get("git_branch", ""), style="dim cyan"),
                        Text(fish_path(n.metadata.get("cwd", "")), style="dim"),
                        Text(n.message, style="dim"),
                        Text(
                            format_wake_time(n.snooze_until) if n.snooze_until else "",
                            style="yellow",
                        ),
                    ],
                )
                for n in notifications
            ],
        )

        if rebuilt and snoozed_table.row_count > 0:
            snoozed_table.move_cursor(row=min(current_row, snoozed_table.row_count - 1))

        count = snoozed_table.row_count
        self._set_status(
            f"{count} snoozed session{'s' if count != 1 else ''}  |  Enter to wake now"
        )

    def _wake_selected(self) -> None:
        """Wake the selected snoozed session and return it to the inbox."""
        row_key = self._get_current_row_key()
        if not row_key:
            return

        with db.connect() as conn:
            notification = db.get(conn, int(row_key))
            if not notification:
                return

            entry = undo.capture(
                conn,
                "unsnooze",
                f'Woke "{notification.name or notification.channel}"',
                undo.channel_row_ids(conn, notification.id),
            )
            db.unsnooze(conn, notification.channel)

        self._undo_stack.push(entry)
        _log.info("unsnooze: %s", notification.channel)
        self._refresh_snoozed()
        self.notify(f"{entry.description} — press {self._undo_key()} to undo")

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

        resume = resume_mod.build_resume_command(
            self.config, notification.channel, notification.metadata
        )
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

    def action_tmux_resume(self) -> None:
        """Spawn a new tmux session around the selected history entry."""
        if not self._history_mode:
            return

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

        resume = resume_mod.build_resume_command(
            self.config, notification.channel, notification.metadata
        )
        if not resume:
            self.notify("No cwd metadata — can't build resume command", severity="warning")
            return

        cwd, argv = resume

        # Unarchive so the session appears in the inbox once it starts
        with db.connect() as conn:
            conn.execute(
                "UPDATE notifications SET status = 'unread', read_at = NULL, created_at = ? WHERE id = ?",
                (time.time(), notification.id),
            )
            conn.commit()

        error = spawn_session(
            cwd=cwd,
            config=self.config.tmux_session,
            resume_argv=argv,
            channel=notification.channel,
            session_metadata=notification.metadata,
            session_name=notification.name or "",
        )
        if error:
            _log.warning("tmux_resume failed: %s", error)
            self.notify(error, severity="error")

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
        elif self._snoozed_mode and table.id == "snoozed_table":
            self._wake_selected()
        elif table.id == "main_table":
            table.action_select_cursor()

    def action_refresh(self) -> None:
        self._refresh_notifications()

    def _undo_key(self) -> str:
        keys = self.config.tui.keybindings.undo
        return keys[0] if keys else "z"

    def action_mark_read(self) -> None:
        table = self._focused_table()
        if table.row_count == 0:
            return

        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        if row_key:
            notification_id = int(row_key.value)
            with db.connect() as conn:
                n = db.get(conn, notification_id)
                if not n:
                    return

                entry = undo.capture(
                    conn,
                    "mark_read",
                    f'Marked read "{n.name or n.channel}"',
                    [notification_id],
                )
                db.mark_read(conn, notification_id)

            self._undo_stack.push(entry)
            _log.info("mark_read: %s", n.channel)
            # Keep cursor on unread items when possible
            self._refresh_notifications(stay_on_unread=True)

    def action_archive(self) -> None:
        """Archive the selected session (removes from active list)."""
        table = self._focused_table()
        if table.row_count == 0:
            return

        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        if not row_key:
            return

        notification_id = int(row_key.value)
        with db.connect() as conn:
            n = db.get(conn, notification_id)
            if not n:
                return

            # archive() touches every row on the channel, so snapshot them all.
            entry = undo.capture(
                conn,
                "archive",
                f'Archived "{n.name or n.channel}"',
                undo.channel_row_ids(conn, notification_id),
            )
            db.archive(conn, notification_id)

        self._undo_stack.push(entry)
        _log.info("archive: %s", n.channel)
        self._refresh_notifications()
        self.notify(f"{entry.description} — press {self._undo_key()} to undo")

    def action_snooze(self) -> None:
        """Snooze the selected session out of the inbox for a chosen duration."""
        if self._history_mode or self._snoozed_mode:
            return

        row_key = self._get_current_row_key()
        if not row_key:
            return

        notification_id = int(row_key)
        with db.connect() as conn:
            notification = db.get(conn, notification_id)

        if not notification:
            return

        def handle_snooze(until: float | None) -> None:
            if until is None:
                return

            with db.connect() as conn:
                entry = undo.capture(
                    conn,
                    "snooze",
                    f'Snoozed "{notification.name or notification.channel}" '
                    f"until {format_wake_time(until)}",
                    undo.channel_row_ids(conn, notification_id),
                )
                db.snooze(conn, notification_id, until)

            self._undo_stack.push(entry)
            _log.info("snooze: %s until %.0f", notification.channel, until)
            self._refresh_notifications()
            self.notify(f"{entry.description} — press {self._undo_key()} to undo")

        self.push_screen(
            SnoozeScreen(session_name=notification.name or ""),
            handle_snooze,
        )

    def action_undo(self) -> None:
        """Reverse the most recent undoable inbox change."""
        entry = self._undo_stack.pop()
        if entry is None:
            self.notify("Nothing to undo", severity="information")
            return

        with db.connect() as conn:
            restored = undo.restore(conn, entry)

        _log.info("undo: %s (%d rows)", entry.action, restored)
        if self._history_mode:
            self._refresh_history()
        elif self._snoozed_mode:
            self._refresh_snoozed()
        else:
            self._refresh_notifications()

        self.notify(f"Undid: {entry.description}")

    def action_rename(self) -> None:
        """Rename the selected session."""
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
                return

            name_to_set = new_name.strip() if new_name.strip() else None
            with db.connect() as conn:
                entry = undo.capture(
                    conn,
                    "rename",
                    f'Renamed "{notification.name or notification.channel}"',
                    [notification_id],
                )
                db.update_name(conn, notification_id, name_to_set)

            self._undo_stack.push(entry)
            if self._history_mode:
                self._refresh_history()
            else:
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

        if event.data_table.id == "snoozed_table":
            self._wake_selected()
            return

        if event.data_table.id != "main_table":
            return

        if event.row_key is None:
            return

        notification_id = int(event.row_key.value)

        with db.connect() as conn:
            notification = db.get(conn, notification_id)
            if notification:
                # Channel drives cwd-based fallback resolution; name is the
                # session name to reuse if the pane is gone and we respawn.
                metadata = {
                    **notification.metadata,
                    "channel": notification.channel,
                    "name": notification.name or "",
                }
                if not handle_notification(
                    metadata,
                    self.config,
                    switch_source=notification.switch_source,
                ):
                    self.notify("Could not switch to or recreate that session", severity="warning")
                    return

                # In scratch/auto-dismiss mode, hide the pane after navigation
                if self._scratch_mode:
                    self._hide_scratch_pane()


def main() -> None:
    set_terminal_title("lma")
    app = LemonaidApp()
    app.run()
