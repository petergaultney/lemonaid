"""Where the scratch pane sits, and which number describes it.

A top pane is measured in rows and a left one in columns. Those are different
quantities, so they are stored in different files and configured separately -
flipping position keeps the size chosen for each, rather than reinterpreting one
number as the other and producing a 10-column pane nobody can read.
"""

import subprocess

from lemonaid.tmux import scratch


def _pane_size(monkeypatch, value: str) -> None:
    """Stand in for `tmux display-message -p #{pane_height|width}`."""

    def _run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout=f"{value}\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)


def test_top_splits_vertically():
    assert scratch._split_flag("top") == "-v"


def test_left_splits_horizontally():
    assert scratch._split_flag("left") == "-h"


def test_each_position_reads_its_own_dimension():
    assert scratch._pane_size_format("top") == "#{pane_height}"
    assert scratch._pane_size_format("left") == "#{pane_width}"


def test_each_position_gets_its_own_state_file():
    assert scratch._size_path("top") != scratch._size_path("left")
    assert scratch._size_path("top").name.endswith("-height")
    assert scratch._size_path("left").name.endswith("-width")


def test_saving_a_left_pane_leaves_the_height_alone(monkeypatch, tmp_path):
    """Otherwise switching back to top would inherit a column count."""
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)
    monkeypatch.setattr(scratch, "_get_pane_id", lambda: "%1")
    scratch._height_path().write_text("10")

    _pane_size(monkeypatch, "60")
    scratch.save_current_size("left")

    assert scratch._width_path().read_text() == "60"
    assert scratch._height_path().read_text() == "10"


def test_drift_compares_against_the_position_in_use(monkeypatch, tmp_path):
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)
    monkeypatch.setattr(scratch, "_get_pane_id", lambda: "%1")
    scratch._height_path().write_text("10")
    scratch._width_path().write_text("45")

    # tmux reports 45 for whichever dimension is asked about.
    _pane_size(monkeypatch, "45")

    assert scratch.size_has_drifted("top")
    assert not scratch.size_has_drifted("left")


def test_no_saved_size_is_not_drift(monkeypatch, tmp_path):
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)
    monkeypatch.setattr(scratch, "_get_pane_id", lambda: "%1")

    _pane_size(monkeypatch, "45")

    assert not scratch.size_has_drifted("left")


def test_a_stale_percentage_is_not_drift(monkeypatch, tmp_path):
    """Left over from when sizes could be percentages; it must not crash."""
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)
    monkeypatch.setattr(scratch, "_get_pane_id", lambda: "%1")
    scratch._height_path().write_text("20%")

    _pane_size(monkeypatch, "10")

    assert not scratch.size_has_drifted("top")


def _window_size(monkeypatch, value: str) -> None:
    """Stand in for `tmux display-message -p #{window_width|height}`."""

    def _run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout=f"{value}\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)


def test_a_saved_size_is_used_when_it_fits(monkeypatch):
    _window_size(monkeypatch, "200")

    assert scratch._capped("45", "left") == "45"


def test_a_saved_size_yields_only_to_a_client_that_cannot_hold_it(monkeypatch):
    """The main pane keeps follow.MIN_MAIN; the sidebar takes the rest."""
    _window_size(monkeypatch, "80")

    assert scratch._capped("45", "left") == "40"

    _window_size(monkeypatch, "100")
    assert scratch._capped("45", "left") == "45"


def test_an_unreadable_window_size_leaves_the_size_alone(monkeypatch):
    def _run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)

    assert scratch._capped("45", "left") == "45"


def test_each_position_caps_against_its_own_axis():
    left = scratch._window_size_format("left")
    top = scratch._window_size_format("top")

    assert "width" in left and "height" not in left
    assert "height" in top and "width" not in top


def test_position_falls_back_to_config_until_something_sets_it(monkeypatch, tmp_path):
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)

    assert scratch.current_position("left") == "left"
    assert scratch.current_position("top") == "top"


def test_a_set_position_outlives_the_config_default(monkeypatch, tmp_path):
    """Which edge you want depends on the window, which changes far more often."""
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)
    scratch.set_position("top")

    assert scratch.current_position("left") == "top"


def test_flipping_alternates(monkeypatch, tmp_path):
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)

    assert scratch.flip_position("left") == "top"
    assert scratch.flip_position("left") == "left"
    assert scratch.flip_position("left") == "top"


def test_the_size_is_capped_against_the_smaller_of_client_and_window():
    """Neither alone is right.

    A window no client has shown reports tmux's 80x24 default, so the window
    under-reports before a switch - that is why the client is consulted. But a
    window can also be genuinely smaller and stay that way, and the split
    happens in the window: sizing a client-width sidebar into it leaves the main
    pane below MIN_MAIN, the swap that would fix it is capped against the wide
    client, and the slot keeps its placeholder - a bare `sleep`, which renders
    as an empty pane.
    """
    fmt = scratch._window_size_format("left")

    assert "client_width" in fmt
    assert "window_width" in fmt


def test_the_size_format_falls_back_to_the_window_with_no_client():
    """A client-less server reports an empty dimension, and comparing against
    empty yields empty rather than the window."""
    fmt = scratch._window_size_format("left")

    assert fmt.startswith("#{?client_width,")
    assert fmt.endswith(",#{window_width}}")


def test_both_axes_are_capped_the_same_way():
    top = scratch._window_size_format("top")

    assert "client_height" in top
    assert "window_height" in top
