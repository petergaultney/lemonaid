"""Status badges, `?4` as a glyph and a count in the status's color, and the bar that lays them out.

Imports nothing from `inbox.tui`, so the grove can draw the bar without loading the inbox's app.
"""

from collections import abc

from rich.style import Style
from rich.text import Text

from .. import config, status_registry

_STATES = ("active", "idle", "deaf", "dead", "")  # after the statuses, for a brief with none
_FIXED_SLOT = 5  # a two-digit badge: glyph, two digits, a cell either side


def glyphs() -> dict[str, str]:
    """Each configured status's badge glyph, in slot order."""
    return {s.name: s.glyph for s in config.brief_statuses()}


def has_badge(status: str) -> bool:
    return status in glyphs()


def order() -> tuple[str, ...]:
    """Where each status's count sits; any other word follows these, by name."""
    return (*status_registry.names(config.brief_statuses()), *_STATES)


def badge(status: str, count: int) -> Text:
    """*count* lemons of *status* as its glyph and number, filled with the status's color."""
    found = status_registry.by_name(config.brief_statuses()).get(status)
    fill = Style(color=found.on_fill, bgcolor=found.fill) if found else Style()
    return Text(f" {glyphs()[status]}{count} ", fill + Style(bold=True, underline=False))


def fixed(every: abc.Mapping[str, int]) -> Text:
    """*every* as badges in slots that hold a two-digit count, so none moves as counts change."""
    shown = [s for s in order() if has_badge(s)]
    marks = {s: badge(s, every[s]) for s in shown if every.get(s)}
    slot = max([_FIXED_SLOT, *(m.cell_len for m in marks.values())])
    plain = sum(n for s, n in every.items() if not has_badge(s))
    return Text.assemble(
        *(
            Text(" " * (slot - marks[s].cell_len)) + marks[s] if s in marks else " " * slot
            for s in shown
        ),
        Text(f" ○{plain}", "dim") if plain else "",
    )
