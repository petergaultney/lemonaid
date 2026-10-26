"""The `?` panel: every key in the grove view, or in a zoomed block, with what it does."""

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Label, Static

from . import flip, select_view, selecting

_GROVE = [
    ("a digit", "zoom into that block; 0 is the packhouse, and 1 0 is block 10"),
    ("a digit, then a letter", "jump to that tree's first lemon, as 2c"),
    (
        "a digit, a dot, a letter, a place",
        "another lemon on that tree, as 2.c1; past nine, 0 and a letter, 2.c0a",
    ),
    ("/", "search Brief-IDs, sessions and names; ↑↓ choose, enter jumps"),
    ("arrows", "pan the grove when it is bigger than the screen"),
    ("Shift and an arrow", "move the view a whole screen"),
    ("Shift or Alt and 1-8", "a screen away from the packhouse: 1 north, clockwise to 8"),
    ("Shift or Alt and 0, Home", "center the packhouse"),
    ("click a block", "zoom into it"),
    ("drag a block", "move it; drag its edge to resize it"),
]
_BLOCK = [
    ("a letter", "jump to the tree's first lemon, l the lead's"),
    (
        "a dot, a letter, a place",
        "another lemon on that tree, as .c1; past nine, 0 and a letter, .c0a",
    ),
    ("/", "search Brief-IDs, sessions and names; ↑↓ choose, enter jumps"),
    ("click a tree", "the same as its letter"),
    ("drag a tree", "move it within its block"),
    ("drag a bare tree", "move it; drag it off its block's ground to clear it away"),
]
_SELECT = [
    ("a digit", "choose that block"),
    ("a letter", "choose that tree's first lemon, l the lead's, and show its card"),
    (
        "a dot, a letter, a place",
        "choose another lemon on that tree, as .c1; past nine, 0 and a letter",
    ),
    ("$, a letter", "choose the whole tree, to edit every lemon on it or to move it"),
    ("↑ ↓", "with a lemon chosen, the next or previous lemon on its tree"),
    (
        "arrows",
        "with a whole tree chosen, move it a step; Shift, five; it hops what it can't stand on",
    ),
    (
        "r, s, a, p, g, c",
        "with a tree or a lemon chosen: rename, snooze, archive, pin or unpin, move to another group, recolor its block",
    ),
    ("enter, o", "jump to the chosen lemon, or the chosen tree's first"),
    ("backspace", "back to the block, then out of it"),
    ("/", "search Brief-IDs, sessions and names; enter chooses the match"),
    ("click a tree", "the same as its letter"),
]
_LAST = [
    ("esc", "back out one step: out of a tree, a block, the grove"),
    ("space", "close the grove"),
    ("q", "close the grove; a search or a dialog takes it as text"),
    ("Q", "quit the process the grove runs in, so the next open starts fresh"),
    ("?", "show or hide this panel"),
]


def _flip_row(flips: flip.Flip, zoomed: bool) -> tuple[str, str]:
    lists = (
        "each lemon's PRs and branch, model and context"
        if zoomed
        else "each tree's lemons mid-turn of all, fullest context, latest report: 1/3 · 88% · 4m"
    )
    if flips.hold:
        return f"hold {flips.key}", f"{lists}; let go to see names again"

    return flips.key, f"{lists}; again to see names"


def rows(
    zoomed: bool,
    flips: flip.Flip = flip.DEFAULT,
    select_key: str = selecting.DEFAULT_KEY,
    selected: bool = False,
) -> list[tuple[str, str]]:
    key = select_view.key_name(select_key)
    select = (
        (f"{key}, esc", "leave select mode")
        if selected
        else (
            key,
            "select mode: keys choose a block, tree or lemon without jumping, a card shows it,"
            " and r s a p g c rename, snooze, archive, pin, move or recolor it",
        )
    )
    return [
        *(_SELECT if selected else _BLOCK if zoomed else _GROVE),
        select,
        _flip_row(flips, zoomed),
        *(row for row in _LAST if not (selected and row[0] == "esc")),
    ]


def _table(zoomed: bool, flips: flip.Flip, select_key: str, selected: bool) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold #f2d94e", no_wrap=True)
    table.add_column(style="#d8dee9")
    for key, what in rows(zoomed, flips, select_key, selected):
        table.add_row(key, what)
    return table


_WIDTH = 104
# Rows the panel adds around its table: border, the title line and the blank after it.
_FRAME_ROWS = 4


class HelpPanel(VerticalScroll):
    """Drawn over the middle of the grove, which stays in view around it."""

    DEFAULT_CSS = f"""
    HelpPanel {{
        layer: overlay; dock: top; width: {_WIDTH}; max-width: 100%; height: auto;
        max-height: 100%; padding: 0 1; background: #121821; border: round #f2d94e;
    }}
    HelpPanel Label {{ color: #9aa5b8; margin-bottom: 1; }}
    """

    def __init__(
        self,
        zoomed: bool,
        flips: flip.Flip = flip.DEFAULT,
        select_key: str = selecting.DEFAULT_KEY,
        selected: bool = False,
    ) -> None:
        super().__init__()
        self._table = _table(zoomed, flips, select_key, selected)
        self._title = (
            "Keys in select mode"
            if selected
            else "Keys in a block"
            if zoomed
            else "Keys in the grove"
        )

    def compose(self) -> ComposeResult:
        yield Label(Text(self._title, style="bold") + Text(" · any key closes"))
        yield Static(self._table)

    def on_mount(self) -> None:
        self.center()

    def center(self) -> None:
        """Placed in the middle before it is first drawn: docked, it would be drawn at the top
        left until laid out, so its size is worked out from its table here.
        """
        screen = self.screen.size
        width = min(_WIDTH, screen.width)
        console = self.app.console
        lines = console.render_lines(self._table, console.options.update_width(width - 4))
        height = min(len(lines) + _FRAME_ROWS, screen.height)
        self.styles.offset = ((screen.width - width) // 2, (screen.height - height) // 2)
