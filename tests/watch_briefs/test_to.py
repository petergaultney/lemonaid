import argparse

import pytest

from lemonaid.brief import store
from lemonaid.watch import briefs_cli, briefs_events, delivery, waiter_lock

from .shared import args, lemon, link, open_watch, poll


@pytest.mark.parametrize("target", store.STATES)
@pytest.mark.parametrize("state", store.STATES)
def test_only_selected_destination_wakes(family, target, state):
    _, child, path, _ = family
    w = open_watch(family, to=frozenset({target}))
    path.write_text(path.read_text().replace("Status: working", f"Status: {state}"))
    assert poll(w) == ([f"{child}: Status: none -> {state} ({path})"] if state == target else [])
    assert poll(open_watch(family, to=frozenset({target}))) == []


def test_filtered_changes_advance_state_and_needs_alone_stay_quiet(family):
    _, child, path, _ = family
    targets = frozenset({"merge", "done"})
    w = open_watch(family, to=targets)
    before = "working"
    for state in ("waiting", "blocked", "running"):
        path.write_text(path.read_text().replace(f"Status: {before}", f"Status: {state}"))
        assert poll(w) == []
        w = open_watch(family, to=targets)
        before = state
    path.write_text(path.read_text().replace("Status: running", "Status: merge") + "- merge PR\n")
    assert poll(w) == [f"{child}: Status: running -> merge; Needs: merge PR ({path})"]
    path.write_text(path.read_text().replace("merge PR", "merge both PRs"))
    assert poll(w) == []
    path.write_text(path.read_text().replace("Status: merge", "Status: done"))
    assert "Status: merge -> done" in poll(w)[0]


def test_target_sets_have_independent_state_and_order_does_not_matter(family):
    _, _, path, _ = family
    merge = open_watch(family, to=frozenset({"merge"}))
    done = open_watch(family, to=frozenset({"done"}))
    both = open_watch(family, to=frozenset(("merge", "done")))
    assert both.reported_path == open_watch(family, to=frozenset(("done", "merge"))).reported_path
    path.write_text(path.read_text().replace("Status: working", "Status: merge"))
    assert poll(done) == []
    assert poll(merge)
    assert poll(both)


def test_new_children_only_wake_for_selected_statuses(family):
    parent, _, _, _ = family
    w = open_watch(family, to=frozenset({"done"}))
    child, path = lemon("new", "merge")
    link(child, parent)
    assert poll(w) == []
    path.write_text(path.read_text().replace("Status: merge", "Status: done"))
    assert poll(w) == [f"{child}: Status: merge -> done ({path})"]
    new, new_path = lemon("finished", "done")
    link(new, parent)
    assert poll(w) == [f"{new}: Status: done ({new_path})"]


def test_cli_accepts_repeatable_targets_and_passes_them_to_watch(family, capsys):
    parent, _, path, state_dir = family
    open_watch(family, me="", to=frozenset({"merge", "done"}))
    path.write_text(path.read_text().replace("Status: working", "Status: done"))
    parsed = args(state_dir, parent, "--once", "--to", "merge", "--to", "done")
    assert parsed.to == ["merge", "done"]
    assert briefs_cli.run(parsed) == 0
    assert "Status: none -> done" in capsys.readouterr().out


def test_cli_rejects_unknown_target(family, capsys):
    with pytest.raises(SystemExit) as error:
        args(family[3], family[0], "--to", "finished")
    assert error.value.code == 2
    assert "is not one of running" in capsys.readouterr().err


def test_filtered_delivery_failure_is_retried(family):
    _, child, path, _ = family
    targets = frozenset({"done"})
    w = open_watch(family, to=targets)
    path.write_text(path.read_text().replace("Status: working", "Status: done"))

    def fail(message):
        raise delivery.Failed("queue failed")

    with pytest.raises(delivery.Failed):
        briefs_events.poll(w, fail)
    assert poll(open_watch(family, to=targets)) == [f"{child}: Status: none -> done ({path})"]


def test_cli_status_lock_uses_target_set(family):
    parent, _, _, state_dir = family
    state_dir.mkdir(exist_ok=True)
    lock = waiter_lock.acquire(
        briefs_events.state_stem(state_dir, parent, "", frozenset({"done", "merge"})).with_suffix(
            ".lock"
        )
    )
    try:
        assert (
            briefs_cli.run(
                args(
                    state_dir, parent, "--status", "--to", "merge", "--to", "done", "--to", "merge"
                )
            )
            == 0
        )
        assert briefs_cli.run(args(state_dir, parent, "--status", "--to", "blocked")) == 1
        assert briefs_cli.run(args(state_dir, parent, "--status")) == 0
    finally:
        lock.close()


@pytest.mark.parametrize("retired", store.RETIRED)
def test_a_retired_status_is_refused_with_why(retired):
    with pytest.raises(argparse.ArgumentTypeError, match="no longer a brief status"):
        briefs_cli._target(retired)
