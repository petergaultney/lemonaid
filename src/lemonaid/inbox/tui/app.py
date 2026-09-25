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
from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.coordinate import Coordinate
from textual.timer import Timer
from textual.widgets import ContentSwitcher, DataTable, Footer, Header, Input, Static

from ... import brief, claude, codex, openclaw, opencode
from ... import resume as resume_mod
from ...claude.patcher import apply_patch, check_status, find_binary
from ...config import load_config
from ...handlers import check_pane_exists_by_tty, handle_notification
from ...lemon_watchers import (
    ModelInfo,
    detect_terminal_switch_source,
    fish_path,
    get_tmux_socket,
    start_unified_watcher,
    stop_unified_watcher,
)
from ...log import get_logger
from ...tmux import navigation
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
from .. import db, emoji, pins, undo
from . import backend_indicators, brief_cards
from .brief_view import BriefView
from .help_screen import HelpScreen
from .screens import RenameScreen, SnoozeScreen, format_wake_time
from .table import ClickToActTable
from .utils import (
    ATTENTION_COLOR,
    FIELD_STYLES,
    GUTTER_WIDTH,
    HERE_BAR,
    HERE_BAR_STYLE,
    HERE_BLOCK,
    JUMP_DIGITS,
    PIN_MARK,
    UNREAD_MARKER_STYLE,
    backend_cell,
    jump_gutter,
    set_terminal_title,
    styled_cell,
)

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
# Ten cells hold the longest current model label (`Sonnet 4.6`); one more holds
# the pin in a single-line row. The fixed width prevents a row from reflowing
# when its model becomes known, and the labels share their right edge.
_BACKEND_WIDTH = 11
_CARD_MIN_TEXT = 16
_CARD_CHROME_ROWS = 4  # header, status row, and a little slack
_INDENT = " "  # one column, so a card's body clears the marker but little else
# Cards draw their own gutter - a single space, with the marker in the column
# before it - so the table adds none. Every column a narrow pane spends on
# padding is one the message doesn't get.
_CARD_CELL_PADDING = 0
_COLUMN_CELL_PADDING = 1  # DataTable's own default, restored on the way back

_DAY_SECONDS = 86400
_FOCUS_CACHE_SECONDS = 1.0

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
    """The clock time for today and yesterday, a date for anything older.

    Yesterday keeps a time because it is still the recent past - what you want
    from a row from last night is the hour, not the date. It is prefixed `y`
    so the hour is not read as today's: a bare 23:59 at breakfast says nothing
    about which night it was.

    Only past that does the clock stop being the useful part and the calendar
    day take over.
    """
    dt = datetime.fromtimestamp(ts)
    days_ago = (datetime.now().date() - dt.date()).days
    if days_ago == 0:
        return dt.strftime("%H:%M:%S")

    if days_ago == 1:
        return f"y {dt.strftime('%H:%M')}"

    return dt.strftime("%Y-%m-%d")


def _time_cell(ts: float, is_unread: bool, *, history: bool = False) -> Text:
    """The time column, greyed once the row is more than a day old.

    The text says when; the colour says whether it is still worth reacting to.
    The two disagree either side of the yesterday boundary - 00:30 last night
    is recent by breakfast and 23:00 the night before is not, though both read
    as yesterday - so recency is measured in hours rather than taken from the
    same calendar test the text uses.
    """
    field = "time" if time.time() - ts < _DAY_SECONDS else "time_old"
    return styled_cell(_format_timestamp(ts), is_unread, field, history=history)


