"""The configured arranger process, asked how to order and fold each refresh's rows."""

import time
from collections import abc

from ....config import Config
from ....log import get_logger
from ... import db, view
from ...arrange import answer, child

_log = get_logger("tui")


class Arrangement:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._arranger = (
            child.Arranger(child.parse_command(config.inbox.arrange))
            if config.inbox.arrange
            else None
        )
        self.parents_first = True
        self.error = ""  # why the last answer wasn't used, for the status line
        self._logged: set[str] = set()

    def close(self) -> None:
        if self._arranger is not None:
            self._arranger.close()

    def arranged(
        self,
        active: "view.Active",
        shown: list[db.Notification],
        folded: list[db.Notification],
        pinned: frozenset[str],
        hidden: frozenset[str],
        emojis: abc.Mapping[str, str],
        cards: bool,
        width: int,
    ) -> tuple[list[db.Notification], list[db.Notification], str, list[db.Notification]]:
        """*shown*, *folded*, the fold label, and group members' order before folding.

        While it has no usable answer they come back as they are, and `error` says why.
        """
        self.parents_first = True
        if self._arranger is None:
            return shown, folded, "", active.rows

        now = time.time()
        reply = self._arranger.answer(
            view.snapshot(
                active, shown, folded, pinned, emojis, "sidebar" if cards else "table", width, now
            ),
            now,
        )
        self.error = self._arranger.error
        if reply is None:
            return shown, folded, "", active.rows

        try:
            arranged = answer.apply(
                reply,
                shown,
                folded,
                self._config.inbox.arrange_may_fold_unread,
                active.deaf,
                hidden,
            )
        except answer.AnswerError as e:
            if str(e) not in self._logged:
                _log.warning("arrange: %s", e)
                self._logged.add(str(e))
            self.error = str(e)
            return shown, folded, "", active.rows

        if len(self._logged) > 1000:
            self._logged.clear()  # problems name row ids, which keep changing
        for problem in set(arranged.problems) - self._logged:
            _log.info("arrange: %s", problem)
        self._logged.update(arranged.problems)
        self.parents_first = False
        return (
            arranged.shown,
            arranged.folded,
            arranged.fold_label,
            [*arranged.shown, *arranged.folded],
        )
