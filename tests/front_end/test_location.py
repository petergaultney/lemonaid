"""One location record, whichever terminal's keys an inbox row carries."""

from lemonaid.front_end import location


def test_a_tmux_row_is_its_session_window_and_pane():
    assert location.of(
        {
            "tty": "/dev/ttys5",
            "tmux_session": "work",
            "tmux_window": 4,
            "tmux_socket": "/tmp/tmux-1/default",
            "tmux_pane_identity": ["%12", 1700000000],
        }
    ) == location.Location("tmux", "/tmp/tmux-1/default", "work", "4", "%12", "/dev/ttys5")


def test_a_wezterm_row_is_its_workspace_and_pane():
    assert location.of(
        {"tty": "/dev/ttys6", "wezterm_pane": 9, "wezterm_workspace": "feat-x"}
    ) == location.Location("wezterm", "", "feat-x", "", "9", "/dev/ttys6")


def test_tmux_inside_cmux_is_tmux():
    assert location.of({"tmux_session": "work", "cmux_surface": "S1"}).front_end == "tmux"


def test_a_cmux_row_is_its_surface():
    assert location.of({"tty": "/dev/ttys7", "cmux_surface": "S1"}) == location.Location(
        "cmux", pane="S1", tty="/dev/ttys7"
    )


def test_a_tty_alone_is_a_plain_terminal_and_nothing_is_nowhere():
    assert location.of({"tty": "/dev/ttys8"}).front_end == "plain"
    assert location.of({}) == location.Location("")


def test_the_terminal_a_hook_ran_in_names_the_front_end():
    assert location.of({"tmux_session": "work"}, "cmux").front_end == "cmux"


def test_a_lemon_that_moved_to_wezterm_reads_wezterm_s_keys_not_the_tmux_ones_it_kept():
    moved = {
        "tmux_session": "old",
        "tmux_socket": "/tmp/tmux-1/default",
        "wezterm_pane": 9,
        "wezterm_workspace": "new",
        "wezterm_socket": "/tmp/gui-sock",
    }

    assert location.of(moved, "wezterm") == location.Location(
        "wezterm", "/tmp/gui-sock", "new", "", "9", ""
    )
    assert location.of({"tmux_session": "old", "cmux_surface": "S1"}, "cmux") == location.Location(
        "cmux", pane="S1"
    )
