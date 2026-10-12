"""The session-history table, and resuming the session under its cursor."""

from collections import abc

from textual.widgets import DataTable

from ...config import Config
from .. import db
from . import (
    brief_cards,
    error_screen,
    history_resume,
    history_rows,
    inbox_switch,
    row_keys,
    row_parts,
)


class HistoryTable(DataTable):
    def __init__(
        self,
        config: Config,
        parts: row_parts.RowParts,
        brief_cache: brief_cards.BriefCache,
        back_to_inbox: abc.Callable[[db.Notification], None],
        exec_here: abc.Callable[[str, list[str]], None],
        redraw: abc.Callable[[], None],
        *,
        id: str,
    ) -> None:
        """`back_to_inbox` takes over once a session turns out still to be running;
        `exec_here` replaces this program with a resumed session.
        """
        super().__init__(id=id)
        self._config = config
        self._parts = parts
        self._brief_cache = brief_cache
        self._back_to_inbox = back_to_inbox
        self._exec_here = exec_here
        self._redraw = redraw

    def refill(
        self,
        text: str,
        searching_from: str | None,
        searching: bool,
        card_width: int,
        card_shape: tuple[int, int],
    ) -> int:
        """Redraw the archived sessions matching *text*; how many there are."""
        history_rows.fill(
            self,
            history_rows.load(text, searching_from, searching),
            self._config,
            self._parts,
            self._brief_cache,
            card_width,
            card_shape,
        )
        return self.row_count

    def _selected(self) -> db.Notification | None:
        if self.row_count == 0 or not (key := row_keys.at_row(self, self.cursor_row)):
            return None

        with db.connect() as conn:
            notification = db.get(conn, int(key.value))
        if not notification:
            error_screen.show(
                self.app,
                "That session is gone",
                "Its row was removed from the inbox since the list was drawn.",
            )
        return notification

    def _act_on(self, notification: db.Notification, done: history_resume.Outcome) -> None:
        if done.kind == "running":
            self._back_to_inbox(notification)
        elif done.kind == "unresumable":
            error_screen.show(
                self.app,
                "Could not resume that session",
                "No working directory is recorded for it, so there is nowhere to resume it.",
            )
        elif done.kind == "failed":
            inbox_switch.resume_failed(self, done.command, done.reason)
        elif done.kind == "started":
            self._redraw()
        elif done.kind == "exec":
            self._exec_here(done.cwd, list(done.argv))
        else:
            inbox_switch.copy_resume(self, done.command)

    def resume(self, mode: history_resume.Mode, here_tty: str) -> history_resume.Outcome | None:
        """Resume the session under the cursor; what happened, if there was one."""
        if not (notification := self._selected()):
            return None

        done = history_resume.run(notification, self._config, mode, here_tty)
        self._act_on(notification, done)
        return done

    def resume_in_new_session(self) -> None:
        """Spawn a new tmux session around the session under the cursor."""
        if notification := self._selected():
            self._act_on(notification, history_resume.in_new_session(notification, self._config))
