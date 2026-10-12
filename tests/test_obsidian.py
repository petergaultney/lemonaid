"""A path under a vault root, as a terminal or brief wrote it, opens in that vault."""

from pathlib import Path

from lemonaid import obsidian


def test_a_path_with_spaces_under_a_root_opens_in_the_vault_named_for_its_folder(tmp_path):
    (tmp_path / "trove").mkdir()

    assert obsidian.vault_link(tmp_path / "trove" / "94 System" / "a.md", [tmp_path / "trove"]) == (
        "obsidian://open?vault=trove&file=94%20System%2Fa"
    )


def test_anything_but_a_md_file_under_a_root_has_no_link(tmp_path):
    roots = [tmp_path / "trove"]

    assert obsidian.vault_link(tmp_path / "trove" / "a.py", roots) is None
    assert obsidian.vault_link(tmp_path / "other" / "a.md", roots) is None


def test_a_root_under_home_is_spelled_from_tilde_and_in_full():
    assert obsidian.spellings(Path.home() / "trove") == ["~/trove", f"{Path.home()}/trove"]
