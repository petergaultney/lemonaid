"""Which lemon a brief card is: its task, Lemon-ID and parent, as lines of the card."""

from rich.console import Console
from rich.text import Text

from ...brief import render

_CONSOLE = Console()  # for measuring wraps only; nothing is printed through it


def _parent(section: render.Section) -> Text:
    line = Text("Parent: ", style="dim")
    if section.parent_name:
        line.append(section.parent_name)
        line.append(" (")

    line.append(id_text(section.parent))
    if section.parent_name:
        line.append(")")

    return line


def id_text(brief_id: str, label: str = "") -> Text:
    line = Text(label, style="dim")
    description, separator, name = brief_id.rpartition(".")
    if separator and name:
        line.append(description, style="dim")
        line.append(".", style="dim")
        line.append(name, style="bold")
    else:
        line.append(brief_id, style="dim")

    return line


def lines(section: render.Section, width: int) -> list[Text]:
    """The task in bold, then the Lemon-ID and parent, wrapped to *width*.

    A compact section puts the Lemon-ID and parent on one line. A section
    without a lemon names its task in the card's headline instead.
    """
    lemon_id = id_text(section.lemon_id, "Brief-ID: ") if section.lemon_id else None
    parent = _parent(section) if section.parent else None
    ids = [line for line in (lemon_id, parent) if line]
    unwrapped = [
        *([Text(section.title, style="bold")] if section.lemon and section.title else []),
        *([Text(" · ", style="dim").join(ids)] if section.compact and ids else ids),
    ]
    wrapped = [w for line in unwrapped for w in line.wrap(_CONSOLE, max(1, width))]
    return wrapped if section.compact or not wrapped else [Text(""), *wrapped, Text("")]
