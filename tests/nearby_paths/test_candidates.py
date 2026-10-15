import os

import pytest

from lemonaid.watch import nearby_paths


@pytest.mark.parametrize("folder,parent_rename", [(False, False), (True, False), (False, True)])
def test_suggests_common_nearby_moves(tmp_path, folder, parent_rename):
    parent = tmp_path / "before"
    parent.mkdir()
    original = parent / "target"
    original.mkdir() if folder else original.write_text("body")
    previous = nearby_paths.identity(original)
    destination = tmp_path / "after"
    if parent_rename:
        parent.rename(destination)
        expected = destination / "target"
    else:
        destination.mkdir()
        expected = destination / "new-name"
        original.rename(expected)
    assert nearby_paths.candidates(original, previous) == [expected]


def test_work_is_bounded_even_without_a_match(tmp_path, monkeypatch):
    for index in range(100):
        (tmp_path / f"entry-{index}").touch()
    scanned = []
    real = os.scandir

    def scandir(path):
        scanned.append(path)
        return real(path)

    monkeypatch.setattr(nearby_paths.os, "scandir", scandir)
    assert nearby_paths.candidates(tmp_path / "absent", (-1, -1, -1, 0), entries=5) == []
    assert scanned == [tmp_path]
    scanned.clear()
    assert nearby_paths.candidates(tmp_path / "absent", (-1, -1, -1, 0), directories=1) == []
    assert scanned == [tmp_path]


def test_does_not_descend_through_symlinks_or_hidden_directories(tmp_path):
    original = tmp_path / "file"
    original.write_text("body")
    previous = nearby_paths.identity(original)
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    original.rename(hidden / "renamed")
    (tmp_path / "link").symlink_to(hidden, target_is_directory=True)
    assert nearby_paths.candidates(original, previous) == []


def test_nearest_subdirectory_is_searched_before_a_crowded_parent(tmp_path):
    parent = tmp_path / "crowded"
    parent.mkdir()
    for index in range(1100):
        (parent / f"unrelated-{index}").mkdir()
    workspace = parent / "workspace"
    workspace.mkdir()
    original = workspace / "old.md"
    original.write_text("body")
    previous = nearby_paths.identity(original)
    nearby = workspace / "nearby"
    nearby.mkdir()
    renamed = nearby / "new.md"
    original.rename(renamed)
    assert nearby_paths.candidates(original, previous) == [renamed]
