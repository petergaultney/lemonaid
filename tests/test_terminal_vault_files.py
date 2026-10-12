"""Top-level vault names and resolving a path written without its root."""

from pathlib import Path

from lemonaid.terminal import vault_files


def _vault(root: Path) -> Path:
    (root / "proj" / "sub").mkdir(parents=True)
    (root / ".obsidian").mkdir()
    (root / "proj" / "sub" / "n.md").write_text("x")
    (root / "top.md").write_text("x")
    (root / "image.png").write_text("x")
    (root / "bad;dir").mkdir()
    return root


def test_spaced_folders_lists_only_visible_folders_with_a_space(tmp_path):
    root = _vault(tmp_path / "v")
    (root / "My Notes").mkdir()
    (root / ".hid den").mkdir()
    (root / "a b;c").mkdir()
    (root / "x y.md").write_text("x")

    assert vault_files.spaced_folders([root, tmp_path / "missing"], ";") == ["My Notes"]


def test_resolve_takes_the_first_root_holding_the_path(tmp_path):
    first, second = _vault(tmp_path / "a"), _vault(tmp_path / "b")
    (first / "proj" / "sub" / "n.md").unlink()

    assert vault_files.resolve(Path("proj/sub/n.md"), [first, second]) == second / "proj/sub/n.md"


def test_resolve_finds_nothing_for_an_unfound_relative_path_and_keeps_absolute_ones(tmp_path):
    root = _vault(tmp_path / "v")

    assert vault_files.resolve(Path("proj/none.md"), [root]) is None
    assert vault_files.resolve(root / "top.md", []) == root / "top.md"
