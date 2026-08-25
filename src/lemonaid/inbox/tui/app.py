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

from rich.console import Console
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
from ...handlers import check_pane_exists_by_tty, handle_notification
from ...lemon_watchers import (
    detect_terminal_switch_source,
    fish_path,
    start_unified_watcher,
)
from ...log import get_logger
from ...tmux.scratch import (
    _clear_state,
    _hide,
    current_position,
    flip_position,
    is_follow_enabled,
    move_scratch,
    save_current_size,
    size_has_drifted,
)
from ...tmux.session import spawn_session
from .. import db, undo
from .screens import RenameScreen, SnoozeScreen, format_wake_time
from .table import ClickToActTable
from .utils import FIELD_STYLES, UNREAD_MARKER_STYLE, set_terminal_title, styled_cell

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
# Cards are for panes shaped tall and narrow. Two ways to qualify: too narrow for
# the columns to fit at all, or enough taller than wide that the rows are the
# abundant resource and the columns are the scarce one. The second case matters
# because a pane can be wide enough to draw every column and still only have room
# to show four characters of each - which is what a side pane usually is.
_CARD_LAYOUT_COLS = 54
# A pane this narrow is a sidebar however short the window makes it. Above it,
# height decides - but only for panes narrow enough for the question to matter,
# so a sidebar does not change layout with the window it is joined to.
_SIDEBAR_COLS = 72
_CARD_ASPECT = 1.2  # rows per column, above which a pane counts as tall and narrow
_CARD_HEIGHT = 3  # headline + one context line + one message line
_CARD_MAX_HEIGHT = 14  # a card long enough to hold most messages whole
_CARD_MAX_SHARE = 0.4  # most of a tall pane one card may claim
_CARD_BODY_COLUMN = 0
_CARD_BACKEND_COLUMN = 1
# Two cells for the label ("CC", "cx", a two-cell emoji) and one to keep it
# off the card's text. The label is right-justified into it, so it is the
# pane's edge the labels line up against.
_BACKEND_WIDTH = 3
_CARD_MIN_TEXT = 16
_CARD_CHROME_ROWS = 4  # header, status row, and a little slack
_INDENT = " "  # one column, so a card's body clears the marker but little else
# Cards draw their own gutter - a single space, with the marker in the column
# before it - so the table adds none. Every column a narrow pane spends on
# padding is one the message doesn't get.
_CARD_CELL_PADDING = 0
_COLUMN_CELL_PADDING = 1  # DataTable's own default, restored on the way back

_TIME_CELL = 0
_UNREAD_CELL = 1
_BACKEND_CELL = 2
_NAME_CELL = 3
_BRANCH_CELL = 4
_CWD_CELL = 5
_MSG_CELL = 6


_CONSOLE = Console()  # for measuring wraps only; nothing is printed through it

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


def _as_card(
    cells: list[Text], width: int, context_lines: int = 1, message_lines: int = 1
) -> list[Text]:
    """Fold a column row into the cells of a card.

    Line 1 is the name, line 2 the short identifiers that place it, then the
    message. Every field the column layout carries survives except the TTY, which
    the two narrower column layouts already drop.

    The name and the context line are truncated, never wrapped: they are fields
    you scan for, so each has to sit in one predictable place down the list. Only
    the message wraps, because it is the one field that reads as prose.
    """
    # Cells arrive already coloured by field and dimmed by read state, so a card
    # rearranges them rather than restyling: both layouts then agree on what a
    # colour means, and fixing one fixes the other.
    #
    # The dot rides on the name rather than owning a column: it is empty for most
    # rows, and a permanently-indented card wastes width a narrow pane hasn't got.
    marker = cells[_UNREAD_CELL]
    headline = Text(marker.plain or " ", style=UNREAD_MARKER_STYLE) + Text(" ") + cells[_NAME_CELL]

    context = Text(" · ", style=FIELD_STYLES["backend"]).join(
        part for part in (cells[_TIME_CELL], cells[_CWD_CELL], cells[_BRANCH_CELL]) if part.plain
    )

    message = cells[_MSG_CELL]

    body = width - len(_INDENT)
    lines = [
        _truncated(headline, width),
        Text(_INDENT) + _truncated(context, body),
        # The message is the only field with the vertical space spent on it: it
        # is unbounded, and the one an ellipsis costs you most.
        *(Text(_INDENT) + line for line in _wrapped(message, body, message_lines)),
        Text(""),  # separates this card from the next
    ]
    # Right-justified so the backend labels line up against the pane's edge
    # whatever their width, rather than against each other's first character.
    backend = cells[_BACKEND_CELL].copy()
    backend.justify = "right"
    return [Text("\n").join(lines), backend]


