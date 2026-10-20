"""The brief view as the inbox shows it: which brief is up, and browsing from row to row.

Browsing redraws at once and switches the main pane behind it; only the
newest selection is switched to once a switch finishes.
"""

import os
from collections import abc

from textual.widgets import ContentSwitcher, DataTable

from .... import brief
from ....config import Config
from ....log import get_logger
from ... import db, emoji
from ..tables import row_keys
from .brief_view import BriefView

_log = get_logger("tui")

_Switch = tuple[db.Notification, brief.target.Target]


class BriefPane(BriefView):
    def __init__(
        self,
        config: Config,
        row_key: abc.Callable[[], str | None],
        focused: abc.Callable[[str], None],
        closed: abc.Callable[[], None],
        **kwargs: object,
    ) -> None:
        """`row_key` names the row under the inbox cursor, whose brief is shown;
        `focused` hears the tty the main pane switched to; `closed` redraws the
        inbox once it is back.
        """
        super().__init__(
            brief.pr.configured(config.brief.pr_state),
            config.brief.vaults,
            config.tui.keybindings,
            config.tui.mid_turn_working,
            config.places.roots,
            config.tui.project_name_colors,
            **kwargs,
        )
        self._config = config
        self._cursor_key = row_key
        self._note_focus = focused
        self._inbox_back = closed
        self.target: brief.target.Target | None = None  # the brief shown, while one is
        self.local = False  # shown here only: its lemon's terminal can't be switched to
        # Resolving a target asks tmux twice, which is most of an arrow's cost.
        self.targets: dict[int, brief.target.Target] = {}
        self.switch_pending: _Switch | None = None
        self._switching = False
        self._saved_focus = "main_table"
        self._saved_subtitle = "attention inbox"

    @property
    def switching(self) -> bool:
        return self._switching

    def open(self, found: brief.target.Target, unread: abc.Callable[[], bool]) -> None:
        """Show *found* in place of the inbox; `unread` says whether its row is."""
        if found == self.target:
            return

        if self.target is None:
            focused = self.screen.focused
            self._saved_focus = focused.id if focused and focused.id else "main_table"
            self._saved_subtitle = self.app.sub_title

        self.local = False
        self.target = found
        self.screen.query_one(ContentSwitcher).current = "brief_view"
        self.app.sub_title = "brief"
        self.show(found, unread())
        self.focus()
        self.app.refresh_bindings()

    def close(self) -> bool:
        """Put the inbox back as it was before the brief opened; False if none was open."""
        if self.target is None:
            return False

        self.target = None
        self.local = False
        self.targets.clear()
        self.screen.query_one(ContentSwitcher).current = "inbox_content"
        self.app.sub_title = self._saved_subtitle
        previous = self.screen.query(f"#{self._saved_focus}")
        (previous.first() if previous else self._main()).focus()
        self.app.refresh_bindings()
        return True

    def target_for(
        self, notification: db.Notification, *, fresh: bool = False
    ) -> brief.target.Target:
        if not fresh and (found := self.targets.get(notification.id)):
            return found

        with db.connect() as conn:
            attached = brief.attached.for_rows(conn, [notification])
            emojis = emoji.by_channel(conn)
        self.targets.pop(notification.id, None)
        return brief.target.for_notification(
            notification, attached, emojis.get(notification.channel, "")
        )

    def adjacent(self, table: DataTable, direction: int) -> tuple[int, db.Notification] | None:
        """The next lemon's row and notification *direction* rows away, past group headers."""
        next_row = table.cursor_coordinate.row + direction
        while (
            0 <= next_row < table.row_count
            and row_keys.key_id(row_keys.at_row(table, next_row)) is None
        ):
            next_row += direction
        if not 0 <= next_row < table.row_count:
            return None

        if (notification_id := row_keys.key_id(row_keys.at_row(table, next_row))) is None:
            return None
        with db.connect() as conn:
            notification = db.get(conn, notification_id)

        return (next_row, notification) if notification else None

    def prefetch(self, table: DataTable) -> None:
        """Resolve the targets of the rows around the cursor, ready for the next arrows."""
        row = table.cursor_coordinate.row
        keys = [
            row_keys.at_row(table, near)
            for near in (row - 2, row - 1, row + 1, row + 2)
            if 0 <= near < table.row_count
        ]
        with db.connect() as conn:
            rows = [
                notification
                for key in keys
                if (found := row_keys.key_id(key)) is not None
                and found not in self.targets
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
            self.app.call_from_thread(lambda: self.targets.update(found))

        self.run_worker(resolve, thread=True, group="brief-prefetch")

    def stay_local(self, message: str) -> None:
        """Keep the brief here, saying why its lemon's terminal isn't coming up."""
        self.switch_pending = None
        self.local = True
        self.notice(message)

    def request_switch(self, notification: db.Notification, found: brief.target.Target) -> None:
        self.switch_pending = (notification, found)
        if not self._switching:
            self._switching = True
            self.run_worker(self._run_switches, thread=True, group="brief-switch")

    def _take_switch(self) -> _Switch | None:
        request, self.switch_pending = self.switch_pending, None
        if request is None:
            self._switching = False

        return request

    def _run_switches(self) -> None:
        """The worker thread: switch to the newest selection until none is waiting."""
        while request := self.app.call_from_thread(self._take_switch):
            notification, found = request
            metadata = {
                **notification.metadata,
                "channel": notification.channel,
                "name": notification.name or "",
            }
            try:
                switched = brief.sidebar.switch_beside(
                    metadata, notification.switch_source, self._config, found
                )
            except Exception:  # the thread's top level; the pane must not die with it
                _log.exception("brief switch to %s failed", notification.channel)
                switched = False
            self.app.call_from_thread(self._switched, notification, switched)

    def _main(self) -> DataTable:
        return self.screen.query_one("#main_table", DataTable)

    def unread(self) -> bool:
        """Whether the row under the cursor, whose brief is shown, is unread."""
        if not (row_key := self._cursor_key()):
            return False

        with db.connect() as conn:
            notification = db.get(conn, int(row_key))

        return bool(notification and notification.is_unread)

    def set_view(self, found: brief.target.Target | None) -> None:
        """Show *found* in place of the inbox, or with None put the inbox back."""
        if found is not None:
            self.open(found, self.unread)
        elif self.close():
            self._inbox_back()

    def sync(self) -> None:
        """Show what the sidebar says this window's brief is, unless one is kept here."""
        if self.target is not None and self.local:
            return

        pane = os.environ.get("TMUX_PANE")
        shown = brief.sidebar.read(pane) if pane else None
        self.set_view(shown[0] if shown and brief.sidebar.window_id(pane) == shown[1] else None)

    def toggle(self, found: brief.target.Target) -> bool:
        """Open *found* in the sidebar, or close it there; False if the sidebar can't."""
        if not brief.sidebar.toggle(
            found, brief.sidebar.window_id(os.environ.get("TMUX_PANE", ""))
        ):
            return False

        self.sync()
        if self.target is not None:
            self.prefetch(self._main())
        return True

    def retarget(self, notification: db.Notification) -> None:
        """Resolve the shown brief's target again, after a change to the row it is for.

        The target carries the row's name, and so does the sidebar option a wake
        restores it from, so both are replaced.
        """
        found = self.target_for(notification, fresh=True)
        if pane := os.environ.get("TMUX_PANE", ""):
            brief.sidebar.show(found, brief.sidebar.window_id(pane))
        self.set_view(found)

    def dismiss(self) -> None:
        self.switch_pending = None
        if pane := os.environ.get("TMUX_PANE"):
            brief.sidebar.clear(pane)
        self.set_view(None)

    def navigate(self, direction: int, detached: abc.Set[str]) -> None:
        """Show the adjacent row's brief now, and move the main pane to its lemon after."""
        main = self._main()
        if not (step := self.adjacent(main, direction)):
            return

        row, notification = step
        found = self.target_for(notification)
        main.move_cursor(row=row)
        self.set_view(found)
        self.prefetch(main)
        if notification.channel in detached or notification.switch_source != "tmux":
            self.stay_local(
                f"Its terminal is unavailable here. Press {self._config.tui.keybindings.resume_detached} "
                "to resume; up/down keeps browsing."
            )
            return

        self.request_switch(notification, found)

    def _switched(self, notification: db.Notification, switched: bool) -> None:
        if self.target is None:
            # Closed while the switch ran, which set the sidebar brief again.
            if pane := os.environ.get("TMUX_PANE", ""):
                brief.sidebar.clear(pane)
            return

        if self._cursor_key() != str(notification.id):
            return

        if switched:
            self.local = False
            tty = notification.metadata.get("tty")
            if isinstance(tty, str) and tty:
                self._note_focus(tty)
        if self.switch_pending is not None:
            return

        if not switched:
            self.stay_local(
                f"Its terminal could not be opened. Press {self._config.tui.keybindings.resume_detached} "
                "to try resuming; up/down keeps browsing."
            )
            return

        self.sync()
