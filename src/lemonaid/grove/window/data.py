"""What the grove window shows, and the changes it asks for: jumping, and gardening its blocks,
trees and bare trees.

Reads the live grove without saving anything; only a dropped tree writes the layout, through
the same rule `lemonaid grove plant` follows.
"""

import subprocess
from collections import abc

from ... import go, handlers
from ...config import Config
from ...inbox import db, ended
from ...lemon_watchers.common import detect_terminal_switch_source
from .. import as_json
from ..draw import bars, tree_stats
from ..layout import arrange, edit, state, tangles
from ..model import Block
from ..source import live
from ..tui import drop, frame, garden, keys
from ..tui.frame import Grove
from . import roads


def load(config: Config) -> Grove:
    source = detect_terminal_switch_source()
    return live.preview(config, None if source == "unknown" else source)


def shown(grove: Grove) -> dict:
    """The grove as `grove show --json` gives it, with roads as the window draws them, and the
    terminal grove's top bar: its summary, and its attention chips as runs of [text, color, fill, bold]."""
    houses = [p for p in grove.arrangement.plots.values() if p.texture == "house"]
    shown = as_json.grove(grove.blocks, grove.arrangement)
    for block, drawn in zip(grove.blocks, shown["blocks"], strict=True):
        for tree, tree_drawn in zip(block.trees, drawn["trees"], strict=True):
            tree_drawn["stats"] = tree_stats.line(tree) if tree.lemons else ""  # the flip key's tag
    return shown | {
        "roads": roads.drawn(grove.arrangement.roads, houses),
        "summary": frame.summary(grove),
        "attention": bars.chips(frame.attention(grove)),
    }


def search(grove: Grove, text: str) -> list[dict]:
    """The lemons the terminal grove's `/` finds for *text*, best first, each by its block's digit,
    its tree's key and letter, and its place on the tree."""
    return [
        {
            "digit": match.block.digit,
            "key": match.tree.key,
            "letter": grove.arrangement.trees[(match.block.name, match.tree.key)].letter,
            "index": match.tree.lemons.index(match.lemon),
            "channel": match.lemon.channel,
        }
        for match in keys.matches(grove.blocks, text)
    ]


def _pane_gone(found: db.Notification) -> bool:
    """Whether the tmux pane the lemon ran in is known to be gone, which resuming it replaces;
    a pane that can't be checked isn't."""
    tty = found.metadata.get("tty")
    return (
        not tty
        or handlers.check_pane_exists_by_tty(
            tty, "tmux", found.metadata.get("tmux_socket"), found.created_at
        )
        is False
    )


def jump(channel: str, client: str, config: Config) -> str:
    """Bring the lemon on *channel* to the front; returns why it couldn't, or "". A tmux lemon
    the terminal grove could jump to switches tmux *client*, the one the window was summoned over;
    one whose pane is gone is resumed by its front end, as the inbox resumes it, but not one lost
    with its tmux server (`lemonaid restore` brings those back) or one whose pane is there but
    can't be told apart. A lemon in WezTerm or cmux is shown by its front end."""
    with db.connect() as conn:
        found = db.get_by_channel(conn, channel, unread_only=False)
    if found is None:
        return f"No live lemon on {channel}"

    name = found.name or channel
    try:
        if found.switch_source == "tmux":
            problem = go.jump_problems([found]).get(channel, "")
            if not problem:
                go.jump_tmux(found, client)
                return ""
            if ended.lost(found.metadata) or not _pane_gone(found):
                return f"Can't jump to {name}: {problem}"

        metadata = {**found.metadata, "channel": channel}
        shown = handlers.handle_notification(metadata, config, switch_source=found.switch_source)
    except (LookupError, ValueError, OSError, subprocess.SubprocessError) as error:
        return f"Could not switch to {name}: {error}"
    return "" if shown else f"Could not switch to {name}"


def refusal(grove: Grove, digit: str, key: str, x: int, y: int) -> str:
    """Why tree *key* of block *digit* can't stand at (*x*, *y*) in its plot, or "": the spot itself,
    then everything saving it checks, such as a lead tree standing nearest the packhouse, judged on a
    copy of the layout the window drew."""
    block = next((b for b in grove.blocks if b.digit == digit), None)
    if block is None or not any(t.key == key for t in block.trees):
        return "that tree is gone"
    if grove.arrangement.plots[block.name].texture == "house":
        return "the packhouse's bays stay in order"

    problem = tangles.refusal_at(block, grove.arrangement, key, x, y)
    if problem:
        return problem

    try:
        tangles.plant(grove.blocks, grove.saved, block, {key: (x, y)})
    except edit.EditError as error:
        return str(error)
    return ""