def _without_marker(cells: list[Text]) -> list[Text]:
    """Cells minus the unread marker, for a table built without that column."""
    return [cell for index, cell in enumerate(cells) if index != _UNREAD_CELL]


def _row_height(cells: list[Text]) -> int:
    """A card is as tall as it needs to be - a padded one is mostly blank lines.

    The trailing separator counts: a row allocated shorter than its card clips
    that blank line, which made the gap between cards come and go depending on
    how far the message happened to wrap.
    """
    return len(cells[_CARD_BODY_COLUMN].plain.split("\n"))


def _truncated(line: Text, width: int) -> Text:
    line.truncate(width, overflow="ellipsis")
    return line


def _wrapped(line: Text, width: int, budget: int) -> list[Text]:
    """`line` over at most `budget` lines, or fewer when it doesn't need them."""
    # rich pads a wrap to the full width, which yields a blank last line when the
    # text ends near a boundary - and a blank there reads as a second separator.
    wrapped = [line for line in list(line.wrap(_CONSOLE, width))[:budget] if line.plain.strip()]
    if wrapped:
        # Whatever didn't fit in the budget is gone; say so on the last line.
        _truncated(wrapped[-1], width)

    return wrapped


def _sync_rows(
    table: DataTable,
    rows: list[tuple[str, list[Text]]],
    card_width: int = 0,
    shape: tuple[int, int] = (1, 1),
) -> bool:
    """Bring a DataTable in line with `rows`, in place where possible.

    `table.clear()` plus re-adding resets the cursor and scroll offset, which
    reads as the list flashing to the top on every refresh tick. When the row set
    and its order are unchanged — the common case, where only a message or status
    moved — cells are updated in place and the cursor never moves.

    Returns True if the table was rebuilt, meaning the caller has to restore the
    cursor itself. Textual has no public row-reorder API, so a genuine order
    change still costs a rebuild.
    """
    cards = card_width > 0
    shaped = [
        (key, _as_card(cells, card_width, *shape) if cards else cells) for key, cells in rows
    ]

    if [str(key.value) for key in table.rows] == [key for key, _ in shaped]:
        resized = False
        for key, cells in shaped:
            row_index = table.get_row_index(key)
            for column, value in enumerate(cells):
                table.update_cell_at((row_index, column), value, update_width=False)
            # A row keeps the height it was added with, so a card whose message
            # shortened would otherwise hold its old size and pad with blanks.
            if cards:
                row = table.rows[table.ordered_rows[row_index].key]
                height = _row_height(cells)
                if row.height != height:
                    row.height = height
                    resized = True
        if resized:
            table._update_dimensions(table.rows.keys())
        return False

    table.clear()
    for key, cells in shaped:
        table.add_row(*cells, key=key, height=_row_height(cells) if cards else 1)

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


def _fill_card_columns(table: DataTable, total_width: int) -> None:
    """Give the card body everything the backend label doesn't need.

    Two unpadded columns is arithmetic rather than a distribution, and the flex
    path's approximations cost a column here - which is the column that puts the
    backend label against the pane's edge instead of one short of it.
    """
    columns = list(table.columns.values())
    if len(columns) < 2 or total_width <= 0:
        return

    for column in columns:
        column.auto_width = False
    columns[_CARD_BACKEND_COLUMN].width = _BACKEND_WIDTH
    columns[_CARD_BODY_COLUMN].width = max(_CARD_MIN_TEXT, total_width - _BACKEND_WIDTH)


