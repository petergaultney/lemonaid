"""The follow hook runs inside the tmux server, once per switch, whatever fires it.

A switch fires two hooks. Two background shells each saw the pane absent and
both joined it, and a pane joined twice into one window came out 117 columns
wide instead of 58. Hooks that run in the server run in order, so the second
sees what the first did. The integration tests below drive a real server
because that ordering is the whole point and cannot be faked.
"""

import shutil
import subprocess
import uuid

import pytest

from lemonaid.tmux import follow, scratch


def test_the_hook_never_leaves_the_server():
    command = follow.hook_command()

    assert command.startswith("if-shell -F")
    assert "run-shell -C" in command
    assert "run-shell -b" not in command


def test_the_pane_is_swapped_not_moved():
    """-d: the switch target keeps focus, with no second relayout."""
    assert "swap-pane -d" in follow.hook_command()
    assert "split-window -d" in follow.hook_command()


def test_the_placeholder_command_is_safe_inside_a_format():
    """`#` starts a format sequence, and `pane_start_command` is stored quoted
    when it contains spaces - so the match is a glob on a single token."""
    assert "#" not in " ".join(follow.PLACEHOLDER_COMMAND)
    assert not any(" " in word for word in follow.PLACEHOLDER_COMMAND)


def test_after_select_window_is_retired():
    """It fires alongside session-window-changed on every window switch."""
    assert "after-select-window" not in follow.HOOKS
    assert "after-select-window" in follow.RETIRED_HOOKS


def test_the_parking_session_is_never_a_destination():
    assert "_lma_scratch" in follow.hook_condition()


def test_the_size_is_measured_against_both_the_client_and_the_window():
    """Neither dimension can be trusted alone at hook time.

    A window no client has shown reports tmux's 80x24 default, and the client,
    read from inside a hook mid-switch, can report the size it is leaving rather
    than the one it is arriving at - observed as `win=214 client=80`. Sizing
    against either one alone can split a sidebar that leaves the main pane under
    MIN_MAIN, and then the slot keeps its placeholder: a bare `sleep`, which
    renders as an empty pane.
    """
    command = follow.hook_command()

    assert "client_width" in command and "client_height" in command
    assert "window_width" in command and "window_height" in command


# --- against a real server -------------------------------------------------


