"""`lemonaid hooks install`: lemonaid's hooks in both harnesses, everyone else's left alone."""

import json
import shlex

from lemonaid.hooks import install

_FOLDER_NOTES = {
    "matcher": "Read|Edit|Write",
    "hooks": [{"type": "command", "command": "python3 folder-notes-hook.py"}],
}
_NOTIFY = {"hooks": [{"type": "command", "command": "lemonaid codex notify"}]}
_LEGACY_SCRIPT = "; ".join(
    [
        "d=$(cat)",
        'v() { printf "%s" "$d" | tr ",{" "\\n\\n" | '
        'sed -n "s/^ *\\"$1\\" *: *\\"\\([^\\"]*\\)\\".*/\\1/p" | sort -u; }',
        "s=$(v session_id)",
        '[ -n "$s" ] && [ -d "${TMPDIR:-/tmp}/watch-doc/own/claude-$s" ] || exit 0',
        'case "$(v file_path)" in *.md*) ;; *) exit 0 ;; esac',
        'printf "%s" "$d" | exec lemonaid claude own-edit',
    ]
)


def _commands(path, event):
    return [
        h["command"]
        for entry in json.loads(path.read_text())["hooks"].get(event, [])
        for h in entry["hooks"]
    ]


def test_codex_hooks_go_beside_the_users_own(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    hooks_json = tmp_path / "codex" / "hooks.json"
    hooks_json.parent.mkdir()
    hooks_json.write_text(
        json.dumps(
            {
                "description": "foo",
                "hooks": {"PostToolUse": [_FOLDER_NOTES], "PermissionRequest": [_NOTIFY]},
            }
        )
    )

    install.install("codex")
    again = install.install("codex")

    saved = json.loads(hooks_json.read_text())
    assert saved["description"] == "foo"
    assert saved["hooks"]["PostToolUse"][0] == _FOLDER_NOTES
    assert saved["hooks"]["PermissionRequest"] == [_NOTIFY]
    assert _commands(hooks_json, "Stop") == ["lemonaid hooks stop --harness codex"]
    assert _commands(hooks_json, "PreToolUse") == [install.own_change_command("codex")]
    assert all("already installed" in line for line in again)

    install.uninstall("codex")
    assert json.loads(hooks_json.read_text())["hooks"] == {
        "PostToolUse": [_FOLDER_NOTES],
        "PermissionRequest": [_NOTIFY],
    }


def test_claude_install_replaces_the_edit_and_write_only_hook(tmp_path):
    settings = tmp_path / "settings.json"
    legacy = {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command", "command": f"sh -c {shlex.quote(_LEGACY_SCRIPT)}"}],
    }
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [legacy], "PostToolUse": [legacy]}}))

    install.install("claude", settings)

    for event in ("PreToolUse", "PostToolUse"):
        assert _commands(settings, event) == [install.own_change_command("claude")]
    assert _commands(settings, "Stop") == ["lemonaid claude waiter-check"]
    assert _commands(settings, "SessionStart") == ["lemonaid hooks session-start --harness claude"]


def test_a_dry_run_changes_nothing(tmp_path):
    settings = tmp_path / "settings.json"

    lines = install.install("claude", settings, dry_run=True)

    assert not settings.exists()
    assert all(line.startswith("would add") for line in lines)


def test_codex_install_adds_tool_used_once_beside_a_hand_added_one(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    hooks_json = tmp_path / "hooks.json"
    tool_used = {"hooks": [{"type": "command", "command": "lemonaid codex tool-used"}]}
    hooks_json.write_text(json.dumps({"hooks": {"PostToolUse": [_FOLDER_NOTES, tool_used]}}))

    install.install("codex")

    assert _commands(hooks_json, "PostToolUse").count("lemonaid codex tool-used") == 1

    install.uninstall("codex")
    assert _commands(hooks_json, "PostToolUse") == ["python3 folder-notes-hook.py"]


def test_a_fresh_codex_install_adds_tool_used(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))

    install.install("codex")

    assert "lemonaid codex tool-used" in _commands(tmp_path / "hooks.json", "PostToolUse")
