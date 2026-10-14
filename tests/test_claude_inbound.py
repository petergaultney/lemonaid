"""Lemonaid pushes into a Claude session only when the session won't hold the message for approval."""

import json
from pathlib import Path

from lemonaid.claude import inbound, session_socket

_LEMON = ["claude", "--allow-dangerously-skip-permissions"]


def _user_settings(settings: dict) -> None:
    path = session_socket.claude_dir() / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings))


def test_a_session_that_cannot_reach_bypass_mode_accepts_without_the_setting(tmp_path: Path):
    assert inbound.accepts(["claude", "--permission-mode", "auto"], str(tmp_path))


def test_a_session_that_can_reach_bypass_mode_needs_the_setting(tmp_path: Path):
    assert not inbound.accepts(_LEMON, str(tmp_path))
    assert not inbound.accepts(["claude", "--permission-mode", "bypassPermissions"], str(tmp_path))
    assert not inbound.accepts(["claude", "--dangerously-skip-permissions"], str(tmp_path))


def test_bypass_as_the_default_mode_needs_the_setting(tmp_path: Path):
    _user_settings({"permissions": {"defaultMode": "bypassPermissions"}})

    assert not inbound.accepts(["claude"], str(tmp_path))


def test_accept_in_user_settings_lets_a_bypass_session_receive(tmp_path: Path):
    _user_settings({"crossSessionInbound": "accept"})

    assert inbound.accepts(_LEMON, str(tmp_path))


def test_accept_passed_as_a_settings_json_string(tmp_path: Path):
    assert inbound.accepts(
        [*_LEMON, "--settings", '{"crossSessionInbound": "accept"}'], str(tmp_path)
    )


def test_project_settings_override_user_settings(tmp_path: Path):
    _user_settings({"crossSessionInbound": "accept"})
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text('{"crossSessionInbound": "hold"}')

    assert not inbound.accepts(["claude"], str(tmp_path))


def test_a_settings_file_overrides_project_settings(tmp_path: Path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.local.json").write_text('{"crossSessionInbound": "hold"}')
    flagged = tmp_path / "lemon-settings.json"
    flagged.write_text('{"crossSessionInbound": "accept"}')

    assert inbound.accepts([*_LEMON, f"--settings={flagged}"], str(tmp_path))


def test_a_relative_settings_path_is_read_from_the_session_s_directory(tmp_path: Path):
    (tmp_path / "lemon.json").write_text('{"crossSessionInbound": "accept"}')

    assert inbound.accepts([*_LEMON, "--settings", "lemon.json"], str(tmp_path))