def _decorated_name(n: db.Notification, emojis: abc.Mapping[str, str]) -> str:
    """The session's name, after its emoji when it has one."""
    decoration = emojis.get(n.channel, "")
    return f"{decoration} {n.name or ''}".rstrip() if decoration else n.name or ""


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
    cells: list[Text],
    width: int,
    context_lines: int = 1,
    message_lines: int = 1,
    gutter_width: int = 0,
    unread_style: str = "dot",
    emoji: str = "",
    card_brief: brief_cards.CardBrief | None = None,
    stale_hours: float = 6.0,
    now: float = 0.0,
) -> list[Text]:
    """Fold a column row into the cells of a card.

    Line 1 is the name, line 2 the short identifiers that place it, then the
    message. Every field the column layout carries survives except the TTY, which
    the two narrower column layouts already drop.

    The name and the context line are truncated, never wrapped: they are fields
    you scan for, so each has to sit in one predictable place down the list. Only
    the message wraps, because it is the one field that reads as prose.

    `gutter_width` is how much of the name cell the column layout's gutter takes,
    for a card to strip before laying out its own.
    """
    # Cells arrive already coloured by field and dimmed by read state, so a card
    # rearranges them rather than restyling: both layouts then agree on what a
    # colour means, and fixing one fixes the other.
    #
    # The dot rides on the name rather than owning a column: it is empty for most
    # rows, and a permanently-indented card wastes width a narrow pane hasn't got.
    # Styled only when there is a dot to style. The marker style is bold, and a
    # bold empty placeholder still emits the attribute - which the name that
    # follows then inherits, since a colour change does not clear it.
    marker = cells[_UNREAD_CELL]
    dot = Text("●", style=UNREAD_MARKER_STYLE) if marker.plain else Text(" ")

    # The first cell is one stable navigation slot: a jump digit until this is
    # the current session, then the green bar. Read titles start in the fourth
    # cell; an unread dot, with breathing room on both sides, nudges the title
    # one cell right as part of the attention signal.
    name = cells[_NAME_CELL]
    is_here = name.plain.startswith(HERE_BLOCK)
    selector = Text(_INDENT)
    if gutter_width:
        selector = (
            Text(HERE_BAR, style=HERE_BAR_STYLE) if is_here else name[: len(_INDENT)]
        )
        name = name[gutter_width:]
    if emoji and name.plain.startswith(f"{emoji} "):
        name = name[len(emoji) + 1 :]

    # The bar goes in the column every line already spends on padding, rather
    # than before it. Prepending would push the whole card right by one the
    # moment it was marked, which reads as the list jumping under the cursor.
    edge = Text(HERE_BAR, style=HERE_BAR_STYLE) if is_here else Text(_INDENT)
    bar_unread = unread_style == "bar" and bool(marker.plain) and card_brief is None
    if bar_unread:
        headline = selector + Text("  ") + name
    else:
        headline = (
            selector + Text(" ") + dot + Text(" ") + name
            if marker.plain
            else selector + Text("  ") + name
        )

    context = Text(" · ", style=FIELD_STYLES["backend"]).join(
        part for part in (cells[_TIME_CELL], cells[_CWD_CELL], cells[_BRANCH_CELL]) if part.plain
    )

    message = cells[_MSG_CELL]
    if card_brief and card_brief.status == "waiting" and not marker.plain:
        headline.stylize("dim")
        context.stylize("dim")
        message = message.copy()
        message.stylize("dim")

    # The bar is a column of the card's width, not an extra one beside it, so
    # every line's budget shrinks by it. Without that the context line overflows
    # the pane and wraps - and a wrapped line starts at column 0, breaking the
    # edge the bar is there to draw.
    body = width - len(_INDENT)
    backend = cells[_BACKEND_CELL].copy()
    pin = Text("")
    if backend.plain.endswith(PIN_MARK):
        pin = backend[-len(PIN_MARK) :]
        backend = backend[: -len(PIN_MARK)]
    backend.justify = None
    pin.justify = None
    if card_brief and card_brief.status == "waiting" and not marker.plain:
        backend.stylize("dim")
    markers = Text(emoji)
    if pin.plain:
        markers += Text(" ") if emoji else Text("")
        markers += pin

    if bar_unread:
        backend_style = backend.get_style_at_offset(_CONSOLE, 0)
        badge = Text(f" {backend.plain} ")
        badge.stylize(
            Style(
                color="#000000",
                bgcolor=backend_style.color or ATTENTION_COLOR,
            )
        )
        headline = _right_aligned(headline, badge, width)
        # Keep the selected-session bar green; everything after it is the
        # yellow title bar until the provider-coloured model badge begins.
        headline.stylize(
            Style(color="#000000", bgcolor=ATTENTION_COLOR),
            1 if is_here else 0,
            len(headline) - len(badge),
        )
    else:
        headline = _right_aligned(headline, backend, width)

    if card_brief and card_brief.status in {"blocked", "done"}:
        background = ATTENTION_COLOR if card_brief.status == "blocked" else "#285995"
        foreground = "#000000" if card_brief.status == "blocked" else "#ffffff"
        headline.stylize(Style(color=foreground, bgcolor=background), 1 if is_here else 0)
        if marker.plain:
            headline.stylize(
                "bold #000000" if card_brief.status == "blocked" else UNREAD_MARKER_STYLE,
                2,
                3,
            )

    # What the lemon needs from you sits right under who it is, in the attention
    # colour whatever the state: a waiting card dims everything else, not this.
    brief_lines = (
        [
            *([Text(card_brief.needs_line, style=UNREAD_MARKER_STYLE)] if card_brief.needs_line else []),
            Text(card_brief.age(now, stale_hours), style="dim"),
            *([Text(card_brief.waiting_line, style="dim")] if card_brief.waiting_line else []),
        ]
        if card_brief
        else []
    )

    lines = [
        headline,
        _right_aligned(edge + context, markers, width),
        *(edge + _truncated(line, body) for line in brief_lines),
        # The message is the only field with the vertical space spent on it: it
        # is unbounded, and the one an ellipsis costs you most.
        *(edge + line for line in _wrapped(message, body, message_lines)),
        # Separates this card from the next, and carries the bar when there is
        # one: the blank line is part of the card's own cell, so it takes the row
        # cursor's background with the rest, and an edge stopping short of it
        # reads as one that ran out rather than one that ends the card. Left
        # genuinely empty otherwise, so an unmarked card ends where it did.
        edge if is_here else Text(""),
    ]
    # Model and pin live in the first two lines rather than a second table
    # column. That gives the message every column below them instead of making
    # a short label reserve a blank strip down the entire card.
    return [Text("\n").join(lines)]


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