@pytest.fixture
def tmux(monkeypatch, tmp_path):
    """A throwaway server with two 245x90 sessions, a parking session, and a
    control-mode client attached to `a` so switch-client and client_width work.

    $TMUX is pointed at it, so the plain `tmux` that follow.py and scratch.py
    run reaches this server and no other.
    """
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    name = f"lemonaid-test-{uuid.uuid4().hex[:8]}"

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["tmux", "-L", name, *args], capture_output=True, text=True)

    started = run(
        "-f", "/dev/null", "new-session", "-d", "-s", "a", "-n", "w1", "-x", "245", "-y", "90"
    )
    if started.returncode != 0:
        pytest.skip(f"cannot start tmux: {started.stderr.strip()}")

    run("new-window", "-d", "-t", "a", "-n", "w2")  # -d: w1 stays current, so w2 is a change
    run("new-session", "-d", "-s", "b", "-n", "w1", "-x", "245", "-y", "90")
    run("new-window", "-d", "-t", "b", "-n", "w2")
    run("new-session", "-d", "-s", scratch._SCRATCH_SESSION, "-x", "245", "-y", "90", "sh")
    client = subprocess.Popen(
        ["tmux", "-L", name, "-C", "attach", "-t", "a"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    run("refresh-client", "-C", "245x90")
    monkeypatch.setenv("TMUX", f"{run('display', '-p', '#{socket_path}').stdout.strip()},0,0")
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)
    try:
        yield run
    finally:
        client.kill()
        run("kill-server")


def _panes(run, window: str) -> list[tuple[str, int, int, bool]]:
    """(pane_id, width, height, active) for each pane in `window`."""
    out = run(
        "list-panes", "-t", window, "-F", "#{pane_id} #{pane_width} #{pane_height} #{pane_active}"
    )
    return [
        (p, int(w), int(h), a == "1")
        for p, w, h, a in (line.split() for line in out.stdout.split("\n") if line)
    ]


def _followed_pane(run, **options: str) -> str:
    """Mark the parking session's pane as the scratch pane, following left at 58."""
    pane = run("display", "-t", scratch._SCRATCH_SESSION, "-p", "#{pane_id}").stdout.strip()
    scratch._mark_pane(pane)
    scratch._save_pane_id(pane)
    follow.publish(
        {
            follow.FOLLOW_OPTION: "on",
            follow.POSITION_OPTION: "left",
            follow.WIDTH_OPTION: "58",
            follow.HEIGHT_OPTION: "12",
            **options,
        }
    )
    follow.install_hooks()
    return pane


def test_the_pane_follows_a_window_switch(tmux):
    pane = _followed_pane(tmux)

    tmux("select-window", "-t", "a:w2")

    assert (pane, 58, 90, False) in _panes(tmux, "a:w2")


def test_a_switch_that_fires_two_hooks_joins_once(tmux):
    """switch-client to a session:window fires session-window-changed and
    client-session-changed. The second must find the pane already there."""
    pane = _followed_pane(tmux)

    tmux("switch-client", "-t", "b:w2")

    panes = _panes(tmux, "b:w2")
    assert len(panes) == 2
    assert (pane, 58, 90, False) in panes


def test_the_switch_target_keeps_focus(tmux):
    _followed_pane(tmux)

    tmux("switch-client", "-t", "b:w1")

    assert tmux("display", "-p", "#{pane_id}").stdout.strip() != scratch._get_pane_id()


def _assert_sane(run, pane: str) -> None:
    """The pane is in the client's window, every window holds at most one slot
    (the pane or a placeholder), and no slot outside the parking session has focus."""
    here = run("display", "-p", "#{session_name}:#{window_index}").stdout.strip()
    assert (
        run("display", "-p", "-t", pane, "#{session_name}:#{window_index}").stdout.strip() == here
    )
    out = run(
        "list-panes",
        "-a",
        "-F",
        "#{session_name}:#{window_index} #{pane_id} #{pane_active} #{pane_start_command}",
    )
    slots: dict[str, list[str]] = {}
    for line in out.stdout.splitlines():
        window, pane_id, active, *_ = line.split()
        if pane_id == pane or "LEMONAID_PLACEHOLDER" in line:
            slots.setdefault(window, []).append(pane_id)
            assert active == "0" or window.startswith(scratch._SCRATCH_SESSION), line
    assert all(len(ids) == 1 for ids in slots.values()), slots


def test_switching_away_from_the_inbox_leaves_the_window_on_its_own_pane(tmux):
    """swap-pane -d keeps the slot active, which would leave the placeholder
    focused - `sleep` in the status bar - and hand the inbox focus on return."""
    pane = _followed_pane(tmux)
    tmux("select-window", "-t", "a:w2")
    tmux("select-pane", "-t", pane)

    tmux("select-window", "-t", "a:w1")

    _assert_sane(tmux, pane)
    assert _main_pane(tmux, "a:w2")[3]
    tmux("select-window", "-t", "a:w2")
    _assert_sane(tmux, pane)
    assert _main_pane(tmux, "a:w2")[3]


def test_a_switch_from_the_inbox_still_follows_across_sessions(tmux):
    """A select-pane in another window moves the hook's own target there; a
    format read after it would split and swap in the window the pane just left."""
    pane = _followed_pane(tmux)
    for target in ("a:w2", "b:w2", "b:w1", "a:w2", "b:w1", "a:w1", "b:w2"):
        tmux("select-pane", "-t", pane)
        tmux("switch-client", "-t", target)
        _assert_sane(tmux, pane)
        assert (pane, 58, 90, False) in _panes(tmux, target)


def test_focus_goes_back_to_the_pane_it_came_from(tmux):
    pane = _followed_pane(tmux)
    tmux("select-window", "-t", "a:w2")
    first = _main_pane(tmux, "a:w2")[0]
    tmux("split-window", "-t", first)  # a second main pane, focused
    tmux("select-pane", "-t", first)
    tmux("select-pane", "-t", pane)

    tmux("select-window", "-t", "a:w1")

    _assert_sane(tmux, pane)
    assert tmux("display", "-p", "-t", "a:w2", "#{pane_id}").stdout.strip() == first


def test_a_focused_slot_never_hands_focus_to_the_inbox(tmux):
    pane = _followed_pane(tmux)
    tmux("select-window", "-t", "a:w2")
    tmux("select-window", "-t", "a:w1")
    tmux("select-pane", "-t", follow.placeholders("a:w2")[0])

    tmux("select-window", "-t", "a:w2")

    _assert_sane(tmux, pane)
    assert _main_pane(tmux, "a:w2")[3]


def test_a_top_pane_is_measured_in_rows(tmux):
    pane = _followed_pane(tmux, **{follow.POSITION_OPTION: "top"})

    tmux("select-window", "-t", "a:w2")

    assert (pane, 245, 12, False) in _panes(tmux, "a:w2")


def test_a_saved_size_is_used_as_saved(tmux):
    pane = _followed_pane(tmux, **{follow.WIDTH_OPTION: "70"})

    tmux("select-window", "-t", "a:w2")

    assert (pane, 70, 90, False) in _panes(tmux, "a:w2")


def test_a_saved_size_the_client_cannot_hold_leaves_the_main_pane_room(tmux):
    pane = _followed_pane(tmux, **{follow.WIDTH_OPTION: "300"})

    tmux("select-window", "-t", "a:w2")

    assert (pane, 245 - follow.MIN_MAIN["left"], 90, False) in _panes(tmux, "a:w2")


def test_the_slot_is_on_the_left(tmux):
    """A placeholder split without -b sits on the right, and every swap after
    that moves the sidebar to the other side."""
    pane = _followed_pane(tmux)

    tmux("select-window", "-t", "a:w2")

    assert tmux("display", "-t", pane, "-p", "#{pane_left}").stdout.strip() == "0"
    tmux("select-window", "-t", "a:w1")
    assert (
        tmux("display", "-t", follow.placeholders("a:w2")[0], "-p", "#{pane_left}").stdout.strip()
        == "0"
    )


def test_follow_off_leaves_the_pane_where_it_is(tmux):
    _followed_pane(tmux, **{follow.FOLLOW_OPTION: "off"})

    tmux("select-window", "-t", "a:w2")

    assert len(_panes(tmux, "a:w2")) == 1


def test_a_parked_pane_stays_parked(tmux):
    """q clears the state; the hook must see that without a file to read."""
    _followed_pane(tmux)
    scratch._clear_state()

    tmux("select-window", "-t", "a:w2")

    assert len(_panes(tmux, "a:w2")) == 1


def _main_pane(run, window: str) -> tuple[str, int, int, bool]:
    return next(
        p
        for p in _panes(run, window)
        if p[0] not in follow.placeholders(window) and p[0] != scratch._get_pane_id()
    )


def test_a_revisited_window_keeps_its_layout(tmux):
    """The whole point of placeholders: the window's own pane never changes size."""
    _followed_pane(tmux)
    tmux("select-window", "-t", "a:w2")
    first = _main_pane(tmux, "a:w2")
    assert first[1] == 245 - 58 - 1

    tmux("select-window", "-t", "a:w1")
    assert _main_pane(tmux, "a:w2") == first  # a placeholder holds the slot
    assert len(follow.placeholders("a:w2")) == 1

    tmux("select-window", "-t", "a:w2")
    assert _main_pane(tmux, "a:w2") == first
    assert len(_panes(tmux, "a:w2")) == 2  # swapped in, not added


def test_the_first_visit_leaves_a_placeholder_where_the_pane_was(tmux):
    _followed_pane(tmux)

    tmux("select-window", "-t", "a:w2")

    assert follow.placeholders(scratch._SCRATCH_SESSION, whole_session=True)


def test_a_window_left_holding_only_a_placeholder_is_closed(tmux):
    _followed_pane(tmux)
    tmux("select-window", "-t", "a:w2")
    tmux("select-window", "-t", "a:w1")
    tmux("kill-pane", "-t", _main_pane(tmux, "a:w2")[0])

    windows = tmux("list-windows", "-t", "a", "-F", "#{window_name}").stdout.split()
    assert windows == ["w1"]


def test_a_sessions_last_window_is_never_closed(tmux):
    """detach-on-destroy would take the client with it."""
    _followed_pane(tmux)
    tmux("switch-client", "-t", "b:w2")
    tmux("switch-client", "-t", "a:w1")
    tmux("kill-window", "-t", "b:w1")
    tmux("kill-pane", "-t", _main_pane(tmux, "b:w2")[0])

    assert tmux("list-windows", "-t", "b", "-F", "#{window_name}").stdout.split() == ["w2"]


def test_the_slot_keeps_its_width_when_the_client_shrinks(tmux):
    """tmux spreads a resize over every pane; the sidebar is a character count."""
    pane = _followed_pane(tmux)
    tmux("select-window", "-t", "a:w2")

    tmux("refresh-client", "-C", "200x90")

    assert (pane, 58, 90, False) in _panes(tmux, "a:w2")


def test_show_swaps_into_a_placeholder_rather_than_adding_a_sidebar(tmux):
    """Unparking with prefix+l in a window that already has a slot."""
    pane = _followed_pane(tmux)
    tmux("select-window", "-t", "a:w2")
    tmux("select-window", "-t", "a:w1")
    main = _main_pane(tmux, "a:w2")

    assert scratch._show(pane, "58", "left", main[0])

    assert (pane, 58, 90, False) in _panes(tmux, "a:w2")
    assert len(_panes(tmux, "a:w2")) == 2
    assert _main_pane(tmux, "a:w2") == main
    assert len(follow.placeholders("a:w1")) == 1  # took the pane's old slot


def test_a_dead_pane_is_no_error(tmux):
    pane = _followed_pane(tmux)
    tmux("kill-pane", "-t", pane)

    assert tmux("select-window", "-t", "a:w2").returncode == 0
    assert len(_panes(tmux, "a:w2")) == 1
