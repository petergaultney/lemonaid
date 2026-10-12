"""Main Lemonaid TUI application."""

import os
import threading
import time
import typing as ty
from pathlib import Path

from textual import events
from textual.app import App, ComposeResult
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import ContentSwitcher, DataTable, Footer, Input, Static
from textual.widgets.data_table import RowKey

from ... import brief, groups
from ...claude import patch_status
from ...claude.patcher import find_binary
from ...config import load_config
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
    sections,
    undo,
)
from . import (
    bindings,
    brief_cards,
    claude_patch,
    edit_dialogs,
    focus,
    history_resume,
    inbox_draw,
    inbox_edits,
    inbox_groups,
    inbox_switch,
    row_keys,
    row_parts,
    session_names,
    status_line,
    styles,
    table_nav,
    usage_view,
    utils,
    view_modes,
    watcher_hooks,
)
from .brief_pane import BriefPane
from .error_screen import ErrorScreen
from .help_screen import HelpScreen
from .history_table import HistoryTable
from .inbox_content import InboxContent
from .inbox_list import InboxList
from .notes import NotesPanel
from .snoozed_table import SnoozedTable
from .table import ClickToActTable
from .usage_view import UsageHeader
from .utils import (
    JUMP_DIGITS,
    set_terminal_title,
)

_NAME_REFRESH_SECONDS = 20  # transcript re-scan cadence for session-name upgrades
_KEY_HINT_SECONDS = 10  # how long the footer's key hints stay up before yielding the row

_log = get_logger("tui")

