"""Parent markers in the persistent indicator strip and the column layout's fixed slot."""

from rich.text import Text

from ..tables import layout


def _label(children: int) -> Text:
    return Text(f"\u2193{children}" if children else "", style="dim not bold")


def indicators(children: int, emoji: str, pin: Text) -> Text:
    return Text(" ").join(part for part in (_label(children), Text(emoji), pin) if part.plain)


def columns(cells: list[Text], children: int, width: int, gutter: int) -> list[Text]:
    if not width:
        return cells

    name = cells[layout.NAME_CELL]
    marker = _label(children)
    return [
        name[:gutter] + marker + Text(" " * (width - marker.cell_len)) + name[gutter:]
        if i == layout.NAME_CELL
        else cell
        for i, cell in enumerate(cells)
    ]
