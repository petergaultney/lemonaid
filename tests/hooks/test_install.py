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
    assert _commands(hooks_json, "PreToolUse") == [
        install.own_change_command("codex"),
        install.docs_command("codex"),
        "lemonaid codex turn",
    ]
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

    assert _commands(settings, "PreToolUse") == [
        install.own_change_command("claude"),
        install.docs_command("claude"),
    ]
    assert _commands(settings, "PostToolUse") == [
        install.own_change_command("claude"),
        install.docs_created_command(),
    ]
    assert _commands(settings, "Stop") == ["lemonaid claude waiter-check"]
    assert _commands(settings, "SessionStart") == [
        "lemonaid hooks session-start --harness claude",
        install.docs_command("claude"),
    ]


def test_a_dry_run_changes_nothing(tmp_path):
    settings = tmp_path / "settings.json"

    lines = install.install("claude", settings, dry_run=True)

    assert not settings.exists()
    assert all(line.startswith("would add") for line in lines)


def test_codex_install_replaces_the_old_tool_used_hook_with_the_turn_hook(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    hooks_json = tmp_path / "hooks.json"
    tool_used = {"hooks": [{"type": "command", "command": "lemonaid codex tool-used"}]}
    hooks_json.write_text(json.dumps({"hooks": {"PostToolUse": [_FOLDER_NOTES, tool_used]}}))

    install.install("codex")

    for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "Interrupt", "PostModelRequest"):
        assert _commands(hooks_json, event).count("lemonaid codex turn") == 1
        assert "lemonaid codex tool-used" not in _commands(hooks_json, event)

    install.uninstall("codex")
    assert _commands(hooks_json, "PreToolUse") == []
    assert _commands(hooks_json, "PostToolUse") == ["python3 folder-notes-hook.py"]


def test_codex_session_start_takes_the_whole_context_doc(tmp_path):
    hooks_json = tmp_path / "hooks.json"
    command = install.session_start_command("codex")
    hooks_json.write_text(
        json.dumps(
            {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": command}]}]}}
        )
    )

    lines = install.install("codex", hooks_json)

    entry, _ = json.loads(hooks_json.read_text())["hooks"]["SessionStart"]
    assert entry["hooks"] == [
        {
            "type": "command",
            "command": command,
            "statusMessage": "lemonaid: session-start",
            "additionalContextLimit": 0,
        }
    ]
    assert any(line.startswith("updated SessionStart") for line in lines)
    assert all("already installed" in line for line in install.install("codex", hooks_json))


def test_codex_hooks_are_named_and_claude_hooks_are_not(tmp_path):
    codex, claude = tmp_path / "hooks.json", tmp_path / "settings.json"

    install.install("codex", codex)
    install.install("claude", claude)

    names = {
        hook.get("statusMessage")
        for entries in json.loads(codex.read_text())["hooks"].values()
        for entry in entries
        for hook in entry["hooks"]
    }
    assert names == {
        "lemonaid: own-change",
        "lemonaid: stop",
        "lemonaid: session-start",
        "lemonaid: session-end",
        "lemonaid: turn",
        "lemonaid: docs",
    }
    assert "statusMessage" not in claude.read_text()


def test_the_harness_waits_for_every_docs_hook_and_codex_takes_all_its_context(tmp_path):
    for harness in install.HARNESSES:
        install.install(harness, tmp_path / harness)
        docs = [
            hook
            for entries in json.loads((tmp_path / harness).read_text())["hooks"].values()
            for entry in entries
            for hook in entry["hooks"]
            if "hooks docs" in hook["command"]
        ]
        assert len(docs) == (4 if harness == "claude" else 3)
        assert all("async" not in hook for hook in docs)
        if harness == "codex":
            assert all(hook["additionalContextLimit"] == 0 for hook in docs)


def test_reinstalling_makes_the_harness_wait_for_a_docs_session_start_hook_again(tmp_path):
    for harness in install.HARNESSES:
        path = tmp_path / harness
        command = install.docs_command(harness)
        earlier = {"type": "command", "command": command, "async": True}
        path.write_text(json.dumps({"hooks": {"SessionStart": [{"hooks": [earlier]}]}}))

        install.install(harness, path)

        (start,) = [
            h
            for e in json.loads(path.read_text())["hooks"]["SessionStart"]
            for h in e["hooks"]
            if h["command"] == command
        ]
        assert "async" not in start
