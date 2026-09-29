"""The inbox's table, which switches to a session on the first click."""

from rich.style import Style
from textual import events
from textual.coordinate import Coordinate
from textual.message import Message
from textual.widgets import DataTable
from textual.widgets.data_table import RowKey


class ClickToActTable(DataTable):
    """A DataTable whose rows act on one click rather than two.

    Since Textual 7.5.0 the base widget posts RowSelected only when a click lands
    on the coordinate the cursor already holds. Under a row cursor the column is
    invisible to the reader, so a click on any other column of the target row
    merely moves the cursor, and the row has to be clicked again - which reads as
    the first click having been ignored.

    Rows here are destinations, and a row cursor means the column was never part
    of the intent.

    The cursor also fills a row's background without repainting its text.
    Textual's default gives the cursor's foreground priority over the cell's
    own, which flattens every field to one colour - and here colour *is* the
    field's identity, so the selected row loses exactly what the list is read
    for. The mouse-hover highlight is left alone: it is transient and follows
    the pointer rather than marking a choice.

    A click on the row the cursor already holds posts SelectedRowClicked instead
    of RowSelected, so the app can tell it from Enter.
    """

    class SelectedRowClicked(Message):
        def __init__(self, table: "ClickToActTable", row_key: RowKey) -> None:
            super().__init__()
            self.data_table = table
            self.row_key = row_key

    def __init__(self, *args: object, **kwargs: object) -> None:
        kwargs.setdefault("cursor_foreground_priority", "renderable")
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        # Fills a whole row, padding included, which a cell's own style can't.
        # Keyed by row key; set it before the cell updates that repaint the rows.
        self.row_backgrounds: dict[str, Style] = {}

    def _get_row_style(self, row_index: int, base_style: Style) -> Style:
        style = super()._get_row_style(row_index, base_style)
        if row_index < 0 or row_index >= len(self.ordered_rows):
            return style

        fill = self.row_backgrounds.get(str(self.ordered_rows[row_index].key.value))
        return style + fill if fill else style

    def on_click(self, event: events.Click) -> None:
        # Public on_click runs alongside the base _on_click rather than replacing
        # it: Textual dispatches to every class in the MRO that defines a handler,
        # so overriding _on_click and calling super() runs the base body twice and
        # posts twice.
        meta = event.style.meta
        if "row" not in meta or "column" not in meta:
            return

        row = meta["row"]
        if row < 0 or not self.show_cursor or self.cursor_type != "row":
            return

        if row == self.cursor_row:
            event.prevent_default()
            event.stop()
            self.post_message(
                self.SelectedRowClicked(self, self.coordinate_to_cell_key(Coordinate(row, 0))[0])
            )
            return

        self.post_message(
            DataTable.RowSelected(self, row, self.coordinate_to_cell_key(Coordinate(row, 0))[0])
        )
