"""The snoozed table, and waking the session under its cursor."""

from collections import abc

from textual.widgets import DataTable

from ...config import Config
from .. import undo
from . import bindings, brief_cards, inbox_edits, row_keys, row_parts, snoozed_rows


class SnoozedTable(DataTable):
    def __init__(
        self,
        config: Config,
        parts: row_parts.RowParts,
        brief_cache: brief_cards.BriefCache,
        undo_stack: undo.Stack,
        redraw: abc.Callable[[], None],
        *,
        id: str,
    ) -> None:
        """`redraw` refills this table and says how many are snoozed."""
        super().__init__(id=id)
        self._config = config
        self._parts = parts
        self._brief_cache = brief_cache
        self._undo_stack = undo_stack
        self._redraw = redraw

    def refill(self, card_width: int, card_shape: tuple[int, int]) -> int:
        """Bring the table in line with what is snoozed; how many sessions that is."""
        snoozed_rows.fill(
            self, self._config, self._parts, self._brief_cache, card_width, card_shape
        )
        return self.row_count

    def wake(self) -> None:
        """Wake the session under the cursor and return it to the inbox."""
        key = row_keys.notification_at_cursor(self)
        if key and (entry := inbox_edits.wake(int(key))):
            self._redraw()
            self._undo_stack.push(entry)
            self.notify(f"{entry.description} — press {bindings.undo_key(self._config)} to undo")
