from textual import events
from textual.app import ComposeResult
from textual.content import Content
from textual.layout import Layout
from textual.style import Style
from textual.widgets._markdown import MarkdownTableContent

# The cell's own two columns of padding, and the same again so a word never sits flush.
_CELL_PADDING = 4

# A column whose longest cell is no longer than this is exactly as wide as that cell.
_FIXED_MAX = 40

# The text a column keeps as width runs out: at most this many characters, or all of its
# text if it has less, and a wrapping column keeps more.
_MIN_TEXT = 12
_MIN_FLEXIBLE = 24

# A column whose text is this short has little to wrap, so it is never narrowed.
_WHOLE_COLUMN = 20


def _shortened(cell: Content) -> Content:
    """An absolute path's file name, which is what tells paths apart; the rest is in its tooltip."""
    plain = cell.plain
    if not plain.startswith("/"):
        return cell

    name = plain.rstrip("/").rsplit("/", 1)[-1]

    return cell[len(plain.rstrip("/")) - len(name) :].rstrip("/")


def _floor(column: tuple[Content, ...], need: int) -> int:
    """The narrowest a column goes: whole if its text is short, else a readable stub."""
    if max(len(cell.plain) for cell in column) <= _WHOLE_COLUMN:
        return need

    return min(need, _MIN_TEXT + _CELL_PADDING)


def _columns(headers: list[Content], rows: list[list[Content]], width: int) -> str:
    """Short columns are as wide as their content; columns with more text wrap in what's left.

    When *width* can't hold that, the widest short column gives up width first, down to
    its floor. No column goes below its floor: if they all sit at it and still don't fit,
    the table is wider than *width*.
    """
    columns = list(zip(headers, *rows, strict=False))
    needs = [max(len(cell.plain) for cell in column) + _CELL_PADDING for column in columns]
    longest = needs.index(max(needs))
    fixed = {i: n for i, n in enumerate(needs) if i != longest and n <= _FIXED_MAX}
    wrapping = [i for i in range(len(needs)) if i not in fixed]
    floors = {i: _floor(columns[i], fixed[i]) for i in fixed}
    wrapping_floor = sum(min(needs[i], _MIN_FLEXIBLE) for i in wrapping)
    over = sum(fixed.values()) + (len(needs) - 1) + wrapping_floor - width
    while over > 0 and (squeezable := [i for i in fixed if fixed[i] > floors[i]]):
        fixed[max(squeezable, key=fixed.__getitem__)] -= 1
        over -= 1

    return " ".join(
        str(fixed[i]) if i in fixed else str(min(needs[i], _MIN_FLEXIBLE)) if over > 0 else "1fr"
        for i in range(len(needs))
    )


class _SizedTableContent(MarkdownTableContent):
    def __init__(self, headers: list[Content], rows: list[list[Content]]) -> None:
        self._full = [[cell.plain for cell in row] for row in rows]
        shortened = [[_shortened(cell) for cell in row] for row in rows]
        super().__init__(headers, shortened)
        self._sized = (headers, shortened)
        self.styles.grid_columns = _columns(headers, shortened, 1_000)

    def on_resize(self, event: events.Resize) -> None:
        self.styles.grid_columns = _columns(*self._sized, event.size.width)

    def compose(self) -> ComposeResult:
        for widget in super().compose():
            if widget.name and widget.name.startswith("cell"):
                row, _, column = widget.name.removeprefix("cell").partition(".")
                widget.tooltip = self._full[int(row) - 1][int(column) - 1]
                if column == "1" and (
                    url := next(
                        (
                            span.style.link
                            for span in widget.content.spans
                            if isinstance(span.style, Style) and span.style.link
                        ),
                        "",
                    )
                ):
                    widget.tooltip = url
            yield widget

    def pre_layout(self, layout: Layout) -> None:
        super().pre_layout(layout)
        layout.auto_minimum = False
        layout.shrink = False


def content(headers: list[Content], rows: list[list[Content]]) -> MarkdownTableContent:
    return _SizedTableContent(headers, rows)
