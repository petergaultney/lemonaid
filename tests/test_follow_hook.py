"""What the generated follow hook decides at run time versus what it bakes in.

The hook is regenerated only by --follow and --flip. Anything it compiles in is
therefore stale the moment that value changes by another route - which is how a
left pane came to be rejoined along the top, at a width meant for columns.
"""

from lemonaid.tmux import scratch


def _script(monkeypatch, tmp_path, size="45", position="left") -> str:
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)
    return scratch._write_follow_script(size, position).read_text()


def test_position_is_read_from_state_not_compiled_in(monkeypatch, tmp_path):
    script = _script(monkeypatch, tmp_path, position="left")

    assert "-position" in script


def test_both_axes_are_present_whichever_position_generated_it(monkeypatch, tmp_path):
    """A hook written while left must still be able to join a top pane."""
    script = _script(monkeypatch, tmp_path, position="left")

    assert "axis=-h" in script
    assert "axis=-v" in script


def test_each_axis_reads_its_own_dimension(monkeypatch, tmp_path):
    script = _script(monkeypatch, tmp_path)

    assert "dimension=width" in script
    assert "dimension=height" in script


def test_the_generating_position_is_only_a_fallback(monkeypatch, tmp_path):
    script = _script(monkeypatch, tmp_path, position="top")

    assert "|| position=top" in script


def test_the_size_cap_survives_the_rewrite(monkeypatch, tmp_path):
    """Without it, `place open` gets a pane taking most of an 80-column window."""
    script = _script(monkeypatch, tmp_path)

    assert f"* {int(scratch._MAX_SHARE * 100)} / 100" in script


def test_the_hook_is_executable(monkeypatch, tmp_path):
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)

    assert scratch._write_follow_script("45", "left").stat().st_mode & 0o111


def test_the_join_and_the_focus_restore_are_one_command(monkeypatch, tmp_path):
    """Two commands relayout the window twice, which is visible as a double resize."""
    script = _script(monkeypatch, tmp_path)

    join = next(line for line in script.splitlines() if "join-pane" in line)
    assert "select-pane" in join
    assert "\\;" in join
