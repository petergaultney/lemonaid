"""Family relationships in the persistent indicator strip and the column layout's fixed slot."""

from rich.text import Text

from ..tables import layout

PARENT = "\u2193"
CHILD = "\u2191"
LEAD = "\u265b"  # ♛, the member with the most descendants in the group the row is drawn under


def _label(children: int, visible: int | None) -> Text:
    count = str(children) if visible is None or visible == children else f"{visible}/{children}"
    return Text(f"\u2193{count}" if children else "", style="dim not bold")


def indicators(
    children: int,
    emoji: str,
    pin: Text,
    visible: int | None = None,
    family: str | None = None,
    lead: bool = False,
) -> Text:
    relationship = (
        Text({"parent": PARENT, "child": CHILD}.get(family, " "), style="bold not dim")
        if family is not None
        else Text()
    )
    return Text(" ").join(
        part
        for part in (
            relationship,
            Text(LEAD if lead else ""),
            _label(children, visible),
            Text(emoji),
            pin,
        )
        if part.plain
    )


def columns(
    cells: list[Text],
    children: int,
    width: int,
    gutter: int,
    visible: int | None = None,
    family: str | None = None,
    lead: bool = False,
) -> list[Text]:
    if not width:
        return cells

    name = cells[layout.NAME_CELL]
    marker = indicators(children, "", Text(), visible, family, lead)
    return [
        name[:gutter] + marker + Text(" " * max(0, width - marker.cell_len)) + name[gutter:]
        if i == layout.NAME_CELL
        else cell
        for i, cell in enumerate(cells)
    ]