def plant(grove: Grove, digit: str, key: str, x: int, y: int) -> str:
    """Stand the tree at (*x*, *y*) in the live layout; returns why it didn't, or ""."""
    problem = refusal(grove, digit, key, x, y)
    if problem:
        return problem

    block = next(b for b in grove.blocks if b.digit == digit)

    def stand(saved: dict) -> dict:
        # The window reads without saving, so a tree no grove has saved yet has a spot only once
        # the saved layout is arranged with today's blocks, here, under the layout's lock.
        laid_out = arrange.arrange(grove.blocks, saved)[1]
        return tangles.plant(grove.blocks, laid_out, block, {key: (x, y)})

    try:
        state.update(stand)
    except edit.EditError as error:
        return str(error)
    return ""


_SIDES = frozenset({"left", "right", "top", "bottom"})


def _block_drag(
    grove: Grove, digit: str, sides: abc.Iterable[str], dx: int, dy: int
) -> garden.Drag:
    """The terminal grove's drag of block *digit*, or of open ground `open:N`, by (*dx*, *dy*) grove
    units: its *sides*, or all of it when there are none. Terrain is judged a cell per grove unit."""
    sides = frozenset(sides) & _SIDES
    if digit.startswith("open:"):
        index = int(digit.removeprefix("open:"))
        was = grove.arrangement.open[index]
        return garden.Drag(
            Block("", "", "", ()), "", sides, (0, 0), (1.0, 1.0), (dx, dy), open=index, open_was=was
        )
    block = next(b for b in grove.blocks if b.digit == digit)
    return garden.Drag(block, "", sides, (0, 0), (1.0, 1.0), moved=(dx, dy))


def _gone(grove: Grove, digit: str) -> bool:
    if digit.startswith("open:"):
        index = digit.removeprefix("open:")
        return not index.isdigit() or int(index) >= len(grove.arrangement.open)
    return not any(b.digit == digit for b in grove.blocks)


def block_refusal(grove: Grove, digit: str, sides: abc.Iterable[str], dx: int, dy: int) -> str:
    """Why block *digit* can't be moved, or its *sides* dragged, by (*dx*, *dy*), or ""."""
    if _gone(grove, digit):
        return "that block is gone"

    return drop.refused(grove, _block_drag(grove, digit, sides, dx, dy))


def reframe(grove: Grove, digit: str, sides: abc.Iterable[str], dx: int, dy: int) -> str:
    """Move block *digit*, or drag its *sides*, by (*dx*, *dy*) in the live layout; returns why
    it didn't, or ""."""
    problem = block_refusal(grove, digit, sides, dx, dy)
    if problem:
        return problem

    dropped = drop.drop(grove, _block_drag(grove, digit, sides, dx, dy))
    try:
        # As in `plant`: a block no grove has saved yet gets its plot from arranging, under the lock.
        state.update(lambda saved: dropped(arrange.arrange(grove.blocks, saved)[1]))
    except edit.EditError as error:
        return str(error)
    return ""


def _stump_drag(grove: Grove, digit: str, key: str, dx: int, dy: int) -> garden.Drag:
    """The terminal grove's drag of the bare tree left by tree *key* of block *digit*."""
    block = next(b for b in grove.blocks if b.digit == digit)
    return garden.Drag(block, key, frozenset(), (0, 0), (1.0, 1.0), moved=(dx, dy), stump=True)


def stump_refusal(grove: Grove, digit: str, key: str, dx: int, dy: int) -> str:
    """Why the bare tree left by tree *key* of block *digit* can't be moved by (*dx*, *dy*), or "".
    A move off its block's ground clears it, and is never refused."""
    block = next((b for b in grove.blocks if b.digit == digit), None)
    if block is None or not any(s.key == key for s in grove.arrangement.stumps.get(block.name, ())):
        return "that bare tree is gone"

    return drop.refused(grove, _stump_drag(grove, digit, key, dx, dy))


def stump_drop(grove: Grove, digit: str, key: str, dx: int, dy: int) -> str:
    """Move the bare tree by (*dx*, *dy*) in the live layout, or clear it when that's off its
    block's ground; returns why it didn't, or ""."""
    problem = stump_refusal(grove, digit, key, dx, dy)
    if problem:
        return problem

    try:
        # Against the layout as saved, not as this snapshot would arrange it: a tree that came back
        # since is live there, and the terminal grove's save refuses to move or clear its spot.
        state.update(drop.drop(grove, _stump_drag(grove, digit, key, dx, dy)))
    except edit.EditError as error:
        return str(error)
    return ""
