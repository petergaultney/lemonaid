"""Main Lemonaid TUI application."""

import contextlib
import dataclasses
import os
import shlex
import sqlite3
import subprocess
import threading
import time
from collections import abc
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

from rich.console import Console
from rich.markup import escape
from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.color import Color, ColorParseError
from textual.containers import Container
from textual.coordinate import Coordinate
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import ContentSwitcher, DataTable, Footer, Header, Input, Static
from textual.widgets.data_table import RowKey

from ... import brief, claude, codex, groups, handlers, openclaw, opencode, palette
from ... import resume as resume_mod
from ...brief import attached as brief_attached
from ...claude import notify, patch_status
from ...claude.patcher import apply_patch, find_binary
from ...config import KeybindingsConfig, PlaceRoot, TuiConfig, load_config
from ...handlers import handle_notification
from ...lemon_watchers import (
    ModelInfo,
    detect_terminal_switch_source,
    fish_path,
    get_tmux_socket,
    start_unified_watcher,
    stop_unified_watcher,
)
from ...log import get_logger
from ...skills import refresh
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
from .. import (
    context_use,
    db,
    emoji,
    order,
    pins,
    presence,
    resume_archived,
    search,
    sections,
    teardown_evidence,
    unarchive,
    undo,
    view,
)
from ..arrange import answer, child
from . import (
    backend_indicators,
    brief_cards,
    brief_rows,
    card_context,
    context_reading,
    focus,
    group_headers,
    pr_numbers,
    project_names,
    utils,
)
from .brief_view import BriefView
from .error_screen import ErrorScreen
from .help_screen import HelpScreen
from .notes import NotesPanel
from .resume_error import ResumeErrorScreen
from .screens import RenameScreen, SnoozeScreen, format_wake_time
from .table import ClickToActTable
from .utils import (
    ATTENTION_COLOR,
    GUTTER_WIDTH,
    HERE_BAR,
    HERE_BAR_STYLE,
    HERE_BLOCK,
    JUMP_DIGITS,
    PIN_MARK,
    backend_cell,
    jump_gutter,
    same_cell,
    set_terminal_title,
    styled_cell,
    update_static,
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
_CONTEXT_WIDTH = 7  # ` 999% ` and the model's padding, when readings are configured
_CARD_MIN_TEXT = 16
_CARD_CHROME_ROWS = 3  # title, status row, and a little slack
_INDENT = " "  # one column, so a card's body clears the marker but little else
GROUP_RAIL = HERE_BAR  # one kind of edge, in the group's colour
# Cards draw their own gutter - a single space, with the marker in the column
# before it - so the table adds none. Every column a narrow pane spends on
# padding is one the message doesn't get.
_CARD_CELL_PADDING = 0
_COLUMN_CELL_PADDING = 1  # DataTable's own default, restored on the way back

_DAY_SECONDS = 86400
_FOCUS_CACHE_SECONDS = 1.0
_INPUT_FOCUS_CACHE_SECONDS = 0.5

_TIME_CELL = 0
_UNREAD_CELL = 1
_BACKEND_CELL = 2
_NAME_CELL = 3
_BRANCH_CELL = 4
_CWD_CELL = 5
_MSG_CELL = 6


_CONSOLE = Console()  # for measuring wraps only; nothing is printed through it

_log = get_logger("tui")


def _tmux_pane_receives_keys(pane: str) -> bool | None:
    """Whether this pane is selected in a visible, attached tmux window."""
    try:
        result = subprocess.run(
            [
                "tmux",
                "display-message",
                "-p",
                "-t",
                pane,
                "#{pane_active} #{window_active} #{session_attached}",
            ],
            capture_output=True,
            text=True,
            timeout=0.3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    parts = result.stdout.split()
    if len(parts) != 3 or any(not part.isdecimal() for part in parts):
        return None
    return parts[0] == "1" and parts[1] == "1" and int(parts[2]) > 0


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


def _time_cell(
    ts: float, is_unread: bool, *, history: bool = False, neutral_timing: bool = False
) -> Text:
    """The time column, greyed once the row is more than a day old.

    The text says when; the colour says whether it is still worth reacting to.
    The two disagree either side of the yesterday boundary - 00:30 last night
    is recent by breakfast and 23:00 the night before is not, though both read
    as yesterday - so recency is measured in hours rather than taken from the
    same calendar test the text uses.
    """
    field = "time" if time.time() - ts < _DAY_SECONDS else "time_old"
    return styled_cell(
        _format_timestamp(ts), is_unread, field, history=history, neutral_timing=neutral_timing
    )


def _decorated_name(n: db.Notification, emojis: abc.Mapping[str, str]) -> str:
    """The session's name, after its emoji when it has one."""
    decoration = emojis.get(n.channel, "")
    return f"{decoration} {n.name or ''}".rstrip() if decoration else n.name or ""


def _name_cell(
    n: db.Notification,
    emojis: abc.Mapping[str, str],
    wordybin: str,
    is_unread: bool,
    pr_number: pr_numbers.PR | None = None,
) -> Text:
    """The decorated name with its PR number and optional grey brief name."""
    name = styled_cell(_decorated_name(n, emojis), is_unread, "name")
    if pr_number:
        offset = len(emojis[n.channel]) + 1 if emojis.get(n.channel) else 0
        number = styled_cell(f"#{pr_number.number} ", is_unread, "name")
        number.stylize("bold")
        if pr_number.url:
            number.stylize(Style(link=pr_number.url), 0, len(number) - 1)
        name = name[:offset] + number + name[offset:]
    if not wordybin:
        return name

    suffix = styled_cell(f" · {wordybin}", False, "backend")
    suffix.stylize(Style(meta={"lemonaid_wordybin": True}))
    return name + suffix


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


def _overlay(target: Text, piece: Text, offset: int) -> None:
    """Apply `piece`'s styles to the same text in `target`, starting at `offset`."""
    for span in piece.spans:
        target.stylize(span.style, offset + span.start, offset + span.end)


def _as_card(
    cells: list[Text],
    width: int,
    context_lines: int = 1,
    message_lines: int = 1,
    gutter_width: int = 0,
    unread_style: str = "dot",
    emoji: str = "",
    card_brief: brief_cards.CardBrief | None = None,
    now: float = 0.0,
    context_parts: abc.Sequence[card_context.Part] | None = None,
    age_inline: bool = False,
    neutral_timing: bool = False,
    rail: str = "",
) -> list[Text]:
    """Fold a column row into the cells of a card.

    Line 1 is the name, line 2 the short identifiers that place it, then the
    message. Every field the column layout carries survives except the TTY, which
    the two narrower column layouts already drop.

    The name and the context line are truncated, never wrapped: they are fields
    you scan for, so each has to sit in one predictable place down the list. Only
    the message wraps, because it is the one field that reads as prose.

    `gutter_width` is how much of the name cell the column layout's gutter takes,
    for a card to strip before laying out its own. `context_parts` is the second
    line, the time, cwd and branch cells when not given.
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
    dot = Text("●", style=utils.unread_marker_style()) if marker.plain else Text(" ")

    # The first cell is one stable navigation slot: a jump digit until this is
    # the current session, then the green bar. Read titles start in the fourth
    # cell; an unread dot, with breathing room on both sides, nudges the title
    # one cell right as part of the attention signal.
    name = cells[_NAME_CELL]
    is_here = name.plain.startswith(HERE_BLOCK)
    selector = Text(_INDENT)
    if gutter_width:
        selector = Text(HERE_BAR, style=HERE_BAR_STYLE) if is_here else name[: len(_INDENT)]
        name = name[gutter_width:]
    if emoji and name.plain.startswith(f"{emoji} "):
        name = name[len(emoji) + 1 :]

    # The bar goes in the column every line already spends on padding, rather
    # than before it. Prepending would push the whole card right by one the
    # moment it was marked, which reads as the list jumping under the cursor.
    edge = Text(HERE_BAR, style=HERE_BAR_STYLE) if is_here else Text(_INDENT)

    # A card in an open group gives up its first column to an unbroken rail in
    # the group's colour, so the run of colour shows where the group starts and
    # ends. Ungrouped cards keep the full width.
    if rail:
        width -= 1
    bar_unread = unread_style == "bar" and bool(marker.plain) and card_brief is None
    if bar_unread:
        headline = selector + Text("  ") + name
    else:
        headline = (
            selector + Text(" ") + dot + Text(" ") + name
            if marker.plain
            else selector + Text("  ") + name
        )

    message = cells[_MSG_CELL]
    dimmed = bool(card_brief and card_brief.shown == "idle" and not marker.plain)
    if dimmed:
        headline.stylize("dim")
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
    reading, backend = context_reading.split(backend)
    reading.justify = None
    backend.justify = None
    pin.justify = None
    if card_brief and card_brief.shown == "idle" and not marker.plain:
        backend.stylize("dim")
        reading.stylize("dim")
    markers = Text(emoji)
    if pin.plain:
        markers += Text(" ") if emoji else Text("")
        markers += pin
    context = card_context.fitted(
        context_parts
        if context_parts is not None
        else [
            card_context.Part("time", cells[_TIME_CELL], cells[_TIME_CELL].cell_len),
            card_context.Part("cwd", cells[_CWD_CELL]),
            card_context.Part("branch", cells[_BRANCH_CELL]),
        ],
        body - (markers.cell_len + 1 if markers.plain else 0),
    )
    if dimmed:
        context.stylize("dim")

    if bar_unread:
        backend_style = backend.get_style_at_offset(_CONSOLE, 0)
        badge = Text(f" {backend.plain} ")
        badge.stylize(
            Style(
                color="#000000",
                bgcolor=backend_style.color or ATTENTION_COLOR,
            )
        )
        filled = context_reading.filled(reading)
        headline = _right_aligned(headline, filled + badge, width)
        # Keep the selected-session bar green; everything after it is the
        # yellow title bar until the provider-coloured model badge begins.
        headline.stylize(
            Style(color="#000000", bgcolor=ATTENTION_COLOR),
            1 if is_here else 0,
            len(headline) - len(badge),
        )
        _overlay(headline, filled, len(headline) - len(badge) - len(filled))
        name_offset = len(selector) + 2
        for span in name.spans:
            if isinstance(span.style, Style) and span.style.meta.get("lemonaid_wordybin"):
                headline.stylize(
                    Style(color="bright_black", bgcolor=ATTENTION_COLOR),
                    name_offset + span.start,
                    name_offset + span.end,
                )
    else:
        if card_brief and card_brief.shown in brief_cards.STATUS_STYLES:
            backend = context_reading.padded_model(
                reading, backend, backend.get_style_at_offset(_CONSOLE, 0)
            )
            reading = context_reading.filled(reading)
        headline = _right_aligned(headline, reading + backend, width)

    if card_brief and card_brief.shown in brief_cards.STATUS_STYLES:
        headline.stylize(brief_cards.STATUS_STYLES[card_brief.shown], 1 if is_here else 0)
        if backend.plain:
            # The model keeps its provider colour, as a badge, like the column row's.
            provider = backend.get_style_at_offset(_CONSOLE, 0).color
            headline.stylize(
                Style(color="#000000", bgcolor=provider or ATTENTION_COLOR),
                len(headline) - len(backend),
            )
        _overlay(headline, reading, len(headline) - len(backend) - len(reading))
        if marker.plain:
            headline.stylize(
                brief_cards.DOT_STYLES.get(card_brief.shown, utils.unread_marker_style()),
                2,
                3,
            )

    # What the lemon needs from you sits right under who it is, in the attention
    # colour whatever the state: a waiting card dims everything else, not this.
    brief_lines = (
        [
            *(
                [Text(card_brief.needs_line, style=utils.unread_marker_style())]
                if card_brief.needs_line
                else []
            ),
            *(
                []
                if age_inline
                else [card_brief.age_text(now, style="bright_black" if neutral_timing else "dim")]
            ),
            *(
                [Text(card_brief.running_line, style=brief_cards.running_text())]
                if card_brief.running_line
                else []
            ),
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
    if rail:
        # Added last, as a span, so no status fill, dimming or base style reaches it.
        lines = [Text.assemble((GROUP_RAIL, rail)) + line for line in lines]
    # Model and pin live in the first two lines rather than a second table
    # column. That gives the message every column below them instead of making
    # a short label reserve a blank strip down the entire card.
    return [Text("\n").join(lines)]


def _without_marker(cells: list[Text]) -> list[Text]:
    """Cells minus the unread marker, for a table built without that column."""
    return [cell for index, cell in enumerate(cells) if index != _UNREAD_CELL]


def _key_id(key: RowKey | None) -> int | None:
    """The notification a table row's key names, or None for none or a group header."""
    return sections.notification_id(str(key.value)) if key is not None and key.value else None


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
    now: float = 0.0,
    contexts_by_row: abc.Mapping[str, abc.Sequence[card_context.Part]] | None = None,
    age_inline: bool = False,
    neutral_timing: bool = False,
    headers: abc.Mapping[str, tuple[list[Text], Style | None]] | None = None,
    rails_by_row: abc.Mapping[str, str] | None = None,
) -> bool:
    """Bring a DataTable in line with `rows`, in place where possible.

    `headers` are group header rows by key, already drawn, with their fill.

    `table.clear()` plus re-adding resets the cursor and scroll offset, which
    reads as the list flashing to the top on every refresh tick. When the row set
    and its order are unchanged — the common case, where only a message or status
    moved — cells are updated in place and the cursor never moves.

    Returns True if the table was rebuilt, meaning the caller has to restore the
    cursor itself. Textual has no public row-reorder API, so a genuine order
    change still costs a rebuild.
    """
    cards = card_width > 0
    headers = headers or {}
    shapes = iter(
        [
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
                    now,
                    (contexts_by_row or {}).get(key),
                    age_inline,
                    neutral_timing,
                    (rails_by_row or {}).get(key, ""),
                )
                if cards
                else brief_rows.styled(
                    cells,
                    (briefs_by_row or {}).get(key),
                    _UNREAD_CELL,
                    _BACKEND_CELL,
                    _NAME_CELL,
                    gutter_width,
                ),
            )
            for key, cells in rows
            if key not in headers
        ]
    )
    shaped = [(key, headers[key][0]) if key in headers else next(shapes) for key, _ in rows]

    if isinstance(table, ClickToActTable):
        table.row_backgrounds = {
            key: fill
            for key, _ in rows
            if not cards
            and (
                fill := headers[key][1]
                if key in headers
                else brief_rows.background((briefs_by_row or {}).get(key))
            )
        }

    if [str(key.value) for key in table.rows] == [key for key, _ in shaped]:
        resized = False
        for key, cells in shaped:
            row_index = table.get_row_index(key)
            for column, value in enumerate(cells):
                if not same_cell(table.get_cell_at(Coordinate(row_index, column)), value):
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

    CSS = (
        f"$attention: {ATTENTION_COLOR};\n"
        + """
    #content_switcher, #inbox_content {
        height: 1fr;
    }

    #main_table {
        height: 1fr;
    }

    #main_table.-custom-active-row > .datatable--cursor {
        background: $active-row-color;
    }

    App.-input-inactive #main_table > .datatable--cursor {
        background: $inactive-row-color;
    }

    /* HeaderIcon is only a second route to the command palette, which already
       has a keybinding in the footer. Hide its matching empty clock spacer too,
       so the title remains centred across the full pane. */
    HeaderIcon, HeaderClockSpace {
        display: none;
    }

    /* Unlike tmux's half-border, these mark the pane that will receive keys.
       Keep them separate from the unread bar below the title. */
    App.-input-active Screen {
        border-bottom: heavy $input-focus;
    }

    App.-input-active Header {
        background: $input-focus;
        color: $input-focus-text;
        text-style: bold;
    }

    /* The column layout's header row also carries the state of the list:
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

    #fold_label {
        height: 1;
        color: $text-muted;
        padding: 0 1;
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

    #search_archive_label {
        height: 1;
        background: $accent;
        color: $background;
        padding: 0 1;
        text-style: bold;
    }

    App.-search-archive #main_table {
        height: auto;
    }

    #snoozed_table {
        height: 1fr;
    }
    """
    )

    def __init__(self, scratch_mode: bool = False) -> None:
        self.config = load_config()  # before super(), which reads the CSS variables
        super().__init__()
        self._setup_keybindings()
        self.current_env = detect_terminal_switch_source()
        self._claude_patch_status: str | None = None
        self._claude_binary = find_binary()
        self._scratch_mode = scratch_mode
        self._history_mode = False
        self._search_mode = False
        self._snoozed_mode = False
        self._fold_open = False
        self._unfolded_ids: frozenset[str] = (
            frozenset()
        )  # rows the last refresh kept out of the fold
        self._history_filter = ""
        self._undo_stack = undo.Stack()
        self._last_name_refresh = 0.0
        self._name_scan_mtimes: dict[str, float] = {}
        self._focused: frozenset[str] = frozenset()
        self._focused_asked_at = 0.0
        self._restore_checked: frozenset[str] = frozenset()
        self._input_focus_asked_at = 0.0
        self._exec_on_exit: tuple[str, list[str]] | None = None
        self._keys_shown = True
        self._hint_timer: Timer | None = None
        self._card_layout = False
        self._notes_open = True  # the notes key's choice; shown only in card layout too
        self._models_by_channel: dict[str, ModelInfo] = {}
        self._brief_cache = brief_cards.BriefCache()
        self._presence = presence.Probe(presence.DEAF_AFTER_SECONDS)
        self._pr_numbers = pr_numbers.Cache()
        self._arranger = (
            child.Arranger(child.parse_command(self.config.inbox.arrange))
            if self.config.inbox.arrange
            else None
        )
        self._arrange_error = ""
        self._arrange_logged: set[str] = set()
        self._fold_name = ""  # the arranger's name for the folded group
        self._drawn: list[db.Notification | None] = []  # the main table's rows; None for a header
        self._group_bands: dict[int, str] = {}  # each drawn group's band, by group id
        self._headers: dict[str, sections.Header] = {}  # the drawn headers, by row key
        self._marked_header = ""  # the header drawn with the cursor's marker
        self._followed_focus: frozenset[str] = frozenset()  # the lemons the cursor last went to
        # The row a group was collapsed from, drawn until the cursor leaves it.
        self._kept: frozenset[str] = frozenset()
        self._detached_channels: frozenset[str] = frozenset()
        self._resume_footer_shown = True
        # Each row's project, by (cwd, branch, area): finding one resolves paths,
        # which a refresh tick shouldn't repeat for rows that haven't changed.
        self._projects: dict[tuple[str, str, str], card_context.Part] = {}
        self._project_names = project_names.Cache()
        self._brief_target: brief.target.Target | None = None
        # Browsing briefs redraws at once and switches the main pane behind it;
        # only the newest selection is switched to once a switch finishes.
        self._brief_switch_pending: tuple[db.Notification, brief.target.Target] | None = None
        self._brief_switching = False
        self._brief_local = False
        # Resolving a target asks tmux twice, which is most of an arrow's cost.
        self._brief_targets: dict[int, brief.target.Target] = {}
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
        self._bindings.bind("enter", "select_brief", "Switch", show=False, priority=True)

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

        for b in _build_bindings(kb.resume_detached, "resume_detached", "Resume"):
            self.bind(b.key, b.action, description=b.description, show=b.show)

        for b in _build_bindings(kb.brief, "brief", "Brief"):
            self.bind(b.key, b.action, description=b.description, show=b.show)
        if kb.brief_key:
            # Textual gives Tab to focus-next, so this has to come first; check_action
            # hands the key back where something else wants it. App.bind can't set priority.
            self._bindings.bind(kb.brief_key, "brief", "Brief", show=False, priority=True)
        if kb.group_key:
            # Priority for the same reason as brief_key's.
            self._bindings.bind(kb.group_key, "toggle_group", "Group", show=False, priority=True)

        for b in _build_bindings(kb.pin, "pin", "Pin"):
            self.bind(b.key, b.action, description=b.description, show=b.show)

        if self.config.tui.fold_statuses or self.config.inbox.arrange:
            for b in _build_bindings(kb.fold, "toggle_fold", "Folded"):
                self.bind(b.key, b.action, description=b.description, show=b.show)

        if self.config.tui.notes is not None:
            for b in _build_bindings(kb.notes, "toggle_notes", "Notes"):
                self.bind(b.key, b.action, description=b.description, show=b.show)

        # Named keys rather than a string of alternatives: these carry a modifier.
        if kb.move_pin_up:
            self.bind(kb.move_pin_up, "move_pin_up", description="Move Up", show=False)
        if kb.move_pin_down:
            self.bind(kb.move_pin_down, "move_pin_down", description="Move Down", show=False)

        # Priority, so that a table's own Home/End, a sideways scroll, loses to these.
        # check_action hands them back to an Input, a dialog and the brief view.
        for key in dict.fromkeys((kb.first, "home")):
            if key:
                self._bindings.bind(key, "cursor_first", "Top", show=False, priority=True)
        for key in dict.fromkeys((kb.last, "end")):
            if key:
                self._bindings.bind(key, "cursor_last", "Bottom", show=False, priority=True)

        for b in _build_bindings(kb.tmux_resume, "tmux_resume", "Tmux"):
            self.bind(b.key, b.action, description=b.description, show=False)

        if kb.search:
            self.bind(
                "slash" if kb.search == "/" else kb.search,
                "filter_history",
                description="Search",
                show=False,
            )

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
        self._bindings.bind("up", "cursor_up", "Up", show=False, priority=True)
        self._bindings.bind("down", "cursor_down", "Down", show=False, priority=True)

        # Additional up/down keys (vim-style, if configured)
        if len(kb.up_down) == 2:
            up, down = kb.up_down
            self.bind(up, "cursor_up", description="Up", show=False)
            self.bind(down, "cursor_down", description="Down", show=False)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "select_brief":
            return (
                self._brief_target is not None
                and not isinstance(self.screen, ModalScreen)
                and not isinstance(self.focused, Input)
            )

        if action in {"cursor_up", "cursor_down"} and (
            isinstance(self.focused, Input) or isinstance(self.screen, ModalScreen)
        ):
            return False

        if action in {"copy_resume", "tmux_resume"} and self._search_mode:
            return self.focused is self.query_one("#history_table", DataTable)

        if action == "resume_detached":
            return self._selected_channel() in self._detached_channels or self._brief_local

        if action in ("brief", "toggle_group", "cursor_first", "cursor_last") and (
            isinstance(self.screen, ModalScreen) or isinstance(self.focused, Input)
        ):
            return False

        if self._brief_target is not None:
            # Only what acts on the row whose brief is shown and leaves it in the list.
            return action in {
                "quit",
                "brief",
                "refresh",
                "help",
                "flip_position",
                "cursor_up",
                "cursor_down",
                "select",
                "mark_read",
                "mark_unread",
                "undo",
                "rename",
            }
        return True

    def get_css_variables(self) -> dict[str, str]:
        try:
            focus = Color.parse(self.config.tui.focus_color)
        except ColorParseError:
            _log.warning("tui.focus_color %r is not a colour", self.config.tui.focus_color)
            focus = Color.parse(TuiConfig.focus_color)
        active_row = "#1f4a85"
        if self.config.tui.active_row_color:
            try:
                active_row = Color.parse(self.config.tui.active_row_color).hex
            except ColorParseError:
                _log.warning(
                    "tui.active_row_color %r is not a colour", self.config.tui.active_row_color
                )
        variables = super().get_css_variables()
        cursor = Color.parse(
            active_row
            if self._uses_custom_active_row()
            else variables.get("block-cursor-background", active_row)
        )
        inactive_row = cursor.blend(Color.parse(variables.get("background", "#000000")), 0.7).hex
        if self.config.tui.inactive_row_color:
            try:
                inactive_row = Color.parse(self.config.tui.inactive_row_color).hex
            except ColorParseError:
                _log.warning(
                    "tui.inactive_row_color %r is not a colour", self.config.tui.inactive_row_color
                )
        return {
            **variables,
            "input-focus": focus.hex,
            "input-focus-text": focus.get_contrast_text(1.0).hex,
            "active-row-color": active_row,
            "inactive-row-color": inactive_row,
        }

    def _uses_custom_active_row(self) -> bool:
        configured = self.config.tui.active_row_color
        if configured:
            try:
                Color.parse(configured)
            except ColorParseError:
                return self.current_theme.dark
            return True

        return self.current_theme.dark

    def _update_active_row_background(self) -> None:
        self.query_one("#main_table", ClickToActTable).set_class(
            self._uses_custom_active_row(), "-custom-active-row"
        )

    def compose(self) -> ComposeResult:
        yield Header()
        with ContentSwitcher(initial="inbox_content", id="content_switcher"):
            with Container(id="inbox_content"):
                yield Input(
                    placeholder="Search name, brief, message, cwd, branch...", id="history_filter"
                )
                yield ClickToActTable(id="main_table")
                yield Static("", id="fold_label")
                yield Static("", id="other_sources_label")
                yield DataTable(id="other_sources_table", show_header=False)
                yield Static("", id="search_archive_label")
                # History resumes a session, replacing the terminal you are sitting in.
                # That wants picking a row and committing to it to stay separate.
                yield DataTable(id="history_table")
                yield DataTable(id="snoozed_table")
                if self.config.tui.notes is not None:
                    yield NotesPanel(self.config.tui.notes, id="notes")
                yield Static("", id="status")
            yield BriefView(
                brief.pr.configured(self.config.brief.pr_state),
                self.config.brief.vaults,
                self.config.tui.keybindings,
                self.config.tui.mid_turn_working,
                self.config.places.roots,
                self.config.tui.project_name_colors,
                id="brief_view",
            )
        yield Footer()

    def watch_theme(self, theme: str) -> None:
        # Text colours follow the theme's background; the next refresh redraws them.
        utils.use_light_theme(not self.current_theme.dark)
        if self.is_mounted and self._screen_stack:
            self._update_active_row_background()

    def on_mount(self) -> None:
        self.title = "lemonaid"
        self.sub_title = "attention inbox"
        utils.use_light_theme(not self.current_theme.dark)
        self._update_active_row_background()
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
        self.query_one("#fold_label", Static).display = False
        self.query_one("#other_sources_label", Static).display = False
        self.query_one("#search_archive_label", Static).display = False
        other_table.display = False
        history_table.display = False
        snoozed_table.display = False
        self.query_one("#history_filter", Input).display = False

        self._refresh_notifications()
        self.query_one("#main_table", DataTable).focus()
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
            record_context=self._record_channel_context,
            models=self._recorded_models,
            sockets=self._recorded_sockets,
            session_orders=self._recorded_tmux_session_orders,
            locate_sessions=self._locate_sessions,
            auto_read_patterns=self.config.inbox.auto_read,
            mark_read_after_turn=self._mark_channel_read_after_turn,
            record_turn=self._record_channel_turn,
            protected_channels=self._protected_brief_channels,
            detached_channels=self._set_detached_channels,
        )
        self.call_later(self._check_claude_patch)
        self.call_later(self._refresh_skills)
        self.call_later(self._stretch_all_tables)
        # Kick Footer to pick up dynamically-bound keys
        self.refresh_bindings()
        self._show_keys(True)
        self._hint_timer = self.set_timer(_KEY_HINT_SECONDS, lambda: self._show_keys(False))

    def on_unmount(self) -> None:
        """Stop the DB-mutating watcher before this app's resources disappear."""
        stop_unified_watcher()
        if self._arranger is not None:
            self._arranger.close()

    def _refresh_skills(self) -> None:
        """Bring installed skills up to date after an upgrade, saying so only when it did something."""
        result = refresh.refresh_installed()
        message = refresh.notice(result)
        if message:
            self.notify(message, severity="warning" if result.failed else "information", timeout=15)

    def _check_claude_patch(self) -> None:
        if not self._claude_binary:
            self._claude_patch_status = None
            return

        self.run_worker(self._run_claude_patch_check(self._claude_binary), exclusive=True)

    async def _run_claude_patch_check(self, binary: Path) -> None:
        self._set_patch_status(await patch_status.check_status_in_child(binary))

    def _set_patch_status(self, status: str) -> None:
        """Set patch status and refresh UI (called from main thread)."""
        self._claude_patch_status = status
        self._refresh_notifications()

    def on_app_focus(self) -> None:
        """Refresh when the app regains focus."""
        self._input_focus_asked_at = 0.0
        self._refresh_notifications()

    def _update_input_indicator(self) -> None:
        pane = os.environ.get("TMUX_PANE") if self._scratch_mode else None
        if not pane:
            return
        now = time.monotonic()
        if now - self._input_focus_asked_at < _INPUT_FOCUS_CACHE_SECONDS:
            return
        self._input_focus_asked_at = now
        active = _tmux_pane_receives_keys(pane)
        if active is not None:
            self.set_class(active, "-input-active")
            self.set_class(not active, "-input-inactive")

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

        rows = self.size.height - _CARD_CHROME_ROWS - self._notes_height()
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

    def _where_label(self, table_id: str) -> str:
        """History and the snoozed list keep the cwd: they are records, searched by path."""
        inbox = table_id in {"#main_table", "#other_sources_table"}
        return "Project" if inbox and "project" in self.config.tui.card_fields else "CWD"

    def _column_labels(self, table_id: str) -> dict[int, str]:
        return {
            0: "Time",
            3: "Name",
            _BRANCH_COLUMN: "Branch",
            5: self._where_label(table_id),
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
            table.show_header = False  # The card column has no label
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
        table.add_column(  # Model, right-aligned
            "",
            width=_BACKEND_WIDTH + (_CONTEXT_WIDTH if self.config.tui.context_threshold else 0),
        )
        table.add_column("Name", width=24)
        table.add_column("Branch", width=12)
        table.add_column(self._where_label(f"#{table.id}"), width=16)
        table.add_column("Message", width=30)  # Stretched on resize
        # TTY holds "ttysNNN"; the snoozed view's wake label is "Fri 09:00".
        table.add_column("Wakes" if wake_column else "TTY", width=9 if wake_column else 7)

    def _active_table_id(self) -> str:
        if self._history_mode:
            return "#history_table"
        if self._snoozed_mode:
            return "#snoozed_table"

        return "#main_table"

    @staticmethod
    def _raw_row_key(table: DataTable) -> str | None:
        """The key of the row at a table's cursor: a notification's, or a group header's."""
        if table.row_count == 0:
            return None
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
            return row_key.value if row_key else None
        except Exception:
            return None

    @classmethod
    def _row_key(cls, table: DataTable) -> str | None:
        """The notification ID at a table's cursor, or None on a group header.

        A lemon in two groups is drawn twice, under keys `<id>@<group>`; both
        name the same notification.
        """
        raw = cls._raw_row_key(table)
        found = sections.notification_id(raw) if raw else None
        return str(found) if found is not None else None

    def _get_current_row_key(self) -> str | None:
        """Get the row key (notification ID) at current cursor."""
        return self._row_key(self.query_one(self._active_table_id(), DataTable))

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

    def _backend_value(self, n: db.Notification, is_unread: bool, *, history: bool = False) -> Text:
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
            context_percent=None if history else self._context_percent(n, remembered),
        )

    def _context_percent(self, n: db.Notification, model: ModelInfo | None) -> int | None:
        used = n.metadata.get("context_tokens")
        window = n.metadata.get("context_window")
        if not isinstance(used, int):
            return None

        threshold = context_use.threshold_for(
            self.config.tui.context_threshold,
            n.channel.split(":")[0],
            model.model if model else "",
        )
        if threshold is None:
            return None

        return context_use.percent(used, window if isinstance(window, int) else 0, threshold)

    def _project_names_changed(self) -> None:
        self._projects.clear()
        if self._history_mode:
            self._refresh_history()
        else:
            self._refresh_notifications()

    def _project(self, n: db.Notification, area: str) -> card_context.Part:
        key = (n.metadata.get("cwd", ""), n.metadata.get("git_branch", ""), area)
        if key not in self._projects:
            if self._project_names.request(
                key[0], self.config.places.root_for(key[0]) if key[0] else None
            ):
                self.run_worker(
                    self._project_names.drain(self._project_names_changed), group="project-names"
                )
            self._projects[key] = card_context.project_part(
                self.config.places, *key, project_name=self._project_names.names.get(key[0], "")
            )

        return self._projects[key]

    def _where_cell(self, n: db.Notification, is_unread: bool, area: str) -> Text:
        """The directory column: the project, unless `card_fields` asks for the cwd instead."""
        if "project" not in self.config.tui.card_fields:
            return styled_cell(fish_path(n.metadata.get("cwd", "")), is_unread, "cwd")

        where = self._project(n, area)
        if self.config.tui.project_name_colors and where.field == "project" and where.project_name:
            return utils.styled_project_cell(where.text.plain, where.project_name, is_unread)
        return styled_cell(where.text.plain, is_unread, where.field)

    def _context_parts(
        self,
        n: db.Notification,
        is_unread: bool,
        area: str,
        card_brief: brief_cards.CardBrief | None = None,
        now: float = 0.0,
    ) -> list[card_context.Part]:
        return card_context.parts(
            self.config.tui.card_fields,
            _time_cell(n.created_at, is_unread, neutral_timing=self.config.tui.project_name_colors),
            self._project(n, area),
            n.metadata.get("git_branch", ""),
            n.metadata.get("cwd", ""),
            is_unread,
            card_brief.age_text(now) if card_brief else "",
            self.config.tui.project_name_colors,
            neutral_timing=self.config.tui.project_name_colors,
        )

    def _active_row(
        self,
        n: db.Notification,
        row_index: int,
        focused_channels: frozenset[str],
        pinned: frozenset[str],
        emojis: abc.Mapping[str, str],
        area: str = "",
        wordybin: str = "",
        pr_number: pr_numbers.PR | None = None,
    ) -> tuple[str, list[Text]]:
        """Build the main-table row for a session, keyed by notification id.

        `row_index` is the session's position in the list, which is what its jump
        digit names - so a row's number changes when the list reorders.

        `focused_channels` names the lemons a user is looking at, and `pinned` the set of
        pinned channels. Both are passed in rather than looked up here, since
        every row in one refresh shares the answer.
        """
        is_unread = n.is_unread
        is_here = n.channel in focused_channels
        return str(n.id), [
            _time_cell(n.created_at, is_unread, neutral_timing=self.config.tui.project_name_colors),
            Text("●", style=utils.unread_marker_style()) if is_unread else Text(""),
            backend_cell(
                self._backend_value(n, is_unread),
                n.channel in pinned,
            ),
            jump_gutter(row_index, is_here)
            + _name_cell(n, emojis, wordybin, is_unread, pr_number)
            + self._detached_marker(n),
            styled_cell(n.metadata.get("git_branch", ""), is_unread, "branch"),
            self._where_cell(n, is_unread, area),
            styled_cell(n.message, is_unread, "message"),
            styled_cell(n.metadata.get("tty", "").replace("/dev/", ""), is_unread, "tty"),
        ]

    def _other_row(
        self,
        n: db.Notification,
        emojis: abc.Mapping[str, str],
        area: str = "",
        wordybin: str = "",
        pr_number: pr_numbers.PR | None = None,
    ) -> tuple[str, list[Text]]:
        """Build the non-switchable-table row for a session. Always dimmed."""
        return str(n.id), [
            _time_cell(n.created_at, False, neutral_timing=self.config.tui.project_name_colors),
            Text("○", style="dim") if n.is_unread else Text(""),
            self._backend_value(n, False),
            _name_cell(n, emojis, wordybin, False, pr_number),
            styled_cell(n.metadata.get("git_branch", ""), False, "branch"),
            self._where_cell(n, False, area),
            styled_cell(n.message, False, "message"),
            styled_cell(n.metadata.get("tty", "").replace("/dev/", ""), False, "tty"),
        ]

    def _ordered_active(self, conn: sqlite3.Connection, switch_source: str | None) -> "view.Active":
        return view.ordered_active(
            conn,
            switch_source,
            self._brief_cache,
            self._presence,
            self.config.tui.mid_turn_working,
            time.time(),
        )

    def _arranged(
        self,
        active: "view.Active",
        shown: list[db.Notification],
        folded: list[db.Notification],
        pinned: frozenset[str],
        emojis: abc.Mapping[str, str],
    ) -> tuple[list[db.Notification], list[db.Notification], str]:
        """*shown* and *folded* as the arranger has them, and its fold label.

        While it has no usable answer they come back as they are, and
        `_arrange_error` says why for the status line.
        """
        if self._arranger is None:
            return shown, folded, ""

        now = time.time()
        layout = "sidebar" if self._card_layout else "table"
        reply = self._arranger.answer(
            view.snapshot(active, shown, folded, pinned, emojis, layout, self.size.width, now), now
        )
        self._arrange_error = self._arranger.error
        if reply is None:
            return shown, folded, ""

        try:
            arranged = answer.apply(reply, shown, folded, self.config.inbox.arrange_may_fold_unread)
        except answer.AnswerError as e:
            if str(e) not in self._arrange_logged:
                _log.warning("arrange: %s", e)
                self._arrange_logged.add(str(e))
            self._arrange_error = str(e)
            return shown, folded, ""

        if len(self._arrange_logged) > 1000:
            self._arrange_logged.clear()  # problems name row ids, which keep changing
        for problem in set(arranged.problems) - self._arrange_logged:
            _log.info("arrange: %s", problem)
        self._arrange_logged.update(arranged.problems)
        return arranged.shown, arranged.folded, arranged.fold_label

    def _refresh_pr_numbers(self) -> None:
        for root in self._pr_numbers.due(self.config.places.roots, time.monotonic()):

            def load(root: PlaceRoot = root) -> None:
                numbers = pr_numbers.refresh(root)
                self.call_from_thread(self._pr_numbers.store, root, numbers, time.monotonic())
                self.call_from_thread(self._refresh_notifications)

            self.run_worker(load, thread=True, group="pr-numbers")

    def _refresh_notifications(self, *, stay_on_unread: bool = False) -> None:
        if not self.is_running:
            return  # a timer tick during shutdown, while the screen's widgets are being removed

        self._update_input_indicator()
        self._refresh_notes()
        if self._brief_target is not None:
            self._wake_expired_snoozes()
            self.query_one(BriefView).update_brief(self._brief_target, self._brief_unread())
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
        self._refresh_pr_numbers()

        main_table = self.query_one("#main_table", DataTable)
        fold_label = self.query_one("#fold_label", Static)
        other_table = self.query_one("#other_sources_table", DataTable)
        other_label = self.query_one("#other_sources_label", Static)

        # Remember current selection (both key and index) for both tables
        current_key = self._get_current_row_key()
        current_row = self._raw_row_key(main_table)  # a header's, or a lemon's under its group
        self._kept = self._kept if current_row in self._kept else frozenset()
        current_index = self._get_current_row_index()
        other_index = other_table.cursor_coordinate.row if other_table.row_count > 0 else 0
        focused_on_other = self.focused is other_table
        other_key = self._row_key(other_table) if focused_on_other else None

        focused = self._focused_ttys()
        with db.connect() as conn:
            if focused != self._restore_checked:
                self._restore_checked = focused  # asked once per change of focus: it can cost a ps
                unarchive.restore_focused(conn, focused)
            env_filter = self.current_env if self.current_env != "unknown" else None
            pinned = frozenset(pins.pinned_positions(conn))
            # Main table: only sessions switchable from the current environment
            active = self._ordered_active(conn, env_filter)
            focused_channels = focus.channels(active.rows, focused)
            matching_ids = (
                {result.notification.id for result in search.find(conn, self._history_filter)}
                if self._search_mode
                else None
            )
            cards = active.cards
            in_view = {
                n.channel
                for n in active.rows
                if n.channel in focused_channels or str(n.id) == current_key
            }
            shown, folded = order.fold(
                view.inbox_rows(active, pinned, in_view),
                view.statuses(cards),
                pinned,
                self.config.tui.fold_statuses,
                {
                    n.channel
                    for n in active.rows
                    if n.channel in focused_channels
                    or (str(n.id) == current_key and current_key in self._unfolded_ids)
                },
            )  # a focused lemon stays out of the fold, and so does the cursor's row until the cursor leaves it
            emojis = emoji.by_channel(conn)
            group_list = groups.store.all_groups(conn)
            colours = palette.assign_groups(
                (g.name for g in group_list), self.config.tui.group_colors
            )
            group_list = [dataclasses.replace(g, colour=colours[g.name]) for g in group_list]
            wordybins = (
                {
                    c: brief.identity.brief_name(i)
                    for c, i in brief.identity.by_channel(conn).items()
                }
                if self.config.tui.brief_names_in_inbox
                else {}
            )
            # Lower pane: live sessions from other switchable terminals.
            # Headless sessions (switch_source IS NULL) are excluded — they can't be
            # switched to from anywhere, so they belong in history instead.
            if env_filter:
                other_active = self._ordered_active(conn, None)
                other_in_view = {
                    n.channel
                    for n in other_active.rows
                    if n.metadata.get("tty", "") in focused or str(n.id) in {current_key, other_key}
                }
                other_notifications = [
                    n
                    for n in view.inbox_rows(other_active, pinned, other_in_view)
                    if n.switch_source is not None and n.switch_source != env_filter
                ]
            else:
                other_notifications = []
            numbers = pr_numbers.rows(
                conn, [*active.rows, *other_notifications], self.config.places, self._pr_numbers
            )

        shown, folded, self._fold_name = self._arranged(active, shown, folded, pinned, emojis)
        self._unfolded_ids = frozenset(str(n.id) for n in shown)
        entries: list[sections.Header | sections.Row]
        if matching_ids is not None:
            entries = [
                sections.Row(str(n.id), n) for n in [*shown, *folded] if n.id in matching_ids
            ]
            other_notifications = [n for n in other_notifications if n.id in matching_ids]
        else:
            entries, folded = sections.layout(
                shown,
                folded,
                pinned,
                active.memberships,
                group_list,
                view.statuses(cards),
                self._kept,
                self._fold_open,
            )
            if self._fold_open:
                entries = [*entries, *(sections.Row(str(n.id), n) for n in folded)]
        drawn = [e for e in entries if isinstance(e, sections.Row)]
        numbers_by_key = {e.key: i for i, e in enumerate(drawn)}  # jump digits skip headers
        current_notifications = [e.notification for e in drawn]
        briefs = (
            {e.key: cards[e.notification.channel] for e in drawn if e.notification.channel in cards}
            if self.config.tui.brief_status
            else {}
        )
        age_inline = "age" in self.config.tui.card_fields
        extra_lines = max(
            (
                card.extra_lines(age_inline)
                for card in briefs.values()
                if card and self._card_width()
            ),
            default=0,
        )
        now = time.time()

        self._drawn = [e.notification if isinstance(e, sections.Row) else None for e in entries]
        self._group_bands = {
            e.group.group_id: e.band for e in entries if isinstance(e, sections.Header)
        }
        areas = {channel: card.area for channel, card in cards.items() if card.area}
        unread_count = len({n.id for n in current_notifications if n.is_unread})
        self._headers = {e.key: e for e in entries if isinstance(e, sections.Header)}
        self._marked_header = current_row if current_row in self._headers else ""
        headers = {
            e.key: (
                group_headers.cells(
                    e,
                    self._card_width(),
                    len(main_table.columns),
                    _NAME_CELL,
                    e.key == self._marked_header,
                ),
                group_headers.background(e),
            )
            for e in entries
            if isinstance(e, sections.Header)
        }
        self.set_class(bool(unread_count), "-unread")
        rebuilt = _sync_rows(
            main_table,
            [
                (e.key, headers[e.key][0])
                if isinstance(e, sections.Header)
                else (
                    e.key,
                    self._active_row(
                        e.notification,
                        numbers_by_key[e.key],
                        focused_channels,
                        pinned,
                        emojis,
                        areas.get(e.notification.channel, ""),
                        wordybins.get(e.notification.channel, ""),
                        numbers.get(e.notification.channel),
                    )[1],
                )
                for e in entries
            ],
            self._card_width(),
            self._card_shape(extra_lines),
            GUTTER_WIDTH,
            self.config.tui.card_unread_style,
            {e.key: emojis.get(e.notification.channel, "") for e in drawn},
            briefs,
            now,
            {
                e.key: self._context_parts(
                    e.notification,
                    e.notification.is_unread,
                    areas.get(e.notification.channel, ""),
                    briefs.get(e.key),
                    now,
                )
                for e in drawn
            },
            age_inline,
            self.config.tui.project_name_colors,
            headers,
            {
                e.key: self._headers[f"group:{group}"].group.colour
                for e in drawn
                if (group := sections.row_group_id(e.key)) is not None
                and f"group:{group}" in self._headers
            },
        )

        fold_label.display = bool(folded) and not self._search_mode
        update_static(fold_label, self._fold_label(len(folded)))

        # Populate non-switchable table (always dim, not interactive).
        # Hide it if the terminal is too short — main table gets priority.
        _MIN_MAIN_ROWS = 5
        chrome = 3 + bool(folded)  # header, other_label, the status/footer row, the fold line
        other_height = min(len(other_notifications), 8)
        room_for_main = self.size.height - chrome - other_height
        show_other = other_notifications and room_for_main >= _MIN_MAIN_ROWS

        if show_other:
            other_label.update("── non-switchable ──")
            other_label.display = True
            other_table.display = True
            _sync_rows(
                other_table,
                [
                    self._other_row(
                        n,
                        emojis,
                        areas.get(n.channel, ""),
                        wordybins.get(n.channel, ""),
                        numbers.get(n.channel),
                    )
                    for n in other_notifications
                ],
                self._card_width(),
                self._card_shape(),
                contexts_by_row={
                    str(n.id): self._context_parts(n, False, areas.get(n.channel, ""))
                    for n in other_notifications
                },
            )
        else:
            if other_table.row_count:
                other_table.clear()
            other_label.display = False
            other_table.display = False
            if focused_on_other:
                self.query_one("#main_table", DataTable).focus()

        # Restore other table cursor
        if other_table.row_count > 0:
            other_target = None
            if other_key:
                with contextlib.suppress(Exception):
                    other_target = other_table.get_row_index(other_key)
            other_table.move_cursor(
                row=(
                    other_target
                    if other_target is not None
                    else min(other_index, other_table.row_count - 1)
                )
            )

        # Restore cursor position. An in-place update leaves the cursor where it
        # was, so only a rebuild (or an explicit jump) needs to move it — moving
        # it every tick is what made the list flash back to the top.
        # When the focused lemon changes, by whatever route, the cursor goes to its
        # row, unless the cursor is already on one of its rows.
        follow = None
        if focused_channels != self._followed_focus:
            self._followed_focus = focused_channels
            if not any(
                str(n.id) == current_key and n.channel in focused_channels for n in active.rows
            ):
                follow = focus.first_row(entries, focused_channels)
        if main_table.row_count > 0 and follow is not None:
            main_table.move_cursor(row=follow)
        elif main_table.row_count > 0 and (rebuilt or stay_on_unread):
            target_index = None
            unread_rows = [i for i, n in enumerate(self._drawn) if n and n.is_unread]
            if stay_on_unread and unread_rows:
                # The next unread at or below the cursor, else the last one above.
                # Pins and blocked rows mean unread rows need not be contiguous.
                target_index = next((i for i in unread_rows if i >= current_index), unread_rows[-1])
            elif stay_on_unread:
                # No unread left, go to top
                target_index = 0
            else:
                # The same row, else the same lemon wherever it went, else the same place
                for key in (current_row, current_key):
                    if key and target_index is None:
                        with contextlib.suppress(Exception):
                            target_index = main_table.get_row_index(key)
                # Fall back to same position (clamped to valid range)
                if target_index is None:
                    target_index = min(current_index, main_table.row_count - 1)
            main_table.move_cursor(row=target_index)

        self._refresh_resume_binding()

        archive_count = 0
        archive_label = self.query_one("#search_archive_label", Static)
        history_table = self.query_one("#history_table", DataTable)
        if self._search_mode:
            archive_count = self._refresh_history()
            update_static(
                archive_label,
                f"━ ARCHIVE · {archive_count} MATCH{'ES' if archive_count != 1 else ''} ━",
            )
            inbox_height = int(main_table.show_header) + sum(
                row.height for row in main_table.rows.values()
            )
            if show_other:
                inbox_height += 1 + min(8, sum(row.height for row in other_table.rows.values()))
            available_height = (
                self.query_one("#inbox_content", Container).size.height
                - self.query_one("#history_filter", Input).outer_size.height
                - self.query_one("#status", Static).outer_size.height
                - self._notes_height()
            )
            show_archive = bool(archive_count) and (not other_notifications or bool(show_other))
            if show_archive:
                first_archive_row = next(iter(history_table.rows.values())).height
                show_archive = (
                    available_height - inbox_height
                    >= 1 + int(history_table.show_header) + first_archive_row
                )
            self.set_class(show_archive, "-search-archive")
            history_table.display = show_archive
            archive_label.display = show_archive
            if not show_archive and self.focused is history_table:
                main_table.focus()
        else:
            self.set_class(False, "-search-archive")
            history_table.display = False
            archive_label.display = False

        read_count = len(active.rows) - unread_count
        env_label = f" [{self.current_env}]" if self.current_env != "unknown" else ""
        status_text = f"{unread_count} unread, {read_count} read{env_label}"
        if self._search_mode:
            inbox_count = len(current_notifications) + len(other_notifications)
            status_text = (
                f"{inbox_count} inbox match{'es' if inbox_count != 1 else ''} and "
                f"{archive_count} archive match{'es' if archive_count != 1 else ''}"
            )

        # Add patch warning if Claude is unpatched
        if self._claude_patch_status == "unpatched":
            status_text += "  |  [bold cyan]P[/]atch Claude for faster notifications"

        position = current_position(self.config.tmux_session.scratch_position)
        dimension = "width" if position == "left" else "height"
        if (
            self._scratch_mode
            and is_follow_enabled()
            and size_has_drifted(position, getattr(self.size, dimension))
        ):
            status_text += (
                f"  |  [bold cyan]{self.config.tui.keybindings.save_size}[/] save pane {dimension}"
            )

        if self._arrange_error:
            status_text += f"  |  [bold red]arrange:[/] {escape(self._arrange_error)}"

        self._set_status(status_text)

    def _fold_label(self, count: int) -> str:
        """The folded group's one line: which statuses, how many, and the key that opens it."""
        key = self.config.tui.keybindings.fold[:1]
        group = (
            f"{self._fold_name or ', '.join(self.config.tui.fold_statuses) or 'folded'} ({count})"
        )
        if self._fold_open:
            return f"▴ {group} above" + (f" · {key} to fold" if key else "")

        return f"▸ {group}" + (f" · {key} to show" if key else "")

    def action_toggle_fold(self) -> None:
        if self._history_mode or self._snoozed_mode:
            return

        self._fold_open = not self._fold_open
        self._refresh_notifications()

    def action_quit(self) -> None:
        """Quit the app, or just hide the pane in scratch mode.

        In history mode, q quits directly (use h to return to active view).
        The snoozed list is a subview, so q backs out of it instead.
        """
        if self._brief_target is not None:
            self._brief_switch_pending = None
            pane = os.environ.get("TMUX_PANE")
            if pane:
                brief.sidebar.clear(pane)
            self._set_brief_view(None)
            return

        if self._snoozed_mode:
            self._set_snoozed_mode(False)
            return

        if self._search_mode:
            self._stop_search()
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
        self.push_screen(HelpScreen(self._help_keys(), wide=not self._card_layout))

    def _help_keys(self) -> KeybindingsConfig:
        """The keybindings the reference lists: only the ones that are bound.

        The fold and notes keys are bound only when something folds or there
        are notes.
        """
        kb = self.config.tui.keybindings
        if not (self.config.tui.fold_statuses or self.config.inbox.arrange):
            kb = dataclasses.replace(kb, fold="")
        if self.config.tui.notes is None:
            kb = dataclasses.replace(kb, notes="")
        return kb

    def action_toggle_notes(self) -> None:
        self._notes_open = not self._notes_open
        self._refresh_notifications()  # refreshes the notes, then sizes the cards to them

    def on_notes_panel_resized(self, _message: NotesPanel.Resized) -> None:
        self._refresh_notifications()

    def _notes_panel(self) -> NotesPanel | None:
        panels = self.query(NotesPanel)
        return panels.first() if panels else None

    def _refresh_notes(self) -> None:
        """Show the notes under the cards, unless hidden; a top strip has no room for them."""
        panel = self._notes_panel()
        if panel is None:
            return

        panel.display = self._notes_open and self._card_layout
        if panel.display:
            panel.reload()

    def _notes_height(self) -> int:
        """Rows the notes take from the cards, as last laid out."""
        panel = self._notes_panel()
        return panel.outer_size.height if panel is not None and panel.display else 0

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
        update_static(self.query_one("#status", Static), text)

    def _refresh_resume_binding(self) -> None:
        resume_footer_shown = (
            self._selected_channel() in self._detached_channels or self._brief_local
        )
        if resume_footer_shown != self._resume_footer_shown:
            self._resume_footer_shown = resume_footer_shown
            self._set_binding_footer("resume_detached", show=resume_footer_shown)
            self.refresh_bindings()

    def _detached_marker(self, notification: db.Notification) -> Text:
        if notification.channel not in self._detached_channels:
            return Text()

        marker = Text(" · detached", style="dim")
        if not self._can_resume_detached(notification):
            marker.append(" · resume unavailable", style="dim red")

        return marker

    def _can_resume_detached(self, notification: db.Notification) -> bool:
        return notification.switch_source in {"tmux", "cmux"} and bool(
            resume_mod.build_resume_command(
                self.config, notification.channel, notification.metadata
            )
        )

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
                (
                    n.id,
                    n.metadata.get("session_id", ""),
                    n.metadata.get("cwd", ""),
                    n.metadata.get("transcript_path"),
                )
                for n in db.get_active(conn, switch_source=None)
                if n.channel.startswith("claude:")
                and n.metadata.get("name_source") not in ("claude_rename", "claude_index")
                and n.metadata.get("session_id")
                and n.metadata.get("cwd")
            ]

        upgraded = False
        for notification_id, session_id, cwd, transcript_path in candidates:
            transcript = notify.find_transcript(session_id, cwd, transcript_path)
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
            resolved = notify.resolve_session_name(session_id, cwd, transcript_path)
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
        if enabled and self._search_mode:
            self._stop_search(refresh=False)
        self._history_mode = enabled
        self._history_filter = ""

        main_table = self.query_one("#main_table", DataTable)
        other_label = self.query_one("#other_sources_label", Static)
        other_table = self.query_one("#other_sources_table", DataTable)
        history_table = self.query_one("#history_table", DataTable)
        history_filter = self.query_one("#history_filter", Input)

        # Inbox-only actions
        for action in (
            "jump_unread",
            "mark_read",
            "mark_unread",
            "archive",
            "snooze",
            "toggle_fold",
        ):
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
        if enabled and self._resume_footer_shown:
            self._resume_footer_shown = False
            self._set_binding_footer("resume_detached", show=False)
        self.refresh_bindings()

        self.set_class(enabled, "-history")

        if enabled:
            self.sub_title = "session history"
            main_table.display = False
            self.query_one("#fold_label", Static).display = False
            other_label.display = False
            other_table.display = False
            self.query_one("#search_archive_label", Static).display = False
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

    def _refresh_history(self) -> int:
        history_table = self.query_one("#history_table", DataTable)
        current_row = history_table.cursor_coordinate.row if history_table.row_count > 0 else 0

        history_table.clear()

        with db.connect() as conn:
            if self._search_mode:
                source = self.current_env if self.current_env != "unknown" else None
                results = search.find(
                    conn,
                    self._history_filter,
                    include_history=True,
                    switch_source=source,
                )
                notifications = [
                    result.notification for result in results if result.source == "archive"
                ]
            else:
                notifications = db.get_history(conn, search=self._history_filter)
            brief_paths = brief_attached.by_channel(conn, [n.channel for n in notifications])

        for n in notifications:
            if not resume_mod.has_resume_command(self.config, n.channel):
                continue

            created = _format_timestamp(n.created_at)
            branch = n.metadata.get("git_branch", "")

            name_cell = styled_cell(n.name or "", False, "name", history=True)
            card = (path := brief_paths.get(n.channel)) and self._brief_cache.get(path)
            area = card.area if card else ""
            if card and card.status:
                name_cell.append(
                    f" · {card.status}",
                    style=brief_cards.STATUS_STYLES.get(card.status, "dim"),
                )

            cells = [
                styled_cell(
                    created,
                    False,
                    "time",
                    history=True,
                    neutral_timing=self.config.tui.project_name_colors,
                ),
                Text(""),  # archived: never a marker, but cards index by position
                self._backend_value(n, False, history=True),
                name_cell,
                styled_cell(branch, False, "branch", history=True),
                self._where_cell(n, False, area),
                styled_cell(n.message, False, "message", history=True),
                Text(""),  # No TTY for archived
            ]
            card_width = self._card_width()
            shape = self._card_shape()
            # Columns drop the marker; cards have no columns to drop, and index
            # their fields by position.
            card = (
                _as_card(
                    cells, card_width, *shape, context_parts=self._context_parts(n, False, area)
                )
                if card_width
                else _without_marker(cells)
            )
            history_table.add_row(
                *card, key=str(n.id), height=_row_height(card) if card_width else 1
            )

        if history_table.row_count > 0:
            history_table.move_cursor(row=min(current_row, history_table.row_count - 1))

        count = history_table.row_count
        if not self._search_mode:
            self._set_status(f"{count} archived session{'s' if count != 1 else ''}")
        return count

    def _set_snoozed_mode(self, enabled: bool) -> None:
        if enabled and self._search_mode:
            self._stop_search(refresh=False)
        self._snoozed_mode = enabled

        main_table = self.query_one("#main_table", DataTable)
        snoozed_table = self.query_one("#snoozed_table", DataTable)
        other_label = self.query_one("#other_sources_label", Static)
        other_table = self.query_one("#other_sources_table", DataTable)

        # Inbox-only actions don't apply to the snoozed list
        for action in ("jump_unread", "mark_read", "mark_unread", "snooze", "toggle_fold"):
            self._set_binding_footer(action, show=not enabled)

        self._set_binding_footer(
            "toggle_snoozed",
            label="Exit Snoozed" if enabled else "Snoozed",
        )
        self._set_binding_footer("select", label="Wake" if enabled else "Switch")
        if enabled and self._resume_footer_shown:
            self._resume_footer_shown = False
            self._set_binding_footer("resume_detached", show=False)
        self.refresh_bindings()

        if enabled:
            self.sub_title = "snoozed"
            main_table.display = False
            self.query_one("#fold_label", Static).display = False
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
            brief_paths = brief_attached.by_channel(conn, [n.channel for n in notifications])
        areas = {
            channel: card.area
            for channel, path in brief_paths.items()
            if (card := self._brief_cache.get(path))
        }

        rebuilt = _sync_rows(
            snoozed_table,
            [
                (
                    str(n.id),
                    [
                        _time_cell(
                            n.created_at,
                            False,
                            history=True,
                            neutral_timing=self.config.tui.project_name_colors,
                        ),
                        Text("○", style="dim") if n.snooze_prev_status == "unread" else Text(""),
                        self._backend_value(n, False),
                        styled_cell(n.name or "", False, "name"),
                        styled_cell(n.metadata.get("git_branch", ""), False, "branch"),
                        self._where_cell(n, False, areas.get(n.channel, "")),
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
            contexts_by_row={
                str(n.id): self._context_parts(n, False, areas.get(n.channel, ""))
                for n in notifications
            },
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

    def _show_error(self, title: str, message: str) -> None:
        _log.warning("%s: %s", title, message)
        self.push_screen(ErrorScreen(title, message))

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
            resume = (
                resume_mod.build_resume_command(
                    self.config, notification.channel, notification.metadata
                )
                if notification.switch_source == "tmux"
                else None
            )
            if resume:
                cwd, argv = resume
                command = f"cd {shlex.quote(cwd)} && {shlex.join(argv)}"
                self.push_screen(
                    ResumeErrorScreen(
                        "No safe tmux destination",
                        "Lemonaid could not identify one existing session safely. "
                        "Copy this command, then paste it into the session where you want "
                        "the lemon to run.",
                        offer="copy the resume command",
                        details=(
                            f"Original directory is gone: {notification.metadata.get('cwd')}. "
                            f"The conversation will resume in {cwd}.\n\n{command}"
                            if cwd != notification.metadata.get("cwd")
                            else command
                        ),
                    ),
                    lambda copy: self._copy_resume_command(command) if copy else None,
                )
                return False

            title = "Could not switch to that session"
            message = "Its pane is gone and lemonaid could not recreate one for it."
            _log.warning("%s: %s", title, message)
            self.push_screen(
                ResumeErrorScreen(
                    title,
                    message + " Open its brief with b, or restore its directory and try again.",
                    offer="archive it",
                ),
                lambda archive: self._archive_notification(notification.id) if archive else None,
            )
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

    def _copy_resume_command(self, command: str) -> None:
        try:
            subprocess.run(["pbcopy"], input=command.encode(), check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.notify(f"Resume: {command}", severity="information")
        else:
            self.notify("Copied resume command to clipboard")

    def action_resume_detached(self) -> None:
        """Resume the selected row only when its pane is known to be gone."""
        if self._selected_channel() not in self._detached_channels and not self._brief_local:
            return

        table = self.query_one("#main_table", DataTable)
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        if (notification_id := _key_id(row_key)) is None:
            return

        with db.connect() as conn:
            notification = db.get(conn, notification_id)

        if notification is None:
            self._show_error("That session is gone", "Its row was removed from the inbox.")
            return

        if not self._can_resume_detached(notification):
            self.push_screen(
                ResumeErrorScreen(
                    "Resume unavailable",
                    "This backend or its saved session details do not provide a resume command. "
                    "Press Escape to return, then b to read its brief. Restore its directory "
                    "or start the harness manually with the saved session ID.",
                )
            )
            return

        self._switch_to_notification(notification)

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
            self._show_error(
                "That session is gone",
                "Its row was removed from the inbox since the list was drawn.",
            )
            return

        # A session that never stopped needs returning to the inbox, not a
        # second copy of itself started next to the one already running.
        if not copy_only and unarchive.running(notification):
            with db.connect() as conn:
                unarchive.restore(conn, notification.channel)

            if self._search_mode:
                self._stop_search()
            else:
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
            self._show_error(
                "Could not resume that session",
                "No working directory is recorded for it, so there is nowhere to resume it.",
            )
            return

        cwd, argv = resume
        quoted_argv = [shlex.quote(a) for a in argv]
        cmd_str = (
            f"cd {shlex.quote(cwd)} && {' '.join(quoted_argv)}"
            if argv
            else f"cd {shlex.quote(cwd)}"
        )
        mode = "copy" if copy_only else ("tmux" if self._scratch_mode else "exec")
        _log.info("resume: %s (%s) -> %s", notification.channel, mode, cmd_str)

        # The scratch pane has no terminal of its own to run the session in.
        if mode == "tmux" and argv:
            error = resume_archived.in_tmux(notification, self.config)
            if error:
                self._resume_failed(cmd_str, error)
                return

            self._refresh_notifications()
            if not is_follow_enabled():
                self._hide_scratch_pane()
            return

        # Before the row is unread, or the watcher judges it by its dead pane.
        if mode == "exec" and argv and navigation.is_inside_tmux() and os.isatty(0):
            with db.connect() as conn:
                resume_archived.recorded_here(conn, notification.channel, os.ttyname(0))

        # Unarchive so the session appears in the main inbox immediately
        with db.connect() as conn:
            conn.execute(
                "UPDATE notifications SET status = 'unread', read_at = NULL, created_at = ? WHERE id = ?",
                (time.time(), notification.id),
            )
            conn.commit()

        # Non-scratch, non-copy: exec in the current terminal
        if mode == "exec" and argv:
            self._exec_on_exit = (cwd, argv)
            self.exit()
            return

        # Copy to clipboard
        try:
            subprocess.run(["pbcopy"], input=cmd_str.encode(), check=True)
            self.notify(f"Copied: {cmd_str}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.notify(f"Resume: {cmd_str}", severity="information")

    def _resume_failed(self, command: str, reason: str) -> None:
        _log.warning("resume failed: %s", reason)
        self.push_screen(
            ResumeErrorScreen(
                "Could not resume that session",
                f"{reason} Copy the command to run it in a terminal of your choice.",
                offer="copy the resume command",
                details=command,
            ),
            lambda copy: self._copy_resume_command(command) if copy else None,
        )

    def action_copy_resume(self) -> None:
        """Copy the resume command for the selected history session."""
        if not (self._history_mode or self._search_mode):
            return
        self._resume_session(copy_only=True)

    def action_tmux_resume(self) -> None:
        """Spawn a new tmux session around the selected history entry."""
        if not (self._history_mode or self._search_mode):
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
            self._show_error(
                "That session is gone",
                "Its row was removed from the inbox since the list was drawn.",
            )
            return

        resume = resume_mod.build_resume_command(
            self.config, notification.channel, notification.metadata
        )
        if not resume:
            self._show_error(
                "Could not resume that session",
                "No working directory is recorded for it, so there is nowhere to resume it.",
            )
            return

        cwd, argv = resume
        error = resume_archived.in_new_session(notification, self.config)
        if error:
            self._resume_failed(f"cd {shlex.quote(cwd)} && {shlex.join(argv)}", error)
            return

        self._refresh_notifications()

    def action_filter_history(self) -> None:
        """Search inbox rows, or focus the existing history filter."""
        if not self._history_mode and not self._search_mode:
            self._search_mode = True
            self._history_filter = ""
            self.sub_title = "search"
            self.set_class(True, "-search")
            self._refresh_notifications()
        history_filter = self.query_one("#history_filter", Input)
        history_filter.display = True
        history_filter.focus()

    def _stop_search(self, *, refresh: bool = True) -> None:
        self._search_mode = False
        self._history_filter = ""
        self.sub_title = "attention inbox"
        self.set_class(False, "-search")
        history_filter = self.query_one("#history_filter", Input)
        history_filter.value = ""
        history_filter.display = False
        self.query_one("#search_archive_label", Static).display = False
        self.query_one("#history_table", DataTable).display = False
        if refresh:
            self._refresh_notifications()
            self.query_one("#main_table", DataTable).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "history_filter":
            self._history_filter = event.value
            if self._search_mode:
                self._refresh_notifications()
            elif self._history_mode:
                self._refresh_history()

    def on_key(self, event: events.Key) -> None:
        """Handle special keys in the filter input."""
        if event.key == "f12" and self._scratch_mode:
            event.prevent_default()
            event.stop()
            if not self._brief_switching:  # a switch in flight wakes it twice on the way
                self._sync_brief_view()
            # The follow hook sends it after moving this pane, so the focused pane has changed.
            self._focused_asked_at = 0.0
            self._refresh_notifications()
            return

        if not (isinstance(self.focused, Input) and self.focused.id == "history_filter"):
            return

        # Down/Enter: keep filter active, move focus to matching rows.
        if event.key in ("down", "enter"):
            event.prevent_default()
            event.stop()
            main = self.query_one("#main_table", DataTable)
            other = self.query_one("#other_sources_table", DataTable)
            archive = self.query_one("#history_table", DataTable)
            if self._search_mode and main.row_count:
                main.focus()
            elif self._search_mode and other.display and other.row_count:
                other.focus()
            elif self._search_mode and archive.display and archive.row_count:
                archive.focus()
            else:
                (main if self._search_mode else archive).focus()
            return

        # Escape: clear filter, hide it, focus table
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            if self._search_mode:
                self._stop_search()
                return

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
        if self._brief_target is not None:
            self._navigate_brief(-1)
            return
        table = self._focused_table()
        if table.id == "history_table" and self._search_mode and table.cursor_coordinate.row == 0:
            other = self.query_one("#other_sources_table", DataTable)
            main = self.query_one("#main_table", DataTable)
            previous = other if other.display and other.row_count else main
            previous.focus()
            if previous.row_count:
                previous.move_cursor(row=previous.row_count - 1)
        elif table.id == "other_sources_table" and table.cursor_coordinate.row == 0:
            main = self.query_one("#main_table", DataTable)
            main.focus()
            if main.row_count > 0:
                main.move_cursor(row=main.row_count - 1)
        else:
            table.action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move cursor down, jumping to other table from main table when at bottom."""
        if self._brief_target is not None:
            self._navigate_brief(1)
            return
        table = self._focused_table()
        if table.id == "main_table" and table.cursor_coordinate.row >= table.row_count - 1:
            other = self.query_one("#other_sources_table", DataTable)
            if other.display and other.row_count > 0:
                other.focus()
                other.move_cursor(row=0)
                return

        if (
            self._search_mode
            and table.id in {"main_table", "other_sources_table"}
            and table.cursor_coordinate.row >= table.row_count - 1
        ):
            archive = self.query_one("#history_table", DataTable)
            if archive.display and archive.row_count:
                archive.focus()
                archive.move_cursor(row=0)
                return

        table.action_cursor_down()

    def action_cursor_first(self) -> None:
        """Move to the top row: the main table's first, pins included."""
        table = self._focused_table()
        if table.id == "other_sources_table":
            table = self.query_one("#main_table", DataTable)
            table.focus()
        if table.row_count > 0:
            table.move_cursor(row=0)

    def action_cursor_last(self) -> None:
        """Move to the bottom row of the focused table.

        In the inbox that is the main table's last row: a folded group stays
        folded, and the lower table, which nothing can be switched to, is skipped.
        """
        table = self._focused_table()
        if table.id == "other_sources_table":
            table = self.query_one("#main_table", DataTable)
            table.focus()
        if table.row_count > 0:
            table.move_cursor(row=table.row_count - 1)

    def _navigate_brief(self, direction: int) -> None:
        """Show the adjacent row's brief now, and move the main pane to its lemon after."""
        table = self.query_one("#main_table", DataTable)
        next_row = table.cursor_coordinate.row + direction
        if not 0 <= next_row < table.row_count:
            return

        while (
            0 <= next_row < table.row_count
            and _key_id(table.coordinate_to_cell_key(Coordinate(next_row, 0))[0]) is None
        ):
            next_row += direction  # past a group header
        if not 0 <= next_row < table.row_count:
            return

        key, _ = table.coordinate_to_cell_key(Coordinate(next_row, 0))
        if (notification_id := _key_id(key)) is None:
            return
        with db.connect() as conn:
            notification = db.get(conn, notification_id)
            attached = brief.attached.for_rows(conn, [notification] if notification else [])
            emojis = emoji.by_channel(conn)
        if notification is None:
            return

        found = self._brief_targets.get(notification.id) or brief.target.for_notification(
            notification, attached, emojis.get(notification.channel, "")
        )
        table.move_cursor(row=next_row)
        self._set_brief_view(found)
        self._prefetch_brief_targets()
        if notification.channel in self._detached_channels or notification.switch_source != "tmux":
            self._brief_switch_pending = None
            self._brief_local = True
            self.query_one(BriefView).notice(
                f"Its terminal is unavailable here. Press {self.config.tui.keybindings.resume_detached} "
                "to resume; up/down keeps browsing."
            )
            return

        self._brief_switch_pending = (notification, found)
        if not self._brief_switching:
            self._brief_switching = True
            self.run_worker(self._run_brief_switches, thread=True, group="brief-switch")

    def _prefetch_brief_targets(self) -> None:
        """Resolve the targets of the rows around the cursor, ready for the next arrows."""
        table = self.query_one("#main_table", DataTable)
        row = table.cursor_coordinate.row
        keys = [
            table.coordinate_to_cell_key(Coordinate(near, 0))[0]
            for near in (row - 2, row - 1, row + 1, row + 2)
            if 0 <= near < table.row_count
        ]
        with db.connect() as conn:
            rows = [
                notification
                for key in keys
                if (found := _key_id(key)) is not None
                and found not in self._brief_targets
                and (notification := db.get(conn, found))
            ]
            if not rows:
                return

            attached = brief.attached.for_rows(conn, rows)
            emojis = emoji.by_channel(conn)

        def resolve() -> None:
            try:
                found = {
                    n.id: brief.target.for_notification(n, attached, emojis.get(n.channel, ""))
                    for n in rows
                }
            except Exception:  # the thread's top level; the next arrow resolves its own
                _log.exception("could not resolve briefs near the cursor")
                return
            self.call_from_thread(lambda: self._brief_targets.update(found))

        self.run_worker(resolve, thread=True, group="brief-prefetch")

    def _take_brief_switch(self) -> tuple[db.Notification, brief.target.Target] | None:
        request, self._brief_switch_pending = self._brief_switch_pending, None
        if request is None:
            self._brief_switching = False

        return request

    def _run_brief_switches(self) -> None:
        """The worker thread: switch to the newest selection until none is waiting."""
        while request := self.call_from_thread(self._take_brief_switch):
            notification, found = request
            metadata = {
                **notification.metadata,
                "channel": notification.channel,
                "name": notification.name or "",
            }
            try:
                switched = brief.sidebar.switch_beside(
                    metadata, notification.switch_source, self.config, found
                )
            except Exception:  # the thread's top level; the pane must not die with it
                _log.exception("brief switch to %s failed", notification.channel)
                switched = False
            self.call_from_thread(self._brief_switched, notification, switched)

    def _brief_switched(self, notification: db.Notification, switched: bool) -> None:
        pane = os.environ.get("TMUX_PANE", "")
        if self._brief_target is None:
            # Closed while the switch ran, which set the sidebar brief again.
            if pane:
                brief.sidebar.clear(pane)
            return

        if self._get_current_row_key() != str(notification.id):
            return

        if switched:
            self._brief_local = False
            tty = notification.metadata.get("tty")
            if isinstance(tty, str) and tty:
                self._focused = frozenset({tty})
                self._focused_asked_at = time.time()
        if self._brief_switch_pending is not None:
            return

        if not switched:
            self._brief_local = True
            self.query_one(BriefView).notice(
                f"Its terminal could not be opened. Press {self.config.tui.keybindings.resume_detached} "
                "to try resuming; up/down keeps browsing."
            )
            return

        self._sync_brief_view()

    def action_select(self) -> None:
        """Select the current row (same as Enter). No-op on non-switchable table."""
        table = self._focused_table()
        if (self._history_mode or self._search_mode) and table.id == "history_table":
            self._resume_session()
        elif self._snoozed_mode and table.id == "snoozed_table":
            self._wake_selected()
        elif table.id == "main_table":
            table.action_select_cursor()

    def action_select_brief(self) -> None:
        self.action_select()

    def action_refresh(self) -> None:
        if self._brief_target is not None:
            self.query_one(BriefView).show(self._brief_target, self._brief_unread())
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
        if (notification_id := _key_id(row_key)) is not None:
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
        if (notification_id := _key_id(row_key)) is None:
            return

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
        if (notification_id := _key_id(row_key)) is None:
            return

        self._archive_notification(notification_id)

    def _archive_notification(self, notification_id: int) -> None:
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
            db.archive(conn, notification_id, "user-action")

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
                found = _key_id(key)
                notification = db.get(conn, found) if found is not None else None
                channels.append(notification.channel if notification else "")

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

    def _selected_group(self) -> "groups.store.Group | None":
        """The group whose header is under the cursor, in the main list only."""
        if self._history_mode or self._snoozed_mode:
            return None

        raw = self._raw_row_key(self.query_one("#main_table", DataTable))
        found = sections.group_id(raw) if raw else None
        if found is None:
            return None

        with db.connect() as conn:
            return next((g for g in groups.store.all_groups(conn) if g.group_id == found), None)

    def _select_key(self, key: str) -> None:
        table = self.query_one("#main_table", DataTable)
        with contextlib.suppress(Exception):
            table.move_cursor(row=table.get_row_index(key))

    def _toggle_group(self, group_id: int, from_row: str = "") -> None:
        """Collapse an open group to its header, or open a collapsed one.

        Collapsing from one of its lemons keeps that lemon drawn, under the
        cursor, until the cursor moves off it.
        """
        with db.connect() as conn:
            group = next((g for g in groups.store.all_groups(conn) if g.group_id == group_id), None)
            if group is None:
                return

            groups.arrangement.set_collapsed(conn, group, not group.collapsed)

        self._kept = frozenset({from_row} if from_row and not group.collapsed else ())
        self._refresh_notifications()
        self._select_key(from_row or f"group:{group_id}")

    def action_toggle_group(self) -> None:
        """Open or collapse the group whose header or lemon is under the cursor."""
        if self._history_mode or self._snoozed_mode:
            return

        raw = self._raw_row_key(self.query_one("#main_table", DataTable)) or ""
        if (found := sections.group_id(raw)) is not None:
            self._toggle_group(found)
            return

        if (found := sections.row_group_id(raw)) is not None:
            self._toggle_group(found, from_row=raw)

    def _move_group(self, group: "groups.store.Group", offset: int) -> None:
        """Trade places with the group header *offset* away on screen.

        Groups sort by their most pressing row first, so only the order among
        groups drawn next to each other is the user's to change.
        """
        table = self.query_one("#main_table", DataTable)
        on_screen = [
            found
            for row in range(table.row_count)
            if (key := table.coordinate_to_cell_key(Coordinate(row, 0))[0]) is not None
            and (found := sections.group_id(str(key.value))) is not None
        ]
        neighbour = on_screen.index(group.group_id) + offset
        if not 0 <= neighbour < len(on_screen):
            return

        if self._group_bands.get(on_screen[neighbour]) != self._group_bands.get(group.group_id):
            self.notify("Groups sort by their most pressing lemon; this one can't pass that group")
            return

        with db.connect() as conn:
            other = next(
                (g for g in groups.store.all_groups(conn) if g.group_id == on_screen[neighbour]),
                None,
            )
            if other is None:
                return

            groups.arrangement.swap(conn, group, other)

        self._refresh_notifications()
        self._select_key(f"group:{group.group_id}")

    def action_move_pin_up(self) -> None:
        if group := self._selected_group():
            self._move_group(group, -1)
        else:
            self._move_pin(-1)

    def action_move_pin_down(self) -> None:
        if group := self._selected_group():
            self._move_group(group, 1)
        else:
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
            SnoozeScreen(
                session_name=notification.name or "",
                presets=self.config.inbox.snooze_presets,
                day_start=self.config.inbox.snooze_day_starts,
            ),
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
        self._retarget_brief()
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
                self._retarget_brief()
                self._refresh_notifications()

        self.push_screen(
            RenameScreen(current_name=notification.name or ""),
            handle_rename,
        )

    def _retarget_brief(self) -> None:
        """Resolve the shown brief's target again, after a change to the row it is for.

        The target carries the row's name, and so does the sidebar option a wake
        restores it from, so both are replaced.
        """
        row_key = self._get_current_row_key()
        if self._brief_target is None or not row_key:
            return

        with db.connect() as conn:
            notification = db.get(conn, int(row_key))
            if notification is None:
                return

            attached = brief.attached.for_rows(conn, [notification])
            emojis = emoji.by_channel(conn)

        self._brief_targets.pop(notification.id, None)
        found = brief.target.for_notification(
            notification, attached, emojis.get(notification.channel, "")
        )
        pane = os.environ.get("TMUX_PANE", "")
        if pane:
            brief.sidebar.show(found, brief.sidebar.window_id(pane))
        self._set_brief_view(found)

    def _set_brief_view(self, found: brief.target.Target | None) -> None:
        view = self.query_one(BriefView)
        switcher = self.query_one(ContentSwitcher)
        if found is None:
            if self._brief_target is None:
                return

            self._brief_target = None
            self._brief_local = False
            self._brief_targets.clear()
            switcher.current = "inbox_content"
            self.sub_title = self._brief_saved_subtitle
            self.query_one(f"#{self._brief_saved_focus}").focus()
            self.refresh_bindings()
            self._show_keys(self._keys_shown)
            self._refresh_notifications()
            return

        if found == self._brief_target:
            return

        if self._brief_target is None:
            self._brief_saved_focus = (
                self.focused.id if self.focused and self.focused.id else "main_table"
            )
            self._brief_saved_subtitle = self.sub_title

        self._brief_local = False
        self._brief_target = found
        switcher.current = "brief_view"
        self.sub_title = "brief"
        view.show(found, self._brief_unread())
        view.focus()
        self.refresh_bindings()

    def _brief_unread(self) -> bool:
        """Whether the row under the cursor, whose brief is shown, is unread."""
        row_key = self._get_current_row_key()
        if not row_key:
            return False

        with db.connect() as conn:
            notification = db.get(conn, int(row_key))

        return bool(notification and notification.is_unread)

    def _sync_brief_view(self) -> None:
        if self._brief_local and self._brief_target is not None:
            return

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
            self._show_error(
                "No brief to show", "No brief or directory is recorded for this session."
            )
            return

        if (
            self._scratch_mode
            and is_follow_enabled()
            and not self._history_mode
            and not self._snoozed_mode
            and current_position(self.config.tmux_session.scratch_position) == "left"
        ):
            pane = os.environ.get("TMUX_PANE", "")
            if brief.sidebar.toggle(target, brief.sidebar.window_id(pane)):
                self._sync_brief_view()
                if self._brief_target is not None:
                    self._prefetch_brief_targets()
                return

        brief.popup.open_popup(target)

    def action_jump_unread(self) -> None:
        """Jump directly to the earliest unread session."""
        unread = [(n.created_at, row) for row, n in enumerate(self._drawn) if n and n.is_unread]
        if not unread:
            self.notify("No unread notifications", severity="information")
            return

        # Pins and status bands spread unread rows through the list, so the
        # earliest is found by age rather than by position.
        table = self.query_one("#main_table", DataTable)
        table.move_cursor(row=min(unread)[1])
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

        lemons = [
            row for row, n in enumerate(self._drawn) if n is not None
        ]  # headers are unnumbered
        nth = JUMP_DIGITS.find(digit)
        if nth < 0 or nth >= len(lemons):
            return

        table.move_cursor(row=lemons[nth])
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
                self._show_error("Nothing to patch", "No patterns were found in the Claude binary.")
        except Exception as e:
            self._show_error("Patch failed", str(e))

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

    def _mark_channel_read_after_turn(self, channel: str) -> int:
        with db.connect() as conn:
            return db.mark_read_after_turn(conn, channel)

    def _record_channel_turn(self, channel: str, at: float | None) -> None:
        with db.connect() as conn:
            db.record_turn(conn, channel, at)

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

    def _recorded_tmux_session_orders(self) -> dict[str, navigation.SessionOrder]:
        """Each active channel's tmux identity, if recorded by its own hook."""
        with db.connect() as conn:
            orders: dict[str, navigation.SessionOrder] = {}
            for notification in db.get_active(conn, switch_source="tmux"):
                value = notification.metadata.get("tmux_session_order")
                if (
                    isinstance(value, list)
                    and len(value) == 3
                    and all(isinstance(part, int) for part in value)
                ):
                    orders[notification.channel] = (value[0], value[1], value[2])
            return orders

    def _protected_brief_channels(self) -> set[str]:
        """Channels whose attached brief is waiting for a person to act."""
        with db.connect() as conn:
            channels = [
                n.channel
                for n in db.get_active(conn, switch_source=None)
                if not teardown_evidence.applies(n)
            ]
            paths = brief_attached.by_channel(conn, channels)
        return {
            channel
            for channel, path in paths.items()
            if (card := self._brief_cache.get(path)) is not None
            and card.status in {"merge", "approve", "blocked", "alert"}
        }

    def _locate_sessions(self, active: list[tuple]) -> dict[str, str | Literal[False] | None]:
        """Where each active session that can outlive its tty runs now (see handlers)."""
        channels = {row[0] for row in active if row[7] in handlers.PER_SESSION_SOURCES}
        if not channels:
            return {}

        with db.connect() as conn:
            sessions = [
                (n.switch_source, {**n.metadata, "channel": n.channel})
                for n in db.get_active(conn, switch_source=None)
                if n.channel in channels
            ]
        return handlers.where_sessions_are(sessions)

    def _set_detached_channels(self, channels: set[str]) -> None:
        self._detached_channels = frozenset(channels)

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
        self,
        channel: str,
        session: str,
        window: str,
        socket: str | None = None,
        session_order: navigation.SessionOrder | None = None,
    ) -> None:
        """Note where a session is sitting, so `tmux restore` can rebuild it.

        Done on the watcher's poll rather than only when a session notifies:
        an idle session would otherwise never record one, and those are the
        ones whose position is hardest to remember after a crash.
        """
        with db.connect() as conn:
            db.record_location(conn, channel, session, window, socket, session_order)

    def _record_channel_model(self, channel: str, provider: str, model: str) -> None:
        with db.connect() as conn:
            db.record_model(conn, channel, provider, model)

    def _record_channel_context(self, channel: str, used: int, window: int) -> None:
        with db.connect() as conn:
            db.record_context(conn, channel, used, window)

    def _archive_channel(self, channel: str) -> None:
        """Archive all notifications for a channel (session exited)."""
        with db.connect() as conn:
            db.archive_channel(conn, channel, "watcher-stale-session")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if not self.is_running:
            return  # queued highlights can arrive after shutdown removes the tables

        if event.data_table.id == "main_table":
            self._mark_header(str(event.row_key.value) if event.row_key else "")
        self._refresh_resume_binding()

    def _mark_header(self, key: str) -> None:
        """Move the cursor's marker to the header at *key*, or off every header."""
        wanted = key if key in self._headers else ""
        if wanted == self._marked_header:
            return

        table = self.query_one("#main_table", DataTable)
        for changed in (self._marked_header, wanted):
            if not changed:
                continue

            cells = group_headers.cells(
                self._headers[changed],
                self._card_width(),
                len(table.columns),
                _NAME_CELL,
                changed == wanted,
            )
            with contextlib.suppress(Exception):  # the row may be gone before a refresh
                row = table.get_row_index(changed)
                for column, value in enumerate(cells):
                    table.update_cell_at((row, column), value, update_width=False)
        self._marked_header = wanted

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._activate_row(event.data_table.id, event.row_key)

    def on_click_to_act_table_selected_row_clicked(
        self, event: ClickToActTable.SelectedRowClicked
    ) -> None:
        # Keep a click to stay in scratch only when this row still names the
        # pane behind it. An external jump can leave the cursor on another lemon.
        if event.data_table.id == "main_table" and self.has_class("-input-active"):
            with db.connect() as conn:
                found = _key_id(event.row_key)
                notification = db.get(conn, found) if found is not None else None
            behind = focus.behind_scratch(os.environ.get("TMUX_PANE", ""), get_tmux_socket())
            if notification and behind and notification.metadata.get("tty") == behind:
                return

        self._activate_row(event.data_table.id, event.row_key)

    def _activate_row(self, table_id: str | None, row_key: RowKey | None) -> None:
        """Main table: switch to session. History table: resume session."""
        if table_id == "history_table":
            self._resume_session()
            return

        if table_id == "snoozed_table":
            self._wake_selected()
            return

        if table_id != "main_table":
            return

        if row_key is not None and (group_id := sections.group_id(str(row_key.value))) is not None:
            self._toggle_group(group_id)
            return

        if (notification_id := _key_id(row_key)) is None:
            return

        with db.connect() as conn:
            notification = db.get(conn, notification_id)

        if notification:
            self._switch_to_notification(notification)


def main() -> None:
    set_terminal_title("lma")
    app = LemonaidApp()
    app.run()
