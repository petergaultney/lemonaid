"""Tests for lemonaid.claude.notify module."""

from contextlib import contextmanager
from unittest.mock import patch

from lemonaid.claude import notify


@contextmanager
def _fake_connect():
    yield object()


def test_handle_submit_registers_working():
    payload = '{"session_id":"abc123","cwd":"/tmp/project","hook_event_name":"UserPromptSubmit"}'

    with (
        patch("lemonaid.claude.notify.db.connect", _fake_connect),
        patch(
            "lemonaid.claude.notify.resolve_session_name",
            return_value=notify.SessionName("Test Session", notify.TITLE_SOURCE),
        ),
        patch("lemonaid.claude.notify.get_tmux_session_name", return_value=None),
        patch("lemonaid.claude.notify.get_tty", return_value="/dev/ttys001"),
        patch("lemonaid.claude.notify.detect_terminal_switch_source", return_value="tmux"),
        patch("lemonaid.claude.notify.get_git_branch", return_value="main"),
        patch("lemonaid.claude.notify.db.register_working") as mock_register,
    ):
        notify.handle_submit(stdin_data=payload)

    kwargs = mock_register.call_args.kwargs
    assert kwargs["channel"] == "claude:abc123"
    assert kwargs["name"] == "Test Session"
    assert kwargs["message"] == "Working in tmp/project"
    assert kwargs["metadata"]["session_id"] == "abc123"
    assert kwargs["metadata"]["tty"] == "/dev/ttys001"
    assert kwargs["switch_source"] == "tmux"


def test_handle_submit_headless_has_no_switch_source():
    payload = '{"session_id":"abc123","cwd":"/tmp/project"}'

    with (
        patch("lemonaid.claude.notify.db.connect", _fake_connect),
        patch("lemonaid.claude.notify.resolve_session_name", return_value=None),
        patch("lemonaid.claude.notify.get_tmux_session_name", return_value=None),
        patch("lemonaid.claude.notify.get_name_from_cwd", return_value="project"),
        patch("lemonaid.claude.notify.get_tty", return_value=None),
        patch("lemonaid.claude.notify.detect_terminal_switch_source", return_value="unknown"),
        patch("lemonaid.claude.notify.get_git_branch", return_value=None),
        patch("lemonaid.claude.notify.db.register_working") as mock_register,
    ):
        notify.handle_submit(stdin_data=payload)

    assert mock_register.call_args.kwargs["switch_source"] is None