def _stretch_columns(
    table: DataTable,
    flex_specs: list[tuple[int, int, float, int]],
    total_width: int,
) -> None:
    """Distribute remaining table width among flex columns.

    Textual DataTable doesn't natively expand columns to fill available width.
    Each flex_spec is (column_index, min_width, weight, max_width); a max_width of
    0 means unbounded. Remaining space after fixed columns is divided
    proportionally by weight, floored at min_width and capped at max_width.

    The caps exist because a proportional share of a very wide terminal is mostly
    padding: names and paths have a length past which the extra columns show
    nothing. The last flex column is the message, whose length is unbounded, and
    it takes whatever the capped columns decline.
    """
    if not flex_specs or not table.columns or total_width <= 0:
        return

    columns = list(table.columns.values())
    flex_indices = {spec[0] for spec in flex_specs}
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
    total_weight = sum(spec[2] for spec in flex_specs)
    honour_minimums = sum(spec[1] for spec in flex_specs) <= remaining

    budget = remaining
    for position, (idx, min_w, frac, max_w) in enumerate(flex_specs):
        if idx >= len(columns):
            continue

        share = int(remaining * frac / total_weight) if total_weight else min_w
        width = max(share, min_w) if honour_minimums else share
        # The last flex column absorbs the rounding remainder so the row fills
        # the width exactly instead of leaving a ragged gap.
        if position == len(flex_specs) - 1:
            width = max(width, budget)
        elif max_w and honour_minimums:
            width = min(width, max_w)

        columns[idx].auto_width = False
        columns[idx].width = min(width, budget)
        budget -= columns[idx].width

    # `padding_total` only approximates what DataTable will charge, so reconcile
    # against the real measure: overshooting by one cell costs a whole row of height
    # to a horizontal scrollbar. Trim the widest column first and Name last.
    overflow = _rendered_width(table) - total_width
    while overflow > 0:
        trimmable = [
            spec[0] for spec in flex_specs if spec[0] < len(columns) and columns[spec[0]].width
        ]
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

    /* The bar above the list is the table's header row, which carries no labels
       in card layout - so it is free to carry the state of the list instead:
       whether anything in it wants you, and which list you are looking at.
       ANSI colours rather than theme variables, so it tracks the same terminal
       palette the unread marker is drawn from - the bar and the dot are the
       same colour by construction rather than by matching two hex values
       against one terminal's rendering of them. */
    DataTable > .datatable--header {
        background: ansi_bright_blue;
    }

    App.-unread DataTable > .datatable--header {
        background: ansi_bright_red;
        color: ansi_black;
    }

    /* History is a record, not a queue. Same specificity as the unread rule
       above and deliberately after it: which list you are looking at outranks
       what is in the one you left. */
    App.-history DataTable > .datatable--header {
        background: ansi_blue;
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
        self._card_layout = False
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

        for b in _build_bindings(kb.mark_unread, "mark_unread", "Mark Unread"):
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

        for b in _build_bindings(kb.flip_position, "flip_position", "Flip", show=False):
            self.bind(b.key, b.action, description=b.description, show=b.show)

        for b in _build_bindings(kb.save_size, "save_scratch_size", "Save Size", show=False):
            self.bind(b.key, b.action, description=b.description, show=b.show)

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
        yield ClickToActTable(id="main_table")
        yield Static("", id="other_sources_label")
        yield DataTable(id="other_sources_table", show_header=False)
        yield Input(placeholder="Filter by name, cwd, branch...", id="history_filter")
        # History resumes a session, replacing the terminal you are sitting in.
        # That wants picking a row and committing to it to stay separate.
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
        self._setup_table(history_table, marker_column=False)

        snoozed_table = self.query_one("#snoozed_table", DataTable)
        self._setup_table(snoozed_table, wake_column=True)

        # Hide other sources section and the alternate views initially
        self.query_one("#other_sources_label", Static).display = False
        other_table.display = False
        history_table.display = False
        snoozed_table.display = False
        self.query_one("#history_filter", Input).display = False

        self._refresh_notifications()
        self.set_interval(self.config.tui.refresh_interval, self._refresh_notifications)
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
            record_location=self._record_channel_location,
            sockets=self._recorded_sockets,
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

    def on_resize(self, event: events.Resize) -> None:
        # self.size still reports the old width while this event is being handled,
        # so every decision here keys off the size the event carries.
        width = event.size.width
        height = event.size.height
        # Cards and columns are different column sets, so crossing that threshold
        # rebuilds the tables rather than just restretching them.
        crossed = self._cards(width, height) != self._card_layout
        _log.info(
            "resize %sx%s -> %s%s",
            width,
            height,
            "cards" if self._cards(width, height) else "columns",
            " (changed)" if crossed else "",
        )
        if crossed:
            self._card_layout = self._cards(width, height)
            for table_id, wake in (
                ("#main_table", False),
                ("#other_sources_table", False),
                ("#history_table", False),
                ("#snoozed_table", True),
            ):
                self._setup_table(
                    self.query_one(table_id, DataTable),
                    wake_column=wake,
                    width=width,
                    height=height,
                )

        # Stretch before refilling: a card truncates to the width its column was
        # stretched to, which is not the placeholder width _setup_table gave it.
        self._stretch_all_tables(width)
        if crossed:
            self._refresh_notifications()

    def _cards(self, width: int | None = None, height: int | None = None) -> bool:
        """Whether to draw cards rather than columns.

        The scratch pane is a sidebar or a strip by declaration - its position -
        never by measurement. It takes its height from whichever window it is in
        and can be any width for a moment while tmux rearranges a layout, and a
        layout that follows those is a sidebar rendering as a top pane.

        A plain `lma` in a terminal decides from its shape: a pane narrow enough
        to be a sidebar gets cards whatever its height.
        """
        if self._scratch_mode:
            return current_position(self.config.tmux_session.scratch_position) == "left"

        w = self.size.width if width is None else width
        h = self.size.height if height is None else height
        if w <= 0:
            return False

        if w < _SIDEBAR_COLS:
            return True

        return h >= w * _CARD_ASPECT

    def _card_shape(self) -> tuple[int, int]:
        """How many lines the context and message get inside one card.

        A card grows only while the sessions on screen still fit: vertical space
        is what a tall pane has spare, but not at the cost of scrolling a list
        that used to fit. Everything past what the pane can hold stays at the
        minimum, since a taller card can't help a list that already overflows.
        """
        if not self._card_layout:
            return 1, 1

        rows = self.size.height - _CARD_CHROME_ROWS
        sessions = max(1, self.query_one("#main_table", DataTable).row_count)
        spare = rows // sessions - _CARD_HEIGHT
        if spare <= 0:
            return 1, 1

        # A card only ever renders the lines its message actually fills, so this
        # is a ceiling rather than padding - a short message stays short. The
        # share cap keeps one long message from owning a mostly-empty pane.
        ceiling = min(_CARD_MAX_HEIGHT, max(_CARD_HEIGHT, int(rows * _CARD_MAX_SHARE)))

        # All of it goes to the message: context is one truncated line by
        # design, so lines handed to it would be discarded.
        return 1, 1 + min(spare, ceiling - _CARD_HEIGHT)

    def _card_width(self) -> int:
        """Width the card's body column was stretched to, or 0 outside card mode.

        Keys off _card_layout rather than the current size: this decides how many
        cells a row has, and it must match the columns the tables were built with,
        which self.size disagrees with while a resize is being handled.
        """
        if not self._card_layout:
            return 0

        columns = list(self.query_one("#main_table", DataTable).columns.values())
        if len(columns) <= _CARD_BODY_COLUMN:
            return _CARD_MIN_TEXT

        return max(_CARD_MIN_TEXT, columns[_CARD_BODY_COLUMN].width)

    def _stretch_all_tables(self, width: int | None = None) -> None:
        w = self.size.width if width is None else width
        if w <= 0:
            return

        if self._card_layout:
            for table_id in (
                "#main_table",
                "#other_sources_table",
                "#history_table",
                "#snoozed_table",
            ):
                table = self.query_one(table_id, DataTable)
                _fill_card_columns(table, w - _vertical_scrollbar_width(table))
            return

        # Name carries Claude's conversation title, which is what actually
        # distinguishes one session from another, so it gets the largest share of
        # flex space. Narrower terminals can't fit every column, and starving
        # Name to keep the others is the wrong trade: TTY is diagnostic, Branch is
        # usually inferable from CWD, and Message is mostly "Waiting in <path>",
        # which CWD already says. They come back as the terminal widens.
        if w >= _WIDE_LAYOUT_COLS:
            hidden: set[int] = set()
            flex = [(3, 40, 0.46, 48), (4, 10, 0.11, 32), (5, 12, 0.13, 30), (6, 16, 0.30, 0)]
        elif w >= _MEDIUM_LAYOUT_COLS:
            hidden = {_TTY_COLUMN}
            flex = [(3, 36, 0.48, 44), (4, 9, 0.10, 28), (5, 11, 0.12, 28), (6, 14, 0.30, 0)]
        else:
            hidden = {_TTY_COLUMN, _BRANCH_COLUMN, _MESSAGE_COLUMN}
            flex = [(3, 30, 0.72, 0), (5, 10, 0.28, 0)]

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

    def _setup_table(
        self,
        table: DataTable,
        wake_column: bool = False,
        width: int | None = None,
        height: int | None = None,
        marker_column: bool = True,
    ) -> None:
        table.cursor_type = "row"
        # Idempotent: a resize across the card threshold re-runs this on a table
        # that already has the other layout's columns.
        if table.columns:
            table.clear(columns=True)

        if self._cards(width, height):
            table.cell_padding = _CARD_CELL_PADDING
            table.add_column("", width=20)  # The card body, stretched on resize
            table.add_column("", width=3)  # Backend icon, right-justified in it
            return

        table.cell_padding = _COLUMN_CELL_PADDING
        # Time holds "HH:MM:SS" or the wider "YYYY-MM-DD" for older sessions.
        table.add_column("Time", width=10)
        # Everything in history is archived, so the marker would always be
        # empty. Dropping it shifts every row left, which is a structural cue
        # that this is a different list rather than a differently-tinted one.
        if marker_column:
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
            styled_cell(_format_timestamp(n.created_at), is_unread, "time"),
            Text("●", style=UNREAD_MARKER_STYLE) if is_unread else Text(""),
            styled_cell(
                _backend_label(n.channel, self.config.tui.backend_labels), is_unread, "backend"
            ),
            styled_cell(n.name or "", is_unread, "name"),
            styled_cell(n.metadata.get("git_branch", ""), is_unread, "branch"),
            styled_cell(fish_path(n.metadata.get("cwd", "")), is_unread, "cwd"),
            styled_cell(n.message, is_unread, "message"),
            styled_cell(n.metadata.get("tty", "").replace("/dev/", ""), is_unread, "tty"),
        ]

    def _other_row(self, n: db.Notification) -> tuple[str, list[Text]]:
        """Build the non-switchable-table row for a session. Always dimmed."""
        return str(n.id), [
            styled_cell(_format_timestamp(n.created_at), False, "time"),
            Text("○", style="dim") if n.is_unread else Text(""),
            styled_cell(
                _backend_label(n.channel, self.config.tui.backend_labels), False, "backend"
            ),
            styled_cell(n.name or "", False, "name"),
            styled_cell(n.metadata.get("git_branch", ""), False, "branch"),
            styled_cell(fish_path(n.metadata.get("cwd", "")), False, "cwd"),
            styled_cell(n.message, False, "message"),
            styled_cell(n.metadata.get("tty", "").replace("/dev/", ""), False, "tty"),
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
        self.set_class(bool(unread_count), "-unread")
        rebuilt = _sync_rows(
            main_table,
            [self._active_row(n) for n in current_notifications],
            self._card_width(),
            self._card_shape(),
        )

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
            _sync_rows(
                other_table,
                [self._other_row(n) for n in other_notifications],
                self._card_width(),
                self._card_shape(),
            )
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

        position = current_position(self.config.tmux_session.scratch_position)
        if self._scratch_mode and is_follow_enabled() and size_has_drifted(position):
            dimension = "width" if position == "left" else "height"
            status_text += (
                f"  |  [bold cyan]{self.config.tui.keybindings.save_size}[/] save pane {dimension}"
            )

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
        for action in ("jump_unread", "mark_read", "mark_unread", "archive", "snooze"):
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

        self.set_class(enabled, "-history")

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

            cells = [
                styled_cell(created, False, "time", history=True),
                Text(""),  # archived: never a marker, but cards index by position
                styled_cell(
                    _backend_label(n.channel, self.config.tui.backend_labels),
                    False,
                    "backend",
                    history=True,
                ),
                styled_cell(n.name or "", False, "name", history=True),
                styled_cell(branch, False, "branch", history=True),
                styled_cell(cwd, False, "cwd", history=True),
                styled_cell(n.message, False, "message", history=True),
                Text(""),  # No TTY for archived
            ]
            card_width = self._card_width()
            shape = self._card_shape()
            # Columns drop the marker; cards have no columns to drop, and index
            # their fields by position.
            card = _as_card(cells, card_width, *shape) if card_width else _without_marker(cells)
            history_table.add_row(
                *card, key=str(n.id), height=_row_height(card) if card_width else 1
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
        for action in ("jump_unread", "mark_read", "mark_unread", "snooze"):
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
                        styled_cell(_format_timestamp(n.created_at), False, "time"),
                        Text("○", style="dim") if n.snooze_prev_status == "unread" else Text(""),
                        styled_cell(
                            _backend_label(n.channel, self.config.tui.backend_labels),
                            False,
                            "backend",
                        ),
                        styled_cell(n.name or "", False, "name"),
                        styled_cell(n.metadata.get("git_branch", ""), False, "branch"),
                        styled_cell(fish_path(n.metadata.get("cwd", "")), False, "cwd"),
                        styled_cell(n.message, False, "message"),
                        Text(
                            format_wake_time(n.snooze_until) if n.snooze_until else "",
                            style="bold yellow",
                        ),
                    ],
                )
                for n in notifications
            ],
            self._card_width(),
            self._card_shape(),
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

    def _switch_to_notification(self, notification) -> None:
        """Put the terminal on this session, recreating its pane if it is gone."""
        # Channel drives cwd-based fallback resolution; name is the
        # session name to reuse if the pane is gone and we respawn.
        if not handle_notification(
            {
                **notification.metadata,
                "channel": notification.channel,
                "name": notification.name or "",
            },
            self.config,
            switch_source=notification.switch_source,
        ):
            self.notify("Could not switch to or recreate that session", severity="warning")
            return

        # In scratch mode the pane hides after navigation, unless follow
        # mode is on - there the hook re-shows it in the target window.
        if self._scratch_mode and not is_follow_enabled():
            self._hide_scratch_pane()

    def _still_running(self, notification) -> bool:
        """Whether this session's pane is still there to switch to.

        Archiving is a guess made from outside the session - a watcher that
        could not find the pane - and it is wrong often enough that history
        holds sessions which never stopped running. Asked of the server the
        session was recorded on, since a pane on another one is absent from
        this one's listing for reasons that have nothing to do with it.
        """
        tty = notification.metadata.get("tty")
        if not tty or not notification.switch_source:
            return False

        return (
            check_pane_exists_by_tty(
                tty, notification.switch_source, notification.metadata.get("tmux_socket")
            )
            is True
        )

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

        # A session that never stopped needs returning to the inbox, not a
        # second copy of itself started next to the one already running.
        if not copy_only and self._still_running(notification):
            with db.connect() as conn:
                db.mark_unread(conn, notification.id)

            self._set_history_mode(False)
            self._refresh_notifications()
            self.notify(f"{notification.name or notification.channel} is running - back in the inbox")
            self._switch_to_notification(notification)
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

        if self._scratch_mode and not copy_only and not is_follow_enabled():
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

    def action_mark_unread(self) -> None:
        table = self._focused_table()
        if table.row_count == 0:
            return

        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        if not row_key:
            return

        notification_id = int(row_key.value)
        with db.connect() as conn:
            n = db.get(conn, notification_id)
            if not n or n.is_unread:
                return

            entry = undo.capture(
                conn,
                "mark_unread",
                f'Marked unread "{n.name or n.channel}"',
                [notification_id],
            )
            db.mark_unread(conn, notification_id)

        self._undo_stack.push(entry)
        _log.info("mark_unread: %s", n.channel)
        self._refresh_notifications()

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

    def action_flip_position(self) -> None:
        if not self._scratch_mode:
            return

        default = self.config.tmux_session.scratch_position
        position = flip_position(default)
        move_scratch(
            self.config.tmux_session.scratch_width
            if position == "left"
            else self.config.tmux_session.scratch_height,
            position,
        )
        self.notify(f"Pane moved to the {position}")

    def action_save_scratch_size(self) -> None:
        if not self._scratch_mode:
            return

        position = current_position(self.config.tmux_session.scratch_position)
        save_current_size(position)
        self.notify("Pane width saved" if position == "left" else "Pane height saved")
        self._refresh_notifications()

    def _hide_scratch_pane(self) -> None:
        """Hide the scratch pane back to its holding session.

        Clears the pane state file so follow hooks become no-ops until
        the user re-opens with prefix+l (which rewrites the state file).
        """
        pane_id = os.environ.get("TMUX_PANE")
        if pane_id:
            _clear_state()
            _hide(pane_id)

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

    def _recorded_sockets(self) -> dict[str, str]:
        """Which tmux server each active session was last seen on.

        The watcher asks tmux whether a pane is still there, and a pane on
        another server is absent from this one's listing for reasons that have
        nothing to do with the session being alive.
        """
        with db.connect() as conn:
            return {
                n.channel: socket
                for n in db.get_active(conn, switch_source="tmux")
                if (socket := n.metadata.get("tmux_socket"))
            }

    def _record_channel_location(
        self, channel: str, session: str, window: str, socket: str | None = None
    ) -> None:
        """Note where a session is sitting, so `tmux restore` can rebuild it.

        Done on the watcher's poll rather than only when a session notifies:
        an idle session would otherwise never record one, and those are the
        ones whose position is hardest to remember after a crash.
        """
        with db.connect() as conn:
            db.record_location(conn, channel, session, window, socket)

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
            self._switch_to_notification(notification)


def main() -> None:
    set_terminal_title("lma")
    app = LemonaidApp()
    app.run()
