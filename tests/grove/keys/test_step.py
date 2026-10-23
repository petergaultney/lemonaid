from lemonaid.grove.layout import arrange
from lemonaid.grove.tui.keys import Where, step

from ..shared import NOW, block, lemon, tree

AUTHOR, REVIEWER = lemon("claude:author", "SwordAce"), lemon("codex:reviewer", "WagonCoy")
BIG = tree("tars/postgres-core", AUTHOR, REVIEWER, lemon("codex:third", "GlobeAim"))
PAIR = tree(
    "tars/postgres-ops", lemon("claude:ops", "CycleKeg"), lemon("codex:ops-review", "VoiceSay")
)
LEAD = tree("tars/postgres-report", lemon("claude:lead", "DizzyWin"), lead=True)
BLOCKS = (
    block("oria-postgres", "1", LEAD, BIG, PAIR),
    *(block(f"group-{n}", str(n), tree(f"t{n}")) for n in range(2, 12)),
)
ARRANGEMENT, _ = arrange.arrange(BLOCKS, {"plots": {}, "trees": {}}, NOW)


def letter(key: str) -> str:
    return ARRANGEMENT.trees[("oria-postgres", key)].letter


def press(*typed: str, where: Where | None = None) -> tuple[Where, str]:
    where, channel = where or Where(), ""
    for key in typed:
        where, channel = step(where, key, BLOCKS, ARRANGEMENT)
    return where, channel


def test_a_digit_zooms_to_its_block():
    assert press("1")[0].block == "1"


def test_a_second_digit_reaches_a_two_digit_block():
    assert press("1", "1")[0].block == "11"


def test_l_jumps_to_the_lead():
    assert letter("tars/postgres-report") == "l"
    assert press("1", "l")[1] == "claude:lead"


def test_a_capital_takes_a_trees_second_lemon():
    ops = letter("tars/postgres-ops")
    assert press("1", ops)[1] == "claude:ops"
    assert press("1", ops.upper())[1] == "codex:ops-review"


def test_a_tree_of_three_opens_and_a_number_picks():
    core = letter("tars/postgres-core")
    where, channel = press("1", core)
    assert where.tree == core and not channel
    assert press("3", where=where)[1] == "codex:third"


def test_escape_backs_out_one_level_at_a_time():
    where, _ = press("1", letter("tars/postgres-core"), "escape")
    assert where.block == "1" and not where.tree
    assert press("escape", where=where)[0] == Where()


def test_a_letter_before_a_block_explains_itself():
    where, channel = press("c")
    assert not channel and "block number" in where.note


def test_search_enter_jumps_to_the_brief_id_match():
    assert press("/", "w", "a", "g", "o", "n", "enter")[1] == "codex:reviewer"


def test_search_arrows_choose_among_matches():
    assert press("/", "o", "p", "s", "down", "enter")[1] == "codex:ops-review"


def test_enter_confirms_a_number_that_prefixes_a_longer_one():
    ten = tree("big", *(lemon(f"claude:big{i}") for i in range(1, 11)))
    blocks = (block("g", "1", ten),)
    arrangement, _ = arrange.arrange(blocks, {"plots": {}, "trees": {}}, NOW)
    where, channel = Where(), ""
    for key in ("1", arrangement.trees[("g", "big")].letter, "1", "enter"):
        where, channel = step(where, key, blocks, arrangement)
    assert channel == "claude:big1"


def test_escape_keeps_the_pan():
    assert press("escape", where=Where(pan=(40.0, 8.0)))[0].pan == (40.0, 8.0)
