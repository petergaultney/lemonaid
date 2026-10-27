import dataclasses
import subprocess

import pytest

from lemonaid import go
from lemonaid.inbox import db


def _row(channel="codex:a", socket="/test/socket"):
    return db.Notification(
        id=1,
        channel=channel,
        message="",
        switch_source="tmux",
        metadata={
            "tty": "/dev/target",
            "tmux_socket": socket,
            "tmux_session_order": [100, 90, 2],
            "tmux_pane_identity": ["%7", 90],
        },
    )


@pytest.mark.parametrize(
    "panes",
    [
        "%8|/dev/target|other|100|90|$2",  # reused tty
        "%7|/dev/target|work|100|91|$2",  # restarted server
        "",  # missing pane
    ],
)
def test_unavailable_targets_have_the_same_reason_as_direct_jumps(monkeypatch, panes):
    monkeypatch.setattr(go, "_tmux", lambda *args: panes)
    row = _row()
    with pytest.raises(LookupError) as error:
        go._pane([], row)
    assert go.jump_problems([row]) == {row.channel: str(error.value)}


def test_panes_are_read_once_per_server_and_renames_and_links_remain_jumpable(monkeypatch):
    calls = []

    def listed(*args):
        calls.append(args)
        return "%7|/dev/target|renamed|100|90|$2\n" * 2

    monkeypatch.setattr(go, "_tmux", listed)
    rows = [_row(), _row("codex:b"), _row("codex:c", "/other/server")]
    rows.append(dataclasses.replace(_row("headless"), switch_source=None))
    assert go.jump_problems(rows) == {}
    assert len(calls) == 2


def test_query_failure_and_missing_identity_explain_why_a_jump_is_unavailable(monkeypatch):
    def failed(*args):
        raise subprocess.TimeoutExpired("tmux", 5)

    monkeypatch.setattr(go, "_tmux", failed)
    assert "Cannot check" in go.jump_problems([_row()])["codex:a"]
    monkeypatch.setattr(go, "_tmux", lambda *args: "")
    assert "No recorded" in go.jump_problems([dataclasses.replace(_row(), metadata={})])["codex:a"]
