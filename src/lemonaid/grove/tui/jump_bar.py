"""A one-line bar over the inbox that takes the rest of a grove key typed there, as `5s`."""

from textual import events
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static

from . import keys
from .frame import Grove


def _line(where: keys.Where, grove: Grove) -> str:
    if where.note:
        return f"{where.note} · esc cancels"

    block = next((b for b in grove.blocks if b.digit == where.block), None)
    if block is None:
        return "type a block number · esc cancels"
    if where.tree:
        return f"{where.block}{where.tree}: the lemon's number {where.number}"

    trees = "  ".join(
        f"{grove.arrangement.trees[(block.name, t.key)].letter} "
        f"{grove.arrangement.trees[(block.name, t.key)].label}"
        for t in block.trees
    )
    return f"{block.digit} {block.name or 'no group'}: {trees}"


class JumpBar(ModalScreen[str]):
    """Dismisses with the chosen lemon's channel, or "" when cancelled."""

    DEFAULT_CSS = """
    JumpBar { background: transparent; }
    JumpBar > Static { dock: bottom; height: 1; width: 100%; background: #1d2333; color: #e6ebf2; }
    """

    def __init__(self, grove: Grove, first: str) -> None:
        super().__init__()
        self._grove = grove
        self._where, _ = keys.step(keys.Where(), first, grove.blocks, grove.arrangement)

    def compose(self) -> ComposeResult:
        yield Static(_line(self._where, self._grove))

    def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()
        if event.key == "escape" and not self._where.tree:
            self.dismiss("")
            return

        key = (
            event.character
            if event.character and event.character.isprintable() and len(event.character) == 1
            else event.key
        )
        self._where, channel = keys.step(
            self._where, key, self._grove.blocks, self._grove.arrangement
        )
        if channel:
            self.dismiss(channel)
            return
        if self._where == keys.Where():
            self.dismiss("")
            return

        self.query_one(Static).update(_line(self._where, self._grove))
