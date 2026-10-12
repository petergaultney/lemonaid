"""Main Lemonaid TUI application."""

import os
import shlex
import subprocess
import threading
import time
from pathlib import Path

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.coordinate import Coordinate
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import ContentSwitcher, DataTable, Footer, Input, Static
from textual.widgets.data_table import RowKey

from ... import brief, groups
from ... import resume as resume_mod
from ...claude import notify, patch_status
from ...claude.patcher import apply_patch, find_binary
from ...config import load_config
from ...handlers import handle_notification
from ...lemon_watchers import (
    detect_terminal_switch_source,
    get_tmux_socket,
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
    db,
    emoji,
    pins,
    resume_archived,
    sections,
    unarchive,
    undo,
)
from . import (
    bindings,
    brief_cards,
    focus,
    history_rows,
    inbox_groups,
    inbox_list,
    layout,
    row_keys,
    row_parts,
    snoozed_rows,
    status_line,
    styles,
    table_columns,
    table_layout,
    usage_view,
    utils,
    view_modes,
    watcher_hooks,
)
from .brief_view import BriefView
from .error_screen import ErrorScreen
from .help_screen import HelpScreen
from .inbox_list import InboxList
from .notes import NotesPanel
from .resume_error import ResumeErrorScreen
from .screens import RenameScreen, SnoozeScreen, format_wake_time
from .table import ClickToActTable
from .usage_view import UsageHeader
from .utils import (
    JUMP_DIGITS,
    set_terminal_title,
    update_static,
)

_NAME_REFRESH_SECONDS = 20  # transcript re-scan cadence for session-name upgrades
_KEY_HINT_SECONDS = 10  # how long the footer's key hints stay up before yielding the row

_FOCUS_CACHE_SECONDS = 1.0
_INPUT_FOCUS_CACHE_SECONDS = 0.5

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


