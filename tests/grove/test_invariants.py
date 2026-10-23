"""What must hold for any grove, checked over many seeded random ones as they change.

Each scenario lays out a grove, then lets sessions arrive, leave, grow and be renamed over
several arrangements, saving the layout between them as the inbox does.
"""

import dataclasses
import functools
import itertools
import random

import pytest

from lemonaid.grove.draw import canvas, scene_parts
from lemonaid.grove.layout import arrange, room
from lemonaid.grove.model import Block, Lemon, Tree
from lemonaid.grove.tui import keys
from lemonaid.grove.tui.frame import Grove, render

from .shared import NOW, lemon

_WORDS = ["stray", "Stray", "spatial", "Spatial", "élan", "inbox", "cards", "s", "lemon", "Lead"]
_KEYS = ["~lead", ":x", "sess", "tars/core", "tars/ops", "edi/837", "q", "Q"]
_LETTERS = set("abcdefghijklmnopqrstuvwxyz")


def _name(rng: random.Random) -> str:
    return " ".join(rng.choice(_WORDS) for _ in range(rng.randint(1, 3)))


def _tree(rng: random.Random, key: str, lead: bool, serial: list[int]) -> Tree:
    def one() -> Lemon:
        serial[0] += 1
        made = lemon(f"claude:{key}-{serial[0]}", born=NOW - rng.randint(0, 5) * 86400)
        if rng.random() < 0.4:
            made = dataclasses.replace(made, name=_name(rng), named=True)
        return made

    return Tree(key, key, tuple(one() for _ in range(rng.randint(1, 6))), lead)


def _blocks(rng: random.Random, trees: dict[str, dict[str, Tree]]) -> tuple[Block, ...]:
    return tuple(
        Block(name, str(i) if name else "0", "#6495ed", tuple(group.values()))
        for i, (name, group) in enumerate(trees.items(), start=1)
        if group
    )


def _change(rng: random.Random, trees: dict[str, dict[str, Tree]], serial: list[int]) -> None:
    for name, group in trees.items():
        for key in list(group):
            if rng.random() < 0.15 and not group[key].lead:
                del group[key]  # a session ends
            elif rng.random() < 0.2:
                grown = _tree(rng, key, group[key].lead, serial)
                group[key] = dataclasses.replace(grown, lemons=group[key].lemons + grown.lemons[:2])
        if rng.random() < 0.4:
            key = f"{rng.choice(_KEYS)}-{name}-{serial[0]}"
            group[key] = _tree(rng, key, False, serial)  # a session starts


@functools.cache  # each test reads the same scenarios; building them is the slow part
def _scenario(seed: int) -> tuple[Grove, ...]:
    rng = random.Random(seed)
    serial = [0]
    trees: dict[str, dict[str, Tree]] = {}
    for name in [f"group {i}" for i in range(rng.randint(1, 4))] + [""]:
        keys_here = rng.sample(_KEYS, rng.randint(1, 5))
        lead = rng.choice(keys_here) if name and rng.random() < 0.7 else ""
        trees[name] = {
            f"{key}-{name}": _tree(rng, f"{key}-{name}", key == lead, serial) for key in keys_here
        }
    saved: dict = {"plots": {}, "trees": {}}
    groves = []
    for step in range(5):
        found = _blocks(rng, trees)
        arrangement, saved = arrange.arrange(found, saved, NOW + step * 3600)
        groves.append(Grove(found, arrangement))
        _change(rng, trees, serial)
    return tuple(groves)


SEEDS = range(25)


@pytest.mark.parametrize("seed", SEEDS)
def test_every_lemon_has_its_own_key_and_the_key_reaches_it(seed):
    for grove in _scenario(seed):
        names = keys.names(grove.blocks, grove.arrangement)
        lemons = [m.channel for b in grove.blocks for t in b.trees for m in t.lemons]
        assert sorted(names) == sorted(lemons)
        assert len(set(names.values())) == len(names), names
        for channel, key in names.items():
            where, chosen = keys.Where(), ""
            for character in key:
                where, chosen = keys.step(where, character, grove.blocks, grove.arrangement)
            if not chosen:  # `1` on a tree of ten or more waits for Enter, in case of `10`
                where, chosen = keys.step(where, "enter", grove.blocks, grove.arrangement)
            assert chosen == channel, (key, channel)


@pytest.mark.parametrize("seed", SEEDS)
def test_tree_letters_are_lowercase_unique_and_l_is_the_lead(seed):
    for grove in _scenario(seed):
        for block in grove.blocks:
            letters = [grove.arrangement.trees[(block.name, t.key)].letter for t in block.trees]
            assert set(letters) <= _LETTERS, letters
            assert len(set(letters)) == len(letters), letters
            for tree, letter in zip(block.trees, letters, strict=True):
                assert (letter == "l") == tree.lead, (tree.key, letter)


@pytest.mark.parametrize("seed", SEEDS)
def test_a_tree_that_stays_keeps_its_place_letter_and_bay(seed):
    groves = _scenario(seed)
    for before, after in itertools.pairwise(groves):
        for (group, key), was in before.arrangement.trees.items():
            now = after.arrangement.trees.get((group, key))
            if now is None:
                continue

            # On the ground: a plot that grows left or up moves its corner, not its trees.
            then_plot, now_plot = before.arrangement.plots[group], after.arrangement.plots[group]
            assert (now_plot.x + now.cx, now_plot.y + now.cy, now.letter, now.bay) == (
                then_plot.x + was.cx,
                then_plot.y + was.cy,
                was.letter,
                was.bay,
            )


@pytest.mark.parametrize("seed", SEEDS)
def test_no_tree_stands_on_another(seed):
    for grove in _scenario(seed):
        for block in grove.blocks:
            if grove.arrangement.plots[block.name].texture == "house":
                continue  # the packhouse draws bays, not trees

            stands = {t.key: grove.arrangement.trees[(block.name, t.key)] for t in block.trees}
            assert not room.tangled(
                (t, room.footprint(t, s.label, s.letter, s.size, s.cx, s.cy))
                for t in sorted(block.trees, key=lambda t: (not t.lead, t.born, t.key))
                for s in [stands[t.key]]
            ), block.name


@pytest.mark.parametrize("seed", SEEDS[:8])
@pytest.mark.parametrize("size", [(210, 62), (120, 40)])
def test_every_tree_shows_its_letter_where_a_click_reaches_it(seed, size):
    for grove in _scenario(seed)[::2]:
        whole = (
            [keys.Where()] if not scene_parts.pans(canvas.blank(*size), grove.arrangement) else []
        )
        views = [*whole, *(keys.Where(block=b.digit, digits=b.digit) for b in grove.blocks)]
        for where in views:
            picture = render(grove, where, *size, 0.5)
            shown = {
                (cell.target, cell.char)
                for row in picture.rows
                for cell in row
                if len(cell.target) == 2
            }
            for block in grove.blocks:
                if where.block and where.block != block.digit:
                    continue
                for tree in block.trees:
                    letter = grove.arrangement.trees[(block.name, tree.key)].letter
                    target = (block.digit, letter)
                    assert (target, letter) in shown, (where.block or "overview", tree.key)


def test_a_scenario_is_the_same_every_time():
    first, again = _scenario.__wrapped__(7), _scenario.__wrapped__(7)
    assert [g.arrangement.trees for g in first] == [g.arrangement.trees for g in again]
    assert canvas.plain_lines(render(first[0], keys.Where(), 160, 48, 0.5)) == canvas.plain_lines(
        render(again[0], keys.Where(), 160, 48, 0.5)
    )
