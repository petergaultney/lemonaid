"""Family relationships in the persistent indicator strip and the column layout's fixed slot."""

from rich.text import Text

from ..tables import layout

PARENT = "\u2191"
CHILD = "\u2193"


def _label(children: int, visible: int | None) -> Text:
    count = str(children) if visible is None or visible == children else f"{visible}/{children}"
    return Text(f"\u2193{count}" if children else "", style="dim not bold")


def indicators(
    children: int, emoji: str, pin: Text, visible: int | None = None, family: str | None = None
) -> Text:
    relationship = (
        Text({"parent": PARENT, "child": CHILD}.get(family, " "), style="bold not dim")
        if family is not None
        else Text()
    )
    return Text(" ").join(
        part for part in (relationship, _label(children, visible), Text(emoji), pin) if part.plain
    )


def columns(
    cells: list[Text],
    children: int,
    width: int,
    gutter: int,
    visible: int | None = None,
    family: str | None = None,
) -> list[Text]:
    if not width:
        return cells

    name = cells[layout.NAME_CELL]
    marker = indicators(children, "", Text(), visible, family)
    return [
        name[:gutter] + marker + Text(" " * max(0, width - marker.cell_len)) + name[gutter:]
        if i == layout.NAME_CELL
        else cell
        for i, cell in enumerate(cells)
    ]