class LemonaidApp(App):
    """Lemonaid TUI - attention inbox for your lemons."""

    CSS = styles.CSS

    def __init__(self, scratch_mode: bool = False) -> None:
        self.config = load_config()  # before super(), which reads the CSS variables
        super().__init__()
        self._setup_keybindings()
        self.current_env = detect_terminal_switch_source()
        self._claude_patch_status: str | None = None
        self._claude_binary = find_binary()
        self._scratch_mode = scratch_mode
        self._mode: view_modes.Mode | None = None  # an alternate view, while one is shown
        self._search_mode = False
        self._history_filter = ""
        self._undo_stack = undo.Stack()
        self._last_name_refresh = 0.0
        self._name_scan_mtimes: dict[str, float] = {}
        self._focused: frozenset[str] = frozenset()
        self._focused_asked_at = 0.0
        self._input_focus_asked_at = 0.0
        self._exec_on_exit: tuple[str, list[str]] | None = None
        self._keys_shown = True
        self._hint_timer: Timer | None = None
        self._card_layout = False
        self._notes_open = True  # the notes key's choice; shown only in card layout too
        self._brief_cache = brief_cards.BriefCache()
        self._parts = row_parts.RowParts(
            self.config,
            lambda drain: self.run_worker(drain, group="project-names"),
            self._project_names_changed,
        )
        self._detached_channels: frozenset[str] = frozenset()
        self._resume_footer_shown = True
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
        for b in bindings.app_bindings(self.config):
            self._bindings.bind(b.key, b.action, b.description, show=b.show, priority=b.priority)

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
        return styles.css_variables(
            super().get_css_variables(), self.config.tui, self._uses_custom_active_row()
        )

    def _uses_custom_active_row(self) -> bool:
        return styles.uses_custom_active_row(
            self.config.tui.active_row_color, self.current_theme.dark
        )

    def _update_active_row_background(self) -> None:
        self.query_one("#main_table", ClickToActTable).set_class(
            self._uses_custom_active_row(), "-custom-active-row"
        )

    def compose(self) -> ComposeResult:
        yield UsageHeader()
        with ContentSwitcher(initial="inbox_content", id="content_switcher"):
            with Container(id="inbox_content"):
                yield Input(
                    placeholder="Search name, brief, message, cwd, branch...", id="history_filter"
                )
                yield InboxList(
                    self.config,
                    self._parts,
                    self._brief_cache,
                    self._undo_stack,
                    self._refresh_notifications,
                    id="inbox_list",
                )
                yield Static("", id="search_archive_label")
                # History resumes a session, replacing the terminal you are sitting in.
                # That wants picking a row and committing to it to stay separate.
                yield DataTable(id="history_table")
                yield DataTable(id="snoozed_table")
                yield DataTable(id="usage_table")
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

    def _refresh_usage(self) -> None:
        if not (self.config.usage.overall_pace or self._mode is view_modes.USAGE):
            return

        def load() -> None:
            self.call_from_thread(self._show_usage, usage_view.read_samples())

        self.run_worker(load, thread=True, group="usage", exclusive=True)

    def _show_usage(self, current: dict) -> None:
        usage_view.show(
            self.query_one(UsageHeader),
            self.query_one("#usage_table", DataTable) if self._mode is view_modes.USAGE else None,
            current,
            self.config.usage,
        )

    def on_mount(self) -> None:
        self.title = "lemonaid"
        self.sub_title = "attention inbox"
        self._refresh_usage()
        self.set_interval(self.config.usage.poll_seconds, self._refresh_usage)
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
        usage_view.setup_table(self.query_one("#usage_table", DataTable))
        self.query_one("#usage_table", DataTable).display = False
        self.query_one("#history_filter", Input).display = False

        self._refresh_notifications()
        self.query_one("#main_table", DataTable).focus()
        self.set_interval(self.config.tui.refresh_interval, self._refresh_notifications)
        # Transcript watchers: auto-dismiss, message updates, and exit detection
        watcher_hooks.start(self.config, self._brief_cache, self._set_detached_channels)
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
        return table_layout.wants_cards(
            self.size.width if width is None else width,
            self.size.height if height is None else height,
            current_position(self.config.tmux_session.scratch_position) == "left"
            if self._scratch_mode
            else None,
        )

    def _card_shape(self, extra_lines: int = 0) -> tuple[int, int]:
        if not self._card_layout:
            return 1, 1

        return table_layout.card_shape(
            self.size.height,
            self._notes_height(),
            self.query_one("#main_table", DataTable).row_count,
            extra_lines,
        )

    def _card_width(self) -> int:
        """Width the card's body column was stretched to, or 0 outside card mode.

        Keys off _card_layout rather than the current size: this decides how many
        cells a row has, and it must match the columns the tables were built with,
        which self.size disagrees with while a resize is being handled.
        """
        if not self._card_layout:
            return 0

        return table_layout.card_width(
            [c.width for c in self.query_one("#main_table", DataTable).columns.values()]
        )

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
                table_columns.fill_card_columns(
                    table, w - table_columns.vertical_scrollbar_width(table)
                )
            return

        hidden, flex = table_layout.column_plan(w)

        for table_id in ("#main_table", "#other_sources_table", "#history_table", "#snoozed_table"):
            table = self.query_one(table_id, DataTable)
            # The snoozed view's last column is a wake time, not a TTY, and is
            # the whole point of that view — never hide it.
            table_hidden = hidden - {layout.TTY_COLUMN} if table_id == "#snoozed_table" else hidden
            table_columns.hide_columns(table, table_hidden, self._column_labels(table_id))
            # Which columns to show keys off the terminal width, so the layout doesn't
            # reshuffle when a scrollbar appears; how wide to draw them keys off what
            # the table can actually paint into.
            table_columns.stretch_columns(
                table, flex, w - table_columns.vertical_scrollbar_width(table)
            )

    def _column_labels(self, table_id: str) -> dict[int, str]:
        return table_layout.column_labels(table_id, self.config.tui.card_fields)

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
            table.cell_padding = layout.CARD_CELL_PADDING
            table.show_header = False  # The card column has no label
            table.add_column("", width=20)  # The card body, stretched on resize
            return

        table.cell_padding = layout.COLUMN_CELL_PADDING
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
            width=layout.BACKEND_WIDTH
            + (layout.CONTEXT_WIDTH if self.config.tui.context_threshold else 0),
        )
        table.add_column("Name", width=24)
        table.add_column("Branch", width=12)
        table.add_column(
            table_layout.where_label(f"#{table.id}", self.config.tui.card_fields), width=16
        )
        table.add_column("Message", width=30)  # Stretched on resize
        # TTY holds "ttysNNN"; the snoozed view's wake label is "Fri 09:00".
        table.add_column("Wakes" if wake_column else "TTY", width=9 if wake_column else 7)

    def _active_table_id(self) -> str:
        return self._mode.table_id if self._mode else "#main_table"

    def _get_current_row_key(self) -> str | None:
        """Get the row key (notification ID) at current cursor."""
        return row_keys.notification_at_cursor(self.query_one(self._active_table_id(), DataTable))

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

    def _project_names_changed(self) -> None:
        if self._mode is view_modes.HISTORY:
            self._refresh_history()
        else:
            self._refresh_notifications()

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
        if self._mode is not None:
            self._wake_expired_snoozes()
            if self._mode is view_modes.SNOOZED:
                self._refresh_snoozed()
            return

        self._wake_expired_snoozes()
        self._refresh_session_names()

        inbox = self.query_one(InboxList)
        drawn = inbox.refresh_list(
            focused=self._focused_ttys(),
            env_filter=self.current_env if self.current_env != "unknown" else None,
            search_text=self._history_filter if self._search_mode else None,
            detached=self._detached_channels,
            cards=self._card_layout,
            width=self.size.width,
            height=self.size.height,
            card_width=self._card_width(),
            card_shape=self._card_shape,
            stay_on_unread=stay_on_unread,
        )
        self.set_class(bool(drawn.unread), "-unread")
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
            inbox_height = int(inbox.main.show_header) + sum(
                row.height for row in inbox.main.rows.values()
            )
            if drawn.other_shown:
                inbox_height += 1 + min(8, sum(row.height for row in inbox.other.rows.values()))
            available_height = (
                self.query_one("#inbox_content", Container).size.height
                - self.query_one("#history_filter", Input).outer_size.height
                - self.query_one("#status", Static).outer_size.height
                - self._notes_height()
            )
            show_archive = bool(archive_count) and (not drawn.other or drawn.other_shown)
            if show_archive:
                first_archive_row = next(iter(history_table.rows.values())).height
                show_archive = table_layout.archive_fits(
                    available_height,
                    inbox_height,
                    int(history_table.show_header),
                    first_archive_row,
                )
            self.set_class(show_archive, "-search-archive")
            history_table.display = show_archive
            archive_label.display = show_archive
            if not show_archive and self.focused is history_table:
                inbox.main.focus()
        else:
            self.set_class(False, "-search-archive")
            history_table.display = False
            archive_label.display = False

        position = current_position(self.config.tmux_session.scratch_position)
        dimension = "width" if position == "left" else "height"
        self._set_status(
            status_line.inbox_status(
                drawn.unread,
                drawn.read,
                self.current_env,
                (drawn.matches, archive_count) if self._search_mode else None,
                self._claude_patch_status == "unpatched",
                dimension
                if self._scratch_mode
                and is_follow_enabled()
                and size_has_drifted(position, getattr(self.size, dimension))
                else "",
                self.config.tui.keybindings.save_size,
                inbox.arrange_error,
            )
        )

    def action_toggle_fold(self) -> None:
        if self._mode is not None:
            return

        inbox = self.query_one(InboxList)
        inbox.fold_open = not inbox.fold_open
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

        if self._mode in (view_modes.SNOOZED, view_modes.USAGE):
            self._set_mode(self._mode, False)
            return

        if self._search_mode:
            self._stop_search()
            return

        if self._scratch_mode:
            self._hide_scratch_pane()
        else:
            self.exit()

    def _toggle_mode(self, mode: view_modes.Mode) -> None:
        leaving = self._mode
        if leaving is not None:
            self._set_mode(leaving, False)
        if leaving is not mode:
            self._set_mode(mode, True)

    def action_toggle_history(self) -> None:
        self._toggle_mode(view_modes.HISTORY)

    def action_toggle_usage(self) -> None:
        self._toggle_mode(view_modes.USAGE)

    def action_toggle_snoozed(self) -> None:
        self._toggle_mode(view_modes.SNOOZED)

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
        self.push_screen(HelpScreen(bindings.help_keys(self.config), wide=not self._card_layout))

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
        bindings.set_footer(self._bindings.key_to_bindings, action, show=show, label=label)

    def _set_mode(self, mode: view_modes.Mode, enabled: bool) -> None:
        if enabled and self._search_mode:
            self._stop_search(refresh=False)
        self._mode = mode if enabled else None
        if mode is view_modes.HISTORY:
            self._history_filter = ""

        for action in mode.hidden_actions:
            self._set_binding_footer(action, show=not enabled)
        for action in mode.shown_actions:
            self._set_binding_footer(action, show=enabled)
        self._set_binding_footer(
            mode.toggle_action,
            label=f"Exit {mode.toggle_label}" if enabled else mode.toggle_label,
        )
        if mode.select_label:
            self._set_binding_footer("select", label=mode.select_label if enabled else "Switch")
            if enabled and self._resume_footer_shown:
                self._resume_footer_shown = False
                self._set_binding_footer("resume_detached", show=False)
        self.refresh_bindings()
        if mode is view_modes.HISTORY:
            self.set_class(enabled, "-history")

        inbox = self.query_one(InboxList)
        table = self.query_one(mode.table_id, DataTable)
        history_filter = self.query_one("#history_filter", Input)
        if not enabled:
            self.sub_title = "attention inbox"
            table.display = False
            if mode is view_modes.HISTORY:
                history_filter.display = False
            inbox.display = True
            self._refresh_notifications()
            inbox.main.focus()
            return

        self.sub_title = mode.sub_title
        inbox.display = False
        self.query_one("#search_archive_label", Static).display = False
        table.display = True
        if mode is view_modes.HISTORY:
            history_filter.display = False
            history_filter.value = ""
            self._refresh_history()
        elif mode is view_modes.SNOOZED:
            self._refresh_snoozed()
        else:
            self._refresh_usage()
        table.focus()

    def _set_history_mode(self, enabled: bool) -> None:
        self._set_mode(view_modes.HISTORY, enabled)

    def _refresh_history(self) -> int:
        history_table = self.query_one("#history_table", DataTable)
        history_rows.fill(
            history_table,
            history_rows.load(
                self._history_filter,
                self.current_env if self.current_env != "unknown" else None,
                self._search_mode,
            ),
            self.config,
            self._parts,
            self._brief_cache,
            self._card_width(),
            self._card_shape(),
        )
        count = history_table.row_count
        if not self._search_mode:
            self._set_status(f"{count} archived session{'s' if count != 1 else ''}")
        return count

    def _refresh_snoozed(self) -> None:
        snoozed_table = self.query_one("#snoozed_table", DataTable)
        snoozed_rows.fill(
            snoozed_table,
            self.config,
            self._parts,
            self._brief_cache,
            self._card_width(),
            self._card_shape(),
        )
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
        self.notify(f"{entry.description} — press {bindings.undo_key(self.config)} to undo")

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
        if (notification_id := row_keys.key_id(row_key)) is None:
            return

        with db.connect() as conn:
            notification = db.get(conn, notification_id)

        if notification is None:
            self._show_error("That session is gone", "Its row was removed from the inbox.")
            return

        if not inbox_list.can_resume_detached(notification, self.config):
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
        if not (self._mode is view_modes.HISTORY or self._search_mode):
            return
        self._resume_session(copy_only=True)

    def action_tmux_resume(self) -> None:
        """Spawn a new tmux session around the selected history entry."""
        if not (self._mode is view_modes.HISTORY or self._search_mode):
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
        if self._mode is not view_modes.HISTORY and not self._search_mode:
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
            elif self._mode is view_modes.HISTORY:
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
            and row_keys.key_id(table.coordinate_to_cell_key(Coordinate(next_row, 0))[0]) is None
        ):
            next_row += direction  # past a group header
        if not 0 <= next_row < table.row_count:
            return

        key, _ = table.coordinate_to_cell_key(Coordinate(next_row, 0))
        if (notification_id := row_keys.key_id(key)) is None:
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
                if (found := row_keys.key_id(key)) is not None
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
        if (self._mode is view_modes.HISTORY or self._search_mode) and table.id == "history_table":
            self._resume_session()
        elif self._mode is view_modes.SNOOZED and table.id == "snoozed_table":
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

    def action_mark_read(self) -> None:
        table = self._focused_table()
        if table.row_count == 0:
            return

        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        if (notification_id := row_keys.key_id(row_key)) is not None:
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
        if (notification_id := row_keys.key_id(row_key)) is None:
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
        if (notification_id := row_keys.key_id(row_key)) is None:
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
        self.notify(f"{entry.description} — press {bindings.undo_key(self.config)} to undo")

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
                found = row_keys.key_id(key)
                notification = db.get(conn, found) if found is not None else None
                channels.append(notification.channel if notification else "")

        return channels

    def _selected_channel(self) -> str | None:
        """The channel of the row under the cursor, in the main list only."""
        if self._mode is not None:
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
        channel = self._selected_channel()
        if channel and inbox_groups.move_pin(
            self.query_one(InboxList), channel, self._row_channels(), offset
        ):
            self._select_channel(channel)

    def _selected_group(self) -> "groups.store.Group | None":
        """The group whose header is under the cursor, in the main list only."""
        return None if self._mode is not None else self.query_one(InboxList).selected_group()

    def action_toggle_group(self) -> None:
        """Open or collapse the group whose header or lemon is under the cursor."""
        if self._mode is None:
            self.query_one(InboxList).toggle_group_at_cursor()

    def _move_pin_or_group(self, offset: int) -> None:
        if group := self._selected_group():
            if refused := self.query_one(InboxList).move_group(group, offset):
                self.notify(refused)
        else:
            self._move_pin(offset)

    def action_move_pin_up(self) -> None:
        self._move_pin_or_group(-1)

    def action_move_pin_down(self) -> None:
        self._move_pin_or_group(1)

    def _selected_lemon(self) -> "tuple[db.Notification, str] | None":
        """The row under the cursor in the main list and its Lemon-ID, when it has a brief."""
        channel = self._selected_channel()
        if not channel or self._brief_target is not None:
            return None

        with db.connect() as conn:
            notification = db.get(conn, int(self._get_current_row_key() or 0))
            try:
                lemon_id = brief.lemon.lemon_id(conn, channel)
            except (LookupError, ValueError, brief.store.ChangedUnderneath):
                self.notify("This session has no brief, so it can't be in a group")
                return None

        return (notification, lemon_id) if notification else None

    def action_group_tree(self) -> None:
        if found := self._selected_lemon():
            inbox_groups.group_tree(self.query_one(InboxList), *found)

    def action_group_add(self) -> None:
        if found := self._selected_lemon():
            inbox_groups.group_add(self.query_one(InboxList), *found)

    def action_group_remove(self) -> None:
        """Take the lemon out of the group it's drawn in; on a header, delete the group."""
        inbox = self.query_one(InboxList)
        if group := self._selected_group():
            inbox_groups.delete_group(inbox, group)
            return

        group_id = sections.row_group_id(row_keys.at_cursor(inbox.main) or "")
        found = self._selected_lemon() if group_id is not None else None
        if group_id is not None and found is not None:
            inbox_groups.group_remove(inbox, group_id, *found)

    def _select_channel(self, channel: str) -> None:
        """Put the cursor back on a channel after the list around it moved."""
        table = self.query_one(self._active_table_id(), DataTable)
        for index, c in enumerate(self._row_channels()):
            if c == channel and index < table.row_count:
                table.move_cursor(row=index)
                return

    def action_snooze(self) -> None:
        """Snooze the selected session out of the inbox for a chosen duration."""
        if self._mode is not None:
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
            self.notify(f"{entry.description} — press {bindings.undo_key(self.config)} to undo")

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
        entry = self._undo_stack.peek()
        if entry is None:
            self.notify("Nothing to undo", severity="information")
            return

        try:
            with db.connect() as conn:
                unwritten = (
                    groups.editing.undo(conn, entry.group_change) if entry.group_change else []
                )
                restored = undo.restore(conn, entry)
        except groups.store.GroupError as error:
            # A name taken since can be freed again; a group changed since stays changed.
            if isinstance(error, groups.snapshot.Changed):
                self._undo_stack.pop()
            self.notify(f"Can't undo {entry.description}: {error}", severity="warning")
            return

        self._undo_stack.pop()
        for path in unwritten:
            self.notify(f"Couldn't update the Groups: line in {path}", severity="warning")

        _log.info("undo: %s (%d rows)", entry.action, restored)
        self._retarget_brief()
        if self._mode is view_modes.HISTORY:
            self._refresh_history()
        elif self._mode is view_modes.SNOOZED:
            self._refresh_snoozed()
        else:
            self._refresh_notifications()

        self.notify(f"Undid: {entry.description}")

    def action_rename(self) -> None:
        """Rename the selected session, or the group whose header is under the cursor."""
        if self._brief_target is None and (group := self._selected_group()):
            inbox_groups.rename(self.query_one(InboxList), group, "Rename Group")
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
            if self._mode is view_modes.HISTORY:
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
            and self._mode is None
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
        inbox = self.query_one(InboxList)
        row = inbox.earliest_unread_row()
        if row is None:
            self.notify("No unread notifications", severity="information")
            return

        inbox.main.move_cursor(row=row)
        inbox.main.action_select_cursor()

    def action_jump_to_number(self, digit: str) -> None:
        """Switch to the numbered session, as though it had been selected by hand.

        Inbox only. In history Enter resumes rather than switches, and a resume
        is too costly to hang on a single unconfirmed keystroke. The lower table
        is unnumbered for the same reason in reverse: nothing there can be
        switched to at all.
        """
        inbox = self.query_one(InboxList)
        if self._mode is view_modes.HISTORY or not inbox.display:
            return

        row = inbox.lemon_row(JUMP_DIGITS.find(digit))
        if row is not None:
            inbox.main.move_cursor(row=row)
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

    def _set_detached_channels(self, channels: set[str]) -> None:
        self._detached_channels = frozenset(channels)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if not self.is_running:
            return  # queued highlights can arrive after shutdown removes the tables

        if event.data_table.id == "main_table":
            self.query_one(InboxList).mark_header(
                str(event.row_key.value) if event.row_key else "", self._card_width()
            )
        self._refresh_resume_binding()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._activate_row(event.data_table.id, event.row_key)

    def on_click_to_act_table_selected_row_clicked(
        self, event: ClickToActTable.SelectedRowClicked
    ) -> None:
        # Keep a click to stay in scratch only when this row still names the
        # pane behind it. An external jump can leave the cursor on another lemon.
        if event.data_table.id == "main_table" and self.has_class("-input-active"):
            with db.connect() as conn:
                found = row_keys.key_id(event.row_key)
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
            self.query_one(InboxList).toggle_group(group_id)
            return

        if (notification_id := row_keys.key_id(row_key)) is None:
            return

        with db.connect() as conn:
            notification = db.get(conn, notification_id)

        if notification:
            self._switch_to_notification(notification)


def main() -> None:
    set_terminal_title("lma")
    app = LemonaidApp()
    app.run()
