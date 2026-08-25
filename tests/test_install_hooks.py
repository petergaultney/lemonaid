"""Editing Claude Code's settings without disturbing what is already there."""

import json

import pytest

from lemonaid.claude import install_hooks


def _settings(tmp_path, content=None):
    p = tmp_path / "settings.json"
    if content is not None:
        p.write_text(json.dumps(content))
    return p


def test_installing_into_a_fresh_file(tmp_path):
    p = _settings(tmp_path)
    install_hooks.install_session_start(p)

    entries = json.loads(p.read_text())["hooks"]["SessionStart"]
    assert entries[0]["hooks"][0]["command"] == "lemonaid claude session-start"


def test_installing_twice_changes_nothing(tmp_path):
    p = _settings(tmp_path)
    install_hooks.install_session_start(p)
    before = p.read_text()
    result = install_hooks.install_session_start(p)

    assert p.read_text() == before
    assert "already installed" in result


def test_other_hooks_are_left_alone(tmp_path):
    """The file is the user's; lemonaid adds to it and owns only its own line."""
    p = _settings(
        tmp_path,
        {
            "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "something-else"}]}]},
            "model": "opus",
        },
    )
    install_hooks.install_session_start(p)

    settings = json.loads(p.read_text())
    assert settings["model"] == "opus"
    assert settings["hooks"]["Stop"][0]["hooks"][0]["command"] == "something-else"


def test_an_existing_session_start_hook_is_kept(tmp_path):
    p = _settings(
        tmp_path, {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "mine"}]}]}}
    )
    install_hooks.install_session_start(p)

    commands = [
        h["command"] for e in json.loads(p.read_text())["hooks"]["SessionStart"] for h in e["hooks"]
    ]
    assert commands == ["mine", "lemonaid claude session-start"]


def test_dry_run_writes_nothing(tmp_path):
    p = _settings(tmp_path)
    result = install_hooks.install_session_start(p, dry_run=True)

    assert not p.exists()
    assert "would add" in result


def test_uninstall_removes_only_ours(tmp_path):
    p = _settings(
        tmp_path, {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "mine"}]}]}}
    )
    install_hooks.install_session_start(p)
    install_hooks.uninstall_session_start(p)

    commands = [
        h["command"] for e in json.loads(p.read_text())["hooks"]["SessionStart"] for h in e["hooks"]
    ]
    assert commands == ["mine"]


def test_uninstalling_what_was_never_installed(tmp_path):
    p = _settings(tmp_path, {"hooks": {}})

    assert "no lemonaid SessionStart hook" in install_hooks.uninstall_session_start(p)


def test_broken_json_is_not_overwritten(tmp_path):
    """Rewriting a settings file we could not parse would lose it."""
    p = tmp_path / "settings.json"
    p.write_text("{not json")

    with pytest.raises(ValueError):
        install_hooks.install_session_start(p)

    assert p.read_text() == "{not json"
