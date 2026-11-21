import dataclasses

from lemonaid.groups.store import Group
from lemonaid.grove.draw import colors
from lemonaid.grove.layout import arrange
from lemonaid.grove.source import blocks, inputs
from lemonaid.inbox import context_use, db
from lemonaid.inbox.tui.rows import pr_numbers

from .selecting.shared import press
from .shared import NOW
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


def _wezterm(channel: str, workspace: str, socket: str = "/tmp/gui") -> db.Notification:
    return dataclasses.replace(
        notification(channel, ""),
        metadata={
            "wezterm_pane": hash(channel) % 100,
            "wezterm_workspace": workspace,
            "wezterm_socket": socket,
            "cwd": "/work",
        },
        switch_source="wezterm",
    )


def test_wezterm_lemons_share_a_tree_by_workspace_not_by_directory():
    rows = [_wezterm("claude:a", "w1"), _wezterm("codex:b", "w1"), _wezterm("claude:c", "w2")]
    (oria,) = blocks.blocks(read(rows, {row.channel: ("oria",) for row in rows}), {})
    assert sorted((t.label, len(t.lemons)) for t in oria.trees) == [("w1", 2), ("w2", 1)]


def test_equal_names_in_tmux_and_two_wezterm_instances_stay_three_trees():
    rows = [
        notification("claude:t", "work"),
        _wezterm("claude:w", "work"),
        _wezterm("claude:v", "work", "/tmp/other-gui"),
    ]
    (oria,) = blocks.blocks(read(rows, {row.channel: ("oria",) for row in rows}), {})
    assert sorted(t.label for t in oria.trees) == ["work", "work", "work"]
    assert [t.key for t in oria.trees if t.lemons[0].session] == ["work"]


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


def test_a_grafted_lemon_hangs_after_its_hosts_tree_mates_until_its_host_goes():
    rows = [
        notification("claude:host", "richer"),
        notification("codex:mate", "richer"),
        notification("claude:guest", "window"),
    ]
    found = dataclasses.replace(
        read(rows, {row.channel: ("oria",) for row in rows}),
        lemon_ids={"claude:host": "SillyOil.richer"},
        grafts={"claude:guest": "SillyOil.richer"},
    )
    (oria,) = blocks.blocks(found, {})
    assert [(t.key, [m.channel for m in t.lemons]) for t in oria.trees] == [
        ("richer", ["claude:host", "codex:mate", "claude:guest"])
    ]
    assert oria.trees[0].lemons[2].grafted_onto == "SillyOil.richer"

    gone = dataclasses.replace(found, rows=rows[1:])
    (oria,) = blocks.blocks(gone, {})
    assert sorted(t.key for t in oria.trees) == ["richer", "window"]
    assert not any(m.grafted_onto for t in oria.trees for m in t.lemons)


def test_a_grafted_lead_comes_after_its_hosts_own_so_the_tree_still_renames_its_session():
    rows = [
        notification("claude:host", "host"),
        notification("claude:lead", "lead"),
        notification("claude:child", "lead"),
    ]
    found = dataclasses.replace(
        read(rows, {row.channel: ("oria",) for row in rows}, {"claude:child": "claude:lead"}),
        grafts={"claude:lead": "claude:host"},
    )
    grove = blocks.blocks(found, {})
    host = next(t for t in grove[0].trees if t.key == "host")
    assert host.lead and [m.channel for m in host.lemons] == ["claude:host", "claude:lead"]

    arrangement, _ = arrange.arrange(grove, {"plots": {}, "trees": {}}, NOW)
    letter = arrangement.trees[("oria", "host")].letter
    _, _, rename = press("tab", "1", "$", letter, "r", blocks=grove, arrangement=arrangement)
    assert (rename.channel, rename.name) == ("", "host")
