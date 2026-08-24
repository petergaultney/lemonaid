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
