"""A one-line bar over the inbox that takes the rest of a grove key typed there, as `5s`."""

from rich.style import Style
from rich.text import Text
from textual import events
from textual.widgets import Static

from ..draw import colors
from ..model import Block
from . import keys
from .frame import Grove

_SIGN_TEXT = "#0b0e13"  # on a block's color, as on the grove's block signs


def _typed(block: Block, where: keys.Where) -> str:
    return block.digit + (f".{where.tree}{where.number}" if where.tree else "." * where.dot)


def _line(where: keys.Where, grove: Grove) -> Text:
    if where.note:
        return Text(f"{where.note} · esc closes")

    block = next((b for b in grove.blocks if b.digit == where.block), None)
    if block is None:
        return Text("type a block number · esc closes")

    if where.dot:
        hint = "the tree's letter"
    elif where.tree:
        hint = f"the lemon's {'letter' if where.number else 'place on the tree'}"
    else:
        hint = "  ".join(
            f"{grove.arrangement.trees[(block.name, t.key)].letter} "
            f"{grove.arrangement.trees[(block.name, t.key)].label}"
            for t in block.trees
        )
    return Text.assemble(
        (f" {_typed(block, where)} ", Style(color=_SIGN_TEXT, bgcolor=block.color, bold=True)),
        (f" {block.name or 'no group'}", Style(color=block.color, bold=True)),
        f"  {hint}",
    )


def key_name(event: events.Key) -> str:
    """A typed character as itself, which keeps its case; any other key by its name."""
    if event.character and event.character.isprintable() and len(event.character) == 1:
        return event.character
    return event.key


class JumpBar(Static):
    """A one-line bar the inbox shows while a grove key is typed; the inbox hands it each key
    first, so a key it doesn't take, and the mouse, act on the inbox as usual and in order.
    """

    DEFAULT_CSS = f"""
    JumpBar {{
        dock: bottom; height: 1; width: 100%; background: {colors.BAR}; color: {colors.TEXT};
        text-style: bold;
    }}
    """

    def __init__(self, grove: Grove, first: str) -> None:
        self._grove = grove
        self._where, _ = keys.step(keys.Where(), first, grove.blocks, grove.arrangement)
        super().__init__(_line(self._where, grove))

    @property
    def zoom(self) -> tuple[str, str]:
        """The block typed so far, and the letter of the tree after it, each "" until typed."""
        return self._where.block, self._where.tree

    def take(self, key: str) -> tuple[bool, str | None]:
        """Whether the bar takes *key*, and once it is done, the lemon chosen or "" (else None).
        A key the bar doesn't take closes it, for the inbox to act on.
        """
        if key == "escape":
            return True, ""
        if not keys.uses(self._where, key, self._grove.blocks, self._grove.arrangement):
            return False, ""

        self._where, channel = keys.step(
            self._where, key, self._grove.blocks, self._grove.arrangement
        )
        if channel:
            return True, channel
        if self._where == keys.Where():
            return True, ""

        self.update(_line(self._where, self._grove))
        return True, None
