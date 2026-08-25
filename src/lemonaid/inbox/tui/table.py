"""The inbox's table, which switches to a session on the first click."""

from textual import events
from textual.coordinate import Coordinate
from textual.widgets import DataTable


class ClickToActTable(DataTable):
    """A DataTable whose rows act on one click rather than two.

    Since Textual 7.5.0 the base widget posts RowSelected only when a click lands
    on the coordinate the cursor already holds. Under a row cursor the column is
    invisible to the reader, so a click on any other column of the target row
    merely moves the cursor, and the row has to be clicked again - which reads as
    the first click having been ignored.

    Rows here are destinations, and a row cursor means the column was never part
    of the intent.
    """

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

        if (row, meta["column"]) == tuple(self.cursor_coordinate):
            return  # the base posts this one itself

        self.post_message(
            DataTable.RowSelected(self, row, self.coordinate_to_cell_key(Coordinate(row, 0))[0])
        )