def _right_aligned(left: Text, right: Text, width: int) -> Text:
    """Fit a right-hand label beside a line without reserving later lines."""
    left = left.copy()
    right = right.copy()
    _truncated(right, width)
    if not right.plain:
        return _truncated(left, width)

    left_width = max(0, width - right.cell_len - 1)
    _truncated(left, left_width)
    gap = max(0, width - left.cell_len - right.cell_len)
    return left + Text(" " * gap) + right


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
    gutter_width: int = 0,
    unread_style: str = "dot",
    emojis_by_row: abc.Mapping[str, str] | None = None,
    briefs_by_row: abc.Mapping[str, brief_cards.CardBrief | None] | None = None,
    stale_hours: float = 6.0,
    now: float = 0.0,
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
        (
            key,
            _as_card(
                cells,
                card_width,
                *shape,
                gutter_width,
                unread_style,
                (emojis_by_row or {}).get(key, ""),
                (briefs_by_row or {}).get(key),
                stale_hours,
                now,
            )
            if cards
            else cells,
        )
        for key, cells in rows
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
    """Give the card's single cell the entire paintable width."""
    columns = list(table.columns.values())
    if not columns or total_width <= 0:
        return

    for column in columns:
        column.auto_width = False
    columns[_CARD_BODY_COLUMN].width = max(_CARD_MIN_TEXT, total_width)


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

    CSS = f"$attention: {ATTENTION_COLOR};\n" + """
    #content_switcher, #inbox_content {
        height: 1fr;
    }

    #main_table {
        height: 1fr;
    }

    /* HeaderIcon is only a second route to the command palette, which already
       has a keybinding in the footer. Hide its matching empty clock spacer too,
       so the title remains centred across the full pane. */
    HeaderIcon, HeaderClockSpace {
        display: none;
    }

    /* The bar above the list is the table's header row, which carries no labels
       in card layout - so it is free to carry the state of the list instead:
       whether anything in it wants you, and which list you are looking at.
       The attention colour is shared with the unread marker, so the bar and
       dot remain the same lemon yellow by construction. */
    DataTable > .datatable--header {
        background: ansi_bright_blue;
    }

    DataTable {
        scrollbar-size-vertical: 1;
    }

    App.-unread DataTable > .datatable--header {
        background: $attention;
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
        self._name_scan_mtimes: dict[str, float] = {}
        self._focused: frozenset[str] = frozenset()
        self._focused_asked_at = 0.0
        self._exec_on_exit: tuple[str, list[str]] | None = None
        self._keys_shown = True
        self._hint_timer: Timer | None = None
        self._card_layout = False
        self._models_by_channel: dict[str, ModelInfo] = {}
        self._brief_cache = brief_cards.BriefCache()
        self._brief_target: brief.target.Target | None = None
        self._brief_saved_focus = "main_table"
        self._brief_saved_subtitle = "attention inbox"
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

        for b in _build_bindings(kb.brief, "brief", "Brief"):
            self.bind(b.key, b.action, description=b.description, show=b.show)

        for b in _build_bindings(kb.pin, "pin", "Pin"):
            self.bind(b.key, b.action, description=b.description, show=b.show)

        # Named keys rather than a string of alternatives: these carry a modifier.
        if kb.move_pin_up:
            self.bind(kb.move_pin_up, "move_pin_up", description="Move Up", show=False)
        if kb.move_pin_down:
            self.bind(kb.move_pin_down, "move_pin_down", description="Move Down", show=False)

        for b in _build_bindings(kb.tmux_resume, "tmux_resume", "Tmux"):
            self.bind(b.key, b.action, description=b.description, show=False)

        self.bind("slash", "filter_history", description="Filter", show=False)

        # Patch Claude (always hidden, always 'P')
        self.bind("P", "patch_claude", description="Patch Claude", show=False)

        # Key hints share the bottom row with the status text, so they're a toggle
        # rather than a permanent fixture. Hidden from the footer it controls.
        self.bind("question_mark", "help", description="Keys", show=False)

        for b in _build_bindings(kb.flip_position, "flip_position", "Flip", show=False):
            self.bind(b.key, b.action, description=b.description, show=b.show)

        for b in _build_bindings(kb.save_size, "save_scratch_size", "Save Size", show=False):
            self.bind(b.key, b.action, description=b.description, show=b.show)

        if self.config.tui.keybindings.jump_by_number:
            for digit in JUMP_DIGITS:
                self.bind(digit, f"jump_to_number('{digit}')", description="Jump", show=False)

        # Cross-table arrow navigation (always active)
        self.bind("up", "cursor_up", description="Up", show=False)
        self.bind("down", "cursor_down", description="Down", show=False)

        # Additional up/down keys (vim-style, if configured)
        if len(kb.up_down) == 2:
            up, down = kb.up_down
            self.bind(up, "cursor_up", description="Up", show=False)
            self.bind(down, "cursor_down", description="Down", show=False)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if self._brief_target is not None:
            return action in {"quit", "brief", "refresh", "help", "flip_position"}
        return True

    def compose(self) -> ComposeResult:
        yield Header()
        with ContentSwitcher(initial="inbox_content", id="content_switcher"):
            with Container(id="inbox_content"):
                yield ClickToActTable(id="main_table")
                yield Static("", id="other_sources_label")
                yield DataTable(id="other_sources_table", show_header=False)
                yield Input(placeholder="Filter by name, cwd, branch...", id="history_filter")
                # History resumes a session, replacing the terminal you are sitting in.
                # That wants picking a row and committing to it to stay separate.
                yield DataTable(id="history_table")
                yield DataTable(id="snoozed_table")
                yield Static("", id="status")
            yield BriefView(brief.pr.configured(self.config.brief.pr_state), id="brief_view")
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
            record_model=self._record_channel_model,
            models=self._recorded_models,
            sockets=self._recorded_sockets,
        )
        self.call_later(self._check_claude_patch)
        self.call_later(self._stretch_all_tables)
        # Kick Footer to pick up dynamically-bound keys
        self.refresh_bindings()
        self._show_keys(True)
        self._hint_timer = self.set_timer(_KEY_HINT_SECONDS, lambda: self._show_keys(False))

    def on_unmount(self) -> None:
        """Stop the DB-mutating watcher before this app's resources disappear."""
        stop_unified_watcher()

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

    def _card_shape(self, extra_lines: int = 0) -> tuple[int, int]:
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
        # _CARD_HEIGHT includes the first message line, but not the blank separator.
        # Account for it on brief cards without changing the existing card sizing.
        card_height = _CARD_HEIGHT + extra_lines + int(extra_lines > 0)
        spare = rows // sessions - card_height
        if spare <= 0:
            return 1, 1

        # A card only ever renders the lines its message actually fills, so this
        # is a ceiling rather than padding - a short message stays short. The
        # share cap keeps one long message from owning a mostly-empty pane.
        ceiling = min(_CARD_MAX_HEIGHT, max(_CARD_HEIGHT, int(rows * _CARD_MAX_SHARE)))

        # All of it goes to the message: context is one truncated line by
        # design, so lines handed to it would be discarded.
        return 1, 1 + min(spare, max(0, ceiling - card_height))

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
            if table.id != "other_sources_table":
                table.show_header = self.config.tui.card_unread_style != "bar"
            table.add_column("", width=20)  # The card body, stretched on resize
            return

        table.cell_padding = _COLUMN_CELL_PADDING
        if table.id != "other_sources_table":
            table.show_header = True
        # Time holds "HH:MM:SS", "y HH:MM" for yesterday, or "YYYY-MM-DD".
        table.add_column("Time", width=10)
        # Everything in history is archived, so the marker would always be
        # empty. Dropping it shifts every row left, which is a structural cue
        # that this is a different list rather than a differently-tinted one.
        if marker_column:
            table.add_column("", width=1)  # Unread indicator
        table.add_column("", width=_BACKEND_WIDTH)  # Model, right-aligned
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

    def _focused_ttys(self) -> frozenset[str]:
        """Which pane the user is looking at, asked of tmux at most once a second.

        A refresh runs on the poll interval and again on every action that
        changes the list - far more often than a pane can be switched by hand,
        and the answer costs a subprocess each time.
        """
        now = time.time()
        if now - self._focused_asked_at >= _FOCUS_CACHE_SECONDS:
            self._focused = frozenset(navigation.focused_ttys(get_tmux_socket()))
            self._focused_asked_at = now

        return self._focused

    def _backend_value(
        self, n: db.Notification, is_unread: bool, *, history: bool = False
    ) -> Text:
        remembered = self._models_by_channel.get(n.channel)
        model = n.metadata.get("model")
        if isinstance(model, str) and model:
            provider = n.metadata.get("model_provider")
            if not isinstance(provider, str):
                provider = remembered.provider if remembered else ""
            remembered = ModelInfo(provider, model)
            self._models_by_channel[n.channel] = remembered

        return backend_indicators.backend_text(
            n.channel,
            self.config.tui.backend_labels,
            is_unread,
            model=remembered.model if remembered else "",
            model_provider=remembered.provider if remembered else "",
            history=history,
        )

    def _active_row(
        self,
        n: db.Notification,
        row_index: int,
        focused: frozenset[str],
        pinned: frozenset[str],
        emojis: abc.Mapping[str, str],
    ) -> tuple[str, list[Text]]:
        """Build the main-table row for a session, keyed by notification id.

        `row_index` is the session's position in the list, which is what its jump
        digit names - so a row's number changes when the list reorders.

        `focused` is the set of ttys a user is looking at, and `pinned` the set of
        pinned channels. Both are passed in rather than looked up here, since
        every row in one refresh shares the answer.
        """
        is_unread = n.is_unread
        is_here = n.metadata.get("tty", "") in focused
        return str(n.id), [
            _time_cell(n.created_at, is_unread),
            Text("●", style=UNREAD_MARKER_STYLE) if is_unread else Text(""),
            backend_cell(
                self._backend_value(n, is_unread),
                n.channel in pinned,
            ),
            jump_gutter(row_index, is_here)
            + styled_cell(_decorated_name(n, emojis), is_unread, "name"),
            styled_cell(n.metadata.get("git_branch", ""), is_unread, "branch"),
            styled_cell(fish_path(n.metadata.get("cwd", "")), is_unread, "cwd"),
            styled_cell(n.message, is_unread, "message"),
            styled_cell(n.metadata.get("tty", "").replace("/dev/", ""), is_unread, "tty"),
        ]

    def _other_row(
        self, n: db.Notification, emojis: abc.Mapping[str, str]
    ) -> tuple[str, list[Text]]:
        """Build the non-switchable-table row for a session. Always dimmed."""
        return str(n.id), [
            _time_cell(n.created_at, False),
            Text("○", style="dim") if n.is_unread else Text(""),
            self._backend_value(n, False),
            styled_cell(_decorated_name(n, emojis), False, "name"),
            styled_cell(n.metadata.get("git_branch", ""), False, "branch"),
            styled_cell(fish_path(n.metadata.get("cwd", "")), False, "cwd"),
            styled_cell(n.message, False, "message"),
            styled_cell(n.metadata.get("tty", "").replace("/dev/", ""), False, "tty"),
        ]

    def _refresh_notifications(self, *, stay_on_unread: bool = False) -> None:
        if self._brief_target is not None:
            self._wake_expired_snoozes()
            self.query_one(BriefView).update_brief(self._brief_target)
            return

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

            pinned = frozenset(pins.pinned_positions(conn))
            emojis = emoji.by_channel(conn)
            attached = (
                brief.attached.for_rows(conn, current_notifications)
                if self.config.tui.brief_status and self._card_width()
                else {}
            )

        card_briefs = {
            str(n.id): self._brief_cache.get(attached[n.channel])
            for n in current_notifications
            if n.channel in attached
        }
        extra_lines = max(
            (card.extra_lines for card in card_briefs.values() if card),
            default=0,
        )

        unread_count = sum(1 for n in current_notifications if n.is_unread)
        self.set_class(bool(unread_count), "-unread")
        focused = self._focused_ttys()
        rebuilt = _sync_rows(
            main_table,
            [
                self._active_row(n, i, focused, pinned, emojis)
                for i, n in enumerate(current_notifications)
            ],
            self._card_width(),
            self._card_shape(extra_lines),
            GUTTER_WIDTH,
            self.config.tui.card_unread_style,
            {str(n.id): emojis.get(n.channel, "") for n in current_notifications},
            card_briefs,
            self.config.tui.brief_stale_hours,
            time.time(),
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
                [self._other_row(n, emojis) for n in other_notifications],
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
        if self._brief_target is not None:
            pane = os.environ.get("TMUX_PANE")
            if pane:
                brief.sidebar.clear(pane)
            self._set_brief_view(None)
            return

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

    def action_help(self) -> None:
        """Show the key reference.

        The footer is one row and truncates in a sidebar, so the full list lives
        in a modal that gets the whole pane. The startup peek at the footer is
        left alone - it is a reminder that keys exist, not the reference.
        """
        if self._hint_timer is not None:
            self._hint_timer.stop()
            self._hint_timer = None

        self._show_keys(False)
        self.push_screen(HelpScreen(self.config.tui.keybindings, wide=not self._card_layout))

    def action_toggle_keys(self) -> None:
        # An explicit toggle outranks the startup timer, which would otherwise
        # hide the hints part-way through the user reading them.
        if self._hint_timer is not None:
            self._hint_timer.stop()
            self._hint_timer = None

        self._show_keys(not self._keys_shown)

    def _show_keys(self, shown: bool) -> None:
        self._keys_shown = shown
        if self._brief_target is not None:
            return

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
                if n.channel.startswith("claude:")
                and n.metadata.get("name_source") not in ("claude_rename", "claude_index")
                and n.metadata.get("session_id")
                and n.metadata.get("cwd")
            ]

        upgraded = False
        for notification_id, session_id, cwd in candidates:
            transcript = claude.notify.find_transcript(session_id, cwd)
            if not transcript:
                continue

            # resolve_session_name reads the full transcript, which can be
            # megabytes. With 60+ sessions this dominates CPU when nothing
            # has changed.
            cache_key = str(transcript)
            try:
                mtime = transcript.stat().st_mtime
            except OSError:
                continue

            if mtime == self._name_scan_mtimes.get(cache_key):
                continue

            self._name_scan_mtimes[cache_key] = mtime
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
                self._backend_value(n, False, history=True),
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
                        _time_cell(n.created_at, False, history=True),
                        Text("○", style="dim") if n.snooze_prev_status == "unread" else Text(""),
                        self._backend_value(n, False),
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

    def _switch_to_notification(self, notification) -> bool:
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
            return False

        # We already know where a successful in-app switch went. Reflect that
        # immediately instead of waiting for the next tmux poll; the periodic
        # lookup remains authoritative for switches made outside lemonaid.
        tty = notification.metadata.get("tty")
        if isinstance(tty, str) and tty:
            self._focused = frozenset({tty})
            self._focused_asked_at = time.time()
            self._refresh_notifications()

        # In scratch mode the pane hides after navigation, unless follow
        # mode is on - there the hook re-shows it in the target window.
        if self._scratch_mode and not is_follow_enabled():
            self._hide_scratch_pane()

        return True

    def _still_running(self, notification) -> bool:
        """Whether this session's pane is still there to switch to.

        Archiving is a guess made from outside the session - a watcher that
        could not find the pane - and it is wrong often enough that history
        holds sessions which never stopped running. Asked of the server the
        session was recorded on, since a pane on another one is absent from
        this one's listing for reasons that have nothing to do with it.

        A tty alone does not identify a session across a reboot, so a pane in a
        tmux session younger than this notification does not count as it.
        """
        tty = notification.metadata.get("tty")
        if not tty or not notification.switch_source:
            return False

        return (
            check_pane_exists_by_tty(
                tty,
                notification.switch_source,
                notification.metadata.get("tmux_socket"),
                notification.created_at,
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
            self.notify(
                f"{notification.name or notification.channel} is running - back in the inbox"
            )
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
        if event.key == "f12" and self._scratch_mode:
            event.prevent_default()
            event.stop()
            self._sync_brief_view()
            return

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
        if self._brief_target is not None:
            self.query_one(BriefView).show(self._brief_target)
            return

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

    def _row_channels(self) -> list[str]:
        """The channel of every row on screen, in the order they are drawn.

        Read from the table rather than re-queried, so a reorder acts on the
        list the user is looking at even when the watcher has changed the
        inbox since the last refresh.
        """
        table = self.query_one(self._active_table_id(), DataTable)
        channels = []
        with db.connect() as conn:
            for row in range(table.row_count):
                key, _ = table.coordinate_to_cell_key(Coordinate(row, 0))
                notification = db.get(conn, int(key.value)) if key and key.value else None
                if notification:
                    channels.append(notification.channel)

        return channels

    def _selected_channel(self) -> str | None:
        """The channel of the row under the cursor, in the main list only."""
        if self._history_mode or self._snoozed_mode:
            return None

        row_key = self._get_current_row_key()
        if not row_key:
            return None

        with db.connect() as conn:
            notification = db.get(conn, int(row_key))

        return notification.channel if notification else None

    def action_pin(self) -> None:
        """Hold the selected session at its place in the list, or release it."""
        channel = self._selected_channel()
        if not channel:
            return

        with db.connect() as conn:
            now_pinned = pins.toggle(conn, channel)

        _log.info("pin: %s -> %s", channel, now_pinned)
        self._refresh_notifications()
        self.notify(f"{'Pinned' if now_pinned else 'Unpinned'} {channel}")

    def _move_pin(self, offset: int) -> None:
        """Trade places with the nearest pinned session `offset` away on screen.

        The neighbour is taken from the rendered list rather than from the pins
        table, so a pinned session that is currently snoozed keeps its position
        and returns between the same two rows it sat between before.
        """
        channel = self._selected_channel()
        if not channel:
            return

        with db.connect() as conn:
            if not pins.is_pinned(conn, channel):
                return

            pinned_now = pins.pinned_positions(conn)
            on_screen = [c for c in self._row_channels() if c in pinned_now]
            if channel not in on_screen:
                return

            neighbour = on_screen.index(channel) + offset
            if not 0 <= neighbour < len(on_screen):
                return

            pins.swap(conn, channel, on_screen[neighbour])

        self._refresh_notifications()
        self._select_channel(channel)

    def action_move_pin_up(self) -> None:
        self._move_pin(-1)

    def action_move_pin_down(self) -> None:
        self._move_pin(1)

    def _select_channel(self, channel: str) -> None:
        """Put the cursor back on a channel after the list around it moved."""
        table = self.query_one(self._active_table_id(), DataTable)
        for index, c in enumerate(self._row_channels()):
            if c == channel and index < table.row_count:
                table.move_cursor(row=index)
                return

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

    def _set_brief_view(self, found: brief.target.Target | None) -> None:
        view = self.query_one(BriefView)
        switcher = self.query_one(ContentSwitcher)
        if found is None:
            if self._brief_target is None:
                return

            self._brief_target = None
            switcher.current = "inbox_content"
            self.sub_title = self._brief_saved_subtitle
            self.query_one(f"#{self._brief_saved_focus}").focus()
            self.refresh_bindings()
            self._show_keys(self._keys_shown)
            self._refresh_notifications()
            return

        if self._brief_target is None:
            self._brief_saved_focus = (
                self.focused.id if self.focused and self.focused.id else "main_table"
            )
            self._brief_saved_subtitle = self.sub_title

        self._brief_target = found
        switcher.current = "brief_view"
        self.sub_title = "brief"
        view.show(found)
        view.focus()
        self.refresh_bindings()

    def _sync_brief_view(self) -> None:
        pane = os.environ.get("TMUX_PANE")
        shown = brief.sidebar.read(pane) if pane else None
        if shown and brief.sidebar.window_id(pane) == shown[1]:
            self._set_brief_view(shown[0])
        else:
            self._set_brief_view(None)

    def action_brief(self) -> None:
        """Show a brief in the sidebar, or use a popup if it is unavailable."""
        if self._brief_target is not None:
            self.action_quit()
            return

        row_key = self._get_current_row_key()
        if not row_key:
            return

        with db.connect() as conn:
            notification = db.get(conn, int(row_key))
            attached = brief.attached.for_rows(conn, [notification] if notification else [])
            emojis = emoji.by_channel(conn)

        target = (
            brief.target.for_notification(
                notification, attached, emojis.get(notification.channel, "")
            )
            if notification
            else None
        )
        if not target or not (target.attached or target.dirs):
            self.notify("No brief or directory recorded for this session", severity="warning")
            return

        if (
            self._scratch_mode
            and is_follow_enabled()
            and not self._history_mode
            and not self._snoozed_mode
            and notification.switch_source == "tmux"
            and current_position(self.config.tmux_session.scratch_position) == "left"
            and self._switch_to_notification(notification)
        ):
            pane = os.environ.get("TMUX_PANE", "")
            if brief.sidebar.toggle(target, brief.sidebar.window_id(pane)):
                self._sync_brief_view()
                return

        brief.popup.open_popup(target)

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

    def action_jump_to_number(self, digit: str) -> None:
        """Switch to the numbered session, as though it had been selected by hand.

        Inbox only. In history Enter resumes rather than switches, and a resume
        is too costly to hang on a single unconfirmed keystroke. The lower table
        is unnumbered for the same reason in reverse: nothing there can be
        switched to at all.
        """
        if self._history_mode:
            return

        table = self.query_one("#main_table", DataTable)
        if not table.display:
            return

        row = JUMP_DIGITS.find(digit)
        if row < 0 or row >= table.row_count:
            return

        table.move_cursor(row=row)
        self.action_select()

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

    def _recorded_models(self) -> dict[str, ModelInfo]:
        with db.connect() as conn:
            return {
                n.channel: ModelInfo(provider, model)
                for n in db.get_active(conn, switch_source=None)
                if isinstance((provider := n.metadata.get("model_provider")), str)
                and isinstance((model := n.metadata.get("model")), str)
                and model
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

    def _record_channel_model(self, channel: str, provider: str, model: str) -> None:
        with db.connect() as conn:
            db.record_model(conn, channel, provider, model)

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
