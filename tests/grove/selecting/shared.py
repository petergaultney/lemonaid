import dataclasses

from lemonaid.grove.layout import arrange
from lemonaid.grove.tui import selecting
from lemonaid.grove.tui.keys import Where

from ..shared import NOW, block, lemon, tree


def _in(session: str, *lemons):
    return tree(session, *(dataclasses.replace(m, session=session) for m in lemons))


BIG = _in("core", lemon("claude:a", "SwordAce"), lemon("codex:b", "WagonCoy"), lemon("codex:c"))
LOOSE = tree("/work/notes", lemon("claude:notes"))
OTHER = _in("other", lemon("claude:o"))
BLOCKS = (block("oria", "1", BIG, LOOSE), block("relay", "2", OTHER))
ARRANGEMENT, _ = arrange.arrange(BLOCKS, {"plots": {}, "trees": {}}, NOW)
CORE = ARRANGEMENT.trees[("oria", "core")].letter
NOTES = ARRANGEMENT.trees[("oria", "/work/notes")].letter


def press(*typed: str, where: Where | None = None, blocks=BLOCKS, arrangement=ARRANGEMENT):
    where, channel, target = where or Where(), "", None
    for key in typed:
        where, channel, target = selecting.step(where, key, blocks, arrangement)
    return where, channel, target
