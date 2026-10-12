"""Column visibility and width distribution for the inbox DataTables."""

from collections import abc

from rich.text import Text
from textual.widgets import DataTable

from . import layout


def hide_columns(table: DataTable, indices: abc.Container[int], labels: dict[int, str]) -> None:
    """Collapse the given columns to zero width, restoring the rest.

    Textual's DataTable has no column-visibility flag, so a hidden column is one
    with no label and no width. `labels` supplies the text to restore.
    """
    for i, column in enumerate(table.columns.values()):
        hidden = i in indices
        column.label = Text("" if hidden else labels.get(i, ""))
        if hidden:
            column.auto_width = False
            column.width = 0


def _rendered_width(table: DataTable) -> int:
    """The row width DataTable will report as its virtual width.

    Mirrors Column.get_render_width, which adds cell padding on both sides of every
    column — including one collapsed to zero width, which still costs its padding.
    """
    return sum(c.width + 2 * table.cell_padding for c in table.columns.values())


def vertical_scrollbar_width(table: DataTable) -> int:
    """Width to hold back for the vertical scrollbar, whether or not it's showing.

    Reserved unconditionally rather than keyed on `show_vertical_scrollbar`: the two
    scrollbars are mutually dependent (narrower columns can retract the horizontal
    bar, which grows the viewport, which can retract the vertical one), so reading
    the live flag oscillates between two layouts. Costs two columns of flex width on
    a list short enough not to scroll.
    """
    return int(table.styles.scrollbar_size_vertical or 0)


def fill_card_columns(table: DataTable, total_width: int) -> None:
    """Give the card's single cell the entire paintable width."""
    columns = list(table.columns.values())
    if not columns or total_width <= 0:
        return

    for column in columns:
        column.auto_width = False
    columns[layout.CARD_BODY_COLUMN].width = max(layout.CARD_MIN_TEXT, total_width)


def stretch_columns(
    table: DataTable,
    flex_specs: list[tuple[int, int, float, int]],
    total_width: int,
) -> None:
    """Distribute remaining table width among flex columns.

    Textual DataTable doesn't natively expand columns to fill available width.
    Each flex_spec is (column_index, min_width, weight, max_width); a max_width of
    0 means unbounded. Remaining space after fixed columns is divided
    proportionally by weight, floored at min_width and capped at max_width.

    The caps exist because a proportional share of a very wide terminal is mostly
    padding: names and paths have a length past which the extra columns show
    nothing. The last flex column is the message, whose length is unbounded, and
    it takes whatever the capped columns decline.
    """
    if not flex_specs or not table.columns or total_width <= 0:
        return

    columns = list(table.columns.values())
    flex_indices = {spec[0] for spec in flex_specs}
    # A hidden column has been collapsed to zero width and draws no padding.
    hidden = sum(1 for i, c in enumerate(columns) if i not in flex_indices and not c.width)
    padding_total = 2 * table.cell_padding * (len(columns) - hidden) + 1
    fixed_total = sum(c.width for i, c in enumerate(columns) if i not in flex_indices)
    remaining = total_width - fixed_total - padding_total
    if remaining <= 0:
        return

    # Honour the minimums only while they fit. When the terminal is too narrow
    # for all of them, fall back to pure proportional division rather than
    # overflowing the table horizontally.
    total_weight = sum(spec[2] for spec in flex_specs)
    honour_minimums = sum(spec[1] for spec in flex_specs) <= remaining

    budget = remaining
    for position, (idx, min_w, frac, max_w) in enumerate(flex_specs):
        if idx >= len(columns):
            continue

        share = int(remaining * frac / total_weight) if total_weight else min_w
        width = max(share, min_w) if honour_minimums else share
        # The last flex column absorbs the rounding remainder so the row fills
        # the width exactly instead of leaving a ragged gap.
        if position == len(flex_specs) - 1:
            width = max(width, budget)
        elif max_w and honour_minimums:
            width = min(width, max_w)

        columns[idx].auto_width = False
        columns[idx].width = min(width, budget)
        budget -= columns[idx].width

    # `padding_total` only approximates what DataTable will charge, so reconcile
    # against the real measure: overshooting by one cell costs a whole row of height
    # to a horizontal scrollbar. Trim the widest column first and Name last.
    overflow = _rendered_width(table) - total_width
    while overflow > 0:
        trimmable = [
            spec[0] for spec in flex_specs if spec[0] < len(columns) and columns[spec[0]].width
        ]
        if not trimmable:
            break

        # Name only gives up cells once nothing else has any left to give.
        candidates = [idx for idx in trimmable if idx != layout.NAME_COLUMN] or trimmable
        widest = max(candidates, key=lambda idx: columns[idx].width)
        columns[widest].width -= 1
        overflow -= 1
