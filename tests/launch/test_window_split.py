"""A replacement shell is opened in the source window."""

import subprocess

from lemonaid.launch import window


def test_split_pane_keeps_window_and_source_focus(tmp_path, monkeypatch):
    calls = []

    def tmux(*args):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "%3\t@2\n", "")

    monkeypatch.setattr(window, "_tmux", tmux)
    result, error = window.split_pane(
        window.Pane("%2", "@2"), tmp_path, {"LEMONAID_HANDOFF_TOKEN": "token"}
    )
    assert (result, error) == (window.Pane("%3", "@2"), "")
    assert calls == [
        (
            "split-window",
            "-d",
            "-t",
            "%2",
            "-c",
            str(tmp_path),
            "-e",
            "LEMONAID_HANDOFF_TOKEN=token",
            "-P",
            "-F",
            "#{pane_id}\t#{window_id}",
        )
    ]


def test_split_pane_rejects_another_window(tmp_path, monkeypatch):
    monkeypatch.setattr(
        window, "_tmux", lambda *_args: subprocess.CompletedProcess([], 0, "%3\t@other\n", "")
    )
    result, error = window.split_pane(window.Pane("%2", "@2"), tmp_path, {})
    assert result is None
    assert "Could not split" in error
