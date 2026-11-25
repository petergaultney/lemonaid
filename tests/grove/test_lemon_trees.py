from lemonaid.grove.source import lemon_trees

from .shared import block, lemon, tree


def test_each_lemon_is_a_tree_and_a_session_s_main_lemon_keeps_its_key():
    author, reviewer = lemon("claude:author"), lemon("codex:reviewer")
    found = (block("g", "1", tree("misc"), tree("grove/work", author, reviewer, lead=True)),)

    (split,) = lemon_trees.one_per_lemon(found)

    assert [(t.key, t.branch, t.lead) for t in split.trees] == [
        ("grove/work", "grove/work", True),  # the lead's session first
        ("codex:reviewer", "grove/work", False),
        ("misc", "misc", False),
    ]
    assert [t.lemons for t in split.trees][:2] == [(author,), (reviewer,)]
    assert split.trees[1].label == reviewer.name
