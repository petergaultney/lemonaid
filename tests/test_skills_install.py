"""`lemonaid skills install`: composing packaged skills with a user file, and linking them."""

import json
import pathlib
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


def _packaged(name, harness):
    return compose.render(compose.PACKAGED_DIR, pathlib.Path("/nonexistent"), name, harness).text


def test_packaged_skills_name_no_user_and_call_only_lemonaid():
    raw = lambda name: (compose.PACKAGED_DIR / name / "SKILL.md").read_text()  # noqa: E731
    names = compose.packaged_names(compose.PACKAGED_DIR)

    assert names == ["brief", "watch-briefs", "watch-doc", "watch-pr"]
    for name in names:
        text = raw(name)
        assert text.startswith(f"---\nname: {name}\n")
        assert "watch-doc.py" not in text
        assert "watch-pr.py" not in text
        assert "Peter" not in text
        assert "vault" not in text


def test_install_links_each_harness_to_its_own_rendered_copy(homes):
    result = _install("--json")

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert [r["skill"] for r in report] == ["brief", "watch-briefs", "watch-doc", "watch-pr"]
    for r in report:
        assert r["source"] == "packaged"
        assert [h["outcome"] for h in r["harnesses"]] == ["linked", "linked"]
        for harness in ("claude", "codex"):
            entry = homes / harness / "skills" / r["skill"]
            assert entry.is_symlink()
            assert (entry / "SKILL.md").read_text() == _packaged(r["skill"], harness)
            assert str(entry.resolve()).endswith(f"/skills/{harness}/{r['skill']}")


def test_a_rerun_updates_the_rendered_copy_in_place(homes):
    _install()
    overlay = _user_file(homes, "watch-pr", "overlay.md", "## Mine\n\nMy review policy.\n")

    result = _install("watch-pr")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0].startswith(f"watch-pr: packaged + {overlay} -> ")
    assert "  claude: already linked" in result.stdout
    assert (homes / "claude" / "skills" / "watch-pr" / "SKILL.md").read_text() == (
        _packaged("watch-pr", "claude").rstrip() + "\n\n## Mine\n\nMy review policy.\n"
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


def test_a_link_through_another_harness_is_repointed_to_its_own_copy(homes):
    _install("watch-pr", "--harness", "claude")
    codex_entry = homes / "codex" / "skills" / "watch-pr"
    codex_entry.parent.mkdir(parents=True)
    codex_entry.symlink_to(homes / "claude" / "skills" / "watch-pr")

    result = _install("watch-pr", "--json")

    assert [h["outcome"] for h in json.loads(result.stdout)[0]["harnesses"]] == [
        "current",
        "linked",
    ]
    assert str(codex_entry.resolve()).endswith("/skills/codex/watch-pr")


def test_print_writes_nothing(homes):
    _user_file(homes, "watch-pr", "overlay.md", "## Mine\n")

    result = _install("--print", "watch-pr")

    assert result.stdout == _packaged("watch-pr", "claude").rstrip() + "\n\n## Mine\n"
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
    theirs = homes / "state" / "skills" / "claude" / "watch-pr"
    theirs.mkdir(parents=True)
    (theirs / "SKILL.md").write_text("theirs\n")
    target = homes / "elsewhere"
    target.mkdir()
    (homes / "state" / "skills" / "claude" / "watch-doc").symlink_to(target)

    result = _install("watch-doc", "watch-pr", "--harness", "claude")

    assert result.returncode == 1
    assert (
        f"claude watch-pr: refused: {theirs} exists and lemonaid didn't create it" in result.stderr
    )
    assert "claude watch-doc: refused:" in result.stderr
    assert (theirs / "SKILL.md").read_text() == "theirs\n"
    assert list(target.iterdir()) == []
    assert not (homes / "claude" / "skills" / "watch-pr").exists()
    assert not (homes / "claude" / "skills" / "watch-doc").exists()


def test_print_brief_with_overlay_writes_no_installation(homes):
    overlay = "## Local conventions\n\nNeeds Sam.\n"
    _user_file(homes, "brief", "overlay.md", overlay)

    result = _install("--print", "brief")

    assert result.returncode == 0, result.stderr
    assert result.stdout == _packaged("brief", "claude").rstrip() + "\n\n" + overlay
    assert not (homes / "state" / "skills").exists()
    assert not (homes / "claude" / "skills").exists()
    assert not (homes / "codex" / "skills").exists()


def test_each_harness_text_names_only_its_own_watch_mechanism(homes):
    for name in compose.packaged_names(compose.PACKAGED_DIR):
        claude, codex = _packaged(name, "claude"), _packaged(name, "codex")

        for text in (claude, codex):
            assert "<!-- harness" not in text
            assert "<!-- /harness" not in text
            assert "don't start `lemonaid watch --self`" not in text
        assert "--codex-thread" not in claude
        assert "codex queue" not in claude
        assert "push scout" not in codex
        assert "--push" not in codex
        assert "run_in_background" not in codex
        assert "background Bash" not in codex


def test_each_harness_gets_its_own_attached_brief_guidance(homes):
    claude, codex = _packaged("watch-pr", "claude"), _packaged("watch-pr", "codex")

    assert "`lemonaid watch --self --status`" in claude
    assert "`lemonaid watch --self --push`" in claude
    assert "lemonaid brief pr add" in claude
    assert "Run `lemonaid watch --self --codex-thread` in an escalated exec_command" in codex
    assert "lemonaid brief pr add" not in codex


def test_sections_of_an_overlay_and_a_replacement_follow_the_harness(homes):
    _user_file(
        homes,
        "watch-pr",
        "overlay.md",
        "<!-- harness: codex -->\nCodex only.\n<!-- /harness -->\n\nBoth.\n",
    )

    claude, codex = (
        _install("--print", "watch-pr"),
        _install("--print", "watch-pr", "--harness", "codex"),
    )

    assert claude.stdout.endswith("\n\nBoth.\n")
    assert "Codex only." not in claude.stdout
    assert codex.stdout.endswith("Codex only.\n\nBoth.\n")


def test_an_unknown_harness_in_a_section_marker_is_refused(homes):
    _user_file(homes, "watch-pr", "overlay.md", "<!-- harness: codx -->\nx\n<!-- /harness -->\n")

    result = _install("--print", "watch-pr")

    assert result.returncode == 2
    assert "unknown harness 'codx'" in result.stderr
