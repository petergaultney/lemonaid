from lemonaid.grove.layout import arrange
from lemonaid.grove.tui.keys import Where, names, step

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


def test_a_trees_letter_takes_its_first_lemon_whatever_its_size():
    assert press("1", letter("tars/postgres-ops"))[1] == "claude:ops"
    assert press("1", letter("tars/postgres-core"))[1] == "claude:author"


def test_the_capital_and_a_place_take_the_rest():
    ops, core = letter("tars/postgres-ops"), letter("tars/postgres-core")
    assert press("1", ops.upper(), "2")[1] == "codex:ops-review"
    where, channel = press("1", core.upper())
    assert where.tree == core and not channel
    assert press("3", where=where)[1] == "codex:third"


def test_escape_backs_out_one_level_at_a_time():
    where, _ = press("1", letter("tars/postgres-core").upper(), "escape")
    assert where.block == "1" and not where.tree
    assert press("escape", where=where)[0] == Where()


def test_a_letter_before_a_block_explains_itself():
    where, channel = press("c")
    assert not channel and "block number" in where.note


def test_search_enter_jumps_to_the_brief_id_match():
    assert press("/", "w", "a", "g", "o", "n", "enter")[1] == "codex:reviewer"


def test_search_arrows_choose_among_matches():
    assert press("/", "o", "p", "s", "down", "enter")[1] == "codex:ops-review"


def _big(count: int):
    big = tree("big", *(lemon(f"claude:big{i}") for i in range(1, count + 1)))
    blocks = (block("g", "1", big),)
    return blocks, arrange.arrange(blocks, {"plots": {}, "trees": {}}, NOW)[0]


def _typed(blocks, arrangement, *keys: str) -> tuple[Where, str]:
    where, channel = Where(), ""
    for key in ("1", arrangement.trees[("g", "big")].letter.upper(), *keys):
        where, channel = step(where, key, blocks, arrangement)
    return where, channel


def test_a_single_digit_picks_a_lemon_at_once_whatever_the_trees_size():
    blocks, arrangement = _big(12)
    assert _typed(blocks, arrangement, "2")[1] == "claude:big2"
    assert _typed(blocks, arrangement, "9")[1] == "claude:big9"


def test_past_nine_a_lemon_is_0_and_a_letter():
    blocks, arrangement = _big(12)
    where, channel = _typed(blocks, arrangement, "0")
    assert not channel and where.number == "0"
    assert _typed(blocks, arrangement, "0", "a")[1] == "claude:big10"
    assert _typed(blocks, arrangement, "0", "c")[1] == "claude:big12"
    assert "no lemon 0d" in _typed(blocks, arrangement, "0", "d")[0].note


def test_0_is_no_lemon_on_a_tree_of_nine_or_fewer():
    blocks, arrangement = _big(9)
    assert "no lemon 0" in _typed(blocks, arrangement, "0")[0].note


def test_escape_keeps_the_pan():
    assert press("escape", where=Where(pan=(40.0, 8.0)))[0].pan == (40.0, 8.0)


def test_a_tree_past_0z_still_names_every_lemon_it_can():
    blocks, arrangement = _big(37)
    named = names(blocks, arrangement)
    assert len(named) == 35 and "claude:big36" not in named