_W = ty.TypeVar("_W", bound=Widget)


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
        self._undo_stack = undo.Stack()
        self._last_name_refresh = 0.0
        self._name_scan_mtimes: dict[str, float] = {}
        self._attention = focus.Probe()
        self._exec_on_exit: tuple[str, list[str]] | None = None
        self._keys_shown = True
        self._hint_timer: Timer | None = None
        self._brief_cache = brief_cards.BriefCache()
        self._parts = row_parts.RowParts(
            self.config,
            lambda drain: self.run_worker(drain, group="project-names"),
            self._project_names_changed,
        )
        self._detached_channels: frozenset[str] = frozenset()
        self._resume_footer_shown = True
        # Enable ANSI colors for terminal transparency support
        if self.config.tui.transparent:
            self.ansi_color = True
            self.dark = True  # Use dark theme as base

    def _setup_keybindings(self) -> None:
        for b in bindings.app_bindings(self.config):
            self._bindings.bind(b.key, b.action, b.description, show=b.show, priority=b.priority)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        return bindings.permitted(
            action,
            brief_shown=self._brief_target is not None,
            overlaid=isinstance(self.screen, ModalScreen) or isinstance(self.focused, Input),
            searching=self._search_mode,
            history_focused=lambda: self.focused is self.query_one("#history_table", DataTable),
            resume_available=lambda: (
                self._selected_channel() in self._detached_channels or self._brief_local()
            ),
        )

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
        lists = row_parts.Lists(self.config, self._parts, self._brief_cache, self._undo_stack)
        yield UsageHeader()
        with ContentSwitcher(initial="inbox_content", id="content_switcher"):
            yield InboxContent(
                self.config,
                self._sidebar,
                Input(
                    placeholder="Search name, brief, message, cwd, branch...", id="history_filter"
                ),
                InboxList(lists, self._refresh_notifications, id="inbox_list"),
                Static("", id="search_archive_label"),
                # History resumes a session, replacing the terminal you are sitting in.
                # That wants picking a row and committing to it to stay separate.
                HistoryTable(
                    lists,
                    self._back_to_inbox,
                    self._exec_here,
                    self._refresh_notifications,
                    id="history_table",
                ),
                SnoozedTable(lists, self._refresh_snoozed, id="snoozed_table"),
                DataTable(id="usage_table"),
                *(
                    []
                    if self.config.tui.notes is None
                    else [NotesPanel(self.config.tui.notes, id="notes")]
                ),
                Static("", id="status"),
                id="inbox_content",
            )
            yield BriefPane(
                self.config,
                self._get_current_row_key,
                self._attention.note,
                self._brief_closed,
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

        self._content.build_tables(
            self._content.wants_cards(self.size.width, self.size.height), history_marker=False
        )

        usage_view.setup_table(self.query_one("#usage_table", DataTable))

        self._refresh_notifications()
        self.query_one("#main_table", DataTable).focus()
        self.set_interval(self.config.tui.refresh_interval, self._refresh_notifications)
        # Transcript watchers: auto-dismiss, message updates, and exit detection
        watcher_hooks.start(self.config, self._brief_cache, self._set_detached_channels)
        self.call_later(self._check_claude_patch)
        self.call_later(self._refresh_skills)
        self.call_later(lambda: self._content.stretch(self.size.width))
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
        self._attention.input_at = 0.0
        self._refresh_notifications()

    def _update_input_indicator(self) -> None:
        pane = os.environ.get("TMUX_PANE") if self._scratch_mode else None
        if pane and (active := self._attention.has_keys(pane)) is not None:
            self.set_class(active, "-input-active")
            self.set_class(not active, "-input-inactive")

    def on_resize(self, event: events.Resize) -> None:
        # self.size still reports the old width while this event is being handled,
        # so every decision here keys off the size the event carries.
        width = event.size.width
        cards = self._content.wants_cards(width, event.size.height)
        # Cards and columns are different column sets, so crossing that threshold
        # rebuilds the tables rather than just restretching them.
        crossed = cards != self._content.cards
        _log.info(
            "resize %sx%s -> %s%s",
            width,
            event.size.height,
            "cards" if cards else "columns",
            " (changed)" if crossed else "",
        )
        if crossed:
            self._content.cards = cards
            self._content.build_tables(cards, history_marker=True)

        # Stretch before refilling: a card truncates to the width its column was
        # stretched to, which is not the placeholder width table_setup gave it.
        self._content.stretch(width)
        if crossed:
            self._refresh_notifications()

    def _sidebar(self) -> bool | None:
        if not self._scratch_mode:
            return None

        return current_position(self.config.tmux_session.scratch_position) == "left"

    @property
    def _content(self) -> InboxContent:
        return self.query_one(InboxContent)

    def _the(self, widget: type[_W]) -> _W | None:
        """The one *widget*, or None before the screen is up or after it is torn down."""
        found = self.query(widget) if self._screen_stack else None
        return found.first() if found else None

    @property
    def _mode(self) -> view_modes.Mode | None:
        content = self._the(InboxContent)
        return content.mode if content else None

    @property
    def _search_mode(self) -> bool:
        content = self._the(InboxContent)
        return bool(content and content.searching)

    @property
    def _history_filter(self) -> str:
        return self._content.filter_text

    def _card_width(self) -> int:
        return self._content.card_width()

    def _card_shape(self, extra_lines: int = 0) -> tuple[int, int]:
        return self._content.card_shape(extra_lines)

    def _active_table_id(self) -> str:
        return f"#{self._content.active_table().id}"

    def _get_current_row_key(self) -> str | None:
        """Get the row key (notification ID) at current cursor."""
        return row_keys.notification_at_cursor(self.query_one(self._active_table_id(), DataTable))

    def _get_current_row_index(self) -> int:
        """Get the current cursor row index."""
        table = self.query_one("#main_table", DataTable)
        return table.cursor_coordinate.row

    def _project_names_changed(self) -> None:
        if self._mode is view_modes.HISTORY:
            self._refresh_history()
        else:
            self._refresh_notifications()

    def _refresh_notifications(self, *, stay_on_unread: bool = False) -> None:
        if not self.is_running:
            return  # a timer tick during shutdown, while the screen's widgets are being removed

        self._update_input_indicator()
        self._content.refresh_notes()
        if self._brief_target is not None:
            self._wake_expired_snoozes()
            self.query_one(BriefPane).update_brief(
                self._brief_target, self.query_one(BriefPane).unread()
            )
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

        inbox = self._content.inbox
        drawn = inbox.refresh_list(
            focused=self._attention.ttys(),
            env_filter=self.current_env if self.current_env != "unknown" else None,
            search_text=self._history_filter if self._search_mode else None,
            detached=self._detached_channels,
            cards=self._content.cards,
            width=self.size.width,
            height=self.size.height,
            card_width=self._card_width(),
            card_shape=self._card_shape,
            stay_on_unread=stay_on_unread,
        )
        self.set_class(bool(drawn.unread), "-unread")
        self._refresh_resume_binding()

        archive_count = 0
        if self._search_mode:
            archive_count = self._refresh_history()
            show_archive = self._content.place_archive(drawn, archive_count)
            self.set_class(show_archive, "-search-archive")
            if not show_archive and self.focused is self._content.history:
                inbox.main.focus()
        else:
            self.set_class(False, "-search-archive")
            self._content.hide_archive()

        position = current_position(self.config.tmux_session.scratch_position)
        dimension = "width" if position == "left" else "height"
        self._content.set_status(
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
                inbox.arrangement.error,
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
            self.query_one(BriefPane).dismiss()
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
        self.push_screen(HelpScreen(bindings.help_keys(self.config), wide=not self._content.cards))

    def action_toggle_notes(self) -> None:
        self._content.notes_open = not self._content.notes_open
        self._refresh_notifications()  # refreshes the notes, then sizes the cards to them

    def on_notes_panel_resized(self, _message: NotesPanel.Resized) -> None:
        self._refresh_notifications()

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

    def _refresh_resume_binding(self) -> None:
        resume_footer_shown = (
            self._selected_channel() in self._detached_channels or self._brief_local()
        )
        if resume_footer_shown != self._resume_footer_shown:
            self._resume_footer_shown = resume_footer_shown
            self._set_binding_footer("resume_detached", show=resume_footer_shown)
            self.refresh_bindings()

    def _refresh_session_names(self) -> None:
        """Pull newly-available backend titles into the inbox.

        Throttled and run off the event loop: resolving a title reads a
        transcript, which is too slow to do synchronously on every tick.
        """
        now = time.time()
        if now - self._last_name_refresh < _NAME_REFRESH_SECONDS:
            return

        def scan() -> None:
            if session_names.upgrade(self._name_scan_mtimes):
                self.call_from_thread(self._refresh_notifications)

        self._last_name_refresh = now
        threading.Thread(target=scan, daemon=True).start()

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
        self._content.show_mode(mode, enabled)

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

        self.sub_title = mode.sub_title if enabled else "attention inbox"
        if not enabled:
            self._refresh_notifications()
            self._content.inbox.main.focus()
        elif mode is view_modes.HISTORY:
            self._refresh_history()
        elif mode is view_modes.SNOOZED:
            self._refresh_snoozed()
        else:
            self._refresh_usage()
        if enabled:
            self.query_one(mode.table_id, DataTable).focus()

    def _set_history_mode(self, enabled: bool) -> None:
        self._set_mode(view_modes.HISTORY, enabled)

    def _refresh_history(self) -> int:
        return self._content.refill_history(
            self.current_env if self.current_env != "unknown" else None
        )

    def _refresh_snoozed(self) -> None:
        self._content.refill_snoozed()

    def _undoable(self, entry: undo.Entry) -> None:
        self._undo_stack.push(entry)
        self.notify(f"{entry.description} — press {bindings.undo_key(self.config)} to undo")

    def _wake_selected(self) -> None:
        self.query_one(SnoozedTable).wake()

    def _show_error(self, title: str, message: str) -> None:
        _log.warning("%s: %s", title, message)
        self.push_screen(ErrorScreen(title, message))

    def _switch_to_notification(self, notification: db.Notification) -> bool:
        if not inbox_switch.switch_to(self, notification, self.config, self._archive_notification):
            return False

        # We already know where a successful in-app switch went. Reflect that
        # immediately instead of waiting for the next tmux poll; the periodic
        # lookup remains authoritative for switches made outside lemonaid.
        tty = notification.metadata.get("tty")
        if isinstance(tty, str) and tty:
            self._attention.note(tty)
            self._refresh_notifications()

        # In scratch mode the pane hides after navigation, unless follow
        # mode is on - there the hook re-shows it in the target window.
        if self._scratch_mode and not is_follow_enabled():
            self._hide_scratch_pane()

        return True

    def action_resume_detached(self) -> None:
        """Resume the selected row only when its pane is known to be gone."""
        if self._selected_channel() not in self._detached_channels and not self._brief_local():
            return

        table = self.query_one("#main_table", DataTable)
        if (notification_id := row_keys.key_id(row_keys.at_row(table, table.cursor_row))) is None:
            return

        with db.connect() as conn:
            notification = db.get(conn, notification_id)
        if notification is None:
            self._show_error("That session is gone", "Its row was removed from the inbox.")
        elif not inbox_draw.can_resume_detached(notification, self.config):
            inbox_switch.resume_unavailable(self)
        else:
            self._switch_to_notification(notification)

    def _back_to_inbox(self, notification: db.Notification) -> None:
        """A session resumed from history that never stopped: show it in the inbox."""
        if self._search_mode:
            self._stop_search()
        else:
            self._set_history_mode(False)
        self._refresh_notifications()
        self.notify(f"{notification.name or notification.channel} is running - back in the inbox")
        self._switch_to_notification(notification)

    def _exec_here(self, cwd: str, argv: list[str]) -> None:
        self._exec_on_exit = (cwd, argv)
        self.exit()

    def _resume_session(self, *, copy_only: bool = False) -> None:
        """Resume the selected history session."""
        mode: history_resume.Mode = (
            "copy" if copy_only else ("tmux" if self._scratch_mode else "exec")
        )
        here_tty = (
            os.ttyname(0) if mode == "exec" and navigation.is_inside_tmux() and os.isatty(0) else ""
        )
        done = self.query_one(HistoryTable).resume(mode, here_tty)
        if done and done.kind == "started" and not is_follow_enabled():
            self._hide_scratch_pane()

    def action_copy_resume(self) -> None:
        """Copy the resume command for the selected history session."""
        if self._mode is view_modes.HISTORY or self._search_mode:
            self._resume_session(copy_only=True)

    def action_tmux_resume(self) -> None:
        """Spawn a new tmux session around the selected history entry."""
        if self._mode is view_modes.HISTORY or self._search_mode:
            self.query_one(HistoryTable).resume_in_new_session()

    def action_filter_history(self) -> None:
        """Search inbox rows, or focus the existing history filter."""
        if self._mode is not view_modes.HISTORY and not self._search_mode:
            self._content.start_search()
            self.sub_title = "search"
            self.set_class(True, "-search")
            self._refresh_notifications()
        self._content.open_search_box()

    def _stop_search(self, *, refresh: bool = True) -> None:
        self._content.stop_search()
        self.sub_title = "attention inbox"
        self.set_class(False, "-search")
        if refresh:
            self._refresh_notifications()
            self._content.inbox.main.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "history_filter":
            self._content.filter_text = event.value
            if self._search_mode:
                self._refresh_notifications()
            elif self._mode is view_modes.HISTORY:
                self._refresh_history()

    def on_key(self, event: events.Key) -> None:
        """Handle special keys in the filter input."""
        if event.key == "f12" and self._scratch_mode:
            event.prevent_default()
            event.stop()
            if not self.query_one(BriefPane).switching:  # a switch in flight wakes it twice
                self.query_one(BriefPane).sync()
            # The follow hook sends it after moving this pane, so the focused pane has changed.
            self._attention.focused_at = 0.0
            self._refresh_notifications()
            return

        if not (isinstance(self.focused, Input) and self.focused.id == "history_filter"):
            return

        # Down/Enter: keep filter active, move focus to matching rows.
        if event.key in ("down", "enter"):
            event.prevent_default()
            event.stop()
            table_nav.into_results(*self._stacked_tables(), self._search_mode)
            return

        # Escape: clear filter, hide it, focus table
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            if self._search_mode:
                self._stop_search()
                return

            self._content.clear_history_filter()
            self._refresh_history()
            self._content.history.focus()

    def _focused_table(self) -> DataTable:
        focused = self.focused
        if isinstance(focused, DataTable):
            return focused
        return self.query_one("#main_table", DataTable)

    def _stacked_tables(self) -> tuple[DataTable, DataTable, DataTable]:
        return self._content.stacked()

    def action_cursor_up(self) -> None:
        if self._brief_target is not None:
            self.query_one(BriefPane).navigate(-1, self._detached_channels)
        else:
            main, other, _ = self._stacked_tables()
            table_nav.up(self._focused_table(), main, other, self._search_mode)

    def action_cursor_down(self) -> None:
        if self._brief_target is not None:
            self.query_one(BriefPane).navigate(1, self._detached_channels)
        else:
            table_nav.down(self._focused_table(), *self._stacked_tables(), self._search_mode)

    def action_cursor_first(self) -> None:
        """Move to the top row: the main table's first, pins included."""
        table_nav.to_end(self._focused_table(), self.query_one(InboxList).main, last=False)

    def action_cursor_last(self) -> None:
        """Move to the bottom row of the focused table; in the inbox, a folded group stays folded."""
        table_nav.to_end(self._focused_table(), self.query_one(InboxList).main, last=True)

    def _brief_closed(self) -> None:
        self._show_keys(self._keys_shown)
        self._refresh_notifications()

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
            self.query_one(BriefPane).show(self._brief_target, self.query_one(BriefPane).unread())
            return

        self._refresh_notifications()

    def _focused_row_id(self) -> int | None:
        table = self._focused_table()
        return (
            row_keys.key_id(row_keys.at_row(table, table.cursor_row)) if table.row_count else None
        )

    def action_mark_read(self) -> None:
        if (found := self._focused_row_id()) is not None and (
            entry := inbox_edits.mark_read(found)
        ):
            self._undo_stack.push(entry)
            self._refresh_notifications(stay_on_unread=True)  # keep the cursor on unread rows

    def action_mark_unread(self) -> None:
        if (found := self._focused_row_id()) is not None and (
            entry := inbox_edits.mark_unread(found)
        ):
            self._undo_stack.push(entry)
            self._refresh_notifications()

    def action_archive(self) -> None:
        """Archive the selected session (removes from active list)."""
        if (found := self._focused_row_id()) is not None:
            self._archive_notification(found)

    def _archive_notification(self, notification_id: int) -> None:
        if entry := inbox_edits.archive(notification_id):
            self._refresh_notifications()
            self._undoable(entry)

    def _row_channels(self) -> list[str]:
        return row_keys.channels(self.query_one(self._active_table_id(), DataTable))

    def _selected_channel(self) -> str | None:
        """The channel of the row under the cursor, in the main list only."""
        found = None if self._mode is not None else self._selected_notification()
        return found.channel if found else None

    def action_pin(self) -> None:
        if channel := self._selected_channel():
            inbox_groups.toggle_pin(self.query_one(InboxList), channel)

    def _move_pin(self, offset: int) -> None:
        channel = self._selected_channel()
        if channel and inbox_groups.move_pin(
            self.query_one(InboxList), channel, self._row_channels(), offset
        ):
            self._select_channel(channel)

    def _selected_group(self) -> "groups.store.Group | None":
        """The group whose header is under the cursor, in the main list only."""
        return (
            None
            if self._mode is not None
            else inbox_groups.selected_group(self.query_one(InboxList))
        )

    def action_toggle_group(self) -> None:
        """Open or collapse the group whose header or lemon is under the cursor."""
        if self._mode is None:
            inbox_groups.toggle_group_at_cursor(self.query_one(InboxList))

    def _move_pin_or_group(self, offset: int) -> None:
        if group := self._selected_group():
            if refused := inbox_groups.move_group(self.query_one(InboxList), group, offset):
                self.notify(refused)
        else:
            self._move_pin(offset)

    def action_move_pin_up(self) -> None:
        self._move_pin_or_group(-1)

    def action_move_pin_down(self) -> None:
        self._move_pin_or_group(1)

    def _selected_lemon(self) -> "tuple[db.Notification, str] | None":
        """The row under the cursor in the main list and its Lemon-ID, when it has a brief."""
        if self._mode is not None or self._brief_target is not None:
            return None

        found = self._selected_notification()
        return inbox_groups.lemon(self.query_one(InboxList), found) if found else None

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
        row_keys.select_channel(self.query_one(self._active_table_id(), DataTable), channel)

    def _selected_notification(self) -> db.Notification | None:
        return row_keys.notification(self._get_current_row_key())

    def action_snooze(self) -> None:
        """Snooze the selected session out of the inbox for a chosen duration."""
        if self._mode is None and (notification := self._selected_notification()):
            edit_dialogs.snooze(self, notification, self.config, self._snoozed)

    def _snoozed(self, entry: undo.Entry) -> None:
        self._refresh_notifications()
        self._undoable(entry)

    def action_undo(self) -> None:
        """Reverse the most recent undoable inbox change."""
        if (entry := self._undo_stack.peek()) is None:
            self.notify("Nothing to undo", severity="information")
            return

        unwritten = inbox_edits.undo_latest(self._undo_stack, entry)
        if isinstance(unwritten, str):
            self.notify(unwritten, severity="warning")
            return

        for path in unwritten:
            self.notify(f"Couldn't update the Groups: line in {path}", severity="warning")
        self._retarget_brief()
        self._refresh_view()
        self.notify(f"Undid: {entry.description}")

    def _refresh_view(self) -> None:
        if self._mode is view_modes.HISTORY:
            self._refresh_history()
        elif self._mode is view_modes.SNOOZED:
            self._refresh_snoozed()
        else:
            self._refresh_notifications()

    def action_rename(self) -> None:
        """Rename the selected session, or the group whose header is under the cursor."""
        if self._brief_target is None and (group := self._selected_group()):
            inbox_groups.rename(self.query_one(InboxList), group, "Rename Group")
            return

        if notification := self._selected_notification():
            edit_dialogs.rename(self, notification, self._renamed)

    def _renamed(self, entry: undo.Entry) -> None:
        self._undo_stack.push(entry)
        if self._mode is view_modes.HISTORY:
            self._refresh_history()
        else:
            self._retarget_brief()
            self._refresh_notifications()

    def _retarget_brief(self) -> None:
        if self._brief_target is not None and (notification := self._selected_notification()):
            self.query_one(BriefPane).retarget(notification)

    @property
    def _brief_target(self) -> brief.target.Target | None:
        """The brief shown in place of the inbox, if one is."""
        pane = self._the(BriefPane)
        return pane.target if pane else None

    def _set_brief_view(self, found: brief.target.Target | None) -> None:
        self.query_one(BriefPane).set_view(found)

    def action_brief(self) -> None:
        """Show a brief in the sidebar, or use a popup if it is unavailable."""
        if self._brief_target is not None:
            self.action_quit()
            return

        if not (key := self._get_current_row_key()):
            return  # a group header, or an empty list

        notification = row_keys.notification(key)
        target = (
            self.query_one(BriefPane).target_for(notification, fresh=True) if notification else None
        )
        if not target or not (target.attached or target.dirs):
            self._show_error(
                "No brief to show", "No brief or directory is recorded for this session."
            )
            return

        if not (
            self._scratch_mode
            and is_follow_enabled()
            and self._mode is None
            and current_position(self.config.tmux_session.scratch_position) == "left"
            and self.query_one(BriefPane).toggle(target)
        ):
            brief.popup.open_popup(target)

    def action_jump_unread(self) -> None:
        """Jump directly to the earliest unread session."""
        if not self._content.inbox.jump_unread():
            self.notify("No unread notifications", severity="information")

    def action_jump_to_number(self, digit: str) -> None:
        """Switch to the numbered session, as though it had been selected by hand.

        Inbox only. In history Enter resumes rather than switches, and a resume
        is too costly to hang on a single unconfirmed keystroke. The lower table
        is unnumbered for the same reason in reverse: nothing there can be
        switched to at all.
        """
        inbox = self._content.inbox
        if (
            self._mode is not view_modes.HISTORY
            and inbox.display
            and inbox.move_to_lemon(JUMP_DIGITS.find(digit))
        ):
            self.action_select()

    def action_patch_claude(self) -> None:
        """Patch Claude Code binary for faster notifications."""
        if self._claude_binary and self._claude_patch_status == "unpatched":
            self._claude_patch_status = claude_patch.apply(self, self._claude_binary)
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

    def _brief_local(self) -> bool:
        """Whether the brief shown stays here because its lemon's terminal can't come up."""
        pane = self._the(BriefPane)
        return bool(pane and pane.local)

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
            inbox_groups.toggle_group(self.query_one(InboxList), group_id)
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
