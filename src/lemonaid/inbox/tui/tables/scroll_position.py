"""Keep the visible row in place while table data changes."""

import contextlib
import functools
import typing as ty
from collections import abc

from textual.coordinate import Coordinate
from textual.widgets import DataTable


def _rows(table: DataTable) -> list[tuple[str, int, int]]:
    y = 0
    rows = []
    for row in table.ordered_rows:
        rows.append((str(row.key.value), y, row.height))
        y += row.height
    return rows


class StableTable(DataTable):
    _preserving = False

    def _scroll_cursor_into_view(self, animate: bool = False) -> None:
        if not self._preserving:
            super()._scroll_cursor_into_view(animate)

    def watch_cursor_coordinate(self, old: Coordinate, new: Coordinate) -> None:
        if self._preserving:
            pending = self._require_update_dimensions
            self._require_update_dimensions = False
            try:
                super().watch_cursor_coordinate(old, new)
            finally:
                self._require_update_dimensions = pending
        else:
            super().watch_cursor_coordinate(old, new)

    def move_cursor(
        self,
        *,
        row: int | None = None,
        column: int | None = None,
        animate: bool = False,
        scroll: bool = True,
    ) -> None:
        with self._without_cursor_scroll(not scroll):
            super().move_cursor(row=row, column=column, animate=animate, scroll=scroll)

    @contextlib.contextmanager
    def _without_cursor_scroll(self, enabled: bool) -> abc.Iterator[None]:
        before = self._preserving
        self._preserving |= enabled
        try:
            yield
        finally:
            self._preserving = before

    @contextlib.contextmanager
    def preserve_scroll(self) -> abc.Iterator[None]:
        x, y = self.scroll_x, self.scroll_y
        anchors = [(key, top - y) for key, top, height in _rows(self) if top + height > y]
        with self._without_cursor_scroll(True):
            yield
        if self._require_update_dimensions:
            self._require_update_dimensions = False
            new_rows = self._new_rows.copy()
            self._new_rows.clear()
            self._update_dimensions(new_rows)
        positions = {key: top for key, top, _ in _rows(self)}
        target = next((positions[key] - offset for key, offset in anchors if key in positions), y)
        self.scroll_to(x=x, y=target, animate=False, force=True, immediate=True)


_P = ty.ParamSpec("_P")
_R = ty.TypeVar("_R")


def preserve_scroll(
    fn: abc.Callable[ty.Concatenate[DataTable, _P], _R],
) -> abc.Callable[ty.Concatenate[DataTable, _P], _R]:
    @functools.wraps(fn)
    def call(table: DataTable, *args: _P.args, **kwargs: _P.kwargs) -> _R:
        with (
            table.preserve_scroll() if isinstance(table, StableTable) else contextlib.nullcontext()
        ):
            return fn(table, *args, **kwargs)

    return call
