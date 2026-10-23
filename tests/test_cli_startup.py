"""Discover parser paths and installed scripts instead of maintaining a help list."""

import argparse
import importlib.metadata
import json
from collections import abc
from unittest.mock import patch

import pytest

import lemonaid.cli
from tests.cli_startup_shared import run

_NO_TEXTUAL = """
import sys
assert 'textual' not in sys.modules
assert not any(name.startswith('textual.') for name in sys.modules)
"""


def _parser_paths() -> abc.Iterator[tuple[str, ...]]:
    with (
        patch.object(
            argparse.ArgumentParser, "parse_args", autospec=True, side_effect=SystemExit(0)
        ) as parse,
        patch.object(lemonaid.cli.sys, "argv", ["lemonaid"]),
        pytest.raises(SystemExit),
    ):
        lemonaid.cli.main()
    pending = [((), parse.call_args.args[0])]
    while pending:
        words, parser = pending.pop()
        yield words
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                pending.extend(((*words, name), child) for name, child in action.choices.items())


@pytest.mark.skipif(lemonaid.cli.sys.version_info < (3, 15), reason="PEP 810 requires Python 3.15")
@pytest.mark.parametrize(
    "command", list(_parser_paths()), ids=lambda words: " ".join(words) or "root"
)
def test_every_command_help_avoids_textual(tmp_path, command):
    run(
        tmp_path,
        f"""
import sys
import lemonaid.cli
sys.argv = {["lemonaid", *command, "--help"]!r}
try:
    lemonaid.cli.main()
except SystemExit as error:
    assert error.code == 0
else:
    raise AssertionError('help did not exit')
"""
        + _NO_TEXTUAL,
    )


_SCRIPTS = {
    ep.name: ep
    for ep in importlib.metadata.distribution("lemonaid-inbox").entry_points
    if ep.group == "console_scripts"
}
_SCRIPT_CASES = {
    "lemonaid": ["config", "path"],
    "lemonaid-tmux-window-status": ["", "/tmp", "xonsh"],
    "lemonaid-tmux-session-name": ["test-session"],
    "lemonaid-claude-statusline": [],
}


def test_every_installed_entry_point_is_classified():
    assert set(_SCRIPTS) == set(_SCRIPT_CASES) | {"lma"}


@pytest.mark.parametrize("script", _SCRIPT_CASES)
def test_non_tui_console_scripts_avoid_textual(tmp_path, script):
    code = f"""
import importlib
import sys
sys.argv = {[script, *_SCRIPT_CASES[script]]!r}
module, function = {_SCRIPTS[script].value!r}.split(':')
getattr(importlib.import_module(module), function)()
"""
    if lemonaid.cli.sys.version_info >= (3, 15):
        code += _NO_TEXTUAL
    run(tmp_path, code, stdin="{}")


@pytest.mark.skipif(lemonaid.cli.sys.version_info < (3, 15), reason="PEP 810 requires Python 3.15")
@pytest.mark.parametrize(
    "command",
    [
        ("claude", "notify"),
        ("claude", "submit"),
        ("claude", "session-start"),
        ("codex", "notify"),
        ("opencode", "notify"),
        ("openclaw", "notify"),
    ],
    ids=lambda words: " ".join(words),
)
def test_notification_hooks_write_without_textual(tmp_path, command):
    setup = ""
    if command == ("codex", "notify"):
        sessions = tmp_path / ".codex" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "rollout-test-lazy-imports.jsonl").write_text(
            json.dumps({"type": "session_meta", "payload": {"id": "test-lazy-imports"}}) + "\n"
        )
        setup = f"import os\nos.environ['HOME'] = {str(tmp_path)!r}\n"
    payload = json.dumps(
        {
            "session_id": "test-lazy-imports",
            "cwd": str(tmp_path),
            "transcript_path": str(tmp_path / "transcript.jsonl"),
        }
    )
    run(
        tmp_path,
        setup
        + f"""
import sys
import lemonaid.cli
from lemonaid.messages import service
from lemonaid.inbox import db

# Delivery is a detached process; keep this check inside its isolated interpreter.
service.ensure_running = lambda: None
sys.argv = {["lemonaid", *command]!r}
lemonaid.cli.main()
with db.connect() as conn:
    assert conn.execute('SELECT count(*) FROM notifications').fetchone()[0] == 1
"""
        + _NO_TEXTUAL,
        stdin=payload,
    )


@pytest.mark.skipif(lemonaid.cli.sys.version_info < (3, 15), reason="PEP 810 requires Python 3.15")
@pytest.mark.parametrize(
    "command",
    [
        ("config", "init"),
        ("config", "show"),
        ("inbox", "list", "--json"),
        ("inbox", "get", "1", "--json"),
        ("inbox", "add", "test:new", "A notification"),
        ("inbox", "read", "1"),
        ("inbox", "emojis", "--json"),
        ("inbox", "snoozed", "--json"),
        ("inbox", "purge"),
        ("group", "list", "--json"),
        ("brief", "show", "--file", "task.md"),
        ("mark-read", "--tty", "/dev/test"),
        ("mark-unread", "--tty", "/dev/test"),
    ],
    ids=lambda words: " ".join(words),
)
def test_non_rendering_commands_execute_without_textual(tmp_path, command):
    run(
        tmp_path,
        f"""
import sys
from pathlib import Path
import lemonaid.cli
from lemonaid.inbox import db
Path('task.md').write_text('# Task\\n\\n## Now\\n\\nTesting CLI startup.\\n')
with db.connect() as conn:
    db.add(conn, channel='test:existing', message='Existing notification')
sys.argv = {["lemonaid", *command]!r}
lemonaid.cli.main()
"""
        + _NO_TEXTUAL,
    )
