"""The installed own-edit hook command, which starts Python only when there may be something to record."""

import json
import os
import subprocess
from pathlib import Path

from lemonaid.claude import install_hooks

_SESSION = "11111111-2222-3333-4444-555555555555"


def _run_installed(tmp_path: Path, stdin: str) -> str:
    """Run the installed hook command; what the fake `lemonaid` it hands off to received."""
    bin_dir, received = tmp_path / "bin", tmp_path / "received"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "lemonaid"
    fake.write_text(f'#!/bin/sh\ncat > "{received}"\n')
    fake.chmod(0o755)
    received.unlink(missing_ok=True)
    subprocess.run(
        install_hooks.OWN_EDIT_COMMAND,
        shell=True,
        input=stdin,
        text=True,
        check=True,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "TMPDIR": str(tmp_path / "tmp"),
        },
    )
    return received.read_text() if received.exists() else ""


def _event(path: str) -> str:
    return json.dumps(
        {
            "session_id": _SESSION,
            "hook_event_name": "PostToolUse",
            "tool_use_id": "toolu_1",
            "tool_input": {"file_path": path, "old_string": "a", "new_string": "b"},
        }
    )


def test_a_session_that_never_ran_a_doc_waiter_stays_in_the_shell(tmp_path):
    assert _run_installed(tmp_path, _event("/vault/review.md")) == ""


def test_a_watching_session_hands_markdown_edits_to_python(tmp_path):
    (tmp_path / "tmp" / "watch-doc" / "own" / f"claude-{_SESSION}").mkdir(parents=True)

    assert _run_installed(tmp_path, _event("/vault/review.md")) == _event("/vault/review.md")
    assert _run_installed(tmp_path, _event("/src/app.py")) == ""


def test_the_hooks_install_with_a_matcher_for_edit_tools(tmp_path):
    settings = tmp_path / "settings.json"
    for event in ("PreToolUse", "PostToolUse"):
        install_hooks.install(
            event, install_hooks.OWN_EDIT_COMMAND, settings, matcher=install_hooks.OWN_EDIT_MATCHER
        )

    hooks = json.loads(settings.read_text())["hooks"]
    assert hooks["PreToolUse"] == [
        {
            "matcher": "Edit|Write|MultiEdit",
            "hooks": [{"type": "command", "command": install_hooks.OWN_EDIT_COMMAND}],
        }
    ]
    assert hooks["PostToolUse"] == hooks["PreToolUse"]
