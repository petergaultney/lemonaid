import dataclasses

from lemonaid.groups.store import Group
from lemonaid.grove.draw import colors
from lemonaid.grove.source import blocks, inputs
from lemonaid.inbox import context_use, db
from lemonaid.inbox.tui.rows import pr_numbers

from .shared import lemon as shared_lemon


def notification(channel: str, session: str) -> db.Notification:
    return db.Notification(
        id=hash(channel) % 1000,
        channel=channel,
        message="",
        name=channel,
        metadata={"tmux_session": session, "cwd": "/work"},
        switch_source="tmux",
    )


def read(
    rows: list[db.Notification],
    memberships: dict[str, tuple[str, ...]],
    parents: dict[str, str] | None = None,
    numbers: dict[str, tuple[pr_numbers.PR, ...]] | None = None,
) -> inputs.Inputs:
    return inputs.Inputs(
        rows=rows,
        cards={},
        memberships=memberships,
        groups=[
            Group(1, "oria", 10.0, (), color="#6495ed"),
            Group(2, "relay", 20.0, (), color="#2fb5a5"),
        ],
        pinned=frozenset(),
        emojis={},
        lemon_ids={},
        parents=parents or {},
        births={},
        hidden=frozenset(),
        numbers=numbers or {},
    )


def test_lemons_in_one_terminal_session_share_a_tree():
    rows = [notification("claude:a", "tars/core"), notification("codex:b", "tars/core")]
    (oria,) = blocks.blocks(read(rows, {"claude:a": ("oria",), "codex:b": ("oria",)}), {})
    assert [len(t.lemons) for t in oria.trees] == [2]


def test_a_lemon_in_two_groups_stands_in_the_first():
    rows = [notification("claude:a", "x")]
    found = blocks.blocks(read(rows, {"claude:a": ("relay", "oria")}), {})
    assert [(b.name, b.digit) for b in found] == [("relay", "1")]


def test_lemons_in_no_group_stand_in_block_zero():
    rows = [notification("claude:a", "x"), notification("claude:b", "y")]
    found = blocks.blocks(read(rows, {"claude:a": ("oria",)}), {})
    assert [(b.name, b.digit) for b in found] == [("oria", "1"), ("", "0")]


def test_hq_leads_the_packhouse_though_its_children_are_in_groups():
    rows = [
        notification("claude:hq", "hq"),
        notification("claude:x", "x"),
        notification("claude:kid", "k"),
    ]
    found = blocks.blocks(read(rows, {"claude:kid": ("oria",)}, {"claude:kid": "claude:hq"}), {})
    packhouse = found[-1]
    assert [t.lead for t in packhouse.trees if t.key == "hq"] == [True]


def test_a_tree_of_done_and_idle_lemons_shows_done():
    finished = dataclasses.replace(shared_lemon("claude:a"), status="done")
    assert colors.tree_status((finished, shared_lemon("claude:b"))) == "done"
    merging = dataclasses.replace(shared_lemon("claude:c"), status="merge")
    assert colors.tree_status((finished, merging)) == "merge"


def test_a_context_reading_far_past_its_threshold_is_capped_as_the_inbox_caps_it():
    n = dataclasses.replace(
        notification("claude:a", "s"),
        metadata={"tmux_session": "s", "context_tokens": 10_050, "model": "opus"},
    )
    thresholds = {"claude": context_use.Threshold(tokens=1000)}
    assert blocks._context(n, thresholds) == "999%"


def test_a_lemon_knows_its_branch_prs_and_age():
    n = dataclasses.replace(
        notification("codex:a", "x"),
        metadata={"cwd": "/work/x", "git_branch": "grove/x", "model": "gpt-6.1-sol"},
        created_at=1000.0,
    )
    numbers = {
        "codex:a": (pr_numbers.PR("411", "https://github.com/o/r/pull/411"), pr_numbers.PR("409"))
    }
    (found,) = blocks.blocks(read([n], {}, numbers=numbers), {}, now=1000.0 + 240)
    (lemon,) = found.trees[0].lemons
    assert (lemon.branch, lemon.cwd, lemon.prs, lemon.age, lemon.model) == (
        "grove/x",
        "/work/x",
        (("411", "https://github.com/o/r/pull/411"), ("409", "")),
        "4m ago",
        "Sol 6.1",
    )
