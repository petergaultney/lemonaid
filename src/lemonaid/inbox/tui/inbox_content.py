"""The panes under the inbox's header: which list shows, the search box, the notes and status line.

It owns which view is up, whether a search is on and what it matches, and
whether the tables are drawn as cards or columns. The app decides when any
of that changes; this decides what the panes look like for it.
"""

from collections import abc

from textual.containers import Container
from textual.widget import Widget
from textual.widgets import DataTable, Input, Static

from ...config import Config
from . import search_archive, table_layout, table_setup, view_modes
from .history_table import HistoryTable
from .inbox_draw import Drawn
from .inbox_list import InboxList
from .notes import NotesPanel
from .snoozed_table import SnoozedTable
from .utils import update_static


class InboxContent(Container):
    def __init__(
        self, config: Config, sidebar: abc.Callable[[], bool | None], *children: Widget, id: str
    ) -> None:
        """`sidebar` says whether the scratch pane is a left-hand sidebar, or None outside one."""
        super().__init__(*children, id=id)
        self._config = config
        self._sidebar = sidebar
        self.mode: view_modes.Mode | None = None  # an alternate view, while one is shown
        self.searching = False
        self.filter_text = ""
        self.cards = False  # the layout the tables are built for
        self.notes_open = True  # the notes key's choice; shown only in card layout too

    @property
    def inbox(self) -> InboxList:
        return self.query_one(InboxList)

    @property
    def history(self) -> HistoryTable:
        return self.query_one(HistoryTable)

    @property
    def snoozed(self) -> SnoozedTable:
        return self.query_one(SnoozedTable)

    def active_table(self) -> DataTable:
        return self.query_one(self.mode.table_id if self.mode else "#main_table", DataTable)

    def stacked(self) -> tuple[DataTable, DataTable, DataTable]:
        """The main, other-terminals and history tables, top to bottom."""
        return self.inbox.main, self.inbox.other, self.history

    def wants_cards(self, width: int, height: int) -> bool:
        return table_layout.wants_cards(width, height, self._sidebar())

    def _tables(self) -> dict[str, DataTable]:
        return {table_id: self.query_one(table_id, DataTable) for table_id in table_setup.TABLE_IDS}

    def build_tables(self, cards: bool, history_marker: bool) -> None:
        """Give every table the columns of a card or column layout.

        `history_marker` gives the history table an unread-marker column, as a
        rebuild on resize does; it is built without one at startup.
        """
        for table_id, table in self._tables().items():
            table_setup.setup(
                table,
                cards,
                self._config.tui,
                wake_column=table_id == "#snoozed_table",
                marker_column=history_marker or table_id != "#history_table",
            )

    def stretch(self, width: int) -> None:
        table_setup.stretch(self._tables(), self.cards, width, self._config.tui.card_fields)

    def card_width(self) -> int:
        """Width the card's body column was stretched to, or 0 outside card mode.

        Keys off `cards` rather than the current size: this decides how many
        cells a row has, and it must match the columns the tables were built with,
        which the app's size disagrees with while a resize is being handled.
        """
        if not self.cards:
            return 0

        return table_layout.card_width([c.width for c in self.inbox.main.columns.values()])

    def card_shape(self, extra_lines: int = 0) -> tuple[int, int]:
        if not self.cards:
            return 1, 1

        return table_layout.card_shape(
            self.app.size.height, self.notes_height(), self.inbox.main.row_count, extra_lines
        )

    def _notes(self) -> NotesPanel | None:
        panels = self.query(NotesPanel)
        return panels.first() if panels else None

    def refresh_notes(self) -> None:
        """Show the notes under the cards, unless hidden; a top strip has no room for them."""
        panel = self._notes()
        if panel is None:
            return

        panel.display = self.notes_open and self.cards
        if panel.display:
            panel.reload()

    def notes_height(self) -> int:
        """Rows the notes take from the cards, as last laid out."""
        panel = self._notes()
        return panel.outer_size.height if panel is not None and panel.display else 0

    def set_status(self, text: str) -> None:
        update_static(self.query_one("#status", Static), text)

    def show_mode(self, mode: view_modes.Mode, enabled: bool) -> None:
        """Put *mode*'s table in place of the inbox, or the inbox back."""
        self.mode = mode if enabled else None
        if mode is view_modes.HISTORY:
            self.filter_text = ""
        table = self.query_one(mode.table_id, DataTable)
        box = self.query_one("#history_filter", Input)
        if not enabled:
            table.display = False
            if mode is view_modes.HISTORY:
                box.display = False
            self.inbox.display = True
            return

        self.inbox.display = False
        self.query_one("#search_archive_label", Static).display = False
        table.display = True
        if mode is view_modes.HISTORY:
            box.display = False
            box.value = ""

    def open_search_box(self) -> None:
        box = self.query_one("#history_filter", Input)
        box.display = True
        box.focus()

    def start_search(self) -> None:
        self.searching = True
        self.filter_text = ""

    def stop_search(self) -> None:
        self.searching = False
        self.filter_text = ""
        box = self.query_one("#history_filter", Input)
        box.value = ""
        box.display = False
        self.query_one("#search_archive_label", Static).display = False
        self.history.display = False

    def clear_history_filter(self) -> None:
        self.filter_text = ""
        box = self.query_one("#history_filter", Input)
        box.value = ""
        box.display = False

    def refill_history(self, searching_from: str | None) -> int:
        count = self.history.refill(
            self.filter_text, searching_from, self.searching, self.card_width(), self.card_shape()
        )
        if not self.searching:
            self.set_status(f"{count} archived session{'s' if count != 1 else ''}")
        return count

    def refill_snoozed(self) -> None:
        count = self.snoozed.refill(self.card_width(), self.card_shape())
        self.set_status(f"{count} snoozed session{'s' if count != 1 else ''}  |  Enter to wake now")

    def place_archive(self, drawn: Drawn, count: int) -> bool:
        """Show a search's archive matches under its inbox matches if they fit."""
        return search_archive.show(
            self.query_one("#search_archive_label", Static),
            self.history,
            self.inbox.main,
            self.inbox.other if drawn.other_shown else None,
            count,
            self.size.height
            - self.query_one("#history_filter", Input).outer_size.height
            - self.query_one("#status", Static).outer_size.height
            - self.notes_height(),
            drawn.other and not drawn.other_shown,
        )

    def hide_archive(self) -> None:
        self.history.display = False
        self.query_one("#search_archive_label", Static).display = False
