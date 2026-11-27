"""`skills install` and `skills list` with a configured source, and the startup refresh."""

import json

from lemonaid.skills import install, refresh

from .shared import configure, lemonaid_skills, skill


def _source(tmp_path):
    skill(tmp_path / "src", "reply-format", "Reply like this.")
    skill(tmp_path / "src", "review-guide")
    (tmp_path / "src" / "skills.toml").write_text('optional = ["review-guide"]\n')
    configure(f'[[skills.sources]]\nname = "mine"\npath = "{tmp_path / "src"}"\n')


def test_install_includes_a_sources_skills_but_not_its_optional_ones(tmp_path):
    _source(tmp_path)

    done = lemonaid_skills("install", "--harness", "claude", "--json")

    assert done.returncode == 0, done.stderr
    report = {r["skill"]: r["source"] for r in json.loads(done.stdout)}
    assert report["reply-format"] == "mine" and report["watch-doc"] == "packaged"
    assert "review-guide" not in report
    entry = install.harness_skill_dirs()["claude"] / "reply-format" / "SKILL.md"
    assert "Reply like this." in entry.read_text()


def test_an_optional_skill_installs_when_named_and_list_says_where_each_comes_from(tmp_path):
    _source(tmp_path)

    assert lemonaid_skills("install", "review-guide", "--harness", "claude").returncode == 0
    listed = {r["skill"]: r for r in json.loads(lemonaid_skills("list", "--json").stdout)}

    assert listed["review-guide"] == {
        "skill": "review-guide",
        "source": "mine",
        "optional": True,
        "installed": True,
    }
    assert listed["reply-format"]["installed"] is False


def test_startup_refresh_rewrites_an_installed_skill_its_source_changed(tmp_path):
    _source(tmp_path)
    lemonaid_skills("install", "reply-format", "--harness", "claude")
    skill(tmp_path / "src", "reply-format", "Reply like that now.")

    result = refresh.refresh_installed()

    assert "reply-format" in result.rewritten
    rendered = install.default_rendered_dir("claude") / "reply-format" / "SKILL.md"
    assert "Reply like that now." in rendered.read_text()


def test_startup_refresh_skips_a_sources_directories_that_hold_no_skill(tmp_path):
    _source(tmp_path)
    (tmp_path / "src" / ".git").mkdir()
    (tmp_path / "src" / "docs").mkdir()
    lemonaid_skills("install", "reply-format", "--harness", "claude")
    skill(tmp_path / "src", "reply-format", "Reply like that now.")

    result = refresh.refresh_installed()

    assert result.failed == [] and "reply-format" in result.rewritten
