from lemonaid.grove.layout import arrange
from lemonaid.grove.tui import picking

from .selecting.shared import BLOCKS, CORE, _in, press
from .shared import NOW, block, lemon


def test_a_whole_tree_rename_names_its_session_from_its_current_name():
    where, _, rename = press("tab", "1", "$", CORE, "r")
    assert rename == picking.Target(
        "rename",
        "oria",
        ("oria",),
        "core",
        "",
        "core",
        (("claude:a", ""), ("codex:b", ""), ("codex:c", "")),
    )
    assert picking.prompt(where, BLOCKS) == "renaming tmux session core"


def test_a_lemons_rename_starts_from_its_name_and_the_prompt_names_it():
    where, _, rename = press("tab", "1", CORE, "r")
    assert (rename.channel, rename.name) == ("claude:a", "lemon claude:a")
    assert picking.prompt(where, BLOCKS) == "renaming lemon SwordAce"


def test_a_session_rename_covers_its_trees_in_every_group():
    shared = (
        block("a", "1", _in("old", lemon("claude:x"))),
        block("b", "2", _in("old", lemon("claude:y"))),
    )
    found, _ = arrange.arrange(shared, {"plots": {}, "trees": {}}, NOW)
    letter = found.trees[("a", "old")].letter
    _, _, rename = press("tab", "1", "$", letter, "r", blocks=shared, arrangement=found)
    assert rename.groups == ("a", "b")
    assert rename.lemons == (("claude:x", ""), ("claude:y", ""))


def test_whole_tree_edits_carry_every_lemon_on_the_tree():
    where, _, target = press("tab", "1", "$", CORE, "p")
    assert (target.action, target.channel) == ("pin", "")
    assert [channel for channel, _ in target.lemons] == ["claude:a", "codex:b", "codex:c"]
    assert picking.prompt(where, BLOCKS) == "pinning or unpinning all 3 lemons on core"


def test_the_packhouse_has_no_color():
    house = _in("hq", lemon("claude:hq"))
    packhouse = (block("", "0", house),)
    found, _ = arrange.arrange(packhouse, {"plots": {}, "trees": {}}, NOW)
    letter = found.trees[("", "hq")].letter
    where, _, target = press("tab", "0", letter, "c", blocks=packhouse, arrangement=found)
    assert target is None and "no color" in where.note
