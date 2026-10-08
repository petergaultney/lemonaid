"""`lemonaid skills install`: composing packaged skills with a user file, and linking them."""

import json
import subprocess
import sys

import pytest

from lemonaid.skills import compose


@pytest.fixture
def homes(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_LEMONS_DIR", str(tmp_path / "lemons"))
    (tmp_path / "claude").mkdir()
    (tmp_path / "codex").mkdir()
    return tmp_path


def _install(*args):
    return subprocess.run(
        [sys.executable, "-m", "lemonaid", "skills", "install", *args],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _user_file(homes, name, filename, text):
    path = homes / "lemons" / "skills" / name / filename
    path.parent.mkdir(parents=True)
    path.write_text(text)
    return path


def _packaged(name):
    return (compose.PACKAGED_DIR / name / "SKILL.md").read_text()


def test_packaged_skills_name_no_user_and_call_only_lemonaid():
    names = compose.packaged_names(compose.PACKAGED_DIR)

    assert names == ["watch-briefs", "watch-doc", "watch-pr"]
    for name in names:
        text = _packaged(name)
        assert text.startswith(f"---\nname: {name}\n")
        assert "watch-doc.py" not in text
        assert "watch-pr.py" not in text
        assert "Peter" not in text
        assert "vault" not in text


def test_install_links_every_harness_to_one_rendered_copy(homes):
    result = _install("--json")

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert [r["skill"] for r in report] == ["watch-briefs", "watch-doc", "watch-pr"]
    for r in report:
        assert r["source"] == "packaged"
        assert [h["outcome"] for h in r["harnesses"]] == ["linked", "linked"]
        for harness in ("claude", "codex"):
            entry = homes / harness / "skills" / r["skill"]
            assert entry.is_symlink()
            assert (entry / "SKILL.md").read_text() == _packaged(r["skill"])


def test_a_rerun_updates_the_rendered_copy_in_place(homes):
    _install()
    overlay = _user_file(homes, "watch-pr", "overlay.md", "## Mine\n\nMy review policy.\n")

    result = _install("watch-pr")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0].startswith(f"watch-pr: packaged + {overlay} -> ")
    assert "  claude: already linked" in result.stdout
    assert (homes / "claude" / "skills" / "watch-pr" / "SKILL.md").read_text() == (
        _packaged("watch-pr").rstrip() + "\n\n## Mine\n\nMy review policy.\n"
    )


def test_a_replacement_is_used_verbatim(homes):
    replacement = _user_file(homes, "watch-doc", "SKILL.md", "---\nname: watch-doc\n---\nmine\n")

    result = _install("watch-doc", "--harness", "claude", "--json")

    assert json.loads(result.stdout)[0]["source"] == f"{replacement} (replaces packaged)"
    assert (homes / "claude" / "skills" / "watch-doc" / "SKILL.md").read_text().endswith("mine\n")
    assert not (homes / "codex" / "skills").exists()


def test_an_entry_lemonaid_did_not_create_is_left_alone(homes):
    theirs = homes / "claude" / "skills" / "watch-pr"
    theirs.mkdir(parents=True)
    (theirs / "SKILL.md").write_text("theirs\n")
    elsewhere = homes / "codex" / "skills" / "watch-pr"
    elsewhere.parent.mkdir(parents=True)
    elsewhere.symlink_to(homes / "somewhere")

    result = _install("watch-pr")

    assert result.returncode == 1
    assert (
        f"claude: refused {theirs}: {theirs} exists and lemonaid didn't create it" in result.stdout
    )
    assert f"links to {homes / 'somewhere'}, which lemonaid didn't create" in result.stdout
    assert (theirs / "SKILL.md").read_text() == "theirs\n"


def test_a_link_through_another_harness_counts_as_installed(homes):
    _install("watch-pr", "--harness", "claude")
    codex_entry = homes / "codex" / "skills" / "watch-pr"
    codex_entry.parent.mkdir(parents=True)
    codex_entry.symlink_to(homes / "claude" / "skills" / "watch-pr")

    result = _install("watch-pr", "--json")

    assert [h["outcome"] for h in json.loads(result.stdout)[0]["harnesses"]] == [
        "current",
        "current",
    ]


def test_print_writes_nothing(homes):
    _user_file(homes, "watch-pr", "overlay.md", "## Mine\n")

    result = _install("--print", "watch-pr")

    assert result.stdout == _packaged("watch-pr").rstrip() + "\n\n## Mine\n"
    assert not (homes / "claude" / "skills").exists()


def test_user_file_mistakes_are_refused(homes):
    _user_file(homes, "watch-pr", "overlay.md", "---\nname: x\n---\n")
    frontmatter = _install("--print", "watch-pr")
    _user_file(homes, "watch-doc", "overlay.md", "a\n")
    (homes / "lemons" / "skills" / "watch-doc" / "SKILL.md").write_text("b\n")
    both = _install("watch-doc")

    assert frontmatter.returncode == 2
    assert "starts with frontmatter" in frontmatter.stderr
    assert both.returncode == 2
    assert "has both overlay.md and SKILL.md" in both.stderr
    assert _install("nope").stderr.startswith("no packaged skill 'nope'")


def test_a_rendered_directory_lemonaid_did_not_create_is_left_alone(homes):
    theirs = homes / "state" / "skills" / "watch-pr"
    theirs.mkdir(parents=True)
    (theirs / "SKILL.md").write_text("theirs\n")
    target = homes / "elsewhere"
    target.mkdir()
    (homes / "state" / "skills" / "watch-doc").symlink_to(target)

    result = _install("watch-doc", "watch-pr")

    assert result.returncode == 1
    assert f"watch-pr: refused: {theirs} exists and lemonaid didn't create it" in result.stderr
    assert "watch-doc: refused:" in result.stderr
    assert (theirs / "SKILL.md").read_text() == "theirs\n"
    assert list(target.iterdir()) == []
    assert not (homes / "claude" / "skills").exists()
