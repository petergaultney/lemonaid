"""scripts/release.py prints the next version and notes from files added since a tag."""

import subprocess
from pathlib import Path

import pytest

from .shared import load

release = load("release.py", "release")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout


def _commit(root: Path, files: dict[str, str], message: str) -> None:
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", message)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "sam@example.com")
    _git(tmp_path, "config", "user.name", "Sam")
    _commit(
        tmp_path,
        {"changes/README.md": "about\n", "changes/2026-10-01-old-break.md": "# Major\n\n- Old.\n"},
        "start",
    )
    _git(tmp_path, "tag", "v0.115.3")
    _git(tmp_path, "tag", "v0.9.0")
    return tmp_path


def _run(repo: Path, capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str]:
    code = release.main([*args, "--root", str(repo)])
    return code, capsys.readouterr().out


def test_counts_only_files_added_since_the_highest_tag(repo: Path, capsys):
    _commit(repo, {"changes/2026-10-12-small-fix.md": "# Patch\n\n- **A fix.**\n"}, "fix")
    _commit(repo, {"changes/2026-10-14-new-feature.md": "# Minor\n\n- **A feature.**\n"}, "feat")

    assert _run(repo, capsys, "version") == (0, "0.116.0\n")
    assert _run(repo, capsys, "notes") == (0, "- **A fix.**\n\n- **A feature.**\n")


def test_since_and_until_pick_another_range(repo: Path, capsys):
    _commit(repo, {"changes/2026-10-12-small-fix.md": "# Patch\n\n- **A fix.**\n"}, "fix")
    _git(repo, "tag", "v0.115.4")
    _commit(repo, {"changes/2026-10-14-new-feature.md": "# Minor\n\n- **A feature.**\n"}, "feat")

    assert _run(repo, capsys, "notes", "--since", "v0.115.3", "--until", "v0.115.4") == (
        0,
        "- **A fix.**\n",
    )
    assert _run(repo, capsys, "version") == (0, "0.116.0\n")


def test_notes_merge_sections_from_every_commit_in_the_range(repo: Path, capsys):
    _commit(
        repo,
        {"changes/2026-10-12-first-fix.md": "# Patch\n\n#### Fixed\n\n- First fix.\n"},
        "first",
    )
    _commit(
        repo,
        {"changes/2026-10-14-last-fix.md": "# Patch\n\n#### Fixed\n\n- Last fix.\n"},
        "last",
    )
    assert _run(repo, capsys, "notes", "--since", "v0.115.3", "--until", "HEAD") == (
        0,
        "#### Fixed\n\n- First fix.\n\n- Last fix.\n",
    )


def test_nothing_added_exits_2(repo: Path, capsys):
    _commit(repo, {"changes/README.md": "edited\n"}, "docs")
    assert _run(repo, capsys, "version") == (2, "")


def test_malformed_file_exits_1(repo: Path, capsys):
    _commit(repo, {"changes/2026-10-14-bad-file.md": "- no heading\n"}, "bad")
    assert _run(repo, capsys, "version") == (1, "")


def test_odd_file_names_are_reported_not_crashed_on(repo: Path, capsys):
    _commit(repo, {"changes/2026-10-14-caf\u00e9 thing.md": "# Patch\n\n- x\n"}, "odd")
    assert release.main(["version", "--root", str(repo)]) == 1
    assert "not named" in capsys.readouterr().err


def test_latest_prints_the_highest_tag_or_the_highest_below_a_version(repo: Path, capsys):
    _git(repo, "tag", "v0.116.0")
    assert _run(repo, capsys, "latest") == (0, "0.116.0\n")
    assert _run(repo, capsys, "latest", "--below", "0.116.0") == (0, "0.115.3\n")
