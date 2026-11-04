from lemonaid.grove.layout import arrange
from lemonaid.grove.tui.keys import Where, step
from lemonaid.lemon_keys import lookup

from ..grove.shared import NOW, block, lemon, tree

AUTHOR, REVIEWER = lemon("claude:author", "SwordAce"), lemon("codex:reviewer", "WagonCoy")
PAIR = tree("tars/postgres-core", AUTHOR, REVIEWER)
BLOCKS = (
    block("oria-postgres", "1", PAIR, tree("tars/postgres-ops", lemon("claude:ops"))),
    block("lemonaid", "5", tree("wezterm", lemon("claude:wezterm", status="done"))),
)
ARRANGEMENT, _ = arrange.arrange(BLOCKS, {"plots": {}, "trees": {}}, NOW)
EVERYTHING = lookup.every(BLOCKS, ARRANGEMENT)
LETTER = ARRANGEMENT.trees[("oria-postgres", "tars/postgres-core")].letter


def channels(typed: str) -> list[str]:
    return [k.lemon.channel for k in lookup.resolve(EVERYTHING, typed)]


def test_a_tree_key_names_every_lemon_on_it_main_one_first():
    assert channels(f"1{LETTER}") == ["claude:author", "codex:reviewer"]


def test_a_dotted_key_names_one_lemon():
    assert channels(f"1.{LETTER}1") == ["codex:reviewer"]


def test_a_block_digit_names_the_whole_block():
    assert channels("1") == ["claude:author", "codex:reviewer", "claude:ops"]


def test_case_and_spaces_are_ignored():
    assert channels(f" 1{LETTER.upper()} ") == ["claude:author", "codex:reviewer"]


def test_an_unknown_key_names_nothing():
    assert channels("9z") == []


def test_each_key_reaches_the_lemon_typing_it_in_the_grove_reaches():
    for keyed in EVERYTHING:
        where, chosen = Where(), ""
        for key in keyed.key:
            where, chosen = step(where, key, BLOCKS, ARRANGEMENT)
        assert chosen == keyed.lemon.channel, keyed.key
