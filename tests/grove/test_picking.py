import dataclasses

from lemonaid.grove.layout import arrange
from lemonaid.grove.tui import picking

from .selecting.shared import ARRANGEMENT, BLOCKS, CORE, NOTES, _in, press
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


def test_a_graft_offers_each_other_trees_main_lemon_its_own_block_first():
    where, _, target = press("tab", "1", NOTES, "t")
    other = ARRANGEMENT.trees[("relay", "other")]
    assert target.trees == (
        ("claude:a", f"1{CORE} {ARRANGEMENT.trees[('oria', 'core')].label}"),
        ("claude:o", f"2{other.letter} {other.label}"),
    )
    assert picking.prompt(where, BLOCKS) == "grafting lemon lemon claude:notes"


def test_a_grafted_lemon_can_go_back_and_a_session_rename_leaves_it_where_it_runs():
    guest = dataclasses.replace(
        lemon("claude:g"), session="elsewhere", grafted_onto="SwordAce.core"
    )
    core = _in("core", lemon("claude:a", "SwordAce"))
    grafted = (block("oria", "1", dataclasses.replace(core, lemons=(*core.lemons, guest))),)
    found, _ = arrange.arrange(grafted, {"plots": {}, "trees": {}}, NOW)
    letter = found.trees[("oria", "core")].letter
    _, _, back = press("tab", "1", ".", letter, "1", "t", blocks=grafted, arrangement=found)
    assert back.trees == (("", "back to its own tree"),)
    _, _, rename = press("tab", "1", "$", letter, "r", blocks=grafted, arrangement=found)
    assert rename.lemons == (("claude:a", ""),)


def test_a_session_rename_covers_lemons_running_there_that_a_graft_draws_elsewhere():
    a = dataclasses.replace(lemon("claude:a"), grafted_onto="claude:c")
    old = _in("old", lemon("claude:b"))
    other = _in("other", lemon("claude:c"))
    other = dataclasses.replace(
        other, lemons=(*other.lemons, dataclasses.replace(a, session="old"))
    )
    same = dataclasses.replace(lemon("claude:s"), session="old", grafted_onto="claude:b")
    old = dataclasses.replace(old, lemons=(*old.lemons, same))
    grafted = (block("oria", "1", old, other),)
    found, _ = arrange.arrange(grafted, {"plots": {}, "trees": {}}, NOW)
    letter = found.trees[("oria", "old")].letter
    _, _, rename = press("tab", "1", "$", letter, "r", blocks=grafted, arrangement=found)
    assert sorted(channel for channel, _ in rename.lemons) == ["claude:a", "claude:b", "claude:s"]


def test_an_edit_in_block_0_names_its_home_group():
    home = dataclasses.replace(block("", "0", _in("m", lemon("claude:meyer"))), home="meyer")
    found, _ = arrange.arrange((home,), {"plots": {}, "trees": {}}, NOW)
    letter = next(s.letter for (_, key), s in found.trees.items())
    _, _, move = press("tab", "0", letter, "g", blocks=(home,), arrangement=found)
    assert (move.block, home.title) == ("meyer", "meyer")
