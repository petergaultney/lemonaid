"""What a new lemon's launch gives it for its docs mode."""

import json
from pathlib import Path

import pytest

from lemonaid.config import load_config
from lemonaid.docs import launch, mode, start

from ..shared import configure, doc

_NO_KIN = launch.Kin()


def _prepare(tmp_path, wanted="packages", claude=True, kin=_NO_KIN, line=""):
    line = line or ("claude --model opus" if claude else "codex --no-daemon")
    return launch.prepare(wanted, tmp_path, kin, load_config(), line)


def _start_text(started: launch.Launch) -> str:
    return Path(started.claude_flags[1]).read_text()


@pytest.mark.usefixtures("root")
def test_a_claude_packages_lemon_gets_its_packages_and_skips_the_classic_docs(tmp_path):
    started = _prepare(tmp_path)

    assert started.environment[mode.ENV] == "packages" and not started.warning
    assert "Write plainly." in _start_text(started) and "flaky" not in _start_text(started)
    settings = json.loads(Path(started.claude_flags[3]).read_text())
    assert settings == {"claudeMdExcludes": [str(tmp_path / "classic.md")]}
    manifest = json.loads(Path(started.environment[start.START_ENV]).read_text())
    assert list(manifest["docs"]) == [f"{tmp_path / 'docs' / 'voice.md'}#"]


@pytest.mark.usefixtures("root")
def test_a_codex_packages_lemon_gets_only_its_mode(tmp_path):
    assert _prepare(tmp_path, claude=False) == launch.Launch({mode.ENV: "packages"})


@pytest.mark.usefixtures("root")
def test_a_classic_lemon_in_a_group_gets_only_the_group_s_package(tmp_path):
    started = _prepare(tmp_path, wanted="", kin=launch.Kin(groups=("oria",)))

    assert mode.ENV not in started.environment
    assert "--settings" not in started.claude_flags
    assert "Chase flaky tests." in _start_text(started) and "plainly" not in _start_text(started)


@pytest.mark.usefixtures("root")
def test_a_classic_lemon_outside_any_group_is_launched_as_before(tmp_path):
    assert _prepare(tmp_path, wanted="") == launch.Launch()


def test_without_roots_packages_falls_back_to_classic(tmp_path):
    started = _prepare(tmp_path)

    assert started.environment == {mode.ENV: "classic"} and started.claude_flags == ()
    assert "[docs] roots is not set" in started.warning


def test_a_lemon_no_package_is_for_falls_back_to_classic(tmp_path):
    root = tmp_path / "docs"
    doc(root, "packages/python.md", {"package-for": [{"file": "pyproject.toml"}]})
    configure([root])

    started = _prepare(tmp_path)

    assert started.environment == {mode.ENV: "classic"}
    assert "no package is for this lemon" in started.warning


def test_a_claude_lemon_without_a_classic_root_falls_back_to_classic(tmp_path, monkeypatch):
    root = tmp_path / "docs"
    doc(root, "packages/core.md", {"package-for": [{}]})
    doc(root, "voice.md", {"package": "core"})
    configure([root])

    assert "[docs] classic is not set" in _prepare(tmp_path).warning
    assert _prepare(tmp_path, claude=False).environment == {mode.ENV: "packages"}


@pytest.mark.usefixtures("root")
def test_a_claude_line_with_its_own_settings_falls_back_to_classic(tmp_path):
    started = _prepare(tmp_path, line="claude --settings '{\"x\": 1}'")

    assert "--settings" in started.warning and started.environment[mode.ENV] == "classic"


def _brief(tmp_path, mode: str) -> Path:
    path = tmp_path / "brief.md"
    path.write_text(f"---\ntype: Brief\ndocs-mode: {mode}\n---\n# Work\n")
    return path


@pytest.mark.usefixtures("root")
def test_a_brief_s_docs_mode_applies_unless_docs_overrides_it(tmp_path):
    kin = launch.Kin(brief=_brief(tmp_path, "packages"))

    assert _prepare(tmp_path, wanted="", kin=kin).environment[mode.ENV] == "packages"
    assert _prepare(tmp_path, wanted="classic", kin=kin).environment[mode.ENV] == "classic"


@pytest.mark.usefixtures("root")
def test_a_brief_s_unknown_docs_mode_is_ignored(tmp_path):
    kin = launch.Kin(brief=_brief(tmp_path, "lean"))

    assert _prepare(tmp_path, wanted="", kin=kin) == launch.Launch()
