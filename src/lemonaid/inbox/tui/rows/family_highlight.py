"""Cursor-relative relationship marks, updated from cached row renderers."""

from collections import abc

from rich.text import Text
from textual.coordinate import Coordinate
from textual.widgets import DataTable

from ..utils import same_cell


class Highlighter:
    def __init__(self) -> None:
        self._channels: dict[str, str] = {}
        self._keys: dict[str, set[str]] = {}
        self._parents: dict[str, str] = {}
        self._children: dict[str, set[str]] = {}
        self.roles: dict[str, str] = {}
        self._renderers: dict[str, abc.Callable[[str, str], list[Text]]] = {}
        self._tables: dict[str, DataTable] = {}

    def _roles(self, key: str) -> dict[str, str]:
        channel = self._channels.get(key, "")
        if not channel:
            return {}

        parent = self._parents.get(channel, "")
        roles = {
            k: "child"
            for child in self._children.get(channel, ())
            for k in self._keys.get(child, ())
        }
        if parent != channel:
            roles.update({k: "parent" for k in self._keys.get(parent, ())})
        return roles

    def prepare(self, channels: dict[str, str], parents: abc.Mapping[str, str], key: str) -> None:
        self._channels = channels
        self._keys = {}
        for row_key, channel in channels.items():
            self._keys.setdefault(channel, set()).add(row_key)
        self._parents = dict(parents)
        self._children = {}
        for child, parent in parents.items():
            if child != parent and child in self._keys:
                self._children.setdefault(parent, set()).add(child)
        self.roles = self._roles(key)
        self._renderers = {}
        self._tables = {}

    def bind(
        self,
        table: DataTable,
        keys: abc.Iterable[str],
        render: abc.Callable[[str, str], list[Text]],
    ) -> None:
        for key in keys:
            self._renderers[key] = render
            self._tables[key] = table

    def highlight(self, key: str) -> None:
        wanted = self._roles(key)
        changed = {
            k
            for k in self.roles.keys() | wanted.keys()
            if self.roles.get(k, "") != wanted.get(k, "")
        }
        self.roles = wanted
        for row_key in changed:
            if row_key not in self._renderers:
                continue

            table = self._tables[row_key]
            row = table.get_row_index(row_key)
            for column, value in enumerate(
                self._renderers[row_key](row_key, wanted.get(row_key, ""))
            ):
                if not same_cell(table.get_cell_at(Coordinate(row, column)), value):
                    table.update_cell_at((row, column), value, update_width=False)
