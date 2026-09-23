"""Tests for tmux status-line window names."""

from subprocess import CompletedProcess

from lemonaid.tmux import window_status


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


def test_configured_title_wins_even_when_it_matches_the_directory():
    formatted = window_status.format_window(
        "/work/mops-console",
        "python3.14",
        "mops-console",
        named_processes=("mops-console",),
    )

    assert formatted.count("mops-console") == 1
    assert ": " not in formatted
