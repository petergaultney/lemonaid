import dataclasses

from lemonaid.groups.store import Group
from lemonaid.grove.draw import colors
from lemonaid.grove.source import blocks, inputs
from lemonaid.inbox import db

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
