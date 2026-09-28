"""Tests for tmux status-line window names."""

import re
import shlex
from pathlib import Path
from subprocess import CompletedProcess

from lemonaid.tmux import window_status


def test_documented_tmux_status_command_keeps_empty_positional_arguments():
    docs = (Path(__file__).resolve().parents[1] / "docs" / "tmux.md").read_text()
    arguments = {
        "pane_path": "",
        "pane_current_path": "/work/a folder",
        "pane_current_command": "python3.14",
        "pane_title": "Unable to read Peter's $context | project",
        "window_active": "1",
        "pane_pid": "123",
    }
    expected = ["lemonaid-tmux-window-status", *arguments.values()]

    for option in ("window-status-format", "window-status-current-format"):
        line = next(line for line in docs.splitlines() if line.startswith(f"setw -g {option} "))
        command = line.split("#(", 1)[1].split(")", 1)[0]
        for name, value in arguments.items():
            # tmux q: backslash-escapes metacharacters but emits nothing for an
            # empty value. shlex.quote("") would emit "''" and mask this bug.
            escaped = re.sub(r"([^\w@%+=:,./-])", r"\\\1", value)
            command = command.replace(f"#{{q:{name}}}", escaped)

        assert shlex.split(command) == expected
        # Without the documented wrappers, the empty path disappears and the
        # next five values shift left, as they did in the broken configuration.
        assert len(shlex.split(command.replace("''", ""))) == len(expected) - 1


def test_configured_exact_process_replaces_the_directory():
    formatted = window_status.format_window(
        "/work/filter-guard",
        "mops-console",
        named_processes=("mops-console",),
    )

    assert "mops-console" in formatted
    assert "filter-guard" not in formatted


def test_configured_python_entrypoint_replaces_the_directory(monkeypatch):
    monkeypatch.setattr(
        window_status.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args[0], 0, "123 /venv/bin/python /venv/bin/mops-console serve\n", ""
        ),
    )

    formatted = window_status.format_window(
        "/work/filter-guard",
        "python3.14",
        "user@host: /work/filter-guard | xonsh",
        pane_pid="42",
        named_processes=("mops-console",),
    )

    assert "mops-console" in formatted
    assert "filter-guard" not in formatted


def test_configured_entrypoint_is_found_behind_a_launcher(monkeypatch):
    monkeypatch.setattr(
        window_status.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args[0], 0, "123 mise mops-console\n", ""),
    )

    formatted = window_status.format_window(
        "/work/eula-mgt",
        "mise",
        "user@host: /work/eula-mgt | xonsh",
        pane_pid="42",
        named_processes=("mops-console",),
    )

    assert "mops-console" in formatted
    assert "eula-mgt" not in formatted


def test_unconfigured_python_entrypoint_still_uses_the_directory(monkeypatch):
    monkeypatch.setattr(
        window_status.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args[0], 0, "123 /venv/bin/python /venv/bin/mops-console serve\n", ""
        ),
    )

    formatted = window_status.format_window(
        "/work/filter-guard",
        "python3.14",
        "user@host: /work/filter-guard | xonsh",
        pane_pid="42",
    )

    assert "filter-guard" in formatted
    assert "mops-console" not in formatted


def test_codex_behind_python_shell_ignores_task_title(monkeypatch):
    monkeypatch.setattr(
        window_status.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args[0], 0, "95117 node /opt/node/bin/codex REVIEW #81 delivery service\n", ""
        ),
    )

    formatted = window_status.format_window(
        "/work/delivery-service",
        "python3.14",
        "Unable to read required context | delivery-service",
        pane_pid="95113",
    )

    assert "codex" in formatted
    assert "Unable to read required context" not in formatted
    assert "delivery-service" not in formatted


def test_configured_title_wins_even_when_it_matches_the_directory():
    formatted = window_status.format_window(
        "/work/mops-console",
        "python3.14",
        "mops-console",
        named_processes=("mops-console",),
    )

    assert formatted.count("mops-console") == 1
    assert ": " not in formatted


def test_node_task_title_does_not_become_process_name(monkeypatch):
    monkeypatch.setattr(
        window_status.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args[0], 0, "", ""),
    )

    formatted = window_status.format_window(
        "/work/tars-eula",
        "node",
        "Install slack plugin | tars-eula",
        pane_pid="42",
    )

    assert "Install" not in formatted
    assert "node" in formatted
    assert "tars-eula" in formatted


def test_python_task_title_does_not_become_process_name():
    formatted = window_status.format_window(
        "/work/main",
        "python3.14",
        "Review backend sandbox PRs | main",
    )

    assert "Review" not in formatted
    assert formatted.startswith("$")
    assert "main" in formatted
