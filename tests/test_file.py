import os

import pytest

from lemonaid import file


def test_the_file_is_replaced_whole_with_its_mode_kept(tmp_path) -> None:
    path = tmp_path / "a.py"
    path.write_text("old\n")
    os.chmod(path, 0o755)

    assert file.replace(path, "new\n") is True

    assert path.read_text() == "new\n"
    assert path.stat().st_mode & 0o777 == 0o755
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.py"]


def test_a_file_that_changed_meanwhile_is_left_alone(tmp_path) -> None:
    path = tmp_path / "a.py"
    path.write_text("saved by an editor\n")

    assert file.replace(path, "new\n", unless_changed_from="what we read\n") is False

    assert path.read_text() == "saved by an editor\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.py"]


def test_newline_empty_keeps_and_compares_line_endings_as_they_are(tmp_path) -> None:
    path = tmp_path / "a.py"
    path.write_bytes(b"a\r\nb\r")

    replaced = file.replace(path, "a\r\nc\r", unless_changed_from="a\r\nb\r", newline="")

    assert replaced is True
    assert path.read_bytes() == b"a\r\nc\r"


def test_a_second_holder_waits_then_is_told_the_file_is_busy(tmp_path) -> None:
    path = tmp_path / "a.py"
    path.write_text("x = 1\n")

    with (
        file.locked(path),
        pytest.raises(file.Busy, match="another lemonaid process"),
        file.locked(path, wait_seconds=0.1),
    ):
        pass


def test_the_lock_is_free_again_once_released_and_sits_outside_the_file_s_folder(tmp_path) -> None:
    path = tmp_path / "a.py"
    path.write_text("x = 1\n")
    with file.locked(path):
        pass

    with file.locked(path, wait_seconds=0):
        pass

    assert sorted(p.name for p in tmp_path.iterdir() if p.name != "state") == ["a.py"]
