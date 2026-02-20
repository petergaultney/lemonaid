"""Tests for lemonaid.opencode.notify module."""

from contextlib import contextmanager
from unittest.mock import patch

from lemonaid.opencode import notify


@contextmanager
def _fake_connect():
    yield object()


def test_handle_notification_from_event_payload():
    payload = '{"type":"session.idle","properties":{"sessionID":"ses_abc123"}}'

    with (
        patch("lemonaid.opencode.notify.db.connect", _fake_connect),
        patch(
            "lemonaid.opencode.notify.get_cwd_and_name",
            return_value=("/tmp/project", "Test Session"),
        ),
        patch("lemonaid.opencode.notify.get_tty", return_value="/dev/ttys001"),
        patch("lemonaid.opencode.notify.detect_terminal_switch_source", return_value="tmux"),
        patch("lemonaid.opencode.notify.get_git_branch", return_value="main"),
        patch("lemonaid.opencode.notify.db.add") as mock_add,
    ):
        notify.handle_notification(stdin_data=payload)

    kwargs = mock_add.call_args.kwargs
    assert kwargs["channel"] == "opencode:ses_abc123"
    assert kwargs["name"] == "Test Session"
    assert kwargs["message"] == "Waiting in tmp/project"
    assert kwargs["metadata"]["session_id"] == "ses_abc123"
    assert kwargs["metadata"]["tty"] == "/dev/ttys001"
    assert kwargs["switch_source"] == "tmux"
