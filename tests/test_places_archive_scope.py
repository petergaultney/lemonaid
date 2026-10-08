from pathlib import Path

import pytest

from lemonaid.inbox import db
from lemonaid.places import archive_scope


@pytest.mark.parametrize(
    ("channel", "source", "terminal", "expected"),
    [
        ("claude:lemon", "tmux", {}, []),
        ("claude:lemon", "tmux", {"tty": "/tty"}, []),
        ("codex:daemon", "tmux", {}, [1]),
        ("codex:legacy", "tmux", {"tty": "/daemon"}, [1]),
        (
            "codex:cli",
            "tmux",
            {"tty": "/tty", "tmux_pane_identity": ["%1", 1], "tmux_session_order": [1, 1, 1]},
            [],
        ),
        ("codex:other", "cmux", {}, []),
        ("codex:other", "wezterm", {"tty": "/tty"}, []),
    ],
)
def test_only_unlocated_codex_rows_use_directory_membership(channel, source, terminal, expected):
    row = db.Notification(
        id=1,
        channel=channel,
        message="",
        switch_source=source,
        metadata={"cwd": "/place/sub", **terminal},
    )
    assert archive_scope.doomed_rows([row], [Path("/place")]) == expected


@pytest.mark.parametrize("cwd", ["/elsewhere", "/place-sibling", ""])
def test_codex_rows_outside_the_released_directory_are_kept(cwd):
    row = db.Notification(id=1, channel="codex:daemon", message="", metadata={"cwd": cwd})
    assert archive_scope.doomed_rows([row], [Path("/place")]) == []
